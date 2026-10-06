/**
 * The browser bundle's `node:fs`: an in-memory file system with the synchronous calls the validator makes.
 * Files live under absolute POSIX paths; directories exist implicitly above every file, or when made.
 * scripts/bundle.mjs maps `node:fs` to this module; Node builds keep the real `node:fs`.
 */
const files = new Map<string, Uint8Array>();
const dirs = new Set<string>(["/"]);
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8");

function norm(p: string): string {
  const parts: string[] = [];
  for (const seg of String(p).split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") parts.pop();
    else parts.push(seg);
  }
  return "/" + parts.join("/");
}

function noEntry(p: string): Error {
  const e = new Error(`ENOENT: no such file or directory, '${p}'`) as Error & { code: string };
  e.code = "ENOENT";
  return e;
}

function addParents(p: string): void {
  let d = p;
  while (d !== "/") {
    d = d.slice(0, d.lastIndexOf("/")) || "/";
    dirs.add(d);
  }
}

/** Put files at `prefix` (an absolute directory), replacing what was there. */
export function mount(prefix: string, entries: Record<string, Uint8Array | string>): void {
  rmSync(prefix, { recursive: true, force: true });
  const base = norm(prefix);
  dirs.add(base);
  addParents(base);
  for (const [rel, data] of Object.entries(entries)) {
    const p = norm(`${base}/${rel}`);
    files.set(p, typeof data === "string" ? encoder.encode(data) : data);
    addParents(p);
  }
}

export function reset(): void {
  files.clear();
  dirs.clear();
  dirs.add("/");
}

export function existsSync(p: string): boolean {
  const n = norm(p);
  return files.has(n) || dirs.has(n);
}

class Stats {
  constructor(private readonly file: boolean, readonly size: number) {}
  isFile(): boolean { return this.file; }
  isDirectory(): boolean { return !this.file; }
  isSymbolicLink(): boolean { return false; }
}

export function statSync(p: string): Stats {
  const n = norm(p);
  if (files.has(n)) return new Stats(true, files.get(n)!.length);
  if (dirs.has(n)) return new Stats(false, 0);
  throw noEntry(p);
}

class Dirent {
  constructor(readonly name: string, private readonly file: boolean) {}
  isFile(): boolean { return this.file; }
  isDirectory(): boolean { return !this.file; }
  isSymbolicLink(): boolean { return false; }
}

export function readdirSync(p: string, options?: { withFileTypes?: boolean }): Array<string | Dirent> {
  const n = norm(p);
  if (!dirs.has(n)) throw noEntry(p);
  const prefix = n === "/" ? "/" : n + "/";
  const names = new Map<string, boolean>();
  for (const f of files.keys()) if (f.startsWith(prefix)) {
    const rest = f.slice(prefix.length);
    const i = rest.indexOf("/");
    names.set(i < 0 ? rest : rest.slice(0, i), i < 0);
  }
  for (const d of dirs) if (d.startsWith(prefix) && d !== n) {
    const rest = d.slice(prefix.length);
    if (rest && !rest.includes("/") && !names.has(rest)) names.set(rest, false);
  }
  const sorted = [...names.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return options?.withFileTypes ? sorted.map(([name, file]) => new Dirent(name, file)) : sorted.map(([name]) => name);
}

export function readFileSync(p: string, encoding?: string | { encoding?: string }): string | Uint8Array {
  const n = norm(p);
  const data = files.get(n);
  if (!data) throw noEntry(p);
  const enc = typeof encoding === "string" ? encoding : encoding?.encoding;
  return enc ? decoder.decode(data) : data;
}

export function writeFileSync(p: string, data: string | Uint8Array): void {
  const n = norm(p);
  files.set(n, typeof data === "string" ? encoder.encode(data) : data);
  addParents(n);
}

export function mkdirSync(p: string): void {
  const n = norm(p);
  dirs.add(n);
  addParents(n);
}

let counter = 0;
export function mkdtempSync(prefix: string): string {
  const p = norm(`${prefix}${++counter}`);
  mkdirSync(p);
  return p;
}

export function rmSync(p: string, _options?: { recursive?: boolean; force?: boolean }): void {
  const n = norm(p);
  for (const f of [...files.keys()]) if (f === n || f.startsWith(n + "/")) files.delete(f);
  for (const d of [...dirs]) if (d !== "/" && (d === n || d.startsWith(n + "/"))) dirs.delete(d);
}

export function realpathSync(p: string): string {
  if (!existsSync(p)) throw noEntry(p);
  return norm(p);
}

export type { Stats };
export default { mount, reset, existsSync, statSync, readdirSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync, realpathSync };
