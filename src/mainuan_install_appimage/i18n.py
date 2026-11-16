"""Gettext helpers and language-neutral messages for the privilege boundary.

Text domain: ``mainuan-install-appimage`` (the Debian package name).  Catalogs
are looked up in ``$MAINUAN_INSTALL_APPIMAGE_LOCALEDIR`` (optional), in the
source tree's ``build/locale`` (only when running from a checkout) and in
``/usr/share/locale``.  The language comes from the session (``LANGUAGE``,
``LC_ALL``, ``LC_MESSAGES``, ``LANG``); it is never forced.

Messages that cross a process boundary (unprivileged parser -> root helper ->
GUI) are never translated by the sending process: they travel as a
``MESSAGE:`` line holding the English msgid and its arguments as JSON, and the
GUI translates them with the user's catalog.  The root helper calls
:func:`disable_translation` so that nothing is rendered with root's
environment.
"""
from __future__ import annotations

import gettext
import json
import os
import re
import threading
from pathlib import Path

DOMAIN = "mainuan-install-appimage"
LOCALEDIR_ENV = "MAINUAN_INSTALL_APPIMAGE_LOCALEDIR"
SYSTEM_LOCALEDIR = "/usr/share/locale"
WIRE_PREFIX = "MESSAGE:"

_MAX_WIRE_DEPTH = 4
_MAX_WIRE_ARGS = 16
_MAX_WIRE_TEXT = 64 * 1024
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

_lock = threading.Lock()
_translation: gettext.NullTranslations | None = None
_disabled = False


def localedirs() -> list[str]:
    """Candidate catalog directories, most specific first."""
    candidates = []
    override = os.environ.get(LOCALEDIR_ENV)
    if override:
        candidates.append(override)
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "po" / "i18n.conf").is_file():
        candidates.append(str(checkout / "build" / "locale"))
    candidates.append(SYSTEM_LOCALEDIR)
    return candidates


def _catalog() -> gettext.NullTranslations:
    global _translation
    with _lock:
        if _translation is None:
            found: gettext.NullTranslations = gettext.NullTranslations()
            for directory in localedirs():
                candidate = gettext.translation(DOMAIN, directory, fallback=True)
                if type(candidate) is not gettext.NullTranslations:
                    found = candidate
                    break
            _translation = found
        return _translation


def reset() -> None:
    """Forget the cached catalog (tests change LANGUAGE between cases)."""
    global _translation, _disabled
    with _lock:
        _translation = None
        _disabled = False


def disable_translation() -> None:
    """Render msgids verbatim in this process (root helper, sandboxed parser)."""
    global _disabled, _translation
    with _lock:
        _disabled = True
        _translation = gettext.NullTranslations()


def _(message: str) -> str:
    if not message or _disabled:
        return message
    return _catalog().gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    if _disabled:
        return singular if count == 1 else plural
    return _catalog().ngettext(singular, plural, count)


def pgettext(context: str, message: str) -> str:
    if not message or _disabled:
        return message
    return _catalog().pgettext(context, message)


def N_(message: str) -> str:
    """Mark a string for extraction; it is translated later, where it is shown."""
    return message


def _substitute(template: str, values: dict[str, str]) -> str:
    # Plain {name} replacement only: no attribute access or format specs.
    return _PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), template)


class Message:
    """An English msgid plus arguments, translated only when rendered."""

    __slots__ = ("msgid", "args")

    def __init__(self, msgid: str, /, **args: object) -> None:
        self.msgid = msgid
        self.args = args

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return f"Message({self.msgid!r}, **{self.args!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Message):
            return (self.msgid, self.args) == (other.msgid, other.args)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.msgid)

    def render(self) -> str:
        values = {key: str(value) for key, value in self.args.items()}
        return _substitute(_(self.msgid), values) if values else _(self.msgid)

    def to_wire(self) -> dict:
        def encode(value: object) -> object:
            if isinstance(value, LocalizedError):
                return value.full_message().to_wire()
            if isinstance(value, Message):
                return value.to_wire()
            return str(value)
        return {"id": self.msgid, "args": {key: encode(value) for key, value in self.args.items()}}

    @classmethod
    def from_wire(cls, data: object, _depth: int = 0) -> "Message":
        if _depth > _MAX_WIRE_DEPTH or not isinstance(data, dict) or set(data) != {"id", "args"}:
            raise ValueError("malformed message")
        msgid, args = data["id"], data["args"]
        if (not isinstance(msgid, str) or not msgid or len(msgid) > _MAX_WIRE_TEXT
                or not isinstance(args, dict) or len(args) > _MAX_WIRE_ARGS):
            raise ValueError("malformed message")
        decoded: dict[str, object] = {}
        for key, value in args.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key):
                raise ValueError("malformed message argument")
            if isinstance(value, str):
                if len(value) > _MAX_WIRE_TEXT:
                    raise ValueError("malformed message argument")
                decoded[key] = value
            else:
                decoded[key] = cls.from_wire(value, _depth + 1)
        return cls(msgid, **decoded)


class LocalizedError(Exception):
    """Exception whose text is a :class:`Message`, rendered in the reader's language."""

    def __init__(self, message: "str | Message", /, **args: object) -> None:
        self.message = message if isinstance(message, Message) else Message(message, **args)
        super().__init__(self.message.msgid)

    def full_message(self) -> Message:
        return self.message

    def __str__(self) -> str:
        return str(self.full_message())


def wire_line(item: "Message | LocalizedError") -> str:
    """One protocol line; msgids stay untranslated across the boundary."""
    message = item.full_message() if isinstance(item, LocalizedError) else item
    return WIRE_PREFIX + json.dumps(message.to_wire(), ensure_ascii=True, separators=(",", ":"))


def parse_wire(line: str) -> Message | None:
    """Return the message carried by a protocol line, or None for plain text."""
    if not line.startswith(WIRE_PREFIX):
        return None
    try:
        return Message.from_wire(json.loads(line[len(WIRE_PREFIX):]))
    except (ValueError, RecursionError):
        return None


def render_line(line: str) -> str:
    """Translate a helper output line when it is a protocol message."""
    message = parse_wire(line)
    return line if message is None else str(message)
