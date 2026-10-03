"""`.owpignore`: package-relative paths that are not package files (spec section 5).

The syntax is the gitignore subset: one pattern per line; blank lines and lines starting with `#` are skipped;
`!` re-includes; a trailing `/` matches directories only; a pattern with another `/` is anchored at the package
root, otherwise it matches a name at any depth; `*` and `?` do not cross `/`, `**` does, `[...]` is a character
class. The last matching pattern wins, and a file inside an excluded directory cannot be re-included.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

IGNORE_FILE = ".owpignore"


@dataclass(frozen=True)
class _Rule:
    regex: re.Pattern[str]
    negate: bool
    dir_only: bool
    anchored: bool


def _glob_regex(glob: str) -> str:
    out: list[str] = []
    i, n = 0, len(glob)
    while i < n:
        c = glob[i]
        if glob.startswith("**", i):
            before = i == 0 or glob[i - 1] == "/"
            after = i + 2 == n or glob[i + 2] == "/"
            if before and after:
                if i + 2 == n:
                    out.append(".*")  # trailing "/**": everything inside
                    i += 2
                else:
                    out.append("(?:.*/)?")  # "**/": zero or more directories
                    i += 3
                continue
            out.append("[^/]*")  # "**" inside a name acts like "*"
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[" and (end := glob.find("]", i + 2 if glob[i + 1:i + 2] in ("!", "^") else i + 1)) != -1:
            body = glob[i + 1:end]
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = end + 1
        elif c == "\\" and i + 1 < n:
            out.append(re.escape(glob[i + 1]))
            i += 2
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def parse_ignore(text: str) -> list[_Rule]:
    rules: list[_Rule] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        elif line.startswith(("\\#", "\\!")):
            line = line[1:]
        dir_only = line.endswith("/")
        line = line.rstrip("/")
        if not line:
            continue
        anchored = "/" in line
        line = line.lstrip("/")
        rules.append(_Rule(re.compile(_glob_regex(line) + r"\Z"), negate, dir_only, anchored))
    return rules


def load_ignore(root: Path) -> list[_Rule]:
    try:
        return parse_ignore((root / IGNORE_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return []


def is_ignored(rules: list[_Rule], rel: str) -> bool:
    """Whether the package-relative POSIX file path `rel` is excluded."""
    if not rules:
        return False
    parts = rel.split("/")
    for i in range(1, len(parts) + 1):
        is_dir = i < len(parts)
        sub = "/".join(parts[:i])
        excluded = False
        for rule in rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.regex.match(sub if rule.anchored else parts[i - 1]):
                excluded = not rule.negate
        if excluded:
            return True
    return False
