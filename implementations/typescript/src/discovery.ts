/**
 * Spec section 5: local assets are found by their own apiVersion and kind, not listed in owp.yaml.
 *
 * Discovery reads every .yaml/.yml file of the package except owp.yaml and the listed PackageExample files.
 * It skips path components that start with "." or name a build/tooling directory, paths that .owpignore excludes,
 * files that resolve outside the package, and subdirectories that hold their own owp.yaml (a nested package).
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { IgnoreRule, isIgnored, loadIgnore } from "./ignore.js";
import { get, isObj, isYamlPath, loadYamlFile, Obj, staysInside } from "./util.js";

const IGNORED = new Set(["__pycache__", "venv", "node_modules", "dist", "build"]);

/** OWP documents that are package files, not assets. */
export const DOCUMENT_KINDS = new Set(["ObservationSet", "EffectiveWorldState"]);

export interface PackageDocument {
  rel: string;
  ok: boolean;
  value?: unknown;
  error?: string;
}

/** A YAML document that declares an OWP apiVersion. */
export function isOwpDocument(doc: unknown): doc is Obj {
  return isObj(doc) && typeof doc.apiVersion === "string" && doc.apiVersion.startsWith("openworld/");
}

function walk(root: string, dir: string, rules: IgnoreRule[], out: string[]): void {
  for (const entry of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
    if (entry.name.startsWith(".") || IGNORED.has(entry.name)) continue;
    const rel = dir ? `${dir}/${entry.name}` : entry.name;
    const abs = path.join(root, rel);
    let stat: fs.Stats;
    try {
      stat = fs.statSync(abs);
    } catch {
      continue;
    }
    if (stat.isDirectory()) {
      if (!fs.existsSync(path.join(abs, "owp.yaml"))) walk(root, rel, rules, out); // a nested package is not entered
    } else if (stat.isFile() && isYamlPath(rel) && rel !== "owp.yaml" && !isIgnored(rules, rel) && staysInside(root, abs)) {
      out.push(rel);
    }
  }
}

export function packageDocuments(root: string, skip: Set<string> = new Set()): PackageDocument[] {
  const rels: string[] = [];
  walk(root, "", loadIgnore(root), rels);
  return rels
    .filter((rel) => !skip.has(rel))
    .sort()
    .map((rel) => {
      const l = loadYamlFile(path.join(root, rel));
      return l.ok ? { rel, ok: true, value: l.value } : { rel, ok: false, error: l.error };
    });
}

/** Kinds of a package's local assets by path: discovered documents and listed PackageExample files. */
export function localAssetKinds(root: string, manifest: Obj): Map<string, string> {
  const kinds = new Map<string, string>();
  const assets = get(manifest, "spec", "assets");
  for (const a of Array.isArray(assets) ? assets : []) {
    if (isObj(a) && a.kind === "PackageExample" && typeof a.path === "string") kinds.set(a.path, "PackageExample");
  }
  for (const d of packageDocuments(root, new Set(kinds.keys()))) {
    if (d.ok && isOwpDocument(d.value) && typeof d.value.kind === "string" && !DOCUMENT_KINDS.has(d.value.kind)) {
      kinds.set(d.rel, d.value.kind);
    }
  }
  return kinds;
}
