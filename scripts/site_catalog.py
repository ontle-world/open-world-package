"""The package catalog on the project site (registry step P0): a static page per example package, from its report.

    catalog/index.html                         every package, with a filter
    catalog/index.json                         a PackageIndex (spec section 11.1): ontle --source index:<url>
    catalog/archives/<ns>-<name>-<version>.owp.zip
    catalog/<ns>/<name>/<version>/index.html   card, report, assets, dependencies and dependents, archive

Everything on a page comes from the package or from `ontle inspect --report`; nothing is written by hand.
build_site.py calls build_catalog().
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Callable

import markdown

from ontle.core import deterministic_pack, load_manifest, local_assets
from ontle.distribution import build_index
from ontle.report import package_report

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/ontle-world/open-world-package"
SITE = "https://ontle-world.github.io/open-world-package"
KIND_LABEL = {"WorldPackage": "World", "WorldModelPackage": "World Model", "OntologyPackage": "Ontology"}

CATALOG_STYLE = """
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin:16px 0}
.card{border:1px solid var(--line);border-radius:8px;padding:12px 14px;text-decoration:none;color:inherit;display:block}
.card:hover{border-color:var(--accent)} .card h3{margin:2px 0 4px;font-size:16px} .card p{margin:4px 0;font-size:14px}
.badge{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 8px;margin:2px 4px 2px 0;color:var(--muted)}
.badge.ok{color:var(--accent);border-color:var(--accent)} .kind{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:28px} @media (max-width:760px){.cols{grid-template-columns:1fr}}
aside pre{white-space:pre-wrap;word-break:break-all}
aside h3{font-size:14px;margin:18px 0 6px;color:var(--muted)} aside p,aside li{font-size:14px;margin:2px 0} aside ul{padding-left:18px;margin:4px 0}
input[type=search]{width:100%;max-width:420px;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit}
"""


def _identity_parts(identity: str) -> tuple[str, str, str]:
    name_part, _, version = identity.rpartition("@")
    namespace, _, name = name_part.partition("/")
    return namespace, name, version


def _dependencies(manifest: dict[str, Any]) -> list[str]:
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
    out = []
    for d in spec.get("dependencies") or []:
        ref = d.get("ref") if isinstance(d, dict) else d
        if isinstance(ref, str):
            out.append(ref)
    return out


def scale(report: dict[str, Any], observations: int) -> dict[str, str]:
    """How big an example is, from its report: the package's breadth, and its sample data.

    breadth: an OntologyPackage by its terms; any other package by its assets (minimal up to 5, focused up to 19,
    full from 20). data: how many sample observations it ships, and whether it binds real external artifacts.
    """
    if report.get("ontology"):
        breadth = f"{report['ontology']['terms']} terms"
    else:
        n = report["assets"]["total"]
        breadth = "minimal" if n <= 5 else "focused" if n < 20 else "full"
    refs = report["externalRefs"]["total"]
    data = f"{observations} sample observation{'' if observations == 1 else 's'}" if observations else "no sample data"
    if refs:
        data += f" · binds {refs} real artifact{'' if refs == 1 else 's'}"
    return {"breadth": breadth, "data": data}


def observation_count(root: Path, kinds: dict[str, str], docs: dict[str, Any]) -> int:
    """Observations in the ObservationSets a package ships as PackageExample files."""
    total = 0
    for rel, kind in kinds.items():
        doc = docs.get(rel)
        if kind == "PackageExample" and isinstance(doc, dict) and doc.get("kind") == "ObservationSet":
            listed = (doc.get("spec") or {}).get("observations")
            total += len(listed) if isinstance(listed, list) else 0
    return total


def _badges(report: dict[str, Any]) -> list[tuple[str, bool]]:
    badges: list[tuple[str, bool]] = [("valid" if report["valid"] else "invalid", report["valid"])]
    profile = (report.get("profile") or {}).get("satisfied")
    if profile:
        badges.append((profile, True))
    refs = report["externalRefs"]
    if refs["total"]:
        badges.append((f"refs pinned {refs['pinned']}/{refs['total']}", refs["pinned"] == refs["total"]))
    if report["evidence"]["included"]:
        badges.append((f"evidence {report['evidence']['included']}", True))
    return badges


def _badge_html(badges: list[tuple[str, bool]]) -> str:
    return "".join(f'<span class="badge{" ok" if ok else ""}">{html.escape(text)}</span>' for text, ok in badges)


def _card_html(text: str, repo_dir: str) -> str:
    """The card without its title (the page has it), with links relative to the package pointed at the repository."""
    text = re.sub(r"\A\s*# [^\n]*\n", "", text)
    text = re.sub(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)", lambda m: f"]({REPO}/blob/main/{repo_dir}/{m.group(1)})", text)
    return markdown.markdown(text, extensions=["tables", "fenced_code"])


def build_catalog(out: Path, page: Callable[[str, str], str], packages: list[Path] | None = None) -> list[dict[str, Any]]:
    """Write catalog/ under the site root `out`; returns one entry per package (identity, report, page path)."""
    catalog = out / "catalog"
    archives = catalog / "archives"
    archives.mkdir(parents=True)
    dirs = packages if packages is not None else sorted(m.parent for m in ROOT.glob("examples/*/*/owp.yaml"))
    entries: list[dict[str, Any]] = []
    for d in dirs:
        root, manifest = load_manifest(d)
        md = manifest.get("metadata") or {}
        archive = deterministic_pack(root, archives / f"{md['namespace']}-{md['name']}-{md['version']}.owp.zip")
        report = package_report(archive)
        kinds, docs = local_assets(root, manifest.get("spec") or {})
        entries.append({"dir": root, "manifest": manifest, "report": report, "archive": archive, "assets": dict(sorted(kinds.items())),
                        "dependencies": _dependencies(manifest), "scale": scale(report, observation_count(root, kinds, docs))})
    index = build_index([e["archive"] for e in entries], base=catalog, terms=True)
    (catalog / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_identity = {e["report"]["identity"]: e for e in entries}
    for e in entries:
        e["usedBy"] = sorted(other["report"]["identity"] for other in entries if e["report"]["identity"] in other["dependencies"])
    for e in entries:
        _package_page(e, catalog, by_identity, page)
    _index_page(entries, catalog, page)
    return [{"identity": e["report"]["identity"], "report": e["report"], "page": e["page"], "scale": e["scale"]} for e in entries]


def _package_page(e: dict[str, Any], catalog: Path, by_identity: dict[str, Any], page: Callable[[str, str], str]) -> None:
    report = e["report"]
    identity = report["identity"]
    ns, name, version = _identity_parts(identity)
    target = catalog / ns / name / version
    target.mkdir(parents=True)
    e["page"] = f"catalog/{ns}/{name}/{version}/"
    up = "../../../"  # from the package page to catalog/
    repo_dir = e["dir"].relative_to(ROOT).as_posix()
    meta = report["metadata"]
    card_path = (report.get("card") or {}).get("path")
    card = _card_html((e["dir"] / card_path).read_text(encoding="utf-8"), repo_dir) if card_path else "<p class=muted>No card.</p>"

    def link(ref: str) -> str:
        other = by_identity.get(ref)
        if other is None:
            return f"<code>{html.escape(ref)}</code>"
        o_ns, o_name, o_version = _identity_parts(ref)
        return f'<a href="{up}{o_ns}/{o_name}/{o_version}/">{html.escape(ref)}</a>'

    deps = "".join(f"<li>{link(d)}</li>" for d in e["dependencies"]) or "<li class=muted>none</li>"
    used = "".join(f"<li>{link(u)}</li>" for u in e["usedBy"]) or "<li class=muted>none in this catalog</li>"
    stats = []
    if "state" in report:
        s = report["state"]
        stats.append(f"<p>EWS fields with a binding: {s['withBinding']}/{s['fields']} ({s['stateCompilers']} State Compiler{'s' if s['stateCompilers'] != 1 else ''})</p>")
    if "semanticCoverage" in report:
        c = report["semanticCoverage"]
        stats.append(f"<p>Fields bound to ontology terms: {c['boundToTerms']}/{c['fields']}</p>")
    if "ontology" in report:
        stats.append(f"<p>Terms: {report['ontology']['terms']}</p>")
    refs = report["externalRefs"]
    stats.append(f"<p>External references pinned: {refs['pinned']}/{refs['total']}</p>")
    if report["standardBindings"]["standards"]:
        stats.append(f"<p>Standards: {html.escape(', '.join(report['standardBindings']['standards']))}</p>")
    if report["evidence"]["included"]:
        stats.append(f"<p>Evidence: {report['evidence']['included']} ({html.escape(', '.join(report['evidence']['statuses']))})</p>")
    integrity = report["integrity"]
    archive_name = e["archive"].name
    assets = "".join(f"<tr><td><code>{html.escape(p)}</code></td><td>{html.escape(k)}</td></tr>" for p, k in e["assets"].items())
    use = (f"ontle validate --resolve --source index:{SITE}/catalog/index.json &lt;your-package&gt;\n"
           f"# in your owp.yaml:\nspec:\n  dependencies:\n  - {html.escape(identity)}")
    body = f"""<p class="kind"><a href="{up}">Catalog</a> · {html.escape(KIND_LABEL.get(report['packageKind'], str(report['packageKind'])))}</p>
