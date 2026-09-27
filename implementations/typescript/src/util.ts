import * as fs from "node:fs";
import * as path from "node:path";
import { parseDocument } from "yaml";

/** SemVer 2.0 core+prerelease+build, as in schemas/owp-manifest.schema.json. */
export const SEMVER_RE =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

/** `<name>@<exact-semver>` (spec section 9). */
export const PINNED_RE =
  /^[^@\s]+@(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

/** `<namespace>/<name>@<semver>` (spec section 2). */
export const PACKAGE_REF_RE =
  /^([^/@#\s]+)\/([^/@#\s]+)@((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)$/;

export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type Obj = { [k: string]: unknown };

export function isObj(v: unknown): v is Obj {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function isNonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.trim().length > 0;
}

export function get(o: unknown, ...keys: string[]): unknown {
  let cur: unknown = o;
  for (const k of keys) {
    if (!isObj(cur)) return undefined;
    cur = cur[k];
  }
  return cur;
}

export type YamlLoad =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

export function loadYamlFile(file: string): YamlLoad {
  let text: string;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch (e) {
    return { ok: false, error: `cannot read file: ${(e as Error).message}` };
  }
  try {
    // uniqueKeys: duplicate mapping keys are a parse error (YAML 1.2 requires unique keys).
    const doc = parseDocument(text, { uniqueKeys: true, prettyErrors: false });
    if (doc.errors.length > 0) {
      return { ok: false, error: doc.errors.map((e) => e.message).join("; ") };
    }
    return { ok: true, value: doc.toJS() };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}

/**
 * Normalize a package-relative path. Returns null when the path is absolute,
 * escapes the package root, or is otherwise not a usable relative path.
 */
export function normalizeRelPath(p: string): string | null {
  if (!isNonEmptyString(p)) return null;
  if (p.includes("\\") || p.includes("\0")) return null;
  if (path.posix.isAbsolute(p) || /^[A-Za-z]:/.test(p)) return null;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(p)) return null; // URL, not a local path
  const norm = path.posix.normalize(p);
  if (norm === "." || norm.startsWith("../") || norm === "..") return null;
  return norm.replace(/\/$/, "");
}

export function isYamlPath(p: string): boolean {
  return /\.ya?ml$/i.test(p);
}

export function fileExists(abs: string): boolean {
  try {
    return fs.statSync(abs).isFile();
  } catch {
    return false;
  }
}

/** Resolve the real path and confirm it stays inside root (guards symlink escapes). */
export function staysInside(root: string, abs: string): boolean {
  try {
    const r = fs.realpathSync(root);
    const a = fs.realpathSync(abs);
    return a === r || a.startsWith(r + path.sep);
  } catch {
    return false;
  }
}
