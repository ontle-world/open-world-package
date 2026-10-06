import * as fs from "node:fs";
import { Context, error, hasAssetOfKind, LocalAsset, localAssetsOfKind, Profile, PROFILES, warn } from "../context.js";
import { Problem } from "../structure.js";
import { get, isNonEmptyString, isObj, Obj, packageFile, SEMVER_RE } from "../util.js";
import { localKinds, resolvedInclude } from "./experimental.js";

/**
 * Spec section 6.1: WorldPackage conformance profiles.
 * Each profile check returns its unmet requirements as {rule, msg} (Appendix A rule ids).
 * Profiles are cumulative: the satisfied profile is the highest one whose requirements
 * and all lower requirements are met. Paths are compared as exact strings (spec 3).
 */
interface Failure {
  rule: string;
  msg: string;
}
type ProfileCheck = (ctx: Context, w: WorldInfo) => Failure[];

interface WorldInfo {
  world: Record<string, unknown> | undefined;
  defaultView: unknown;
  defaultStateCompiler: unknown;
  views: LocalAsset[];
  compilers: LocalAsset[];
}

function assetSpec(a: LocalAsset): Record<string, unknown> | undefined {
  const s = get(a.doc, "spec");
  return isObj(s) ? s : undefined;
}

const descriptive: ProfileCheck = (ctx, w) => {
  if (isNonEmptyString(w.world?.definition)) return [];
  return [{ rule: "profile.descriptive", msg: "requires spec.world.definition" }];
};

const viewable: ProfileCheck = (ctx, w) => {
  const out: Failure[] = [];
  const r = "profile.viewable";
  if (!hasAssetOfKind(ctx, "WorldViewProfile")) out.push({ rule: r, msg: "requires at least one WorldViewProfile asset" });
  if (w.defaultView === undefined) {
    out.push({ rule: r, msg: "requires spec.world.defaultView" });
    return out;
  }
  const v = w.views.find((a) => a.rawPath === w.defaultView);
  if (!v) {
    out.push({ rule: r, msg: `spec.world.defaultView ${JSON.stringify(w.defaultView)} is not the path of a local WorldViewProfile asset` });
  } else if (!v.exists || !isObj(v.doc)) {
    out.push({ rule: r, msg: `default WorldViewProfile ${v.rawPath} is missing or unreadable` });
  }
  return out;
};

const stateful: ProfileCheck = (ctx, w) => {
  const out: Failure[] = [];
  const r = "profile.stateful";
  const viewPaths = new Set(w.views.filter((a) => a.exists).map((a) => a.rawPath));
  if (!hasAssetOfKind(ctx, "StateCompilerProfile")) out.push({ rule: r, msg: "requires at least one StateCompilerProfile asset" });
  if (w.defaultStateCompiler === undefined) {
    out.push({ rule: r, msg: "requires spec.world.defaultStateCompiler" });
  } else {
    const c = w.compilers.find((a) => a.rawPath === w.defaultStateCompiler);
    if (!c) {
      out.push({ rule: r, msg: `spec.world.defaultStateCompiler ${JSON.stringify(w.defaultStateCompiler)} is not the path of a local StateCompilerProfile asset` });
    } else if (!c.exists || !isObj(c.doc)) {
      out.push({ rule: r, msg: `default StateCompilerProfile ${c.rawPath} is missing or unreadable` });
    } else if (assetSpec(c)?.worldViewRef !== w.defaultView) {
      out.push({ rule: "profile.stateful.default-compiler-view", msg: `default StateCompilerProfile ${c.rawPath} spec.worldViewRef must equal spec.world.defaultView` });
    }
  }
  for (const c of w.compilers) {
    if (!c.exists || !isObj(c.doc)) {
      out.push({ rule: r, msg: `StateCompilerProfile ${c.rawPath} is missing or unreadable` });
      continue;
    }
    const s = assetSpec(c);
    const ref = s?.worldViewRef;
    if (typeof ref !== "string" || !viewPaths.has(ref)) {
      out.push({ rule: "profile.stateful.compiler-view", msg: `StateCompilerProfile ${c.rawPath} spec.worldViewRef ${JSON.stringify(ref)} does not name a local WorldViewProfile` });
    }
    if (s?.outputContract !== "EffectiveWorldState") {
      out.push({ rule: "profile.stateful.output-contract", msg: `StateCompilerProfile ${c.rawPath} must declare spec.outputContract: EffectiveWorldState` });
    }
    // Spec 6.1 (round 3): malformed bindings fail stateful for declared and satisfied profile.
    for (const p of outputListProblems(s, compilerFields(ctx, c).fields)) out.push({ rule: p.rule, msg: `StateCompilerProfile ${c.rawPath}: ${p.msg}` });
    for (const m of bindingProblems(s, compilerFields(ctx, c).fields)) out.push({ rule: "compiler.binding", msg: `StateCompilerProfile ${c.rawPath}: ${m}` });
    for (const p of unitProblems(s, compilerFields(ctx, c).fields)) out.push({ rule: p.rule, msg: `StateCompilerProfile ${c.rawPath}: ${p.msg}` });
  }
  return out;
};

