from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from . import __version__
from .core import OWPError, deterministic_pack, inspect_package, load_manifest, package_files, validate_package, verify_archive
from .ews import check_ews, compile_ews, load_document
from .ontology import export_rdf, write_term_index
from .resolve import ews_jsonld, ews_ngsi, ews_rdf, resolve_package, validate_resolved
from .scaffold import add_extension, init_project, new_asset
from .yamlio import dump_yaml, load_yaml


def cmd_init(args):
    path = init_project(args.name, args.namespace, args.template, args.destination, args.world, args.view)
    print(path)  # stdout is the project path alone, for scripts
    for line in next_steps(path, args.template):
        print(line, file=sys.stderr)
    return 0


def next_steps(path: Path, template: str) -> list[str]:
    """What to do after `ontle init`: edit, validate, report."""
    try:
        shown = path.relative_to(Path.cwd())
    except ValueError:
        shown = path
    card = {"ontology": "ONTOLOGY.md", "worldmodel": "WORLDMODEL.md", "worldmodel-multimodal": "WORLDMODEL.md"}.get(template, "WORLD.md")
    return ["Next:",
            f"  1. edit {shown / 'owp.yaml'} (title, description, license) and {shown / card}",
            f"  2. ontle validate {shown}",
            f"  3. ontle inspect {shown} --report    # what a catalog would show, with hints"]


def cmd_validate(args):
    notes: list[str] = []
    if args.resolve:
        result = validate_resolved(args.path, args.source + project_sources(args.path))[0]
    else:
        result = validate_package(args.path)
        spec = (result.manifest or {}).get("spec")
        deps = (spec.get("dependencies") if isinstance(spec, dict) else None) or []
        if result.valid and deps:
            # Check the cross-package rules too when every dependency can be found; otherwise say what was skipped.
            full, resolution = validate_resolved(args.path, args.source + project_sources(args.path))
            missing = [e.split("cannot resolve ", 1)[-1] for e in full.errors if e.startswith(("resolve.unresolved", "resolve.reference"))]
            if any("the version differs" in m for m in missing):  # the package is there; spec.dependencies names another version
                notes.append(f"WARN: dependencies not resolved: {'; '.join(missing)}. Fix the version in spec.dependencies "
                             "(and semanticGrounding); grounding was not checked.")
            elif missing:
                notes.append(f"NOTE: checked this package only; dependencies not found: {', '.join(missing)}. "
                             "Grounding and other cross-package rules were not checked: pass --source <dir|zip> or set ONTLE_PATH.")
            else:
                result = full
                n = len(resolution.packages) - 1
                notes.append(f"NOTE: resolved {n} {'dependency' if n == 1 else 'dependencies'} and checked cross-package rules")
    for w in result.warnings:
        print(f"WARN: {w}")
    if result.valid:
        for n in notes:
            print(n)
        print("VALID")
        return 0
    for line in fold_errors(result.errors):
        print(line, file=sys.stderr)
    return 1


