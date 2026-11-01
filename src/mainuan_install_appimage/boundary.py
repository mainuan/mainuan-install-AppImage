"""Restricted protocol between the administrative helper and the content parser."""
from __future__ import annotations

import base64
import json
import os
import pwd
import selectors
import signal
import shutil
import tempfile
import stat
import subprocess
import time
from pathlib import Path

from .inspector import Inspection, MAX_IMAGE_SIZE, _clean_text, _debian_version, _identity_for_desktop
from .installer import InstallationError
from .categories import validate_categories

MAX_RESPONSE = 256 * 1024


def validate_response(raw: bytes, source: Path, digest: str) -> tuple[Inspection, dict[int, bytes]]:
    """Validate bounded primitive values; never decode icons or accept package paths."""
    if len(raw) > MAX_RESPONSE:
        raise InstallationError("Resposta de inspeção excessiva.")
    try:
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("campo JSON duplicado")
                result[key] = value
            return result
        data = json.loads(raw, object_pairs_hook=unique_object)
        expected_keys = {"image_sha256", "image_size", "squashfs_offset", "name", "version", "debian_version", "comment", "architecture", "desktop_identity", "package_name", "icons", "categories"}
        if not isinstance(data, dict) or set(data) != expected_keys:
            raise ValueError("objeto esperado")
        if not isinstance(data["categories"], list):
            raise ValueError("Categorias do protocolo devem ser uma lista JSON.")
        data["categories"] = validate_categories(data["categories"])
        for key, maximum in (("name", 160), ("comment", 240), ("version", 80), ("desktop_identity", 400)):
            if not isinstance(data.get(key), str) or not 0 < len(data[key]) <= maximum:
                raise ValueError("texto inválido")
        for key in ("name", "comment", "version"):
            if data[key] != _clean_text(data[key], 240):
                raise ValueError("controle ou quebra de linha em texto")
        identity = data["desktop_identity"].split("\n")
        if len(identity) != 2 or any(not part or "/" in part or "\\" in part or part != _clean_text(part, 200) for part in identity):
            raise ValueError("identidade inválida")
        package, _ = _identity_for_desktop(identity[0] + ".desktop")
        if data.get("package_name") != package:
            raise ValueError("pacote não corresponde à identidade")
        if data.get("image_sha256") != digest or data.get("image_size") != source.stat().st_size:
            raise ValueError("conteúdo divergente")
        if type(data.get("image_size")) is not int or not 64 <= data["image_size"] <= MAX_IMAGE_SIZE:
            raise ValueError("tamanho inválido")
        if type(data.get("squashfs_offset")) is not int or not 64 <= data["squashfs_offset"] < data["image_size"]:
            raise ValueError("offset inválido")
        if data.get("architecture") not in ("amd64", "arm64", "i386", "armhf"):
            raise ValueError("arquitetura inválida")
        version = _debian_version(data["version"] if data["version"] != "Não informada" else "", digest)
        if data.get("debian_version") != version:
            raise ValueError("versão Debian inválida")
        icons = {}
        if not isinstance(data.get("icons"), dict) or set(data["icons"]) != {"64", "128"}:
            raise ValueError("ícones inválidos")
        for size in (64, 128):
            value = data["icons"][str(size)]
            if not isinstance(value, str) or len(value) > 128 * 1024:
                raise ValueError("ícone excessivo")
            icon = base64.b64decode(value, validate=True)
            if len(icon) > 96 * 1024 or icon[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError("ícone incompatível")
            # Opaque data from here on: root does not decode or render this image.
            icons[size] = icon
        data.pop("icons")
        data["image_path"] = source
        data["icon_png"] = None
        return Inspection(**data), icons
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
        raise InstallationError(f"A resposta da inspeção foi recusada: {error}") from error


def inspect_reduced(source: Path, digest: str) -> tuple[Inspection, dict[int, bytes]]:
    account = pwd.getpwnam("nobody")
    if account.pw_uid == 0 or account.pw_gid == 0:
        raise InstallationError("Conta de inspeção sem privilégios indisponível.")
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    process = None
    scratch_root = None
    try:
        scratch_root = Path(tempfile.mkdtemp(prefix="mainuan-parser-root-", dir="/var/tmp"))
        scratch_root.chmod(0o711)
        scratch = scratch_root / "scratch"
        scratch.mkdir(mode=0o700)
        os.chown(scratch, account.pw_uid, account.pw_gid)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InstallationError("A cópia administrativa não é regular.")
        process = subprocess.Popen(
            ["/usr/bin/python3", "-I", "-m", "mainuan_install_appimage.reduced", str(descriptor)],
            pass_fds=(descriptor,), user=account.pw_uid, group=account.pw_gid, extra_groups=[],
            cwd="/", start_new_session=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8", "HOME": "/nonexistent", "TMPDIR": str(scratch)},
        )
        output, errors = bytearray(), bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, output)
            selector.register(process.stderr, selectors.EVENT_READ, errors)
            deadline = time.monotonic() + 180
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise InstallationError("Limite operacional: tempo da inspeção administrativa; limite=180 s.")
                for key, _ in selector.select(0.25):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        key.data.extend(chunk)
                        if len(output) + len(errors) > MAX_RESPONSE:
                            raise InstallationError(f"Limite operacional: saída do parser; observado={len(output) + len(errors)}, limite={MAX_RESPONSE} bytes.")
        code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        if code != 0:
            raise InstallationError(f"Falha na inspeção sem privilégios: código={code}; limites CPU=120 s, espaço de endereçamento=1073741824 bytes. " + errors.decode("utf-8", "replace"))
        return validate_response(bytes(output), source, digest)
    except (OSError, KeyError, subprocess.TimeoutExpired) as error:
        raise InstallationError(f"Não foi possível executar a inspeção sem privilégios: {error}") from error
    finally:
        os.close(descriptor)
        if process:
            # Also stop descendants if the parser fails or times out.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
            process.stderr.close()
        if scratch_root is not None:
            shutil.rmtree(scratch_root)
