/** The browser bundle's `node:path`: POSIX paths only (the in-memory file system's). */
export const sep = "/";
export const delimiter = ":";

function normalizeParts(p: string): string {
  const abs = p.startsWith("/");
  const parts: string[] = [];
  for (const seg of p.split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") {
      if (parts.length && parts[parts.length - 1] !== "..") parts.pop();
      else if (!abs) parts.push("..");
    } else parts.push(seg);
  }
  const out = (abs ? "/" : "") + parts.join("/");
  return out || (abs ? "/" : ".");
}

export function normalize(p: string): string { return normalizeParts(p); }
export function join(...parts: string[]): string { return normalizeParts(parts.filter((x) => x !== "").join("/")); }
export function isAbsolute(p: string): boolean { return p.startsWith("/"); }
export function resolve(...parts: string[]): string {
  let out = "";
  for (const p of parts) out = p.startsWith("/") ? p : `${out}/${p}`;
  return normalizeParts(out.startsWith("/") ? out : `/${out}`);
}
export function dirname(p: string): string {
  const n = normalizeParts(p);
  const i = n.lastIndexOf("/");
  return i < 0 ? "." : i === 0 ? "/" : n.slice(0, i);
}
export function basename(p: string, ext?: string): string {
  const b = normalizeParts(p).split("/").pop() ?? "";
  return ext && b.endsWith(ext) ? b.slice(0, -ext.length) : b;
}
export function extname(p: string): string {
  const b = basename(p);
  const i = b.lastIndexOf(".");
  return i > 0 ? b.slice(i) : "";
}
export function relative(from: string, to: string): string {
  const a = resolve(from).split("/").filter(Boolean);
  const b = resolve(to).split("/").filter(Boolean);
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return [...a.slice(i).map(() => ".."), ...b.slice(i)].join("/");
}
const posixPath = { sep, delimiter, normalize, join, isAbsolute, resolve, dirname, basename, extname, relative };
export const posix = posixPath;
export default { ...posixPath, posix: posixPath };
