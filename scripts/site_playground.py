"""The Playground on the project site (registry step P3): check a package in the browser, without uploading it.

    playground/index.html          drop a package folder or an .owp.zip, or try an example from the catalog
    playground/owp-validator.js    the TypeScript validator, resolver, and report built for the browser
                                   (implementations/typescript: npm run bundle)

The page resolves dependencies through the catalog's index (catalog/index.json). build_site.py calls build_playground().
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "implementations" / "typescript" / "dist-browser" / "owp-validator.js"

STYLE = """
.drop{border:2px dashed var(--line);border-radius:10px;padding:28px;text-align:center;margin:16px 0}
.drop.over{border-color:var(--accent);background:var(--code)}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:center;margin-top:10px}
button,label.btn{font:inherit;font-size:14px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:6px 12px;cursor:pointer}
button:hover,label.btn:hover{border-color:var(--accent)} input[type=file]{display:none}
.verdict{font-size:20px;font-weight:600;margin:4px 0} .ok{color:var(--accent)} .bad{color:#c0392b}
@media (prefers-color-scheme: dark){.bad{color:#ff7b6b}}
.issues li{margin:4px 0;font-size:14px} .issues code{font-size:12px}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:28px} @media (max-width:760px){.cols{grid-template-columns:1fr}}
aside h3{font-size:14px;margin:18px 0 6px;color:var(--muted)} aside p{font-size:14px;margin:2px 0}
#status{min-height:1.5em}
"""

BODY = """<p class="muted"><a href="../">Open World Package</a> · <a href="../catalog/">Catalog</a></p>
<h1>OWP Playground</h1>
<p>Check a package in your browser. Nothing is uploaded: the TypeScript validator runs on this page and gives the same
verdict as <code>ontle validate</code>. Dependencies are fetched from the <a href="../catalog/">package catalog</a> and checked against their digests.</p>
<div class="drop" id="drop">
  <p><strong>Drop a package folder or an <code>.owp.zip</code> here</strong></p>
  <div class="row">
    <label class="btn">Choose a folder<input type="file" id="folder" webkitdirectory multiple></label>
    <label class="btn">Choose an archive<input type="file" id="archive" accept=".zip"></label>
  </div>
  <div class="row" id="examples"><span class="muted">or try an example:</span></div>
  <div class="row"><label><input type="checkbox" id="resolve" checked> resolve dependencies from the catalog</label></div>
</div>
<p id="status" class="muted"></p>
<div id="result"></div>
<script type="module">
import { check } from "./owp-validator.js";
const indexUrl = new URL("../catalog/index.json", location.href).href;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

function markdown(text) {  // headings, lists, code blocks, paragraphs, inline code: enough for a card
  const out = []; let list = false, code = false, para = [];
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
  const flush = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  for (const line of text.split("\\n")) {
    if (line.startsWith("```")) { flush(); if (list) { out.push("</ul>"); list = false; } out.push(code ? "</pre>" : "<pre>"); code = !code; continue; }
    if (code) { out.push(esc(line) + "\\n"); continue; }
    const h = /^(#{1,4})\\s+(.*)$/.exec(line), li = /^\\s*[-*]\\s+(.*)$/.exec(line);
    if (h) { flush(); if (list) { out.push("</ul>"); list = false; } const n = Math.min(h[1].length + 1, 4); out.push(`<h${n}>${inline(h[2])}</h${n}>`); }
    else if (li) { flush(); if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(li[1])}</li>`); }
    else if (!line.trim()) { flush(); if (list) { out.push("</ul>"); list = false; } }
    else para.push(line.trim());
  }
  flush(); if (list) out.push("</ul>"); if (code) out.push("</pre>");
  return out.join("");
}

function render(r) {
  const rep = r.report || {};
  const issues = (title, list) => list.length ? `<h2>${title} (${list.length})</h2><ul class="issues">${list.map((x) => `<li><code>${esc(x.code)}</code> ${esc(x.message)}</li>`).join("")}</ul>` : "";
  const stats = [];
  if (rep.profile) stats.push(`<p>Profile: declared ${esc(rep.profile.declared ?? "none")}, satisfied ${esc(rep.profile.satisfied ?? "none")}</p>`);
  if (rep.state) stats.push(`<p>EWS fields with a binding: ${rep.state.withBinding}/${rep.state.fields}</p>`);
  if (rep.semanticCoverage) stats.push(`<p>Fields bound to ontology terms: ${rep.semanticCoverage.boundToTerms}/${rep.semanticCoverage.fields}</p>`);
  if (rep.externalRefs) stats.push(`<p>External references pinned: ${rep.externalRefs.pinned}/${rep.externalRefs.total}</p>`);
  if (rep.assets) stats.push(`<p>Assets: ${rep.assets.total}</p>`);
  if (rep.integrity) stats.push(`<p class="muted">${esc(rep.integrity.digest.slice(0, 19))}… · ${rep.integrity.size.toLocaleString()} bytes</p>`);
  const deps = r.resolved.length || r.unresolved.length
    ? `<h3>Dependencies</h3>${r.resolved.map((d) => `<p>${esc(d)}: from the catalog</p>`).join("")}${r.unresolved.map((d) => `<p class="bad">${esc(d)}: not in the catalog; cross-package rules not checked</p>`).join("")}` : "";
  const hints = (rep.hints || []).length ? `<h3>Hints</h3>${rep.hints.map((h) => `<p>${esc(h)}</p>`).join("")}` : "";
  $("result").innerHTML = `<p class="verdict ${r.valid ? "ok" : "bad"}">${r.valid ? "VALID" : "INVALID"}</p>
    <p><code>${esc(r.identity ?? "no identity")}</code></p>
    <div class="cols"><div>${issues("Errors", r.errors)}${issues("Warnings", r.warnings)}
    ${r.card ? `<h2>Card <span class="muted">${esc(r.card.path)}</span></h2>${markdown(r.card.text)}` : ""}</div>
    <aside><h3>Report</h3>${stats.join("") || "<p class=muted>no report</p>"}${deps}${hints}
    <h3>Checked by</h3><p class="muted">${esc((rep.validator || {}).implementation ?? "owp-validator-ts")} ${esc((rep.validator || {}).version ?? "")}, in this browser</p></aside></div>`;
}

async function run(input, label) {
  $("status").textContent = `Checking ${label}…`; $("result").innerHTML = "";
  try {
    const r = await check(input, $("resolve").checked ? { indexUrl } : {});
    $("status").textContent = `Checked ${label}.`; render(r);
  } catch (e) {
    $("status").textContent = ""; $("result").innerHTML = `<p class="verdict bad">Could not check ${esc(label)}</p><p>${esc(e.message)}</p>`;
  }
}

async function readEntry(entry, prefix, out) {  // a dropped folder, walked with the File and Directory Entries API
  if (entry.isFile) { const f = await new Promise((ok, no) => entry.file(ok, no)); out[prefix + entry.name] = new Uint8Array(await f.arrayBuffer()); return; }
  const reader = entry.createReader();
  for (;;) {
    const batch = await new Promise((ok, no) => reader.readEntries(ok, no));
    if (!batch.length) break;
    for (const e of batch) await readEntry(e, `${prefix}${entry.name}/`, out);
  }
}

const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", async (e) => {
  e.preventDefault(); drop.classList.remove("over");
  const items = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (items.length === 1 && items[0].isFile && items[0].name.endsWith(".zip")) {
    const f = e.dataTransfer.files[0]; return run({ archive: new Uint8Array(await f.arrayBuffer()) }, f.name);
  }
  const files = {};
  for (const entry of items) await readEntry(entry, "", files);
  run({ files }, items.length === 1 ? items[0].name : "the dropped files");
});
$("folder").addEventListener("change", async (e) => {
  const files = {};
  for (const f of e.target.files) files[f.webkitRelativePath || f.name] = new Uint8Array(await f.arrayBuffer());
  run({ files }, "the folder");
});
$("archive").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (f) run({ archive: new Uint8Array(await f.arrayBuffer()) }, f.name);
});
const linked = new URLSearchParams(location.search).get("archive");  // ?archive=<URL relative to this page>: check it now
if (linked) fetch(new URL(linked, location.href)).then((r) => r.arrayBuffer()).then((b) => run({ archive: new Uint8Array(b) }, linked.split("/").pop()));
fetch(indexUrl).then((r) => r.json()).then((index) => {
  for (const p of index.packages.slice(0, 6)) {
    const b = document.createElement("button");
    b.textContent = p.title || p.identity;
    b.addEventListener("click", async () => {
      const bytes = new Uint8Array(await (await fetch(new URL(p.archive, indexUrl))).arrayBuffer());
      run({ archive: bytes }, p.identity);
    });
    $("examples").append(b);
  }
}).catch(() => {});
</script>"""


def build_playground(out: Path, page: Callable[[str, str], str], bundle: Path = BUNDLE) -> bool:
    """Write playground/ under the site root `out`; False (and nothing written) when the bundle has not been built."""
    if not bundle.is_file():
        return False
    target = out / "playground"
    target.mkdir(parents=True)
    shutil.copy2(bundle, target / "owp-validator.js")
    (target / "index.html").write_text(page("OWP Playground", f"<style>{STYLE}</style>{BODY}"), encoding="utf-8")
    return True
