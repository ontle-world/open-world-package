/**
 * Spec section 11: dependency resolution over ordered package sources
 * (directory, .owp.zip archive, git) plus cross-package rules (extension definitions, semantic binding, WorldModel grounding).
 */
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { localAssetKinds, packageDocuments } from "./discovery.js";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { get, isObj, loadYamlFile, Obj } from "./util.js";
import { canon } from "./ews.js";
import { Issue } from "./context.js";
import { readZip } from "./zip.js";
import { Dependency, parseDependencies, parsePackageRef } from "./rules/dependencies.js";
import { parseContractRef } from "./rules/worldmodel.js";
import { viewExternalNames } from "./rules/world.js";
import { bindingCuries, bindingGroundingProblems, bindingSemanticProblems, mergeSchemaModels } from "./rules/binding.js";
import { compactIri, expandCurie, ontologyTerms, ontologyUses, removedTerms, replacedByRefs, schemaModel, termStatuses } from "./rules/ontology.js";
import { validatePackage, ValidationResult } from "./validate.js";

export interface Candidate {
  identity: string;
  dir: string;
  manifest: Obj;
  /** `sha256:<digest>` for archives, `git:<commit>` for git, undefined for directories. */
  revision?: string;
  source: string;
  /** Set when the candidate may not be used (e.g. archive integrity failure). */
  error?: string;
}

export interface ResolvedPackage {
  identity: string;
  kind: string;
  dir: string;
  source: string;
  revision?: string;
}

export interface ResolveOptions {
  /** Ordered global package sources. */
  sources: string[];
  /** Where archives are extracted and git sources are cloned. */
  cacheDir?: string;
}

export interface ResolutionResult extends ValidationResult {
  resolved: ResolvedPackage[];
}

function defaultCacheDir(): string {
  if (process.env.OWP_CACHE_DIR) return path.resolve(process.env.OWP_CACHE_DIR);
  const here = path.dirname(fileURLToPath(import.meta.url));
  return path.join(here, "..", ".owp-cache");
}

