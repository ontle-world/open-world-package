import * as fs from "node:fs";
import * as path from "node:path";
import { isScalar, parseDocument, visit } from "yaml";

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

/** table[key] when the table itself has that key: a document's "toString" or "constructor" is not a table entry. */
export function own<T>(table: Record<string, T>, key: unknown): T | undefined {
  return typeof key === "string" && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

/** String(value) for a JSON value, without calling a mapping's own toString (a key a YAML document may define). */
export function jsString(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined";
  if (Array.isArray(value)) return value.map((x) => (x === null || x === undefined ? "" : jsString(x))).join(",");
  if (isObj(value)) return "[object Object]";
  return String(value);
}

export type YamlLoad =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

const CORE_TAG = "tag:yaml.org,2002:";
const BAD = Symbol("bad tag");
/** The value of a scalar with an explicit YAML core tag, as the YAML 1.2 core schema reads it; BAD otherwise. */
function coerceTagged(short: string | undefined, raw: unknown): unknown {
  const s = String(raw);
  switch (short) {
    case "str": return s;
    case "null": return /^(?:~|null|Null|NULL|)$/.test(s) ? null : BAD;
    case "bool": return /^(?:true|True|TRUE)$/.test(s) ? true : /^(?:false|False|FALSE)$/.test(s) ? false : BAD;
    case "int":
      if (/^[-+]?[0-9]+$/.test(s)) return Number(s);
      if (/^0o[0-7]+$/.test(s)) return parseInt(s.slice(2), 8);
      return /^0x[0-9a-fA-F]+$/.test(s) ? parseInt(s.slice(2), 16) : BAD;
    case "float":
      if (/^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?$/.test(s)) return Number(s);
      if (/^[-+]?\.(?:inf|Inf|INF)$/.test(s)) return s.startsWith("-") ? -Infinity : Infinity;
      return /^\.(?:nan|NaN|NAN)$/.test(s) ? NaN : BAD;
    default: return BAD;
  }
}

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
    // Spec 5.2: mapping keys are strings, as in the JSON data model.
    let badKey: string | undefined;
    visit(doc, {
      Pair(_, pair) {
        if (!isScalar(pair.key) || typeof pair.key.value !== "string") {
          badKey = String(isScalar(pair.key) ? pair.key.value : pair.key);
          return visit.BREAK;
        }
      },
    });
    if (badKey !== undefined) return { ok: false, error: `mapping key ${badKey} is not a string` };
    // Spec 5.2: values are JSON values. The YAML core tags are applied (!!float 3 is the number 3); any other tag
    // (!!binary, !!set, !!timestamp, a local !note) is an error rather than a value read as plain text.
    let badTag: string | undefined;
    visit(doc, {
      Node(_, node) {
        const tag = (node as { tag?: string }).tag;
        if (tag === undefined || tag === "!") return;
        const short = tag.startsWith(CORE_TAG) ? tag.slice(CORE_TAG.length) : undefined;
        if (isScalar(node)) {
          const coerced = coerceTagged(short, node.source ?? node.value);
          if (coerced === BAD) { badTag = tag; return visit.BREAK; }
          node.value = coerced;
        } else if (short !== "map" && short !== "seq") { badTag = tag; return visit.BREAK; }
      },
    });
    if (badTag !== undefined) return { ok: false, error: `YAML tag ${badTag} is not allowed: values are JSON values` };
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

/**
 * An existing file inside the package, named by a package-relative path (relative POSIX, no leading ./).
 * Returns its absolute path, or null.
 */
export function packageFile(root: string, p: unknown): string | null {
  if (typeof p !== "string" || p.length === 0 || p.startsWith("./")) return null;
  const norm = normalizeRelPath(p);
  if (norm === null) return null;
  const abs = path.join(root, norm);
  return fileExists(abs) && staysInside(root, abs) ? abs : null;
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
