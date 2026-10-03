"""YAML 1.2 core schema loading and dumping for OWP documents (spec section 5.2).

PyYAML implements YAML 1.1 implicit typing (`yes` -> true, `0755` -> 493, `1:20` -> 80, dates, `<<` merge keys).
OWP documents are read with the YAML 1.2 core schema instead. Mapping keys are strings, as in the JSON data
model, and duplicate keys are errors.
"""
from __future__ import annotations

import re
from typing import Any

import yaml

YAMLError = yaml.YAMLError

_CORE_RESOLVERS = [
    ("tag:yaml.org,2002:null", re.compile(r"^(?:~|null|Null|NULL|)$"), ["~", "n", "N", ""]),
    ("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")),
    ("tag:yaml.org,2002:int", re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"), list("-+0123456789")),
    ("tag:yaml.org,2002:float", re.compile(
        r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
        r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"), list("-+.0123456789")),
]


def _resolvers(base: dict | None = None) -> dict:
    table: dict = {ch: list(entries) for ch, entries in (base or {}).items()}
    for tag, rx, first in _CORE_RESOLVERS:
        for ch in first:
            table.setdefault(ch, []).append((tag, rx))
    return table


class _CoreMixin:
    """YAML 1.2 core schema scalars; non-string and duplicate keys raise an error."""

    yaml_implicit_resolvers = _resolvers()

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key_node, _ in node.value:
                if not (isinstance(key_node, yaml.ScalarNode) and key_node.tag == "tag:yaml.org,2002:str"):
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark, "found a key that is not a string", key_node.start_mark)
                if key_node.value in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark, f"found duplicate key {key_node.value!r}", key_node.start_mark)
                seen.add(key_node.value)
        return super().construct_mapping(node, deep=deep)


class CoreLoader(_CoreMixin, yaml.SafeLoader):
    """Pure-Python loader with the YAML 1.2 core schema."""


# libyaml parses about ten times faster; scalar resolution and construction stay in Python, so both loaders
# return the same data.
FastCoreLoader = type("FastCoreLoader", (_CoreMixin, yaml.CSafeLoader), {}) if yaml.__with_libyaml__ else CoreLoader


def _construct_int(loader: CoreLoader, node: yaml.ScalarNode) -> int:
    value = loader.construct_scalar(node)
    if value.startswith("0o"):
        return int(value[2:], 8)
    if value.startswith("0x"):
        return int(value[2:], 16)
    return int(value, 10)


def _construct_float(loader: CoreLoader, node: yaml.ScalarNode) -> float:
    value = loader.construct_scalar(node).lower()
    if value.endswith(".inf"):
        return float("-inf") if value.startswith("-") else float("inf")
    if value == ".nan":
        return float("nan")
    return float(value)


for _loader in {CoreLoader, FastCoreLoader}:
    _loader.add_constructor("tag:yaml.org,2002:int", _construct_int)
    _loader.add_constructor("tag:yaml.org,2002:float", _construct_float)


class CoreDumper(yaml.SafeDumper):
    """SafeDumper that quotes a string when either YAML 1.1 or the YAML 1.2 core schema would read it as another type."""

    yaml_implicit_resolvers = _resolvers(yaml.SafeDumper.yaml_implicit_resolvers)


def load_yaml(text: str | bytes) -> Any:
    """Parse one YAML document with the YAML 1.2 core schema."""
    return yaml.load(text, Loader=FastCoreLoader)


def dump_yaml(data: Any, **kwargs: Any) -> str:
    kwargs.setdefault("sort_keys", False)
    kwargs.setdefault("allow_unicode", True)
    return yaml.dump(data, Dumper=CoreDumper, **kwargs)