const modelReady: ProfileCheck = (ctx, w) => {
  const out: Failure[] = [];
  for (const c of w.compilers) {
    if (!c.exists || !isObj(c.doc)) continue; // reported at stateful
    const fields = compilerFields(ctx, c).fields;
    if (!fields || fields.length === 0) {
      out.push({ rule: "profile.model-ready.output-schema", msg: `StateCompilerProfile ${c.rawPath} must declare a non-empty spec.outputSchema.fields or a resolvable spec.outputSchemaRef` });
    }
  }
  return out;
};

const actionReady: ProfileCheck = (ctx) =>
  ["ActionBindingProfile", "CommitContract", "EffectVerificationProfile"]
    .filter((k) => !hasAssetOfKind(ctx, k))
    .map((k) => ({ rule: "profile.action-ready", msg: `requires a ${k} asset` }));

/** Ordered with PROFILES. Extend here when new profiles are added. */
const PROFILE_CHECKS: Record<Profile, ProfileCheck> = {
  descriptive,
  viewable,
  stateful,
  "model-ready": modelReady,
  "action-ready": actionReady,
};

export function checkWorldPackage(ctx: Context): void {
  const spec = isObj(ctx.manifest.spec) ? ctx.manifest.spec : undefined;
  const world = spec?.world;
  if (!isObj(world)) error(ctx, "world.spec", "WorldPackage requires a spec.world mapping", "owp.yaml");
  const w: WorldInfo = {
    world: isObj(world) ? world : undefined,
    defaultView: isObj(world) ? world.defaultView : undefined,
    defaultStateCompiler: isObj(world) ? world.defaultStateCompiler : undefined,
    views: localAssetsOfKind(ctx, "WorldViewProfile"),
    compilers: localAssetsOfKind(ctx, "StateCompilerProfile"),
  };

  let declared: Profile = "descriptive";
  const conf = spec?.conformance;
  if (conf !== undefined) {
    if (!isObj(conf)) {
      error(ctx, "profile.unknown", "spec.conformance must be a mapping with a defined profile", "owp.yaml");
    } else if (conf.profile !== undefined) {
      if ((PROFILES as readonly unknown[]).includes(conf.profile)) declared = conf.profile as Profile;
      else error(ctx, "profile.unknown", `spec.conformance.profile must be one of ${PROFILES.join(", ")} (got ${JSON.stringify(conf.profile)})`, "owp.yaml");
    }
  }
  ctx.declaredProfile = declared;

  let satisfied: Profile | null = null;
  const failures: Record<string, Failure[]> = {};
  let chainIntact = true;
  for (const p of PROFILES) {
    const f = PROFILE_CHECKS[p](ctx, w);
    failures[p] = f;
    if (chainIntact && f.length === 0) satisfied = p;
    else chainIntact = false;
  }
  ctx.satisfiedProfile = satisfied;

  const declaredIdx = PROFILES.indexOf(declared);
  for (let i = 0; i <= declaredIdx; i++) {
    for (const f of failures[PROFILES[i]]) error(ctx, f.rule, `declared profile "${declared}" not satisfied: ${f.msg}`, "owp.yaml");
  }

  if (isObj(world) && !isNonEmptyString(world.definition) && !isNonEmptyString(world.description)) {
    warn(ctx, "world.undescribed", "spec.world has neither definition nor description", "owp.yaml");
  }
}

