"""Hostile package fixtures are validated only, never installed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from mainuan_install_appimage.boundary import validate_response
from mainuan_install_appimage.gui import MainWindow
from mainuan_install_appimage.installer import (
    InstallationError, InstallationState, _png_icon, _write_package, validate_built_package,
)
from mainuan_install_appimage.inspector import inspect_appimage, InspectionError
from mainuan_install_appimage.staging import StagedImage
from test_installer import make_appimage


class HardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_data_manifest_rejects_extra_links_modes_and_modified_image(self):
        for attack in ('extra', 'link', 'mode', 'image', 'control', 'script'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                source = make_appimage(base / 'source')
                info = inspect_appimage(source)
                root = base / 'package'
                root.mkdir(mode=0o755)
                _write_package(info, source, root)
                binary = root / 'opt/mainuan-appimages' / info.package_name / 'AppImage'
                if attack == 'extra':
                    (root / 'etc').mkdir()
                    (root / 'etc/unapproved').write_text('not permitted')
                elif attack == 'link':
                    binary.unlink()
                    binary.symlink_to('/etc/shadow')
                elif attack == 'mode':
                    binary.chmod(0o4755)
                elif attack == 'image':
                    with binary.open('r+b') as stream:
                        stream.write(b'BAD!')
                elif attack == 'control':
                    with (root / 'DEBIAN/control').open('a') as stream:
                        stream.write('Replaces: unrelated-package\n')
                else:
                    script = root / 'DEBIAN/postinst'
                    script.write_text('#!/bin/sh\nexit 0\n')
                    script.chmod(0o755)
                package = base / 'hostile.deb'
                subprocess.run(['/usr/bin/dpkg-deb', '--build', '--root-owner-group', str(root), str(package)], check=True, capture_output=True)
                with self.assertRaises(InstallationError):
                    validate_built_package(package, info)

    def test_deb_renamed_as_appimage_is_not_an_installable_input(self):
        from mainuan_install_appimage.installer import build_deb
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = make_appimage(base / 'source')
            info = inspect_appimage(source)
            package = build_deb(info, source, base / 'arbitrary.AppImage')
            with self.assertRaisesRegex(InspectionError, 'ELF'):
                inspect_appimage(package)

    def test_build_and_validation_with_administrative_private_umask(self):
        import stat
        from mainuan_install_appimage.installer import build_deb
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = make_appimage(base / 'source')
            info = inspect_appimage(source)
            previous = os.umask(0o077)
            try:
                package = build_deb(info, source, base / 'private.deb')
                validate_built_package(package, info)
            finally:
                os.umask(previous)
            self.assertEqual(stat.S_IMODE(base.stat().st_mode), 0o700)

    def test_root_icon_decoding_is_fail_closed(self):
        with patch('os.geteuid', return_value=0):
            with self.assertRaisesRegex(InstallationError, 'root'):
                _png_icon(None, 64)

    def test_protocol_duplicate_and_deep_json_fail_cleanly(self):
        for raw in (b'{"name":"first","name":"second"}', b'[' * 2000 + b'0' + b']' * 2000):
            with self.subTest(raw=raw[:30]), self.assertRaises(InstallationError):
                validate_response(raw, Path('/not-opened'), '0' * 64)

    def test_invalid_declared_version_is_not_shown_or_inferred_from_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = make_appimage(Path(temporary), version='1.0 garbage')
            renamed = source.with_name('Editor-99.0.AppImage')
            source.rename(renamed)
            info = inspect_appimage(renamed)
            self.assertEqual(info.version, 'Não informada')
            self.assertTrue(info.debian_version.startswith('0~'))

    def test_button_order_is_left_to_right_even_with_rtl_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = make_appimage(Path(temporary))
            info = inspect_appimage(source)
            window = MainWindow()
            window.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            window._show_inspection(StagedImage(source, source, info), InstallationState('new'))
            window.show()
            self.app.processEvents()
            self.assertLess(window.install_button.mapTo(window, window.install_button.rect().topLeft()).x(), window.close_button.mapTo(window, window.close_button.rect().topLeft()).x())
            self.assertTrue(window.step_label.isHidden())
            self.assertTrue(window.select_button.isHidden())
            self.assertTrue(window.status_label.isHidden())
            window._show_result()
            self.app.processEvents()
            self.assertLess(window.open_button.x(), window.close_button.x())
            window.close()
