"""Capture real Qt Widgets with simulated states; no auth or transaction.

PYTHONPATH=src:tests QT_QPA_PLATFORM=wayland python3 tests/capture_ui.py --theme light
"""
import argparse
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--theme', choices=['system', 'light', 'dark'], default='system')
parser.add_argument('--large', action='store_true')
parser.add_argument('--decoration', action='store_true', help='Capture our active window with Spectacle, if available')
parser.add_argument('--output', type=Path, default=Path('dist/captures/consolidation'))
args = parser.parse_args()
settings = None
if args.theme != 'system':
    scheme = Path('/usr/share/color-schemes') / ('BreezeLight.colors' if args.theme == 'light' else 'BreezeDark.colors')
    if not scheme.is_file():
        parser.error('Esquema KDE não disponível: ' + str(scheme))
    settings = tempfile.TemporaryDirectory(prefix='mainuan-installer-theme-')
    shutil.copyfile(scheme, Path(settings.name) / 'kdeglobals')
    os.environ['XDG_CONFIG_HOME'] = settings.name
    os.environ['KDE_COLOR_SCHEME_PATH'] = str(scheme)
    os.environ['QT_QPA_PLATFORMTHEME'] = 'kde'

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from mainuan_install_appimage.gui import MainWindow
from mainuan_install_appimage.installer import InstallationState
from mainuan_install_appimage.reduced import inspect_descriptor
from mainuan_install_appimage.boundary import validate_response
from mainuan_install_appimage.staging import StagedImage
from test_installer import make_appimage

app = QApplication([])
if args.large:
    font = app.font()
    font.setPointSize(20)
    app.setFont(font)
platform = app.platformName()
mode = args.theme + ('-large' if args.large else '')
args.output.mkdir(parents=True, exist_ok=True)
fixture = tempfile.TemporaryDirectory()
source = make_appimage(Path(fixture.name))
with source.open('rb') as stream:
    data = inspect_descriptor(stream.fileno())
info, _ = validate_response(json.dumps(data).encode(), source, data['image_sha256'])
window = MainWindow()
staged = StagedImage(source, source, info)
failures = []


def show_state(state):
    window.close_button.setEnabled(True)
    window._show_inspection(staged, InstallationState('new'))
    window._staged = None
    if state == 'reinstall':
        window._show_inspection(staged, InstallationState('managed', info.debian_version, image_sha256=info.image_sha256))
    if state == 'replace':
        window._show_inspection(staged, InstallationState('managed', '0.9', image_sha256='0' * 64))
    if state == 'progress':
        window.install_button.hide()
        window.close_button.setEnabled(False)
        window.step_label.setText('Instalando…')
        window.step_label.show()
        window.progress.show()
    if state == 'result':
        window._show_result()
    if state == 'error':
        window._finish_failure('A instalação não foi concluída.', 'dpkg: falha simulada em /var/tmp/arquivo-interno')
    window.show()
    window.adjustSize()


states = iter(['loaded', 'progress', 'result', 'reinstall', 'replace', 'error'])

def next_state():
    try:
        state = next(states)
    except StopIteration:
        window.close()
        app.quit()
        return
    show_state(state)
    def capture():
        try:
            app.processEvents()
            assert window.windowTitle() == "Instalador de AppImage"
            print("title:", repr(window.windowTitle()), "active:", window.isActiveWindow(), flush=True)
            assert window.grab().save(str(args.output / f'{platform}-{mode}-{state}.png'))
            if state == 'loaded' and args.decoration and platform == 'wayland':
                if window.isActiveWindow() and shutil.which('spectacle'):
                    subprocess.run(['spectacle', '-a', '-b', '-n', '-S', '-o', str((args.output / f'{platform}-{mode}-decoration.png').resolve())], check=True, timeout=10, capture_output=True)
                else:
                    print('Decoration capture pending: our window is not active or Spectacle unavailable.', flush=True)
            if state == 'loaded':
                assert window.install_button.x() < window.close_button.x()
                assert window.select_button.isHidden()
                assert window.status_label.isHidden()
                assert window.step_label.isHidden()
            if state == 'result':
                assert window.open_button.x() < window.close_button.x()
            if state == 'error':
                assert window.details.isHidden()
                assert window.details_button.isVisible()
                assert '/var/tmp' not in window.step_label.text()
            print(platform, mode, state, 'buttons:', [(b.text(), b.x()) for b in (window.install_button, window.open_button, window.close_button) if b.isVisible()], flush=True)
            QTimer.singleShot(40, next_state)
        except Exception as error:
            failures.append(str(error))
            app.exit(1)
    QTimer.singleShot(350, capture)

print('Platform:', platform, 'desktop:', os.environ.get('XDG_CURRENT_DESKTOP'), 'background:', app.palette().window().color().name(), 'font:', app.font().pointSize(), flush=True)
QTimer.singleShot(0, next_state)
QTimer.singleShot(15000, lambda: app.exit(2))
result = app.exec()
fixture.cleanup()
if settings:
    settings.cleanup()
for failure in failures:
    print('FAIL:', failure)
raise SystemExit(result or bool(failures))
