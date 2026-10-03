/**
 * Work, actor, artifact, and knowledge kinds (spec sections 16-19) and the experimental kinds (Appendix C).
 * The checks are written once with experimental ids; for the standard kinds in FAMILIES, promote() reports
 * them as errors under the family's ids (an unknown value of an open value set stays the warning
 * `value.unknown`). ArtifactTemplate and View specialization stay experimental: warnings only. Extension
 * rules (spec 13) are errors for all of them.
 */
import * as path from "node:path";
import { Context, error, LocalAsset, warn } from "../context.js";
import { ANY, ASSET_METADATA, closed, EXTERNAL_REF, leaves, list, OPEN, Shape, structureProblems } from "../structure.js";
import { isUtcTimestamp } from "../ews.js";
import { fileExists, isObj, normalizeRelPath, Obj, packageFile as packageFileAt, PINNED_RE, staysInside } from "../util.js";
import { VALUE_SETS } from "../vocab.js";
import { externalRefProblems } from "./externalref.js";

const doc = (spec: Record<string, Shape>): Shape => closed({ ...leaves("apiVersion", "kind"), metadata: ASSET_METADATA, spec: closed(spec) }, false);
const CONTENT = closed({ path: ANY, ref: EXTERNAL_REF });

export const EXPERIMENTAL_STRUCTURES: Record<string, Shape> = {
  TaskSetProfile: doc({
    task: closed(leaves("objectiveRefs", "workPatterns")),
    requires: closed(leaves("worldRefs", "worldViews", "knowledge", "actors")),
    workPatternRefs: ANY,
    mayUse: closed(leaves("worldModels", "capabilities", "workflows", "scenarios", "skills", "tools")),
    produces: closed(leaves("artifacts")),
    evaluationRefs: ANY,
  }),
  WorkPatternProfile: doc({
    pattern: closed(leaves("kind", "family")),
    inputs: closed(leaves("semanticRoles")),
    outputs: closed(leaves("semanticRoles")),
    ...leaves("objective", "inputContracts", "outputContracts", "requiredContracts", "optionalCapabilities"),
    graph: closed({
      nodes: list(closed(leaves("id", "family", "patternKind", "description"))),
      transitions: list(closed(leaves("from", "to", "guard", "event"))),
      guards: list(closed(leaves("id", "description"))),
      events: list(closed(leaves("id", "triggers", "description"))),
      loops: list(closed(leaves("nodes", "maxIterations", "until"))),
    }),
    ...leaves("worldViewRef", "governanceRefs", "evaluationRefs"),
  }),
  ArtifactContract: doc({
    artifact: closed(leaves("type", "representation")),
    ...leaves("purposeRef", "audienceRef", "inputs", "sourceBindings", "validationRefs", "evaluationRefs"),
    ...leaves("schemaRef", "sourceRefs", "evidenceRefs", "allowedOperations", "supersedes"),
    storage: closed(leaves("kind", "uri")),
    structure: closed(leaves("required", "optional")),
    serialization: closed(leaves("formats")),
    delivery: closed(leaves("destinations")),
    governance: closed(leaves("approvalRequired", "policyRefs")),
  }),
  ArtifactTemplate: doc({ ...leaves("artifactContractRef", "format"), content: CONTENT }),
  ConsumerRepresentationProfile: doc({
    actor: closed(leaves("kind", "ref")),
    worldViewRef: ANY,
    representation: closed({ ...leaves("mode", "provenance"), freshness: OPEN }),
    human: closed({ ...leaves("artifactContractRefs", "presentation", "locale", "decisionRights"), notification: OPEN }),
    agent: closed({ toolScope: closed(leaves("capabilityRefs")), memoryScope: OPEN, contextBudget: OPEN, ...leaves("feasibleActions", "includes") }),
    model: closed({ ...leaves("adapterRef", "modalities"), temporalWindow: OPEN }),
    system: closed({ ...leaves("interfaceRefs", "deliveryMode"), serviceLevel: OPEN }),
  }),
  KnowledgeAsset: doc({
    ...leaves("roles", "representation", "format", "provenance", "license", "access", "sensitivity", "evaluationRefs"),
    conformsTo: closed(leaves("ontology", "shapes")),
    snapshot: closed(leaves("asOf")),
    content: CONTENT,
    delta: closed(leaves("base", "format")),
  }),
  KnowledgeExtractionProfile: doc({
    source: ANY,
    parameters: OPEN,
    query: closed(leaves("language", "text")),
    observations: list(closed({ ...leaves("type", "id", "subject", "multi"), values: OPEN, observedAt: closed(leaves("column", "default")) })),
  }),
  ActorProfile: doc({
    ...leaves("actorType", "roleRefs", "capabilityRefs", "agentRef", "memberOf"),
    assignments: list(closed(leaves("roleRef", "taskRef", "scope", "validFrom", "expiresAt"))),
  }),
  RoleProfile: doc({
    permissions: list(closed(leaves("actions", "scope"))),
    authorities: list(closed({ ...leaves("decisions", "scope"), ceiling: OPEN })),
    ...leaves("responsibilities", "accountabilities"),
  }),
  DelegationProfile: doc({
    ...leaves("delegator", "delegatee", "scope", "permittedActions", "validFrom", "expiresAt", "evidenceRefs"),
    authorityCeiling: closed({ decisions: ANY, limits: OPEN }),
    revocation: closed(leaves("by")),
    escalation: closed(leaves("to", "when")),
  }),
};

