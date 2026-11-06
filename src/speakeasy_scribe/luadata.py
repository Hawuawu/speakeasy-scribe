"""Read and write the Lua data files WoW uses for SavedVariables.

Only data is accepted (assignments of literals and tables); nothing is executed.
Lua strings are bytes; they are decoded as UTF-8, keeping any invalid bytes
through ``surrogateescape`` so a file round-trips unchanged.
"""

from __future__ import annotations

import math
import re
from typing import Any

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_NAME_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)[ \t\r\n]*=(?!=)")
_MATH_HUGE = re.compile(r"math\.huge(?![A-Za-z0-9_])")
_LONG_BRACKET = re.compile(r"\[(=*)\[")
_DECIMAL_ESCAPE = re.compile(r"[0-9]{1,3}")
_HEX_ESCAPE = re.compile(r"x([0-9a-fA-F]{2})")
_UNICODE_ESCAPE = re.compile(r"u\{([0-9a-fA-F]+)\}")
_SPACE_CHARS = " \t\r\n\f\v"
_MAX_BYTE = 255
_CONSTANTS: dict[str, bool | None] = {"true": True, "false": False, "nil": None}
_SIMPLE_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "\n": "\n",
}


class LuaDataError(ValueError):
    """Raised when a file is not plain Lua data."""


def _from_bytes(raw: str) -> str:
    return raw.encode("latin-1").decode("utf-8", errors="surrogateescape")