<h1>{html.escape(meta.get('title') or name)}</h1>
<p><code>{html.escape(identity)}</code> {_badge_html([(e["scale"]["breadth"], False)] + _badges(report))}</p>
<p class="muted">Size: {html.escape(e["scale"]["breadth"])} · {html.escape(e["scale"]["data"])}</p>
<p>{html.escape(meta.get('description', ''))}</p>
<div class="cols"><div>{card}
<h2>Assets</h2><table><tr><th>Path</th><th>Kind</th></tr>{assets}</table></div>
<aside>
<h3>Use this package</h3><pre>{use}</pre>
<h3>Archive</h3><p><a href="{up}archives/{archive_name}">{html.escape(archive_name)}</a></p>
<p class="muted">{integrity['size']:,} bytes · {integrity['files']} files<br><code>{integrity['digest'][:19]}…</code></p>
<p class="muted">Check it with <code>ontle verify {html.escape(archive_name)}</code>, or <a href="{up}../playground/?archive=../catalog/archives/{archive_name}">in the Playground</a>.</p>
<h3>Report</h3>{''.join(stats)}
<p class="muted">Checked by {html.escape(report['validator']['implementation'])} {html.escape(report['validator']['version'])}. <a href="report.json">report.json</a></p>
<h3>Depends on</h3><ul>{deps}</ul>
<h3>Used by</h3><ul>{used}</ul>
<h3>License</h3><p>{html.escape(meta.get('license', 'not declared'))}</p>
<h3>Source</h3><p><a href="{REPO}/tree/main/{repo_dir}">{html.escape(repo_dir)}</a></p>
</aside></div>"""
    (target / "index.html").write_text(page(f"{identity} · OWP catalog", f"<style>{CATALOG_STYLE}</style>{body}"), encoding="utf-8")
    (target / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _index_page(entries: list[dict[str, Any]], catalog: Path, page: Callable[[str, str], str]) -> None:
    cards = []
    for e in sorted(entries, key=lambda x: (list(KIND_LABEL).index(x["report"]["packageKind"]) if x["report"]["packageKind"] in KIND_LABEL else 9, x["report"]["identity"])):
        r = e["report"]
        meta = r["metadata"]
        stats = [f"{r['assets']['total']} asset{'' if r['assets']['total'] == 1 else 's'}", e["scale"]["data"]]
        if r["domains"]:
            stats.append(", ".join(r["domains"]))
        if r["standardBindings"]["standards"]:
            stats.append(", ".join(r["standardBindings"]["standards"]))
        if meta.get("license"):
            stats.append(meta["license"])
        search = " ".join([r["identity"], meta.get("title", ""), meta.get("description", ""), *r["domains"], *r["standardBindings"]["standards"],
                           KIND_LABEL.get(r["packageKind"], "")]).lower()
        cards.append(f"""<a class="card" href="{e['page'].removeprefix('catalog/')}" data-search="{html.escape(search)}">