def project_sources(path: str) -> list[str]:
    """Package sources recorded by `ontle init --world` in .ontle/project.yaml, relative to the package root."""
    state = Path(path) / ".ontle" / "project.yaml"
    try:
        data = load_yaml(state.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return []
    return [str((Path(path) / s).resolve()) for s in data.get("sources") or [] if isinstance(s, str)]


def fold_errors(errors: list[str]) -> list[str]:
    """Print order for errors: an unknown field with a suggestion first, then the errors that mention the
    suggested field, indented as likely consequences. Only the presentation changes; every error is printed."""
    roots: list[tuple[str, str]] = []
    for e in errors:
        m = re.search(r"did you mean '([^']+)'", e) if e.startswith("schema.unknown-field:") else None
        if m:
            roots.append((e, m.group(1)))
    lines: list[str] = []
    shown: set[int] = set()
    for root, suggestion in roots:
        lines.append(f"ERROR: {root}")
        shown.add(errors.index(root))
        for i, e in enumerate(errors):
            if i not in shown and not e.startswith("schema.unknown-field:") and re.search(rf"\b{re.escape(suggestion)}\b", e):
                lines.append(f"  likely caused by the error above: {e}")
                shown.add(i)
    lines += [f"ERROR: {e}" for i, e in enumerate(errors) if i not in shown]
    return collapse_after_unresolved(lines)


def collapse_after_unresolved(lines: list[str]) -> list[str]:
    """When a dependency does not resolve, the terms it would define are unknown: print the first such error per
    package and count the rest, instead of one line per term."""
    if not any(line.startswith("ERROR: resolve.unresolved:") for line in lines):
        return lines
    out: list[str] = []
    hidden: dict[str, int] = {}
    for line in lines:
        m = re.match(r"ERROR: (grounding\.prefix-unknown): ([^:]+@[^:]+): ", line)
        if m:
            key = f"{m.group(1)} in {m.group(2)}"
            if key in hidden:
                hidden[key] += 1
                continue
            hidden[key] = 0
        out.append(line)
    out += [f"  ... and {n} more {key}, likely caused by the unresolved dependency above" for key, n in hidden.items() if n]
    return out


def cmd_resolve(args):
    resolution = resolve_package(args.path, args.source)
    print(json.dumps(resolution.to_dict(), indent=2, ensure_ascii=False))
    return 1 if resolution.errors else 0


def merged_observations(paths: list[str]) -> Any:
    """One ObservationSet from several files; ids must stay unique (checked by the compiler)."""
    docs = [load_document(path) for path in paths]
    if len(docs) == 1:
        return docs[0]
    merged: list = []
    for doc in docs:
        spec = doc.get("spec") if isinstance(doc, dict) else None
        listed = spec.get("observations") if isinstance(spec, dict) else None
        merged += listed if isinstance(listed, list) else []
    return {"apiVersion": "openworld/v1alpha1", "kind": "ObservationSet", "spec": {"observations": merged}}


def cmd_ews_compile(args):
    observations = merged_observations(args.observations)
    compiler = args.compiler
    if compiler is None:
        manifest = load_manifest(args.world)[1]
        spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
        world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
        compiler = world.get("defaultStateCompiler")
        if not isinstance(compiler, str):
            raise OWPError("the World declares no spec.world.defaultStateCompiler; pass --compiler")
    ews = compile_ews(args.world, compiler, observations, args.as_of)
    if args.jsonld:
        print(json.dumps(ews_jsonld(args.world, ews, args.source), indent=2, ensure_ascii=False))
        return 0
    if args.rdf:
        print(ews_rdf(args.world, ews, observations, args.source), end="")
        return 0
    if args.ngsi_ld:
        print(json.dumps(ews_ngsi(args.world, ews, observations, args.source), indent=2, ensure_ascii=False))
        return 0
    print(dump_yaml(ews), end="")
    return 0


def cmd_observations_csv(args):
    from .observations import csv_observations
    print(dump_yaml(csv_observations(args.file, args.type, args.subject, args.time, args.number, args.list, args.separator,
                                     args.column)), end="")
    return 0


def cmd_ews_check(args):
    try:
        ews = load_document(args.ews, rule="ews.kind")
    except OWPError as exc:
        errors = [str(exc)]
    else:
        errors = check_ews(args.world, ews)
    if not errors and args.observations:  # also recompile and compare: the values, not only the shape
        from .ews import ews_differences
        spec = ews.get("spec") or {}
        compiler = (spec.get("stateCompiler") or "").partition("#")[2]
        as_of = args.as_of or (spec.get("context") or {}).get("asOf")
        if not compiler or not isinstance(as_of, str):
            errors = ["ews check --observations needs the EWS's spec.stateCompiler and spec.context.asOf (or --as-of)"]
        else:
            compiled = compile_ews(args.world, compiler, merged_observations(args.observations), as_of)
            errors = [f"compiled value differs: {d}" for d in ews_differences(ews, compiled)]
    if not errors and args.source:
        for w in ews_range_warnings(args.world, ews, args.source):
            print(f"WARN: {w}")
    if not errors:
        print("VALID")
        return 0
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1


def ews_range_warnings(world: str, ews: dict, sources: list[str]) -> list[str]:
    """Values of fields bound to an enum-typed property (owp-yaml schemas of the World's ontologies) that are not values
    of the enum. A runtime data finding, not a validation rule."""
    from .binding import enum_ranges
    from .resolve import binding_context, resolve_package
    resolution = resolve_package(world, sources)
    binding_docs, prefixes, model = binding_context(resolution.root, resolution)
    if not binding_docs or model is None:
        return []
    spec = ews.get("spec") or {}
    out: list[str] = []
    for field, (enum_iri, allowed) in enum_ranges(binding_docs, prefixes, model).items():
        for section in ("state", "unresolved"):
            value = (spec.get(section) or {}).get(field)
            groups = value.items() if isinstance(value, dict) else [(None, value)]
            for subject, v in groups:
                for x in v if isinstance(v, list) else [v]:
                    if x is not None and str(x) not in allowed:
                        at = f"{field}" + (f" subject {subject!r}" if subject is not None else "")
                        out.append(f"value outside range: {section}.{at} is {x!r}, not one of {enum_iri} ({', '.join(sorted(allowed))})")
    return out


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
        parameters[name] = load_yaml(value) if value[:1] in "[{" or value in {"true", "false"} or value.replace(".", "", 1).isdigit() else value
    results = json.loads(Path(args.results).read_text(encoding="utf-8")) if args.results else None
    print(dump_yaml(run_extraction(args.package, args.profile, parameters, results)), end="")
    return 0


def cmd_kg_check(args):
    from .kgcheck import ADVICE, check_bindings, check_knowledge_graphs
    if args.bindings:
        notes: list[str] = []
        found = check_bindings(args.package, args.source, notes)
        if args.json:
            print(json.dumps({"warnings": found, "notes": list(dict.fromkeys(notes))}, indent=2, ensure_ascii=False))
            return 0
        for w in found:
            print(f"WARN: {w}")
        for n in dict.fromkeys(notes):
            print(f"NOTE: {n}")
        print(f"{len(found)} binding warning{'' if len(found) == 1 else 's'}")
        return 0
    report = check_knowledge_graphs(args.package, args.source)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0 if report.ok else 1
    for f in report.findings:
        advice = f.code in ADVICE
        print(("WARN: " if advice else "ERROR: ") + f.line(), file=sys.stdout if advice else sys.stderr)
    for rel in report.skipped:
        print(f"SKIP: {rel}: not a local RDF graph with spec.conformsTo.ontology")
    for n in report.notes:
        print(f"NOTE: {n}")
    if not report.checked and not report.findings:
        print("no knowledge graph to check")
    elif report.ok:
        print("OK: " + ", ".join(report.checked))
    return 0 if report.ok else 1


def cmd_diff(args):
    from .ontodiff import diff_ontologies
    result = diff_ontologies(args.old, args.new)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if result.enough else 1
    print(f"{result.old} -> {result.new}")
    for c in result.changes:
        print(f"{c.level}: {c.change}")
    for n in result.notes:
        print(f"NOTE: {n}")
    need = result.required
    if need is None:
        print("no term changed")
        return 0
    zero = result.old.rsplit("@", 1)[1].startswith("0.")
    print(f"changes call for: {need}" + (" (a " + {"major": "minor", "minor": "patch", "patch": "patch"}[need] + " increment while the major version is 0)" if zero else ""))
    if result.enough:
        print(f"OK: the {result.increment} increment is enough")
        return 0
    print(f"ERROR: the version increment ({result.increment or 'none'}) is not enough", file=sys.stderr)
    return 1


def cmd_interop_mcp(args):
    from .interop import mcp_description
    print(json.dumps(mcp_description(args.world), indent=2, ensure_ascii=False))
    return 0


def cmd_mcp(args):
    from .mcp import run
    return run(args.package, args.observations, args.source + project_sources(args.package))


def cmd_fetch(args):
    from .distribution import fetch_package
    for path in fetch_package(args.path, args.into):
        print(path)
    return 0


def cmd_lock(args):
    from .distribution import pin_https_refs
    changed = pin_https_refs(args.path)
    print("\n".join(f"pinned {p}" for p in changed) or "nothing to pin")
    return 0


def cmd_push(args):
    from .distribution import oci_push
    print(oci_push(args.archive, args.reference))
    return 0


def cmd_sign(args):
    from .distribution import sign_archive
    print(sign_archive(args.archive, args.key))
    return 0


def cmd_index_build(args):
    from .distribution import build_index
    archives = [Path(a) for a in args.archives]
    index = build_index(archives, Path(args.base) if args.base else None, args.base_url, terms=args.terms)
    text = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def cmd_evidence_check(args):
    from .distribution import check_detached_evidence
    errors = check_detached_evidence(load_document(args.evidence), args.package)
    if not errors:
        print("VALID")
        return 0
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1


def cmd_evidence_attach(args):
    from .distribution import oci_attach_evidence
    print(oci_attach_evidence(args.reference, args.evidence))
    return 0


def cmd_catalog(args):
    from .distribution import catalog
    print(catalog(args.path, args.format), end="")
    return 0


def cmd_inspect(args):
    if args.report:
        from .report import package_report
        print(json.dumps(package_report(args.path), indent=2, ensure_ascii=False))
        return 0
    from .report import opened_package
    with opened_package(args.path) as (root, integrity):
        summary = inspect_package(root, graph=args.graph, resolved_views=args.resolved_views)
        if integrity is not None:  # an archive: name it, not the temporary directory it was read from
            summary["root"] = str(Path(args.path).resolve())
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_pack(args):
    if args.list:  # preview only: nothing is written
        root = load_manifest(args.path)[0]
        for f in package_files(root):
            print(f.relative_to(root).as_posix())
        return 0
    out = deterministic_pack(args.path, args.output, vendor=args.vendor)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    print(f"{len(names)} files", file=sys.stderr)
    from .report import pack_size_hint
    hint = pack_size_hint(out.stat().st_size, PACK_SIZE_HINT)
    if hint:
        print(f"WARN: {hint}", file=sys.stderr)
    print(out)  # stdout is the archive path alone, for scripts
    return 0


PACK_SIZE_HINT = 50_000_000  # bytes; registries set their own upload limits


def cmd_verify(args):
    ok, errors = verify_archive(args.archive)
    if ok and args.signature:
        from .distribution import verify_signature
        verify_signature(args.archive, args.key, args.identity, args.issuer)
        print("VERIFIED (hashes and signature)")
        return 0
    if ok:
        print("VERIFIED")
        return 0
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1


def cmd_add(args):
    name = add_extension(args.path, args.name, args.as_name, args.must_understand)
    print(f"declared extension {name} -> {args.name}")
    return 0


def cmd_new(args):
    print(new_asset(args.package, args.kind, args.path, args.specializes, args.composes))
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
    x.add_argument("--world", help="World Model templates: ground the model in this World (a package directory or "
                                    "<namespace>/<name>@<version>) and add it to spec.dependencies")
    x.add_argument("--view", help="with --world: the World View to ground in (a path in the World); its State Compiler "
                                   "is found by worldViewRef. Default: the World's defaultView")
    x.set_defaults(func=cmd_init)

    x = sp.add_parser("validate", help="validate an OWP project")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--resolve", action="store_true", help="require dependencies to resolve (an unresolved one is an error); "
                   "without it, cross-package rules are checked when every dependency is found, and skipped with a NOTE otherwise")
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
    y.add_argument("--compiler", help="StateCompilerProfile path inside the World package (default: the World's defaultStateCompiler)")
    y.add_argument("--observations", required=True, action="append", help="ObservationSet file (YAML or JSON), relative to the current directory (repeatable; sets are merged)")
    y.add_argument("--as-of", required=True, help="compilation time, UTC YYYY-MM-DDTHH:MM:SSZ")
    y.add_argument("--jsonld", action="store_true", help="print JSON with an @context from the World's SemanticBinding (needs its ontology dependencies)")
    y.add_argument("--ngsi-ld", action="store_true", help="print NGSI-LD entities (normalized): per-subject fields as attributes, unresolved alternatives as datasetId instances")
    y.add_argument("--rdf", action="store_true", help="print Turtle 1.2 in the OWP vocabulary: each value a reified, unasserted triple with its provenance (PROV) and derivation")
    y.add_argument("--source", action="append", default=[], help="package source for the ontology dependencies (repeatable; ONTLE_PATH is also read)")
    y.set_defaults(func=cmd_ews_compile)
    y = esp.add_parser("check", help="check an EWS document against its State Compiler output contract")
    y.add_argument("ews", help="EffectiveWorldState YAML file")
    y.add_argument("--world", required=True, help="World package directory")
    y.add_argument("--observations", action="append", default=[], help="also compile these ObservationSet files with the EWS's State "
                   "Compiler and compare the values (repeatable)")
    y.add_argument("--as-of", help="with --observations: compilation time (default: the EWS's spec.context.asOf)")
    y.add_argument("--source", action="append", default=[], help="package source for the World's ontologies: warn about values of fields bound "
                   "to an enum-typed property that are not values of the enum (repeatable; ONTLE_PATH is also read)")
    y.set_defaults(func=cmd_ews_check)

    x = sp.add_parser("observations", help="make ObservationSet documents from records")
    osp2 = x.add_subparsers(dest="observations_command", required=True)
    y = osp2.add_parser("csv", help="one CSV of one record type -> an ObservationSet on stdout (merge sets with repeated ews compile --observations)")
    y.add_argument("file")
    y.add_argument("--type", required=True, help="observation type, as State Compiler bindings name it in `from`, for example QMS.claim")
    y.add_argument("--subject", required=True, help="column with the record's subject (the entity it is about)")
    y.add_argument("--time", required=True, help="column with the time it was observed, UTC YYYY-MM-DDTHH:MM:SSZ")
    y.add_argument("--number", action="append", default=[], help="column whose values are numbers (repeatable)")
    y.add_argument("--list", action="append", default=[], help="column whose values are lists (repeatable)")
    y.add_argument("--separator", default=";", help="list separator (default ';')")
    y.add_argument("--column", action="append", default=[], help="keep only these value columns (repeatable; default: every other column)")
    y.set_defaults(func=cmd_observations_csv)

    x = sp.add_parser("inspect", help="inspect package identity and summary")
    x.add_argument("path", nargs="?", default=".", help="package directory or .owp.zip archive")
    x.add_argument("--report", action="store_true", help="print the PackageReport (schemas/package-report.schema.json): verdict, "
                   "profile, asset counts, binding coverage, external references, evidence, card hints; with an archive, its digest and size")
    x.add_argument("--graph", action="store_true", help="include the reference graph between the package, its dependencies, and its assets")
    x.add_argument("--resolved-views", action="store_true", help="include each World View with specializes or composes applied")
    x.set_defaults(func=cmd_inspect)

    x = sp.add_parser("ontology", help="ontology tooling")
    osp = x.add_subparsers(dest="ontology_command", required=True)
    y = osp.add_parser("index", help="write spec.ontology.termIndex from the schema entrypoints (RDF needs: pip install 'ontle[rdf]')")
    y.add_argument("path", nargs="?", default=".")
    y.set_defaults(func=cmd_ontology_index)

    x = sp.add_parser("kg", help="knowledge graph tooling (spec section 19)")
    ksp = x.add_subparsers(dest="kg_command", required=True)
    y = ksp.add_parser("extract", help="run a KnowledgeExtractionProfile and print the ObservationSet (SPARQL needs the rdf extra)")
    y.add_argument("package", help="package directory")
    y.add_argument("--profile", required=True, help="KnowledgeExtractionProfile asset path")
    y.add_argument("--param", action="append", default=[], help="parameter value name=value (repeatable)")
    y.add_argument("--results", help="JSON file of query result rows; skips running the query")
    y.set_defaults(func=cmd_kg_extract)

    y = ksp.add_parser("check", help="check that a KnowledgeAsset graph uses only the classes and properties of its ontology, within their domains and ranges, "
                       "and that it satisfies the ontology's SHACL shapes; also check the terms the SPARQL queries of its KnowledgeExtractionProfiles name "
                       "(needs the rdf extra; shapes need the shacl extra)")
    y.add_argument("package", nargs="?", default=".", help="package directory")
    y.add_argument("--source", action="append", default=[], help="package source for the ontology dependencies (repeatable; ONTLE_PATH is also read)")
    y.add_argument("--bindings", action="store_true", help="instead: check the SemanticBinding's field paths and value maps against the "
                   "RDF T-box of the dependency ontologies, RDF schema entrypoints included (binding.path-domain, binding.value-range)")
    y.add_argument("--json", action="store_true", help="print the report as JSON: findings with counts, and each graph's ontology and snapshot")
    y.set_defaults(func=cmd_kg_check)

    x = sp.add_parser("diff", help="compare two versions of an OntologyPackage and say which SemVer increment the changes call for (needs the rdf extra)")
    x.add_argument("old", help="the earlier version: package directory or .owp.zip")
    x.add_argument("new", help="the later version: package directory or .owp.zip")
    x.add_argument("--json", action="store_true")
    x.set_defaults(func=cmd_diff)

    x = sp.add_parser("interop", help="mappings to neighbouring standards (docs/interop/)")
    isp = x.add_subparsers(dest="interop_command", required=True)
    y = isp.add_parser("mcp", help="print what a Model Context Protocol server for this World exposes: resources, resource templates, tools")
    y.add_argument("world", help="World package directory")
    y.set_defaults(func=cmd_interop_mcp)

    x = sp.add_parser("mcp", help="serve one package read-only to agents as a Model Context Protocol server on stdio (docs/interop/MCP.md)")
    x.add_argument("package", nargs="?", default=".", help="package directory or .owp.zip archive")
    x.add_argument("--observations", action="append", default=[], help="ObservationSet file (YAML or JSON) the EWS resources compile from "
                   "(repeatable; sets are merged)")
    x.add_argument("--source", action="append", default=[], help="package source for its dependencies, so term_lookup also searches "
                   "the ontologies it depends on (repeatable; ONTLE_PATH is also read)")
    x.set_defaults(func=cmd_mcp)

    x = sp.add_parser("export", help="export an OntologyPackage's owp-yaml schema as RDF")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--format", choices=["turtle", "jsonld"], default="turtle")
    x.set_defaults(func=cmd_export)

    x = sp.add_parser("pack", help="build a deterministic .owp.zip archive")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--output", help="archive file, or a directory for the default name <namespace>-<name>-<version>.owp.zip (default: <package>/dist/)")
    x.add_argument("--vendor", action="store_true", help="include pinned https external content in the archive (spec section 7)")
    x.add_argument("--list", action="store_true", help="print the files the archive would contain, without writing it")
    x.set_defaults(func=cmd_pack)

    x = sp.add_parser("verify", help="verify hashes inside an .owp.zip archive")
    x.add_argument("archive")
    x.add_argument("--signature", action="store_true", help="also verify <archive>.sigstore.json with cosign")
    x.add_argument("--key", help="public key for a key-based signature")
    x.add_argument("--identity", help="certificate identity for a keyless signature")
    x.add_argument("--issuer", help="OIDC issuer for a keyless signature")
    x.set_defaults(func=cmd_verify)

    x = sp.add_parser("fetch", help="download and verify the external content a package references")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--into", required=True)
    x.set_defaults(func=cmd_fetch)

    x = sp.add_parser("lock", help="pin unpinned https external references in owp.yaml by their digest")
    x.add_argument("path", nargs="?", default=".")
    x.set_defaults(func=cmd_lock)

    x = sp.add_parser("push", help="push a verified .owp.zip as an OCI artifact (needs oras)")
    x.add_argument("archive")
    x.add_argument("reference", help="registry reference, or oci-layout:<dir>:<tag>")
    x.set_defaults(func=cmd_push)

    x = sp.add_parser("sign", help="sign an .owp.zip with cosign; writes <archive>.sigstore.json")
    x.add_argument("archive")
    x.add_argument("--key", help="private key; keyless (OIDC) when omitted")
    x.set_defaults(func=cmd_sign)

    x = sp.add_parser("index", help="static package index")
    isp = x.add_subparsers(dest="index_command", required=True)
    y = isp.add_parser("build", help="write a PackageIndex for .owp.zip archives")
    y.add_argument("archives", nargs="+")
    y.add_argument("--base", help="directory archive paths are written relative to")
    y.add_argument("--base-url", help="URL prefix for archive locations")
    y.add_argument("--terms", action="store_true", help="add a term index: which packages define and use each ontology term, and their mapping sets")
    y.add_argument("--output")
    y.set_defaults(func=cmd_index_build)

    x = sp.add_parser("evidence", help="evidence published outside a package")
    esp2 = x.add_subparsers(dest="evidence_command", required=True)
    y = esp2.add_parser("check", help="check detached CompatibilityEvidence against a package archive")
    y.add_argument("evidence")
    y.add_argument("--package", required=True, help=".owp.zip archive of the subject")
    y.set_defaults(func=cmd_evidence_check)
    y = esp2.add_parser("attach", help="attach detached evidence to a pushed package as an OCI referrer (needs oras)")
    y.add_argument("evidence")
    y.add_argument("--reference", required=True)
    y.set_defaults(func=cmd_evidence_attach)

    x = sp.add_parser("catalog", help="export catalog metadata (informative)")
    x.add_argument("path", nargs="?", default=".")
    x.add_argument("--format", required=True, choices=["dcat", "croissant", "hf-card"])
    x.set_defaults(func=cmd_catalog)

    x = sp.add_parser("new", help="write a skeleton asset file (found by its apiVersion and kind; owp.yaml is unchanged)")
    x.add_argument("kind", help="asset kind, for example WorldViewProfile, StateCompilerProfile, or <extension>:<Kind>")
    x.add_argument("path", help="package-relative file, for example views/barista.yaml")
    x.add_argument("--package", default=".", help="package directory (default: current directory)")
    x.add_argument("--specializes", help="WorldViewProfile: path of the local View this View specializes (experimental)")
    x.add_argument("--composes", action="append", help="WorldViewProfile: path of a local View this View composes (repeatable; experimental)")
    x.set_defaults(func=cmd_new)

    x = sp.add_parser("add", help="declare a publisher extension in spec.dependencies")
    x.add_argument("what", choices=["extension"])
    x.add_argument("name", help="the defining package <namespace>/<name>@<version>")
    x.add_argument("--path", default=".")
    x.add_argument("--as", dest="as_name", help="local name (default: package name without a trailing -extension)")
    x.add_argument("--must-understand", action="store_true", help="runtimes that do not implement it must not run the package")
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
