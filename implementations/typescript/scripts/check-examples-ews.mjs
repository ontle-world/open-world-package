// Compiles each example World's examples/observations.yaml at the asOf recorded in
// examples/expected-ews.yaml and compares under spec 12.2 equality; also runs the 12.1 check.
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { compileEws, ewsEqual, checkEws } from "../dist/ews.js";

const ex = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "examples");
let bad = 0;
for (const w of ["business/manufacturing-quality-world", "business/sales-prioritization-world", "physical-ai/mobile-manipulation-world"]) {
  const dir = path.join(ex, w);
  const expected = parse(fs.readFileSync(path.join(dir, "examples/expected-ews.yaml"), "utf8"));
  const obs = parse(fs.readFileSync(path.join(dir, "examples/observations.yaml"), "utf8"));
  const compiler = expected.spec.stateCompiler.split("#")[1];
  const r = compileEws(dir, compiler, obs, expected.spec.context.asOf);
  if (!r.ok) { bad++; console.log(`FAIL ${w}: refused ${r.errors.join("; ")}`); continue; }
  const eq = ewsEqual(r.ews, expected);
  const chk = checkEws(expected, dir);
  const ok = eq.equal && chk.valid;
  if (!ok) bad++;
  console.log(`${ok ? "PASS" : "FAIL"} ${w} (compile==expected: ${eq.equal}; expected passes 12.1: ${chk.valid})`);
  for (const d of eq.diffs) console.log("   " + d);
  for (const e of chk.errors) console.log("   " + e.message);
}
process.exitCode = bad ? 1 : 0;
