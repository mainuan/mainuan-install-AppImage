"""Translations follow the session language, and boundary messages stay msgids.

The pt_BR catalog is compiled from po/pt_BR.po into a temporary directory and
selected through MAINUAN_INSTALL_APPIMAGE_LOCALEDIR, so this runs the real
lookup code without installing anything.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import QApplication

from mainuan_install_appimage import i18n
from mainuan_install_appimage.boundary import _parser_detail
from mainuan_install_appimage import gui
from mainuan_install_appimage.gui import MainWindow
from mainuan_install_appimage.i18n import Message, N_, parse_wire, render_line, wire_line
from mainuan_install_appimage.inspector import InspectionError, inspect_appimage
from mainuan_install_appimage.installer import InstallationError

ROOT = Path(__file__).resolve().parents[1]


def _set_language(value: str) -> None:
    os.environ["LANGUAGE"] = value
    i18n.reset()


class I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.locale = tempfile.TemporaryDirectory()
        target = Path(cls.locale.name) / "pt_BR" / "LC_MESSAGES"
        target.mkdir(parents=True)
        # Fails loudly without GNU gettext: an unchecked catalog is no test.
        subprocess.run(["msgfmt", "--check", "-o", str(target / f"{i18n.DOMAIN}.mo"),
                        str(ROOT / "po" / "pt_BR.po")], check=True)
        cls.saved = {key: os.environ.get(key) for key in ("LANGUAGE", i18n.LOCALEDIR_ENV)}
        os.environ[i18n.LOCALEDIR_ENV] = cls.locale.name

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        i18n.reset()
        cls.locale.cleanup()

    def tearDown(self):
        _set_language("C")

    def test_window_follows_language(self):
        for language, title, select, close in (
            ("pt_BR", "Instalador de AppImage", "Selecionar arquivo", "Fechar"),
            ("en", "AppImage Installer", "Select File", "Close"),
            ("C", "AppImage Installer", "Select File", "Close"),
        ):
            with self.subTest(language=language):
                _set_language(language)
                window = MainWindow()
                self.assertEqual(window.windowTitle(), title)
                self.assertEqual(window.select_button.text(), select)
                self.assertEqual(window.close_button.text(), close)
                window._install_finished(126, QProcess.ExitStatus.NormalExit)
                window.close()

    def test_right_to_left_catalog_mirrors_without_qtbase(self):
        for language in ("ar", "ur"):
            target = Path(self.locale.name) / language / "LC_MESSAGES"
            target.mkdir(parents=True, exist_ok=True)
            subprocess.run(["msgfmt", "--check", "-o", str(target / f"{i18n.DOMAIN}.mo"),
                            str(ROOT / "po" / f"{language}.po")], check=True)
        self.addCleanup(self.app.setLayoutDirection, Qt.LayoutDirection.LayoutDirectionAuto)
        with tempfile.TemporaryDirectory() as empty, \
                mock.patch.object(gui.QLibraryInfo, "path", return_value=empty):
            # Arabic application catalog, no qtbase_ar.qm: mirrored anyway.
            _set_language("ar")
            gui._install_qt_translator(self.app)
            self.assertEqual(self.app.layoutDirection(), Qt.LayoutDirection.RightToLeft)
            window = MainWindow()
            self.assertTrue(window.isRightToLeft())
            window.close()
            # Urdu has an application catalog but no qtbase_ur: mirrored by the catalog.
            self.app.setLayoutDirection(Qt.LayoutDirection.LayoutDirectionAuto)
            _set_language("ur")
            gui._install_qt_translator(self.app)
            self.assertEqual(self.app.layoutDirection(), Qt.LayoutDirection.RightToLeft)
            # Yiddish is right-to-left but has no application catalog: English, left to right.
            self.app.setLayoutDirection(Qt.LayoutDirection.LayoutDirectionAuto)
            _set_language("yi")
            gui._install_qt_translator(self.app)
            self.assertEqual(self.app.layoutDirection(), Qt.LayoutDirection.LeftToRight)

    def test_portuguese_ui_is_unchanged(self):
        _set_language("pt_BR")
        window = MainWindow()
        self.assertEqual(window.app_name.text(), "Nenhum aplicativo selecionado")
        self.assertEqual(window.status_label.text(), "Selecione um arquivo.")
        window._finish_failure("x", "")
        self.assertEqual(window.status_label.text(), "Instalação não concluída.")
        window._install_finished(1, QProcess.ExitStatus.NormalExit)
        self.assertEqual(window.step_label.text(), "A instalação não foi concluída.")
        self.assertEqual(window.details.toPlainText(), "Código de saída: 1.")
        window.close()

    def test_inspection_error_in_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            bogus = Path(temporary) / "bogus.AppImage"
            bogus.write_bytes(b"\0" * 128)
            for language, expected in (
                ("pt_BR", "Formato ou metadados: O arquivo não é um executável ELF."),
                ("en", "Format or metadata: The file is not an ELF executable."),
            ):
                _set_language(language)
                with self.assertRaises(InspectionError) as caught:
                    inspect_appimage(bogus)
                self.assertEqual(str(caught.exception), expected)

    def test_root_messages_cross_the_boundary_untranslated(self):
        error = InstallationError(
            N_("dpkg did not complete the transaction. The previous installation was not removed "
               "beforehand; dpkg itself may leave a partially configured transaction. "
               "Details: {details}"),
            details=Message(N_("unknown error")),
        )
        _set_language("pt_BR")
        i18n.disable_translation()  # what the root helper does
        line = wire_line(error)
        self.assertIn("unknown error", line)
        self.assertNotIn("desconhecido", line)
        self.assertTrue(str(error).endswith("Details: unknown error"))
        i18n.reset()  # back in the GUI, with the user's session language
        self.assertEqual(
            render_line(line),
            "O dpkg não concluiu a transação. A instalação anterior não foi removida previamente; "
            "o próprio dpkg pode deixar uma transação parcialmente configurada. Detalhes: erro desconhecido",
        )
        _set_language("en")
        self.assertTrue(render_line(line).endswith("Details: unknown error"))
        self.assertEqual(render_line("dpkg: raw output"), "dpkg: raw output")

    def test_gui_translates_helper_output(self):
        _set_language("pt_BR")
        window = MainWindow()
        window._messages = []
        window._process = None
        lines = [wire_line(Message(N_("File received and hash verified."))), "plain dpkg text"]
        window._messages.extend(render_line(line) for line in lines)
        self.assertEqual(window._messages, ["Arquivo recebido e hash conferido.", "plain dpkg text"])
        window.close()

    def test_parser_stderr_is_nested_only_when_well_formed(self):
        inner = InspectionError(N_("The .desktop file is malformed."))
        detail = _parser_detail((wire_line(inner) + "\n").encode())
        outer = InstallationError(
            N_("Unprivileged inspection failed: code={code}; limits CPU=120 s, address space=1073741824 bytes. {detail}"),
            code=1, detail=detail)
        _set_language("pt_BR")
        self.assertTrue(str(outer).endswith("Formato ou metadados: O arquivo .desktop está malformado."))
        self.assertEqual(_parser_detail(b"Traceback\nboom\n"), "Traceback\nboom\n")

    def test_wire_rejects_malformed_and_never_formats(self):
        self.assertIsNone(parse_wire("MESSAGE:{"))
        self.assertIsNone(parse_wire('MESSAGE:{"id":"x","args":{"a":1}}'))
        self.assertIsNone(parse_wire('MESSAGE:{"id":"x","args":{},"extra":1}'))
        deep = {"id": "{a}", "args": {}}
        for _level in range(10):
            deep = {"id": "{a}", "args": {"a": deep}}
        self.assertIsNone(parse_wire("MESSAGE:" + json.dumps(deep)))
        message = parse_wire('MESSAGE:{"id":"{a.__class__} {a!r} {b}","args":{"a":"v","b":"{a}"}}')
        _set_language("C")
        self.assertEqual(str(message), "{a.__class__} {a!r} {a}")

    def test_helper_cli_message_is_translated_for_regular_user(self):
        if os.geteuid() == 0:
            self.skipTest("the not-root branch only runs for regular users")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), LANGUAGE="pt_BR")
        for language, expected in (("pt_BR", "Este helper só pode ser iniciado pelo PolicyKit."),
                                   ("C", "This helper can only be started by PolicyKit.")):
            env["LANGUAGE"] = language
            result = subprocess.run([sys.executable, "-m", "mainuan_install_appimage.privileged"],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.strip(), expected)

    def test_potfiles_list_existing_sources(self):
        listed = [line.split()[-1] for line in (ROOT / "po" / "POTFILES.in").read_text().splitlines()
                  if line.strip() and not line.startswith("#")]
        self.assertTrue(listed)
        for name in listed:
            self.assertTrue((ROOT / name).is_file(), name)
        sources = {f"src/mainuan_install_appimage/{path.name}"
                   for path in (ROOT / "src" / "mainuan_install_appimage").glob("*.py")
                   if any(marker in path.read_text(encoding="utf-8") for marker in ('N_("', '_("'))}
        sources.discard("src/mainuan_install_appimage/i18n.py")
        self.assertEqual(sources - set(listed), set())


if __name__ == "__main__":
    unittest.main()
