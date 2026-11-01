from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QApplication, QLabel

from mainuan_install_appimage.boundary import validate_response
from mainuan_install_appimage.gui import MainWindow, DISPLAY_NAME
from mainuan_install_appimage.installer import InstallationError, InstallationState, build_deb, validate_built_package
from mainuan_install_appimage.reduced import inspect_descriptor, restrict_process
from mainuan_install_appimage.staging import StagedImage
from test_installer import make_appimage


class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parser_protocol_and_package_without_root_image_decoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = make_appimage(Path(temporary))
            with source.open('rb') as stream:
                data = inspect_descriptor(stream.fileno())
            info, icons = validate_response(json.dumps(data).encode(), source, data['image_sha256'])
            with patch('mainuan_install_appimage.installer._png_icon', side_effect=AssertionError('root must not decode')):
                deb = build_deb(info, source, Path(temporary) / 'app.deb', icons)
            validate_built_package(deb, info)
            for key, value in [('package_name', '../../foreign'), ('name', 'App\nExec=/bin/evil'), ('debian_version', '1\nDepends: evil'), ('architecture', 'all'), ('image_path', '/etc/shadow'), ('image_sha256', '0'*64)]:
                invalid = copy.deepcopy(data)
                invalid[key] = value
                with self.subTest(key=key), self.assertRaises(InstallationError):
                    validate_response(json.dumps(invalid).encode(), source, data['image_sha256'])

    def test_helper_requests_real_credential_drop_and_clean_environment(self):
        from mainuan_install_appimage.boundary import inspect_reduced
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            source = make_appimage(Path(temporary))
            with patch('mainuan_install_appimage.boundary.pwd.getpwnam', return_value=SimpleNamespace(pw_uid=65534, pw_gid=65534)), patch('mainuan_install_appimage.boundary.os.chown'), patch('mainuan_install_appimage.boundary.subprocess.Popen', side_effect=PermissionError('simulated credential operation')) as popen:
                with self.assertRaises(InstallationError):
                    inspect_reduced(source, '0'*64)
                options = popen.call_args.kwargs
                self.assertEqual(options['user'], 65534)
                self.assertEqual(options['group'], 65534)
                self.assertEqual(options['extra_groups'], [])
                self.assertTrue(options['start_new_session'])
                self.assertEqual(options['cwd'], '/')
                self.assertEqual(set(options['env']), {'PATH', 'LC_ALL', 'HOME', 'TMPDIR'})
                self.assertIn('-I', popen.call_args.args[0])

    def test_restriction_rejects_root_or_supplementary_groups(self):
        with patch('os.getresuid', return_value=(0, 65534, 0)), patch('os.getresgid', return_value=(65534,)*3), patch('os.getgroups', return_value=[]):
            with self.assertRaises(RuntimeError):
                restrict_process()
        with patch('os.getresuid', return_value=(65534,)*3), patch('os.getresgid', return_value=(65534,)*3), patch('os.getgroups', return_value=[123]):
            with self.assertRaises(RuntimeError):
                restrict_process()

    def test_minimal_loaded_ui_and_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = make_appimage(Path(temporary))
            with source.open('rb') as stream:
                data = inspect_descriptor(stream.fileno())
            info, _ = validate_response(json.dumps(data).encode(), source, data['image_sha256'])
            window = MainWindow()
            window._show_inspection(StagedImage(source, source, info), InstallationState('new'))
            window.show()
            self.app.processEvents()
            self.assertTrue(window.select_button.isHidden())
            self.assertTrue(window.status_label.isHidden())
            self.assertTrue(window.app_name.font().bold())
            self.assertTrue(window.install_button.isDefault())
            self.assertLess(window.install_button.x(), window.close_button.x())
            self.assertEqual(window.windowTitle(), DISPLAY_NAME)
            texts = ' '.join(label.text() for label in window.findChildren(QLabel))
            self.assertNotIn(DISPLAY_NAME, texts)
            self.assertNotIn(str(source), texts)
            self.assertNotIn('Não instalado', texts)
            window._show_inspection(StagedImage(source, source, replace(info, version='Não informada')), InstallationState('new'))
            self.assertTrue(window.app_details.isHidden())
            window._show_result()
            self.app.processEvents()
            self.assertLess(window.open_button.x(), window.close_button.x())
            window.close()

    def test_error_details_collapsed_and_initial_picker_cancel_closes(self):
        window = MainWindow()
        window.show()
        window._finish_failure('A instalação não foi concluída.', 'dpkg: /var/tmp/private/file')
        self.assertTrue(window.details.isHidden())
        self.assertNotIn('/var/tmp', window.step_label.text())
        window.details_button.click()
        self.assertFalse(window.details.isHidden())
        with patch('mainuan_install_appimage.gui.QFileDialog.getOpenFileName', return_value=('', '')):
            window._choose_file()
        self.assertFalse(window.isVisible())

    def test_close_during_transaction_is_ignored(self):
        window = MainWindow()
        window.show()
        from unittest.mock import Mock
        process = Mock()
        process.state.return_value = QProcess.ProcessState.Running
        window._process = process
        self.assertFalse(window.close())
        self.assertTrue(window.isVisible())
        process.kill.assert_not_called()
        process.terminate.assert_not_called()
        window._process = None
        window.close()


if __name__ == '__main__':
    unittest.main()