function sha256(buf: Buffer): string {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function readManifest(dir: string): Obj | undefined {
  const l = loadYamlFile(path.join(dir, "owp.yaml"));
  return l.ok && isObj(l.value) ? l.value : undefined;
}

function identityOf(m: Obj | undefined): string | undefined {
  const ns = get(m, "metadata", "namespace");
  const n = get(m, "metadata", "name");
  const v = get(m, "metadata", "version");
  return typeof ns === "string" && typeof n === "string" && typeof v === "string" ? `${ns}/${n}@${v}` : undefined;
}

// ---------------------------------------------------------------- archives

/**
 * Spec 7: {"format":"owp-lock/v1alpha2","manifest":"owp.yaml","manifest_sha256":hex,
 * "files":[{"path","sha256","size"}], "externals":[...]}. Hashes are lowercase hex without prefix.
 */
export const LOCK_FORMAT = "owp-lock/v1alpha2";

interface LockData {
  format: string;
  files: Map<string, { sha256: string; size?: number }>;
  manifestSha?: string;
  externals: unknown[];
}

function lockEntries(json: unknown): LockData | string {
  if (!isObj(json)) return "owp.lock.json is not a JSON object";
  if (json.format !== LOCK_FORMAT) {
    return `owp.lock.json format must be ${LOCK_FORMAT} (got ${JSON.stringify(json.format)})`;
  }
  if (json.externals !== undefined && !Array.isArray(json.externals)) return "owp.lock.json externals must be a list";
  if (json.manifest !== undefined && json.manifest !== "owp.yaml") return "owp.lock.json manifest must be owp.yaml";
  if (!Array.isArray(json.files)) return "owp.lock.json files must be a list";
  const files = new Map<string, { sha256: string; size?: number }>();
  for (const f of json.files) {
    if (!isObj(f) || typeof f.path !== "string" || typeof f.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(f.sha256)) {
      return "owp.lock.json file entries need path and a lowercase hex sha256";
    }
    if (files.has(f.path)) return `owp.lock.json lists ${f.path} twice`;
    files.set(f.path, { sha256: f.sha256, ...(typeof f.size === "number" ? { size: f.size } : {}) });
  }
  return {
    format: json.format,
    files,
    manifestSha: typeof json.manifest_sha256 === "string" ? json.manifest_sha256 : undefined,
    externals: Array.isArray(json.externals) ? json.externals : [],
  };
}

export function loadArchive(file: string, cacheDir: string, sourceLabel: string): Candidate | undefined {
  const buf = fs.readFileSync(file);
  const digest = sha256(buf);
  let entries;
  try {
    entries = readZip(buf);
  } catch (e) {
    return { identity: "", dir: "", manifest: {}, source: sourceLabel, error: `${file}: ${(e as Error).message}` };
  }
  // Spec 7: the package root is the archive root.
  const prefix = "";
  if (!entries.some((e) => e.name === "owp.yaml")) {
    return { identity: "", dir: "", manifest: {}, source: sourceLabel, error: `${file}: archive root has no owp.yaml` };
  }
  const dir = path.join(cacheDir, `zip-${digest}`);
  if (!fs.existsSync(path.join(dir, ".complete"))) {
    fs.rmSync(dir, { recursive: true, force: true });
    for (const e of entries) {
      if (!e.name.startsWith(prefix)) continue;
      const rel = e.name.slice(prefix.length);
      const target = path.join(dir, rel);
      if (!target.startsWith(dir + path.sep)) continue; // zip-slip guard
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, e.data);
    }
    fs.writeFileSync(path.join(dir, ".complete"), "");
  }
  const manifest = readManifest(dir) ?? {};
  const cand: Candidate = { identity: identityOf(manifest) ?? "", dir, manifest, revision: `sha256:${digest}`, source: sourceLabel };

  // Integrity: every lock entry verifies and every packaged file is listed.
  const lock = entries.find((e) => e.name === `${prefix}owp.lock.json`);
  if (!lock) {
    cand.error = `${file}: archive has no owp.lock.json`;
    return cand;
  }
  let lockJson: unknown;
  try {
    lockJson = JSON.parse(lock.data.toString("utf8"));
  } catch {
    cand.error = `${file}: owp.lock.json is not valid JSON`;
    return cand;
  }
  const lockData = lockEntries(lockJson);
  if (typeof lockData === "string") {
    cand.error = `${file}: ${lockData}`;
    return cand;
  }
  const want = lockData.files;
  const have = new Map(entries.filter((e) => e.name !== "owp.lock.json").map((e) => [e.name, e.data]));
  for (const [p, h] of want) {
    const data = have.get(p);
    if (!data) {
      cand.error = `${file}: owp.lock.json lists ${p} which is not in the archive`;
      return cand;
    }
    if (sha256(data) !== h.sha256 || (h.size !== undefined && h.size !== data.length)) {
      cand.error = `${file}: ${p} does not match its owp.lock.json hash/size`;
      return cand;
    }
  }
  for (const p of have.keys()) {
    if (!want.has(p)) {
      cand.error = `${file}: ${p} is not listed in owp.lock.json`;
      return cand;
    }
  }
  const man = have.get("owp.yaml");
  if (lockData.manifestSha !== undefined && man && sha256(man) !== lockData.manifestSha) {
    cand.error = `${file}: manifest_sha256 does not match owp.yaml`;
    return cand;
  }
  if (lockData.format === "owp-lock/v1alpha2") {
    const problem = externalsProblem(lockData, manifest, have);
    if (problem) cand.error = `${file}: ${problem}`;
  }
  return cand;
}

/**
 * Spec 7, owp-lock/v1alpha2: `externals` (without vendoredPath) equals the manifest's bound ExternalRefs in
 * manifest order; a vendoredPath is a locked file whose bytes match the entry's digest.
 */
function externalsProblem(lock: LockData, manifest: Obj, have: Map<string, Buffer>): string | undefined {
  const recorded = lock.externals.map((e) => (isObj(e) ? Object.fromEntries(Object.entries(e).filter(([k]) => k !== "vendoredPath")) : e));
  if (canon(recorded) !== canon(lockExternals(manifest))) return "owp.lock.json externals do not match the manifest's external references";
  for (const e of lock.externals) {
    if (!isObj(e) || e.vendoredPath === undefined) continue;
    const vp = e.vendoredPath;
    if (typeof vp !== "string" || !lock.files.has(vp)) return `vendored file ${JSON.stringify(vp)} is not locked`;
    const data = have.get(vp);
    if (typeof e.digest === "string" && (!data || `sha256:${sha256(data)}` !== e.digest)) return `vendored file ${vp} does not match its digest`;
  }
  return undefined;
}

/**
 * Spec 7: the `externals` entries for a manifest — each bound ExternalRef (status absent, null, or bound) of
 * spec.assets[].ref, then spec.ontology.externalImports[].ref, with pointer, provider, uri, and
 * revision/digest/mediaType when declared.
 */
