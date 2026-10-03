/**
 * Spec section 12: Effective World State documents.
 *  - checkEws:   12.1 output contract against a World's State Compiler
 *  - compileEws: 12.2 declarative bindings over an ObservationSet at asOf
 *  - ewsEqual:   12.2 equality
 * Both document kinds contain only their schema fields plus extensions blocks (spec 12);
 * extension names are not checked (no manifest declares them), and compile/equality ignore them.
 */
import * as path from "node:path";
import { Issue } from "./context.js";
import { get, isNonEmptyString, isObj, loadYamlFile, Obj } from "./util.js";
import { API_VERSION } from "./vocab.js";
import { bindingForm, bindingProblems, durationSeconds, outputListProblems, outputLists, outputSchemaFields, outputUnits, unitProblems } from "./rules/world.js";
import { localAssetKinds } from "./discovery.js";
import { EFFECTIVE_WORLD_STATE, OBSERVATION_SET, structureProblems } from "./structure.js";

const UTC_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/;

/** UTC `YYYY-MM-DDTHH:MM:SSZ` that is also a real calendar instant. */
export function isUtcTimestamp(v: unknown): v is string {
  if (typeof v !== "string") return false;
  const m = UTC_RE.exec(v);
  if (!m) return false;
  const d = new Date(v);
  return !Number.isNaN(d.getTime()) && d.toISOString().replace(".000Z", "Z") === v;
}

