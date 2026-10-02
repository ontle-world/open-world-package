/**
 * Spec section 15: standard fields of EvaluationProfile (15.1) and ScenarioProfile (15.2). These checks are
 * errors. CapabilityContract (15.3) and WorldViewProfile (15.4) have no rules beyond their defined fields
 * (src/structure.ts); the remaining experimental fields of these kinds are Appendix C.4 warnings
 * (src/rules/experimental.ts).
 */
import * as path from "node:path";
import { Context, error, LocalAsset } from "../context.js";
import { fileExists, isObj, normalizeRelPath, Obj, PINNED_RE, staysInside } from "../util.js";
import { VALUE_SETS } from "../vocab.js";

const present = (v: unknown): boolean => v !== undefined && v !== null;
const sub = (o: Obj, k: string): Obj => (isObj(o[k]) ? (o[k] as Obj) : {});

/** An existing file inside the package, given as a package-relative path (not ./ or backslashes). */
function packageFile(ctx: Context, p: unknown): boolean {
  if (typeof p !== "string" || p.length === 0 || p.startsWith("./") || p.includes("\\")) return false;
  const norm = normalizeRelPath(p);
  if (norm === null) return false;
  const abs = path.join(ctx.root, norm);
  return fileExists(abs) && staysInside(ctx.root, abs);
}

export function checkStandardFields(ctx: Context, a: LocalAsset): void {
  if (!isObj(a.doc)) return;
  const file = a.rawPath;
  const err = (rule: string, msg: string) => error(ctx, rule, `${file}: ${msg}`, file);
  const listed = new Set(ctx.localAssets.map((x) => x.rawPath));
  const kindOf = (p: string) => ctx.localAssets.find((x) => x.rawPath === p)?.kind;

  /** A value of a standard value set, or a declared extension value `<extension>:<value>`. */
  const value = (v: unknown, set: string, rule: string, at: string) => {
    if (typeof v !== "string") return err(rule, `${at} must be a string`);
    if (v.includes(":")) {
      const name = v.slice(0, v.indexOf(":"));
      if (!ctx.extensionNames.has(name)) {
        error(ctx, "extension.undeclared", `${file}: ${at} "${v}" uses extension "${name}", which spec.dependencies does not declare with "as"`, file);
      }
    } else if (!VALUE_SETS[set].includes(v)) {
      err(rule, `${at} "${v}" is not one of ${VALUE_SETS[set].join(", ")}`);
    }
  };

  const s = isObj(a.doc.spec) ? a.doc.spec : {};
  if (a.kind === "EvaluationProfile") {
    if ("assessmentKind" in s) value(s.assessmentKind, "assessmentKinds", "evaluation.assessment-kind", "spec.assessmentKind");
    const subject = sub(s, "subject");
    if ("kind" in subject) value(subject.kind, "evaluationSubjects", "evaluation.subject", "spec.subject.kind");
    // A ref containing '#' or '@' points into another package or asset; otherwise it is a listed local asset.
    const ref = subject.ref;
    if (present(ref) && !String(ref).includes("#") && !String(ref).includes("@") && !(typeof ref === "string" && listed.has(ref))) {
      err("evaluation.subject", `spec.subject.ref ${JSON.stringify(ref)} is neither a listed local asset nor a package or asset reference`);
    }
    const v = s.verifierRef;
    if (present(v)) {
      const pinned = typeof v === "string" && v.includes("@") && PINNED_RE.test(v);
      if (!pinned && !(typeof v === "string" && kindOf(v) === "VerifierPackage")) {
        err("evaluation.verifier-ref", "spec.verifierRef must be a local VerifierPackage or a pinned <name>@<version>");
      }
    }
    if (present(s.resultSchemaRef) && !packageFile(ctx, s.resultSchemaRef)) {
      err("evaluation.result-schema", `spec.resultSchemaRef ${JSON.stringify(s.resultSchemaRef)} must be a file in the package`);
    }
  } else if (a.kind === "ScenarioProfile") {
    const engine = sub(s, "engine");
    if ("kind" in engine) value(engine.kind, "scenarioEngines", "scenario.engine-kind", "spec.engine.kind");
    const baseline = s.baselineStateRef;
    if (present(baseline) && !String(baseline).includes("://") && !String(baseline).includes("#") && !packageFile(ctx, baseline)) {
      err("scenario.baseline-ref", `spec.baselineStateRef ${JSON.stringify(baseline)} must be a file in the package or a URI`);
    }
    const conf = s.confidence;
    if (present(conf) && !(typeof conf === "number" && conf >= 0 && conf <= 1)) err("scenario.confidence", "spec.confidence must be a number from 0 to 1");
  }
}
