/**
 * Spec section 5: paths that `.owpignore` excludes are not package files.
 *
 * gitignore subset: one pattern per line; blank lines and `#` lines are skipped; `!` re-includes; a trailing `/`
 * matches directories only; a pattern with another `/` is anchored at the package root, otherwise it matches a
 * name at any depth; `*` and `?` do not cross `/`, `**` does, `[...]` is a character class. The last matching
 * pattern wins, and a file inside an excluded directory cannot be re-included.
 */
import * as fs from "node:fs";
import * as path from "node:path";

export const IGNORE_FILE = ".owpignore";

export interface IgnoreRule {
  regex: RegExp;
  negate: boolean;
  dirOnly: boolean;
  anchored: boolean;
}

const escapeRe = (c: string): string => c.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

/** [body start, closing index, negated] of a character class opened at i; a "]" first in the class is literal. */
function classSpan(glob: string, i: number): [number, number, boolean] | null {
  let j = i + 1;
  const negated = glob[j] === "!" || glob[j] === "^";
  if (negated) j += 1;
  const end = glob.indexOf("]", glob[j] === "]" ? j + 1 : j);
  return end === -1 ? null : [j, end, negated];
}

function globRegex(glob: string): string {
  let out = "";
  let i = 0;
  while (i < glob.length) {
    const c = glob[i];
    if (glob.startsWith("**", i)) {
      const before = i === 0 || glob[i - 1] === "/";
      const after = i + 2 === glob.length || glob[i + 2] === "/";
      if (before && after) {
        if (i + 2 === glob.length) {
          out += ".*"; // trailing "/**": everything inside
          i += 2;
        } else {
          out += "(?:.*/)?"; // "**/": zero or more directories
          i += 3;
        }
        continue;
      }
      out += "[^/]*"; // "**" inside a name acts like "*"
      i += 2;
    } else if (c === "*") {
      out += "[^/]*";
      i += 1;
    } else if (c === "?") {
      out += "[^/]";
      i += 1;
    } else if (c === "[" && classSpan(glob, i) !== null) {
      const [start, end, negated] = classSpan(glob, i)!;
      const body = [...glob.slice(start, end)].map((ch) => ("\\]^[".includes(ch) ? "\\" + ch : ch)).join("");
      out += "[" + (negated ? "^" : "") + body + "]";
      i = end + 1;
    } else if (c === "\\" && i + 1 < glob.length) {
      out += escapeRe(glob[i + 1]);
      i += 2;
    } else {
      out += escapeRe(c);
      i += 1;
    }
  }
  return out;
}

export function parseIgnore(text: string): IgnoreRule[] {
  const rules: IgnoreRule[] = [];
  for (let line of text.split(/\r\n|\r|\n/)) {
    line = line.trimEnd();
    if (!line || line.startsWith("#")) continue;
    const negate = line.startsWith("!");
    if (negate) line = line.slice(1);
    else if (line.startsWith("\\#") || line.startsWith("\\!")) line = line.slice(1);
    const dirOnly = line.endsWith("/");
    line = line.replace(/\/+$/, "");
    if (!line) continue;
    const anchored = line.includes("/");
    line = line.replace(/^\/+/, "");
    let regex: RegExp;
    try {
      regex = new RegExp("^" + globRegex(line) + "$", "u");
    } catch {
      continue; // a pattern that is not valid (for example the range [z-a]) excludes nothing
    }
    rules.push({ regex, negate, dirOnly, anchored });
  }
  return rules;
}

export function loadIgnore(root: string): IgnoreRule[] {
  try {
    return parseIgnore(fs.readFileSync(path.join(root, IGNORE_FILE), "utf8"));
  } catch {
    return [];
  }
}

/** Whether the package-relative POSIX file path `rel` is excluded. */
export function isIgnored(rules: IgnoreRule[], rel: string): boolean {
  if (rules.length === 0) return false;
  const parts = rel.split("/");
  for (let i = 1; i <= parts.length; i++) {
    const isDir = i < parts.length;
    const sub = parts.slice(0, i).join("/");
    let excluded = false;
    for (const rule of rules) {
      if (rule.dirOnly && !isDir) continue;
      if (rule.regex.test(rule.anchored ? sub : parts[i - 1])) excluded = !rule.negate;
    }
    if (excluded) return true;
  }
  return false;
}