<span class="kind">{html.escape(KIND_LABEL.get(r['packageKind'], str(r['packageKind'])))}</span>
<h3>{html.escape(meta.get('title') or r['identity'])}</h3><p><code>{html.escape(r['identity'])}</code></p>
<p>{html.escape(meta.get('description', ''))}</p><p>{_badge_html([(e["scale"]["breadth"], False)] + _badges(r))}</p>
<p class="muted">{html.escape(' · '.join(stats))}</p></a>""")
    body = f"""<style>{CATALOG_STYLE}</style><h1>OWP package catalog</h1>
<p>The example packages of this repository, each packed, verified, and checked by the reference CLI. Every number comes from
<code>ontle inspect --report</code>. They are samples: their data is small and illustrative, not production scale. <em>Minimal</em>,
<em>focused</em>, and <em>full</em> say how much of OWP a package uses (up to 5, up to 19, and 20 or more assets); an ontology is
sized by its terms. Two Worlds also bind real public artifacts (a robot dataset, a 3D scene, an OPC UA model). Resolve from this catalog with <code>--source index:{SITE}/catalog/index.json</code> (<a href="index.json">index.json</a>).</p>
<input type="search" id="q" placeholder="Filter: kind, domain, standard, name" aria-label="Filter packages">
<div class="cards" id="cards">{''.join(cards)}</div>
<script>
document.getElementById("q").addEventListener("input", (ev) => {{
  const words = ev.target.value.toLowerCase().split(/\\s+/).filter(Boolean);
  for (const c of document.querySelectorAll("#cards .card")) c.hidden = !words.every((w) => c.dataset.search.includes(w));
}});
</script>"""
    (catalog / "index.html").write_text(page("OWP package catalog", body), encoding="utf-8")
