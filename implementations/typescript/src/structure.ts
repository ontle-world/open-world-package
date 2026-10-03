/**
 * Spec sections 8 ("Defined fields") and 13: which keys each standardized document may contain.
 *
 * Each table follows the JSON Schema of the same document under ../../schemas/. A closed object
 * accepts only its listed fields, plus an `extensions` block where the schema allows one; an open
 * container (`OPEN`) is not checked inside; `ANY` is a leaf value that is not descended into.
 */
import { isObj } from "./util.js";

export const EXTENSION_NAME_RE = /^[a-z][a-z0-9-]{0,62}$/;
export const EXTENSION_KIND_RE = /^([a-z][a-z0-9-]{0,62}):([A-Z][A-Za-z0-9]*)$/;
export const RESERVED_EXTENSION_NAMES = new Set(["owp", "openworld"]);

export type Shape =
  | { t: "any" }
  | { t: "open" }
  | { t: "list"; items: Shape }
  | { t: "closed"; fields: Record<string, Shape>; extensions: boolean };

export const ANY: Shape = { t: "any" };
export const OPEN: Shape = { t: "open" };
export const list = (items: Shape): Shape => ({ t: "list", items });
/** Closed object; `extensions` is allowed unless `ext` is false (document roots). */
export const closed = (fields: Record<string, Shape>, ext = true): Shape => ({ t: "closed", fields, extensions: ext });
export const leaves = (...names: string[]): Record<string, Shape> => Object.fromEntries(names.map((n) => [n, ANY]));

/** schemas/owp-manifest.schema.json $defs/externalRef (spec 5.1). */
export const EXTERNAL_REF: Shape = closed(leaves("provider", "uri", "revision", "digest", "mediaType", "size", "status"));

/** schemas/owp-manifest.schema.json spec.ontology (spec 3.1); `prefixes` is an open map. */
export const ONTOLOGY: Shape = closed({
  ...leaves("description", "iri", "termIndex"),
  prefixes: OPEN,
  entrypoints: list(closed(leaves("path", "format", "role"))),
  externalImports: list(closed({ iri: ANY, ref: EXTERNAL_REF })),
});

/** schemas/owp-manifest.schema.json */
export const MANIFEST: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    metadata: closed(leaves("namespace", "name", "version", "title", "description", "license")),
    spec: closed({
      dependencies: list(closed(leaves("ref", "source", "as", "mustUnderstand"))),
      assets: list(closed({ ...leaves("kind", "path"), ref: EXTERNAL_REF })),
      conformance: closed(leaves("profile")),
      world: closed({
        ...leaves("definition", "description", "defaultView", "defaultStateCompiler", "semanticBinding"),
        boundary: closed(leaves("included", "excluded")),
      }),
      worldModel: closed({
        ...leaves("description", "roles", "outputs"),
        semanticGrounding: closed(leaves("worldRef", "compatibleWorldViews", "compatibleStateCompilers")),
        representation: closed(leaves("adapterRef", "input", "internal", "mode")),
        inputs: closed(leaves("contract")),
        modalities: closed(leaves("inputs", "outputs")),
        temporal: OPEN,
        validity: OPEN,
      }),
      ontology: ONTOLOGY,
      extensionDefinition: closed(leaves("description", "kinds", "schemas")),
      domains: ANY,
      capabilities: ANY,
      validity: OPEN,
    }),
  },
  false,
);

/** `metadata` of a local asset document (schemas/compatibility-evidence.schema.json, schemas/experimental/). */
export const ASSET_METADATA: Shape = closed(leaves("name", "version", "title", "description"));

/** schemas/semantic-profile.schema.json (spec 3.1 owp-yaml entrypoints). */
export const SEMANTIC_PROFILE: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    metadata: ASSET_METADATA,
    spec: closed({
      types: list(
        closed({
          ...leaves("id", "description", "subClassOf", "enum"),
          label: OPEN,
          properties: list(closed({ ...leaves("id", "description", "range", "cardinality"), label: OPEN })),
        }),
      ),
      relations: list(closed({ ...leaves("id", "description", "domain", "range"), label: OPEN })),
    }),
  },
  false,
);

/** schemas/ontology-term-index.schema.json */
export const TERM_INDEX: Shape = closed(
  { ...leaves("apiVersion", "kind"), metadata: ASSET_METADATA, spec: closed({ terms: list(closed(leaves("iri", "type", "label"))) }) },
  false,
);

