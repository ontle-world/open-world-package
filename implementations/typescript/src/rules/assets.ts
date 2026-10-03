import * as path from "node:path";
import { Context, error, LocalAsset, warn } from "../context.js";
import { fileExists, isNonEmptyString, isObj, isYamlPath, loadYamlFile, normalizeRelPath, staysInside } from "../util.js";
import { EXTENSION_KIND_RE } from "../structure.js";
import { externalRefProblems } from "./externalref.js";
import { ASSET_KIND_STABILITY } from "../vocab.js";
import { IGNORE_FILE, isIgnored, loadIgnore } from "../ignore.js";
import { DOCUMENT_KINDS, isOwpDocument, packageDocuments } from "../discovery.js";

/**
 * Spec section 5 + 8. The manifest lists external assets (`ref`) and PackageExample files; every other local
 * asset is discovered from its own apiVersion and kind. Populates ctx.localAssets / ctx.refAssets.
 */
export function collectAssets(ctx: Context): void {
  const spec = ctx.manifest.spec;
  const experimentalKinds = new Map<string, number>();
  /** Kind rules shared by manifest entries and discovered files; false when the kind cannot be used. */
  const kindOk = (kind: string, where: string, file: string, discovered: boolean): boolean => {
    // A kind containing ':' is an extension kind (spec 13.3).
    if (kind.includes(":")) {
      const m = EXTENSION_KIND_RE.exec(kind);
      if (!m) {
        error(ctx, "asset.kind", `${where} "${kind}" contains ':' but is not <extension>:<Kind>`, file);
        return false;
      }
      if (!ctx.extensionNames.has(m[1])) {
        error(ctx, "extension.undeclared", `${where} "${kind}" uses extension "${m[1]}", which spec.dependencies does not declare with "as"`, file);
      }
    } else if (!ASSET_KIND_STABILITY.has(kind)) {
      // A file that says it is an OWP document must name a kind OWP knows; a manifest entry's kind is open.
      if (discovered) {
        error(ctx, "asset.kind", `${where} "${kind}" is not an asset kind of the vocabulary or an extension kind`, file);
        return false;
      }
      warn(ctx, "asset.kind-unknown", `${where} "${kind}" is not in the asset-kind vocabulary`, file);
    } else if (ASSET_KIND_STABILITY.get(kind) === "experimental") {
      experimentalKinds.set(kind, (experimentalKinds.get(kind) ?? 0) + 1);
    }
    return true;
  };

  const assets = isObj(spec) ? spec.assets : undefined;
  if (assets !== undefined && !Array.isArray(assets)) error(ctx, "asset.list", "spec.assets must be a list", "owp.yaml");
  const seen = new Map<string, number>();
  const ignoreRules = loadIgnore(ctx.root);
  (Array.isArray(assets) ? assets : []).forEach((a, i) => {
    const where = `spec.assets[${i}]`;
    if (!isObj(a)) {
      error(ctx, "asset.entry", `${where} must be a mapping`, "owp.yaml");
      return;
    }
    if (!isNonEmptyString(a.kind)) {
      error(ctx, "asset.kind", `${where}.kind must be a non-empty string`, "owp.yaml");
      return;
    }
    const kind = a.kind;
    kindOk(kind, `${where}.kind`, "owp.yaml", false);
    const hasPath = a.path !== undefined;
    // Spec 5.1: a present `ref` key is an ExternalRef, whatever its value.
    const hasRef = Object.prototype.hasOwnProperty.call(a, "ref");
    if (hasRef) {
      const r = externalRefProblems(a.ref, `${where}.ref`, ctx.extensionNames);
      for (const p of r.errors) error(ctx, p.rule, p.msg, "owp.yaml");
      for (const p of r.warnings) warn(ctx, p.rule, p.msg, "owp.yaml");
    }
    if (hasPath && kind !== "PackageExample") {
      error(ctx, "asset.path-or-ref", `${where} lists the local file ${JSON.stringify(a.path)}; local assets are found by their apiVersion and kind, and only PackageExample files are listed`, "owp.yaml");
      return;
    }
    if (hasPath === hasRef) {
      error(ctx, "asset.path-or-ref", `${where} must have exactly one of "path" or "ref"`, "owp.yaml");
      return;
    }
    if (hasRef) {
      if (isObj(a.ref)) ctx.refAssets.push({ index: i, kind, ref: a.ref });
      return;
    }

    if (!isNonEmptyString(a.path)) {
      error(ctx, "asset.path-form", `${where}.path must be a non-empty string`, "owp.yaml");
      return;
    }
    // Spec 3 (round 3): paths are exact strings; relative POSIX, no leading "./".
    const raw = a.path;
    const asset: LocalAsset = { index: i, kind, rawPath: raw, path: raw, exists: false };
    ctx.localAssets.push(asset);
    const absolute = raw.startsWith("/") || /^[A-Za-z]:/.test(raw);
    const formBad = absolute || raw.includes("\\") || raw.startsWith("./") || raw.includes("//") || raw.endsWith("/");
    if (formBad) {
      error(ctx, "asset.path-form", `${where}.path "${raw}" must be a relative POSIX path without a leading ./`, "owp.yaml");
    }
    const norm = absolute ? null : normalizeRelPath(raw);
    if (norm === null) {
      // Absolute paths and paths that climb out of the root resolve outside the package (spec 8).
      if (absolute || path.posix.normalize(raw).startsWith("..")) {
        error(ctx, "asset.path-escape", `${where}.path "${raw}" resolves outside the package root`, "owp.yaml");
      }
      asset.path = null;
      return;
    }
    if (formBad) {
      asset.path = null;
      return;
    }
    const prev = seen.get(raw);
    if (prev !== undefined) {
      error(ctx, "asset.duplicate-path", `${where}.path "${raw}" duplicates spec.assets[${prev}]`, "owp.yaml");
    } else {
      seen.set(raw, i);
    }
    const abs = path.join(ctx.root, norm);
    if (fileExists(abs) && !staysInside(ctx.root, abs)) {
      error(ctx, "asset.path-escape", `${where}.path "${raw}" resolves outside the package root`, raw);
      return;
    }
    if (!fileExists(abs)) {
      error(ctx, "asset.missing-file", `${where}.path "${raw}" does not exist as a file in the package`, raw);
      return;
    }
    if (isIgnored(ignoreRules, norm)) {
      error(ctx, "asset.missing-file", `${where}.path "${raw}" is excluded by ${IGNORE_FILE}, so it is not a package file`, raw);
      return;
    }
    asset.exists = true;
    // Spec 8: a listed PackageExample must parse; it may hold any document, so its kind is not compared.
    if (!isYamlPath(raw)) return;
    const loaded = loadYamlFile(abs);
    if (!loaded.ok) {
      asset.parseError = true;
      error(ctx, "asset.yaml", `asset ${raw} is not parseable YAML: ${loaded.error}`, raw);
      return;
    }
    asset.doc = loaded.value;
  });

  // Discovery (spec 5): a YAML file with an OWP apiVersion is an OWP document; its kind says what it is.
  const examples = new Set(ctx.localAssets.map((a) => a.rawPath));
  for (const d of packageDocuments(ctx.root, examples)) {
    if (!d.ok) {
      error(ctx, "asset.yaml", `${d.rel} is not parseable YAML: ${d.error}`, d.rel);
      continue;
    }
    const doc = d.value;
    if (!isOwpDocument(doc)) continue; // an ordinary package file
    if (doc.apiVersion !== ctx.manifest.apiVersion) {
      error(ctx, "asset.api-version", `${d.rel} declares apiVersion ${JSON.stringify(doc.apiVersion)}; it must equal the manifest's ${JSON.stringify(ctx.manifest.apiVersion)}`, d.rel);
    }
    const kind = doc.kind;
    if (typeof kind === "string" && DOCUMENT_KINDS.has(kind)) continue; // an ObservationSet or EWS document
    if (!isNonEmptyString(kind)) {
      error(ctx, "asset.kind", `${d.rel} declares apiVersion ${JSON.stringify(doc.apiVersion)} but no kind`, d.rel);
      continue;
    }
    if (!kindOk(kind, `${d.rel}: kind`, d.rel, true)) continue;
    ctx.localAssets.push({ index: -1, kind, rawPath: d.rel, path: d.rel, exists: true, doc });
  }

  // One warning per experimental kind, with the number of assets that use it.
  for (const [kind, n] of experimentalKinds) {
    warn(ctx, "asset.kind-experimental", `asset kind ${kind} is experimental and may change or be removed (${n} asset${n > 1 ? "s" : ""})`, "owp.yaml");
  }
}

/**
 * Round 1 required semantic assets to declare `kind`; the revised spec 8 only
 * requires parse + kind agreement, so this is now a no-op kept for extension.
 */
export function checkSemanticAssetShape(_ctx: Context): void {}
