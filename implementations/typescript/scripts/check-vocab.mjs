// Checks that src/vocab.ts equals ../../vocab: ASSET_KINDS (group -> kind -> stability) against
// asset-kinds.yaml, and VALUE_SETS (name -> values) against value-sets.yaml.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { ASSET_KINDS, VALUE_SETS } from "../dist/vocab.js";

const vocab = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "vocab");
const load = (f) => parse(fs.readFileSync(path.join(vocab, f), "utf8"));
const kinds = Object.fromEntries(
  Object.entries(load("asset-kinds.yaml").groups).map(([g, ks]) => [g, Object.fromEntries(Object.entries(ks).map(([k, v]) => [k, v.stability]))]),
);
const valueSets = Object.fromEntries(Object.entries(load("value-sets.yaml").valueSets).map(([n, v]) => [n, Object.keys(v.values).sort()]));
const sortedSets = Object.fromEntries(Object.entries(VALUE_SETS).map(([n, v]) => [n, [...v].sort()]));
const canon = (v) => JSON.stringify(v, (_k, x) => (x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort()) : x));

let bad = 0;
for (const [file, yaml, ts, name] of [
  ["asset-kinds.yaml", kinds, ASSET_KINDS, "ASSET_KINDS"],
  ["value-sets.yaml", valueSets, sortedSets, "VALUE_SETS"],
]) {
  if (canon(yaml) === canon(ts)) {
    console.log(`PASS vocab: src/vocab.ts ${name} matches vocab/${file}`);
  } else {
    bad++;
    console.log(`FAIL vocab: src/vocab.ts ${name} differs from vocab/${file}`);
    console.log(`  yaml: ${canon(yaml)}`);
    console.log(`  ts:   ${canon(ts)}`);
  }
}
process.exitCode = bad ? 1 : 0;
