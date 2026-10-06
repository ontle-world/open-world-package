// The field tables of src/structure.ts and src/rules/experimental.ts define the same fields as ../../schemas/
// (tests/test_structure.py checks the Python tables the same way): a closed table is a closed schema object with
// the same properties (an `extensions` block where the schema allows one), an open container is not closed, and a
// list is an array of the same items.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as S from "../dist/structure.js";
import { EXPERIMENTAL_STRUCTURES, FAMILIES } from "../dist/rules/experimental.js";

const schemas = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "schemas");
const kebab = (kind) => kind.replace(/(?<!^)(?=[A-Z])/g, "-").toLowerCase();
const problems = [];

function resolve(schema, root) {
  while (schema && typeof schema === "object" && "$ref" in schema) {
    let node = root;
    for (const part of schema.$ref.replace(/^#\//, "").split("/")) node = node[part];
    schema = node;
  }
  if (schema && Array.isArray(schema.oneOf)) {  // a dependency: string or mapping
    const objects = schema.oneOf.map((s) => resolve(s, root)).filter((s) => s.type === "object");
    if (objects.length === 1) return objects[0];
  }
  return schema;
}

function compare(shape, schema, root, at) {
  schema = resolve(schema, root);
  if (shape.t === "any") return;
  if (shape.t === "list") {
    if (schema.type !== "array") return problems.push(`${at}: a list in the table, ${schema.type} in the schema`);
    return compare(shape.items, schema.items, root, `${at}[]`);
  }
  if (shape.t === "open") {
    if (schema.additionalProperties === false) problems.push(`${at}: open in the table but closed in the schema`);
    return;
  }
  if (schema.additionalProperties !== false) return problems.push(`${at}: closed in the table but open in the schema`);
  const props = { ...(schema.properties ?? {}) };
  const ext = "extensions" in props;
  delete props.extensions;
  if (ext !== shape.extensions) problems.push(`${at}: an extensions block is allowed in one but not the other`);
  const want = Object.keys(props).sort(), have = Object.keys(shape.fields).sort();
  for (const k of want) if (!have.includes(k)) problems.push(`${at || "(root)"}: the schema has ${k}, the table does not`);
  for (const k of have) if (!want.includes(k)) problems.push(`${at || "(root)"}: the table has ${k}, the schema does not`);
  for (const k of have) if (want.includes(k)) compare(shape.fields[k], props[k], root, at ? `${at}.${k}` : k);
}

const tables = [
  ["owp-manifest", S.MANIFEST],
  ["observation-set", S.OBSERVATION_SET],
  ["effective-world-state", S.EFFECTIVE_WORLD_STATE],
  ["semantic-binding", S.SEMANTIC_BINDING],
  ...Object.entries(S.ASSET_STRUCTURES).map(([kind, shape]) => [kind === "OntologyTermIndex" ? "ontology-term-index" : kebab(kind), shape]),
  ...Object.entries(EXPERIMENTAL_STRUCTURES).map(([kind, shape]) => [(kind in FAMILIES ? "" : "experimental/") + kebab(kind), shape]),
];
let checked = 0;
for (const [name, shape] of tables) {
  const file = path.join(schemas, `${name}.schema.json`);
  if (!fs.existsSync(file)) { problems.push(`${name}: no schema file`); continue; }
  const before = problems.length;
  const root = JSON.parse(fs.readFileSync(file, "utf8"));
  compare(shape, root, root, "");
  for (let i = before; i < problems.length; i++) problems[i] = `${name}.schema.json: ${problems[i]}`;
  checked++;
}
for (const p of problems) console.log(`FAIL structure: ${p}`);
console.log(`structure: ${checked} tables against schemas/, ${problems.length} differences`);
process.exitCode = problems.length ? 1 : 0;
