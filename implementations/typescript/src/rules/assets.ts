import * as path from "node:path";
import { Context, error, LocalAsset, warn } from "../context.js";
import { fileExists, isNonEmptyString, isObj, isYamlPath, loadYamlFile, normalizeRelPath, staysInside } from "../util.js";
import { API_VERSION, KNOWN_ASSET_KINDS } from "../vocab.js";

/**
 * Spec section 5 + 8: `spec.assets` entries, local references, duplicate paths,
 * typed local YAML assets. Populates ctx.localAssets / ctx.refAssets for later rules.
 */
export function collectAssets(ctx: Context): void {
  const spec = ctx.manifest.spec;
  if (!isObj(spec) || spec.assets === undefined) return;
  const assets = spec.assets;
  if (!Array.isArray(assets)) {
    error(ctx, "asset.list", "spec.assets must be a list", "owp.yaml");
    return;
  }

  const seen = new Map<string, number>();
  assets.forEach((a, i) => {
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
    // Spec 8: vocabulary is open; unqualified unknown kinds warn, namespaced kinds (with ':') are accepted.
    if (!KNOWN_ASSET_KINDS.has(kind) && !kind.includes(":")) {
      warn(ctx, "asset.kind-unknown", `${where}.kind "${kind}" is not in the asset-kind vocabulary`, "owp.yaml");
    }
    const hasPath = a.path !== undefined;
    const hasRef = a.ref !== undefined;
    if (hasPath === hasRef) {
      error(ctx, "asset.path-or-ref", `${where} must have exactly one of "path" or "ref"`, "owp.yaml");
      return;
    }
    if (hasRef) {
      if (!isObj(a.ref) || Object.keys(a.ref).length === 0) {
        error(ctx, "asset.entry", `${where}.ref must be a non-empty mapping`, "owp.yaml");
        return;
      }
      ctx.refAssets.push({ index: i, kind, ref: a.ref });
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
    asset.exists = true;
    // Spec 8: every local YAML asset must parse, including PackageExample files.
    if (!isYamlPath(raw)) return;

    const loaded = loadYamlFile(abs);
    if (!loaded.ok) {
      asset.parseError = true;
      error(ctx, "asset.yaml", `asset ${raw} is not parseable YAML: ${loaded.error}`, raw);
      return;
    }
    asset.doc = loaded.value;
    const doc = loaded.value;
    // Typed asset check: when the asset file declares its own kind/apiVersion they must agree.
    // A PackageExample may hold any document (for example an ObservationSet), so its kind is not compared.
    if (isObj(doc) && kind !== "PackageExample") {
      if (doc.kind !== undefined && doc.kind !== kind) {
        error(ctx, "asset.kind-mismatch", `asset ${raw} declares kind ${JSON.stringify(doc.kind)} but owp.yaml declares ${kind}`, raw);
      }
      if (doc.apiVersion !== undefined && doc.apiVersion !== API_VERSION) {
        warn(ctx, "asset.api-version", `asset ${raw} declares apiVersion ${JSON.stringify(doc.apiVersion)}; expected ${API_VERSION}`, raw);
      }
    }
  });
}

/**
 * Round 1 required semantic assets to declare `kind`; the revised spec 8 only
 * requires parse + kind agreement, so this is now a no-op kept for extension.
 */
export function checkSemanticAssetShape(_ctx: Context): void {}
