// End-to-end demos (ROADMAP section 4), checked independently of the Python reference:
// compile each demo's observations to its expected EWS, check the EWS output contract (spec 12.1),
// and check the detached evidence against the committed subject archive (spec 9.1).
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { checkEws, compileEws, ewsEqual } from "../dist/ews.js";
import { checkDetachedEvidence } from "../dist/evidence.js";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const demos = [
  { dir: "physical-ai", world: "examples/physical-ai/mobile-manipulation-world", archive: "multimodal-action-world-model-0.1.0.owp.zip" },
  { dir: "business-ai", world: "examples/business/manufacturing-quality-world", archive: "quality-transition-world-model-0.1.0.owp.zip" },
];
const read = (f) => parse(fs.readFileSync(f, "utf8"));
const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), "owp-demos-"));
let bad = 0;
for (const d of demos) {
  const base = path.join(repo, "demos", d.dir);
  const world = path.join(repo, d.world);
  const expected = read(path.join(base, "expected-ews.yaml"));
  const compiler = expected.spec.stateCompiler.split("#")[1];
  const r = compileEws(world, compiler, read(path.join(base, "observations.yaml")), expected.spec.context.asOf);
  const eq = r.ok && ewsEqual(r.ews, expected).equal;
  const chk = checkEws(expected, world);
  const ev = checkDetachedEvidence(read(path.join(base, "evidence.yaml")), path.join(base, d.archive), cacheDir);
  const ok = eq && chk.valid && ev.valid;
  if (!ok) bad++;
  console.log(`${ok ? "PASS" : "FAIL"} demos/${d.dir} (compile==expected: ${eq}; expected passes 12.1: ${chk.valid}; evidence binds: ${ev.valid})`);
  if (!r.ok) console.log(`  refused: ${r.errors.join("; ")}`);
  for (const e of [...chk.errors, ...ev.errors]) console.log(`  [${e.code}] ${e.message}`);
}
fs.rmSync(cacheDir, { recursive: true, force: true });
process.exit(bad ? 1 : 0);
