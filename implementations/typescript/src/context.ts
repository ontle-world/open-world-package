import type { Obj } from "./util.js";

export interface Issue {
  /** Stable machine code, e.g. "manifest.missing". */
  code: string;
  message: string;
  /** Package-relative file the issue is about, when applicable. */
  file?: string;
}

export const PROFILES = [
  "descriptive",
  "viewable",
  "stateful",
  "model-ready",
  "action-ready",
] as const;
export type Profile = (typeof PROFILES)[number];

export interface LocalAsset {
  index: number;
  kind: string;
  /** Path as written in owp.yaml. */
  rawPath: string;
  /** Normalized package-relative path (null when the path is unusable). */
  path: string | null;
  exists: boolean;
  /** Parsed YAML content, when the asset is a YAML file that parsed. */
  doc?: unknown;
  /** True when a YAML asset failed to parse. */
  parseError?: boolean;
}

export interface RefAsset {
  index: number;
  kind: string;
  ref: Obj;
}

export interface Context {
  root: string;
  manifest: Obj;
  packageKind: string;
  /** `<namespace>/<name>@<version>` when metadata is valid. */
  identity?: string;
  /**
   * `<namespace>/<name>@<version>` built from the raw metadata even when it fails the
   * identity checks; used for identity comparisons so one identity error does not
   * cascade into profile/evidence errors (implementation choice, spec is silent).
   */
  rawIdentity?: string;
  localAssets: LocalAsset[];
  refAssets: RefAsset[];
  errors: Issue[];
  warnings: Issue[];
  satisfiedProfile?: Profile | null;
  declaredProfile?: Profile;
}

export function error(ctx: Pick<Context, "errors">, code: string, message: string, file?: string): void {
  ctx.errors.push(file ? { code, message, file } : { code, message });
}

export function warn(ctx: Pick<Context, "warnings">, code: string, message: string, file?: string): void {
  ctx.warnings.push(file ? { code, message, file } : { code, message });
}

export function localAssetsOfKind(ctx: Context, kind: string): LocalAsset[] {
  return ctx.localAssets.filter((a) => a.kind === kind);
}

export function hasAssetOfKind(ctx: Context, kind: string): boolean {
  return ctx.localAssets.some((a) => a.kind === kind) || ctx.refAssets.some((a) => a.kind === kind);
}
