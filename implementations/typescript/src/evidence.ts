/**
 * Spec 9.1: CompatibilityEvidence published outside the package. It binds to a verified archive by
 * identity (`spec.subject`) and digest (`spec.subjectDigest`); the section 9 scope rules apply
 * against the archive's grounding.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { Context, Issue } from "./context.js";
import { loadArchive } from "./resolve.js";
import { checkEvidence } from "./rules/evaluation.js";
import { checkWorldModelPackage, Grounding } from "./rules/worldmodel.js";
import { COMPATIBILITY_EVIDENCE, structureProblems } from "./structure.js";
import { get, isObj } from "./util.js";

const DETACHED = "evidence.detached-subject";

export interface DetachedEvidenceResult {
  valid: boolean;
  errors: Issue[];
}

export function checkDetachedEvidence(evidence: unknown, archive: string, cacheDir: string): DetachedEvidenceResult {
  const errors: Issue[] = [];
  const e = (code: string, message: string) => errors.push({ code, message });
  for (const p of structureProblems(evidence, COMPATIBILITY_EVIDENCE, null)) e(p.rule, `evidence: ${p.msg}`);
  if (!isObj(evidence) || evidence.kind !== "CompatibilityEvidence") {
    e(DETACHED, "document is not a CompatibilityEvidence");
    return { valid: false, errors };
  }
  fs.mkdirSync(cacheDir, { recursive: true });
  const cand = fs.existsSync(archive) ? loadArchive(path.resolve(archive), cacheDir, archive) : undefined;
  if (!cand || cand.error || !cand.identity) {
    e(DETACHED, `archive does not verify: ${cand?.error ?? `${archive} cannot be read`}`);
    return { valid: false, errors };
  }
  if (get(evidence, "spec", "subject") !== cand.identity) e(DETACHED, `spec.subject must be the archive's identity ${cand.identity}`);
  if (get(evidence, "spec", "subjectDigest") !== cand.revision) e(DETACHED, `spec.subjectDigest must be the archive digest ${cand.revision}`);

  // Section 9 rules against the archive's grounding. Only the evidence itself is a local asset here,
  // so local version binding (evidence.version-mismatch) does not apply.
  const ctx: Context = {
    root: cand.dir,
    manifest: cand.manifest,
    packageKind: typeof cand.manifest.kind === "string" ? cand.manifest.kind : "",
    rawIdentity: cand.identity,
    identity: cand.identity,
    localAssets: [],
    refAssets: [],
    extensionNames: new Set(),
    errors: [],
    warnings: [],
  };
  let g: Grounding | undefined;
  if (ctx.packageKind === "WorldModelPackage") {
    g = checkWorldModelPackage({ ...ctx, errors: [], warnings: [] }); // only the grounding is needed
  }
  checkEvidence(ctx, { index: 0, kind: "CompatibilityEvidence", rawPath: "evidence", path: "evidence", exists: true, doc: evidence }, g);
  errors.push(...ctx.errors.filter((x) => x.code !== "evidence.version-mismatch"));
  return { valid: errors.length === 0, errors };
}
