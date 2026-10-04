"""`ontle mcp`: a read-only Model Context Protocol server for one package, over stdio (tooling, informative).

It serves what docs/interop/MCP.md maps: the manifest, card, World Views, and State Compilers as resources, and the EWS
of a State Compiler as a resource template. Its tools read the package: they describe the World, show a View, look up
terms, compile an EWS from given observations, and give the PackageReport. It does not expose the World's actions:
a server that runs actions is a runtime, outside this repository.

Transport: newline-delimited JSON-RPC 2.0 on stdin and stdout (MCP stdio transport); logs go to stderr.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from . import ontology as ontology_module
from .core import OWPError, load_manifest, local_assets
from .ews import compile_ews
from .experimental import resolve_view
from .interop import ews_uri, mcp_description
from .rdfexport import asset_iri, package_iri
from .report import DEFAULT_CARDS, CARD_SPEC_KEY, package_report
from .yamlio import dump_yaml, load_yaml

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOLS = [
    {"name": "world_describe", "title": "Describe the package",
     "description": "Identity, kind, title, description, domains, the World's definition and boundary, its Views and State Compilers, and the card text.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "view_get", "title": "Show a World View",
     "description": "A World View's purpose, projection, and conditioning, with specializes applied. Without path: the World's default View.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "View path in the package, e.g. views/default.yaml"}},
                     "additionalProperties": False}},
    {"name": "term_lookup", "title": "Look up a term",
     "description": "Find a name, CURIE, or IRI in the package's SemanticBinding (World names, EWS fields, observation types, actions) "
                    "or, for an OntologyPackage, its terms. Matches case-insensitively on substrings.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"name": "ews_compile", "title": "Compile an Effective World State",
     "description": "Run a State Compiler over observations at asOf and return the EWS (unresolved and missing fields included). "
                    "Give the observations as an ObservationSet document, or the path of one in the package.",
     "inputSchema": {"type": "object", "properties": {
         "asOf": {"type": "string", "description": "UTC, YYYY-MM-DDTHH:MM:SSZ"},
         "compiler": {"type": "string", "description": "StateCompilerProfile path; default: the World's defaultStateCompiler"},
         "observations": {"type": "object", "description": "ObservationSet document"},
         "observationsPath": {"type": "string", "description": "ObservationSet file in the package, e.g. examples/observations.yaml"}},
         "required": ["asOf"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "package_report", "title": "Package report",
     "description": "The PackageReport: verdict, conformance profile, asset counts, binding coverage, external references, evidence, card hints.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]
for _tool in TOOLS:
    _tool.setdefault("annotations", {"readOnlyHint": True, "openWorldHint": False})


class ToolError(Exception):
    """A tool call that failed: reported to the client as a tool result with isError, not as a protocol error."""


class PackageServer:
    def __init__(self, root: Path, report_path: str | Path, observations: list[str] | None = None):
        self.root, self.manifest = load_manifest(root)
        self.report_path = report_path  # the directory or archive the user named, so the report carries archive integrity
        self.spec = self.manifest.get("spec") if isinstance(self.manifest.get("spec"), dict) else {}
        md = self.manifest.get("metadata") if isinstance(self.manifest.get("metadata"), dict) else {}
        self.md = md
        self.identity = f"{md.get('namespace')}/{md.get('name')}@{md.get('version')}"
        self.kinds, self.docs = local_assets(self.root, self.spec)
        self.observations = observations or []

    # --- resources -------------------------------------------------------------------------------

    def card_path(self) -> str | None:
        kind = self.manifest.get("kind")
        rel = (self.spec.get(CARD_SPEC_KEY.get(kind, "")) or {}).get("description") if isinstance(self.spec.get(CARD_SPEC_KEY.get(kind, "")), dict) else None
        rel = rel if isinstance(rel, str) and rel.endswith(".md") else DEFAULT_CARDS.get(kind)
        return rel if rel and ontology_module.inside_package(self.root, rel) and (self.root / rel).is_file() else None

    def resources(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if self.manifest.get("kind") == "WorldPackage":
            described = mcp_description(self.root)
            resources, templates = described["resources"], described["resourceTemplates"]
        else:
            resources = [{"uri": package_iri(self.identity), "name": "manifest", "title": self.md.get("title") or self.identity,
                          "mimeType": "application/yaml", "description": "The package manifest."}]
            templates = []
        card = self.card_path()
        if card:
            resources.append({"uri": asset_iri(f"{self.identity}#{card}"), "name": "card", "mimeType": "text/markdown",
                              "description": "The package card."})
        return resources, templates

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri.startswith("owp-ews://"):
            parts = urlsplit(uri)
            as_of = (parse_qs(parts.query).get("asOf") or [None])[0]
            for rel, kind in self.kinds.items():
                if kind == "StateCompilerProfile" and ews_uri(self.identity, rel) == uri.split("?", 1)[0]:
                    if not as_of:
                        raise ToolError("the EWS resource needs ?asOf=YYYY-MM-DDTHH:MM:SSZ")
                    if not self.observations:
                        raise ToolError("no observations: start the server with ontle mcp <package> --observations <ObservationSet>")
                    ews = compile_ews(self.root, rel, self._merged([load_yaml(Path(p).read_text(encoding="utf-8")) for p in self.observations]), as_of)
                    return {"uri": uri, "mimeType": "application/yaml", "text": dump_yaml(ews)}
            raise ToolError(f"no State Compiler for {uri}")
        base = package_iri(self.identity)
        if uri == base:
            return {"uri": uri, "mimeType": "application/yaml", "text": (self.root / "owp.yaml").read_text(encoding="utf-8")}
        if uri.startswith(base + "#"):
            rel = unquote(uri[len(base) + 1:])
            if (rel in self.kinds or rel == self.card_path()) and ontology_module.inside_package(self.root, rel):
                mime = "text/markdown" if rel.endswith(".md") else "application/yaml"
                return {"uri": uri, "mimeType": mime, "text": (self.root / rel).read_text(encoding="utf-8")}
        raise ToolError(f"unknown resource {uri}")

    # --- tools -------------------------------------------------------------------------------

    def call(self, name: str, args: dict[str, Any]) -> Any:
        if name == "world_describe":
            return self.describe()
        if name == "view_get":
            return self.view(args.get("path"))
        if name == "term_lookup":
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ToolError("query must be a non-empty string")
            return self.lookup(query.strip())
        if name == "ews_compile":
            return self.compile(args)
        if name == "package_report":
            return package_report(self.report_path)
        raise ToolError(f"unknown tool {name}")

    def describe(self) -> dict[str, Any]:
        world = self.spec.get("world") if isinstance(self.spec.get("world"), dict) else {}
        out: dict[str, Any] = {"identity": self.identity, "kind": self.manifest.get("kind"),
                               **{k: self.md[k] for k in ("title", "description", "license") if isinstance(self.md.get(k), str)},
                               "domains": self.spec.get("domains") or []}
        if world:
            out["world"] = {k: world[k] for k in ("definition", "boundary", "defaultView", "defaultStateCompiler", "semanticBinding") if k in world}
        out["views"] = sorted(rel for rel, k in self.kinds.items() if k == "WorldViewProfile")
        out["stateCompilers"] = sorted(rel for rel, k in self.kinds.items() if k == "StateCompilerProfile")
        grounding = (self.spec.get("worldModel") or {}).get("semanticGrounding") if isinstance(self.spec.get("worldModel"), dict) else None
        if grounding:
            out["semanticGrounding"] = grounding
        card = self.card_path()
        if card:
            out["card"] = (self.root / card).read_text(encoding="utf-8")
        return out

    def view(self, rel: Any) -> dict[str, Any]:
        if rel is None:
            rel = (self.spec.get("world") or {}).get("defaultView") if isinstance(self.spec.get("world"), dict) else None
            if not isinstance(rel, str):
                raise ToolError("the package declares no spec.world.defaultView; pass path")
        if self.kinds.get(rel) != "WorldViewProfile":
            views = sorted(r for r, k in self.kinds.items() if k == "WorldViewProfile")
            raise ToolError(f"{rel!r} is not a World View in this package; Views: {', '.join(views) or 'none'}")
        return {"path": rel, "uri": asset_iri(f"{self.identity}#{rel}"), "spec": resolve_view(rel, self.docs, self.kinds)}

    def lookup(self, query: str) -> dict[str, Any]:
        q = query.lower()
        matches: list[dict[str, Any]] = []
        binding_rel = (self.spec.get("world") or {}).get("semanticBinding") if isinstance(self.spec.get("world"), dict) else None
        bspec = ((self.docs.get(binding_rel) or {}).get("spec") or {}) if isinstance(binding_rel, str) else {}
        for section in ("terms", "fields", "observationTypes", "actions"):
            entries = bspec.get(section)
            for key, value in (entries.items() if isinstance(entries, dict) else []):
                if q in str(key).lower() or q in json.dumps(value, ensure_ascii=False).lower():
                    matches.append({"in": f"{binding_rel}: spec.{section}", "name": key, "boundTo": value})
        if self.manifest.get("kind") == "OntologyPackage":
            prefixes, iris = ontology_module.terms(self.root, self.manifest)
            for iri in sorted(iris):
                curie = next((f"{p}:{iri[len(ns):]}" for p, ns in prefixes.items() if iri.startswith(ns)), None)
                if q in iri.lower() or (curie and q in curie.lower()):
                    matches.append({"in": "ontology terms", "iri": iri, **({"curie": curie} if curie else {})})
        return {"query": query, "matches": matches}

    def compile(self, args: dict[str, Any]) -> dict[str, Any]:
        as_of = args.get("asOf")
        compiler = args.get("compiler")
        if compiler is None:
            compiler = (self.spec.get("world") or {}).get("defaultStateCompiler") if isinstance(self.spec.get("world"), dict) else None
            if not isinstance(compiler, str):
                raise ToolError("the World declares no spec.world.defaultStateCompiler; pass compiler")
        if "observations" in args and "observationsPath" in args:
            raise ToolError("give observations or observationsPath, not both")
        if "observations" in args:
            observations = args["observations"]
        elif "observationsPath" in args:
            rel = args["observationsPath"]
            if not ontology_module.inside_package(self.root, rel) or not (self.root / rel).is_file():
                raise ToolError(f"observationsPath {rel!r} is not a file in the package")
            observations = load_yaml((self.root / rel).read_text(encoding="utf-8"))
        elif self.observations:
            observations = self._merged([load_yaml(Path(p).read_text(encoding="utf-8")) for p in self.observations])
        else:
            raise ToolError("give observations (an ObservationSet document) or observationsPath")
        return compile_ews(self.root, compiler, observations, as_of)

    @staticmethod
    def _merged(docs: list[Any]) -> Any:
        if len(docs) == 1:
            return docs[0]
        merged: list[Any] = []
        for doc in docs:
            listed = ((doc or {}).get("spec") or {}).get("observations") if isinstance(doc, dict) else None
            merged += listed if isinstance(listed, list) else []
        return {"apiVersion": "openworld/v1alpha1", "kind": "ObservationSet", "spec": {"observations": merged}}

    # --- JSON-RPC ------------------------------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        mid = message.get("id")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if mid is None:  # a notification (notifications/initialized, cancellations): no response
            return None
        try:
            result = self._dispatch(method, params)
        except _RpcError as exc:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": exc.code, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: Any, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {"protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "ontle", "title": self.md.get("title") or self.identity, "version": __version__},
                    "instructions": f"Read-only access to the Open World Package {self.identity}. Start with world_describe."}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            if name not in {t["name"] for t in TOOLS}:
                raise _RpcError(-32602, f"unknown tool {name}")
            try:
                value = self.call(name, args)
            except (ToolError, OWPError) as exc:
                return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(value, indent=2, ensure_ascii=False)}],
                    "structuredContent": value, "isError": False}
        if method == "resources/list":
            return {"resources": self.resources()[0]}
        if method == "resources/templates/list":
            return {"resourceTemplates": self.resources()[1]}
        if method == "resources/read":
            uri = params.get("uri")
            if not isinstance(uri, str):
                raise _RpcError(-32602, "params.uri must be a string")
            try:
                return {"contents": [self.read_resource(uri)]}
            except (ToolError, OWPError) as exc:
                raise _RpcError(-32002, str(exc)) from exc
        raise _RpcError(-32601, f"method not found: {method}")


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def serve(server: PackageServer, stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: dict[str, Any] | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            if isinstance(message, dict):
                response = server.handle(message)
            else:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def run(package: str, observations: list[str] | None = None) -> int:
    from .report import opened_package
    with opened_package(package) as (root, _):
        server = PackageServer(root, package, observations)
        print(f"ontle mcp: serving {server.identity} on stdio", file=sys.stderr)
        serve(server, sys.stdin, sys.stdout)
    return 0