class _Parser:
    def __init__(self, text: str) -> None:
        # Parsing works on a latin-1 view so each character is one byte.
        self.text = text
        self.pos = 0

    def error(self, message: str) -> LuaDataError:
        line = self.text.count("\n", 0, self.pos) + 1
        return LuaDataError(f"line {line}: {message}")

    def skip(self) -> None:
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if char in " \t\r\n\f\v":
                self.pos += 1
            elif text.startswith("--", self.pos):
                self.pos += 2
                level = self._long_bracket_level()
                if level is not None:
                    self._long_bracket(level)
                else:
                    end = text.find("\n", self.pos)
                    self.pos = len(text) if end == -1 else end + 1
            else:
                break

    def peek(self) -> str:
        self.skip()
        return self.text[self.pos : self.pos + 1]

    def expect(self, token: str) -> None:
        self.skip()
        if not self.text.startswith(token, self.pos):
            raise self.error(f"expected {token!r}")
        self.pos += len(token)

    def _long_bracket_level(self) -> int | None:
        match = _LONG_BRACKET.match(self.text, self.pos)
        return len(match.group(1)) if match else None

    def _long_bracket(self, level: int) -> str:
        start = self.pos + level + 2
        close = "]" + "=" * level + "]"
        end = self.text.find(close, start)
        if end == -1:
            raise self.error("unfinished long string or comment")
        self.pos = end + len(close)
        body = self.text[start:end]
        return body[1:] if body.startswith("\n") else body

    def document(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while True:
            self.skip()
            if self.pos >= len(self.text):
                return result
            match = _NAME.match(self.text, self.pos)
            if not match:
                raise self.error("expected a variable name")
            self.pos = match.end()
            self.expect("=")
            result[match.group()] = self.value()
            if self.peek() == ";":
                self.pos += 1

    def value(self) -> Any:
        """Parse one value: a table, string, number, ``true``/``false``/``nil`` or ``math.huge``."""
        char = self.peek()
        if not char:
            raise self.error("expected a value")
        if char == "{":
            return self.table()
        if char in "\"'":
            return self.string()
        if char == "[":
            return self._long_string()
        if char == "-":
            return self._negative()
        if _NAME.match(self.text, self.pos):
            return self._word()
        return self._number()

    def _long_string(self) -> str:
        level = self._long_bracket_level()
        if level is None:
            raise self.error("expected a value")
        return _from_bytes(self._long_bracket(level))

    def _negative(self) -> int | float:
        self.pos += 1
        number = self.value()
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            raise self.error("'-' must be followed by a number")
        return -number

    def _word(self) -> bool | float | None:
        if _MATH_HUGE.match(self.text, self.pos):
            self.pos += len("math.huge")
            return math.inf
        match = _NAME.match(self.text, self.pos)
        word = match.group() if match else ""
        if word not in _CONSTANTS:
            raise self.error(f"unexpected name {word!r}; only data is allowed")
        self.pos += len(word)
        return _CONSTANTS[word]

    def _number(self) -> int | float:
        match = _NUMBER.match(self.text, self.pos)
        if not match:
            raise self.error("expected a value")
        self.pos = match.end()
        token = match.group()
        if token[:2].lower() == "0x":
            return int(token, 16)
        if token.isdigit():
            return int(token)
        return float(token)

    def string(self) -> str:
        """Parse a quoted string with Lua 5.1-5.4 escapes."""
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        while True:
            char = self.text[self.pos : self.pos + 1]
            if char == quote:
                self.pos += 1
                return _from_bytes("".join(out))
            if char in ("", "\n"):
                raise self.error("unfinished string")
            self.pos += 1
            out.append(self._escape() if char == "\\" else char)

    def _escape(self) -> str:
        esc = self.text[self.pos : self.pos + 1]
        if esc in _SIMPLE_ESCAPES:
            self.pos += 1
            return _SIMPLE_ESCAPES[esc]
        if esc.isascii() and esc.isdigit():
            return self._decimal_escape()
        handlers = {"\r": self._newline_escape, "x": self._hex_escape, "z": self._skip_space_escape, "u": self._unicode_escape}
        handler = handlers.get(esc)
        if handler is None:
            raise self.error(f"bad escape \\{esc}")
        return handler()

    def _newline_escape(self) -> str:
        self.pos += 2 if self.text.startswith("\r\n", self.pos) else 1
        return "\n"

    def _decimal_escape(self) -> str:
        match = _DECIMAL_ESCAPE.match(self.text, self.pos)
        if not match or int(match.group()) > _MAX_BYTE:
            raise self.error("decimal escape too large")
        self.pos = match.end()
        return chr(int(match.group()))

    def _hex_escape(self) -> str:
        match = _HEX_ESCAPE.match(self.text, self.pos)
        if not match:
            raise self.error("bad \\x escape")
        self.pos = match.end()
        return chr(int(match.group(1), 16))

    def _skip_space_escape(self) -> str:
        self.pos += 1
        while self.text[self.pos : self.pos + 1] in _SPACE_CHARS:
            self.pos += 1
        return ""

    def _unicode_escape(self) -> str:
        match = _UNICODE_ESCAPE.match(self.text, self.pos)
        if not match:
            raise self.error("bad \\u escape")
        self.pos = match.end()
        return chr(int(match.group(1), 16)).encode("utf-8").decode("latin-1")

    def table(self) -> Any:
        """Parse a table constructor into a list (when it is a plain array) or a dict."""
        self.expect("{")
        array: list[Any] = []
        hashed: dict[Any, Any] = {}
        while self.peek() != "}":
            if not self.peek():
                raise self.error("unfinished table")
            self._field(array, hashed)
            if self.peek() in (",", ";"):
                self.pos += 1
            elif self.peek() != "}":
                raise self.error("expected ',' or '}'")
        self.pos += 1
        return _combine(array, hashed)

    def _field(self, array: list[Any], hashed: dict[Any, Any]) -> None:
        if self.peek() == "[" and self._long_bracket_level() is None:
            self.pos += 1
            key = self.value()
            self.expect("]")
            self.expect("=")
            hashed[key] = self.value()
            return
        match = _NAME_ASSIGNMENT.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            hashed[match.group(1)] = self.value()
        else:
            array.append(self.value())


def _combine(array: list[Any], hashed: dict[Any, Any]) -> Any:
    """Join the positional and keyed parts of a table, as Lua does; nil values vanish."""
    merged: dict[Any, Any] = dict(enumerate(array, start=1))
    merged.update({_normalize_key(key): item for key, item in hashed.items()})
    merged = {key: item for key, item in merged.items() if item is not None}
    if _is_array(merged):
        return [merged[index] for index in range(1, len(merged) + 1)]
    return merged


def _normalize_key(key: Any) -> Any:
    return int(key) if isinstance(key, float) and key.is_integer() else key


def _is_array(table: dict[Any, Any]) -> bool:
    if not table or not all(isinstance(key, int) and not isinstance(key, bool) for key in table):
        return False
    return sorted(table) == list(range(1, len(table) + 1))


def as_table(value: Any) -> dict[Any, Any]:
    """Return ``value`` when it is a Lua table read as a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Read a Lua array that may have come back as a table with gaps, or as junk.

    Lists pass through; tables keep their integer keys in order; anything else is empty.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value[key] for key in sorted(key for key in value if isinstance(key, int) and not isinstance(key, bool))]
    return []


def loads(text: str | bytes) -> dict[str, Any]:
    """Parse a SavedVariables file into ``{global name: value}``."""
    if isinstance(text, str):
        text = text.encode("utf-8", errors="surrogateescape")
    if text.startswith(b"\xef\xbb\xbf"):
        text = text[3:]
    return _Parser(text.decode("latin-1")).document()


def _quote(value: str) -> str:
    raw = value.encode("utf-8", errors="surrogateescape")
    out = ['"']
    for byte in raw:
        char = chr(byte)
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif byte < 32 or byte == 127:
            out.append(f"\\{byte:03d}")
        else:
            out.append(char)
    out.append('"')
    return _from_bytes("".join(out))


def _number(value: int | float) -> str:
    if isinstance(value, float):
        if math.isinf(value):
            return "math.huge" if value > 0 else "-math.huge"
        if math.isnan(value):
            raise LuaDataError("NaN cannot be written to a SavedVariables file")
        if value.is_integer() and abs(value) < 2**53:
            return str(int(value))
        return repr(value)
    return str(value)


def _key(key: Any) -> str:
    if isinstance(key, bool):
        return f"[{'true' if key else 'false'}]"
    if isinstance(key, (int, float)):
        return f"[{_number(key)}]"
    if isinstance(key, str):
        return f"[{_quote(key)}]"
    raise LuaDataError(f"unsupported table key {key!r}")


def _write(value: Any, depth: int, out: list[str]) -> None:
    if isinstance(value, dict):
        _write_table([(f"{_key(key)} = ", item, "") for key, item in value.items() if item is not None], depth, out)
    elif isinstance(value, (list, tuple)):
        if any(item is None for item in value):
            raise LuaDataError("a list cannot hold nil")
        _write_table([("", item, f" -- [{index}]") for index, item in enumerate(value, start=1)], depth, out)
    else:
        out.append(_scalar(value))


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _quote(value)
    raise LuaDataError(f"cannot write {type(value).__name__} to Lua")


def _write_table(fields: list[tuple[str, Any, str]], depth: int, out: list[str]) -> None:
    """Write ``(prefix, value, comment)`` fields the way WoW does, one per line."""
    if not fields:
        out.append("{\n" + "\t" * depth + "}")
        return
    pad = "\t" * (depth + 1)
    out.append("{\n")
    for prefix, item, comment in fields:
        out.append(f"{pad}{prefix}")
        _write(item, depth + 1, out)
        out.append(f",{comment}\n")
    out.append("\t" * depth + "}")


def dumps(variables: dict[str, Any]) -> str:
    """Write globals in the layout WoW itself uses for SavedVariables."""
    out: list[str] = []
    for name, value in variables.items():
        if not _NAME.fullmatch(name):
            raise LuaDataError(f"invalid variable name {name!r}")
        out.append(f"\n{name} = ")
        if value is None:
            out.append("nil")
        else:
            _write(value, 0, out)
        out.append("\n")
    return "".join(out)
