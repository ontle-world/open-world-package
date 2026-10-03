/**
 * Spec section 19.2: knowledge extraction. Turns query result rows (column -> JSON value) into an
 * ObservationSet with a KnowledgeExtractionProfile. Running the query is outside the specification.
 */
import { canon, isUtcTimestamp } from "./ews.js";
import { isExtractionTemplate } from "./rules/experimental.js";
import { isObj, Obj } from "./util.js";
import { API_VERSION } from "./vocab.js";

export type ExtractionResult = { ok: true; observations: Obj } | { ok: false; errors: string[] };

/** Appendix A: invalid extraction input; nothing is produced. */
const INPUT_RULE = "extraction.input";

class ExtractionInputError extends Error {}
const refuse = (message: string): never => {
  throw new ExtractionInputError(message);
};

/** Rule 1: every declared parameter has a value of its type (string by default); no undeclared parameter. */
function checkParameters(spec: Obj, parameters: Obj): void {
  const declared = spec.parameters ?? {};
  if (!isObj(declared)) refuse("spec.parameters must be a mapping");
  const decl = declared as Obj;
  for (const name of Object.keys(parameters)) if (!(name in decl)) refuse(`parameter "${name}" is not declared in spec.parameters`);
  for (const [name, d] of Object.entries(decl)) {
    if (!(name in parameters)) refuse(`parameter "${name}" has no value`);
    const type = isObj(d) && d.type !== undefined ? d.type : "string";
    const v = parameters[name];
    const ok = (type === "string" && typeof v === "string") || (type === "number" && typeof v === "number") || (type === "boolean" && typeof v === "boolean");
    if (!ok) refuse(`parameter "${name}" must be a ${String(type)}`);
  }
}

/**
 * Rule 3: a string as is, a boolean as true/false, a number in its shortest decimal form — without a
 * fraction when integral (10.0 -> "10") and without an exponent (1e-7 -> "0.0000001"). An array,
 * mapping, or other value is invalid input.
 */
function idPart(v: unknown): string {
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number" && Number.isFinite(v)) {
    if (Number.isInteger(v)) return BigInt(v).toString();
    return decimal(String(v)); // String() is the shortest round-trip form; only the exponent needs expanding
  }
  return refuse(`id column values must be strings, numbers, or booleans (got ${JSON.stringify(v)})`);
}

/** Expand JS exponent notation (non-integral numbers only reach it below 1e-6) into plain decimal digits. */
function decimal(s: string): string {
  const m = /^(-?)(\d)(?:\.(\d+))?e-(\d+)$/.exec(s);
  if (!m) return s;
  return `${m[1]}0.${"0".repeat(Number(m[4]) - 1)}${m[2]}${m[3] ?? ""}`;
}

/** Unicode code point order (rule 4), not UTF-16 code unit order. */
function compareCodePoints(a: string, b: string): number {
  const x = [...a];
  const y = [...b];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = x[i].codePointAt(0)! - y[i].codePointAt(0)!;
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

const present = (v: unknown) => v !== undefined && v !== null;

export function transformExtraction(profile: unknown, rows: unknown, parameters: Obj, snapshot: string | undefined): ExtractionResult {
  try {
    return { ok: true, observations: transform(profile, rows, parameters, snapshot) };
  } catch (e) {
    if (e instanceof ExtractionInputError) return { ok: false, errors: [`${INPUT_RULE}: ${e.message}`] };
    throw e;
  }
}

function transform(profile: unknown, rows: unknown, parameters: Obj, snapshot: string | undefined): Obj {
  const p = isObj(profile) ? profile : {};
  const spec = isObj(p.spec) ? p.spec : {};
  checkParameters(spec, parameters);
  if (!Array.isArray(rows) || !rows.every(isObj)) refuse("results must be a list of rows (column -> value)");
  const templates = spec.observations;
  if (!Array.isArray(templates) || templates.length === 0) refuse("spec.observations must be a non-empty list");

  const observations: Obj[] = [];
  const seen = new Set<string>();
  (templates as unknown[]).forEach((t, ti) => {
    if (!isExtractionTemplate(t)) refuse(`spec.observations[${ti}] needs type, a non-empty id column list, and a values mapping`);
    const template = t as { type: string; id: unknown[]; values: Obj; observedAt?: unknown; subject?: unknown };
    const observed = template.observedAt ?? {};
    if (!isObj(observed)) refuse(`spec.observations[${ti}].observedAt must be a mapping`);
    const at0 = observed as Obj;

    // Rule 2: rows to observations.
    const produced: Obj[] = [];
    for (const row of rows as Obj[]) {
      const ids = template.id.map((col) => (typeof col === "string" ? row[col] : undefined));
      if (ids.some((v) => !present(v))) continue;
      const values: Obj = {};
      for (const [key, col] of Object.entries(template.values)) {
        if (typeof col === "string" && present(row[col])) values[key] = row[col];
      }
      if (Object.keys(values).length === 0) continue;
      let at: unknown = typeof at0.column === "string" ? row[at0.column] : undefined;
      if (!present(at)) {
        const def = at0.default ?? "snapshot";
        at = def === "snapshot" ? snapshot : def;
      }
      if (!isUtcTimestamp(at)) refuse(`observation time ${JSON.stringify(at ?? null)} for ${template.type} must be UTC YYYY-MM-DDTHH:MM:SSZ`);
      const obs: Obj = { id: `${template.type}:${ids.map(idPart).join("|")}`, type: template.type, observedAt: at, values };
      // Spec 12.3: the subject column names what the observation is about.
      const subject = typeof template.subject === "string" ? row[template.subject] : undefined;
      if (subject !== undefined && subject !== null) obs.subject = idPart(subject);
      produced.push(obs);
    }

    // Rule 4: order by id; identical repeats collapse; conflicts and cross-entry repeats are errors.
    produced.sort((a, b) => compareCodePoints(a.id as string, b.id as string));
    const unique: Obj[] = [];
    for (const o of produced) {
      const last = unique[unique.length - 1];
      if (last && last.id === o.id) {
        if (canon(last) !== canon(o)) refuse(`observation id ${String(o.id)} has conflicting values or times`);
        continue;
      }
      if (seen.has(o.id as string)) refuse(`observation id ${String(o.id)} is produced by two entries`);
      seen.add(o.id as string);
      unique.push(o);
    }
    observations.push(...unique);
  });

  // Rule 5: provenance.
  const md = isObj(p.metadata) ? p.metadata : {};
  const provenance: Obj = { extraction: present(md.version) && md.version !== "" ? `${String(md.name)}@${String(md.version)}` : String(md.name) };
  if (Object.keys(parameters).length > 0) provenance.parameters = { ...parameters };
  if (snapshot !== undefined) provenance.snapshot = snapshot;
  return { apiVersion: API_VERSION, kind: "ObservationSet", spec: { provenance, observations } };
}
