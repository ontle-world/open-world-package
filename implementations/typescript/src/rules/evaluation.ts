import { Context, error, LocalAsset, localAssetsOfKind, warn } from "../context.js";
import { get, isNonEmptyString, isObj, PINNED_RE, SEMVER_RE } from "../util.js";
import type { Grounding } from "./worldmodel.js";

/** Compare two valid SemVer strings (SemVer 2.0 precedence, build ignored). */
export function compareSemver(a: string, b: string): number {
  const split = (v: string) => {
    const noBuild = v.split("+")[0];
    const dash = noBuild.indexOf("-");
    const core = (dash < 0 ? noBuild : noBuild.slice(0, dash)).split(".").map(Number);
    const pre = dash < 0 ? [] : noBuild.slice(dash + 1).split(".");
    return { core, pre };
  };
  const x = split(a);
  const y = split(b);
  for (let i = 0; i < 3; i++) if (x.core[i] !== y.core[i]) return x.core[i] < y.core[i] ? -1 : 1;
  if (x.pre.length === 0 && y.pre.length === 0) return 0;
  if (x.pre.length === 0) return 1;
  if (y.pre.length === 0) return -1;
  for (let i = 0; i < Math.max(x.pre.length, y.pre.length); i++) {
    const p = x.pre[i];
    const q = y.pre[i];
    if (p === undefined) return -1;
    if (q === undefined) return 1;
    const pn = /^\d+$/.test(p);
    const qn = /^\d+$/.test(q);
    if (pn && qn) {
      if (Number(p) !== Number(q)) return Number(p) < Number(q) ? -1 : 1;
    } else if (pn !== qn) {
      return pn ? -1 : 1;
    } else if (p !== q) {
      return p < q ? -1 : 1;
    }
  }
  return 0;
}

function splitPinned(v: string): { name: string; version: string } {
  const at = v.lastIndexOf("@");
  return { name: v.slice(0, at), version: v.slice(at + 1) };
}

/** Section 9: EvaluationProfile / VerifierPackage versioning and lineage. */
function checkVersionedEvalAsset(ctx: Context, a: LocalAsset): void {
  if (!isObj(a.doc) || a.path === null) return;
  const file = a.path;
  const name = get(a.doc, "metadata", "name");
  const version = get(a.doc, "metadata", "version");
  if (!isNonEmptyString(name)) {
    warn(ctx, "eval.name", `${a.kind} ${file} should declare metadata.name`, file);
  }
  if (version === undefined) {
    warn(ctx, "eval.version-missing", `${a.kind} ${file} SHOULD declare metadata.version (SemVer)`, file);
  } else if (typeof version !== "string" || !SEMVER_RE.test(version)) {
    error(ctx, "eval.version", `${a.kind} ${file} metadata.version must be SemVer (got ${JSON.stringify(version)})`, file);
  }

  const spec = get(a.doc, "spec");
  const supersedes = get(spec, "supersedes");
  if (supersedes !== undefined) {
    if (typeof supersedes !== "string" || !PINNED_RE.test(supersedes)) {
      error(ctx, "eval.supersedes", `${a.kind} ${file} spec.supersedes must be <name>@<exact-semver> (got ${JSON.stringify(supersedes)})`, file);
    } else {
      const s = splitPinned(supersedes);
      if (isNonEmptyString(name) && s.name !== name) {
        warn(ctx, "eval.supersedes.name", `${a.kind} ${file} supersedes "${supersedes}" which has a different name than ${name}`, file);
      }
      if (typeof version === "string" && SEMVER_RE.test(version) && compareSemver(s.version, version) >= 0) {
        warn(ctx, "eval.supersedes.order", `${a.kind} ${file} version ${version} is not greater than superseded version ${s.version}`, file);
      }
    }
    // Spec 9 (revised): changedBecause is recommended and not validated in this alpha.
  }
}

