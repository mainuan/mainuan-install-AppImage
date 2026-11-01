from __future__ import annotations

import hashlib
import os
import re
import stat
import uuid
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .inspector import MAX_IMAGE_SIZE, Inspection, InspectionError, inspect_appimage


@dataclass(frozen=True)
class StagedImage:
    original_path: Path
    staged_path: Path
    inspection: Inspection


def _runtime_directory() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise InspectionError("O ambiente não fornece um diretório temporário seguro.")
    runtime_path = Path(runtime)
    try:
        details = runtime_path.lstat()
    except OSError as error:
        raise InspectionError("O diretório temporário seguro não está disponível.") from error
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
    ):
        raise InspectionError("O diretório temporário seguro tem permissões inválidas.")
    return runtime_path


def stage_and_inspect(
    source_path: str | Path,
    progress: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> StagedImage:
    source = Path(source_path).resolve(strict=True)
    try:
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise InspectionError(f"Não foi possível ler o arquivo selecionado: {error}") from error

    try:
        parent = _runtime_directory() / "mainuan-install-appimage"
    except Exception:
        os.close(source_fd)
        raise
    try:
        parent.mkdir(mode=0o700, exist_ok=True)
        parent_stat = parent.lstat()
    except OSError as error:
        os.close(source_fd)
        raise InspectionError("Não foi possível preparar a área temporária segura.") from error
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_ISLNK(parent_stat.st_mode)
        or parent_stat.st_uid != os.getuid()
        or stat.S_IMODE(parent_stat.st_mode) != 0o700
    ):
        os.close(source_fd)
        raise InspectionError("A área temporária segura tem permissões inválidas.")

    staged_path = parent / f"payload-{uuid.uuid4().hex}.AppImage"
    destination_fd = -1
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_IMAGE_SIZE:
            raise InspectionError("O arquivo selecionado não é regular ou excede o limite.")
        destination_fd = os.open(
            staged_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        digest = hashlib.sha256()
        copied = 0
        deadline = time.monotonic() + 300
        with os.fdopen(source_fd, "rb", closefd=True) as source_file:
            source_fd = -1
            with os.fdopen(destination_fd, "wb", closefd=True) as destination_file:
                destination_fd = -1
                if progress:
                    progress("Copiando o arquivo para uma área temporária protegida…")
                while True:
                    chunk = source_file.read(1024 * 1024)
                    if not chunk:
                        break
                    if cancelled and cancelled():
                        raise InspectionError("Inspeção cancelada.")
                    copied += len(chunk)
                    if copied > MAX_IMAGE_SIZE or time.monotonic() > deadline:
                        raise InspectionError("O arquivo selecionado excede o limite de tamanho.")
                    digest.update(chunk)
                    destination_file.write(chunk)
                destination_file.flush()
                os.fsync(destination_file.fileno())
            after = os.fstat(source_file.fileno())
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino
            or copied != before.st_size
        ):
            raise InspectionError("O arquivo foi alterado durante a cópia; selecione-o novamente.")
        if progress:
            progress("Validando ELF, arquitetura, SquashFS e metadados…")
        inspection = inspect_appimage(staged_path)
        if inspection.image_sha256 != digest.hexdigest():
            raise InspectionError("A cópia temporária não corresponde ao arquivo selecionado.")
        if cancelled and cancelled():
            raise InspectionError("Inspeção cancelada.")
        return StagedImage(source, staged_path, inspection)
    except Exception:
        try:
            staged_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if destination_fd >= 0:
            os.close(destination_fd)


def remove_staged(path: str | Path) -> None:
    staged = Path(path)
    if (
        re.fullmatch(r"payload-[0-9a-f]{32}\.AppImage", staged.name)
        and staged.parent == _runtime_directory() / "mainuan-install-appimage"
    ):
        staged.unlink(missing_ok=True)