/**
 * Spec 12.1: a State Compiler's EWS fields are spec.outputSchema.fields, or the top-level
 * `properties` keys of the package-relative JSON Schema named by spec.outputSchemaRef.
 * `fields` is null when the compiler declares no field list.
 */
type SchemaFields = { fields: string[] | null; problems: Problem[] };

/** EWS fields of a local State Compiler asset, resolved once per validation and kept on ctx. */
export function compilerFields(ctx: Context, a: LocalAsset): SchemaFields {
  ctx.ewsFields ??= new Map();
  let r = ctx.ewsFields.get(a.rawPath);
  if (!r) {
    const spec = isObj(a.doc) && isObj(a.doc.spec) ? a.doc.spec : undefined;
    ctx.ewsFields.set(a.rawPath, (r = outputSchemaFields(ctx.root, spec, a.rawPath)));
  }
  return r;
}

export function outputSchemaFields(root: string, spec: Obj | undefined, file: string): SchemaFields {
  const declared = get(spec, "outputSchema", "fields");
  const fields = Array.isArray(declared) ? declared.filter((f): f is string => typeof f === "string") : null;
  const ref = spec?.outputSchemaRef;
  if (ref === undefined || ref === null) return { fields, problems: [] }; // null counts as absent
  const bad = (msg: string) => ({ fields, problems: [{ rule: "compiler.output-schema-ref", msg: `StateCompilerProfile ${file} spec.outputSchemaRef ${msg}` }] });
  if (typeof ref !== "string" || ref === "" || ref.startsWith("./") || ref.startsWith("/") || ref.includes("\\")) {
    return bad(`${JSON.stringify(ref)} must be a relative POSIX path without a leading './'`);
  }
  const abs = packageFile(root, ref);
  if (abs === null) return bad(`${JSON.stringify(ref)} does not name a file in the package`);
  let doc: unknown;
  try {
    // fatal: invalid UTF-8 is an error, not U+FFFD (spec 12.1: a UTF-8 JSON document)
    doc = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(fs.readFileSync(abs)));
  } catch (e) {
    return bad(`${JSON.stringify(ref)} is not a readable JSON document: ${(e as Error).message}`);
  }
  const props = get(doc, "properties");
  if (!isObj(props) || Object.keys(props).length === 0) return bad(`${JSON.stringify(ref)} must be a JSON Schema with a non-empty top-level properties object`);
  const listed = Object.keys(props);
  if (fields !== null && (new Set(fields).size !== listed.length || !listed.every((f) => fields.includes(f)))) {
    return { fields, problems: [{ rule: "compiler.output-schema-mismatch", msg: `StateCompilerProfile ${file} spec.outputSchema.fields and the properties of ${JSON.stringify(ref)} list different fields` }] };
  }
  // Both declared and equal: outputSchema.fields, in its order, is used (spec 12.1).
  return { fields: fields ?? listed, problems: [] };
}

/** Spec 12.1: every local State Compiler's outputSchemaRef resolves, whatever the package kind or profile. */
export function checkCompilerSchemas(ctx: Context): void {
  for (const c of localAssetsOfKind(ctx, "StateCompilerProfile")) {
    if (!isObj(c.doc)) continue;
    for (const p of compilerFields(ctx, c).problems) error(ctx, p.rule, p.msg, c.rawPath);
  }
}

/** Spec 12.2: binding keys are EWS fields of the compiler; from/value strings; select latest|all. */
export const AGGREGATE_FUNCTIONS = ["count", "distinct_count", "sum", "mean", "min", "max"];
export const CONDITIONS = ["eq", "in", "gt", "gte", "lt", "lte"];
export const SELECTORS = ["latest", "all"];
const DURATION_RE = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/;