function checkEvidence(ctx: Context, a: LocalAsset, g: Grounding | undefined): void {
  if (!isObj(a.doc) || a.path === null) return;
  const file = a.path;
  const doc = a.doc;
  if (!isNonEmptyString(get(doc, "metadata", "name"))) {
    error(ctx, "evidence.required", `CompatibilityEvidence ${file} requires metadata.name`, file);
  }
  const spec = doc.spec;
  if (!isObj(spec)) {
    error(ctx, "evidence.required", `CompatibilityEvidence ${file} requires a spec mapping`, file);
    return;
  }
  if (!isNonEmptyString(spec.subject)) {
    error(ctx, "evidence.subject", `CompatibilityEvidence ${file} requires spec.subject`, file);
  } else if (ctx.packageKind === "WorldModelPackage" && spec.subject !== ctx.rawIdentity) {
    error(ctx, "evidence.subject", `CompatibilityEvidence ${file} subject "${spec.subject}" MUST equal the package identity ${ctx.rawIdentity ?? "(invalid identity)"}`, file);
  }

  // Pinned references.
  for (const key of ["evaluationProfile", "verifier", "goldenSet", "dataset"] as const) {
    const v = spec[key];
    if (v === undefined) {
      if (key === "evaluationProfile") {
        error(ctx, "evidence.required", `CompatibilityEvidence ${file} requires spec.evaluationProfile (<name>@<exact-semver>)`, file);
      }
      continue;
    }
    if (typeof v !== "string" || !PINNED_RE.test(v)) {
      error(ctx, "evidence.unpinned", `CompatibilityEvidence ${file} spec.${key} must be <name>@<exact-semver>; ranges are not allowed (got ${JSON.stringify(v)})`, file);
    }
  }

  // Local version binding.
  for (const [key, kind] of [
    ["evaluationProfile", "EvaluationProfile"],
    ["verifier", "VerifierPackage"],
  ] as const) {
    const v = spec[key];
    if (typeof v !== "string" || !PINNED_RE.test(v)) continue;
    const { name, version } = splitPinned(v);
    const locals = localAssetsOfKind(ctx, kind).filter((x) => get(x.doc, "metadata", "name") === name);
    if (locals.length > 0 && !locals.some((x) => get(x.doc, "metadata", "version") === version)) {
      const have = locals.map((x) => `${x.path}@${JSON.stringify(get(x.doc, "metadata", "version"))}`).join(", ");
      error(ctx, "evidence.version-mismatch", `CompatibilityEvidence ${file} binds ${v} but the local ${kind} "${name}" has a different version (${have})`, file);
    }
  }

  // Scope.
  const scope = spec.scope;
  if (!isObj(scope)) {
    error(ctx, "evidence.scope", `CompatibilityEvidence ${file} requires spec.scope with worldRef and worldView`, file);
  } else {
    for (const k of ["worldRef", "worldView"]) {
      if (!isNonEmptyString(scope[k])) error(ctx, "evidence.scope", `CompatibilityEvidence ${file} requires spec.scope.${k}`, file);
    }
    for (const k of ["stateCompiler", "environment", "task"]) {
      if (scope[k] !== undefined && !isNonEmptyString(scope[k])) {
        error(ctx, "evidence.scope", `CompatibilityEvidence ${file} spec.scope.${k} must be a non-empty string when present`, file);
      }
    }
    if (g) {
      if (isNonEmptyString(scope.worldRef) && g.worldRef !== undefined && scope.worldRef !== g.worldRef) {
        error(ctx, "evidence.scope.world-ref", `CompatibilityEvidence ${file} scope.worldRef "${scope.worldRef}" must equal semanticGrounding.worldRef "${g.worldRef}"`, file);
      }
      if (isNonEmptyString(scope.worldView) && !g.views.includes(scope.worldView)) {
        error(ctx, "evidence.scope.world-view", `CompatibilityEvidence ${file} scope.worldView "${scope.worldView}" is not one of compatibleWorldViews`, file);
      }
      if (isNonEmptyString(scope.stateCompiler) && !g.compilers.includes(scope.stateCompiler)) {
        error(ctx, "evidence.scope.state-compiler", `CompatibilityEvidence ${file} scope.stateCompiler "${scope.stateCompiler}" is not one of compatibleStateCompilers`, file);
      }
    }
  }

  if (!isObj(spec.result)) {
    error(ctx, "evidence.result", `CompatibilityEvidence ${file} requires spec.result mapping`, file);
  }
}

/** Spec section 9. `g` is provided for WorldModelPackages. */
export function checkEvaluation(ctx: Context, g: Grounding | undefined): void {
  // Spec 8 (round 3): two local assets of the same kind MUST NOT share metadata.name.
  for (const kind of ["EvaluationProfile", "VerifierPackage"]) {
    const seen = new Map<string, string>();
    for (const a of localAssetsOfKind(ctx, kind)) {
      const n = get(a.doc, "metadata", "name");
      if (typeof n !== "string") continue;
      if (seen.has(n)) error(ctx, "eval.duplicate-name", `${kind} ${a.rawPath} and ${seen.get(n)} share metadata.name "${n}"`, a.rawPath);
      else seen.set(n, a.rawPath);
    }
  }
  for (const a of ctx.localAssets) {
    if (a.kind === "EvaluationProfile" || a.kind === "VerifierPackage") checkVersionedEvalAsset(ctx, a);
    else if (a.kind === "CompatibilityEvidence") checkEvidence(ctx, a, g);
  }
}
