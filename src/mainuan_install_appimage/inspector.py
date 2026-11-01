from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import selectors
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable
from pathlib import Path, PurePosixPath

from .categories import normalize_categories


MAX_IMAGE_SIZE = 8 * 1024**3
MAX_TREE_OUTPUT = 4 * 1024**2
MAX_TREE_ENTRIES = 10_000  # returned records across selected listings, not application files
MAX_LIST_LINE = 4096
MAX_PATH_DEPTH = 12
MAX_LIST_QUERIES = 64
MAX_DESKTOP_CANDIDATES = 10
MAX_INSPECTION_SECONDS = 120
MAX_STDERR = 16 * 1024
MAX_READER_MEMORY = 1024**3

# No preexec_fn in a Qt worker thread: limit a fresh, isolated interpreter, then exec.
_READER_EXEC = """
import os, resource, sys
if os.geteuid() == 0:
    raise RuntimeError("A leitura SquashFS como root foi recusada.")
resource.setrlimit(resource.RLIMIT_AS, (int(sys.argv[1]), int(sys.argv[1])))
resource.setrlimit(resource.RLIMIT_CPU, (int(sys.argv[2]), int(sys.argv[2])))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.execv(sys.argv[3], sys.argv[3:])
"""
MAX_METADATA_SIZE = 128 * 1024
MAX_ICON_SIZE = 4 * 1024**2
MAX_COMMAND_SECONDS = 30
_DEBIAN_VERSION = re.compile(r"^[0-9][A-Za-z0-9.+:~\-]{0,79}$")
_SQUASHFS_SUPERBLOCK = struct.Struct("<4sIIIIHHHHHHQQQQQQQQ")
_SQUASHFS_SUPERBLOCK_BE = struct.Struct(">4sIIIIHHHHHHQQQQQQQQ")
_SQUASHFS_NO_TABLE = (1 << 64) - 1


class InspectionError(ValueError):
    """Base failure; operational limits never imply an invalid AppImage."""
    category = "Formato ou metadados"

    def __str__(self):
        return f"{self.category}: {super().__str__()}"


class InspectionLimitError(InspectionError):
    category = "Limite operacional (não determina a validade do arquivo)"

    def __init__(self, resource: str, observed: int | float | str, allowed: int | float | str):
        super().__init__(f"{resource}; observado={observed}, limite={allowed}")


class InspectionToolError(InspectionError):
    category = "Ferramenta de leitura SquashFS"


@dataclass(frozen=True)
class Inspection:
    image_path: Path
    image_sha256: str
    image_size: int
    squashfs_offset: int
    name: str
    version: str
    debian_version: str
    comment: str
    architecture: str
    desktop_identity: str
    package_name: str
    icon_png: bytes | None
    categories: tuple[str, ...] = ("Utility",)


@dataclass(frozen=True)
class _Entry:
    path: str
    kind: str
    size: int
    target: str | None = None


class _UnsupportedArchitecture(InspectionError):
    pass


def _clean_text(value: str, limit: int = 160) -> str:
    value = "".join(
        char
        for char in value
        if char in "\t " or unicodedata.category(char)[0] != "C"
    )
    return " ".join(value.split())[:limit]


def _architecture(header: bytes) -> str:
    if len(header) < 64 or header[:4] != b"\x7fELF":
        raise InspectionError("O arquivo não é um executável ELF.")
    elf_class, endian, ident_version = header[4], header[5], header[6]
    if endian != 1 or ident_version != 1:
        raise InspectionError(
            "Formato incompatível: são aceitos somente AppImages ELF little-endian."
        )
    if elf_class not in (1, 2):
        raise InspectionError("O AppImage usa uma classe ELF incompatível.")
    header_size = 52 if elf_class == 1 else 64
    if len(header) < header_size:
        raise InspectionError("O cabeçalho ELF está truncado.")
    elf_type, machine = struct.unpack_from("<HH", header, 16)
    version = struct.unpack_from("<I", header, 20)[0]
    declared_size = struct.unpack_from("<H", header, 40 if elf_class == 1 else 52)[0]
    if elf_type not in (2, 3) or version != 1 or declared_size < header_size:
        raise InspectionError("O cabeçalho ELF do AppImage é inválido.")

    architectures = {
        (1, 3): "i386",
        (2, 62): "amd64",
        (2, 183): "arm64",
    }
    if (elf_class, machine) in architectures:
        return architectures[(elf_class, machine)]
    if elf_class == 1 and machine == 40:
        flags = struct.unpack_from("<I", header, 36)[0]
        if flags & 0x400:
            return "armhf"
    raise _UnsupportedArchitecture(
        "Arquitetura incompatível. Formatos aceitos: amd64, arm64, i386 e armhf."
    )


