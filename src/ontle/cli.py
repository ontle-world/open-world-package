from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .core import OWPError, deterministic_pack, inspect_package, load_manifest, validate_package, verify_archive
from .ews import check_ews, compile_ews, load_document
from .ontology import export_rdf, write_term_index
from .resolve import ews_jsonld, resolve_package, validate_resolved
from .scaffold import add_asset, add_extension, init_project


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
    observations = None
    for path in args.observations:
        doc = load_document(path)
        if not isinstance(doc, dict):
            raise OWPError(f"observations file {path} must contain a YAML mapping")
        if observations is None:
            observations = doc
        else:  # merge several ObservationSets; ids must stay unique (checked by the compiler)
            merged = list((observations.get("spec") or {}).get("observations") or []) + list((doc.get("spec") or {}).get("observations") or [])
            observations = {**observations, "spec": {**(observations.get("spec") or {}), "observations": merged}}
            observations["spec"].pop("provenance", None)
    ews = compile_ews(args.world, args.compiler, observations, args.as_of)
    if args.jsonld:
        print(json.dumps(ews_jsonld(args.world, ews, args.source), indent=2, ensure_ascii=False))
        return 0
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


def cmd_ontology_index(args):
    root, _ = load_manifest(args.path)
    print(write_term_index(root, root / "owp.yaml"))
    return 0


def cmd_export(args):
    root, manifest = load_manifest(args.path)
    if manifest.get("kind") != "OntologyPackage":
        raise OWPError("ontle export reads an OntologyPackage")
    print(export_rdf(root, manifest, args.format), end="")
    return 0


def cmd_kg_extract(args):
    from .extraction import run_extraction
    parameters = {}
    for item in args.param:
        name, sep, value = item.partition("=")
        if not sep:
            raise OWPError(f"--param must be name=value: {item}")
        parameters[name] = yaml.safe_load(value) if value[:1] in "[{" or value in {"true", "false"} or value.replace(".", "", 1).isdigit() else value
    results = json.loads(Path(args.results).read_text(encoding="utf-8")) if args.results else None
    print(yaml.safe_dump(run_extraction(args.package, args.profile, parameters, results), sort_keys=False, allow_unicode=True), end="")
    return 0


def cmd_inspect(args):
    print(json.dumps(inspect_package(args.path, graph=args.graph, resolved_views=args.resolved_views), indent=2, ensure_ascii=False))
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
    if args.asset_kind == "extension":
        name = add_extension(args.path, args.name, args.as_name, args.must_understand)
        print(f"declared extension {name} -> {args.name}")
        return 0
    target = add_asset(args.path, args.asset_kind, args.name, args.specializes)
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
    y.add_argument("--observations", required=True, action="append", help="ObservationSet YAML file (repeatable; sets are merged)")
    y.add_argument("--as-of", required=True, help="compilation time, UTC YYYY-MM-DDTHH:MM:SSZ")
    y.add_argument("--jsonld", action="store_true", help="print JSON with an @context from the World's SemanticBinding (needs its ontology dependencies)")
    y.add_argument("--source", action="append", default=[], help="package source for the ontology dependencies (repeatable; ONTLE_PATH is also read)")
    y.set_defaults(func=cmd_ews_compile)
    y = esp.add_parser("check", help="check an EWS document against its State Compiler output contract")
    y.add_argument("ews", help="EffectiveWorldState YAML file")
    y.add_argument("--world", required=True, help="World package directory")
    y.set_defaults(func=cmd_ews_check)

    x = sp.add_parser("inspect", help="inspect package identity and summary")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--graph", action="store_true", help="include the reference graph between the package, its dependencies, and its assets")
    x.add_argument("--resolved-views", action="store_true", help="include each World View with specializes applied")
    x.set_defaults(func=cmd_inspect)

    x = sp.add_parser("ontology", help="ontology tooling")
    osp = x.add_subparsers(dest="ontology_command", required=True)
    y = osp.add_parser("index", help="write spec.ontology.termIndex from the schema entrypoints (RDF needs: pip install 'ontle-open-world[rdf]')")
    y.add_argument("path", nargs="?", default=".")
    y.set_defaults(func=cmd_ontology_index)

    x = sp.add_parser("kg", help="knowledge graph tooling (experimental, spec Appendix C.1)")
    ksp = x.add_subparsers(dest="kg_command", required=True)
    y = ksp.add_parser("extract", help="run a KnowledgeExtractionProfile and print the ObservationSet (SPARQL needs the rdf extra)")
    y.add_argument("package", help="package directory")
    y.add_argument("--profile", required=True, help="KnowledgeExtractionProfile asset path")
    y.add_argument("--param", action="append", default=[], help="parameter value name=value (repeatable)")
    y.add_argument("--results", help="JSON file of query result rows; skips running the query")
    y.set_defaults(func=cmd_kg_extract)

    x = sp.add_parser("export", help="export an OntologyPackage's owp-yaml schema as RDF")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--format", choices=["turtle", "jsonld"], default="turtle")
    x.set_defaults(func=cmd_export)

    x = sp.add_parser("pack", help="build a deterministic .owp.zip archive")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--output")
    x.set_defaults(func=cmd_pack)

    x = sp.add_parser("verify", help="verify hashes inside an .owp.zip archive")
    x.add_argument("archive")
    x.set_defaults(func=cmd_verify)

    x = sp.add_parser("add", help="add optional scaffolding to an existing package")
    x.add_argument("asset_kind", choices=["view", "compiler", "source", "observation", "action", "commit", "effect", "model", "adapter", "scenario", "dataset", "eval", "verifier", "test", "asset", "extension",
                                         "task", "pattern", "artifact", "template", "consumer", "knowledge"])
    x.add_argument("name", help="asset name, or for 'extension' the defining package <namespace>/<name>@<version>")
    x.add_argument("--path", default=".")
    x.add_argument("--as", dest="as_name", help="extension: local name (default: package name without a trailing -extension)")
    x.add_argument("--must-understand", action="store_true", help="extension: runtimes that do not implement it must not run the package")
    x.add_argument("--specializes", help="view: path of the local World View this View specializes (experimental)")
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