/** schemas/semantic-binding.schema.json (spec 14): sections are maps; `fields` entries are checked with FIELD_BINDING. */
export const SEMANTIC_BINDING: Shape = closed(
  { ...leaves("apiVersion", "kind"), metadata: ASSET_METADATA, spec: closed({ terms: OPEN, fields: OPEN, observationTypes: OPEN, actions: OPEN, subjects: OPEN }) },
  false,
);
export const FIELD_BINDING: Shape = closed(leaves("class", "path", "unit"));

/** schemas/compatibility-evidence.schema.json */
export const COMPATIBILITY_EVIDENCE: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    metadata: ASSET_METADATA,
    spec: closed({
      ...leaves("subject", "subjectDigest", "evaluationProfile", "verifier", "goldenSet", "dataset"),
      scope: closed(leaves("worldRef", "worldView", "stateCompiler", "environment", "task")),
      result: OPEN,
    }),
  },
  false,
);

/** schemas/observation-set.schema.json */
export const OBSERVATION_SET: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    spec: closed({
      observations: list(closed({ ...leaves("id", "type", "observedAt", "subject", "estimatedBy"), values: OPEN, uncertainty: OPEN, units: OPEN })),
      // Spec 12 / Appendix C.1: where the observations came from; compilation ignores it.
      provenance: closed({ ...leaves("extraction", "snapshot"), parameters: OPEN }),
    }),
  },
  false,
);

/** schemas/effective-world-state.schema.json */
export const EFFECTIVE_WORLD_STATE: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    spec: closed({
      ...leaves("worldRef", "worldView", "stateCompiler", "missing"),
      context: closed(leaves("asOf")),
      state: OPEN,
      unresolved: OPEN,
      provenance: OPEN,
      derivation: OPEN,
    }),
  },
  false,
);

/** A standard asset document: apiVersion, kind, metadata, and a closed spec (schemas/<kind>.schema.json). */
const standard = (spec: Record<string, Shape>): Shape => closed({ ...leaves("apiVersion", "kind"), metadata: ASSET_METADATA, spec: closed(spec) }, false);

// Standard kinds with defined fields. Fields marked experimental are Appendix C.4 additions; their
// own checks are warnings (src/rules/experimental.ts), but undefined keys are schema.unknown-field.

/** schemas/world-view-profile.schema.json */
export const WORLD_VIEW_PROFILE: Shape = standard({
  ...leaves("externalWorldRefs", "specializes", "constraints", "evidenceRefs"), // specializes, constraints, evidenceRefs: experimental
  purpose: closed(leaves("task", "actorScope", "objective")),
  projection: closed(leaves("include", "exclude", "principle", "scale", "resolution", "timeScope")),
  conditioning: closed(leaves("authorityScope", "actorRef", "roleRefs", "taskRef")), // *Ref*: experimental
});

/** schemas/evaluation-profile.schema.json */
export const EVALUATION_PROFILE: Shape = standard({
  ...leaves("supersedes", "changedBecause", "metrics", "tasks", "checks"),
  // experimental
  ...leaves("assessmentKind", "objective", "verifierRef", "evaluatorRef", "evidenceRefs", "resultSchemaRef"),
  subject: closed(leaves("kind", "ref")),
  criteria: list(closed(leaves("metric", "rubric", "threshold"))),
  validityScope: OPEN,
});

/** schemas/scenario-profile.schema.json */
export const SCENARIO_PROFILE: Shape = standard({
  ...leaves("description", "objective"),
  standardBindings: OPEN,
  // experimental
  ...leaves("baselineStateRef", "assumptions", "timeHorizon", "constraints", "confidence", "evidenceRefs"),
  intervention: OPEN,
  engine: closed(leaves("kind", "ref")),
  uncertainty: OPEN,
  expectedOutcome: OPEN,
});

/** schemas/capability-contract.schema.json */
export const CAPABILITY_CONTRACT: Shape = standard({
  ...leaves("description", "effect"),
  // experimental
  ...leaves("outcomeRefs", "requiredInputs", "evidenceRefs", "maturity"),
  context: OPEN,
  capacity: OPEN,
  validityScope: OPEN,
});

/** Asset kinds whose documents have a JSON Schema; other kinds are checked only for top-level extension blocks. */