def _valid_superblock(file_size: int, offset: int, raw: bytes) -> bool:
    if len(raw) != _SQUASHFS_SUPERBLOCK.size:
        return False
    magic = raw[:4]
    if magic == b"hsqs":
        fields = _SQUASHFS_SUPERBLOCK.unpack(raw)
    elif magic == b"sqsh":
        fields = _SQUASHFS_SUPERBLOCK_BE.unpack(raw)
    else:
        return False

    (
        _,
        inode_count,
        _,
        block_size,
        _,
        compression,
        block_log,
        _,
        id_count,
        major,
        minor,
        root_inode,
        bytes_used,
        id_table,
        xattr_table,
        inode_table,
        directory_table,
        fragment_table,
        lookup_table,
    ) = fields
    if (
        inode_count == 0
        or block_size < 4096
        or block_size > 1024 * 1024
        or block_size & (block_size - 1)
        or block_log != block_size.bit_length() - 1
        or compression not in range(1, 7)
        or id_count == 0
        or major != 4
        or minor != 0
        or bytes_used < _SQUASHFS_SUPERBLOCK.size
        or offset + bytes_used > file_size
    ):
        return False

    tables = (id_table, xattr_table, inode_table, directory_table, fragment_table, lookup_table)
    if any(value != _SQUASHFS_NO_TABLE and value >= bytes_used for value in tables):
        return False
    if inode_table == _SQUASHFS_NO_TABLE or directory_table == _SQUASHFS_NO_TABLE:
        return False
    root_block = root_inode >> 16
    root_offset = root_inode & 0xffff
    return (
        inode_table + root_block < bytes_used
        and root_offset < 8192
        and inode_table + root_block >= inode_table
    )


def _find_superblocks(image: Path, file_size: int, inspection_deadline: float | None = None) -> list[int]:
    offsets: list[int] = []
    overlap = b""
    absolute = 0
    candidates = 0
    started = time.monotonic()
    deadline = min(started + MAX_COMMAND_SECONDS, inspection_deadline) if inspection_deadline is not None else started + MAX_COMMAND_SECONDS
    allowed = max(0, round(deadline - started, 2))
    with image.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            if time.monotonic() > deadline:
                raise InspectionLimitError("busca SquashFS (s)", round(time.monotonic() - started, 2), allowed)
            data = overlap + chunk
            base = absolute - len(overlap)
            for magic in (b"hsqs", b"sqsh"):
                cursor = 0
                while True:
                    found = data.find(magic, cursor)
                    if found < 0:
                        break
                    candidates += 1
                    if candidates > 4096:
                        raise InspectionLimitError("candidatos a superbloco", candidates, 4096)
                    if time.monotonic() > deadline:
                        raise InspectionLimitError("busca SquashFS (s)", round(time.monotonic() - started, 2), allowed)
                    offset = base + found
                    cursor = found + 1
                    if offset < 64:
                        continue
                    stream.seek(offset)
                    raw = stream.read(_SQUASHFS_SUPERBLOCK.size)
                    if _valid_superblock(file_size, offset, raw):
                        offsets.append(offset)
                        if len(offsets) > 64:
                            raise InspectionLimitError("superblocos estruturais", len(offsets), 64)
                stream.seek(absolute + len(chunk))
            absolute += len(chunk)
            overlap = data[-3:]
    return offsets