/** Canonical JSON (sorted keys) for deep equality / distinctness. */
export function canon(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canon).join(",")}]`;
  if (isObj(v)) return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon(v[k])}`).join(",")}}`;
  return JSON.stringify(v);
}

interface WorldCompiler {
  identity: string;
  compilerPath: string;
  spec: Obj;
  /** EWS fields (spec 12.1); null when the compiler declares none. */
  fields: string[] | null;
  /** Problems resolving outputSchemaRef. */
  fieldProblems: { rule: string; msg: string }[];
}

function loadWorld(worldDir: string): { identity?: string; manifest?: Obj; problems: string[] } {
  const l = loadYamlFile(path.join(worldDir, "owp.yaml"));
  if (!l.ok || !isObj(l.value)) return { problems: [`cannot read World manifest in ${worldDir}`] };
  const m = l.value;
  const ns = get(m, "metadata", "namespace");
  const n = get(m, "metadata", "name");
  const v = get(m, "metadata", "version");
  if (m.kind !== "WorldPackage") return { problems: [`${worldDir} is not a WorldPackage`] };
  return { identity: `${ns}/${n}@${v}`, manifest: m, problems: [] };
}

/** Load a local StateCompilerProfile asset of the World. */
function loadCompiler(worldDir: string, manifest: Obj, identity: string, compilerPath: string): WorldCompiler | string {
  if (localAssetKinds(worldDir, manifest).get(compilerPath) !== "StateCompilerProfile") return `${compilerPath} is not a local StateCompilerProfile asset of ${identity}`;
  const l = loadYamlFile(path.join(worldDir, compilerPath));
  if (!l.ok || !isObj(l.value)) return `cannot read State Compiler ${compilerPath}`;
  const spec = get(l.value, "spec");
  if (!isObj(spec)) return `State Compiler ${compilerPath} has no spec`;
  const { fields, problems } = outputSchemaFields(worldDir, spec, compilerPath);
  return { identity, compilerPath, spec, fields, fieldProblems: problems };
}

// ---------------------------------------------------------------- 12.1 check

export interface EwsCheckResult {
  valid: boolean;
  errors: Issue[];
}

export function checkEws(ews: unknown, worldDir: string): EwsCheckResult {
  const errors: Issue[] = [];
  const e = (code: string, message: string) => errors.push({ code, message });

  const world = loadWorld(worldDir);
  world.problems.forEach((p) => e("ews.world-ref", p));
  if (!world.manifest || !world.identity) return { valid: false, errors };
  // Spec 12.1 (round 3): checking does not require the World package to be valid.

  // Structural form (schemas/effective-world-state.schema.json).
  if (!isObj(ews)) {
    e("ews.kind", "EWS document must be a mapping");
    return { valid: false, errors };
  }
  if (ews.apiVersion !== API_VERSION) e("ews.kind", `apiVersion must be ${API_VERSION}`);
  if (ews.kind !== "EffectiveWorldState") e("ews.kind", "kind must be EffectiveWorldState");
  for (const p of structureProblems(ews, EFFECTIVE_WORLD_STATE, null)) e(p.rule, `EffectiveWorldState: ${p.msg}`);
  const s = ews.spec;
  if (!isObj(s)) {
    e("ews.shape", "spec must be a mapping");
    return { valid: false, errors };
  }
  for (const k of ["worldRef", "worldView", "stateCompiler"]) if (!isNonEmptyString(s[k])) e("ews.shape", `spec.${k} is required`);
  if (!isUtcTimestamp(get(s, "context", "asOf"))) e("ews.as-of", "spec.context.asOf must be a UTC timestamp YYYY-MM-DDTHH:MM:SSZ");
  const state = s.state;
  if (!isObj(state)) e("ews.shape", "spec.state must be a mapping");
  const unresolved = s.unresolved ?? {};
  if (!isObj(unresolved)) e("ews.shape", "spec.unresolved must be a mapping");
  const missing = s.missing ?? [];
  if (!Array.isArray(missing) || !missing.every((x) => typeof x === "string")) e("ews.shape", "spec.missing must be a list of strings");
  else if (new Set(missing).size !== missing.length) e("ews.shape", "spec.missing has duplicate entries");
  const provenance = s.provenance ?? {};
  const idList = (v: unknown) => Array.isArray(v) && v.every((x) => typeof x === "string");
  if (!isObj(provenance)) e("ews.shape", "spec.provenance must be a mapping");
  else for (const [k, v] of Object.entries(provenance)) {
    // A per-subject field maps subjects to id lists (spec 12.3); its shape is checked against the compiler below.
    if (!idList(v) && !(isObj(v) && Object.values(v).every(idList))) e("ews.shape", `provenance.${k} must be a list of observation ids`);
  }
  const derivation = s.derivation ?? {};
  if (!isObj(derivation)) e("ews.shape", "spec.derivation must be a mapping");
  const structural = new Set(["ews.as-of", "schema.unknown-field", "extension.block"]);
  if (errors.some((x) => !structural.has(x.code)) || !isObj(state) || !isObj(unresolved) || !Array.isArray(missing) || !isObj(provenance) || !isObj(derivation)) {
    return { valid: false, errors };
  }

  // Identity bindings.
  const worldRef = s.worldRef as string;
  if (worldRef !== world.identity) e("ews.world-ref", `spec.worldRef ${worldRef} is not the World's identity ${world.identity}`);
  const sc = s.stateCompiler as string;
  const prefix = `${world.identity}#`;
  if (!sc.startsWith(prefix)) {
    e("ews.world-ref", `spec.stateCompiler must be ${prefix}<compiler path>`);
    return { valid: false, errors };
  }
  const comp = loadCompiler(worldDir, world.manifest, world.identity, sc.slice(prefix.length));
  if (typeof comp === "string") {
    e("ews.state-compiler", comp);
    return { valid: false, errors };
  }
  const wvr = comp.spec.worldViewRef;
  if (s.worldView !== `${prefix}${wvr}`) e("ews.world-view", `spec.worldView must be ${prefix}${String(wvr)} (the compiler's worldViewRef)`);

  comp.fieldProblems.forEach((p) => e(p.rule, p.msg));
  // Field partition (skipped when the compiler has no EWS fields; spec 12.1).
  const hasFields = comp.fields !== null;
  const fieldSet = new Set(comp.fields ?? []);
  const places = new Map<string, string[]>();
  const note = (f: string, where: string) => places.set(f, [...(places.get(f) ?? []), where]);
  Object.keys(state).forEach((f) => note(f, "state"));
  Object.keys(unresolved).forEach((f) => note(f, "unresolved"));
  (missing as string[]).forEach((f) => note(f, "missing"));
  const { perSubject, latent } = outputLists(comp.spec);
  for (const f of comp.fields ?? []) {
    const p = places.get(f) ?? [];
    if (perSubject.includes(f) && p.length === 2 && p.includes("state") && p.includes("unresolved")) continue; // subjects split (spec 12.3)
    if (p.length === 0) e("ews.field-placement", `schema field ${f} appears in none of state/unresolved/missing`);
    else if (p.length > 1) e("ews.field-placement", `schema field ${f} appears in more than one place (${p.join(", ")})`);
  }
  for (const f of (comp.fields ?? []).filter((x) => perSubject.includes(x))) {
    for (const [name, sec] of [["state", state], ["unresolved", unresolved], ["provenance", provenance]] as const) {
      if (f in sec && !isObj(sec[f])) e("ews.per-subject-shape", `per-subject field ${f} in ${name} must be a mapping from subject to value`);
    }
    if (isObj(state[f]) && isObj(unresolved[f])) {
      for (const subject of Object.keys(state[f] as Obj).filter((k) => k in (unresolved[f] as Obj)).sort()) {
        e("ews.per-subject-overlap", `subject ${subject} of ${f} is in both state and unresolved`);
      }
    }
  }
  for (const f of latent) {
    if ((f in state || f in unresolved) && !(f in derivation)) e("ews.derivation", `latent field ${f} has a value but no spec.derivation entry`);
  }
  for (const [f, rec] of Object.entries(derivation)) {
    if (!latent.includes(f)) e("ews.derivation", `${f} is not a latent field of the State Compiler`);
    else if (!isObj(rec) || !["estimate", "aggregate", "classify"].includes(rec.kind as string)) e("ews.derivation", `derivation of ${f} must have kind estimate, aggregate, or classify`);
    else if (!(f in state) && !(f in unresolved)) e("ews.derivation", `derivation for ${f}, which has no value`);
  }
  if (hasFields) for (const f of places.keys()) if (!fieldSet.has(f)) e("ews.field-unknown", `field ${f} is not an EWS field of the compiler`);

  // Unresolved alternatives.
  for (const [f, alts] of Object.entries(unresolved)) {
    const groups: Array<[string | null, unknown]> = perSubject.includes(f) && isObj(alts) ? Object.entries(alts) : [[null, alts]];
    for (const [subject, a] of groups) {
      if (!Array.isArray(a) || new Set(a.map(canon)).size < 2) e("ews.unresolved-alternatives", `unresolved.${f}${subject === null ? "" : ` subject ${subject}`} must retain at least two distinct alternatives`);
    }
  }

  // Provenance.
  const present = new Set([...Object.keys(state), ...Object.keys(unresolved)]);
  for (const k of Object.keys(provenance)) if (!present.has(k)) e("ews.provenance-orphan", `provenance.${k} is not a field in state or unresolved`);
  if (comp.spec.traceRequired === true) {
    for (const f of present) {
      const p = provenance[f];
      // An aggregate over no observations (a count of 0) has an empty provenance list (spec 12.4).
      const emptyOk = isObj(derivation[f]) && (derivation[f] as Obj).kind === "aggregate";
      const traced = (ids: unknown) => Array.isArray(ids) && (ids.length > 0 || emptyOk);
      if (perSubject.includes(f) && isObj(p)) {
        const subjects = new Set([...Object.keys(isObj(state[f]) ? (state[f] as Obj) : {}), ...Object.keys(isObj(unresolved[f]) ? (unresolved[f] as Obj) : {})]);
        for (const subject of [...subjects].sort()) {
          if (!traced(p[subject])) e("ews.provenance-required", `traceRequired: field ${f} subject ${subject} has no provenance`);
        }
      } else if (!traced(p)) e("ews.provenance-required", `traceRequired: field ${f} has no provenance`);
    }
  }
  return { valid: errors.length === 0, errors };
}

