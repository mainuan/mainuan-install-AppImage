"""Category preservation, hostile values and Debian launcher replacement."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mainuan_install_appimage.categories import normalize_categories, validate_categories
from mainuan_install_appimage.inspector import _parse_desktop, inspect_appimage, InspectionError
from mainuan_install_appimage.boundary import validate_response
from mainuan_install_appimage.installer import build_deb, validate_built_package, InstallationError
from mainuan_install_appimage.reduced import inspect_descriptor
from test_installer import ROOT, make_appimage, _isolated_dpkg

KDENLIVE = ('Qt', 'KDE', 'AudioVideo', 'AudioVideoEditing')
FIXTURE = Path(__file__).with_name('fixtures') / 'kdenlive-categories.desktop'


class CategoryTests(unittest.TestCase):
    def test_original_multimedia_categories_preserved(self):
        self.assertEqual(_parse_desktop(FIXTURE.read_bytes(), 'editor.desktop')['categories'], KDENLIVE)
        # Name-independent normalization; no application-specific special case.
        self.assertEqual(normalize_categories('Qt;KDE;AudioVideo;AudioVideoEditing;'), KDENLIVE)

    def test_other_categories_and_valid_relevant_tokens(self):
        for raw, expected in (
            ('Development;IDE;Qt;', ('Development', 'IDE', 'Qt')),
            ('Graphics;2DGraphics;RasterGraphics;', ('Graphics', '2DGraphics', 'RasterGraphics')),
            ('Office;Spreadsheet;', ('Office', 'Spreadsheet')),
            ('Network;WebBrowser;X-Unregistered;', ('Network', 'WebBrowser')),
            ('Graphics;IDE;', ('Graphics',)),
            ('Video;Player;', ('Video', 'Player', 'AudioVideo')),
            ('IDE;', ('IDE', 'Development')),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_categories(raw), expected)
                self.assertEqual(validate_categories(list(expected)), expected)

    def test_absent_unknown_and_malformed_fields_use_neutral_category(self):
        for value in ('', 'Unregistered;', 'audioVideo;', 'AudioVideo', 'AudioVideo;;Video;', 'Audio Video;', ';', 'AudioVideo;\t', 'AudioVideo;\r', 'x;' * 33, 'x' * 1025):
            with self.subTest(value=value):
                self.assertEqual(normalize_categories(value), ('Utility',))
        self.assertEqual(_parse_desktop(b'[Desktop Entry]\nName=App\n', 'app.desktop')['categories'], ('Utility',))

    def test_injection_cannot_create_desktop_fields(self):
        for malicious in ('AudioVideo;\nExec=/bin/evil', 'AudioVideo;\rIcon=evil', 'AudioVideo;\\nExec=/bin/evil', '[Desktop Action Evil];', 'AudioVideo;$(touch /tmp/evil);'):
            with self.subTest(malicious=malicious):
                self.assertEqual(normalize_categories(malicious), ('Utility',))
        # Desktop escape sequences are decoded before category validation.
        metadata = _parse_desktop(b'[Desktop Entry]\nName=App\nCategories=AudioVideo;\\nExec=/bin/evil\n', 'app.desktop')
        self.assertEqual(metadata['categories'], ('Utility',))
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image = make_appimage(base, desktop=b'[Desktop Entry]\nName=App\nCategories=AudioVideo;\\nExec=/bin/evil\nExec=/bin/also-evil\n')
            info = inspect_appimage(image)
            package = build_deb(info, image, base / 'safe.deb')
            subprocess.run(['dpkg-deb', '-x', str(package), str(base / 'unpacked')], check=True)
            desktop = (base / 'unpacked/usr/share/applications' / f'{info.package_name}.desktop').read_text()
            self.assertIn('Categories=Utility;\n', desktop)
            self.assertNotIn('/bin/evil', desktop)
            self.assertNotIn('/bin/also-evil', desktop)
            self.assertEqual(sum(line.startswith('Exec=') for line in desktop.splitlines()), 1)

    def test_categories_round_trip_and_admin_rejects_hostile_or_missing_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = make_appimage(Path(temporary), desktop=FIXTURE.read_bytes())
            with image.open('rb') as stream:
                response = inspect_descriptor(stream.fileno())
            self.assertEqual(tuple(response['categories']), KDENLIVE)
            inspection, _ = validate_response(json.dumps(response).encode(), image, response['image_sha256'])
            self.assertEqual(inspection.categories, KDENLIVE)
            for hostile in ([], ['AudioVideo\nExec=/bin/evil'], ['Utility', 'unknown'], ['AudioVideo', 'AudioVideo'], ['Video'], 'AudioVideo;', [42], ['x'] * 33, ['Utility', 'IDE']):
                malformed = copy.deepcopy(response)
                malformed['categories'] = hostile
                with self.subTest(hostile=hostile), self.assertRaises(InstallationError):
                    validate_response(json.dumps(malformed).encode(), image, response['image_sha256'])
            missing = dict(response)
            missing.pop('categories')
            with self.assertRaises(InstallationError):
                validate_response(json.dumps(missing).encode(), image, response['image_sha256'])
            with self.assertRaises(InstallationError):
                build_deb(replace(inspection, categories=('AudioVideo\nExec=/bin/evil',)), image, Path(temporary) / 'bad.deb')

    def test_reinstallation_replaces_launcher_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image = make_appimage(base / 'image', desktop=FIXTURE.read_bytes())
            inspection = inspect_appimage(image)
            previous = replace(inspection, categories=('Utility',))  # old fixed behavior
            old_deb = build_deb(previous, image, base / 'before.deb')
            new_deb = build_deb(inspection, image, base / 'after.deb')
            validate_built_package(new_deb, inspection)
            root = base / 'dpkg-root'
            before = _isolated_dpkg(root, ['--install', str(old_deb)])
            self.assertEqual(before.returncode, 0, before.stderr)
            desktop = root / 'usr/share/applications' / f'{inspection.package_name}.desktop'
            self.assertIn('Categories=Utility;\n', desktop.read_text())
            after = _isolated_dpkg(root, ['--install', str(new_deb)])
            self.assertEqual(after.returncode, 0, after.stderr)
            self.assertIn('Categories=Qt;KDE;AudioVideo;AudioVideoEditing;\n', desktop.read_text())
            self.assertNotIn('Categories=Utility;', desktop.read_text())
            self.assertEqual(len(list(desktop.parent.glob('*.desktop'))), 1)
            self.assertEqual(previous.package_name, inspection.package_name)
            self.assertEqual(previous.debian_version, inspection.debian_version)
            self.assertEqual(previous.image_sha256, inspection.image_sha256)
            if shutil.which('desktop-file-validate'):
                result = subprocess.run(['desktop-file-validate', str(desktop)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.skipTest('desktop-file-validate unavailable (replacement checks executed)')

    def test_other_application_category_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image = make_appimage(base / 'fixture', desktop=b'[Desktop Entry]\nName=Planilha de teste\nCategories=Office;Spreadsheet;\n')
            with image.open('rb') as source:
                response = inspect_descriptor(source.fileno())
            info, icons = validate_response(json.dumps(response).encode(), image, response['image_sha256'])
            self.assertEqual(info.categories, ('Office', 'Spreadsheet'))
            package = build_deb(info, image, base / 'office.deb', icons)
            validate_built_package(package, info)
            subprocess.run(['dpkg-deb', '-x', str(package), str(base / 'unpacked')], check=True)
            desktop = base / 'unpacked/usr/share/applications' / f'{info.package_name}.desktop'
            self.assertIn('Categories=Office;Spreadsheet;\n', desktop.read_text())
            if shutil.which('desktop-file-validate'):
                result = subprocess.run(['desktop-file-validate', str(desktop)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_kdenlive_metadata_when_available(self):
        image = Path('/home/daigo/Downloads/kdenlive-26.08.2-x86_64.AppImage')
        if not image.is_file():
            self.skipTest('Original Kdenlive fixture not available here')
        info = inspect_appimage(image)
        self.assertEqual(info.categories, KDENLIVE)
