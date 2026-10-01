import { Context, error } from "../context.js";
import { isNonEmptyString, isObj, Obj, PACKAGE_REF_RE } from "../util.js";

export interface Dependency {
  ref: string;
  namespace: string;
  name: string;
  version: string;
  /** Per-dependency package source, tried before the global sources (spec 11). */
  source?: string;
  /** Extension name declared with `as` (spec 13.1), when it is a string. */
  as?: string;
}

export function parsePackageRef(ref: string): { namespace: string; name: string; version: string } | null {
  const m = PACKAGE_REF_RE.exec(ref);
  return m ? { namespace: m[1], name: m[2], version: m[3] } : null;
}

/**
 * Spec 11: `spec.dependencies` is a list of exact `<ns>/<name>@<version>` strings or
 * `{ref, source, as, mustUnderstand}` mappings. Ranges are not allowed.
 */
export function parseDependencies(manifest: Obj): { deps: Dependency[]; problems: string[] } {
  const deps: Dependency[] = [];
  const problems: string[] = [];
  const spec = manifest.spec;
  const raw = isObj(spec) ? spec.dependencies : undefined;
  if (raw === undefined) return { deps, problems };
  if (!Array.isArray(raw)) return { deps, problems: ["spec.dependencies must be a list"] };
  raw.forEach((d, i) => {
    let ref: unknown;
    let source: unknown;
    if (typeof d === "string") ref = d;
    else if (isObj(d)) {
      ref = d.ref;
      source = d.source;
      if (source !== undefined && !isNonEmptyString(source)) {
        problems.push(`spec.dependencies[${i}].source must be a non-empty string`);
        source = undefined;
      }
    } else {
      problems.push(`spec.dependencies[${i}] must be a string or a {ref, source} mapping`);
      return;
    }
    if (typeof ref !== "string") {
      problems.push(`spec.dependencies[${i}] requires ref <namespace>/<name>@<version>`);
      return;
    }
    const p = parsePackageRef(ref);
    if (!p) {
      problems.push(`spec.dependencies[${i}] "${ref}" must be an exact <namespace>/<name>@<version>; ranges are not allowed`);
      return;
    }
    const as = isObj(d) && typeof d.as === "string" ? d.as : undefined;
    deps.push({ ref, ...p, ...(typeof source === "string" ? { source } : {}), ...(as !== undefined ? { as } : {}) });
  });
  return { deps, problems };
}

export function checkDependencies(ctx: Context): void {
  for (const p of parseDependencies(ctx.manifest).problems) error(ctx, "manifest.dependency", p, "owp.yaml");
}