const ACTOR_BLOCKS = ["human", "agent", "model", "system"];

/** Kinds promoted to the standard (spec sections 16-19) and their rule-id family. */
export const FAMILIES: Record<string, string> = {
  TaskSetProfile: "work", WorkPatternProfile: "work",
  ArtifactContract: "artifact", ConsumerRepresentationProfile: "artifact",
  ActorProfile: "actor", RoleProfile: "actor", DelegationProfile: "actor",
  KnowledgeAsset: "knowledge", KnowledgeExtractionProfile: "knowledge",
};
/** (field id, reference id) per family. */
const FAMILY_IDS: Record<string, [string, string]> = {
  work: ["work.field", "work.reference"],
  actor: ["actor.field", "actor.reference"],
  artifact: ["artifact.field", "artifact.reference"],
  knowledge: ["knowledge.field", "knowledge.reference"],
};
/** Value sets that grow with use: a value outside them is a warning even on standard kinds. */
const OPEN_VALUE_SETS = new Set(["workPatterns", "artifactTypes", "artifactRepresentations", "artifactOperations", "knowledgeRoles"]);

/** The id and severity a check reports for a standard kind of FAMILIES (or for a promoted reference field). */
function promote(family: string | undefined, refRule: string | undefined, rule: string, msg: string): { rule: string; error: boolean } {
  if (refRule && rule === "experimental.reference") return { rule: refRule, error: true };
  if (family === undefined) return { rule, error: false };
  const [fieldId, referenceId] = FAMILY_IDS[family];
  switch (rule) {
    case "experimental.field": return { rule: fieldId, error: true };
    case "experimental.reference": return { rule: referenceId, error: true };
    case "experimental.value": {
      const m = /is not in the value set (\w+)$/.exec(msg);
      return m && OPEN_VALUE_SETS.has(m[1]) ? { rule: "value.unknown", error: false } : { rule: fieldId, error: true };
    }
    case "actor.delegation-exceeds-authority": return { rule, error: true };
    default: return { rule, error: false };
  }
}

/** A single value or a list of values; null/absent is no values. */
const values = (v: unknown): unknown[] => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v]);
const sub = (o: Obj, k: string): Obj => (isObj(o[k]) ? (o[k] as Obj) : {});
const present = (v: unknown): boolean => v !== undefined && v !== null;