/** Spec 12.4: aggregate.where maps a values key to conditions, the same conditions a classify rule uses. */
function whereProblems(key: string, w: unknown): string[] {
  if (!isObj(w) || Object.keys(w).length === 0) return [`binding "${key}" aggregate.where must be a non-empty mapping from a values key to conditions`];
  const out: string[] = [];
  for (const [k, cond] of Object.entries(w)) {
    if (k === "") out.push(`binding "${key}" aggregate.where keys must be non-empty strings`);
    else if (!isObj(cond) || Object.keys(cond).length === 0 || !Object.keys(cond).every((c) => CONDITIONS.includes(c))) {
      out.push(`binding "${key}" aggregate.where.${k} needs one or more of ${CONDITIONS.join(", ")}`);
    } else if ("in" in cond && !Array.isArray(cond.in)) out.push(`binding "${key}" aggregate.where.${k}.in must be a list`);
  }
  return out;
}

/** Seconds in an ISO 8601 duration of days, hours, minutes, and seconds (spec 12.4); null if malformed. */
export function durationSeconds(v: unknown): number | null {
  if (typeof v !== "string" || v === "P" || v === "PT" || v.endsWith("T")) return null;
  const m = DURATION_RE.exec(v);
  if (!m) return null;
  const [d, h, mi, s] = m.slice(1).map((x) => (x ? Number(x) : 0));
  return ((d * 24 + h) * 60 + mi) * 60 + s;
}

/** `outputSchema.perSubject` and `outputSchema.latent` (spec 12.3, 12.4); malformed lists count as empty. */
export function outputLists(spec: Record<string, unknown> | undefined): { perSubject: string[]; latent: string[] } {
  const schema = isObj(spec?.outputSchema) ? (spec!.outputSchema as Obj) : {};
  const list = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  return { perSubject: list(schema.perSubject), latent: list(schema.latent) };
}

/** observe, estimate, aggregate, or classify; null when the binding has none or several forms. */
export function bindingForm(b: unknown): "observe" | "estimate" | "aggregate" | "classify" | null {
  if (!isObj(b)) return null;
  const forms = (["estimate", "aggregate", "classify"] as const).filter((k) => k in b);
  if (forms.length) return forms.length === 1 && Object.keys(b).length === 1 ? forms[0] : null;
  return "observe";
}

/** Spec 12.3/12.4: perSubject and latent name EWS fields of the compiler. */
export function outputListProblems(spec: Record<string, unknown> | undefined, ewsFields: string[] | null): Problem[] {
  const out: Problem[] = [];
  const schema = isObj(spec?.outputSchema) ? (spec!.outputSchema as Obj) : {};
  const unknown = ewsFields === null && spec?.outputSchemaRef !== undefined && spec?.outputSchemaRef !== null;
  for (const [key, rule] of [["perSubject", "compiler.per-subject-field"], ["latent", "compiler.latent-field"]] as const) {
    if (!(key in schema)) continue;
    const v = schema[key];
    if (!Array.isArray(v) || !v.every((x) => typeof x === "string")) {
      out.push({ rule, msg: `spec.outputSchema.${key} must be a list of EWS field names` });
      continue;
    }
    if (!unknown) for (const n of v) if (!(ewsFields ?? []).includes(n)) out.push({ rule, msg: `spec.outputSchema.${key} names "${n}", which is not one of its EWS fields` });
  }
  return out;
}

export const UCUM_CODE_RE = /^[!-~]+$/; // a UCUM code: printable ASCII without spaces (compared as text, never converted)

/** spec.outputSchema.units (spec 12.5): EWS field -> UCUM code; {} when absent, null when malformed. */
export function outputUnits(spec: Record<string, unknown> | undefined): Record<string, string> | null {
  const schema = isObj(spec?.outputSchema) ? (spec!.outputSchema as Obj) : {};
  const u = schema.units ?? {};
  if (!isObj(u) || !Object.values(u).every((v) => typeof v === "string" && UCUM_CODE_RE.test(v))) return null;
  return Object.assign(Object.create(null), u) as Record<string, string>; // no prototype: a field named "toString" is not a unit
}

