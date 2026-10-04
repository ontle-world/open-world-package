// Evaluates the mutants scripts/parity_fuzz.py wrote: node parity-eval.mjs <mutant dir> <dist dir>.
// Prints {id: {valid, errors, warnings[, ews]} | {crash}} as JSON, the same shape the Python side produces.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [dir, dist] = process.argv.slice(2);
const load = (f) => import(pathToFileURL(path.join(dist, f)).href);
const { validatePackage } = await load("validate.js");
const { validateWithResolution } = await load("resolve.js");
const { checkEws, compileEws } = await load("ews.js");
const { loadYamlFile } = await load("util.js");

const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), "owp-parity-cache-"));
const ids = (xs) => [...new Set(xs)].sort();
const ID = /(?:^|; )([a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+):/g;
const out = {};
for (const m of manifest) {
  const base = path.join(dir, m.id);
  let res;
  try {
    if (m.section === "cases") {
      const r = validatePackage(base);
      res = { valid: r.valid, errors: ids(r.errors.map((e) => e.code)), warnings: ids(r.warnings.map((e) => e.code)) };
    } else if (m.section === "resolution") {
      const r = validateWithResolution(path.join(base, "root"), { sources: [path.join(base, "packages")], cacheDir });
      res = { valid: r.valid, errors: ids(r.errors.map((e) => e.code)), warnings: ids(r.warnings.map((e) => e.code)) };
    } else if (m.section === "ews") {
      const obs = loadYamlFile(path.join(base, "observations.yaml"));
      const r = obs.ok ? compileEws(path.join(base, "world"), m.compiler, obs.value, m.asOf) : { ok: false, errors: [`ews.input: ${obs.error}`] };
      res = r.ok
        ? { valid: true, errors: [], warnings: [], ews: r.ews }
        : { valid: false, errors: ids(r.errors.flatMap((e) => [...e.matchAll(ID)].map((x) => x[1]))), warnings: [] };
    } else {
      const doc = loadYamlFile(path.join(base, "ews.yaml"));
      const r = doc.ok ? checkEws(doc.value, path.join(base, "world")) : { valid: false, errors: [{ code: "ews.kind" }] };
      res = { valid: r.valid, errors: ids(r.errors.map((e) => e.code)), warnings: [] };
    }
  } catch (e) {
    res = { crash: String(e && e.stack).slice(0, 500) };
  }
  out[m.id] = res;
}
fs.rmSync(cacheDir, { recursive: true, force: true });
process.stdout.write(JSON.stringify(out));
