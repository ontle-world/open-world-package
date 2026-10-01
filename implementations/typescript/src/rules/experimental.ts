/**
 * Spec Appendix C: experimental asset kinds and World View specialization.
 * Every check here is a warning (`experimental.field`, `experimental.value`, `experimental.reference`);
 * extension rules (spec 13) stay errors. Field tables follow ../../schemas/experimental/*.schema.json.
 */
import * as path from "node:path";
import { Context, error, LocalAsset, warn } from "../context.js";
import { ANY, ASSET_METADATA, closed, EXTERNAL_REF, leaves, list, OPEN, Shape, structureProblems } from "../structure.js";
import { fileExists, isObj, normalizeRelPath, Obj, staysInside } from "../util.js";
import { VALUE_SETS } from "../vocab.js";
import { externalRefProblems } from "./externalref.js";

const doc = (spec: Record<string, Shape>): Shape => closed({ ...leaves("apiVersion", "kind"), metadata: ASSET_METADATA, spec: closed(spec) }, false);
const CONTENT = closed({ path: ANY, ref: EXTERNAL_REF });

export const EXPERIMENTAL_STRUCTURES: Record<string, Shape> = {
  TaskSetProfile: doc({
    task: closed(leaves("objectiveRefs", "workPatterns")),
    requires: closed(leaves("worldRefs", "worldViews", "knowledge")),
    mayUse: closed(leaves("worldModels", "capabilities", "workflows")),
    produces: closed(leaves("artifacts")),
    evaluationRefs: ANY,
  }),
  WorkPatternProfile: doc({
    pattern: closed(leaves("kind", "family")),
    inputs: closed(leaves("semanticRoles")),
    outputs: closed(leaves("semanticRoles")),
    ...leaves("requiredContracts", "optionalCapabilities", "evaluationRefs"),
  }),
  ArtifactContract: doc({
    artifact: closed(leaves("type", "representation")),
    ...leaves("purposeRef", "audienceRef", "inputs", "sourceBindings", "validationRefs", "evaluationRefs"),
    structure: closed(leaves("required", "optional")),
    serialization: closed(leaves("formats")),
    delivery: closed(leaves("destinations")),
    governance: closed(leaves("approvalRequired", "policyRefs")),
  }),
  ArtifactTemplate: doc({ ...leaves("artifactContractRef", "format"), content: CONTENT }),
  ConsumerRepresentationProfile: doc({
    actor: closed(leaves("kind")),
    worldViewRef: ANY,
    representation: closed({ ...leaves("mode", "provenance"), freshness: OPEN }),
    human: closed({ ...leaves("artifactContractRefs", "presentation", "locale", "decisionRights"), notification: OPEN }),
    agent: closed({ toolScope: closed(leaves("capabilityRefs")), memoryScope: OPEN, contextBudget: OPEN, ...leaves("feasibleActions", "includes") }),
    model: closed({ ...leaves("adapterRef", "modalities"), temporalWindow: OPEN }),
    system: closed({ ...leaves("interfaceRefs", "deliveryMode"), serviceLevel: OPEN }),
  }),
  KnowledgeAsset: doc({
    ...leaves("roles", "representation", "format", "worldRef", "provenance", "license", "access", "sensitivity", "evaluationRefs"),
    conformsTo: closed(leaves("ontology", "shapes")),
    snapshot: closed(leaves("asOf")),
    content: CONTENT,
    delta: closed(leaves("base", "format")),
  }),
  KnowledgeExtractionProfile: doc({
    source: ANY,
    parameters: OPEN,
    query: closed(leaves("language", "text")),
    observations: list(closed({ ...leaves("type", "id", "multi"), values: OPEN, observedAt: closed(leaves("column", "default")) })),
  }),
};

const ACTOR_BLOCKS = ["human", "agent", "model", "system"];

/** A single value or a list of values; null/absent is no values. */
const values = (v: unknown): unknown[] => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v]);
const sub = (o: Obj, k: string): Obj => (isObj(o[k]) ? (o[k] as Obj) : {});

class Checker {
  constructor(
    private readonly ctx: Context,
    private readonly file: string,
    /** Listed local asset path -> kind. */
    private readonly localKinds: Map<string, string>,
  ) {}

  warn(rule: string, msg: string): void {
    warn(this.ctx, rule, `${this.file}: ${msg}`, this.file);
  }

