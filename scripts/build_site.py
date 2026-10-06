#!/usr/bin/env python3
"""Build the static site that https://w3id.org/owp/ redirects to (GitHub Pages; .github/workflows/pages.yml).

    python scripts/build_site.py _site      # needs the rdf extra (rdflib) and `markdown`

Layout (the w3id rules in internal docs map onto these paths):
    vocab/owp/ns.ttl, ns.jsonld, index.html      the vocabulary (https://w3id.org/owp/ns)
    vocab/owp/releases/<release>/ns.ttl          versioned vocabulary (owl:versionIRI)
    vocab/owp/value-sets.ttl, shapes.ttl          value sets as SKOS (https://w3id.org/owp/vs/<set>), SHACL shapes for EWS RDF
    alignments/owp-align-*/                      informative alignments
    spec/<apiVersion>/                           the specification at this commit, as HTML
    pkg/index.html                               what a package IRI identifies; links to its catalog page when there is one
    catalog/                                     the example packages: pages, archives, and a PackageIndex (site_catalog.py)
    playground/                                  check a package in the browser (site_playground.py; needs the TypeScript bundle)
"""
from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path

import markdown
import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from site_catalog import build_catalog
from site_playground import build_playground

ROOT = Path(__file__).resolve().parent.parent
OWP = rdflib.Namespace("https://w3id.org/owp/ns#")
API_VERSION = "v1alpha1"
REPO = "https://github.com/ontle-world/open-world-package"

STYLE = """
:root{--bg:#fbfbfc;--fg:#1b2230;--muted:#5b6573;--line:#dde2e8;--accent:#245f7a;--code:#eef2f5}
@media (prefers-color-scheme: dark){:root{--bg:#13171d;--fg:#e3e7ec;--muted:#9aa3ae;--line:#2b333d;--accent:#7ab8d6;--code:#1c232c}}
body{background:var(--bg);color:var(--fg);font:15px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}
main{max-width:920px;margin:0 auto;padding:32px 20px 64px}
a{color:var(--accent)} h1,h2,h3{line-height:1.25} h1{font-size:28px} h2{margin-top:2em;font-size:20px}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;background:var(--code);border-radius:4px}
code{padding:1px 4px} pre{padding:12px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600} .muted{color:var(--muted)}
"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main>{body}"
            f'<p class="muted">Open World Package · <a href="{REPO}">{REPO}</a></p></main></body></html>\n')


def short(term: rdflib.term.Node, graph: rdflib.Graph) -> str:
    try:
        return graph.namespace_manager.normalizeUri(term)
    except Exception:
        return str(term)


def vocabulary_html(graph: rdflib.Graph) -> str:
    def rows(kinds):
        out = []
        for s in sorted({s for k in kinds for s in graph.subjects(RDF.type, k) if str(s).startswith(str(OWP))}, key=str):
            name = str(s)[len(str(OWP)):]
            comment = graph.value(s, RDFS.comment) or graph.value(s, RDFS.label) or ""
            extra = []
            for p, label in ((RDFS.subClassOf, "subclass of"), (RDFS.domain, "domain"), (RDFS.range, "range"), (RDFS.subPropertyOf, "subproperty of")):
                vals = [short(o, graph) for o in graph.objects(s, p) if isinstance(o, rdflib.URIRef)]
                if vals:
                    extra.append(f"{label} {', '.join(html.escape(v) for v in vals)}")
            out.append(f'<tr id="{html.escape(name)}"><td><code>owp:{html.escape(name)}</code></td><td>{html.escape(str(comment))}'
                       f'{"<br><span class=muted>" + "; ".join(extra) + "</span>" if extra else ""}</td></tr>')
        return "\n".join(out)
    version = graph.value(rdflib.URIRef("https://w3id.org/owp/ns"), OWL.versionIRI)
    body = f"""<h1>OWP vocabulary</h1>
