import { Context, error, hasAssetOfKind, localAssetsOfKind, warn } from "../context.js";
import { get, isNonEmptyString, isObj, normalizeRelPath, PACKAGE_REF_RE } from "../util.js";

export interface Grounding {
  worldRef?: string;
  views: string[];
  compilers: string[];
}

/**
 * Parse `<worldRef>#<asset path>`. Returns the path part, or an error string.
 */
export function parseContractRef(entry: unknown, worldRef: string | undefined): { path: string } | { error: string } {
  if (!isNonEmptyString(entry)) return { error: "must be a non-empty string" };
  const hash = entry.indexOf("#");
  if (hash < 0) return { error: `"${entry}" is not of the form <worldRef>#<asset path>` };
  const ref = entry.slice(0, hash);
  const p = entry.slice(hash + 1);
  if (worldRef !== undefined && ref !== worldRef) {
    return { error: `"${entry}" does not start with semanticGrounding.worldRef "${worldRef}"` };
  }
  // Spec 3 (round 3): exact relative POSIX path, no leading "./".
  const norm = normalizeRelPath(p);
  if (norm === null || p !== norm || p.startsWith("./")) {
    return { error: `"${entry}" has an invalid package-relative asset path "${p}"` };
  }
  return { path: norm };
}

/** Spec sections 3 (WorldModelPackage) and 6. */
export function checkWorldModelPackage(ctx: Context): Grounding {
  const g: Grounding = { views: [], compilers: [] };
  const wm = get(ctx.manifest, "spec", "worldModel");
  if (!isObj(wm)) {
    error(ctx, "worldmodel.spec", "WorldModelPackage requires spec.worldModel mapping", "owp.yaml");
  } else {
    // roles
    const roles = wm.roles;
    if (!Array.isArray(roles) || roles.length === 0 || !roles.every(isNonEmptyString)) {
      error(ctx, "worldmodel.roles", "spec.worldModel.roles must be a non-empty list of non-empty strings", "owp.yaml");
    }

    // semanticGrounding
    const sg = wm.semanticGrounding;
    if (!isObj(sg)) {
      error(ctx, "worldmodel.world-ref", "spec.worldModel.semanticGrounding (worldRef) is required", "owp.yaml");
      error(ctx, "worldmodel.compatible-views", "spec.worldModel.semanticGrounding.compatibleWorldViews is required", "owp.yaml");
      error(ctx, "worldmodel.compatible-compilers", "spec.worldModel.semanticGrounding.compatibleStateCompilers is required", "owp.yaml");
    } else {
      if (!isNonEmptyString(sg.worldRef)) {
        error(ctx, "worldmodel.world-ref", "semanticGrounding.worldRef is required", "owp.yaml");
      } else if (!PACKAGE_REF_RE.test(sg.worldRef)) {
        error(ctx, "worldmodel.world-ref", `semanticGrounding.worldRef "${sg.worldRef}" must be <namespace>/<name>@<semver>`, "owp.yaml");
        g.worldRef = sg.worldRef;
      } else {
        g.worldRef = sg.worldRef;
      }
      for (const [key, into, label, rule] of [
        ["compatibleWorldViews", g.views, "World View", "worldmodel.compatible-views"],
        ["compatibleStateCompilers", g.compilers, "State Compiler", "worldmodel.compatible-compilers"],
      ] as const) {
        const list = sg[key];
        if (!Array.isArray(list) || list.length === 0) {
          error(ctx, rule, `semanticGrounding.${key} must list at least one compatible ${label} as <worldRef>#<asset path>`, "owp.yaml");
          continue;
        }
        list.forEach((e, i) => {
          const r = parseContractRef(e, g.worldRef);
          if ("error" in r) {
            error(ctx, "worldmodel.grounding-ref", `semanticGrounding.${key}[${i}] ${r.error}`, "owp.yaml");
          } else {
            into.push(e as string);
          }
        });
      }
    }

    // inputs.contract
    if (get(wm, "inputs", "contract") !== "EffectiveWorldState") {
      error(ctx, "worldmodel.input-contract", "spec.worldModel.inputs.contract must be EffectiveWorldState", "owp.yaml");
    }
  }

  // Spec 8 severity: missing ModelArtifact / EvaluationProfile are warnings.
  for (const [k, rule] of [
    ["ModelArtifact", "worldmodel.model-artifact-missing"],
    ["EvaluationProfile", "worldmodel.evaluation-profile-missing"],
  ] as const) {
    if (!hasAssetOfKind(ctx, k)) warn(ctx, rule, `WorldModelPackage has no ${k} asset`, "owp.yaml");
  }

  // Representation adapter
  const adapters = localAssetsOfKind(ctx, "RepresentationAdapterProfile");
  if (adapters.length === 0) {
    error(ctx, "worldmodel.adapter", "WorldModelPackage requires a packaged RepresentationAdapterProfile asset", "owp.yaml");
  }
  const adapterRef = isObj(wm) ? get(wm, "representation", "adapterRef") : undefined;
  if (isObj(wm)) {
    if (!isNonEmptyString(adapterRef)) {
      error(ctx, "worldmodel.adapter-ref", "spec.worldModel.representation.adapterRef is required", "owp.yaml");
    } else {
      const a = adapters.find((x) => x.rawPath === adapterRef);
      if (a && a.exists && isObj(a.doc) && get(a.doc, "spec", "source") !== "EffectiveWorldState") {
        // Appendix A `worldmodel.adapter-source` (no body text): the adapter must be sourced from EWS.
        error(ctx, "worldmodel.adapter-source", `RepresentationAdapterProfile ${a.rawPath} spec.source must be EffectiveWorldState (got ${JSON.stringify(get(a.doc, "spec", "source"))})`, a.rawPath);
      }
      if (!a) {
        error(ctx, "worldmodel.adapter-ref", `representation.adapterRef "${adapterRef}" must be the path of a local RepresentationAdapterProfile asset`, "owp.yaml");
      }
    }
  }
  return g;
}
