from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .core import OWPError, deterministic_pack, inspect_package, validate_package, verify_archive
from .ews import check_ews, compile_ews, load_document
from .resolve import resolve_package, validate_resolved
from .scaffold import add_asset, init_project


def cmd_init(args):
    path = init_project(args.name, args.namespace, args.template, args.destination)
    print(path)
    return 0


def cmd_validate(args):
    result = validate_resolved(args.path, args.source)[0] if args.resolve else validate_package(args.path)
    for w in result.warnings:
        print(f"WARN: {w}")
    if result.valid:
        print("VALID")
        return 0
    for e in result.errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1


def cmd_resolve(args):
    resolution = resolve_package(args.path, args.source)
    print(json.dumps(resolution.to_dict(), indent=2, ensure_ascii=False))
    return 1 if resolution.errors else 0


def cmd_ews_compile(args):
    observations = load_document(args.observations)
    if not isinstance(observations, dict):
        raise OWPError("observations file must contain a YAML mapping")
    ews = compile_ews(args.world, args.compiler, observations, args.as_of)
    print(yaml.safe_dump(ews, sort_keys=False, allow_unicode=True), end="")
    return 0


def cmd_ews_check(args):
    ews = load_document(args.ews)
    errors = check_ews(args.world, ews if isinstance(ews, dict) else {})
    if not errors:
        print("VALID")
        return 0
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1


def cmd_inspect(args):
    print(json.dumps(inspect_package(args.path), indent=2, ensure_ascii=False))
    return 0


def cmd_pack(args):
    out = deterministic_pack(args.path, args.output)
    print(out)
    return 0


def cmd_verify(args):
    ok, errors = verify_archive(args.archive)
    if ok:
        print("VERIFIED")
        return 0
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1


def cmd_add(args):
    target = add_asset(args.path, args.asset_kind, args.name)
    print(target)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="ontle", description="Reference CLI for Open World Packages (OWP)")
    p.add_argument("--version", action="version", version=f"ontle {__version__}")
    sp = p.add_subparsers(dest="command", required=True)

    x = sp.add_parser("init", help="create a starter OWP project")
    x.add_argument("name")
    x.add_argument("--namespace", default="example")
    x.add_argument("--template", default="minimal", choices=["minimal", "enterprise", "ontology", "worldmodel", "worldmodel-multimodal"])
    x.add_argument("--destination")
    x.set_defaults(func=cmd_init)

    x = sp.add_parser("validate", help="validate an OWP project")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--resolve", action="store_true", help="also resolve dependencies and check cross-package grounding")
    x.add_argument("--source", action="append", default=[], help="package source: directory, .owp.zip, or git+<url>@<rev>[#subdir=<path>] (repeatable; ONTLE_PATH is also read)")
    x.set_defaults(func=cmd_validate)

    x = sp.add_parser("resolve", help="resolve the dependency closure of an OWP project")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--source", action="append", default=[], help="package source: directory, .owp.zip, or git+<url>@<rev>[#subdir=<path>] (repeatable; ONTLE_PATH is also read)")
    x.set_defaults(func=cmd_resolve)

    x = sp.add_parser("ews", help="compile or check Effective World State documents")
    esp = x.add_subparsers(dest="ews_command", required=True)
    y = esp.add_parser("compile", help="run a declarative State Compiler over an ObservationSet")
    y.add_argument("world", help="World package directory")
    y.add_argument("--compiler", required=True, help="StateCompilerProfile asset path inside the World package")
    y.add_argument("--observations", required=True, help="ObservationSet YAML file")
    y.add_argument("--as-of", required=True, help="compilation time, UTC YYYY-MM-DDTHH:MM:SSZ")
    y.set_defaults(func=cmd_ews_compile)
    y = esp.add_parser("check", help="check an EWS document against its State Compiler output contract")
    y.add_argument("ews", help="EffectiveWorldState YAML file")
    y.add_argument("--world", required=True, help="World package directory")
    y.set_defaults(func=cmd_ews_check)

    x = sp.add_parser("inspect", help="inspect package identity and summary")
    x.add_argument("path", nargs="?", default=".")
    x.set_defaults(func=cmd_inspect)

    x = sp.add_parser("pack", help="build a deterministic .owp.zip archive")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--output")
    x.set_defaults(func=cmd_pack)

    x = sp.add_parser("verify", help="verify hashes inside an .owp.zip archive")
    x.add_argument("archive")
    x.set_defaults(func=cmd_verify)

    x = sp.add_parser("add", help="add optional scaffolding to an existing package")
    x.add_argument("asset_kind", choices=["view", "compiler", "source", "observation", "action", "commit", "effect", "model", "adapter", "scenario", "dataset", "eval", "verifier", "test", "asset"])
    x.add_argument("name")
    x.add_argument("--path", default=".")
    x.set_defaults(func=cmd_add)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except OWPError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