  /** Value-set member, or `<extension>:<value>` with a declared extension. */
  value(v: unknown, set: string, at: string): void {
    if (typeof v !== "string") return this.warn("experimental.value", `${at} must be a string`);
    if (v.includes(":")) {
      const name = v.slice(0, v.indexOf(":"));
      if (!this.ctx.extensionNames.has(name)) {
        error(this.ctx, "extension.undeclared", `${this.file}: ${at} "${v}" uses extension "${name}", which spec.dependencies does not declare with "as"`, this.file);
      }
    } else if (!VALUE_SETS[set].includes(v)) {
      this.warn("experimental.value", `${at} "${v}" is not in the experimental value set ${set}`);
    }
  }

  /** A package-relative path names a listed local asset (of one of `kinds`, when given); `#` refs point into other packages. */
  localRef(ref: unknown, kinds: string[] | null, at: string): void {
    if (typeof ref !== "string" || ref.length === 0) return this.warn("experimental.reference", `${at} must be a package-relative asset path`);
    if (ref.includes("#")) return;
    const kind = this.localKinds.get(ref);
    if (kind === undefined) this.warn("experimental.reference", `${at} "${ref}" is not a listed local asset`);
    else if (kinds && !kinds.includes(kind)) this.warn("experimental.reference", `${at} "${ref}" is a ${kind}, expected ${kinds.join(" or ")}`);
  }

  /** `content`: exactly one of a package path or an ExternalRef (spec 5.1). */
  content(content: Obj): void {
    if (Object.keys(content).length === 0) return;
    const hasPath = Object.prototype.hasOwnProperty.call(content, "path");
    if (hasPath === Object.prototype.hasOwnProperty.call(content, "ref")) return this.warn("experimental.field", "spec.content must declare exactly one of path or ref");
    if (hasPath) {
      const p = content.path;
      const norm = typeof p === "string" ? normalizeRelPath(p) : null;
      const abs = norm === null ? null : path.join(this.ctx.root, norm);
      if (abs === null || !fileExists(abs) || !staysInside(this.ctx.root, abs)) {
        this.warn("experimental.reference", `spec.content.path ${JSON.stringify(p)} does not exist in the package`);
      }
      return;
    }
    const r = externalRefProblems(content.ref, "spec.content.ref", this.ctx.extensionNames);
    for (const p of r.errors) {
      if (p.rule === "extension.undeclared") error(this.ctx, p.rule, `${this.file}: ${p.msg}`, this.file);
      else this.warn("experimental.field", p.msg);
    }
    for (const p of r.warnings) this.warn(p.rule, p.msg);
  }
}