/** UCUM unity: `1`, or an annotation only, such as `{alarm}`. */
export const dimensionless = (unit: string): boolean => unit === "1" || /^\{[^{}]*\}$/.test(unit);

/** Spec 12.5: declared units name EWS fields; counts are dimensionless; labels have none; a criterion's unit is its input's. */
export function unitProblems(spec: Record<string, unknown> | undefined, ewsFields: string[] | null): Problem[] {
  const out: Problem[] = [];
  const schema = isObj(spec?.outputSchema) ? (spec!.outputSchema as Obj) : {};
  const unknown = ewsFields === null && spec?.outputSchemaRef !== undefined && spec?.outputSchemaRef !== null;
  const declared = outputUnits(spec);
  if ("units" in schema && declared === null) {
    out.push({ rule: "compiler.unit", msg: "spec.outputSchema.units must map EWS fields to UCUM codes (printable ASCII, no spaces)" });
  }
  const units: Record<string, string> = declared ?? Object.create(null);
  if (!unknown) for (const k of Object.keys(units)) if (!(ewsFields ?? []).includes(k)) out.push({ rule: "compiler.unit", msg: `spec.outputSchema.units names "${k}", which is not one of its EWS fields` });
  const bindings = isObj(spec?.bindings) ? (spec!.bindings as Obj) : {};
  for (const [field, b] of Object.entries(bindings)) {
    const form = bindingForm(b);
    if (form === "aggregate") {
      const fn = isObj((b as Obj).aggregate) ? ((b as Obj).aggregate as Obj).function : undefined;
      if ((fn === "count" || fn === "distinct_count") && field in units && !dimensionless(units[field])) {
        out.push({ rule: "compiler.unit", msg: `field "${field}" is a ${fn}, so its unit must be dimensionless (1 or an annotation such as {alarm}), not "${units[field]}"` });
      }
    } else if (form === "classify") {
      const c = isObj((b as Obj).classify) ? ((b as Obj).classify as Obj) : {};
      const crit = isObj(c.criterion) ? c.criterion : {};
      if (field in units) out.push({ rule: "compiler.unit", msg: `field "${field}" is a classification; a label has no unit` });
      const inputUnit = typeof c.input === "string" ? units[c.input] : undefined;
      if (crit.unit !== undefined && crit.unit !== null && crit.unit !== inputUnit) {
        out.push({ rule: "compiler.unit", msg: `binding "${field}" criterion.unit ${JSON.stringify(crit.unit)} must equal the unit of its input ${JSON.stringify(c.input)} (${JSON.stringify(inputUnit ?? null)})` });
      }
    }
  }
  return out;
}

