export type Stability = "standard" | "experimental" | "reserved";

/**
 * Asset kind vocabulary, copied from vocab/asset-kinds.yaml (public alpha): group -> kind -> stability.
 * scripts/check-vocab.mjs (run by `npm test`) checks that this table equals the YAML file.
 * Spec 8: the vocabulary is open. An unqualified kind outside it is a warning, a kind marked
 * experimental or reserved is a warning, and a kind containing ':' is an extension kind (spec 13).
 * Group names are informative.
 */
const S: Stability = "standard";
const X: Stability = "experimental";
const R: Stability = "reserved";
export const ASSET_KINDS: Record<string, Record<string, Stability>> = {
  semanticWorld: {
    SemanticProfile: S,
    OntologyTermIndex: S,
    WorldViewProfile: S,
    StateCompilerProfile: S,
    SemanticBinding: S,
  },
  interfaceIntegration: {
    SourceSystemSchemaProfile: S,
    SourceAdapterProfile: R,
    IdentityResolutionProfile: R,
    ObservationAcquisitionProfile: S,
    ActionBindingProfile: S,
    CommitContract: S,
    EffectVerificationProfile: S,
  },
  referenceProfiles: { ReferenceEnterpriseProfile: R, ReferenceIndustryProfile: R, ScenarioProfile: S, EnvironmentProfile: S },
  modelRepresentation: {
    ModelArtifact: S,
    RepresentationAdapterProfile: S,
  },
  capabilityOperational: {
    CapabilityContract: S,
    SkillProfile: R,
    ToolProfile: R,
    AgentProfile: S,
    WorkflowProfile: R,
    OperationalAsset: R,
  },
  evaluationTestEvidence: {
    Dataset: S,
    ReferenceFixture: R,
    NegativeFixture: R,
    BenchmarkCase: R,
    AcceptanceCase: R,
    EvaluationProfile: S,
    VerifierProfile: S,
    CompatibilityEvidence: S,
  },
  governancePublication: { Attestation: R },
  taskWork: { TaskSetProfile: X, WorkPatternProfile: X },
  knowledge: { KnowledgeAsset: X, KnowledgeExtractionProfile: X },
  artifactRepresentation: { ArtifactContract: X, ArtifactTemplate: X, ConsumerRepresentationProfile: X },
  actorAuthority: { ActorProfile: X, RoleProfile: X, DelegationProfile: X },
  packageSupport: { PackageExample: S },
};

/** Kind -> stability across all groups. */
export const ASSET_KIND_STABILITY: Map<string, Stability> = new Map(
  Object.values(ASSET_KINDS).flatMap((g) => Object.entries(g)),
);

/**
 * Experimental value sets, copied from vocab/value-sets.yaml (spec Appendix C; checked by
 * scripts/check-vocab.mjs). A value outside its set is a warning; `<extension>:<value>` is
 * accepted when the extension is declared.
 */
export const VALUE_SETS: Record<string, string[]> = {
  workPatterns: [
    "observe", "detect", "retrieve", "summarize", "analyze", "compare", "diagnose", "forecast", "prioritize", "recommend", "allocate",
    "schedule", "optimize", "simulate", "create", "transform", "review", "approve", "execute", "publish", "evaluate", "learn",
  ],
  artifactTypes: [
    "document", "report", "proposal", "presentation", "spreadsheet", "dataset", "database_object", "knowledge_graph", "form", "dashboard",
    "image", "audio", "video", "code", "app", "workflow", "agent_configuration", "model_configuration", "evaluation_asset", "template",
  ],
  artifactRepresentations: ["document", "table", "graph", "board", "form", "media", "code", "configuration"],
  actorKinds: ["human", "agent", "model", "system"],
  knowledgeRoles: ["source", "evidence", "claim", "rule", "procedure", "definition", "graph", "glossary"],
  knowledgeRepresentations: ["graph", "table", "documents", "rules", "index"],
  queryLanguages: ["sparql", "opencypher", "gql"],
  workNodeFamilies: ["observe_knowledge", "analyze_reason", "create_modify", "decide_plan", "execute_operate", "evaluate_recover"],
  artifactOperations: [
    "create", "inspect", "edit", "transform", "branch", "merge", "compare", "validate", "version",
    "restore", "supersede", "share", "handoff", "publish", "deliver", "commit", "deploy", "activate",
  ],
  assessmentKinds: ["verification", "validation", "evaluation", "review", "approval"],
  evaluationSubjects: ["model", "agent", "workflow", "artifact", "decision", "process", "capability", "environment"],
  scenarioEngines: ["rule", "score_ranking", "optimization", "simulation", "ml_prediction", "world_model", "llm_reasoning"],
  actorTypes: ["human", "ai_agent", "team", "organization", "external_institution", "automated_system"],
};

export const PACKAGE_KINDS = ["WorldPackage", "WorldModelPackage", "OntologyPackage"] as const;

export const HUMAN_CARDS: Record<string, string> = {
  WorldPackage: "WORLD.md",
  WorldModelPackage: "WORLDMODEL.md",
  OntologyPackage: "ONTOLOGY.md",
};

export const API_VERSION = "openworld/v1alpha1";

/** Legacy manifest names (spec 8, revised): these at the package root make a package invalid. */
export const LEGACY_MANIFEST_NAMES = ["package.yaml", "world.yaml"];
