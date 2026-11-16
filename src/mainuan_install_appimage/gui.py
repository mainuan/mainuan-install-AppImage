from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QLibraryInfo, QLocale, QObject, QProcess, QRunnable, QThreadPool, QTimer, QTranslator, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .i18n import N_, _, pgettext, render_line
from .inspector import InspectionError
from .installer import InstallationError, installation_state
from .staging import StagedImage, remove_staged, stage_and_inspect


DISPLAY_NAME = N_("AppImage Installer")
PRIVILEGED_HELPER = "/usr/lib/mainuan-install-appimage/privileged-install"


class _WorkerSignals(QObject):
    progress = pyqtSignal(int, str)
    completed = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)


class _InspectionWorker(QRunnable):
    def __init__(self, generation: int, source: str) -> None:
        super().__init__()
        self.generation = generation
        self.source = source
        self.cancelled = threading.Event()
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = stage_and_inspect(
                self.source,
                lambda message: self.signals.progress.emit(self.generation, message),
                self.cancelled.is_set,
            )
            try:
                from .installer import ensure_host_architecture
                ensure_host_architecture(result.inspection)
                state = installation_state(result.inspection)
            except Exception:
                remove_staged(result.staged_path)
                raise
            if self.cancelled.is_set():
                remove_staged(result.staged_path)
                return
            self.signals.completed.emit(self.generation, (result, state))
        except (InspectionError, InstallationError, OSError, ValueError) as error:
            self.signals.failed.emit(self.generation, str(error))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_(DISPLAY_NAME))
        self.setWindowIcon(QIcon.fromTheme("mainuan-install-appimage", QIcon.fromTheme("package-x-generic")))
        self.setMinimumWidth(440)
        self.resize(440, 190)
        self._pool = QThreadPool.globalInstance()
        self._generation = 0
        self._worker: _InspectionWorker | None = None
        self._staged: StagedImage | None = None
        self._process: QProcess | None = None
        self._messages: list[str] = []
        self._build_ui()
        icon_path = Path(__file__).with_name("AppImage.png")
        if not icon_path.is_file():
            icon_path = Path(__file__).resolve().parents[1] / "AppImage.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._show_selection()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        app_row = QHBoxLayout()
        self.icon = QLabel(central)
        self.icon.setFixedSize(72, 72)
        self.icon.setScaledContents(False)
        app_row.addWidget(self.icon, 0)
        text_column = QVBoxLayout()
        self.app_name = QLabel(central)
        self.app_name.setWordWrap(True)
        self.app_name.setObjectName("applicationName")
        font = self.app_name.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.25)
        self.app_name.setFont(font)
        self.app_details = QLabel(central)
        self.app_details.setWordWrap(True)
        text_column.addWidget(self.app_name)
        text_column.addWidget(self.app_details)
        app_row.addLayout(text_column, 1)
        layout.addLayout(app_row)

        self.status_label = QLabel(central)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.step_label = QLabel(central)
        self.step_label.setWordWrap(True)
        layout.addWidget(self.step_label)
        self.progress = QProgressBar(central)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)

        self.details = QPlainTextEdit(central)
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(180)
        layout.addWidget(self.details)
        self.details_button = QPushButton(_("Show Details"), central)
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.details.setVisible)
        layout.addWidget(self.details_button)
        self.details.hide()
        self.details_button.hide()
        layout.addStretch(1)
        button_bar = QWidget(central)
        button_bar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        buttons = QHBoxLayout(button_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        self.select_button = QPushButton(_("Select File"), central)
        self.cancel_button = QPushButton(pgettext("@action:button", "Cancel"), central)
        self.install_button = QPushButton(pgettext("@action:button", "Install"), central)
        self.install_button.setDefault(True)
        self.open_button = QPushButton(_("Open Application"), central)
        self.close_button = QPushButton(pgettext("@action:button", "Close"), central)
        for button in (
            self.select_button,
            self.cancel_button,
            self.install_button,
            self.open_button,
            self.close_button,
        ):
            buttons.addWidget(button)
        layout.addWidget(button_bar)
        QWidget.setTabOrder(self.install_button, self.close_button)
        QWidget.setTabOrder(self.open_button, self.close_button)
        for label in central.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setCentralWidget(central)

        self.select_button.clicked.connect(self._choose_file)
        self.cancel_button.clicked.connect(self._cancel_inspection)
        self.install_button.clicked.connect(self._start_install)
        self.open_button.clicked.connect(self._open_application)
        self.close_button.clicked.connect(self.close)

    def _show_selection(self, message: str | None = None) -> None:
        if message is None:
            message = _("Select a file.")
        self.icon.clear()
        self.app_name.setText(_("No application selected"))
        self.app_details.clear()
        self.details.hide()
        self.details_button.setChecked(False)
        self.details_button.hide()
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))
        self.step_label.clear()
        self.progress.hide()
        self.select_button.show()
        self.select_button.setEnabled(True)
        self.cancel_button.hide()
        self.install_button.hide()
        self.open_button.hide()
        self.close_button.show()

    def _choose_file(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Select AppImage"),
            str(Path.home()),
            ";;".join((_("AppImages (*.AppImage *.appimage)"), _("All Files (*)"))),
        )
        if file_path:
            self.inspect_file(file_path)
        else:
            self.close()

    def inspect_file(self, file_path: str) -> None:
        if self._worker:
            self._worker.cancelled.set()
        if self._staged:
            remove_staged(self._staged.staged_path)
            self._staged = None
        self._generation += 1
        generation = self._generation
        self._show_selection("")
        self.app_name.clear()

        self.step_label.show()
        self.step_label.setText(_("Preparing…"))
        self.progress.show()
        self.select_button.hide()
        self.cancel_button.show()
        self._worker = _InspectionWorker(generation, file_path)
        self._worker.signals.progress.connect(self._inspection_progress)
        self._worker.signals.completed.connect(self._inspection_completed)
        self._worker.signals.failed.connect(self._inspection_failed)
        self._pool.start(self._worker)

    def _inspection_progress(self, generation: int, message: str) -> None:
        if generation == self._generation:
            self.step_label.setText(_("Inspecting…"))

    def _inspection_completed(self, generation: int, result: object) -> None:
        if not isinstance(result, tuple):
            return
        staged, state = result
        if not isinstance(staged, StagedImage):
            return
        if generation != self._generation:
            remove_staged(staged.staged_path)
            return
        self._staged = staged
        self._show_inspection(staged, state)

    def _inspection_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._finish_failure(_("Could not inspect the file."), message)
        self.cancel_button.hide()
        self.select_button.setEnabled(True)
        if self._staged:
            remove_staged(self._staged.staged_path)
            self._staged = None

    def _show_inspection(self, staged: StagedImage, state: object) -> None:
        info = staged.inspection
        self.app_name.setText(info.name)
        self.app_details.setText(_("Version: {version}").format(version=info.version) if info.version != "Não informada" else "")
        self.app_details.setVisible(bool(self.app_details.text()))

        self.step_label.clear()
        self.step_label.hide()
        self.status_label.clear()
        self.status_label.hide()
        pixmap = QPixmap()
        if info.icon_png:
            pixmap.loadFromData(info.icon_png, "PNG")
        if pixmap.isNull():
            fallback = Path(__file__).with_name("AppImage.png")
            if not fallback.is_file():
                fallback = Path(__file__).resolve().parents[1] / "AppImage.png"
            if not fallback.is_file():
                fallback = Path("/usr/share/mainuan-install-appimage/AppImage.png")
            pixmap.load(str(fallback))
        if not pixmap.isNull():
            self.icon.setPixmap(
                pixmap.scaled(
                    64,
                    64,
                    aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                    transformMode=Qt.TransformationMode.SmoothTransformation,
                )
            )

        if state.kind == "new":
            self.status_label.clear()
            install_text = pgettext("@action:button", "Install")
            can_install = True
        elif state.kind == "managed":
            if state.image_sha256 == info.image_sha256:
                self.status_label.setText(_("The application will be reinstalled."))
                install_text = pgettext("@action:button", "Reinstall")
            else:
                self.status_label.setText(_("The current installation will be replaced."))
                install_text = pgettext("@action:button", "Replace Version")
            can_install = True
        else:
            self.status_label.setText(str(state.message))
            install_text = pgettext("@action:button", "Install")
            can_install = False

        self.status_label.setVisible(bool(self.status_label.text()))
        self.progress.hide()
        self.select_button.hide()
        self.cancel_button.hide()
        self.install_button.setText(install_text)
        self.install_button.setEnabled(can_install)
        self.install_button.show()
        self.install_button.setDefault(True)
        self.install_button.setFocus()
        self.open_button.hide()
        self.close_button.show()
        self.adjustSize()

    def _cancel_inspection(self) -> None:
        if self._worker:
            self._worker.cancelled.set()
        self._generation += 1
        self.step_label.setText(_("Inspection canceled."))
        if self._staged:
            remove_staged(self._staged.staged_path)
            self._staged = None
        self.progress.hide()
        self.cancel_button.hide()
        self.select_button.show()
        self.select_button.setEnabled(True)
        self.install_button.hide()

    def _start_install(self) -> None:
        if not self._staged or (self._process and self._process.state() != QProcess.ProcessState.NotRunning):
            return
        self.install_button.hide()
        self.select_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.open_button.hide()
        self.progress.show()
        self.step_label.show()
        self.step_label.setText(
            _("Waiting for authentication…")
        )
        self.status_label.hide()
        self._messages = []
        self._stdout_tail = ""
        self._process = QProcess(self)
        self._process.setProgram("/usr/bin/pkexec")
        self._process.setArguments(
            [
                PRIVILEGED_HELPER,
                "--install",
                str(self._staged.staged_path),
                self._staged.inspection.image_sha256,
            ]
        )
        self._process.readyReadStandardOutput.connect(self._read_process_output)
        self._process.readyReadStandardError.connect(self._read_process_error)
        self._process.finished.connect(self._install_finished)
        self._process.errorOccurred.connect(self._process_error)
        self._process.start()

    def _read_process_output(self) -> None:
        if not self._process:
            return
        text = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        text = getattr(self, "_stdout_tail", "") + text
        lines = text.split("\n")
        self._stdout_tail = lines.pop()
        for line in lines:
            self._messages.append(render_line(line))
            self._messages = self._messages[-80:]
            stages = {"STAGE:inspect": _("Verifying…"), "STAGE:build": _("Preparing installation…"), "STAGE:install": _("Installing…")}
            if line in stages:
                self.step_label.setText(stages[line])

    def _read_process_error(self) -> None:
        if not self._process:
            return
        text = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        self._messages.extend(render_line(line) for line in text.splitlines() if line)
        self._messages = self._messages[-80:]

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish_failure(_("Could not start PolicyKit."))

    def _install_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._read_process_output()
        self._read_process_error()
        if self._staged:
            remove_staged(self._staged.staged_path)
        if exit_code == 0 and _exit_status == QProcess.ExitStatus.NormalExit:
            self._show_result()
        elif exit_code in (126, 127):
            self._finish_failure(
                _("Authentication was denied or canceled. The installation was not completed.")
            )
        else:
            detail = "\n".join(self._messages[-80:]).strip()
            self._finish_failure(
                _("The installation was not completed."),
                detail or _("Exit code: {code}.").format(code=exit_code)
            )

    def _finish_failure(self, message: str, details: str = "") -> None:
        if self._staged:
            remove_staged(self._staged.staged_path)
            self._staged = None
        self.progress.hide()
        self.step_label.setText(message)
        self.step_label.show()
        self.status_label.setText(_("Installation not completed."))
        self.status_label.hide()
        self.details.setPlainText(details)
        self.details.hide()
        self.details_button.setChecked(False)
        self.details_button.setVisible(bool(details))
        self.cancel_button.hide()
        self.select_button.hide()
        self.install_button.hide()
        self.open_button.hide()
        self.close_button.show()
        self.close_button.setEnabled(True)
        if self._process:
            self._process.deleteLater()
            self._process = None

    def _show_result(self) -> None:
        staged = self._staged
        self._staged = None
        self.progress.hide()
        self.status_label.setText(_("Installation completed."))
        self.status_label.show()
        self.step_label.clear()
        self.step_label.hide()
        if staged:
            self.app_name.setText(staged.inspection.name)
            self.app_details.setText(_("Version: {version}").format(version=staged.inspection.version) if staged.inspection.version != "Não informada" else "")
            self._installed_application = Path(
                "/opt/mainuan-appimages"
                f"/{staged.inspection.package_name}/AppImage"
            )
        self.select_button.hide()
        self.cancel_button.hide()
        self.install_button.hide()
        self.open_button.show()
        self.open_button.setDefault(True)
        self.open_button.setFocus()
        self.close_button.show()
        self.close_button.setEnabled(True)
        if self._process:
            self._process.deleteLater()
            self._process = None

    def _open_application(self) -> None:
        if os.geteuid() == 0:
            return
        application = getattr(self, "_installed_application", None)
        if not application or not application.is_file():
            QMessageBox.warning(
                self,
                _(DISPLAY_NAME),
                _("The installed file is not available to be opened."),
            )
            return
        started, _pid = QProcess.startDetached(str(application), [], str(Path.home()))
        if not started:
            QMessageBox.warning(
                self,
                _(DISPLAY_NAME),
                _("Could not start the application as a regular user."),
            )

    def closeEvent(self, event) -> None:
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self.step_label.setText(_("Wait for the operation to finish."))
            self.step_label.show()
            event.ignore()
            return
        self._generation += 1
        if self._worker:
            self._worker.cancelled.set()
        if self._staged:
            remove_staged(self._staged.staged_path)
            self._staged = None
        event.accept()


def _install_qt_translator(application: QApplication) -> None:
    """Standard Qt dialogs (file picker, message box buttons) in the session language."""
    translator = QTranslator(application)
    if translator.load(QLocale.system(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        application.installTranslator(translator)
        application._mainuan_qt_translator = translator


def main() -> int:
    if os.geteuid() == 0:
        print(_("Run the interface as a regular user."), file=sys.stderr)
        return 1
    application = QApplication(sys.argv[:1])
    _install_qt_translator(application)
    application.setApplicationName("mainuan-install-appimage")
    application.setApplicationDisplayName(_(DISPLAY_NAME))
    application.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    supplied = sys.argv[1:]
    if len(supplied) > 1:
        window._show_selection(_("Provide only one AppImage file at a time."))
        QTimer.singleShot(0, window._choose_file)
    elif supplied:
        QTimer.singleShot(0, lambda: window.inspect_file(supplied[0]))
    else:
        QTimer.singleShot(0, window._choose_file)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