export function lockExternals(manifest: Obj): Obj[] {
  const out: Obj[] = [];
  const add = (pointer: string, ref: unknown) => {
    if (!isObj(ref) || (ref.status !== undefined && ref.status !== null && ref.status !== "bound")) return; // null counts as absent (spec 5.1)
    const entry: Obj = { pointer, provider: ref.provider ?? null, uri: ref.uri ?? null };
    for (const k of ["revision", "digest", "mediaType"]) if (ref[k] !== undefined && ref[k] !== null) entry[k] = ref[k];
    out.push(entry);
  };
  const assets = get(manifest, "spec", "assets");
  (Array.isArray(assets) ? assets : []).forEach((a, i) => isObj(a) && add(`/spec/assets/${i}/ref`, a.ref));
  const imports = get(manifest, "spec", "ontology", "externalImports");
  (Array.isArray(imports) ? imports : []).forEach((imp, i) => isObj(imp) && add(`/spec/ontology/externalImports/${i}/ref`, imp.ref));
  return out;
}

// ---------------------------------------------------------------- sources

function listDirectoryCandidates(dir: string, cacheDir: string, label: string): Candidate[] {
  const out: Candidate[] = [];
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return out;
  const addPkg = (d: string) => {
    if (!fs.existsSync(path.join(d, "owp.yaml"))) return;
    const m = readManifest(d);
    const id = identityOf(m);
    if (m && id) out.push({ identity: id, dir: d, manifest: m, source: label });
  };
  const subdirs = (d: string) =>
    fs
      .readdirSync(d, { withFileTypes: true })
      .filter((e) => e.isDirectory() && !e.name.startsWith("."))
      .map((e) => path.join(d, e.name))
      .sort();
  addPkg(dir);
  const level1 = subdirs(dir);
  level1.forEach(addPkg);
  for (const d of level1) subdirs(d).forEach(addPkg);
  for (const f of fs.readdirSync(dir).filter((n) => n.endsWith(".owp.zip")).sort()) {
    const c = loadArchive(path.join(dir, f), cacheDir, label);
    if (c && c.identity) out.push(c);
  }
  return out;
}

/** `git+<url>@<rev>[#subdir=<path>]` */
export function parseGitSource(s: string): { url: string; rev: string; subdir?: string } | null {
  if (!s.startsWith("git+")) return null;
  let body = s.slice(4);
  let subdir: string | undefined;
  const hash = body.indexOf("#");
  if (hash >= 0) {
    const frag = body.slice(hash + 1);
    body = body.slice(0, hash);
    const m = /^subdir=(.+)$/.exec(frag);
    if (!m) return null;
    subdir = m[1];
  }
  const at = body.lastIndexOf("@");
  if (at <= 0) return null;
  const url = body.slice(0, at);
  const rev = body.slice(at + 1);
  if (!url || !rev) return null;
  return { url, rev, subdir };
}

class Source {
  private cache?: Candidate[];
  public error?: string;
  constructor(public readonly spec: string, private readonly baseDir: string, private readonly cacheDir: string) {}

