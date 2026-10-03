import * as path from "node:path";
import { Context, error, warn } from "../context.js";
import { ASSET_STRUCTURES, EXTENSION_NAME_RE, extensionBlockProblems, MANIFEST, RESERVED_EXTENSION_NAMES, structureProblems } from "../structure.js";
import { checkSemanticBindings } from "./binding.js";
import { standardBindingProblems } from "./externalref.js";
import { checkStandardFields } from "./standard-fields.js";
import { checkExperimentalAsset, checkMultiLatest, checkStandardKindFields, checkViewSpecialization, STANDARD_KINDS_WITH_EXPERIMENTAL_FIELDS, EXPERIMENTAL_STRUCTURES } from "./experimental.js";
import { fileExists, isNonEmptyString, isObj, normalizeRelPath, staysInside } from "../util.js";

const PASCAL_RE = /^[A-Z][A-Za-z0-9]*$/;

/**
 * Spec 13.1: extension declarations in spec.dependencies (`as`, `mustUnderstand`).
 * Populates ctx.extensionNames with the valid declared names.
 */
export function checkExtensionDeclarations(ctx: Context): void {
  const deps = isObj(ctx.manifest.spec) ? ctx.manifest.spec.dependencies : undefined;
  if (!Array.isArray(deps)) return;
  deps.forEach((d, i) => {
    if (!isObj(d)) return;
    const where = `spec.dependencies[${i}]`;
    if (d.mustUnderstand !== undefined) {
      if (d.as === undefined) error(ctx, "extension.declaration", `${where} declares mustUnderstand without as`, "owp.yaml");
      else if (typeof d.mustUnderstand !== "boolean") error(ctx, "extension.declaration", `${where}.mustUnderstand must be true or false`, "owp.yaml");
    }
    if (d.as === undefined) return;
    const name = d.as;
    if (typeof name !== "string" || !EXTENSION_NAME_RE.test(name)) {
      error(ctx, "extension.name", `${where}.as ${JSON.stringify(name)} must match [a-z][a-z0-9-]* (at most 63 characters)`, "owp.yaml");
    } else if (RESERVED_EXTENSION_NAMES.has(name)) {
      error(ctx, "extension.name", `${where}.as "${name}" is a reserved extension name`, "owp.yaml");
    } else if (ctx.extensionNames.has(name)) {
      error(ctx, "extension.duplicate", `${where}.as "${name}" declares an extension name that is already declared`, "owp.yaml");
    } else {
      ctx.extensionNames.add(name);
    }
  });
}

/** Spec 2 + 8 "Defined fields": the manifest has only schema fields and extensions blocks. */
export function checkManifestStructure(ctx: Context): void {
  for (const p of structureProblems(ctx.manifest, MANIFEST, ctx.extensionNames)) error(ctx, p.rule, `owp.yaml: ${p.msg}`, "owp.yaml");
}

/** Spec 13.2: spec.extensionDefinition {description, kinds, schemas}. */
export function checkExtensionDefinition(ctx: Context): void {
  const def = isObj(ctx.manifest.spec) ? ctx.manifest.spec.extensionDefinition : undefined;
  if (def === undefined) return;
  const bad = (msg: string) => error(ctx, "extension.definition", `spec.extensionDefinition${msg}`, "owp.yaml");
  if (!isObj(def)) return bad(" must be a mapping");
  if (def.description !== undefined && typeof def.description !== "string") bad(".description must be a string");
  if (def.kinds !== undefined && !(Array.isArray(def.kinds) && def.kinds.every((k) => typeof k === "string" && PASCAL_RE.test(k)))) {
    bad(".kinds must be a list of PascalCase kind names without an extension prefix");
  }
  if (def.schemas === undefined) return;
  if (!Array.isArray(def.schemas)) return bad(".schemas must be a list of package-relative paths");
  def.schemas.forEach((s, i) => {
    const norm = typeof s === "string" ? normalizeRelPath(s) : null;
    if (!isNonEmptyString(s) || norm === null || s.startsWith("./")) return bad(`.schemas[${i}] ${JSON.stringify(s)} must be a package-relative path`);
    const abs = path.join(ctx.root, norm);
    if (!fileExists(abs) || !staysInside(ctx.root, abs)) bad(`.schemas[${i}] ${s} does not exist in the package`);
  });
}

/**
 * Spec 8 + 13.3 for local asset documents other than PackageExample: kinds with a JSON Schema (CompatibilityEvidence)
 * are checked field by field; every other kind only for extensions blocks in its top-level
 * metadata and spec; experimental kinds follow Appendix C (src/rules/experimental.ts).
 * Extension names are checked against the package's declarations.
 */
export function checkAssetStructure(ctx: Context): void {
  for (const a of ctx.localAssets) {
    const doc = a.doc;
    // Spec 5.3: standard bindings in any local asset other than a PackageExample.
    if (isObj(doc) && a.kind !== "PackageExample" && isObj(doc.spec) && doc.spec.standardBindings !== undefined) {
      const r = standardBindingProblems(doc.spec.standardBindings, `${a.rawPath}: spec.standardBindings`, ctx.extensionNames);
      r.errors.forEach((p) => error(ctx, p.rule, p.msg, a.rawPath));
      r.warnings.forEach((p) => warn(ctx, p.rule, p.msg, a.rawPath));
    }
    // Spec 8 / 13.3: PackageExample files may hold any document, so they are not checked.
    // SemanticBinding documents are checked by checkSemanticBindings (spec 14).
    if (!isObj(doc) || a.kind === "PackageExample" || a.kind === "SemanticBinding") continue;
    // Appendix C: experimental kinds are checked with warnings (extension rules stay errors).
    if (a.kind in EXPERIMENTAL_STRUCTURES) {
      checkExperimentalAsset(ctx, a);
      continue;
    }
    const shape = ASSET_STRUCTURES[a.kind];
    const problems = shape
      ? structureProblems(doc, shape, ctx.extensionNames)
      : ["metadata", "spec"].flatMap((s) => {
          const block = doc[s];
          return isObj(block) && block.extensions !== undefined
            ? extensionBlockProblems(block.extensions, `${s}.extensions`, ctx.extensionNames)
            : [];
        });
    for (const p of problems) error(ctx, p.rule, `${a.rawPath}: ${p.msg}`, a.rawPath);
    if (STANDARD_KINDS_WITH_EXPERIMENTAL_FIELDS.includes(a.kind)) {
      checkStandardFields(ctx, a); // spec 15: errors
      checkStandardKindFields(ctx, a); // Appendix C.1: warnings
    }
  }
  checkViewSpecialization(ctx);
  checkMultiLatest(ctx);
  checkSemanticBindings(ctx);
}
