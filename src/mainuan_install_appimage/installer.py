from __future__ import annotations

import json
import fcntl
from contextlib import contextmanager
import os
import re
import stat
import subprocess
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage, QImageReader, QPainter

from .inspector import Inspection, InspectionError
from .categories import categories_field


class InstallationError(RuntimeError):
    """An installation could not safely be prepared or completed."""


@dataclass(frozen=True)
class InstallationState:
    kind: str
    installed_version: str = ""
    message: str = ""
    image_sha256: str = ""


def _command(arguments: list[str], timeout: int | None = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8",
                 **({"DPKG_FRONTEND_LOCKED": "1"} if os.environ.get("DPKG_FRONTEND_LOCKED") == "1" else {})},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InstallationError(f"Não foi possível consultar o gerenciador de pacotes: {error}") from error


def _package_query(package_name: str) -> tuple[bool, str, str]:
    result = _command(
        [
            "dpkg-query",
            "-W",
            "-f=${db:Status-Status}\t${Version}\t${Architecture}",
            "--",
            package_name,
        ]
    )
    if result.returncode == 1:
        return False, "", ""
    if result.returncode != 0:
        raise InstallationError("O dpkg-query falhou; não é seguro prosseguir.")
    fields = result.stdout.strip().split("\t")
    if len(fields) != 3:
        raise InstallationError("A resposta do dpkg-query está malformada.")
    if fields[0] not in ("installed", "config-files", "not-installed"):
        raise InstallationError("O pacote está em estado parcial no dpkg. Examine-o antes de prosseguir.")
    if fields[0] != "installed":
        return False, "", ""
    return True, fields[1], fields[2]


