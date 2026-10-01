export type Stability = "standard" | "experimental";

/**
 * Asset kind vocabulary, copied from vocab/asset-kinds.yaml (public alpha): group -> kind -> stability.
 * scripts/check-vocab.mjs (run by `npm test`) checks that this table equals the YAML file.
 * Spec 8: the vocabulary is open. An unqualified kind outside it is a warning, a kind marked
 * experimental is a warning, and a kind containing ':' is an extension kind (spec 13).
 * Group names are informative.
 */
const S: Stability = "standard";
export const ASSET_KINDS: Record<string, Record<string, Stability>> = {
  semanticWorld: { SemanticProfile: S, WorldDefinition: S, WorldViewProfile: S, StateCompilerProfile: S },
  interfaceIntegration: {
    SourceSystemSchemaProfile: S,
    SourceAdapterProfile: S,
    MappingSpec: S,
    IdentityResolutionProfile: S,
    ObservationAcquisitionProfile: S,
    ActionBindingProfile: S,
    CommitContract: S,
    EffectVerificationProfile: S,
  },
  referenceProfiles: { ReferenceEnterpriseProfile: S, ReferenceIndustryProfile: S, ScenarioProfile: S, EnvironmentProfile: S },
  modelRepresentation: {
    WorldModelContract: S,
    ModelArtifact: S,
    RepresentationAdapterProfile: S,
    ResolutionProfile: S,
    AggregationCoarseGrainingProfile: S,
  },
  capabilityOperational: {
    CapabilityContract: S,
    SkillProfile: S,
    ToolProfile: S,
    AgentProfile: S,
    WorkflowProfile: S,
    OperationalAsset: S,
    SemanticBinding: S,
  },
  evaluationTestEvidence: {
    Dataset: S,
    ReferenceFixture: S,
    NegativeFixture: S,
    BenchmarkCase: S,
    AcceptanceCase: S,
    Validator: S,
    EvaluationProfile: S,
    VerifierPackage: S,
    CompatibilityEvidence: S,
  },
  governancePublication: { Attestation: S },
  packageSupport: { PackageExample: S },
};

/** Kind -> stability across all groups. */
export const ASSET_KIND_STABILITY: Map<string, Stability> = new Map(
  Object.values(ASSET_KINDS).flatMap((g) => Object.entries(g)),
);

export const PACKAGE_KINDS = ["WorldPackage", "WorldModelPackage", "OntologyPackage"] as const;

export const HUMAN_CARDS: Record<string, string> = {
  WorldPackage: "WORLD.md",
  WorldModelPackage: "WORLDMODEL.md",
  OntologyPackage: "ONTOLOGY.md",
};

export const API_VERSION = "openworld/v1alpha1";

/** Legacy manifest names (spec 8, revised): these at the package root make a package invalid. */
export const LEGACY_MANIFEST_NAMES = ["package.yaml", "world.yaml"];
