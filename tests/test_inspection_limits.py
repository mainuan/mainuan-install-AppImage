"""Targeted SquashFS regressions; real filesystems, never execute an AppImage."""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mainuan_install_appimage import inspector as inspector
from mainuan_install_appimage.boundary import validate_response
from mainuan_install_appimage.installer import build_deb, validate_built_package
from mainuan_install_appimage.reduced import inspect_descriptor
from test_installer import make_appimage, _elf_header, _isolated_dpkg


def repack(base: Path, image: Path):
    sq = base / 'new.squashfs'
    subprocess.run(['mksquashfs', str(base / 'root'), str(sq), '-noappend', '-processors', '1', '-quiet', '-no-progress'], check=True, capture_output=True)
    image.write_bytes(_elf_header() + sq.read_bytes())


class TargetedInspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='mainuan-many-entries-')
        cls.base = Path(cls.temporary.name)
        cls.image = make_appimage(cls.base)
        bulk = cls.base / 'root/usr/lib/huge-application'
        bulk.mkdir(parents=True)
        for number in range(10_050):
            (bulk / f'file-{number:05}.txt').touch()
        repack(cls.base, cls.image)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_many_real_entries_small_metadata_and_package(self):
        real_reader = inspector._run_bounded
        calls = []
        def track(args, *positional, **kwargs):
            calls.append(args)
            return real_reader(args, *positional, **kwargs)
        with patch.object(inspector, '_run_bounded', side_effect=track):
            info = inspector.inspect_appimage(self.image)
        self.assertEqual(info.name, 'Editor de Teste')
        self.assertIsNotNone(info.icon_png)
        self.assertLess(len(calls), 12)
        root = calls[0]
        self.assertEqual(root[root.index('-max-depth') + 1], '1')
        self.assertTrue(all('-lln' in args or '-cat' in args for args in calls))
        self.assertFalse(any('huge-application' in ' '.join(args) for args in calls))
        # Package from independent parser protocol, without root-side image decoding.
        with self.image.open('rb') as source:
            data = inspect_descriptor(source.fileno())
        independent, icons = validate_response(json.dumps(data).encode(), self.image, info.image_sha256)
        with tempfile.TemporaryDirectory() as directory:
            package = build_deb(independent, self.image, Path(directory) / 'many.deb', icons)
            validate_built_package(package, independent)
            root = Path(directory) / "isolated-root"
            installed = _isolated_dpkg(root, ["--install", str(package)])
            self.assertEqual(installed.returncode, 0, installed.stderr)
            binary = root / "opt/mainuan-appimages" / independent.package_name / "AppImage"
            self.assertEqual(binary.read_bytes(), self.image.read_bytes())
            removed = _isolated_dpkg(root, ["--remove", independent.package_name])
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse(binary.exists())

    def test_large_root_really_exceeds_default_record_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image = make_appimage(base)
            for number in range(inspector.MAX_TREE_ENTRIES):
                (base / 'root' / f'root-{number:05}').touch()
            repack(base, image)
            with self.assertRaisesRegex(inspector.InspectionLimitError, r'registros.*observado=10001, limite=10000'):
                inspector.inspect_appimage(image)

    def test_duplicate_and_malformed_listing_are_not_silently_accepted(self):
        line = '-rw-r--r-- 1000/1000 10 2026-10-31 12:00 squashfs-root/a.desktop'
        for lines in (['not a listing'], [line, line]):
            def fake(args, limit, timeout, on_line):
                for record in lines:
                    on_line(record)
                return b''
            with self.subTest(lines=lines), patch.object(inspector, '_run_bounded', side_effect=fake):
                with self.assertRaises(inspector.InspectionToolError):
                    inspector._read_tree(self.image, 64)

    def test_listing_output_and_line_limits_are_incremental(self):
        with patch.object(inspector, 'MAX_TREE_OUTPUT', 100):
            with self.assertRaisesRegex(inspector.InspectionLimitError, 'stdout|listagens'):
                inspector._read_tree(self.image, 64)
        # Use an isolated Python producer instead of unsquashfs: real bounded pipes.
        with patch.object(inspector.shutil, 'which', return_value='/usr/bin/python3'):
            with self.assertRaisesRegex(inspector.InspectionLimitError, 'linha'):
                inspector._run_bounded(['unsquashfs', '-c', 'print("x"*5000)'], 10000, 5, on_line=lambda _: None)
            records = []
            captured = inspector._run_bounded(['unsquashfs', '-c', 'print("a"); print("b")'], 100, 5, on_line=records.append)
            self.assertEqual(records, ['a', 'b'])
            self.assertEqual(captured, b'')  # listing is not accumulated in memory

    def test_tool_exit_and_timeout_have_distinct_diagnostics(self):
        with patch.object(inspector.shutil, 'which', return_value='/usr/bin/python3'):
            with self.assertRaisesRegex(inspector.InspectionToolError, 'código 7.*test diagnostic'):
                inspector._run_bounded(['unsquashfs', '-c', 'import sys; print("test diagnostic", file=sys.stderr); sys.exit(7)'], 1000, 5)
            with self.assertRaisesRegex(inspector.InspectionLimitError, 'tempo.*limite=0.05'):
                inspector._run_bounded(['unsquashfs', '-c', 'import time; time.sleep(5)'], 1000, 0.05)

    def test_metadata_limit_is_failure_not_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image = make_appimage(base)
            (base / 'root/Editor.desktop').write_bytes(b'[Desktop Entry]\nName=Too big\n#' + b'x'*inspector.MAX_METADATA_SIZE)
            repack(base, image)
            with self.assertRaisesRegex(inspector.InspectionLimitError, 'desktop.*131072'):
                inspector.inspect_appimage(image)

    def test_exact_nested_symlinks_and_escape_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image = make_appimage(base)
            root = base / 'root'
            (root / 'usr/share/applications').mkdir(parents=True)
            (root / 'Editor.desktop').rename(root / 'usr/share/applications/Editor.desktop')
            (root / 'Editor.desktop').symlink_to('usr/share/applications/Editor.desktop')
            (root / '.DirIcon').symlink_to('test-icon.png')
            repack(base, image)
            tree = inspector._read_tree(image, 64)
            entry = inspector._resolve_entry('Editor.desktop', tree)
            self.assertEqual(entry.path, 'usr/share/applications/Editor.desktop')
            self.assertLess(tree.examined, 30)
            info = inspector.inspect_appimage(image)
            self.assertEqual(info.name, 'Editor de Teste')
            # Never resolve an absolute/escaping link into a host file.
            (root / 'Editor.desktop').unlink()
            (root / 'Editor.desktop').symlink_to('../../etc/passwd')
            repack(base, image)
            with self.assertRaisesRegex(inspector.InspectionError, 'link .desktop'):
                inspector.inspect_appimage(image)

    def test_query_depth_and_record_budget_preserve_operational_limits(self):
        with self.assertRaisesRegex(inspector.InspectionLimitError, "busca SquashFS"):
            inspector._find_superblocks(self.image, self.image.stat().st_size, time.monotonic() - 1)
        tree = inspector._read_tree(self.image, 64)
        with patch.object(inspector, 'MAX_LIST_QUERIES', tree.queries):
            with self.assertRaisesRegex(inspector.InspectionLimitError, 'consultas exatas'):
                tree.get('not-there')
        with self.assertRaisesRegex(inspector.InspectionLimitError, 'profundidade'):
            tree.get('/'.join(['dir']*13))

    def test_window_title_exact_in_loaded_progress_result_and_error(self):
        from PyQt6.QtWidgets import QApplication, QLabel
        from mainuan_install_appimage.gui import MainWindow
        from mainuan_install_appimage.installer import InstallationState
        from mainuan_install_appimage.staging import StagedImage
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        info = inspector.inspect_appimage(self.image)
        window._show_inspection(StagedImage(self.image, self.image, info), InstallationState('new'))
        self.assertEqual(window.windowTitle(), 'Instalador de AppImage')
        window._inspection_progress(window._generation, 'test')
        self.assertEqual(window.windowTitle(), 'Instalador de AppImage')
        window._show_result()
        self.assertEqual(window.windowTitle(), 'Instalador de AppImage')
        window._finish_failure('Falha.', 'limite excedido')
        self.assertEqual(window.windowTitle(), 'Instalador de AppImage')
        self.assertNotIn('Instalador de AppImage', [label.text() for label in window.findChildren(QLabel)])
        window.close()

    def test_no_root_reader_and_memory_cap_configured(self):
        with patch.object(inspector.shutil, 'which', return_value='/usr/bin/python3'):
            code = 'import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0])'
            output = inspector._run_bounded(['unsquashfs', '-c', code], 100, 5)
            self.assertEqual(int(output), 1024**3)
        # Root denial remains in the fresh reader; never change credentials here.
        self.assertIn('os.geteuid() == 0', inspector._READER_EXEC)