// ---------------------------------------------------------------- 12.2 compile

export interface Observation {
  id: string;
  type: string;
  observedAt: string;
  values: Obj;
  subject?: string;
  estimatedBy?: string;
  units?: Record<string, string>;
}

export type CompileResult = { ok: true; ews: Obj } | { ok: false; errors: string[] };

/** Errors are `<rule-id>: <message>` strings. */
export function parseObservationSet(doc: unknown): { observations: Observation[]; errors: string[] } {
  const errors: string[] = [];
  const observations: Observation[] = [];
  const input = (m: string) => errors.push(refusal("ews.input", m));
  if (!isObj(doc)) return { observations, errors: [refusal("ews.input", "ObservationSet must be a mapping")] };
  for (const p of structureProblems(doc, OBSERVATION_SET, null)) errors.push(refusal(p.rule, `ObservationSet: ${p.msg}`));
  if (doc.apiVersion !== undefined && doc.apiVersion !== API_VERSION) input(`ObservationSet apiVersion must be ${API_VERSION}`);
  if (doc.kind !== "ObservationSet") input("kind must be ObservationSet");
  const list = get(doc, "spec", "observations");
  if (!Array.isArray(list)) {
    input("spec.observations must be a list");
    return { observations, errors };
  }
  const ids = new Set<string>();
  list.forEach((o, i) => {
    if (!isObj(o)) return void input(`observations[${i}] must be a mapping`);
    if (!isNonEmptyString(o.id)) input(`observations[${i}] is missing id`);
    else if (ids.has(o.id)) input(`duplicate observation id ${o.id}`);
    else ids.add(o.id);
    if (!isNonEmptyString(o.type)) input(`observations[${i}] is missing type`);
    if (!isUtcTimestamp(o.observedAt)) input(`observations[${i}].observedAt ${JSON.stringify(o.observedAt)} is not a UTC timestamp YYYY-MM-DDTHH:MM:SSZ`);
    if (!isObj(o.values)) input(`observations[${i}] is missing a values mapping`);
    if ("subject" in o && typeof o.subject !== "string") input(`observations[${i}].subject must be a string`);
    if ("estimatedBy" in o && !isNonEmptyString(o.estimatedBy)) input(`observations[${i}].estimatedBy must be a non-empty string`);
    if ("units" in o && !(isObj(o.units) && Object.values(o.units).every((u) => typeof u === "string" && /^[!-~]+$/.test(u)))) input(`observation ${String(o.id)} units must map value keys to UCUM codes`);
    if (errors.length === 0) observations.push(o as unknown as Observation);
  });
  return { observations, errors };
}

