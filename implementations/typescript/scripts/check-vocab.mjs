// Checks that src/vocab.ts ASSET_KINDS (group -> kind -> stability) equals ../../vocab/asset-kinds.yaml.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { ASSET_KINDS } from "../dist/vocab.js";

const file = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "vocab", "asset-kinds.yaml");
const doc = parse(fs.readFileSync(file, "utf8"));
const fromYaml = Object.fromEntries(
  Object.entries(doc.groups).map(([g, kinds]) => [g, Object.fromEntries(Object.entries(kinds).map(([k, v]) => [k, v.stability]))]),
);
const canon = (v) => JSON.stringify(v, (_k, x) => (x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort()) : x));
if (canon(fromYaml) === canon(ASSET_KINDS)) {
  console.log(`PASS vocab: src/vocab.ts matches ${path.relative(process.cwd(), file)}`);
} else {
  console.log(`FAIL vocab: src/vocab.ts differs from ${file}`);
  console.log(`  yaml: ${canon(fromYaml)}`);
  console.log(`  ts:   ${canon(ASSET_KINDS)}`);
  process.exitCode = 1;
}
