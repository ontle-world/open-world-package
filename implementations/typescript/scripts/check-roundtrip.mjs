// Round-trip gate (docs/PROFILE_PROMOTION.md, Interoperability): re-serializing every YAML file of a
// package in a different layout must not change its validation outcome, because meaning depends on the
// JSON data model, not on YAML formatting (spec section 12).
//
// For every package under ../../examples (each directory with owp.yaml, any depth) and every conformance
// case with valid: true, the package is copied to a temp directory, each .yaml/.yml file is loaded with
// YAML 1.2 core rules (timestamps stay text) and dumped in flow style with sorted keys, and the copy must
// give the same verdict and the same multisets of error ids and warning ids as the original.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse, parseDocument, stringify } from "yaml";
import { validatePackage } from "../dist/validate.js";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

function packagesUnder(dir) {
  const out = [];
  const walk = (d) => {
    const entries = fs.readdirSync(d, { withFileTypes: true });
    if (entries.some((e) => e.isFile() && e.name === "owp.yaml")) out.push(d);
    for (const e of entries) if (e.isDirectory() && !e.name.startsWith(".") && e.name !== "node_modules") walk(path.join(d, e.name));
  };
  walk(dir);
  return out.sort();
}

function packages() {
  const expected = parse(fs.readFileSync(path.join(repo, "conformance", "expected.yaml"), "utf8")).cases;
  const cases = Object.entries(expected)
    .filter(([, exp]) => exp.valid === true)
    .map(([id]) => path.join(repo, "conformance", "cases", id))
    .sort();
  return [...packagesUnder(path.join(repo, "examples")), ...cases];
}

/** Verdict plus sorted error and warning ids (multisets). */
function outcome(dir) {
  const r = validatePackage(dir);
  const ids = (list) => list.map((x) => x.code).sort();
  return JSON.stringify({ valid: r.valid, errors: ids(r.errors), warnings: ids(r.warnings) });
}

function yamlFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...yamlFiles(p));
    else if (e.isFile() && /\.ya?ml$/i.test(e.name)) out.push(p);
  }
  return out;
}

/** Reload with YAML 1.2 core rules and dump in flow style with sorted keys. Unparseable files are left as is. */
function reserialize(file) {
  const doc = parseDocument(fs.readFileSync(file, "utf8"), { uniqueKeys: true });
  if (doc.errors.length > 0) return;
  const text = stringify(doc.toJS(), { collectionStyle: "flow", sortMapEntries: true, lineWidth: 0 });
  fs.writeFileSync(file, text);
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "owp-roundtrip-"));
let checked = 0;
const failures = [];
try {
  for (const pkg of packages()) {
    const copy = path.join(tmp, String(checked));
    // Like Python's shutil.copytree: symlinks are copied as the files they point to.
    fs.cpSync(pkg, copy, { recursive: true, dereference: true });
    for (const f of yamlFiles(copy)) reserialize(f);
    const before = outcome(pkg);
    const after = outcome(copy);
    checked++;
    if (before !== after) failures.push(`${path.relative(repo, pkg)}\n    original:     ${before}\n    reserialized: ${after}`);
  }
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

for (const f of failures) console.log(`FAIL ${f}`);
console.log(`${failures.length ? "FAIL" : "PASS"} roundtrip: ${checked - failures.length}/${checked} packages keep their verdict, error ids, and warning ids after YAML re-serialization`);
process.exitCode = failures.length ? 1 : 0;