function checkDocument(c: Checker, kind: string, s: Obj, manifestSpec: Obj): void {
  switch (kind) {
    case "TaskSetProfile":
      for (const v of values(sub(s, "task").workPatterns)) c.value(v, "workPatterns", "spec.task.workPatterns");
      for (const r of values(sub(s, "requires").worldViews)) c.localRef(r, ["WorldViewProfile"], "spec.requires.worldViews");
      for (const r of values(sub(s, "requires").knowledge)) c.localRef(r, ["KnowledgeAsset"], "spec.requires.knowledge");
      for (const r of values(sub(s, "produces").artifacts)) c.localRef(r, ["ArtifactContract"], "spec.produces.artifacts");
      break;
    case "WorkPatternProfile": {
      const pattern = sub(s, "pattern");
      if (!("kind" in pattern)) c.warn("experimental.field", "spec.pattern.kind is required");
      else c.value(pattern.kind, "workPatterns", "spec.pattern.kind");
      break;
    }
    case "ArtifactContract": {
      const artifact = sub(s, "artifact");
      if (!("type" in artifact)) c.warn("experimental.field", "spec.artifact.type is required");
      else c.value(artifact.type, "artifactTypes", "spec.artifact.type");
      if ("representation" in artifact) c.value(artifact.representation, "artifactRepresentations", "spec.artifact.representation");
      break;
    }
    case "ArtifactTemplate":
      c.localRef(s.artifactContractRef, ["ArtifactContract"], "spec.artifactContractRef");
      c.content(sub(s, "content"));
      break;
    case "ConsumerRepresentationProfile": {
      const actor = sub(s, "actor").kind;
      if (actor === undefined || actor === null) c.warn("experimental.field", "spec.actor.kind is required");
      else c.value(actor, "actorKinds", "spec.actor.kind");
      c.localRef(s.worldViewRef, ["WorldViewProfile"], "spec.worldViewRef");
      const present = ACTOR_BLOCKS.filter((b) => b in s);
      if (typeof actor === "string" && ACTOR_BLOCKS.includes(actor) && present.some((b) => b !== actor)) {
        c.warn("experimental.field", `only the spec.${actor} block may be present for actor kind ${actor} (found ${present.join(", ")})`);
      }
      for (const r of values(sub(s, "human").artifactContractRefs)) c.localRef(r, ["ArtifactContract"], "spec.human.artifactContractRefs");
      for (const r of values(sub(sub(s, "agent"), "toolScope").capabilityRefs)) c.localRef(r, null, "spec.agent.toolScope.capabilityRefs");
      if ("model" in s) c.localRef(sub(s, "model").adapterRef, ["RepresentationAdapterProfile"], "spec.model.adapterRef");
      for (const r of values(sub(s, "system").interfaceRefs)) c.localRef(r, null, "spec.system.interfaceRefs");
      break;
    }
    case "KnowledgeAsset": {
      for (const v of values(s.roles)) c.value(v, "knowledgeRoles", "spec.roles");
      if ("representation" in s) c.value(s.representation, "knowledgeRepresentations", "spec.representation");
      const ontology = sub(s, "conformsTo").ontology;
      if (ontology !== undefined && ontology !== null) {
        const deps = Array.isArray(manifestSpec.dependencies) ? manifestSpec.dependencies : [];
        if (!deps.some((d) => (isObj(d) ? d.ref : d) === ontology)) {
          c.warn("experimental.reference", `spec.conformsTo.ontology ${JSON.stringify(ontology)} must also be listed in spec.dependencies`);
        }
      }
      c.content(sub(s, "content"));
      break;
    }
    case "KnowledgeExtractionProfile": {
      c.localRef(s.source, ["KnowledgeAsset"], "spec.source");
      const query = sub(s, "query");
      if (!("language" in query)) c.warn("experimental.field", "spec.query.language is required");
      else c.value(query.language, "queryLanguages", "spec.query.language");
      const templates = s.observations;
      if (!Array.isArray(templates) || templates.length === 0) c.warn("experimental.field", "spec.observations must be a non-empty list");
      (Array.isArray(templates) ? templates : []).forEach((t, i) => {
        if (!isExtractionTemplate(t)) c.warn("experimental.field", `spec.observations[${i}] needs type, a non-empty id column list, and a values mapping`);
      });
      break;
    }
  }
}

/** Appendix C.1: an observations entry has a type, a non-empty id column list, and a non-empty values mapping. */
export function isExtractionTemplate(t: unknown): t is { type: string; id: unknown[]; values: Obj; observedAt?: unknown; multi?: unknown } {
  return isObj(t) && typeof t.type === "string" && Array.isArray(t.id) && t.id.length > 0 && isObj(t.values) && Object.keys(t.values).length > 0;
}

/**
 * Appendix C.1: warning `compiler.multi-latest` when a local State Compiler binding reads, with
 * select latest (the default), an observation type that a local extraction marks `multi: true`.
 */
export function checkMultiLatest(ctx: Context): void {
  const multi = new Map<string, string>();
  for (const a of ctx.localAssets) {
    if (a.kind !== "KnowledgeExtractionProfile") continue;
    const list = isObj(a.doc) && isObj(a.doc.spec) ? a.doc.spec.observations : undefined;
    for (const t of Array.isArray(list) ? list : []) {
      if (isObj(t) && t.multi === true && typeof t.type === "string") multi.set(t.type, a.rawPath);
    }
  }
  if (multi.size === 0) return;
  for (const a of ctx.localAssets) {
    if (a.kind !== "StateCompilerProfile") continue;
    const bindings = isObj(a.doc) && isObj(a.doc.spec) ? a.doc.spec.bindings : undefined;
    for (const [field, b] of Object.entries(isObj(bindings) ? bindings : {})) {
      if (!isObj(b) || typeof b.from !== "string" || !multi.has(b.from)) continue;
      if ((b.select ?? "latest") === "latest") {
        warn(ctx, "compiler.multi-latest", `${a.rawPath}: binding "${field}" reads ${b.from}, which ${multi.get(b.from)} marks multi-valued; use select: all`, a.rawPath);
      }
    }
  }
}

