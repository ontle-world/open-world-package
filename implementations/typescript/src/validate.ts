import * as fs from "node:fs";
import * as path from "node:path";
import { Context, error, Issue, Profile, warn } from "./context.js";
import { checkManifest } from "./rules/manifest.js";
import { checkSemanticAssetShape, collectAssets } from "./rules/assets.js";
import { checkWorldPackage } from "./rules/world.js";
import { checkWorldModelPackage, Grounding } from "./rules/worldmodel.js";
import { checkEvaluation } from "./rules/evaluation.js";
import { checkDependencies } from "./rules/dependencies.js";
import { isObj, loadYamlFile } from "./util.js";
import { LEGACY_MANIFEST_NAMES } from "./vocab.js";

export type { Issue, Profile } from "./context.js";

export interface ValidationResult {
  valid: boolean;
  errors: Issue[];
  warnings: Issue[];
  /** WorldPackage only: highest profile satisfied independent of the declaration (null if none). */
  satisfiedProfile?: Profile | null;
  /** WorldPackage only: the declared (or defaulted) profile. */
  declaredProfile?: Profile;
  kind?: string;
  identity?: string;
}

/**
 * Validate an OWP package directory against the public-alpha spec.
 * Rule order: filesystem/manifest -> identity -> assets -> kind rules -> evaluation.
 */
export function validatePackage(dir: string): ValidationResult {
  const root = path.resolve(dir);
  const base = { errors: [] as Issue[], warnings: [] as Issue[] };

  let st: fs.Stats;
  try {
    st = fs.statSync(root);
  } catch {
    error(base, "manifest.load", `package directory ${dir} does not exist`);
    return { valid: false, ...base };
  }
  if (!st.isDirectory()) {
    error(base, "manifest.load", `${dir} is not a directory`);
    return { valid: false, ...base };
  }

  // Section 8: absence of legacy manifest names; section 2: exactly one manifest.
  const entries = new Set(fs.readdirSync(root));
  for (const legacy of LEGACY_MANIFEST_NAMES) {
    if (entries.has(legacy)) error(base, "package.legacy-manifest", `legacy manifest name ${legacy} is not allowed; use owp.yaml`, legacy);
  }
  const manifestPath = path.join(root, "owp.yaml");
  if (!entries.has("owp.yaml") || !fs.statSync(manifestPath).isFile()) {
    error(base, "manifest.load", "package root must contain owp.yaml", "owp.yaml");
    return { valid: false, ...base };
  }

  const loaded = loadYamlFile(manifestPath);
  if (!loaded.ok) {
    error(base, "manifest.load", `owp.yaml is not parseable YAML: ${loaded.error}`, "owp.yaml");
    return { valid: false, ...base };
  }
  if (!isObj(loaded.value)) {
    error(base, "manifest.load", "owp.yaml must be a YAML mapping", "owp.yaml");
    return { valid: false, ...base };
  }

  const ctx: Context = {
    root,
    manifest: loaded.value,
    packageKind: typeof loaded.value.kind === "string" ? loaded.value.kind : "",
    localAssets: [],
    refAssets: [],
    errors: base.errors,
    warnings: base.warnings,
  };

  checkManifest(ctx);
  checkDependencies(ctx);
  collectAssets(ctx);
  checkSemanticAssetShape(ctx);

  let grounding: Grounding | undefined;
  switch (ctx.packageKind) {
    case "WorldPackage":
      checkWorldPackage(ctx);
      break;
    case "WorldModelPackage":
      grounding = checkWorldModelPackage(ctx);
      break;
    case "OntologyPackage":
      // Appendix A `ontology.spec` (no body text in the spec): OntologyPackage requires spec.ontology.
      if (!isObj(ctx.manifest.spec) || ctx.manifest.spec.ontology === undefined) {
        error(ctx, "ontology.spec", "OntologyPackage requires spec.ontology", "owp.yaml");
      }
      break;
  }
  if (ctx.packageKind !== "WorldPackage" && isObj(ctx.manifest.spec) && ctx.manifest.spec.conformance !== undefined) {
    warn(ctx, "conformance.notWorld", "spec.conformance applies to WorldPackage only and is ignored", "owp.yaml");
  }
  checkEvaluation(ctx, grounding);

  const result: ValidationResult = {
    valid: ctx.errors.length === 0,
    errors: ctx.errors,
    warnings: ctx.warnings,
    kind: ctx.packageKind || undefined,
    identity: ctx.identity,
  };
  if (ctx.packageKind === "WorldPackage") {
    result.satisfiedProfile = ctx.satisfiedProfile ?? null;
    result.declaredProfile = ctx.declaredProfile;
  }
  return result;
}
