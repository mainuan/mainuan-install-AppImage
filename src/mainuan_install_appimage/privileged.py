from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from .installer import (
    InstallationError,
    copy_verified_source,
    prepare_and_install,
    package_manager_lock,
    verify_staged_source,
)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--install", nargs=2, metavar=("ARQUIVO_TEMPORARIO", "SHA256"))
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        print("Este helper só pode ser iniciado pelo PolicyKit.", file=sys.stderr)
        return 1
    uid_text = os.environ.get("PKEXEC_UID", "")
    if not uid_text.isdecimal() or int(uid_text) == 0:
        print("Não foi possível identificar o usuário que solicitou a instalação.", file=sys.stderr)
        return 1
    if not arguments.install:
        print("Operação administrativa não reconhecida.", file=sys.stderr)
        return 1

    os.environ.clear()
    os.environ.update({"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8", "HOME": "/root", "TMPDIR": "/var/tmp"})
    os.umask(0o077)
    source_fd_path: Path | None = None
    try:
        source_fd_path = verify_staged_source(
            arguments.install[0], arguments.install[1], int(uid_text)
        )
        with tempfile.TemporaryDirectory(
            prefix="mainuan-appimage-root-", dir="/var/tmp"
        ) as directory:
            snapshot = Path(directory) / "validated.AppImage"
            copy_verified_source(source_fd_path, snapshot, arguments.install[1])
            os.close(int(source_fd_path.name.rsplit("/", 1)[-1]))
            source_fd_path = None
            print("Arquivo recebido e hash conferido.", flush=True)
            with package_manager_lock():
                os.environ["DPKG_FRONTEND_LOCKED"] = "1"
                prepare_and_install(snapshot, arguments.install[1])
        return 0
    except (InstallationError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr, flush=True)
        return 1
    finally:
        if source_fd_path is not None:
            try:
                os.close(int(source_fd_path.name.rsplit("/", 1)[-1]))
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
