"""Package integration in disposable dpkg roots, never the host database."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PyQt6.QtWidgets import QApplication
from mainuan_install_appimage.gui import MainWindow, main
from mainuan_install_appimage.installer import package_manager_lock, InstallationError
from test_installer import ROOT, _isolated_dpkg


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
                with self.assertRaisesRegex(InstallationError, 'ocupado'):
                    with package_manager_lock():
                        self.fail('must not acquire busy lock')

    def test_mime_with_spaces_and_accents_in_isolated_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            mime = base / 'mime'
            (mime / 'packages').mkdir(parents=True)
            (mime / 'packages/mainuan-appimage.xml').write_bytes((ROOT / 'packaging/appimage-mime.xml').read_bytes())
            subprocess.run(['update-mime-database', str(mime)], check=True, capture_output=True)
            source = base / 'Aplicativo com espaços e ação.AppImage'
            source.write_bytes(__import__('test_installer').make_appimage(base / 'fixture').read_bytes())
            env = dict(os.environ, XDG_DATA_HOME=str(base), XDG_DATA_DIRS='/usr/local/share:/usr/share')
            result = subprocess.run(['xdg-mime', 'query', 'filetype', str(source)], env=env, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'application/vnd.appimage')
            lower = source.with_suffix('.appimage')
            source.rename(lower)
            result = subprocess.run(['xdg-mime', 'query', 'filetype', str(lower)], env=env, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'application/vnd.appimage')

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
            new_deb = base / 'new.deb'
            subprocess.run(['bash', str(ROOT / 'build.sh'), str(new_deb)], check=True, stdout=subprocess.PIPE)
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