  candidates(): Candidate[] {
    if (this.cache) return this.cache;
    this.cache = [];
    try {
      const git = parseGitSource(this.spec);
      if (this.spec.startsWith("git+")) {
        if (!git) throw new Error(`malformed git source ${this.spec}`);
        const key = crypto.createHash("sha1").update(git.url + "@" + git.rev).digest("hex");
        const dir = path.join(this.cacheDir, `git-${key}`);
        if (!fs.existsSync(path.join(dir, ".git"))) {
          fs.rmSync(dir, { recursive: true, force: true });
          fs.mkdirSync(this.cacheDir, { recursive: true });
          const url = /^[a-z]+:\/\//i.test(git.url) || git.url.includes("@") ? git.url : path.resolve(this.baseDir, git.url);
          execFileSync("git", ["clone", "--quiet", url, dir], { stdio: "pipe" });
        } else if (!/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(git.rev)) {
          // A tag or branch can move: update the cached clone (offline, the cached refs are used).
          try {
            execFileSync("git", ["-C", dir, "fetch", "--quiet", "--force", "--tags", "origin", "+refs/heads/*:refs/remotes/origin/*"], { stdio: "pipe" });
          } catch { /* offline */ }
        }
        try { // a branch: its fetched head, not the local branch made at clone time
          execFileSync("git", ["-C", dir, "checkout", "--quiet", "--detach", `refs/remotes/origin/${git.rev}`], { stdio: "pipe" });
        } catch {
          execFileSync("git", ["-C", dir, "checkout", "--quiet", git.rev], { stdio: "pipe" });
        }
        const commit = execFileSync("git", ["-C", dir, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
        const root = git.subdir ? path.join(dir, git.subdir) : dir;
        this.cache = listDirectoryCandidates(root, this.cacheDir, this.spec).map((c) =>
          c.revision ? c : { ...c, revision: `git:${commit}` },
        );
      } else {
        const p = path.resolve(this.baseDir, this.spec);
        if (p.endsWith(".owp.zip")) {
          if (!fs.existsSync(p)) throw new Error(`archive source ${p} does not exist`);
          const c = loadArchive(p, this.cacheDir, this.spec);
          this.cache = c ? [c] : [];
        } else {
          if (!fs.existsSync(p)) throw new Error(`directory source ${p} does not exist`);
          this.cache = listDirectoryCandidates(p, this.cacheDir, this.spec);
        }
      }
    } catch (e) {
      this.error = (e as Error).message;
    }
    return this.cache;
  }

  find(identity: string): Candidate | undefined {
    if (this.spec.startsWith("index:")) return this.indexFind(identity);
    return this.candidates().find((c) => c.identity === identity);
  }

  /**
   * Spec 11 "Further source types" + 11.1: `index:<path of a PackageIndex>`. The listed archive's bytes must
   * match the entry digest before the archive is verified. This implementation reads local indexes
   * (a path or a file: URL); http(s) indexes are reported as unusable sources.
   */
  private indexFind(identity: string): Candidate | undefined {
    const location = this.spec.slice("index:".length);
    try {
      if (/^[a-z][a-z0-9+.-]*:\/\//i.test(location) && !location.startsWith("file://")) {
        throw new Error(`index ${location}: only local package indexes (a path or file: URL) are supported by this implementation`);
      }
      const file = location.startsWith("file://") ? fileURLToPath(location) : path.resolve(this.baseDir, location);
      const index = JSON.parse(fs.readFileSync(file, "utf8")) as unknown;
      if (!isObj(index) || index.kind !== "PackageIndex" || !Array.isArray(index.packages)) throw new Error(`${location} is not a PackageIndex`);
      const entry = index.packages.find((p) => isObj(p) && p.identity === identity);
      if (!isObj(entry)) return undefined;
      if (typeof entry.archive !== "string") throw new Error(`${location}: entry ${identity} has no archive`);
      const archive = entry.archive.startsWith("file://") ? fileURLToPath(entry.archive) : path.resolve(path.dirname(file), entry.archive);
      const digest = `sha256:${sha256(fs.readFileSync(archive))}`;
      if (entry.digest !== digest) {
        return { identity, dir: "", manifest: {}, source: this.spec, error: `${entry.archive} digest ${digest} does not match the index digest ${String(entry.digest)}` };
      }
      const cand = loadArchive(archive, this.cacheDir, this.spec);
      return cand && (cand.identity === identity || cand.error) ? cand : { identity, dir: "", manifest: {}, source: this.spec, error: `${entry.archive} does not contain ${identity}` };
    } catch (e) {
      this.error = (e as Error).message;
      return undefined;
    }
  }
}

// ---------------------------------------------------------------- resolution

/** Spec 11: package kinds each kind may depend on (dependencies declared with `as` are extensions and exempt). */
export const DEPENDENCY_DIRECTIONS: Record<string, string[]> = {
  OntologyPackage: ["OntologyPackage"],
  WorldPackage: ["OntologyPackage", "WorldPackage"],
  WorldModelPackage: ["OntologyPackage", "WorldPackage", "WorldModelPackage"],
};

interface Node {
  identity: string;
  kind: string;
  dir: string;
  manifest: Obj;
  deps: Dependency[];
}

/**
 * Validate `dir` and resolve its dependency closure (spec 11).
 * The result is valid only if the package itself and the whole closure are valid.
 */
export function validateWithResolution(dir: string, opts: ResolveOptions): ResolutionResult {
  const base = validatePackage(dir);
  const errors: Issue[] = [...base.errors];
  const warnings: Issue[] = [...base.warnings];
  const resolved: ResolvedPackage[] = [];
  const cacheDir = path.resolve(opts.cacheDir ?? defaultCacheDir());
  const cwd = process.cwd();
  const globals = opts.sources.map((s) => new Source(s, cwd, cacheDir));
  const err = (code: string, message: string) => errors.push({ code, message });

  const rootDir = path.resolve(dir);
  const rootManifest = readManifest(rootDir);
  const rootId = identityOf(rootManifest);
  if (!rootManifest || !rootId) {
    return { ...base, errors, warnings, valid: false, resolved };
  }
  for (const p of parseDependencies(rootManifest).problems) err("resolve.reference", p);
  const root: Node = {
    identity: rootId,
    kind: typeof rootManifest.kind === "string" ? rootManifest.kind : "",
    dir: rootDir,
    manifest: rootManifest,
    deps: parseDependencies(rootManifest).deps,
  };

  const versionOf = new Map<string, string>(); // ns/name -> version
  const nodes = new Map<string, Node>(); // identity -> node
  const key = (id: string) => id.slice(0, id.lastIndexOf("@"));
  versionOf.set(key(rootId), rootId.slice(rootId.lastIndexOf("@") + 1));
  nodes.set(rootId, root);
  const reported = new Set<string>();

  const visit = (node: Node, stack: string[]) => {
    // Spec 11: a dependency that is not a package reference cannot be resolved (also reported as manifest.dependency).
    for (const p of parseDependencies(node.manifest).problems) {
      if (!/\.source must be/.test(p)) err("resolve.reference", `${node.identity}: ${p}`);
    }
    for (const dep of node.deps) {
      if (stack.includes(dep.ref)) {
        err("resolve.cycle", `dependency cycle: ${[...stack, dep.ref].join(" -> ")}`);
        continue;
      }
      const k = `${dep.namespace}/${dep.name}`;
      const have = versionOf.get(k);
      if (have !== undefined && have !== dep.version) {
        err("resolve.version-conflict", `version conflict for ${k}: ${k}@${have} and ${dep.ref} (required by ${node.identity})`);
        continue;
      }
      if (nodes.has(dep.ref)) continue; // already resolved (diamond)
      if (reported.has(dep.ref)) continue; // already failed

      const sources = [
        ...(dep.source ? [new Source(dep.source, node.dir, cacheDir)] : []),
        ...globals,
      ];
      let cand: Candidate | undefined;
      for (const s of sources) {
        cand = s.find(dep.ref);
        // Spec 11: a source that cannot be read or verified is an error, never a silent fallback.
        if (s.error) err("resolve.source", `source ${s.spec}: ${s.error}`);
        if (cand) break;
      }
      if (!cand) {
        reported.add(dep.ref);
        err("resolve.unresolved", `cannot resolve ${dep.ref} (required by ${node.identity}) in any package source`);
        continue;
      }
      if (cand.error) {
        // As in the Python reference: the reason, then the dependency stays unresolved.
        reported.add(dep.ref);
        err("resolve.source", `${dep.ref}: ${cand.error}`);
        err("resolve.unresolved", `cannot resolve ${dep.ref} (required by ${node.identity}): the copy found is unusable`);
        continue;
      }
      versionOf.set(k, dep.version);
      const v = validatePackage(cand.dir);
      if (!v.valid) {
        err("resolve.dependency-invalid", `resolved package ${dep.ref} (${cand.source}) is invalid: ${v.errors.map((e) => e.message).join("; ")}`);
      }
      const child: Node = {
        identity: dep.ref,
        kind: typeof cand.manifest.kind === "string" ? cand.manifest.kind : "",
        dir: cand.dir,
        manifest: cand.manifest,
        deps: parseDependencies(cand.manifest).deps,
      };
      nodes.set(dep.ref, child);
      resolved.push({ identity: dep.ref, kind: child.kind, dir: cand.dir, source: cand.source, ...(cand.revision ? { revision: cand.revision } : {}) });
      visit(child, [...stack, dep.ref]);
    }
  };
  visit(root, [rootId]);

  // Spec 11 + 13.1: a dependency declared with `as` resolves to a package with spec.extensionDefinition.
  for (const n of nodes.values()) {
    for (const d of n.deps) {
      const target = d.as !== undefined ? nodes.get(d.ref) : undefined;
      if (target && !isObj(get(target.manifest, "spec", "extensionDefinition"))) {
        err("extension.definition", `${n.identity}: extension "${d.as}" resolves to ${d.ref}, which declares no spec.extensionDefinition`);
      }
    }
  }

  // Spec 11: dependencies point down the hierarchy Ontology <- World <- World Model (warning).
  for (const n of nodes.values()) {
    const allowed = Object.prototype.hasOwnProperty.call(DEPENDENCY_DIRECTIONS, n.kind) ? DEPENDENCY_DIRECTIONS[n.kind] : undefined;
    for (const d of n.deps) {
      const target = d.as === undefined ? nodes.get(d.ref) : undefined;
      if (allowed && target && !allowed.includes(target.kind)) {
        warnings.push({ code: "resolve.dependency-direction", message: `${n.identity} (${n.kind}) depends on ${d.ref} (${target.kind}); allowed for ${n.kind}: ${allowed.join(", ")}` });
      }
    }
  }

  // Spec 6: a View's external Worlds resolve to WorldPackages; names taken from them are in their boundary.
  for (const n of nodes.values()) {
    if (n.kind !== "WorldPackage") continue;
    // Discovered Views only: listed PackageExample files are not assets (spec 5).
    const examples = new Set([...localAssetKinds(n.dir, n.manifest)].filter(([, k]) => k === "PackageExample").map(([p]) => p));
    for (const d of packageDocuments(n.dir, examples)) {
      if (!d.ok || !isObj(d.value) || d.value.kind !== "WorldViewProfile") continue;
      const refs = get(d.value, "spec", "externalWorldRefs");
      for (const r of Array.isArray(refs) ? refs : []) {
        const target = typeof r === "string" ? nodes.get(r) : undefined;
        if (target && target.kind !== "WorldPackage") err("view.external-world", `${n.identity}: ${d.rel}: external World ${r} resolves to a ${target.kind}, not a WorldPackage`);
      }
      for (const [r, name] of viewExternalNames(d.value)) {
        const target = nodes.get(r);
        const included = target && target.kind === "WorldPackage" ? get(target.manifest, "spec", "world", "boundary", "included") : undefined;
        if (Array.isArray(included) && included.length > 0 && !included.includes(name)) {
          warnings.push({ code: "view.outside-world", message: `${n.identity}: ${d.rel}: projection.include '${r}#${name}' is not in that World's spec.world.boundary.included` });
        }
      }
    }
  }

  // Spec 14: SemanticBinding CURIEs resolve against the package's dependency OntologyPackages.
  for (const n of nodes.values()) for (const p of bindingGrounding(n, nodes)) err(p.rule, `${n.identity}: ${p.msg}`);
  for (const n of nodes.values()) for (const p of bindingSemantics(n, nodes)) warnings.push({ code: p.rule, message: `${n.identity}: ${p.msg}` });
  for (const n of nodes.values()) for (const p of ontologyDependencyProblems(n, nodes)) err(p.rule, `${n.identity}: ${p.msg}`);
  for (const n of nodes.values()) for (const p of lifecycleReferences(n, nodes)) warnings.push({ code: p.rule, message: `${n.identity}: ${p.msg}` });

  // Cross-package rules for every WorldModelPackage in the closure.
  for (const n of nodes.values()) {
    if (n.kind === "WorldModelPackage") for (const m of crossPackageProblems(n, nodes)) err(m.rule, `${n.identity}: ${m.msg}`);
  }

  return { ...base, errors, warnings, valid: errors.length === 0, resolved };
}

/** Spec 3.1: a term an OntologyPackage uses from the namespace of an OntologyPackage it depends on is defined there. */
function ontologyDependencyProblems(pkg: Node, nodes: Map<string, Node>): Array<{ rule: string; msg: string }> {
  if (pkg.kind !== "OntologyPackage") return [];
  const deps = pkg.deps
    .map((d) => nodes.get(d.ref))
    .filter((d): d is Node => d !== undefined && d.kind === "OntologyPackage")
    .map((d) => ({ ref: d.identity, iri: get(d.manifest, "spec", "ontology", "iri"), terms: ontologyTerms(d.dir, d.manifest).terms }))
    .filter((d): d is { ref: string; iri: string; terms: Set<string> } => typeof d.iri === "string" && d.iri.length > 0);
  if (deps.length === 0) return [];
  return ontologyUses(pkg.dir, pkg.manifest).flatMap(({ file, where, value, iri }) =>
    deps
      .filter((d) => iri.startsWith(d.iri) && !d.terms.has(iri))
      .map((d) => ({ rule: "ontology.dependency-term", msg: `${file}: ${where} "${value}" (${iri}) is not a term of ${d.ref}` })),
  );
}

/**
 * Appendix C.1 (experimental): a `replacedBy` in a dependency ontology's namespace names a term it defines; owp-yaml
 * schemas, SemanticBindings, and the declared `query.terms` of KnowledgeExtractionProfiles are told when a term they
 * use from a dependency ontology is deprecated or removed; and declared query terms name terms of it.
 */
function lifecycleReferences(pkg: Node, nodes: Map<string, Node>): Array<{ rule: string; msg: string }> {
  const ontologies = pkg.deps
    .map((d) => nodes.get(d.ref))
    .filter((d): d is Node => d !== undefined && d.kind === "OntologyPackage")
    .map((d) => ({
      ref: d.identity,
      iri: get(d.manifest, "spec", "ontology", "iri"),
      ...ontologyTerms(d.dir, d.manifest),
      statuses: termStatuses(d.dir, d.manifest),
      removed: removedTerms(d.dir, d.manifest),
    }));
  const deps = ontologies.filter((d) => typeof d.iri === "string" && d.iri.length > 0);
  if (deps.length === 0) return [];
  const out: Array<{ rule: string; msg: string }> = [];
  const uses: Array<{ file: string; where: string; value: string; iri: string; prefixes: Record<string, unknown> }> = [];
  if (pkg.kind === "OntologyPackage") {
    for (const r of replacedByRefs(pkg.dir, pkg.manifest)) {
      for (const d of deps) {
        if (r.iri.startsWith(d.iri as string) && !d.terms.has(r.iri)) {
          out.push({ rule: "experimental.reference", msg: `${r.file}: ${r.where} ${JSON.stringify(r.value)} (${r.iri}) is not a term of ${d.ref}` });
        }
      }
    }
    const own = get(pkg.manifest, "spec", "ontology", "prefixes");
    for (const u of ontologyUses(pkg.dir, pkg.manifest)) uses.push({ ...u, prefixes: isObj(own) ? own : {} });
  }
  const prefixes: Record<string, string> = Object.create(null);
  for (const d of ontologies) for (const [name, iri] of Object.entries(d.prefixes)) if (!(name in prefixes)) prefixes[name] = iri; // a conflict is grounding.prefix-conflict
  const kinds = [...localAssetKinds(pkg.dir, pkg.manifest)].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  for (const [rel, kind] of kinds) {
    if (kind !== "SemanticBinding") continue;
    const l = loadYamlFile(path.join(pkg.dir, rel));
    for (const [where, value] of bindingCuries(l.ok ? l.value : undefined)) {
      const iri = typeof value === "string" ? expandCurie(value, prefixes) : null;
      if (iri !== null) uses.push({ file: rel, where, value: value as string, iri, prefixes });
    }
  }
  for (const [rel, kind] of kinds) {
    if (kind !== "KnowledgeExtractionProfile") continue;
    const l = loadYamlFile(path.join(pkg.dir, rel));
    const declared = get(l.ok ? l.value : undefined, "spec", "query", "terms");
    (Array.isArray(declared) ? declared : []).forEach((value, i) => {
      if (typeof value !== "string") return;
      const where = `spec.query.terms[${i}]`;
      const iri = expandCurie(value, prefixes);
      if (iri === null) {
        out.push({ rule: "experimental.reference", msg: `${rel}: ${where} ${JSON.stringify(value)} uses a prefix that no dependency OntologyPackage declares` });
        return;
      }
      uses.push({ file: rel, where, value, iri, prefixes });
      for (const d of deps) {
        if (iri.startsWith(d.iri as string) && !d.terms.has(iri) && !d.removed.has(iri)) {
          out.push({ rule: "experimental.reference", msg: `${rel}: ${where} ${JSON.stringify(value)} (${iri}) is not a term of ${d.ref}` });
        }
      }
    });
  }
  for (const u of uses) {
    for (const d of deps) {
      const removed = d.removed.get(u.iri);
      const s = d.statuses.get(u.iri);
      let gone: string;
      let replaced: string[];
      if (removed) {
        gone = removed.removedIn ? `was removed from ${d.ref.slice(0, d.ref.lastIndexOf("@"))} in ${removed.removedIn}` : `is removed in ${d.ref}`;
        replaced = removed.replacedBy;
      } else if (s?.status === "deprecated") {
        gone = `is deprecated in ${d.ref}`;
        replaced = s.replacedBy;
      } else continue;
      const instead = replaced.length ? `; replaced by ${replaced.map((r) => compactIri(r, u.prefixes)).join(", ")}` : "";
      out.push({ rule: "experimental.reference", msg: `${u.file}: ${u.where} ${JSON.stringify(u.value)} (${u.iri}) ${gone}${instead}` });
    }
  }
  return out;
}

/** Spec 14 warnings: binding paths and value maps against the owp-yaml schemas of the dependency ontologies. */
function bindingSemantics(pkg: Node, nodes: Map<string, Node>): Array<{ rule: string; msg: string }> {
  const docs: Array<[string, unknown]> = [];
  for (const [rel, kind] of localAssetKinds(pkg.dir, pkg.manifest)) {
    if (kind !== "SemanticBinding") continue;
    const l = loadYamlFile(path.join(pkg.dir, rel));
    docs.push([rel, l.ok ? l.value : undefined]);
  }
  if (docs.length === 0) return [];
  const ontologies = pkg.deps.map((d) => nodes.get(d.ref)).filter((d): d is Node => d !== undefined && d.kind === "OntologyPackage");
  if (ontologies.length === 0) return [];
  const prefixes: Record<string, string> = Object.create(null);
  for (const o of ontologies) for (const [k, v] of Object.entries(ontologyTerms(o.dir, o.manifest).prefixes)) if (!(k in prefixes)) prefixes[k] = v;
  return bindingSemanticProblems(docs, prefixes, mergeSchemaModels(ontologies.map((o) => schemaModel(o.dir, o.manifest))));
}

function bindingGrounding(pkg: Node, nodes: Map<string, Node>): Array<{ rule: string; msg: string }> {
  const docs: Array<[string, unknown]> = [];
  for (const [rel, kind] of localAssetKinds(pkg.dir, pkg.manifest)) {
    if (kind !== "SemanticBinding") continue;
    const l = loadYamlFile(path.join(pkg.dir, rel));
    docs.push([rel, l.ok ? l.value : undefined]);
  }
  if (docs.length === 0) return [];
  const ontologies = pkg.deps
    .map((d) => nodes.get(d.ref))
    .filter((d): d is Node => d !== undefined && d.kind === "OntologyPackage")
    .map((d) => ({ ref: d.identity, ...ontologyTerms(d.dir, d.manifest) }));
  return bindingGroundingProblems(docs, ontologies);
}

function crossPackageProblems(model: Node, nodes: Map<string, Node>): Array<{ rule: string; msg: string }> {
  const out: Array<{ rule: string; msg: string }> = [];
  const sg = get(model.manifest, "spec", "worldModel", "semanticGrounding");
  const worldRef = get(sg, "worldRef");
  if (typeof worldRef !== "string") return out; // reported by single-package validation
  if (!model.deps.some((d) => d.ref === worldRef)) {
    out.push({ rule: "grounding.world-not-dependency", msg: `semanticGrounding.worldRef ${worldRef} MUST be listed in spec.dependencies` });
    return out;
  }
  const world = nodes.get(worldRef);
  if (!world) return out; // unresolvable: already reported
  if (world.kind !== "WorldPackage") {
    out.push({ rule: "grounding.world-kind", msg: `semanticGrounding.worldRef ${worldRef} resolves to a ${world.kind}, not a WorldPackage` });
    return out;
  }
  const worldKinds = localAssetKinds(world.dir, world.manifest);
  const assetKind = (p: string): string | undefined => worldKinds.get(p);
  const paths = (key: string) => {
    const list = get(sg, key);
    return (Array.isArray(list) ? list : [])
      .map((e) => parseContractRef(e, worldRef))
      .filter((r): r is { path: string } => "path" in r)
      .map((r) => r.path);
  };
  const viewPaths = paths("compatibleWorldViews");
  const compilerPaths = paths("compatibleStateCompilers");
  for (const p of viewPaths) {
    const k = assetKind(p);
    if (k !== "WorldViewProfile") {
      const views = [...worldKinds].filter(([, kind]) => kind === "WorldViewProfile").map(([v]) => v).sort();
      out.push({ rule: "grounding.world-view", msg: `compatible World View ${worldRef}#${p} is ${k ? `a ${k}` : "not an asset"} in ${worldRef}; expected a WorldViewProfile (its Views: ${views.join(", ") || "none"})` });
    }
  }
  for (const p of compilerPaths) {
    const k = assetKind(p);
    if (k !== "StateCompilerProfile") {
      out.push({ rule: "grounding.state-compiler", msg: `compatible State Compiler ${worldRef}#${p} is ${k ? `a ${k}` : "not an asset"} in ${worldRef}; expected a StateCompilerProfile` });
      continue;
    }
    const doc = loadYamlFile(path.join(world.dir, p));
    const wv = doc.ok ? get(doc.value, "spec", "worldViewRef") : undefined;
    if (typeof wv !== "string" || !viewPaths.includes(wv)) {
      out.push({ rule: "grounding.compiler-view", msg: `compatible State Compiler ${worldRef}#${p} has spec.worldViewRef ${JSON.stringify(wv)}, which is not one of the model's compatible View paths` });
    }
  }
  return out;
}

export { parsePackageRef };