// Standard kinds that had a name but no schema (spec section 8): description, standard bindings, and the fields in use.
export const DATASET: Shape = standard({ ...leaves("description", "worldViewRef", "structure"), standardBindings: OPEN });
export const AGENT_PROFILE: Shape = standard({ ...leaves("description"), standardBindings: OPEN });
export const ENVIRONMENT_PROFILE: Shape = standard({ ...leaves("description", "runtimeBinding"), standardBindings: OPEN, exposes: OPEN });
export const MODEL_ARTIFACT: Shape = standard({ ...leaves("description", "implementationStatus", "bundled", "supportedProviders", "entrypoint"), standardBindings: OPEN, artifactRef: EXTERNAL_REF });
export const SOURCE_SYSTEM_SCHEMA_PROFILE: Shape = standard({ ...leaves("description"), standardBindings: OPEN, systems: OPEN });
export const OBSERVATION_ACQUISITION_PROFILE: Shape = standard({ ...leaves("description", "inputs", "rule", "modalities"), standardBindings: OPEN });
export const ACTION_BINDING_PROFILE: Shape = standard({ ...leaves("description", "actions", "execution"), standardBindings: OPEN, actionSpace: OPEN });
export const COMMIT_CONTRACT: Shape = standard({ ...leaves("description", "approvalRequired", "commitExamples", "rule"), standardBindings: OPEN, commitSemantics: OPEN });
export const EFFECT_VERIFICATION_PROFILE: Shape = standard({ ...leaves("description", "verifies", "rule", "observationSources"), standardBindings: OPEN });
export const VERIFIER_PROFILE: Shape = standard({ ...leaves("description", "verifies", "basis"), standardBindings: OPEN });

export const ASSET_STRUCTURES: Record<string, Shape> = {
  CompatibilityEvidence: COMPATIBILITY_EVIDENCE,
  SemanticProfile: SEMANTIC_PROFILE,
  OntologyTermIndex: TERM_INDEX,
  WorldViewProfile: WORLD_VIEW_PROFILE,
  EvaluationProfile: EVALUATION_PROFILE,
  ScenarioProfile: SCENARIO_PROFILE,
  CapabilityContract: CAPABILITY_CONTRACT,
  Dataset: DATASET,
  AgentProfile: AGENT_PROFILE,
  EnvironmentProfile: ENVIRONMENT_PROFILE,
  ModelArtifact: MODEL_ARTIFACT,
  SourceSystemSchemaProfile: SOURCE_SYSTEM_SCHEMA_PROFILE,
  ObservationAcquisitionProfile: OBSERVATION_ACQUISITION_PROFILE,
  ActionBindingProfile: ACTION_BINDING_PROFILE,
  CommitContract: COMMIT_CONTRACT,
  EffectVerificationProfile: EFFECT_VERIFICATION_PROFILE,
  VerifierProfile: VERIFIER_PROFILE,
};

export interface Problem {
  rule: string;
  msg: string;
}

/**
 * Unknown keys and malformed `extensions` blocks in `doc`.
 * `declared` is the set of extension names the package declares, or null for runtime documents
 * (ObservationSet, EWS), whose extension names are not checked (spec 12).
 */
export function structureProblems(doc: unknown, shape: Shape, declared: Set<string> | null): Problem[] {
  const out: Problem[] = [];
  walk(doc, shape, "", declared, out);
  return out;
}

function walk(v: unknown, shape: Shape, at: string, declared: Set<string> | null, out: Problem[]): void {
  if (shape.t === "list") {
    if (Array.isArray(v)) v.forEach((item, i) => walk(item, shape.items, `${at}[${i}]`, declared, out));
    return;
  }
  if (shape.t !== "closed" || !isObj(v)) return; // type errors are reported by the rules that use the value
  for (const [k, sub] of Object.entries(v)) {
    const child = at ? `${at}.${k}` : k;
    if (k === "extensions" && shape.extensions) out.push(...extensionBlockProblems(sub, child, declared));
    else if (Object.prototype.hasOwnProperty.call(shape.fields, k)) walk(sub, shape.fields[k], child, declared, out);
    else out.push({ rule: "schema.unknown-field", msg: `${child} is not a defined field (extension data belongs in an extensions block)` });
  }
}

/** Spec 13.3: an `extensions` block maps declared extension names to mappings. */
export function extensionBlockProblems(block: unknown, at: string, declared: Set<string> | null): Problem[] {
  if (!isObj(block) || !Object.values(block).every(isObj)) {
    return [{ rule: "extension.block", msg: `${at} must map extension names to mappings` }];
  }
  const out: Problem[] = [];
  for (const name of Object.keys(block)) {
    if (!EXTENSION_NAME_RE.test(name)) out.push({ rule: "extension.block", msg: `${at} key ${JSON.stringify(name)} is not an extension name` });
    else if (declared && !declared.has(name)) {
      out.push({ rule: "extension.undeclared", msg: `${at} uses extension ${JSON.stringify(name)}, which spec.dependencies does not declare with "as"` });
    }
  }
  return out;
}