def _legacy_package_name(app_name: str) -> str:
    slug = unicodedata.normalize("NFKD", app_name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    return f"{slug or 'app'}appimage"


def installation_state(inspection: Inspection) -> InstallationState:
    installed, version, architecture = _package_query(inspection.package_name)
    marker = Path(
        "/usr/share/mainuan-install-appimage/managed/"
        f"{inspection.package_name}.json"
    )
    if installed:
        try:
            details = marker.lstat()
            if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
                raise ValueError("arquivo de identidade inválido")
            if details.st_uid != 0 or details.st_mode & 0o022 or details.st_size > 4096:
                raise ValueError("identidade sem proteção administrativa")
            owner = _command(["dpkg-query", "-S", "--", str(marker)])
            if owner.returncode or not any(line.partition(": ")[0] == inspection.package_name for line in owner.stdout.splitlines()):
                raise ValueError("identidade sem propriedade do pacote")
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("identidade malformada")
        except (OSError, ValueError, json.JSONDecodeError):
            return InstallationState(
                "conflict",
                message=(
                    "Já existe um pacote com este identificador que não foi instalado "
                    "por esta ferramenta. Ele será preservado."
                ),
            )
        if (
            metadata.get("managed_by") != "mainuan-install-appimage"
            or metadata.get("package") != inspection.package_name
            or metadata.get("desktop_identity") != inspection.desktop_identity
        ):
            return InstallationState(
                "conflict",
                message=(
                    "O identificador do pacote pertence a outra instalação. "
                    "Nenhum arquivo será substituído."
                ),
            )
        return InstallationState("managed", version, image_sha256=metadata.get("image_sha256", ""))

    legacy_name = _legacy_package_name(inspection.name)
    legacy_installed, _, _ = _package_query(legacy_name)
    if legacy_installed:
        legacy_owner = _command(
            [
                "dpkg-query",
                "-W",
                "-f=${Maintainer}",
                "--",
                legacy_name,
            ]
        )
        if legacy_owner.returncode == 0 and legacy_owner.stdout.strip() == "AppImage Installer":
            return InstallationState(
                "legacy",
                message=(
                    "Foi detectada uma instalação legada com este nome. "
                    "A base do dpkg e os arquivos existentes não serão reparados "
                    "automaticamente."
                ),
            )
    return InstallationState("new")


def _fallback_icon() -> QImage:
    candidates = (
        Path(__file__).with_name("AppImage.png"),
        Path(__file__).resolve().parents[1] / "AppImage.png",
        Path("/usr/share/mainuan-install-appimage/AppImage.png"),
    )
    for candidate in candidates:
        if candidate.is_file():
            image = QImage(str(candidate))
            if not image.isNull():
                return image
    raise InstallationError("O ícone de fallback do instalador não está disponível.")


def _load_icon(inspection: Inspection) -> QImage:
    QImageReader.setAllocationLimit(64)
    if inspection.icon_png:
        image = QImage.fromData(inspection.icon_png, b"PNG")
        if not image.isNull() and image.width() * image.height() <= 32_000_000:
            return image
    return _fallback_icon()


def _png_icon(inspection: Inspection, size: int) -> bytes:
    if os.geteuid() == 0:
        raise InstallationError("A conversão de ícones não pode executar como root.")
    source = _load_icon(inspection)
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not canvas.save(buffer, "PNG"):
        raise InstallationError("Não foi possível preparar os ícones do pacote.")
    return bytes(buffer.data())


def _desktop_value(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def package_paths(inspection: Inspection) -> tuple[str, ...]:
    package = inspection.package_name
    return (
        f"/opt/mainuan-appimages/{package}/AppImage",
        f"/usr/share/applications/{package}.desktop",
        f"/usr/share/icons/hicolor/64x64/apps/{package}.png",
        f"/usr/share/icons/hicolor/128x128/apps/{package}.png",
        f"/usr/share/mainuan-install-appimage/managed/{package}.json",
    )


def _write_package(inspection: Inspection, image_source: Path, root: Path, icons: dict[int, bytes] | None = None) -> None:
    try:
        categories = categories_field(inspection.categories)
    except ValueError as error:
        raise InstallationError(f"Categorias do lançador recusadas: {error}") from error
    application = root / "usr/share/applications"
    icon64 = root / "usr/share/icons/hicolor/64x64/apps"
    icon128 = root / "usr/share/icons/hicolor/128x128/apps"
    marker = root / "usr/share/mainuan-install-appimage/managed"
    image_dir = root / "opt/mainuan-appimages" / inspection.package_name
    for directory in (application, icon64, icon128, marker, image_dir):
        directory.mkdir(parents=True, exist_ok=True)

    image_target = image_dir / "AppImage"
    with image_source.open("rb") as source, image_target.open("xb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
    image_target.chmod(0o755)

    executable = f"/opt/mainuan-appimages/{inspection.package_name}/AppImage"
    desktop = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_desktop_value(inspection.name)}\n"
        f"Comment={_desktop_value(inspection.comment)}\n"
        f"Exec={executable} %F\n"
        f"TryExec={executable}\n"
        f"Icon={inspection.package_name}\n"
        "Terminal=false\n"
        f"Categories={categories}\n"
        "StartupNotify=true\n"
    )
    (application / f"{inspection.package_name}.desktop").write_text(
        desktop, encoding="utf-8"
    )
    (icon64 / f"{inspection.package_name}.png").write_bytes(icons[64] if icons is not None else _png_icon(inspection, 64))
    (icon128 / f"{inspection.package_name}.png").write_bytes(icons[128] if icons is not None else _png_icon(inspection, 128))
    marker_data = {
        "managed_by": "mainuan-install-appimage",
        "package": inspection.package_name,
        "desktop_identity": inspection.desktop_identity,
        "image_sha256": inspection.image_sha256,
    }
    (marker / f"{inspection.package_name}.json").write_text(
        json.dumps(marker_data, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    debian = root / "DEBIAN"
    debian.mkdir()
    (debian / "control").write_text(_control_contents(inspection), encoding="utf-8")


def _control_contents(inspection: Inspection) -> str:
    return "\n".join((
        f"Package: {inspection.package_name}",
        f"Version: {inspection.debian_version}",
        f"Architecture: {inspection.architecture}",
        "Priority: optional",
        "Section: misc",
        "Maintainer: Mainuan <openwebosbr@gmail.com>",
        f"Installed-Size: {max(1, (inspection.image_size + 1023) // 1024)}",
        "Description: Aplicativo AppImage instalado pelo Mainuan.",
        "",
    ))



def _check_destination_safety(inspection: Inspection, allow_existing: bool = False) -> None:
    for absolute in package_paths(inspection):
        path = Path(absolute)
        for parent in reversed(path.parents):
            if parent == Path("/"):
                continue
            try:
                details = parent.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o022:
                raise InstallationError(
                    f"O destino {parent} não é um diretório seguro."
                )

        try:
            target = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(target.st_mode) or not stat.S_ISREG(target.st_mode):
            raise InstallationError(f"O destino {path} já existe e não é um arquivo regular.")
        if not allow_existing:
            raise InstallationError(f"O destino {path} já existe sem uma instalação gerenciada válida.")
        owner = _command(["dpkg-query", "-S", "--", absolute])
        if owner.returncode != 0 or not any(
            line.partition(": ")[0] == inspection.package_name
            for line in owner.stdout.splitlines()
        ):
            raise InstallationError(
                f"O arquivo {path} não pertence a um pacote gerenciado por esta ferramenta."
            )


def build_deb(inspection: Inspection, image_source: Path, output_path: Path, icons: dict[int, bytes] | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mainuan-appimage-build-") as directory:
        root = Path(directory) / "package"
        root.mkdir(mode=0o755)
        # Canonical archive root even under the helper's umask 077; parent stays 0700.
        root.chmod(0o755)
        try:
            _write_package(inspection, image_source, root, icons)
        except (OSError, InspectionError) as error:
            raise InstallationError(f"Não foi possível preparar o pacote: {error}") from error
        for directory in root.rglob("*"):
            if directory.is_dir():
                directory.chmod(0o755)
            else:
                directory.chmod(0o755 if directory.name == "AppImage" else 0o644)
        result = _command(
            ["dpkg-deb", "--build", "--root-owner-group", str(root), str(output_path)],
            timeout=300,
        )
        if result.returncode != 0:
            raise InstallationError(
                "O dpkg-deb não conseguiu gerar o pacote: "
                + (result.stderr.strip() or result.stdout.strip() or "erro desconhecido")
            )
    return output_path


def validate_built_package(deb: Path, inspection: Inspection) -> None:
    """Check our root-owned build, never a package supplied by the caller."""
    import tarfile
    result = _command(["dpkg-deb", "-f", str(deb), "Package", "Version", "Architecture"])
    expected = [f"Package: {inspection.package_name}", f"Version: {inspection.debian_version}", f"Architecture: {inspection.architecture}"]
    if result.returncode or result.stdout.splitlines() != expected:
        raise InstallationError("O controle do pacote preparado não corresponde à instalação.")
    with tempfile.TemporaryFile() as control:
        result_binary = subprocess.run(["/usr/bin/dpkg-deb", "--ctrl-tarfile", str(deb)], stdout=control, stderr=subprocess.PIPE, timeout=30, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})
        if result_binary.returncode or control.tell() > 64 * 1024:
            raise InstallationError("Controle Debian inválido ou excessivo.")
        control.seek(0)
        with tarfile.open(fileobj=control, mode="r:") as archive:
            members = archive.getmembers()
            if len(members) != 2 or {entry.name for entry in members} != {".", "./control"} or any(entry.issym() or entry.islnk() for entry in members):
                raise InstallationError("O pacote contém arquivos de controle não permitidos.")
            for entry in members:
                if entry.uid != 0 or entry.gid != 0:
                    raise InstallationError("Propriedade do controle Debian inválida.")
                if entry.name == "./control":
                    if not entry.isfile() or entry.size > 4096 or entry.mode != 0o644:
                        raise InstallationError("Arquivo de controle Debian inválido.")
                    if archive.extractfile(entry).read() != _control_contents(inspection).encode():
                        raise InstallationError("Campos de controle Debian não permitidos.")
                elif not entry.isdir() or entry.mode != 0o755:
                    raise InstallationError("Diretório de controle Debian inválido.")
    _validate_data_manifest(deb, inspection)


def _validate_data_manifest(deb: Path, inspection: Inspection) -> None:
    """Stream our private build: no extraction, arbitrary paths, links or scripts.

    The input comes exclusively from build_deb in root's 0700 area, not from GUI.
    The watchdog is preparation-only; it never runs during a dpkg transaction.
    """
    import hashlib
    import tarfile
    import threading

    expected = {name.lstrip("/") for name in package_paths(inspection)}
    directories = {"."}
    for name in expected:
        directories.update(str(parent) for parent in Path(name).parents)
    seen = set()
    process = None
    timer = None
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                ["/usr/bin/dpkg-deb", "--fsys-tarfile", str(deb)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"},
            )
            timer = threading.Timer(300, process.kill)
            timer.daemon = True
            timer.start()
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                for count, entry in enumerate(archive, 1):
                    name = entry.name[2:] if entry.name.startswith("./") else entry.name
                    if name in seen or count > len(expected) + len(directories):
                        raise InstallationError("Manifesto Debian duplicado ou excessivo.")
                    seen.add(name)
                    if entry.uid or entry.gid or entry.issparse():
                        raise InstallationError("Metadados de propriedade Debian inválidos.")
                    if entry.isdir():
                        if name not in directories or entry.mode != 0o755 or entry.size != 0:
                            raise InstallationError("Diretório fora do manifesto permitido.")
                        continue
                    if name not in expected or not entry.isfile():
                        raise InstallationError("Arquivo ou link fora do manifesto permitido.")
                    binary = name.endswith("/AppImage")
                    if entry.mode != (0o755 if binary else 0o644):
                        raise InstallationError("Permissões de arquivo Debian inválidas.")
                    if entry.size < 0 or entry.size > (inspection.image_size if binary else 128 * 1024):
                        raise InstallationError("Tamanho fora do manifesto permitido.")
                    digest = hashlib.sha256()
                    with archive.extractfile(entry) as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if binary and (entry.size != inspection.image_size or digest.hexdigest() != inspection.image_sha256):
                        raise InstallationError("O AppImage no pacote não corresponde ao snapshot validado.")
            if seen != expected | directories or process.wait(timeout=30) != 0:
                raise InstallationError("Manifesto Debian incompleto ou inválido.")
    except (OSError, ValueError, tarfile.TarError, subprocess.TimeoutExpired) as error:
        raise InstallationError(f"Não foi possível validar os arquivos do pacote: {error}") from error
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def ensure_host_architecture(inspection: Inspection) -> None:
    result = _command(["dpkg", "--print-architecture"])
    if result.returncode != 0:
        raise InstallationError("Não foi possível identificar a arquitetura do sistema.")
    host_architecture = result.stdout.strip()
    if inspection.architecture != host_architecture:
        raise InstallationError(
            f"O AppImage é {inspection.architecture}, mas o sistema é {host_architecture}. "
            "A instalação foi cancelada."
        )


@contextmanager
def package_manager_lock():
    """Hold the frontend lock while validating ownership and invoking dpkg.

    dpkg still acquires its own database lock. No locks are deleted or bypassed.
    """
    descriptor = os.open("/var/lib/dpkg/lock-frontend", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o640)
    try:
        try:
            fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise InstallationError("O gerenciador de pacotes está ocupado. Tente novamente após a outra transação.") from error
        yield
    finally:
        os.close(descriptor)


def prepare_and_install(image_source: Path, expected_sha256: str) -> None:
    from .boundary import inspect_reduced

    print("STAGE:inspect", flush=True)
    inspection, icons = inspect_reduced(image_source, expected_sha256)
    if inspection.image_sha256 != expected_sha256:
        raise InstallationError(
            "O arquivo mudou desde a inspeção. Selecione-o novamente."
        )
    ensure_host_architecture(inspection)
    state = installation_state(inspection)
    if state.kind in ("conflict", "legacy"):
        raise InstallationError(state.message)
    _check_destination_safety(inspection, allow_existing=state.kind == "managed")

    with tempfile.TemporaryDirectory(
        prefix="mainuan-install-appimage-", dir="/var/tmp"
    ) as directory:
        deb = Path(directory) / f"{inspection.package_name}_{inspection.debian_version}_{inspection.architecture}.deb"
        print("STAGE:build", flush=True)
        build_deb(inspection, image_source, deb, icons)
        validate_built_package(deb, inspection)
        print("STAGE:install", flush=True)
        result = _command(["dpkg", "-i", str(deb)], timeout=None)
        if result.stdout.strip():
            print(result.stdout.strip(), flush=True)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "erro desconhecido"
            raise InstallationError(
                "O dpkg não concluiu a transação. A instalação anterior não foi removida "
                "previamente; o próprio dpkg pode deixar uma transação parcialmente "
                f"configurada. Detalhes: {message}"
            )
        print("Instalação concluída pelo dpkg.", flush=True)


def verify_staged_source(path_text: str, expected_sha256: str, invoking_uid: int) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise InstallationError("O identificador da cópia temporária é inválido.")
    runtime = Path(f"/run/user/{invoking_uid}")
    stage_dir = runtime / "mainuan-install-appimage"
    supplied = Path(path_text)
    if (
        not supplied.is_absolute()
        or supplied.parent != stage_dir
        or not re.fullmatch(r"payload-[0-9a-f]{32}\.AppImage", supplied.name)
    ):
        raise InstallationError("O arquivo não está na área temporária permitida.")
    try:
        runtime_fd = os.open(runtime, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            runtime_stat = os.fstat(runtime_fd)
            directory_fd = os.open("mainuan-install-appimage", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=runtime_fd)
            try:
                stage_stat = os.fstat(directory_fd)
                source_fd = os.open(supplied.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            os.close(runtime_fd)
        source_stat = os.fstat(source_fd)
    except OSError as error:
        raise InstallationError("Não foi possível validar o arquivo temporário seguro.") from error
    if (
        not stat.S_ISDIR(runtime_stat.st_mode)
        or stat.S_ISLNK(runtime_stat.st_mode)
        or runtime_stat.st_uid != invoking_uid
        or runtime_stat.st_mode & 0o077
        or not stat.S_ISDIR(stage_stat.st_mode)
        or stat.S_ISLNK(stage_stat.st_mode)
        or stage_stat.st_uid != invoking_uid
        or stat.S_IMODE(stage_stat.st_mode) != 0o700
        or not stat.S_ISREG(source_stat.st_mode)
        or source_stat.st_uid != invoking_uid
        or source_stat.st_mode & 0o077
        or source_stat.st_size > 8 * 1024**3
    ):
        os.close(source_fd)
        raise InstallationError("A área temporária ou o arquivo tem permissões inválidas.")
    return Path(f"/proc/self/fd/{source_fd}")


def copy_verified_source(source_fd_path: Path, destination: Path, expected_sha256: str) -> None:
    import hashlib

    digest = hashlib.sha256()
    copied = 0
    deadline = time.monotonic() + 300
    with source_fd_path.open("rb") as source, destination.open("xb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > 8 * 1024**3 or time.monotonic() > deadline:
                raise InstallationError("A cópia excedeu o limite de tamanho ou tempo.")
            digest.update(chunk)
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    if digest.hexdigest() != expected_sha256:
        destination.unlink(missing_ok=True)
        raise InstallationError("A cópia temporária não corresponde ao arquivo inspecionado.")