function refusal(rule: string, message: string): string {
  return `${rule}: ${message}`;
}

export function compileEws(worldDir: string, compilerPath: string, observationDoc: unknown, asOf: string): CompileResult {
  const world = loadWorld(worldDir);
  if (!world.manifest || !world.identity) return { ok: false, errors: world.problems.map((p) => refusal("ews.state-compiler", p)) };
  if (!isUtcTimestamp(asOf)) return { ok: false, errors: [refusal("ews.input", `asOf ${JSON.stringify(asOf)} is not a UTC timestamp YYYY-MM-DDTHH:MM:SSZ`)] };
  const comp = loadCompiler(worldDir, world.manifest, world.identity, compilerPath);
  if (typeof comp === "string") return { ok: false, errors: [refusal("ews.state-compiler", comp)] };
  if (comp.spec.bindings === undefined) {
    return { ok: false, errors: [refusal("ews.opaque-compiler", `State Compiler ${compilerPath} declares no bindings; it is opaque and cannot be compiled declaratively`)] };
  }
  const bp = [
    ...comp.fieldProblems.map((p) => refusal(p.rule, p.msg)),
    ...outputListProblems(comp.spec, comp.fields).map((p) => refusal(p.rule, p.msg)),
    ...bindingProblems(comp.spec, comp.fields).map((m) => refusal("compiler.binding", m)),
    ...unitProblems(comp.spec, comp.fields).map((p) => refusal(p.rule, p.msg)),
  ];
  if (bp.length) return { ok: false, errors: bp };
  // Spec 12: an unknown field makes the ObservationSet invalid input, so compilation is refused.
  const { observations, errors } = parseObservationSet(observationDoc);
  if (errors.length) return { ok: false, errors };
  const byId = new Map(observations.map((o) => [o.id, o]));
  const { perSubject, latent } = outputLists(comp.spec);
  const bindings = comp.spec.bindings as Record<string, Obj>;
  const order = (a: Observation, b: Observation) => (a.observedAt < b.observedAt ? -1 : a.observedAt > b.observedAt ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const units: Record<string, string> = outputUnits(comp.spec) ?? Object.create(null);
  const candidates = (field: string, src: Obj, estimates: boolean, since?: string, sameUnit = false, counted = false) => {
    const cands = observations
      .filter((o) => o.type === src.from && o.observedAt <= asOf && Object.prototype.hasOwnProperty.call(o.values, src.value as string)
        && ("estimatedBy" in o) === estimates && (since === undefined || o.observedAt > since))
      .sort(order);
    // Spec 12.5: a reported unit must be the field's declared unit; values are never converted.
    const reported = new Set<string>();
    for (const o of cands) {
      const u = isObj(o.units) && Object.prototype.hasOwnProperty.call(o.units, src.value as string) ? (o.units as Record<string, string>)[src.value as string] : undefined;
      if (u === undefined) continue;
      if (field in units && !counted && u !== units[field]) { // a count's unit is not the unit of what it counts
        throw new Error(refusal("ews.input", `observation ${o.id} reports "${String(src.value)}" in "${u}", but "${field}" is declared in "${units[field]}"`));
      }
      reported.add(u);
    }
    if (sameUnit && reported.size > 1) throw new Error(refusal("ews.input", `"${field}" would combine values in different units (${[...reported].sort().join(", ")}); units are not converted`));
    return cands;
  };
  const grouped = (field: string, cands: Observation[]): Map<string | null, Observation[]> => {
    if (!perSubject.includes(field)) return new Map([[null, cands]]);
    const m = new Map<string | null, Observation[]>();
    for (const o of cands) {
      if (typeof o.subject !== "string") throw new Error(refusal("ews.input", `observation ${o.id} has no subject, but "${field}" is a per-subject field`));
      m.set(o.subject, [...(m.get(o.subject) ?? []), o]);
    }
    return m;
  };

  // results.get(field) = subject (or null) -> result; an absent field is missing.
  const results = new Map<string, Map<string | null, Result>>();
  try {
    for (const field of comp.fields ?? []) {
      const b = bindings[field];
      const form = b === undefined ? null : bindingForm(b);
      const out = new Map<string | null, Result>();
      if (form === "observe" || form === "estimate") {
        const src = (form === "observe" ? b : b.estimate) as Obj;
        for (const [k, g] of grouped(field, candidates(field, src, form === "estimate"))) if (g.length) out.set(k, resolve(g, src.value as string, (src.select as string | undefined) ?? "latest"));
      } else if (form === "aggregate") {
        const a = b.aggregate as Obj;
        const since = "window" in a ? shift(asOf, durationSeconds(a.window)!) : undefined;
        for (const [k, g] of grouped(field, candidates(field, a, false, since, ["sum", "mean", "min", "max"].includes(a.function as string), ["count", "distinct_count"].includes(a.function as string)))) {
          const r = aggregate(g, a.value as string, a.function as string);
          if (r) out.set(k, r);
        }
      } else continue;
      if (out.size) results.set(field, out);
    }
  } catch (err) {
    return { ok: false, errors: [(err as Error).message] };
  }
  const pending = (comp.fields ?? []).filter((f) => bindingForm(bindings[f]) === "classify");
  while (pending.length) {
    for (const field of [...pending]) {
      const c = bindings[field].classify as Obj;
      if (pending.includes(c.input as string)) continue;
      pending.splice(pending.indexOf(field), 1);
      const out = new Map<string | null, Result>();
      for (const [k, r] of results.get(c.input as string) ?? []) {
        const labelled = classify(r, c.criterion as Obj);
        if (labelled) out.set(k, labelled);
      }
      if (out.size) results.set(field, out);
    }
  }

  const state: Obj = {};
  const unresolved: Obj = {};
  const provenance: Obj = {};
  const derivation: Obj = {};
  const missing = (comp.fields ?? []).filter((f) => !results.has(f));
  for (const field of comp.fields ?? []) {
    const res = results.get(field);
    if (!res) continue;
    for (const [subject, r] of res) {
      const target = r.placement === "state" ? state : unresolved;
      if (subject === null) {
        target[field] = r.value;
        provenance[field] = r.ids;
      } else {
        ((target[field] ??= {}) as Obj)[subject] = r.value;
        ((provenance[field] ??= {}) as Obj)[subject] = r.ids;
      }
    }
    if (latent.includes(field)) derivation[field] = derive(bindings[field], res, byId);
  }
  const spec: Obj = {
    worldRef: world.identity,
    worldView: `${world.identity}#${String(comp.spec.worldViewRef)}`,
    stateCompiler: `${world.identity}#${compilerPath}`,
    context: { asOf },
    state,
    unresolved,
    missing,
    provenance,
  };
  if (Object.keys(derivation).length) spec.derivation = derivation;
  return { ok: true, ews: { apiVersion: API_VERSION, kind: "EffectiveWorldState", spec } };
}

interface Result {
  placement: "state" | "unresolved";
  value: unknown;
  ids: string[];
}

function distinctValues(values: unknown[]): unknown[] {
  const out: unknown[] = [];
  const seen = new Set<string>();
  for (const v of values) {
    const c = canon(v);
    if (!seen.has(c)) {
      seen.add(c);
      out.push(v);
    }
  }
  return out;
}

const sortedIds = (os: Observation[]) => os.map((o) => o.id).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

/** Spec 12.2 rules 3 and 4 over candidates in (observedAt, id) order. */
function resolve(cands: Observation[], key: string, select: string): Result {
  if (select === "all") return { placement: "state", value: cands.map((o) => o.values[key]), ids: sortedIds(cands) };
  const newest = cands[cands.length - 1].observedAt;
  const tied = cands.filter((o) => o.observedAt === newest);
  const distinct = distinctValues(tied.map((o) => o.values[key]));
  return distinct.length === 1 ? { placement: "state", value: distinct[0], ids: sortedIds(tied) } : { placement: "unresolved", value: distinct, ids: sortedIds(tied) };
}

const isNumber = (v: unknown): v is number => typeof v === "number";

/** Spec 12.4 aggregates; null when the result is missing. */
function aggregate(cands: Observation[], key: string, fn: string): Result | null {
  const values = cands.map((o) => o.values[key]);
  const ids = sortedIds(cands);
  if (fn === "count") return { placement: "state", value: values.length, ids };
  if (fn === "distinct_count") return { placement: "state", value: distinctValues(values).length, ids };
  if (!values.every(isNumber)) throw new Error(refusal("ews.input", `aggregate ${fn} needs numeric values`));
  const nums = values as number[];
  let total = 0;
  for (const v of nums) total += v;
  if (fn === "sum") return { placement: "state", value: total, ids };
  if (nums.length === 0) return null;
  if (fn === "mean") return { placement: "state", value: total / nums.length, ids };
  return { placement: "state", value: fn === "min" ? Math.min(...nums) : Math.max(...nums), ids };
}

function holds(op: string, v: unknown, x: unknown): boolean {
  if (op === "eq") return canon(v) === canon(x);
  if (op === "in") return Array.isArray(x) && x.some((y) => canon(v) === canon(y));
  if (!isNumber(v) || !isNumber(x)) return false;
  return op === "gt" ? v > x : op === "gte" ? v >= x : op === "lt" ? v < x : v <= x;
}

/** The label a criterion gives a value, or undefined when no rule matches and there is no `otherwise`. */
export function classifyValue(criterion: Obj, v: unknown): unknown {
  for (const rule of (criterion.rules as Obj[]) ?? []) {
    if (Object.entries(rule.when as Obj).every(([op, x]) => holds(op, v, x))) return rule.label;
  }
  return criterion.otherwise;
}

function classify(r: Result, criterion: Obj): Result | null {
  const alternatives = r.placement === "state" ? [r.value] : (r.value as unknown[]);
  const labels = distinctValues(alternatives.map((a) => classifyValue(criterion, a)).filter((l) => l !== undefined && l !== null));
  if (labels.length === 0) return null;
  return labels.length === 1 ? { placement: "state", value: labels[0], ids: r.ids } : { placement: "unresolved", value: labels, ids: r.ids };
}

function shift(ts: string, seconds: number): string {
  return new Date(Date.parse(ts) - seconds * 1000).toISOString().replace(".000Z", "Z");
}

/** Spec 12.4 derivation record of one latent field. */
function derive(b: Obj, res: Map<string | null, Result>, byId: Map<string, Observation>): Obj {
  const form = bindingForm(b);
  if (form === "estimate") {
    const by = (ids: string[]) => [...new Set(ids.map((i) => String(byId.get(i)!.estimatedBy)))].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
    if (res.has(null)) return { kind: "estimate", by: by(res.get(null)!.ids) };
    return { kind: "estimate", by: Object.fromEntries([...res].map(([k, r]) => [k, by(r.ids)])) };
  }
  if (form === "aggregate") {
    const a = b.aggregate as Obj;
    return { kind: "aggregate", ...Object.fromEntries(["from", "value", "function", "window"].filter((k) => k in a).map((k) => [k, a[k]])) };
  }
  const c = b.classify as Obj;
  const crit = c.criterion as Obj;
  return { kind: "classify", input: c.input, criterion: Object.fromEntries(["id", "version", "basis"].filter((k) => k in crit).map((k) => [k, crit[k]])) };
}

// ---------------------------------------------------------------- 12.2 equality

export function ewsEqual(a: unknown, b: unknown): { equal: boolean; diffs: string[] } {
  const diffs: string[] = [];
  const sa = (get(a, "spec") ?? {}) as Obj;
  const sb = (get(b, "spec") ?? {}) as Obj;
  for (const k of ["worldRef", "worldView", "stateCompiler"]) if (sa[k] !== sb[k]) diffs.push(`${k}: ${JSON.stringify(sa[k])} != ${JSON.stringify(sb[k])}`);
  if (get(sa, "context", "asOf") !== get(sb, "context", "asOf")) diffs.push("context.asOf differs");
  if (canon(sa.state ?? {}) !== canon(sb.state ?? {})) diffs.push(`state: ${canon(sa.state ?? {})} != ${canon(sb.state ?? {})}`);
  if (canon(sa.unresolved ?? {}) !== canon(sb.unresolved ?? {})) diffs.push(`unresolved: ${canon(sa.unresolved ?? {})} != ${canon(sb.unresolved ?? {})}`);
  const setOf = (v: unknown) => canon([...new Set((Array.isArray(v) ? v : []).map(canon))].sort());
  if (setOf(sa.missing) !== setOf(sb.missing)) diffs.push(`missing: ${canon(sa.missing)} != ${canon(sb.missing)} (as sets)`);
  const pa = (isObj(sa.provenance) ? sa.provenance : {}) as Obj;
  const pb = (isObj(sb.provenance) ? sb.provenance : {}) as Obj;
  const provSets = (v: unknown) => (isObj(v) ? canon(Object.fromEntries(Object.entries(v).map(([s, ids]) => [s, setOf(ids)]))) : setOf(v));
  for (const k of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
    if (provSets(pa[k]) !== provSets(pb[k])) diffs.push(`provenance.${k}: ${canon(pa[k])} != ${canon(pb[k])} (as sets)`);
  }
  if (canon(sa.derivation ?? {}) !== canon(sb.derivation ?? {})) diffs.push(`derivation: ${canon(sa.derivation ?? {})} != ${canon(sb.derivation ?? {})}`);
  return { equal: diffs.length === 0, diffs };
}