def _run_bounded(arguments: list[str], output_limit: int, timeout: float,
                 on_line: Callable[[str], None] | None = None) -> bytes:
    executable = shutil.which(arguments[0], path="/usr/sbin:/usr/bin:/sbin:/bin")
    if not executable:
        raise InspectionToolError("unsquashfs não está instalado.")
    if timeout <= 0:
        raise InspectionLimitError("tempo da inspeção (s)", MAX_INSPECTION_SECONDS, MAX_INSPECTION_SECONDS)
    try:
        process = subprocess.Popen(
            ["/usr/bin/python3", "-I", "-c", _READER_EXEC, str(MAX_READER_MEMORY),
             str(MAX_COMMAND_SECONDS), executable, *arguments[1:]], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8"},
        )
    except OSError as error:
        raise InspectionToolError(f"Não foi possível iniciar unsquashfs: {error}") from error
    output, pending, errors = bytearray(), bytearray(), bytearray()
    seen, stderr_seen = 0, 0
    started = time.monotonic()
    deadline = started + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "out")
            selector.register(process.stderr, selectors.EVENT_READ, "err")
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise InspectionLimitError("tempo do comando (s)", round(time.monotonic() - started, 2), round(timeout, 2))
                for key, _ in selector.select(min(0.25, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "err":
                        stderr_seen += len(chunk)
                        if stderr_seen > MAX_STDERR:
                            raise InspectionLimitError("stderr de unsquashfs (bytes)", stderr_seen, MAX_STDERR)
                        errors.extend(chunk)
                        continue
                    seen += len(chunk)
                    if seen > output_limit:
                        raise InspectionLimitError("stdout de unsquashfs (bytes)", seen, output_limit)
                    if on_line is None:
                        output.extend(chunk)
                    else:
                        pending.extend(chunk)
                        while b"\n" in pending:
                            line, _, remainder = pending.partition(b"\n")
                            pending = bytearray(remainder)
                            if len(line) > MAX_LIST_LINE:
                                raise InspectionLimitError("linha de listagem (bytes)", len(line), MAX_LIST_LINE)
                            on_line(line.decode("utf-8", "strict"))
                        if len(pending) > MAX_LIST_LINE:
                            raise InspectionLimitError("linha de listagem (bytes)", len(pending), MAX_LIST_LINE)
            if pending:
                on_line(pending.decode("utf-8", "strict"))
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if code:
            detail = errors.decode("utf-8", "replace").strip()[:4096]
            if any(term in detail.lower() for term in ("out of memory", "cannot allocate memory", "memoryerror")):
                raise InspectionLimitError("memória de unsquashfs (bytes; uso exato indisponível)", "alocação recusada", MAX_READER_MEMORY)
            if code == -24:  # SIGXCPU
                raise InspectionLimitError("CPU de unsquashfs (s)", "sinal SIGXCPU", MAX_COMMAND_SECONDS)
            raise InspectionToolError(f"unsquashfs terminou com código {code}. {detail}")
    except UnicodeDecodeError as error:
        raise InspectionToolError("A listagem não é UTF-8 válida.") from error
    except subprocess.TimeoutExpired as error:
        raise InspectionLimitError("tempo do comando (s)", round(time.monotonic() - started, 2), round(timeout, 2)) from error
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()
    return bytes(output)


def _safe_path(value: str) -> bool:
    if (
        not value
        or len(value) > 512
        or value.startswith("/")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        return False
    parts = value.split("/")
    return all(part not in ("", ".", "..") and not part.startswith("-") for part in parts)


def _listing_entry(line: str) -> _Entry | None:
    if not line.strip():
        return None
    fields = line.split(maxsplit=5)
    if (len(fields) != 6 or not re.fullmatch(r"[dl\-bcps][rwxstST-]{9}", fields[0])
            or not re.fullmatch(r"[0-9]+/[0-9]+", fields[1])):
        raise InspectionToolError("A listagem -lln está malformada (campos/modo/UID/GID).")
    try:
        size = int(fields[2])
    except ValueError as error:
        raise InspectionToolError("A listagem contém um tamanho inválido.") from error
    mode, listed = fields[0], fields[5]
    if listed == "squashfs-root":
        if not mode.startswith("d"):
            raise InspectionError("A raiz SquashFS não é um diretório.")
        return None
    if not listed.startswith("squashfs-root/"):
        raise InspectionError("Caminho fora da raiz SquashFS na listagem.")
    relative = listed[len("squashfs-root/"):]
    target = None
    if mode.startswith("l"):
        relative, separator, target = relative.partition(" -> ")
        if len(target) > 1024:
            raise InspectionLimitError("destino de link (caracteres)", len(target), 1024)
        if not separator or not target:
            raise InspectionError("Link simbólico inválido.")
    if len(relative) > 512:
        raise InspectionLimitError("caminho de metadados (caracteres)", len(relative), 512)
    if not _safe_path(relative) or size < 0:
        raise InspectionError("Caminho inválido ou inseguro na listagem.")
    kind = "file" if mode.startswith("-") else "directory" if mode.startswith("d") else "link" if mode.startswith("l") else "other"
    return _Entry(relative, kind, size, target)


class _MetadataTree(dict[str, _Entry]):
    """Root listing plus exact, lazy queries. Never enumerate application subtrees."""
    def __init__(self, image: Path, offset: int, deadline: float):
        super().__init__()
        self.image, self.offset, self.deadline = image, offset, deadline
        self.examined = self.output_bytes = self.queries = 0
        self.absent: set[str] = set()
        self._query("")

    def timeout(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise InspectionLimitError("tempo total da inspeção (s)", MAX_INSPECTION_SECONDS, MAX_INSPECTION_SECONDS)
        return min(MAX_COMMAND_SECONDS, remaining)

    def _query(self, path: str):
        depth = len(PurePosixPath(path).parts) if path else 1
        if depth > MAX_PATH_DEPTH:
            raise InspectionLimitError("profundidade de caminho de metadados", depth, MAX_PATH_DEPTH)
        self.queries += 1
        if self.queries > MAX_LIST_QUERIES:
            raise InspectionLimitError("consultas exatas de metadados", self.queries, MAX_LIST_QUERIES)
        local: dict[str, _Entry] = {}

        def consume(line: str):
            self.output_bytes += len(line.encode("utf-8")) + 1
            if self.output_bytes > MAX_TREE_OUTPUT:
                raise InspectionLimitError("listagens acumuladas (bytes)", self.output_bytes, MAX_TREE_OUTPUT)
            entry = _listing_entry(line)
            if entry is None:
                return
            self.examined += 1
            if self.examined > MAX_TREE_ENTRIES:
                raise InspectionLimitError("registros examinados nas listagens selecionadas", self.examined, MAX_TREE_ENTRIES)
            if entry.path in local:
                raise InspectionToolError("Caminho duplicado na mesma listagem.")
            if (not path and "/" in entry.path) or (path and not (entry.path == path or path.startswith(entry.path + "/"))):
                raise InspectionToolError("unsquashfs retornou entradas fora da seleção/profundidade solicitada.")
            previous = dict.get(self, entry.path)
            if previous is not None and previous != entry:
                raise InspectionError("Metadados divergentes entre consultas à mesma imagem.")
            local[entry.path] = entry
            parent = PurePosixPath(entry.path).parent
            while str(parent) != ".":
                ancestor = local.get(str(parent)) or dict.get(self, str(parent))
                if ancestor is None or ancestor.kind != "directory":
                    raise InspectionError("Árvore de diretórios de metadados inválida.")
                parent = parent.parent
            self[entry.path] = entry

        _run_bounded(["unsquashfs", "-lln", "-no-progress", "-processors", "1", "-mem", "64M",
                      "-no-wildcards", "-max-depth", str(depth), "-o", str(self.offset), str(self.image),
                      *([path] if path else [])], MAX_TREE_OUTPUT - self.output_bytes,
                     self.timeout(), on_line=consume)
        if path and path not in self:
            self.absent.add(path)

    def get(self, path, default=None):
        if path not in self and path not in self.absent:
            if len(path) > 512:
                raise InspectionLimitError("caminho de metadados (caracteres)", len(path), 512)
            if not _safe_path(path):
                raise InspectionError("Caminho de metadados inseguro.")
            self._query(path)
        return dict.get(self, path, default)


def _read_tree(image: Path, offset: int, deadline: float | None = None) -> _MetadataTree:
    return _MetadataTree(image, offset, deadline if deadline is not None else time.monotonic() + MAX_INSPECTION_SECONDS)


def _resolve_entry(path: str, entries: dict[str, _Entry]) -> _Entry | None:
    pending = list(PurePosixPath(path).parts)
    resolved: list[str] = []
    hops = 0
    while pending:
        part = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                return None
            resolved.pop()
            continue
        resolved.append(part)
        current = "/".join(resolved)
        entry = entries.get(current)
        if entry is None:
            return None
        if entry.kind == "link":
            hops += 1
            if hops > 16:
                raise InspectionLimitError("saltos de links simbólicos", hops, 16)
            if entry.target is None or entry.target.startswith("/"):
                return None
            resolved.pop()
            pending = list(PurePosixPath(entry.target).parts) + pending
        elif pending and entry.kind != "directory":
            return None
    return entries.get("/".join(resolved))


def _cat_file(image: Path, offset: int, path: str, limit: int, timeout: float = MAX_COMMAND_SECONDS) -> bytes:
    if not _safe_path(path):
        raise InspectionError("O caminho de metadados do AppImage é inválido.")
    return _run_bounded(
        [
            "unsquashfs",
            "-cat",
            "-processors",
            "1",
            "-mem",
            "64M",
            "-no-wildcards",
            "-o",
            str(offset),
            str(image),
            path,
        ],
        limit,
        timeout,
    )


def _parse_desktop(data: bytes, desktop_path: str) -> dict:
    if len(data) > MAX_METADATA_SIZE:
        raise InspectionLimitError("metadados .desktop (bytes)", len(data), MAX_METADATA_SIZE)
    try:
        text = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        raise InspectionError("O arquivo .desktop não está codificado em UTF-8.") from error
    values: dict[str, str] = {}
    in_entry = False
    found_entry = False
    for line in text.splitlines():
        if len(line) > 4096:
            raise InspectionLimitError("linha .desktop (caracteres)", len(line), 4096)
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_entry = stripped == "[Desktop Entry]"
            found_entry |= in_entry
            continue
        if not in_entry:
            continue
        if "=" not in line:
            raise InspectionError("O arquivo .desktop está malformado.")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9-]+(?:\[[A-Za-z0-9_@.-]+\])?", key.strip()):
            raise InspectionError("O arquivo .desktop contém uma chave inválida.")
        key = key.strip()
        if key in values:
            raise InspectionError("O arquivo .desktop contém chaves duplicadas.")
        values[key] = value if key == "Categories" else value.strip()
    if not found_entry:
        raise InspectionError("O AppImage não contém uma seção [Desktop Entry] válida.")
    if values.get("Type", "Application") != "Application":
        raise InspectionError("O arquivo .desktop não descreve um aplicativo.")

    def unescape(value: str) -> str:
        return re.sub(
            r"\\([snrt\\])",
            lambda match: {
                "s": " ",
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "\\": "\\",
            }[match.group(1)],
            value,
        )

    for key, value in tuple(values.items()):
        values[key] = unescape(value)
    stem = PurePosixPath(desktop_path).stem
    language_name = values.get("Name[pt_BR]") or values.get("Name[pt]") or values.get("Name")
    name = _clean_text(language_name or stem)
    if not name:
        name = "Aplicativo AppImage"
    comment = _clean_text(values.get("Comment[pt_BR]") or values.get("Comment") or "", 240)
    raw_version = values.get("X-AppImage-Version") or ""
    version = raw_version if (raw_version == _clean_text(raw_version, 80)
                              and _debian_version(raw_version, "0" * 64) == raw_version) else ""
    icon = values.get("Icon", "")
    if len(icon) > 512:
        raise InspectionLimitError("referência de ícone (caracteres)", len(icon), 512)
    if any(unicodedata.category(char)[0] == "C" for char in icon):
        icon = ""
    return {"name": name, "identity_name": _clean_text(values.get("Name") or stem), "comment": comment, "version": version, "icon": icon, "categories": normalize_categories(values.get("Categories", ""))}


def _read_icon(image: Path, offset: int, entries: _MetadataTree, desktop_icon: str) -> bytes | None:
    # Only advertised paths and conventional locations, no recursive icon search.
    icon = desktop_icon.lstrip("/")
    candidates = [".DirIcon"]
    if icon and _safe_path(icon):
        candidates.append(icon)
        if "/" not in icon:
            filename = icon if icon.lower().endswith(".png") else icon + ".png"
            candidates.append(filename)
            candidates.extend(f"usr/share/icons/hicolor/{size}/apps/{filename}" for size in
                              ("128x128", "256x256", "64x64", "512x512", "48x48", "32x32"))
            candidates.append(f"usr/share/pixmaps/{filename}")
    total = 0
    for candidate in dict.fromkeys(candidates):
        entry = _resolve_entry(candidate, entries)
        if entry is None or entry.kind != "file":
            continue
        if total + entry.size > MAX_ICON_SIZE:
            raise InspectionLimitError("ícones lidos (bytes)", total + entry.size, MAX_ICON_SIZE)
        data = _cat_file(image, offset, entry.path, MAX_ICON_SIZE - total, entries.timeout())
        total += len(data)
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        width, height = struct.unpack_from(">II", data, 16)
        if width == 0 or height == 0:
            continue
        if width > 8192 or height > 8192 or width * height > 32_000_000:
            raise InspectionLimitError("dimensões PNG (largura,altura,pixels)", f"{width},{height},{width*height}", "8192,8192,32000000")
        return data
    return None


def _identity_for_desktop(desktop_path: str) -> tuple[str, str]:
    stem = PurePosixPath(desktop_path).stem
    slug = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "app"
    suffix = hashlib.sha256(stem.encode("utf-8")).hexdigest()[:10]
    return f"mainuan-appimage-{slug[:48].rstrip('-')}-{suffix}", stem


def _debian_version(value: str, image_sha256: str) -> str:
    if _DEBIAN_VERSION.fullmatch(value) and ":" not in value and ("-" not in value or re.fullmatch(r"[A-Za-z0-9.+~]+", value.rsplit("-", 1)[1])):
        return value
    return f"0~{image_sha256[:16]}"


def inspect_appimage(image_path: str | Path) -> Inspection:
    path = Path(image_path)
    try:
        path = path.resolve(strict=True)
        file_stat = path.stat()
    except OSError as error:
        raise InspectionError(f"Não foi possível abrir o arquivo selecionado: {error}") from error
    if not path.is_file():
        raise InspectionError("O arquivo selecionado não é um arquivo regular.")
    if file_stat.st_size < 64:
        raise InspectionError("Cabeçalho ELF truncado: arquivo com menos de 64 bytes.")
    if file_stat.st_size > MAX_IMAGE_SIZE:
        raise InspectionLimitError("arquivo AppImage (bytes)", file_stat.st_size, MAX_IMAGE_SIZE)

    with path.open("rb") as stream:
        header = stream.read(64)
    architecture = _architecture(header)
    if header[8:11] != b"AI\x02":
        raise InspectionError("Formato incompatível: somente AppImage Type 2 com assinatura AI de tipo 2 é aceito.")
    inspection_deadline = time.monotonic() + MAX_INSPECTION_SECONDS
    image_sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if time.monotonic() > inspection_deadline:
                raise InspectionLimitError("tempo total da inspeção (s)", MAX_INSPECTION_SECONDS, MAX_INSPECTION_SECONDS)
            image_sha256.update(chunk)
    digest = image_sha256.hexdigest()

    offsets = _find_superblocks(path, file_stat.st_size, inspection_deadline)
    if not offsets:
        raise InspectionError(
            "Formato incompatível ou inválido. São aceitos somente AppImages Type 2 "
            "com SquashFS 4.0 validado."
        )

    last_error: InspectionError | None = None
    for offset in offsets:
        if time.monotonic() > inspection_deadline:
            raise InspectionLimitError("tempo total da inspeção (s)", MAX_INSPECTION_SECONDS, MAX_INSPECTION_SECONDS)
        try:
            entries = _read_tree(path, offset, inspection_deadline)
            desktop_files = sorted(
                entry.path
                for entry in entries.values()
                if entry.kind in ("file", "link")
                and "/" not in entry.path
                and entry.path.lower().endswith(".desktop")
            )
            if not desktop_files:
                raise InspectionError(
                    "O AppImage não contém um arquivo .desktop regular na raiz."
                )
            if len(desktop_files) > MAX_DESKTOP_CANDIDATES:
                raise InspectionLimitError("candidatos .desktop na raiz", len(desktop_files), MAX_DESKTOP_CANDIDATES)
            metadata = None
            desktop_path = ""
            for candidate in desktop_files:
                try:
                    resolved = _resolve_entry(candidate, entries)
                    if resolved is not None and resolved.size > MAX_METADATA_SIZE:
                        raise InspectionLimitError("metadados .desktop (bytes)", resolved.size, MAX_METADATA_SIZE)
                    if resolved is None or resolved.kind != "file":
                        raise InspectionError("O link .desktop é inválido ou escapa da árvore.")
                    candidate_data = _cat_file(path, offset, resolved.path, MAX_METADATA_SIZE, entries.timeout())
                    metadata = _parse_desktop(candidate_data, candidate)
                    desktop_path = candidate
                    break
                except (InspectionLimitError, InspectionToolError):
                    raise
                except InspectionError as error:
                    last_error = error
            if metadata is None:
                raise last_error or InspectionError(
                    "O AppImage não contém metadados .desktop válidos."
                )
            package_name, desktop_identity = _identity_for_desktop(desktop_path)
            return Inspection(
                image_path=path,
                image_sha256=digest,
                image_size=file_stat.st_size,
                squashfs_offset=offset,
                name=metadata["name"],
                version=metadata["version"] or "Não informada",
                debian_version=_debian_version(metadata["version"], digest),
                comment=metadata["comment"] or "Aplicativo AppImage",
                architecture=architecture,
                desktop_identity=desktop_identity + "\n" + metadata["identity_name"],
                package_name=package_name,
                icon_png=_read_icon(path, offset, entries, metadata["icon"]),
                categories=metadata["categories"],
            )
        except (InspectionLimitError, InspectionToolError):
            raise
        except InspectionError as error:
            last_error = error
    raise last_error or InspectionError("Não foi possível validar o AppImage.")
