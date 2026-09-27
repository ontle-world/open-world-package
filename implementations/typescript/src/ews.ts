/**
 * Spec section 12: Effective World State documents.
 *  - checkEws:   12.1 output contract against a World's State Compiler
 *  - compileEws: 12.2 declarative bindings over an ObservationSet at asOf
 *  - ewsEqual:   12.2 equality
 */
import * as path from "node:path";
import { Issue } from "./context.js";
import { get, isNonEmptyString, isObj, loadYamlFile, Obj } from "./util.js";
import { API_VERSION } from "./vocab.js";
import { bindingProblems } from "./rules/world.js";

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
  fields: string[];
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
  const assets = get(manifest, "spec", "assets");
  const listed = Array.isArray(assets) && assets.some((a) => isObj(a) && a.kind === "StateCompilerProfile" && a.path === compilerPath);
  if (!listed) return `${compilerPath} is not a local StateCompilerProfile asset of ${identity}`;
  const l = loadYamlFile(path.join(worldDir, compilerPath));
  if (!l.ok || !isObj(l.value)) return `cannot read State Compiler ${compilerPath}`;
  const spec = get(l.value, "spec");
  if (!isObj(spec)) return `State Compiler ${compilerPath} has no spec`;
  const f = get(spec, "outputSchema", "fields");
  const fields = Array.isArray(f) ? f.filter((x): x is string => typeof x === "string") : [];
  return { identity, compilerPath, spec, fields };
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
  if (!isObj(provenance)) e("ews.shape", "spec.provenance must be a mapping");
  else for (const [k, v] of Object.entries(provenance)) {
    if (!Array.isArray(v) || !v.every((x) => typeof x === "string")) e("ews.shape", `provenance.${k} must be a list of observation ids`);
  }
  if (errors.some((x) => x.code !== "ews.as-of") || !isObj(state) || !isObj(unresolved) || !Array.isArray(missing) || !isObj(provenance)) {
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

  // Field partition (skipped when the compiler has no outputSchema.fields; spec 12.1 round 3).
  const hasFields = Array.isArray(get(comp.spec, "outputSchema", "fields"));
  const fieldSet = new Set(comp.fields);
  const places = new Map<string, string[]>();
  const note = (f: string, where: string) => places.set(f, [...(places.get(f) ?? []), where]);
  Object.keys(state).forEach((f) => note(f, "state"));
  Object.keys(unresolved).forEach((f) => note(f, "unresolved"));
  (missing as string[]).forEach((f) => note(f, "missing"));
  for (const f of hasFields ? comp.fields : []) {
    const p = places.get(f) ?? [];
    if (p.length === 0) e("ews.field-placement", `schema field ${f} appears in none of state/unresolved/missing`);
    else if (p.length > 1) e("ews.field-placement", `schema field ${f} appears in more than one place (${p.join(", ")})`);
  }
  if (hasFields) for (const f of places.keys()) if (!fieldSet.has(f)) e("ews.field-unknown", `field ${f} is not in the compiler's outputSchema.fields`);

  // Unresolved alternatives.
  for (const [f, alts] of Object.entries(unresolved)) {
    if (!Array.isArray(alts) || new Set(alts.map(canon)).size < 2) e("ews.unresolved-alternatives", `unresolved.${f} must retain at least two distinct alternatives`);
  }

  // Provenance.
  const present = new Set([...Object.keys(state), ...Object.keys(unresolved)]);
  for (const k of Object.keys(provenance)) if (!present.has(k)) e("ews.provenance-orphan", `provenance.${k} is not a field in state or unresolved`);
  if (comp.spec.traceRequired === true) {
    for (const f of present) {
      const p = provenance[f];
      if (!Array.isArray(p) || p.length === 0) e("ews.provenance-required", `traceRequired: field ${f} has no provenance`);
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
}

export type CompileResult = { ok: true; ews: Obj } | { ok: false; errors: string[] };

export function parseObservationSet(doc: unknown): { observations: Observation[]; errors: string[] } {
  const errors: string[] = [];
  const observations: Observation[] = [];
  if (!isObj(doc)) return { observations, errors: ["ObservationSet must be a mapping"] };
  if (doc.apiVersion !== undefined && doc.apiVersion !== API_VERSION) errors.push(`ObservationSet apiVersion must be ${API_VERSION}`);
  if (doc.kind !== "ObservationSet") errors.push("kind must be ObservationSet");
  const list = get(doc, "spec", "observations");
  if (!Array.isArray(list)) return { observations, errors: [...errors, "spec.observations must be a list"] };
  const ids = new Set<string>();
  list.forEach((o, i) => {
    if (!isObj(o)) return errors.push(`observations[${i}] must be a mapping`);
    if (!isNonEmptyString(o.id)) errors.push(`observations[${i}] is missing id`);
    else if (ids.has(o.id)) errors.push(`duplicate observation id ${o.id}`);
    else ids.add(o.id);
    if (!isNonEmptyString(o.type)) errors.push(`observations[${i}] is missing type`);
    if (!isUtcTimestamp(o.observedAt)) errors.push(`observations[${i}].observedAt ${JSON.stringify(o.observedAt)} is not a UTC timestamp YYYY-MM-DDTHH:MM:SSZ`);
    if (!isObj(o.values)) errors.push(`observations[${i}] is missing a values mapping`);
    if (errors.length === 0) observations.push(o as unknown as Observation);
  });
  return { observations, errors };
}

export function compileEws(worldDir: string, compilerPath: string, observationDoc: unknown, asOf: string): CompileResult {
  const world = loadWorld(worldDir);
  if (!world.manifest || !world.identity) return { ok: false, errors: world.problems.map((p) => `ews.state-compiler: ${p}`) };
  if (!isUtcTimestamp(asOf)) return { ok: false, errors: [`ews.input: asOf ${JSON.stringify(asOf)} is not a UTC timestamp YYYY-MM-DDTHH:MM:SSZ`] };
  const comp = loadCompiler(worldDir, world.manifest, world.identity, compilerPath);
  if (typeof comp === "string") return { ok: false, errors: [`ews.state-compiler: ${comp}`] };
  if (comp.spec.bindings === undefined) return { ok: false, errors: [`ews.opaque-compiler: State Compiler ${compilerPath} declares no bindings; it is opaque and cannot be compiled declaratively`] };
  const bp = bindingProblems(comp.spec);
  if (bp.length) return { ok: false, errors: bp.map((m) => `compiler.binding: ${m}`) };
  const { observations, errors } = parseObservationSet(observationDoc);
  if (errors.length) return { ok: false, errors: errors.map((m) => `ews.input: ${m}`) };

  const bindings = comp.spec.bindings as Record<string, Obj>;
  const state: Obj = {};
  const unresolved: Obj = {};
  const missing: string[] = [];
  const provenance: Record<string, string[]> = {};

  for (const field of comp.fields) {
    const b = bindings[field];
    if (!b) {
      missing.push(field);
      continue;
    }
    const from = b.from as string;
    const key = b.value as string;
    const select = (b.select as string | undefined) ?? "latest";
    const cands = observations
      .filter((o) => o.type === from && o.observedAt <= asOf && Object.prototype.hasOwnProperty.call(o.values, key))
      .sort((a, b2) => (a.observedAt < b2.observedAt ? -1 : a.observedAt > b2.observedAt ? 1 : a.id < b2.id ? -1 : a.id > b2.id ? 1 : 0));
    if (cands.length === 0) {
      missing.push(field);
      continue;
    }
    if (select === "all") {
      state[field] = cands.map((o) => o.values[key]);
      provenance[field] = cands.map((o) => o.id);
      continue;
    }
    const newest = cands[cands.length - 1].observedAt;
    const top = cands.filter((o) => o.observedAt === newest);
    const distinct: unknown[] = [];
    const seen = new Set<string>();
    for (const o of top) {
      const c = canon(o.values[key]);
      if (!seen.has(c)) {
        seen.add(c);
        distinct.push(o.values[key]);
      }
    }
    if (distinct.length === 1) state[field] = distinct[0];
    else unresolved[field] = distinct;
    provenance[field] = top.map((o) => o.id);
  }

  return {
    ok: true,
    ews: {
      apiVersion: API_VERSION,
      kind: "EffectiveWorldState",
      spec: {
        worldRef: world.identity,
        worldView: `${world.identity}#${String(comp.spec.worldViewRef)}`,
        stateCompiler: `${world.identity}#${compilerPath}`,
        context: { asOf },
        state,
        unresolved,
        missing,
        provenance,
      },
    },
  };
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
  for (const k of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
    if (setOf(pa[k]) !== setOf(pb[k])) diffs.push(`provenance.${k}: ${canon(pa[k])} != ${canon(pb[k])} (as sets)`);
  }
  return { equal: diffs.length === 0, diffs };
}