export function bindingProblems(spec: Record<string, unknown> | undefined, ewsFields: string[] | null): string[] {
  const out: string[] = [];
  if (!spec || spec.bindings === undefined) return out;
  const b = spec.bindings;
  if (!isObj(b)) return ["spec.bindings must be a mapping"];
  const fields = new Set(ewsFields ?? []);
  // An outputSchemaRef that does not resolve is already an error; its fields are unknown, so keys are not checked.
  const unknown = ewsFields === null && spec.outputSchemaRef !== undefined && spec.outputSchemaRef !== null;
  const { perSubject, latent } = outputLists(spec);
  const source = (key: string, v: unknown) => {
    if (!isObj(v) || typeof v.from !== "string" || typeof v.value !== "string") out.push(`binding "${key}" must declare string from and value`);
  };
  for (const [key, v] of Object.entries(b)) {
    if (!unknown && !fields.has(key)) out.push(`binding "${key}" is not an EWS field of the compiler`);
    const form = bindingForm(v);
    if (form === null) {
      out.push(`binding "${key}" must be an observation binding or exactly one of estimate, aggregate, classify`);
      continue;
    }
    if (form !== "observe" && !latent.includes(key)) out.push(`binding "${key}" is a ${form} binding, so the field must be listed in spec.outputSchema.latent`);
    if (form === "observe" && latent.includes(key)) out.push(`binding "${key}": a latent field needs an estimate, aggregate, or classify binding`);
    const vv = v as Obj;
    if (form === "observe" || form === "estimate") {
      const inner = form === "observe" ? vv : vv.estimate;
      source(key, inner);
      if (isObj(inner) && inner.select !== undefined && !SELECTORS.includes(inner.select as string)) {
        out.push(`binding "${key}".select must be "latest" or "all" (got ${JSON.stringify(inner.select)})`);
      }
    } else if (form === "aggregate") {
      const a = vv.aggregate;
      source(key, a);
      if (isObj(a)) {
        if (!AGGREGATE_FUNCTIONS.includes(a.function as string)) out.push(`binding "${key}" aggregate.function must be one of ${AGGREGATE_FUNCTIONS.join(", ")}`);
        if ("window" in a && durationSeconds(a.window) === null) out.push(`binding "${key}" aggregate.window must be an ISO 8601 duration such as PT24H or P7D`);
        if ("where" in a) out.push(...whereProblems(key, a.where));
      }
    } else {
      out.push(...classifyProblems(key, vv.classify, ewsFields, perSubject, unknown));
    }
  }
  // Classification inputs must not form a cycle.
  const graph = new Map<string, unknown>();
  for (const [k, v] of Object.entries(b)) if (bindingForm(v) === "classify" && isObj((v as Obj).classify)) graph.set(k, ((v as Obj).classify as Obj).input);
  for (const start of graph.keys()) {
    const seen = new Set<string>();
    let cur: unknown = start;
    while (typeof cur === "string" && graph.has(cur) && !seen.has(cur)) {
      seen.add(cur);
      cur = graph.get(cur);
    }
    if (cur === start) out.push(`classification inputs form a cycle through "${start}"`);
  }
  return out;
}

function classifyProblems(key: string, c: unknown, ewsFields: string[] | null, perSubject: string[], unknown: boolean): string[] {
  if (!isObj(c) || typeof c.input !== "string") return [`binding "${key}" classify.input must name an EWS field`];
  const out: string[] = [];
  const input = c.input;
  if (input === key || (!unknown && !(ewsFields ?? []).includes(input))) out.push(`binding "${key}" classify.input "${input}" must be another EWS field of the compiler`);
  if (perSubject.includes(key) !== perSubject.includes(input)) out.push(`binding "${key}" is per-subject exactly when its input "${input}" is`);
  const crit = c.criterion;
  if (!isObj(crit) || typeof crit.id !== "string" || crit.id === "") return [...out, `binding "${key}" classify.criterion must be a mapping with an id`];
  if ("version" in crit && !(typeof crit.version === "string" && SEMVER_RE.test(crit.version))) out.push(`binding "${key}" classify.criterion.version must be SemVer`);
  if ("basis" in crit && typeof crit.basis !== "string") out.push(`binding "${key}" classify.criterion.basis must be a string`);
  const rules = crit.rules;
  if (!Array.isArray(rules) || rules.length === 0) return [...out, `binding "${key}" classify.criterion.rules must be a non-empty list`];
  rules.forEach((r, i) => {
    const when = isObj(r) ? r.when : undefined;
    if (!isObj(when) || Object.keys(when).length === 0 || !Object.keys(when).every((k) => CONDITIONS.includes(k)) || !("label" in (r as Obj))) {
      out.push(`binding "${key}" classify.criterion.rules[${i}] needs when (one or more of ${CONDITIONS.join(", ")}) and label`);
    } else if ("in" in when && !Array.isArray(when.in)) out.push(`binding "${key}" classify.criterion.rules[${i}].when.in must be a list`);
  });
  return out;
}

/**
 * Spec section 6: a View selects from the World's boundary, and a State Compiler's fields name entities its
 * View selects. Warnings: `view.outside-world` when spec.world.boundary.included is declared, and
 * `compiler.field-outside-view` for a field `<entity>.<property>` whose entity the View does not include.
 */