class Checker {
  constructor(
    private readonly ctx: Context,
    private readonly file: string,
    /** Listed local asset path -> kind. */
    private readonly localKinds: Map<string, string>,
    /** Listed local asset path -> parsed document. */
    private readonly docs: Map<string, unknown>,
    /** Rule-id family of a promoted kind (FAMILIES); undefined for experimental kinds. */
    private readonly family?: string,
    /** For a standard kind's promoted reference field: the error id of a bad reference. */
    private readonly refRule?: string,
  ) {}

  warn(rule: string, msg: string): void {
    const p = promote(this.family, this.refRule, rule, msg);
    (p.error ? error : warn)(this.ctx, p.rule, `${this.file}: ${msg}`, this.file);
  }

  /** An existing file inside the package, given as a package-relative path (not ./ or backslashes). */
  packageFile(p: unknown): boolean {
    return packageFileAt(this.ctx.root, p) !== null;
  }

  /**
   * Appendix C.3: the actions (permissions[].actions) and decisions (authorities[].decisions) granted by
   * the roles of a delegator that is a local ActorProfile; null when it is not one.
   */
  delegatorGrants(delegator: unknown): { actions: Set<string>; decisions: Set<string> } | null {
    if (typeof delegator !== "string" || this.localKinds.get(delegator) !== "ActorProfile") return null;
    const specOf = (p: unknown): Obj => {
      const d = typeof p === "string" ? this.docs.get(p) : undefined;
      return isObj(d) && isObj(d.spec) ? d.spec : {};
    };
    const actions = new Set<string>();
    const decisions = new Set<string>();
    for (const role of values(specOf(delegator).roleRefs)) {
      const r = specOf(role);
      for (const p of Array.isArray(r.permissions) ? r.permissions : []) {
        for (const a of values(isObj(p) ? p.actions : undefined)) if (typeof a === "string") actions.add(a);
      }
      for (const a of Array.isArray(r.authorities) ? r.authorities : []) {
        for (const d of values(isObj(a) ? a.decisions : undefined)) if (typeof d === "string") decisions.add(d);
      }
    }
    return { actions, decisions };
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
      this.warn("experimental.value", `${at} "${v}" is not in the value set ${set}`);
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

/** validFrom and expiresAt, when given, are UTC timestamps and validFrom comes first. */
function checkPeriod(c: Checker, start: unknown, end: unknown, at: string): void {
  for (const [f, v] of [["validFrom", start], ["expiresAt", end]] as const) {
    if (present(v) && !isUtcTimestamp(v)) c.warn("experimental.field", `${at}.${f} must be UTC YYYY-MM-DDTHH:MM:SSZ`);
  }
  if (isUtcTimestamp(start) && isUtcTimestamp(end) && !(start < end)) c.warn("experimental.field", `${at}.validFrom must be before ${at}.expiresAt`);
}

function checkDocument(c: Checker, kind: string, s: Obj, manifestSpec: Obj): void {
  switch (kind) {
    case "TaskSetProfile":
      for (const v of values(sub(s, "task").workPatterns)) c.value(v, "workPatterns", "spec.task.workPatterns");
      for (const r of values(sub(s, "requires").worldViews)) c.localRef(r, ["WorldViewProfile"], "spec.requires.worldViews");
      for (const r of values(sub(s, "requires").knowledge)) c.localRef(r, ["KnowledgeAsset"], "spec.requires.knowledge");
      for (const r of values(sub(s, "produces").artifacts)) c.localRef(r, ["ArtifactContract"], "spec.produces.artifacts");
      // Appendix C.4: composition.
      for (const r of values(sub(s, "requires").actors)) c.localRef(r, ["ActorProfile", "RoleProfile"], "spec.requires.actors");
      for (const r of values(s.workPatternRefs)) c.localRef(r, ["WorkPatternProfile"], "spec.workPatternRefs");
      for (const [f, kind] of [["scenarios", "ScenarioProfile"], ["skills", "SkillProfile"], ["tools", "ToolProfile"]]) {
        for (const r of values(sub(s, "mayUse")[f])) c.localRef(r, [kind], `spec.mayUse.${f}`);
      }
      break;
    case "WorkPatternProfile": {
      const pattern = sub(s, "pattern");
      if (!("kind" in pattern)) c.warn("experimental.field", "spec.pattern.kind is required");
      else c.value(pattern.kind, "workPatterns", "spec.pattern.kind");
      if ("family" in pattern) c.value(pattern.family, "workNodeFamilies", "spec.pattern.family");
      for (const f of ["inputContracts", "outputContracts"]) for (const r of values(s[f])) c.localRef(r, ["ArtifactContract"], `spec.${f}`);
      if (present(s.worldViewRef)) c.localRef(s.worldViewRef, ["WorldViewProfile"], "spec.worldViewRef");
      checkGraph(c, sub(s, "graph"));
      break;
    }
    case "ArtifactContract": {
      const artifact = sub(s, "artifact");
      if (!("type" in artifact)) c.warn("experimental.field", "spec.artifact.type is required");
      else c.value(artifact.type, "artifactTypes", "spec.artifact.type");
      if ("representation" in artifact) c.value(artifact.representation, "artifactRepresentations", "spec.artifact.representation");
      for (const v of values(s.allowedOperations)) c.value(v, "artifactOperations", "spec.allowedOperations");
      if (present(s.schemaRef) && !c.packageFile(s.schemaRef)) c.warn("experimental.reference", `spec.schemaRef ${JSON.stringify(s.schemaRef)} must be a file in the package`);
      if (present(s.supersedes) && !(typeof s.supersedes === "string" && PINNED_RE.test(s.supersedes))) {
        c.warn("experimental.field", "spec.supersedes must be a pinned <name>@<version> reference");
      }
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
      if (present(sub(s, "actor").ref)) c.localRef(sub(s, "actor").ref, ["ActorProfile"], "spec.actor.ref");
      const blocks = ACTOR_BLOCKS.filter((b) => b in s);
      if (typeof actor === "string" && ACTOR_BLOCKS.includes(actor) && blocks.some((b) => b !== actor)) {
        c.warn("experimental.field", `only the spec.${actor} block may be present for actor kind ${actor} (found ${blocks.join(", ")})`);
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
      if ((ontology === undefined || ontology === null) && s.representation === "graph") {
        c.warn("knowledge.graph-ontology", "a graph KnowledgeAsset is an A-box; declare the OntologyPackage that is its T-box in spec.conformsTo.ontology");
      }
      if (ontology !== undefined && ontology !== null) {
        const deps = Array.isArray(manifestSpec.dependencies) ? manifestSpec.dependencies : [];
        if (!deps.some((d) => (isObj(d) ? d.ref : d) === ontology)) {
          c.warn("experimental.reference", `spec.conformsTo.ontology ${JSON.stringify(ontology)} must also be listed in spec.dependencies`);
        }
      }
      c.content(sub(s, "content"));
      break;
    }
    case "ActorProfile":
      if (!("actorType" in s)) c.warn("experimental.field", "spec.actorType is required");
      else c.value(s.actorType, "actorTypes", "spec.actorType");
      for (const r of values(s.roleRefs)) c.localRef(r, ["RoleProfile"], "spec.roleRefs");
      for (const r of values(s.capabilityRefs)) c.localRef(r, ["CapabilityContract"], "spec.capabilityRefs");
      if (present(s.agentRef)) c.localRef(s.agentRef, ["AgentProfile"], "spec.agentRef");
      for (const r of values(s.memberOf)) c.localRef(r, ["ActorProfile"], "spec.memberOf");
      (Array.isArray(s.assignments) ? s.assignments : []).forEach((a, i) => {
        if (!isObj(a)) return;
        const at = `spec.assignments[${i}]`;
        if (("roleRef" in a) === ("taskRef" in a)) c.warn("experimental.field", `${at} names exactly one of roleRef or taskRef`);
        else if ("roleRef" in a) c.localRef(a.roleRef, ["RoleProfile"], `${at}.roleRef`);
        else c.localRef(a.taskRef, ["TaskSetProfile"], `${at}.taskRef`);
        checkPeriod(c, a.validFrom, a.expiresAt, at);
      });
      break;
    case "DelegationProfile": {
      for (const f of ["delegator", "delegatee"]) c.localRef(s[f], ["ActorProfile"], `spec.${f}`);
      for (const r of values(sub(s, "revocation").by)) c.localRef(r, ["ActorProfile"], "spec.revocation.by");
      for (const r of values(sub(s, "escalation").to)) c.localRef(r, ["ActorProfile"], "spec.escalation.to");
      checkPeriod(c, s.validFrom, s.expiresAt, "spec");
      const granted = c.delegatorGrants(s.delegator);
      if (granted) {
        const over = [
          ...values(s.permittedActions).filter((a) => !(typeof a === "string" && (granted.actions.has(a) || granted.decisions.has(a)))),
          ...values(sub(s, "authorityCeiling").decisions).filter((d) => !(typeof d === "string" && granted.decisions.has(d))),
        ];
        if (over.length > 0) {
          c.warn("actor.delegation-exceeds-authority", `delegates ${over.map(String).join(", ")}, which the delegator's roles do not grant`);
        }
      }
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

/**
 * Appendix C.2: work pattern graph — unique string ids for nodes, guards, and events; node families and
 * pattern kinds from their value sets; transitions, events, and loops refer to declared nodes and guards;
 * loop maxIterations is a positive integer.
 */
function checkGraph(c: Checker, graph: Obj): void {
  if (Object.keys(graph).length === 0) return;
  const items = (section: string): Obj[] => (Array.isArray(graph[section]) ? (graph[section] as unknown[]).filter(isObj) : []);
  const ids = (section: string): unknown[] => items(section).map((x) => x.id);
  const nodes = ids("nodes");
  for (const section of ["nodes", "guards", "events"]) {
    const seen = ids(section);
    const duplicate = seen.some((x, i) => seen.indexOf(x) !== i);
    if (duplicate || seen.some((x) => typeof x !== "string" || x.length === 0)) c.warn("experimental.field", `spec.graph.${section} need unique string ids`);
  }
  (Array.isArray(graph.nodes) ? graph.nodes : []).forEach((n, i) => {
    if (!isObj(n)) return;
    if ("family" in n) c.value(n.family, "workNodeFamilies", `spec.graph.nodes[${i}].family`);
    if ("patternKind" in n) c.value(n.patternKind, "workPatterns", `spec.graph.nodes[${i}].patternKind`);
  });
  const guards = ids("guards");
  const events = ids("events");
  const ref = (v: unknown) => JSON.stringify(v ?? null);
  (Array.isArray(graph.transitions) ? graph.transitions : []).forEach((t, i) => {
    if (!isObj(t)) return;
    for (const end of ["from", "to"]) if (!nodes.includes(t[end])) c.warn("experimental.reference", `spec.graph.transitions[${i}].${end} ${ref(t[end])} is not a node`);
    if (present(t.guard) && !guards.includes(t.guard)) c.warn("experimental.reference", `spec.graph.transitions[${i}].guard ${ref(t.guard)} is not a declared guard`);
    if (present(t.event) && !events.includes(t.event)) c.warn("experimental.reference", `spec.graph.transitions[${i}].event ${ref(t.event)} is not a declared event`);
  });
  (Array.isArray(graph.events) ? graph.events : []).forEach((e, i) => {
    for (const target of values(isObj(e) ? e.triggers : undefined)) {
      if (!nodes.includes(target)) c.warn("experimental.reference", `spec.graph.events[${i}].triggers ${ref(target)} is not a node`);
    }
  });
  (Array.isArray(graph.loops) ? graph.loops : []).forEach((l, i) => {
    if (!isObj(l)) return;
    for (const n of values(l.nodes)) if (!nodes.includes(n)) c.warn("experimental.reference", `spec.graph.loops[${i}].nodes ${ref(n)} is not a node`);
    if (present(l.until) && !guards.includes(l.until)) c.warn("experimental.reference", `spec.graph.loops[${i}].until ${ref(l.until)} is not a declared guard`);
    const bound = l.maxIterations;
    if (present(bound) && !(typeof bound === "number" && Number.isInteger(bound) && bound >= 1)) {
      c.warn("experimental.field", `spec.graph.loops[${i}].maxIterations must be a positive integer`);
    }
  });
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

function localDocs(ctx: Context): Map<string, unknown> {
  const m = new Map<string, unknown>();
  for (const a of ctx.localAssets) if (!m.has(a.rawPath)) m.set(a.rawPath, a.doc);
  return m;
}

export function localKinds(ctx: Context): Map<string, string> {
  const m = new Map<string, string>();
  for (const a of ctx.localAssets) if (!m.has(a.rawPath)) m.set(a.rawPath, a.kind);
  return m;
}

/** One experimental asset document; runs after all assets are collected so references to later-listed assets resolve. */
export function checkExperimentalAsset(ctx: Context, a: LocalAsset, kinds = localKinds(ctx)): void {
  if (!isObj(a.doc)) return;
  const c = new Checker(ctx, a.rawPath, kinds, localDocs(ctx), FAMILIES[a.kind]);
  for (const p of structureProblems(a.doc, EXPERIMENTAL_STRUCTURES[a.kind], ctx.extensionNames)) {
    if (p.rule === "schema.unknown-field" && !(a.kind in FAMILIES)) c.warn("experimental.field", p.msg);
    else error(ctx, p.rule, `${a.rawPath}: ${p.msg}`, a.rawPath);
  }
  const manifestSpec = isObj(ctx.manifest.spec) ? ctx.manifest.spec : {};
  checkDocument(c, a.kind, isObj(a.doc.spec) ? a.doc.spec : {}, manifestSpec);
}

/** Standard kinds whose actor, role, and task references are checked here (spec sections 6, 15.1). */
export const STANDARD_KINDS_WITH_EXPERIMENTAL_FIELDS = ["WorldViewProfile", "EvaluationProfile", "ScenarioProfile", "CapabilityContract"];

/** Spec 6 and 15.1: conditioning and evaluator references of standard kinds name local assets of the right kind (errors). */
export function checkStandardKindFields(ctx: Context, a: LocalAsset): void {
  if (!isObj(a.doc)) return;
  const refRule = a.kind === "WorldViewProfile" ? "view.conditioning-ref" : a.kind === "EvaluationProfile" ? "evaluation.evaluator-ref" : undefined;
  const c = new Checker(ctx, a.rawPath, localKinds(ctx), localDocs(ctx), undefined, refRule);
  const s = isObj(a.doc.spec) ? a.doc.spec : {};
  if (a.kind === "WorldViewProfile") {
    for (const [f, kind] of [["actorRef", "ActorProfile"], ["taskRef", "TaskSetProfile"]]) {
      const v = sub(s, "conditioning")[f];
      if (present(v)) c.localRef(v, [kind], `spec.conditioning.${f}`);
    }
    for (const r of values(sub(s, "conditioning").roleRefs)) c.localRef(r, ["RoleProfile"], "spec.conditioning.roleRefs");
  } else if (a.kind === "EvaluationProfile") {
    if (present(s.evaluatorRef)) c.localRef(s.evaluatorRef, ["ActorProfile"], "spec.evaluatorRef");
  }
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
