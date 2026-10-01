import { EXTENSION_NAME_RE, Problem } from "../structure.js";
import { isObj } from "../util.js";

/** Spec 5.1: listed ExternalRef providers; others are `<extension>:<provider>`. */
export const PROVIDERS = new Set(["huggingface", "oci", "git", "https", "s3", "gcs", "doi"]);
const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const COMMIT_RE = /^([0-9a-f]{40}|[0-9a-f]{64})$/;

const has = (o: Record<string, unknown>, k: string) => Object.prototype.hasOwnProperty.call(o, k);
/** An optional field counts as absent when it is missing or null. */
const present = (v: unknown) => v !== undefined && v !== null;

/**
 * Spec 5.1: errors and warnings for one ExternalRef. Unknown fields and extensions blocks
 * are reported by the manifest structure check (src/structure.ts EXTERNAL_REF).
 */
export function externalRefProblems(ref: unknown, at: string, declared: Set<string>): { errors: Problem[]; warnings: Problem[] } {
  const errors: Problem[] = [];
  const warnings: Problem[] = [];
  const shape = (msg: string) => errors.push({ rule: "ref.shape", msg: `${at}${msg}` });
  if (!isObj(ref)) {
    shape(" must be a mapping");
    return { errors, warnings };
  }

  const status = present(ref.status) ? ref.status : "bound";
  if (status !== "bound" && status !== "unbound") {
    shape(`.status must be bound or unbound (got ${JSON.stringify(ref.status)})`);
    return { errors, warnings };
  }

  // `repository` is the deprecated name of `uri`.
  let uri = ref.uri;
  if (has(ref, "repository")) {
    if (has(ref, "uri")) shape(" declares both uri and its deprecated name repository");
    else {
      warnings.push({ rule: "ref.legacy-shape", msg: `${at}.repository is deprecated; use uri` });
      uri = ref.repository;
    }
  }

  const provider = ref.provider;
  const providerError = (msg: string) => errors.push({ rule: "ref.provider", msg: `${at}.provider ${msg}` });
  if (present(provider)) {
    if (typeof provider !== "string") providerError("must be a string");
    else if (provider.includes(":")) {
      const colon = provider.indexOf(":");
      const name = provider.slice(0, colon);
      if (!EXTENSION_NAME_RE.test(name) || colon === provider.length - 1) {
        providerError(`"${provider}" must be one of ${[...PROVIDERS].join(", ")} or <extension>:<provider>`);
      } else if (!declared.has(name)) {
        errors.push({ rule: "extension.undeclared", msg: `${at}.provider "${provider}" uses extension "${name}", which spec.dependencies does not declare with "as"` });
      }
    } else if (!PROVIDERS.has(provider)) {
      providerError(`"${provider}" must be one of ${[...PROVIDERS].join(", ")} or <extension>:<provider>`);
    }
  }

  const digest = ref.digest;
  if (present(digest) && !(typeof digest === "string" && DIGEST_RE.test(digest))) shape(".digest must be sha256:<64 lowercase hex digits>");
  const size = ref.size;
  if (present(size) && !(typeof size === "number" && Number.isInteger(size) && size >= 0)) shape(".size must be a non-negative integer");
  for (const k of ["revision", "mediaType"]) if (present(ref[k]) && typeof ref[k] !== "string") shape(`.${k} must be a string`);

  if (status === "unbound") return { errors, warnings };
  if (!present(provider)) shape(" is bound and must declare provider");
  if (typeof uri !== "string" || uri.length === 0) shape(" is bound and must declare uri");

  // Pinning (SHOULD): not judged for malformed references or extension providers (defined by the extension).
  if (errors.length > 0 || String(provider).includes(":")) return { errors, warnings };
  const commitPinned = (provider === "git" || provider === "huggingface") && typeof ref.revision === "string" && COMMIT_RE.test(ref.revision);
  if (typeof digest !== "string" && !commitPinned) {
    const how = provider === "git" || provider === "huggingface" ? "a commit-hash revision or a digest" : "a digest";
    warnings.push({ rule: "ref.unpinned", msg: `${at} (${String(provider)}) is not pinned; declare ${how}` });
  }
  return { errors, warnings };
}
