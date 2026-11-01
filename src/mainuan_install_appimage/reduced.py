"""Unprivileged content parser, launched only by the fixed helper.

This is privilege separation with resource limits, not a filesystem/network sandbox.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import resource
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path


def restrict_process() -> None:
    if 0 in os.getresuid() or 0 in os.getresgid() or os.getgroups():
        raise RuntimeError("O processo de inspeção não perdeu todos os privilégios.")
    if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError("Não foi possível bloquear novos privilégios.")
    status = Path("/proc/self/status").read_text()
    for line in status.splitlines():
        if line.startswith(("CapEff:", "CapPrm:", "CapAmb:")) and int(line.split()[1], 16):
            raise RuntimeError("O processo de inspeção ainda possui capabilities.")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.umask(0o077)


def inspect_descriptor(descriptor: int) -> dict:
    # Import parsers only after privileges and resource limits have been set.
    from .inspector import inspect_appimage
    from .installer import _png_icon

    with tempfile.TemporaryDirectory(prefix="mainuan-parser-") as directory:
        source = Path(directory) / "input.AppImage"
        with os.fdopen(os.dup(descriptor), "rb") as incoming, source.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        inspection = inspect_appimage(source)
        data = asdict(inspection)
        data.pop("image_path")
        data.pop("icon_png")
        data["icons"] = {str(size): base64.b64encode(_png_icon(inspection, size)).decode("ascii") for size in (64, 128)}
        return data


def main() -> int:
    try:
        restrict_process()
        if len(sys.argv) != 2 or not sys.argv[1].isdecimal():
            raise ValueError("Descritor de entrada inválido.")
        print(json.dumps(inspect_descriptor(int(sys.argv[1])), ensure_ascii=True))
        return 0
    except MemoryError:
        print("Limite operacional: memória do parser; limite de espaço de endereçamento=1073741824 bytes; uso exato indisponível.", file=sys.stderr)
        return 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
