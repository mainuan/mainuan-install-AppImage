"""Package integration in disposable dpkg roots, never the host database."""
import os
import subprocess
import tempfile
import unittest
from fnmatch import fnmatchcase
from pathlib import Path
from unittest.mock import patch, Mock

from PyQt6.QtWidgets import QApplication
from mainuan_install_appimage.gui import MainWindow, main
from mainuan_install_appimage.installer import package_manager_lock, InstallationError
from test_installer import ROOT, _isolated_dpkg


def _binary_stanza() -> dict[str, str]:
    """Fields of the binary package in debian/control (continuation lines joined)."""
    stanzas, current, key = [], {}, None
    for line in (ROOT / 'debian/control').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            if current:
                stanzas.append(current)
            current, key = {}, None
        elif line[0] in ' \t' and key:
            current[key] += ' ' + line.strip()
        else:
            key, _, value = line.partition(':')
            current[key] = value.strip()
    if current:
        stanzas.append(current)
    return next(stanza for stanza in stanzas if stanza.get('Package') == 'mainuan-install-appimage')


def _stand_in_package(base: Path) -> Path:
    """The package is built after the tests (dpkg-buildpackage), so dpkg is given
    a package with the relations declared in debian/control and the launcher
    path. Set MAINUAN_INSTALL_APPIMAGE_DEB to check a built .deb instead."""
    stanza = _binary_stanza()
    tree = base / 'new'
    (tree / 'DEBIAN').mkdir(parents=True)
    fields = ['Package: mainuan-install-appimage', 'Version: 0', 'Architecture: all',
              'Maintainer: Test <test@example.invalid>']
    fields += [f'{name}: {stanza[name]}' for name in ('Provides', 'Conflicts', 'Replaces')]
    fields.append('Description: stand-in with the relations of debian/control')
    (tree / 'DEBIAN/control').write_text('\n'.join(fields) + '\n')
    desktop = tree / 'usr/share/applications/mainuan-install-appimage.desktop'
    desktop.parent.mkdir(parents=True)
    desktop.write_bytes((ROOT / 'packaging/mainuan-install-appimage.desktop').read_bytes())
    deb = base / 'new.deb'
    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(tree), str(deb)], check=True, stdout=subprocess.PIPE)
    return deb


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gui_refuses_root_before_creating_application(self):
        with patch('os.geteuid', return_value=0), patch('mainuan_install_appimage.gui.QApplication') as app:
            self.assertEqual(main(), 1)
            app.assert_not_called()

    def test_open_is_explicit_and_never_uses_pkexec(self):
        window = MainWindow()
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'app'
            binary.touch()
            window._installed_application = binary
            with patch('os.geteuid', return_value=1000), patch('mainuan_install_appimage.gui.QProcess.startDetached', return_value=(True, 123)) as start:
                start.assert_not_called()
                window._open_application()
                self.assertEqual(start.call_args.args[0], str(binary))
                self.assertNotIn('pkexec', str(start.call_args))
            with patch('os.geteuid', return_value=0), patch('mainuan_install_appimage.gui.QProcess.startDetached') as start:
                window._open_application()
                start.assert_not_called()
        window.close()

    def test_frontend_lock_busy_is_reported_without_touching_real_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'lock'
            real_open = os.open
            def isolated_open(path, flags, mode):
                self.assertEqual(path, '/var/lib/dpkg/lock-frontend')
                return real_open(lock, flags, mode)
            with patch('mainuan_install_appimage.installer.os.open', side_effect=isolated_open), patch('fcntl.lockf', side_effect=BlockingIOError):
                with self.assertRaisesRegex(InstallationError, 'busy'):
                    with package_manager_lock():
                        self.fail('must not acquire busy lock')

    def test_mime_with_spaces_and_accents_in_isolated_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            mime = base / 'mime'
            (mime / 'packages').mkdir(parents=True)
            (mime / 'packages/mainuan-appimage.xml').write_bytes((ROOT / 'packaging/appimage-mime.xml').read_bytes())
            subprocess.run(['update-mime-database', str(mime)], check=True, capture_output=True)
            globs = (mime / 'globs2').read_text(encoding='utf-8').splitlines()
            patterns = [
                fields[2]
                for line in globs
                if not line.startswith('#')
                for fields in [line.split(':', 2)]
                if len(fields) == 3 and fields[1] == 'application/vnd.appimage'
            ]
            self.assertTrue(any(fnmatchcase('Aplicativo com espaços e ação.AppImage'.casefold(), pattern.casefold()) for pattern in patterns))
            self.assertTrue(any(fnmatchcase('Aplicativo com espaços e ação.appimage'.casefold(), pattern.casefold()) for pattern in patterns))

    def test_old_installer_transition_removes_only_its_owned_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            old = base / 'old'
            (old / 'DEBIAN').mkdir(parents=True)
            (old / 'DEBIAN/control').write_text('Package: appimage-installer\nVersion: 99.0\nArchitecture: all\nMaintainer: Test <test@example.invalid>\nDescription: isolated legacy installer fixture\n')
            launcher = old / 'usr/share/applications/AppImage-Installer.desktop'
            launcher.parent.mkdir(parents=True)
            launcher.write_text('[Desktop Entry]\nType=Application\nName=Old fixture\nExec=/usr/tigertools/AppImage-Installer %F\n')
            old_deb = base / 'old.deb'
            subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(old), str(old_deb)], check=True, stdout=subprocess.PIPE)
            new_deb = Path(os.environ.get('MAINUAN_INSTALL_APPIMAGE_DEB') or _stand_in_package(base))
            root = base / 'root'
            installed = _isolated_dpkg(root, ['-i', str(old_deb)])
            self.assertEqual(installed.returncode, 0, installed.stderr)
            # Simulates an unrelated/unregistered launcher; the transition must not remove it.
            unrelated = root / 'usr/share/applications/other-handler.desktop'
            unrelated.write_text('preserve other handler')
            replaced = _isolated_dpkg(root, ['--unpack', str(new_deb)])
            self.assertEqual(replaced.returncode, 0, replaced.stderr + replaced.stdout)
            self.assertFalse((root / launcher.relative_to(old)).exists())
            self.assertTrue((root / 'usr/share/applications/mainuan-install-appimage.desktop').exists())
            self.assertEqual(unrelated.read_text(), 'preserve other handler')
            control = subprocess.run(['dpkg-deb', '-f', str(new_deb)], check=True, capture_output=True, text=True).stdout
            self.assertIn('Conflicts: appimage-installer', control)
