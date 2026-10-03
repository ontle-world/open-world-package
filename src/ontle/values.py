"""Value helpers shared by the rule modules, so Python and the TypeScript implementation read a document the same way.

OWP documents follow the JSON data model (spec section 5.2). A rule that asks for "a non-empty string", or
compares a path to a key, must give the same answer in every implementation; these helpers pin down the
details where Python's built-ins differ from JavaScript's (whitespace, string conversion, lookups by a value
that is not a string).
"""
from __future__ import annotations

from decimal import Decimal
import math
import posixpath
import re
from typing import Any

# The whitespace of JavaScript's `\s` and String.prototype.trim (ECMAScript WhiteSpace and LineTerminator).
# Python's `\s`, str.strip() and str.isspace() also match U+001C-U+001F and U+0085, and do not match U+FEFF.
WHITESPACE = "\t\n\v\f\r    -     　﻿"
WS = f"[{WHITESPACE}]"
_TRIM_RE = re.compile(rf"^{WS}+|{WS}+\Z")


def trim(text: str) -> str:
    """`text` without leading and trailing whitespace (String.prototype.trim)."""
    return _TRIM_RE.sub("", text)


def nonempty_str(value: Any) -> bool:
    """A string with at least one character that is not whitespace."""
    return isinstance(value, str) and trim(value) != ""


def js_string(value: Any) -> str:
    """The text JavaScript's String() gives a JSON value, for messages and identities built from raw metadata."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and abs(value) <= 2 ** 53 - 1:
        return str(value)
    if isinstance(value, (int, float)):
        return _js_number(float(value))  # YAML integers beyond 2^53-1 are inexact numbers in JavaScript
    if isinstance(value, list):
        return ",".join("" if v is None else js_string(v) for v in value)
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def _js_number(f: float) -> str:
    """Number.prototype.toString(): the shortest round-trip digits, laid out as ECMAScript does."""
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "Infinity" if f > 0 else "-Infinity"
    if f == 0:
        return "0"
    sign = "-" if f < 0 else ""
    t = Decimal(repr(abs(f))).normalize().as_tuple()
    digits = "".join(map(str, t.digits))
    k = len(digits)
    n = k + int(t.exponent)  # the decimal point is after the n-th digit
    if k <= n <= 21:
        text = digits + "0" * (n - k)
    elif 0 < n <= 21:
        text = f"{digits[:n]}.{digits[n:]}"
    elif -6 < n <= 0:
        text = "0." + "0" * -n + digits
    else:
        text = digits[0] + (f".{digits[1:]}" if k > 1 else "") + f"e{'+' if n - 1 >= 0 else '-'}{abs(n - 1)}"
    return sign + text


def js_equal(a: Any, b: Any) -> bool:
    """JavaScript's `===` on JSON values: mappings and lists equal only themselves; a boolean never equals a number."""
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def hashable(value: Any) -> bool:
    try:
        hash(value)
    except TypeError:
        return False
    return True


class PathMap(dict):
    """Asset paths to kinds or documents. A lookup by a value that is not a key (a list, a mapping) finds nothing."""

    def get(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
        return super().get(key, default) if hashable(key) else default

    def __contains__(self, key: Any) -> bool:
        return hashable(key) and super().__contains__(key)


def normalize_rel_path(path: Any) -> str | None:
    """A package-relative path in normal form, or None when it is absolute, escapes the root, or is a URL."""
    if not nonempty_str(path) or "\\" in path or "\0" in path:
        return None
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", path, re.IGNORECASE):
        return None
    norm = posixpath.normpath(path)
    if norm == "." or norm == ".." or norm.startswith("../"):
        return None
    return norm


def dig(value: Any, *keys: str) -> Any:
    """value[k1][k2]...; None as soon as a level is not a mapping or lacks the key (TypeScript's get())."""
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
