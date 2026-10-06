// The browser bundle gives the CLI's verdicts: run every validation case of the conformance suite through
// dist-browser/owp-validator.js on its in-memory file system and compare with conformance/reference-ids.json
// (exact error and warning ids), and check that every example validates. Run `node scripts/bundle.mjs` first.
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.join(here, "..", "..", "..");
const { check } = await import(path.join(here, "..", "dist-browser", "owp-validator.js"));
const reference = JSON.parse(fs.readFileSync(path.join(repo, "conformance", "reference-ids.json"), "utf8")).cases;

function readTree(dir) {
  const out = {};
  const walk = (rel) => {
    for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isSymbolicLink()) return "symlink"; // a dropped folder holds no links: such cases are not comparable
      if (e.isDirectory()) { if (walk(r) === "symlink") return "symlink"; }
      else out[r] = new Uint8Array(fs.readFileSync(path.join(dir, r)));
    }
  };
  return walk("") === "symlink" ? null : out;
}

const ids = (list) => [...new Set(list.map((x) => x.code))].sort();
let ok = 0, skipped = 0;
const failures = [];
for (const name of Object.keys(reference).sort()) {
  const files = readTree(path.join(repo, "conformance", "cases", name));
  if (files === null || !("owp.yaml" in files)) { skipped++; continue; }
  let r;
  try {
    r = await check({ files });
  } catch (e) {
    failures.push(`${name}: ${e.message}`);
    continue;
  }
  const want = reference[name];
  const got = { errors: ids(r.errors), warnings: ids(r.warnings) };
  if (JSON.stringify(got) === JSON.stringify({ errors: [...want.errors].sort(), warnings: [...want.warnings].sort() })) ok++;
  else failures.push(`${name}: browser ${JSON.stringify(got)} != reference ${JSON.stringify(want)}`);
}
for (const dir of fs.readdirSync(path.join(repo, "examples")).flatMap((g) => fs.readdirSync(path.join(repo, "examples", g)).map((p) => path.join(repo, "examples", g, p)))) {
  if (!fs.existsSync(path.join(dir, "owp.yaml"))) continue;
  const r = await check({ files: readTree(dir) });
  if (r.valid && r.report.kind === "PackageReport") ok++;
  else failures.push(`${path.relative(repo, dir)}: ${JSON.stringify(r.errors)}`);
}
for (const f of failures) console.log(`FAIL ${f}`);
console.log(`browser bundle: ${ok}/${ok + failures.length} agree with the reference${skipped ? ` (${skipped} cases need links or no manifest, skipped)` : ""}`);
process.exit(failures.length ? 1 : 0);