export function checkContainment(ctx: Context): void {
  const included = get(ctx.manifest, "spec", "world", "boundary", "included");
  const boundary = new Set(Array.isArray(included) ? included.filter((x): x is string => typeof x === "string") : []);
  const kinds = localKinds(ctx);
  const docs = new Map<string, unknown>();
  for (const a of ctx.localAssets) if (!docs.has(a.rawPath)) docs.set(a.rawPath, a.doc);
  const includes = new Map<string, Set<string>>();
  for (const [p, k] of [...kinds].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))) {
    if (k !== "WorldViewProfile") continue;
    const all = resolvedInclude(p, docs, kinds);
    const own = all.filter((x) => !x.includes("#"));
    // A compiler field may describe an entity of an external World the View selects.
    includes.set(p, new Set([...own, ...all.filter((x) => x.includes("#")).map((x) => x.slice(x.indexOf("#") + 1))]));
    if (boundary.size === 0) continue;
    for (const name of [...own].sort()) {
      if (!boundary.has(name)) warn(ctx, "view.outside-world", `${p}: projection.include "${name}" is not in spec.world.boundary.included`, p);
    }
  }
  for (const c of localAssetsOfKind(ctx, "StateCompilerProfile")) {
    const view = get(c.doc, "spec", "worldViewRef");
    const names = typeof view === "string" ? includes.get(view) : undefined;
    if (!names || names.size === 0) continue;
    for (const field of compilerFields(ctx, c).fields ?? []) {
      const dot = field.indexOf(".");
      if (dot > 0 && !names.has(field.slice(0, dot))) {
        warn(ctx, "compiler.field-outside-view", `${c.rawPath}: field "${field}" names "${field.slice(0, dot)}", which ${view}'s projection.include does not list`, c.rawPath);
      }
    }
  }
}

/** Spec 6: a World View belongs to the WorldPackage that contains it (`view.world-ref`). */
export function checkViewOwnership(ctx: Context): void {
  const views = [...localAssetsOfKind(ctx, "WorldViewProfile")].sort((a, b) => (a.rawPath < b.rawPath ? -1 : a.rawPath > b.rawPath ? 1 : 0));
  for (const v of views) {
    if (ctx.packageKind !== "WorldPackage") {
      error(ctx, "view.world-ref", `${v.rawPath}: a WorldViewProfile belongs to a WorldPackage, not a ${ctx.packageKind}`, v.rawPath);
      continue;
    }
    // Other Worlds the View reads are named in spec.externalWorldRefs and listed in spec.dependencies.
    const refs = get(v.doc, "spec", "externalWorldRefs");
    if (refs !== undefined && refs !== null && !(Array.isArray(refs) && refs.every((r) => typeof r === "string"))) {
      error(ctx, "view.external-world", `${v.rawPath}: spec.externalWorldRefs must be a list of package references`, v.rawPath);
      continue;
    }
    const declared = new Set((refs ?? []) as string[]);
    const depsRaw = get(ctx.manifest, "spec", "dependencies");
    const deps = new Set((Array.isArray(depsRaw) ? depsRaw : []).map((d) => (isObj(d) ? d.ref : d)));
    for (const r of declared) {
      if (!deps.has(r)) error(ctx, "view.external-world", `${v.rawPath}: external World ${r} must also be listed in spec.dependencies`, v.rawPath);
    }
    for (const [r, name] of viewExternalNames(v.doc)) {
      if (!declared.has(r)) error(ctx, "view.external-world", `${v.rawPath}: projection.include '${r}#${name}' names a World that spec.externalWorldRefs does not list`, v.rawPath);
    }
  }
}

/** [world ref, name] for each projection.include entry written as <world ref>#<name>. */
export function viewExternalNames(doc: unknown): Array<[string, string]> {
  const include = get(doc, "spec", "projection", "include");
  if (!Array.isArray(include)) return [];
  return include
    .filter((x): x is string => typeof x === "string" && x.includes("#"))
    .map((x) => [x.slice(0, x.indexOf("#")), x.slice(x.indexOf("#") + 1)]);
}
