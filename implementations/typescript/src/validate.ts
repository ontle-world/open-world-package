import * as fs from "node:fs";
import * as path from "node:path";
import { Context, error, Issue, warn } from "./context.js";
import { checkManifest } from "./rules/manifest.js";
import { checkSemanticAssetShape, collectAssets } from "./rules/assets.js";
import { checkCompilerSchemas, checkContainment, checkWorldPackage } from "./rules/world.js";
import { checkWorldModelPackage, Grounding } from "./rules/worldmodel.js";
import { checkEvaluation } from "./rules/evaluation.js";
import { checkOntologyPackage } from "./rules/ontology.js";
import { checkDependencies } from "./rules/dependencies.js";
import { checkAssetStructure, checkExtensionDeclarations, checkExtensionDefinition, checkManifestStructure } from "./rules/extensions.js";
import { isObj, loadYamlFile } from "./util.js";
import { LEGACY_MANIFEST_NAMES } from "./vocab.js";

export type { Issue, Profile } from "./context.js";

export interface ValidationResult {
  valid: boolean;
  errors: Issue[];
  warnings: Issue[];
  /** WorldPackage and OntologyPackage: highest profile satisfied independent of the declaration (null if none). */
  satisfiedProfile?: string | null;
  /** WorldPackage: the declared (or defaulted) profile; OntologyPackage: the declared profile, if any. */
  declaredProfile?: string;
  kind?: string;
  identity?: string;
}

/**
 * Validate an OWP package directory against the public-alpha spec.
 * Rule order: filesystem/manifest -> identity -> extensions/defined fields -> assets -> kind rules -> evaluation.
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
    extensionNames: new Set(),
    errors: base.errors,
    warnings: base.warnings,
  };

  checkManifest(ctx);
  checkDependencies(ctx);
  checkExtensionDeclarations(ctx);
  checkManifestStructure(ctx);
  checkExtensionDefinition(ctx);
  collectAssets(ctx);
  checkAssetStructure(ctx);
  checkSemanticAssetShape(ctx);
  checkCompilerSchemas(ctx);

  let grounding: Grounding | undefined;
  switch (ctx.packageKind) {
    case "WorldPackage":
      checkWorldPackage(ctx);
      checkContainment(ctx);
      break;
    case "WorldModelPackage":
      grounding = checkWorldModelPackage(ctx);
      break;
    case "OntologyPackage":
      checkOntologyPackage(ctx);
      break;
  }
  // Spec 3.1 / 6.1: conformance profiles exist for WorldPackage and OntologyPackage only.
  const hasProfiles = ctx.packageKind === "WorldPackage" || ctx.packageKind === "OntologyPackage";
  if (!hasProfiles && isObj(ctx.manifest.spec) && ctx.manifest.spec.conformance !== undefined) {
    warn(ctx, "manifest.conformance-ignored", "spec.conformance applies to WorldPackage and OntologyPackage only and is ignored", "owp.yaml");
  }
  checkEvaluation(ctx, grounding);

  const result: ValidationResult = {
    valid: ctx.errors.length === 0,
    errors: ctx.errors,
    warnings: ctx.warnings,
    kind: ctx.packageKind || undefined,
    identity: ctx.identity,
  };
  if (ctx.packageKind === "WorldPackage" || ctx.packageKind === "OntologyPackage") {
    result.satisfiedProfile = ctx.satisfiedProfile ?? null;
    result.declaredProfile = ctx.declaredProfile;
  }
  return result;
}
