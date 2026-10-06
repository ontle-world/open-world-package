/**
 * The browser entry point (scripts/bundle.mjs builds dist-browser/owp-validator.js from it): check a package the user
 * drops into a page, without uploading it. The validator, resolver, and report are the same code as the CLI; only the
 * platform differs (memfs.ts and the other modules in this directory stand in for Node's).
 *
 * Dependencies resolve through a PackageIndex (spec 11.1) fetched over HTTP: its archives are fetched, checked against
 * their digests, unpacked, and given to the resolver as a directory source.
 */
import { mount, readFileSync, reset } from "./memfs.js";
import { createHash } from "./crypto.js";
import { unzip } from "./unzip.js";
import { packageReport } from "../report.js";
import { validateWithResolution } from "../resolve.js";
import { validatePackage } from "../validate.js";
import { get, isObj, loadYamlFile, Obj } from "../util.js";

const ROOT = "/pkg";
const DEPS = "/deps";

export interface CheckOptions {
  /** URL of a PackageIndex to resolve dependencies from (spec 11.1). */
  indexUrl?: string;
  fetch?: typeof fetch;
}

export interface CheckResult {
  identity?: string;
  valid: boolean;
  errors: Array<{ code: string; message: string }>;
  warnings: Array<{ code: string; message: string }>;
  declaredProfile?: string;
  satisfiedProfile?: string | null;
  /** Dependencies fetched from the index, by identity. */
  resolved: string[];
  /** Dependencies that are not in the index: cross-package rules were not checked. */
  unresolved: string[];
  /** The PackageReport; empty when the manifest cannot be read. */
  report: Obj;
  card?: { path: string; text: string };
}

const hex = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");

/** Drop a common top folder when every path is under one that holds owp.yaml (a dropped directory). */
function packageRoot(files: Record<string, Uint8Array>): Record<string, Uint8Array> {
  const names = Object.keys(files);
  if (names.includes("owp.yaml")) return files;
  const tops = new Set(names.map((n) => n.split("/")[0]));
  const [top] = [...tops];
  if (tops.size === 1 && names.includes(`${top}/owp.yaml`)) {
    return Object.fromEntries(names.map((n) => [n.slice(top.length + 1), files[n]]));
  }
  throw new Error("no owp.yaml at the root of what was dropped");
}

/** An archive's files, after checking every file against owp.lock.json (spec 7). */
async function archiveFiles(bytes: Uint8Array): Promise<Record<string, Uint8Array>> {
  const files = await unzip(bytes);
  const lockBytes = files["owp.lock.json"];
  if (!lockBytes) throw new Error("archive has no owp.lock.json");
  const lock = JSON.parse(new TextDecoder().decode(lockBytes));
  const locked = new Map<string, string>((lock.files ?? []).map((f: Obj) => [String(f.path), String(f.sha256)]));
  for (const [name, data] of Object.entries(files)) {
    if (name === "owp.lock.json") continue;
    if (!locked.has(name)) throw new Error(`archive file ${name} is not in owp.lock.json`);
    if (hex(data) !== locked.get(name)) throw new Error(`archive file ${name} does not match its owp.lock.json hash`);
  }
  for (const name of locked.keys()) if (!(name in files)) throw new Error(`owp.lock.json lists ${name}, which is not in the archive`);
  return files;
}

function dependencyRefs(dir: string): string[] {
  const loaded = loadYamlFile(`${dir}/owp.yaml`);
  const deps = loaded.ok ? get(loaded.value, "spec", "dependencies") : undefined;
  return (Array.isArray(deps) ? deps : []).map((d) => (isObj(d) ? d.ref : d)).filter((r): r is string => typeof r === "string");
}

/** Fetch the dependency closure from a PackageIndex into DEPS; returns the identities found and those not in the index. */
async function fetchDependencies(indexUrl: string, doFetch: typeof fetch): Promise<{ resolved: string[]; unresolved: string[] }> {
  const index = await (await doFetch(indexUrl)).json();
  const entries = new Map<string, Obj>((Array.isArray(index?.packages) ? index.packages : []).map((p: Obj) => [String(p.identity), p]));
  const resolved: string[] = [];
  const unresolved: string[] = [];
  const todo = dependencyRefs(ROOT);
  const seen = new Set<string>();
  while (todo.length) {
    const ref = todo.shift()!;
    if (seen.has(ref)) continue;
    seen.add(ref);
    const entry = entries.get(ref);
    if (!entry) {
      unresolved.push(ref);
      continue;
    }
    const bytes = new Uint8Array(await (await doFetch(new URL(String(entry.archive), indexUrl).href)).arrayBuffer());
    if (`sha256:${hex(bytes)}` !== entry.digest) throw new Error(`${ref}: the archive does not match its index digest`);
    const dir = `${DEPS}/${ref.replace(/[/@]/g, "-")}`;
    mount(dir, await archiveFiles(bytes));
    resolved.push(ref);
    todo.push(...dependencyRefs(dir));
  }
  return { resolved, unresolved };
}

/**
 * Check a package: `files` maps package-relative paths to bytes (a dropped folder), or `archive` holds an .owp.zip.
 * The result has the verdict (with cross-package rules when the dependencies resolve), the PackageReport, and the card.
 */
export async function check(input: { files?: Record<string, Uint8Array>; archive?: Uint8Array }, options: CheckOptions = {}): Promise<CheckResult> {
  reset();
  const doFetch = options.fetch ?? fetch;
  const files = input.archive ? await archiveFiles(input.archive) : packageRoot(input.files ?? {});
  mount(ROOT, files);
  let resolved: string[] = [];
  let unresolved: string[] = [];
  if (options.indexUrl && dependencyRefs(ROOT).length) ({ resolved, unresolved } = await fetchDependencies(options.indexUrl, doFetch));
  // With every dependency fetched, the cross-package rules are checked too (validate --resolve); otherwise the package
  // alone, as `ontle validate` does when a dependency is not found.
  const result = resolved.length && !unresolved.length
    ? validateWithResolution(ROOT, { sources: [DEPS], cacheDir: "/cache" })
    : validatePackage(ROOT);
  let report: Obj;
  try {
    report = packageReport(ROOT);
  } catch {
    report = {}; // no readable manifest: the verdict says why
  }
  if (input.archive && report.kind) {
    report.integrity = { digest: `sha256:${hex(input.archive)}`, size: input.archive.length, files: Object.keys(files).length, signatureBundle: false };
  }
  const cardPath = isObj(report.card) && typeof report.card.path === "string" ? report.card.path : undefined;
  return {
    identity: result.identity,
    valid: result.valid,
    errors: result.errors,
    warnings: result.warnings,
    declaredProfile: result.declaredProfile,
    satisfiedProfile: result.satisfiedProfile,
    resolved,
    unresolved,
    report,
    card: cardPath ? { path: cardPath, text: readFileSync(`${ROOT}/${cardPath}`, "utf8") as string } : undefined,
  };
}

export { unzip };
