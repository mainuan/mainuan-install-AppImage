from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QApplication

from mainuan_install_appimage.gui import MainWindow
from mainuan_install_appimage.inspector import InspectionError, inspect_appimage
from mainuan_install_appimage.installer import (
    InstallationError,
    _package_query,
    build_deb,
    installation_state,
    prepare_and_install,
    copy_verified_source,
    verify_staged_source,
    ensure_host_architecture,
    _check_destination_safety,
    package_paths,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "mainuan-appimage-editor-617d6b9c9b"


def _elf_header(machine: int = 62, elf_class: int = 2) -> bytes:
    header = bytearray(64)
    header[8:11] = b"AI\x02"
    header[:7] = b"\x7fELF" + bytes((elf_class, 1, 1))
    struct.pack_into("<HHI", header, 16, 3, machine, 1)
    struct.pack_into("<H", header, 40 if elf_class == 1 else 52, 52 if elf_class == 1 else 64)
    return bytes(header)


def make_appimage(
    directory: Path,
    *,
    version: str = "1.0",
    desktop: bytes | None = None,
    machine: int = 62,
    elf_class: int = 2,
    external_icon_link: bool = False,
) -> Path:
    root = directory / "root"
    root.mkdir(parents=True)
    if desktop is None:
        desktop = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name[pt_BR]=Editor de Teste\n"
            "Name=Test Editor\n"
            "Comment=Aplicativo de teste\n"
            f"X-AppImage-Version={version}\n"
            "Icon=test-icon\n"
            "Exec=malicious-command --do-not-copy\n"
        ).encode()
    (root / "Editor.desktop").write_bytes(desktop)
    icon_path = ROOT / "src/AppImage.png"
    (root / "test-icon.png").write_bytes(icon_path.read_bytes())
    if external_icon_link:
        os.symlink("../../../../outside.png", root / ".DirIcon")
    squashfs = directory / "filesystem.squashfs"
    subprocess.run(
        [
            "mksquashfs",
            str(root),
            str(squashfs),
            "-noappend",
            "-processors",
            "1",
            "-no-progress",
            "-quiet",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    image = directory / "sample.AppImage"
    image.write_bytes(_elf_header(machine, elf_class) + squashfs.read_bytes())
    return image


def _isolated_dpkg(root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    admin = root / "var/lib/dpkg"
    admin.mkdir(parents=True, exist_ok=True)
    (admin / "status").touch(exist_ok=True)
    return subprocess.run(
        [
            "dpkg",
            f"--log={root / 'dpkg.log'}",
            f"--root={root}",
            f"--admindir={admin}",
            f"--instdir={root}",
            "--force-not-root",
            "--force-script-chrootless",
            *arguments,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )


class InspectorTests(unittest.TestCase):
    def test_invalid_file_and_unvalidated_hsqs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "not-appimage"
            path.write_bytes(b"not an executable" * 8)
            with self.assertRaisesRegex(InspectionError, "ELF"):
                inspect_appimage(path)
            path.write_bytes(_elf_header() + b"random hsqs marker")
            with self.assertRaisesRegex(InspectionError, "Formato incompatível"):
                inspect_appimage(path)

    def test_incompatible_architecture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = make_appimage(Path(temporary), machine=3)
            with self.assertRaisesRegex(InspectionError, "Arquitetura incompatível"):
                inspect_appimage(image)

    def test_metadata_and_paths_with_spaces_accents_and_punctuation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="teste com ç & espaços ") as temporary:
            image = make_appimage(Path(temporary))
            renamed = Path(temporary) / "Aplicativo com acentos & espaços.AppImage"
            image.rename(renamed)
            result = inspect_appimage(renamed)
            self.assertEqual(result.name, "Editor de Teste")
            self.assertEqual(result.version, "1.0")
            self.assertEqual(result.architecture, "amd64")
            self.assertEqual(result.image_path, renamed.resolve())
            self.assertIsNotNone(result.icon_png)

    def test_missing_and_malformed_desktop_metadata_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            malformed = make_appimage(
                Path(temporary),
                desktop=b"[Desktop Entry]\nName=App\nmalformed-line\n",
            )
            with self.assertRaisesRegex(InspectionError, "malformado"):
                inspect_appimage(malformed)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir(parents=True)
            (root / "readme.txt").write_text("no desktop", encoding="utf-8")
            squashfs = Path(temporary) / "filesystem.squashfs"
            subprocess.run(
                [
                    "mksquashfs",
                    str(root),
                    str(squashfs),
                    "-noappend",
                    "-processors",
                    "1",
                    "-no-progress",
                    "-quiet",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            image = Path(temporary) / "missing-desktop.AppImage"
            image.write_bytes(_elf_header() + squashfs.read_bytes())
            with self.assertRaisesRegex(InspectionError, r"\.desktop"):
                inspect_appimage(image)

    def test_external_icon_symlink_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = make_appimage(Path(temporary), external_icon_link=True)
            result = inspect_appimage(image)
            self.assertIsNotNone(result.icon_png)
            self.assertFalse((Path(temporary) / "outside.png").exists())

    def test_architecture_package_identity_is_stable_across_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            one = Path(temporary) / "one"
            two = Path(temporary) / "two"
            one.mkdir()
            two.mkdir()
            first = inspect_appimage(make_appimage(one, version="1.0"))
            second = inspect_appimage(make_appimage(two, version="2.0"))
            self.assertEqual(first.package_name, second.package_name)
            self.assertNotEqual(first.debian_version, second.debian_version)


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication(["installer-tests"])

    def test_generated_deb_has_fixed_launcher_and_no_maintenance_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            image = make_appimage(directory)
            info = inspect_appimage(image)
            package = build_deb(info, image, directory / "app.deb")
            contents = subprocess.run(
                ["dpkg-deb", "--contents", str(package)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
            self.assertIn(f"/opt/mainuan-appimages/{info.package_name}/AppImage", contents)
            self.assertIn(f"/usr/share/applications/{info.package_name}.desktop", contents)
            control_tar = subprocess.run(
                ["dpkg-deb", "--ctrl-tarfile", str(package)],
                check=True,
                stdout=subprocess.PIPE,
            ).stdout
            import io
            import tarfile

            with tarfile.open(fileobj=io.BytesIO(control_tar)) as archive:
                control_files = {member.name for member in archive.getmembers()}
            self.assertEqual(control_files, {".", "./control"})
            extracted = subprocess.run(
                ["dpkg-deb", "-f", str(package), "Package", "Version", "Architecture"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.splitlines()
            extracted = [line.partition(": ")[2] for line in extracted]
            self.assertEqual(extracted, [info.package_name, info.debian_version, "amd64"])

            temporary_control = directory / "control"
            subprocess.run(
                ["dpkg-deb", "--control", str(package), str(temporary_control)],
                check=True,
                stdout=subprocess.PIPE,
            )
            control = (temporary_control / "control").read_text(encoding="utf-8")
            extracted_root = directory / "extracted"
            subprocess.run(["dpkg-deb", "-x", str(package), str(extracted_root)], check=True)
            launcher = (extracted_root / "usr/share/applications" / f"{info.package_name}.desktop").read_text()
            self.assertNotIn("malicious-command", launcher)
            self.assertIn(
                f"Exec=/opt/mainuan-appimages/{info.package_name}/AppImage %F",
                launcher,
            )

    def test_isolated_dpkg_install_replace_reinstall_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "isolated-root"
            first_dir = base / "first"
            second_dir = base / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first_image = make_appimage(first_dir, version="1.0")
            second_image = make_appimage(second_dir, version="2.0")
            first_info = inspect_appimage(first_image)
            second_info = inspect_appimage(second_image)
            first_deb = build_deb(first_info, first_image, base / "first.deb")
            second_deb = build_deb(second_info, second_image, base / "second.deb")
            self.assertEqual(first_info.package_name, second_info.package_name)

            installed = _isolated_dpkg(root, ["--install", str(first_deb)])
            self.assertEqual(installed.returncode, 0, installed.stderr + installed.stdout)
            installed_image = root / "opt/mainuan-appimages" / first_info.package_name / "AppImage"
            self.assertEqual(installed_image.read_bytes(), first_image.read_bytes())

            replaced = _isolated_dpkg(root, ["--install", str(second_deb)])
            self.assertEqual(replaced.returncode, 0, replaced.stderr + replaced.stdout)
            self.assertEqual(installed_image.read_bytes(), second_image.read_bytes())
            reinstalled = _isolated_dpkg(root, ["--install", str(second_deb)])
            self.assertEqual(reinstalled.returncode, 0, reinstalled.stderr + reinstalled.stdout)

            removed = _isolated_dpkg(root, ["--remove", first_info.package_name])
            self.assertEqual(removed.returncode, 0, removed.stderr + removed.stdout)
            self.assertFalse(installed_image.exists())
            for path in package_paths(first_info):
                self.assertFalse((root / path.lstrip("/")).exists(), path)

    def test_failed_preparation_does_not_touch_existing_package_or_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "isolated-root"
            image = make_appimage(base / "fixture")
            info = inspect_appimage(image)
            package = build_deb(info, image, base / "working.deb")
            installed = _isolated_dpkg(root, ["--install", str(package)])
            self.assertEqual(installed.returncode, 0, installed.stderr + installed.stdout)
            installed_image = root / "opt/mainuan-appimages" / info.package_name / "AppImage"
            original = installed_image.read_bytes()

            with self.assertRaises(InstallationError):
                build_deb(info, base / "does-not-exist.AppImage", base / "failed.deb")
            self.assertEqual(installed_image.read_bytes(), original)
            status = _isolated_dpkg(root, ["--status", info.package_name])
            self.assertEqual(status.returncode, 0)
            self.assertIn("Status: install ok installed", status.stdout)

    def test_unmanaged_package_identity_is_reported_as_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            info = inspect_appimage(make_appimage(Path(temporary)))
            with patch(
                "mainuan_install_appimage.installer._package_query",
                return_value=(True, "1.0", "amd64"),
            ):
                state = installation_state(info)
            self.assertEqual(state.kind, "conflict")
            self.assertIn("preservado", state.message)

    def test_authentication_refusal_is_not_reported_as_success(self) -> None:
        window = MainWindow()
        window._install_finished(126, QProcess.ExitStatus.NormalExit)
        self.assertIn("não foi concluída", window.step_label.text())
        self.assertNotIn("Instalação concluída", window.status_label.text())
        window.close()


    def test_ui_distinguishes_install_reinstall_and_replacement(self):
        from mainuan_install_appimage.installer import InstallationState
        from mainuan_install_appimage.staging import StagedImage
        with tempfile.TemporaryDirectory() as temporary:
            image = make_appimage(Path(temporary))
            info = inspect_appimage(image)
            staged = StagedImage(image, image, info)
            window = MainWindow()
            for state, button in ((InstallationState("new"), "Instalar"), (InstallationState("managed", info.debian_version, image_sha256=info.image_sha256), "Reinstalar"), (InstallationState("managed", info.debian_version, image_sha256="0" * 64), "Substituir versão")):
                window._show_inspection(staged, state)
                self.assertEqual(window.install_button.text(), button)
                self.assertNotIn("atualização", window.status_label.text().lower())
            window.close()

    def test_staging_and_cancellation_discard_payload(self):
        from mainuan_install_appimage.staging import stage_and_inspect, remove_staged
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir(mode=0o700)
            image = make_appimage(Path(temporary) / "fixture")
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}):
                staged = stage_and_inspect(image)
                self.assertEqual(staged.staged_path.read_bytes(), image.read_bytes())
                remove_staged(staged.staged_path)
                self.assertFalse(staged.staged_path.exists())
                with self.assertRaisesRegex(InspectionError, "cancelada"):
                    stage_and_inspect(image, cancelled=lambda: True)
                self.assertEqual(list((runtime / "mainuan-install-appimage").iterdir()), [])

    def test_crashed_helper_with_zero_exit_is_failure(self):
        window = MainWindow()
        window._install_finished(0, QProcess.ExitStatus.CrashExit)
        self.assertTrue(window.open_button.isHidden())
        self.assertIn("não concluída", window.status_label.text())
        window.close()

    def test_identity_collision_between_apps_with_same_desktop_basename(self):
        with tempfile.TemporaryDirectory() as temporary:
            a = make_appimage(Path(temporary) / "a")
            b = make_appimage(Path(temporary) / "b", desktop=b"[Desktop Entry]\nName=Unrelated App\n")
            first, second = inspect_appimage(a), inspect_appimage(b)
            self.assertEqual(first.package_name, second.package_name)
            self.assertNotEqual(first.desktop_identity, second.desktop_identity)

    def test_marker_identity_mismatch_is_a_conflict(self):
        from types import SimpleNamespace
        import json
        with tempfile.TemporaryDirectory() as temporary:
            info = inspect_appimage(make_appimage(Path(temporary)))
            marker = {"managed_by": "mainuan-install-appimage", "package": info.package_name, "desktop_identity": "unrelated"}
            owner = subprocess.CompletedProcess([], 0, info.package_name + ": /marker", "")
            with patch("mainuan_install_appimage.installer._package_query", return_value=(True, "1", "amd64")), patch("pathlib.Path.lstat", return_value=SimpleNamespace(st_mode=0o100644, st_uid=0, st_size=256)), patch("pathlib.Path.read_text", return_value=json.dumps(marker)), patch("mainuan_install_appimage.installer._command", return_value=owner):
                self.assertEqual(installation_state(info).kind, "conflict")
                marker["desktop_identity"] = info.desktop_identity
                marker["image_sha256"] = info.image_sha256
            with patch("mainuan_install_appimage.installer._package_query", return_value=(True, "1", "amd64")), patch("pathlib.Path.lstat", return_value=SimpleNamespace(st_mode=0o100644, st_uid=0, st_size=256)), patch("pathlib.Path.read_text", return_value=json.dumps(marker)), patch("mainuan_install_appimage.installer._command", return_value=owner):
                self.assertEqual(installation_state(info).kind, "managed")

    def test_partial_dpkg_state_is_not_treated_as_absent(self):
        result = subprocess.CompletedProcess([], 0, "unpacked\t1.0\tamd64", "")
        with patch("mainuan_install_appimage.installer._command", return_value=result):
            with self.assertRaisesRegex(InstallationError, "parcial"):
                _package_query("mainuan-appimage-example")

    def test_legacy_package_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            info = inspect_appimage(make_appimage(Path(temporary)))
            result = subprocess.CompletedProcess([], 0, "AppImage Installer", "")
            with patch("mainuan_install_appimage.installer._package_query", side_effect=[(False, "", ""), (True, "01", "amd64")]), patch("mainuan_install_appimage.installer._command", return_value=result):
                self.assertEqual(installation_state(info).kind, "legacy")

    def test_host_architecture_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            info = inspect_appimage(make_appimage(Path(temporary)))
            with patch("mainuan_install_appimage.installer._command", return_value=subprocess.CompletedProcess([], 0, "arm64\n", "")):
                with self.assertRaisesRegex(InstallationError, "sistema é arm64"):
                    ensure_host_architecture(info)

    def test_root_copy_rejects_changed_payload_and_arbitrary_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.write_bytes(b"changed data")
            target = Path(temporary) / "snapshot"
            with self.assertRaisesRegex(InstallationError, "não corresponde"):
                copy_verified_source(source, target, "0" * 64)
            self.assertFalse(target.exists())
            with self.assertRaisesRegex(InstallationError, "área temporária"):
                verify_staged_source(str(source), "0" * 64, os.getuid())

    def test_manager_lock_and_install_failure_propagate(self):
        from mainuan_install_appimage.installer import InstallationState
        for reason in ("dpkg frontend lock is locked", "simulated unpack failure"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                image = make_appimage(Path(temporary))
                info = inspect_appimage(image)
                failure = subprocess.CompletedProcess([], 2, "", reason)
                with patch("mainuan_install_appimage.boundary.inspect_reduced", return_value=(info, {64: b"", 128: b""})), patch("mainuan_install_appimage.installer.ensure_host_architecture"), patch("mainuan_install_appimage.installer.installation_state", return_value=InstallationState("new")), patch("mainuan_install_appimage.installer._check_destination_safety"), patch("mainuan_install_appimage.installer.build_deb"), patch("mainuan_install_appimage.installer.validate_built_package"), patch("mainuan_install_appimage.installer._command", return_value=failure):
                    with self.assertRaisesRegex(InstallationError, reason):
                        prepare_and_install(image, info.image_sha256)

    def test_crash_or_auth_failure_does_not_offer_open(self):
        for code in (1, 126, 127):
            window = MainWindow()
            window._install_finished(code, QProcess.ExitStatus.NormalExit)
            self.assertTrue(window.open_button.isHidden())
            self.assertIn("não concluída", window.status_label.text())
            window.close()

    def test_untrusted_text_stays_plain_and_large_font_layout(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QLabel
        window = MainWindow()
        font = window.font()
        font.setPointSize(20)
        window.setFont(font)
        window.show()
        self.application.processEvents()
        for label in window.findChildren(QLabel):
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)
        window.close()


if __name__ == "__main__":
    unittest.main()