function localKinds(ctx: Context): Map<string, string> {
  const m = new Map<string, string>();
  for (const a of ctx.localAssets) if (!m.has(a.rawPath)) m.set(a.rawPath, a.kind);
  return m;
}

/** One experimental asset document; runs after all assets are collected so references to later-listed assets resolve. */
export function checkExperimentalAsset(ctx: Context, a: LocalAsset, kinds = localKinds(ctx)): void {
  if (!isObj(a.doc)) return;
  const c = new Checker(ctx, a.rawPath, kinds);
  for (const p of structureProblems(a.doc, EXPERIMENTAL_STRUCTURES[a.kind], ctx.extensionNames)) {
    if (p.rule === "schema.unknown-field") c.warn("experimental.field", p.msg);
    else error(ctx, p.rule, `${a.rawPath}: ${p.msg}`, a.rawPath);
  }
  const manifestSpec = isObj(ctx.manifest.spec) ? ctx.manifest.spec : {};
  checkDocument(c, a.kind, isObj(a.doc.spec) ? a.doc.spec : {}, manifestSpec);
}

/** Appendix C: WorldViewProfile `spec.specializes` names a local WorldViewProfile, without cycles. */
export function checkViewSpecialization(ctx: Context): void {
  const kinds = localKinds(ctx);
  const docs = new Map<string, unknown>();
  for (const a of ctx.localAssets) if (!docs.has(a.rawPath)) docs.set(a.rawPath, a.doc);
  const base = (p: string): unknown => {
    const s = isObj(docs.get(p)) ? (docs.get(p) as Obj).spec : undefined;
    return isObj(s) ? s.specializes : undefined;
  };
  const isView = (p: unknown): p is string => typeof p === "string" && kinds.get(p) === "WorldViewProfile";
  for (const p of [...kinds.keys()].sort()) {
    if (kinds.get(p) !== "WorldViewProfile") continue;
    const b = base(p);
    if (b === undefined || b === null) continue;
    if (!isView(b)) {
      warn(ctx, "experimental.reference", `${p}: spec.specializes ${JSON.stringify(b)} must be a local WorldViewProfile asset`, p);
      continue;
    }
    const chain = [p];
    for (let cur: unknown = b; isView(cur); cur = base(cur)) {
      if (chain.includes(cur)) {
        warn(ctx, "experimental.reference", `${p}: spec.specializes forms a cycle: ${[...chain, cur].join(" -> ")}`, p);
        break;
      }
      chain.push(cur);
    }
  }
}

/**
 * Appendix C: a View's resolved `projection.include` — the base View's resolved include ∪ its own
 * include − its own exclude, following `specializes` through local WorldViewProfiles (cycles stop the chain).
 */
export function resolvedInclude(p: string, docs: Map<string, unknown>, kinds: Map<string, string>, seen: string[] = []): string[] {
  const s = isObj(docs.get(p)) ? (docs.get(p) as Obj).spec : undefined;
  const spec = isObj(s) ? s : {};
  const projection = isObj(spec.projection) ? spec.projection : {};
  const strings = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  const exclude = new Set(strings(projection.exclude));
  const base = spec.specializes;
  const include: string[] = [];
  if (typeof base === "string" && kinds.get(base) === "WorldViewProfile" && !seen.includes(base) && base !== p) {
    include.push(...resolvedInclude(base, docs, kinds, [...seen, p]));
  }
  for (const x of strings(projection.include)) if (!include.includes(x)) include.push(x);
  return include.filter((x) => !exclude.has(x));
}

/** Union of the resolved projection.include of every local World View. */
export function localViewIncludes(ctx: Context): Set<string> {
  const kinds = localKinds(ctx);
  const docs = new Map<string, unknown>();
  for (const a of ctx.localAssets) if (!docs.has(a.rawPath)) docs.set(a.rawPath, a.doc);
  const out = new Set<string>();
  for (const [p, k] of kinds) if (k === "WorldViewProfile") for (const x of resolvedInclude(p, docs, kinds)) out.add(x);
  return out;
}