<p>Namespace <code>https://w3id.org/owp/ns#</code> · version <code>{html.escape(str(version))}</code> · OWL 2 DL · CC BY 4.0.
Download: <a href="ns.ttl">Turtle</a>, <a href="ns.jsonld">JSON-LD</a>. Also: <a href="value-sets.ttl">value sets as SKOS</a>, <a href="shapes.ttl">SHACL shapes for EWS RDF</a>.</p>
<p>Terms for OWP's own concepts. Provenance, time, licensing and catalogs reuse PROV-O, XSD, DCTERMS and DCAT. Informative alignments: <a href="../../alignments/">PROV-O, BFO 2020 + IAO, DOLCE+DnS Ultralite</a>.</p>
<h2>Classes</h2><table><tr><th>Term</th><th>Meaning</th></tr>{rows([OWL.Class])}</table>
<h2>Properties</h2><table><tr><th>Term</th><th>Meaning</th></tr>{rows([OWL.ObjectProperty, OWL.DatatypeProperty])}</table>
<h2>Individuals</h2><table><tr><th>Term</th><th>Meaning</th></tr>{rows([OWP.Resolution])}</table>"""
    return page("OWP vocabulary", body)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_site").resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / ".nojekyll").write_text("")

    # vocabulary
    vocab = out / "vocab" / "owp"
    vocab.mkdir(parents=True)
    ttl = (ROOT / "vocab" / "owp" / "ns.ttl").read_text(encoding="utf-8")
    graph = rdflib.Graph()
    graph.parse(data=ttl, format="turtle")
    (vocab / "ns.ttl").write_text(ttl, encoding="utf-8")
    for extra in ("value-sets.ttl", "shapes.ttl"):
        shutil.copy2(ROOT / "vocab" / "owp" / extra, vocab / extra)
    (vocab / "ns.jsonld").write_text(graph.serialize(format="json-ld", indent=2), encoding="utf-8")
    (vocab / "index.html").write_text(vocabulary_html(graph), encoding="utf-8")
    release = str(graph.value(rdflib.URIRef("https://w3id.org/owp/ns"), OWL.versionIRI)).rsplit("/", 1)[-1]
    (vocab / "releases" / release).mkdir(parents=True)
    (vocab / "releases" / release / "ns.ttl").write_text(ttl, encoding="utf-8")

    # alignments
    links = []
    for pkg in sorted((ROOT / "alignments").glob("owp-align-*")):
        target = out / "alignments" / pkg.name
        target.mkdir(parents=True)
        for f in ("align.ttl", "mappings.sssom.tsv", "owp.yaml", "ONTOLOGY.md"):
            shutil.copy2(pkg / f, target / f)
        shutil.copytree(pkg / "semantics", target / "semantics")  # the term index owp.yaml points to
        title = (pkg / "ONTOLOGY.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
        links.append(f'<li><a href="{pkg.name}/align.ttl">{html.escape(title)}</a> · <a href="{pkg.name}/mappings.sssom.tsv">SSSOM</a> · <a href="{pkg.name}/owp.yaml">package</a></li>')
    (out / "alignments" / "index.html").write_text(page("OWP alignments", "<h1>OWP alignments</h1><p>Informative: OWP conformance never depends on them. "
                                                        "Checked with HermiT by <code>scripts/check_alignments.sh</code>.</p><ul>" + "".join(links) + "</ul>"), encoding="utf-8")

    # specification snapshot
    spec_dir = out / "spec" / API_VERSION
    spec_dir.mkdir(parents=True)
    items = []
    for md in sorted((ROOT / "spec").glob("*.md")):
        text = md.read_text(encoding="utf-8").replace(".md)", ".html)")
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])
        (spec_dir / f"{md.stem}.html").write_text(page(md.stem.replace("_", " "), body), encoding="utf-8")
        items.append(f'<li><a href="{md.stem}.html">{md.stem}</a></li>')
    (spec_dir / "index.html").write_text(page(f"OWP specification {API_VERSION}", f"<h1>Open World Package specification, {API_VERSION}</h1>"
                                              "<p>Public alpha. Start with OWP_SPEC; it has the document map.</p><ul>" + "".join(items) + "</ul>"), encoding="utf-8")

    # package identifiers
    (out / "pkg").mkdir()
    (out / "pkg" / "index.html").write_text(page("OWP package identifiers", """<h1>OWP package identifiers</h1>
<p id="id" class="muted"></p>
<p><code>https://w3id.org/owp/pkg/{namespace}/{name}/{version}</code> identifies the OWP package <code>{namespace}/{name}@{version}</code>;
<code>…#{path}</code> identifies one of its assets. The identifier names the package, not a download location: get the archive from a registry, an index, or its publisher, and verify it with <code>ontle verify</code>.</p>
<script>
const q = new URLSearchParams(location.search);
if (q.get("ns") && q.get("name") && q.get("version")) {
  const id = q.get("ns") + "/" + q.get("name") + "@" + q.get("version");
  const el = document.getElementById("id");
  el.textContent = "This identifier names the package " + id + ".";
  fetch("../catalog/index.json").then((r) => r.json()).then((index) => {
    if (!index.packages.some((p) => p.identity === id)) return;
    const a = document.createElement("a");
    a.href = "../catalog/" + [q.get("ns"), q.get("name"), q.get("version")].map(encodeURIComponent).join("/") + "/";
    a.textContent = "Open it in the package catalog";
    el.append(" ", a, ".");
  }).catch(() => {});
}
</script>"""), encoding="utf-8")

    # package catalog (registry step P0)
    build_catalog(out, page)
    playground = build_playground(out, page)
    if not playground:
        print("playground skipped: run `npm run bundle` in implementations/typescript first", file=sys.stderr)

    # landing
    (out / "index.html").write_text(page("Open World Package", f"""<h1>Open World Package</h1>
<ul><li><a href="vocab/owp/">Vocabulary</a> (<code>https://w3id.org/owp/ns#</code>)</li>
<li><a href="alignments/">Alignments</a></li><li><a href="spec/{API_VERSION}/">Specification {API_VERSION}</a></li>
<li><a href="catalog/">Package catalog</a>: the example packages, with reports and archives</li>
<li><a href="playground/">Playground</a>: check a package in your browser, without uploading it</li>
<li><a href="pkg/">Package identifiers</a></li></ul>"""), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
