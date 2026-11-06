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
    def __init__(self, text: str):
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
        match = re.compile(r"\[(=*)\[").match(self.text, self.pos)
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
        char = self.peek()
        if char == "{":
            return self.table()
        if char in "\"'":
            return self.string()
        if char == "[" and self._long_bracket_level() is not None:
            return _from_bytes(self._long_bracket(self._long_bracket_level()))
        if char == "-":
            self.pos += 1
            number = self.value()
            if not isinstance(number, (int, float)) or isinstance(number, bool):
                raise self.error("'-' must be followed by a number")
            return -number
        match = _NAME.match(self.text, self.pos)
        if match and match.group() == "math" and self.text.startswith("math.huge", self.pos):
            end = self.pos + len("math.huge")
            if not (end < len(self.text) and (self.text[end].isalnum() or self.text[end] == "_")):
                self.pos = end
                return math.inf
        if match:
            word = match.group()
            constants = {"true": True, "false": False, "nil": None}
            if word not in constants:
                raise self.error(f"unexpected name {word!r}; only data is allowed")
            self.pos = match.end()
            return constants[word]
        match = _NUMBER.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            token = match.group()
            if token[:2].lower() == "0x":
                return int(token, 16)
            if re.fullmatch(r"[0-9]+", token):
                return int(token)
            return float(token)
        raise self.error("expected a value")

    def string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        text = self.text
        while True:
            if self.pos >= len(text):
                raise self.error("unfinished string")
            char = text[self.pos]
            if char == quote:
                self.pos += 1
                return _from_bytes("".join(out))
            if char == "\n":
                raise self.error("unfinished string")
            if char != "\\":
                out.append(char)
                self.pos += 1
                continue
            self.pos += 1
            esc = text[self.pos : self.pos + 1]
            if esc in _SIMPLE_ESCAPES:
                out.append(_SIMPLE_ESCAPES[esc])
                self.pos += 1
            elif esc == "\r":
                out.append("\n")
                self.pos += 2 if text.startswith("\r\n", self.pos) else 1
            elif esc.isdigit():
                digits = re.compile(r"[0-9]{1,3}").match(text, self.pos).group()
                code = int(digits)
                if code > 255:
                    raise self.error("decimal escape too large")
                out.append(chr(code))
                self.pos += len(digits)
            elif esc == "x":
                hexes = text[self.pos + 1 : self.pos + 3]
                if not re.fullmatch(r"[0-9a-fA-F]{2}", hexes):
                    raise self.error("bad \\x escape")
                out.append(chr(int(hexes, 16)))
                self.pos += 3
            elif esc == "z":
                self.pos += 1
                while self.pos < len(text) and text[self.pos] in " \t\r\n\f\v":
                    self.pos += 1
            elif esc == "u":
                match = re.compile(r"u\{([0-9a-fA-F]+)\}").match(text, self.pos)
                if not match:
                    raise self.error("bad \\u escape")
                out.append(chr(int(match.group(1), 16)).encode("utf-8").decode("latin-1"))
                self.pos = match.end()
            else:
                raise self.error(f"bad escape \\{esc}")

    def table(self) -> Any:
        self.expect("{")
        array: list[Any] = []
        hashed: dict[Any, Any] = {}
        while self.peek() != "}":
            if not self.peek():
                raise self.error("unfinished table")
            if self.peek() == "[" and self._long_bracket_level() is None:
                self.pos += 1
                key = self.value()
                self.expect("]")
                self.expect("=")
                hashed[key] = self.value()
            else:
                match = _NAME.match(self.text, self.pos)
                after = match and self.text[match.end() :].lstrip(" \t\r\n")
                if match and after.startswith("=") and not after.startswith("=="):
                    self.pos = match.end()
                    self.expect("=")
                    hashed[match.group()] = self.value()
                else:
                    array.append(self.value())
            if self.peek() in (",", ";"):
                self.pos += 1
            elif self.peek() != "}":
                raise self.error("expected ',' or '}'")
        self.pos += 1
        return _combine(array, hashed)


def _combine(array: list[Any], hashed: dict[Any, Any]) -> Any:
    merged: dict[Any, Any] = {}
    for index, item in enumerate(array, start=1):
        merged[index] = item
    for key, item in hashed.items():
        if isinstance(key, float) and key.is_integer():
            key = int(key)
        merged[key] = item
    merged = {key: item for key, item in merged.items() if item is not None}
    if merged and all(isinstance(k, int) and not isinstance(k, bool) for k in merged):
        if sorted(merged) == list(range(1, len(merged) + 1)):
            return [merged[index] for index in range(1, len(merged) + 1)]
    return merged


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
    if isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, (int, float)):
        out.append(_number(value))
    elif isinstance(value, str):
        out.append(_quote(value))
    elif isinstance(value, (list, tuple, dict)):
        pad = "\t" * (depth + 1)
        if not value:
            out.append("{\n" + "\t" * depth + "}")
            return
        out.append("{\n")
        if isinstance(value, dict):
            for key, item in value.items():
                if item is None:
                    continue
                out.append(f"{pad}{_key(key)} = ")
                _write(item, depth + 1, out)
                out.append(",\n")
        else:
            for index, item in enumerate(value, start=1):
                if item is None:
                    raise LuaDataError("a list cannot hold nil")
                out.append(pad)
                _write(item, depth + 1, out)
                out.append(f", -- [{index}]\n")
        out.append("\t" * depth + "}")
    else:
        raise LuaDataError(f"cannot write {type(value).__name__} to Lua")


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
