import * as path from "node:path";
import { Context, error } from "../context.js";
import { fileExists, isNonEmptyString, isObj, SEMVER_RE, jsString } from "../util.js";
import { API_VERSION, HUMAN_CARDS, PACKAGE_KINDS } from "../vocab.js";

/** Spec section 2 + 3: identity, apiVersion, kind, spec object, human card. */
export function checkManifest(ctx: Context): void {
  const m = ctx.manifest;

  if (m.apiVersion !== API_VERSION) {
    error(ctx, "manifest.api-version", `apiVersion must be "${API_VERSION}" (got ${JSON.stringify(m.apiVersion)})`, "owp.yaml");
  }

  if (!(PACKAGE_KINDS as readonly unknown[]).includes(m.kind)) {
    error(ctx, "manifest.kind", `kind must be one of ${PACKAGE_KINDS.join(", ")} (got ${JSON.stringify(m.kind)})`, "owp.yaml");
  }

  const md = m.metadata;
  if (!isObj(md)) {
    error(ctx, "manifest.metadata", "metadata must be a mapping with namespace, name and version", "owp.yaml");
  } else {
    let ok = true;
    for (const k of ["namespace", "name"] as const) {
      if (!isNonEmptyString(md[k])) {
        error(ctx, "manifest.identity", `metadata.${k} must be a non-empty string`, "owp.yaml");
        ok = false;
      } else if (/[/@#\s]/.test(md[k] as string)) {
        // Identity is `<namespace>/<name>@<version>`: these characters would make it ambiguous.
        error(ctx, "manifest.identity", `metadata.${k} must not contain '/', '@', '#' or whitespace`, "owp.yaml");
        ok = false;
      }
    }
    if (md.version === undefined || md.version === null || md.version === "") {
      error(ctx, "manifest.identity", "metadata.version is required", "owp.yaml");
      ok = false;
    } else if (typeof md.version !== "string" || !SEMVER_RE.test(md.version)) {
      error(ctx, "manifest.version", `metadata.version must be a SemVer string (got ${JSON.stringify(md.version)})`, "owp.yaml");
      ok = false;
    }
    if (md.namespace !== undefined && md.name !== undefined && md.version !== undefined) {
      ctx.rawIdentity = `${jsString(md.namespace)}/${jsString(md.name)}@${jsString(md.version)}`; // any value, even {toString: 1}
    }
    if (ok) ctx.identity = `${md.namespace}/${md.name}@${md.version}`;
  }

  if (!isObj(m.spec)) {
    error(ctx, "manifest.spec", "spec must be a mapping", "owp.yaml");
  }

  const card = Object.prototype.hasOwnProperty.call(HUMAN_CARDS, ctx.packageKind) ? HUMAN_CARDS[ctx.packageKind] : undefined; // kind: toString is no kind
  if (card && !fileExists(path.join(ctx.root, card))) {
    error(ctx, "package.card", `${ctx.packageKind} requires human card ${card} at the package root`, card);
  }
}
