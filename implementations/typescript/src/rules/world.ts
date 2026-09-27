import { Context, error, hasAssetOfKind, LocalAsset, localAssetsOfKind, Profile, PROFILES, warn } from "../context.js";
import { get, isNonEmptyString, isObj } from "../util.js";

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
  if (hasAssetOfKind(ctx, "WorldDefinition")) return [];
  return [{ rule: "profile.descriptive", msg: "requires spec.world.definition or a WorldDefinition asset" }];
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
  } else {
    const ref = assetSpec(v)?.worldRef;
    if (ref !== "self" && ref !== ctx.rawIdentity) {
      out.push({ rule: "profile.viewable.world-ref", msg: `default WorldViewProfile ${v.rawPath} spec.worldRef ${JSON.stringify(ref)} must be "self" or ${ctx.rawIdentity ?? "the package identity"}` });
    }
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
    for (const m of bindingProblems(s)) out.push({ rule: "compiler.binding", msg: `StateCompilerProfile ${c.rawPath}: ${m}` });
  }
  return out;
};

const modelReady: ProfileCheck = (_ctx, w) => {
  const out: Failure[] = [];
  for (const c of w.compilers) {
    if (!c.exists || !isObj(c.doc)) continue; // reported at stateful
    const s = assetSpec(c);
    const fields = get(s, "outputSchema", "fields");
    const hasFields = Array.isArray(fields) && fields.length > 0;
    if (!hasFields && !isNonEmptyString(s?.outputSchemaRef)) {
      out.push({ rule: "profile.model-ready.output-schema", msg: `StateCompilerProfile ${c.rawPath} must declare a non-empty spec.outputSchema.fields or spec.outputSchemaRef` });
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

/** Spec 12.2: binding keys are outputSchema fields; from/value strings; select latest|all. */
export function bindingProblems(spec: Record<string, unknown> | undefined): string[] {
  const out: string[] = [];
  if (!spec || spec.bindings === undefined) return out;
  const b = spec.bindings;
  if (!isObj(b)) return ["spec.bindings must be a mapping"];
  const fieldsRaw = get(spec, "outputSchema", "fields");
  const fields = new Set(Array.isArray(fieldsRaw) ? fieldsRaw.filter((f) => typeof f === "string") : []);
  for (const [key, v] of Object.entries(b)) {
    if (!fields.has(key)) out.push(`binding "${key}" is not a field of spec.outputSchema.fields`);
    if (!isObj(v)) {
      out.push(`binding "${key}" must be a mapping {from, value, select}`);
      continue;
    }
    if (typeof v.from !== "string") out.push(`binding "${key}".from must be a string`);
    if (typeof v.value !== "string") out.push(`binding "${key}".value must be a string`);
    if (v.select !== undefined && v.select !== "latest" && v.select !== "all") {
      out.push(`binding "${key}".select must be "latest" or "all" (got ${JSON.stringify(v.select)})`);
    }
  }
  return out;
}
