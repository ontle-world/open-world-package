/**
 * Asset kind vocabulary, copied from vocab/asset-kinds.yaml (public alpha).
 * The spec does not say whether this vocabulary is closed; this implementation
 * warns (does not error) on kinds outside it.
 */
export const ASSET_KINDS: Record<string, string[]> = {
  semantic: ["SemanticProfile", "WorldDefinition", "WorldViewProfile", "StateCompilerProfile"],
  interface: [
    "SourceSystemSchemaProfile",
    "SourceAdapterProfile",
    "MappingSpec",
    "IdentityResolutionProfile",
    "ObservationAcquisitionProfile",
    "ActionBindingProfile",
    "CommitContract",
    "EffectVerificationProfile",
  ],
  reference: ["ReferenceEnterpriseProfile", "ReferenceIndustryProfile", "ScenarioProfile", "EnvironmentProfile"],
  model: [
    "WorldModelContract",
    "ModelArtifact",
    "RepresentationAdapterProfile",
    "ResolutionProfile",
    "AggregationCoarseGrainingProfile",
  ],
  operational: [
    "CapabilityContract",
    "SkillProfile",
    "ToolProfile",
    "AgentProfile",
    "WorkflowProfile",
    "OperationalAsset",
    "SemanticBinding",
  ],
  evaluation: [
    "Dataset",
    "ReferenceFixture",
    "NegativeFixture",
    "BenchmarkCase",
    "AcceptanceCase",
    "Validator",
    "EvaluationProfile",
    "VerifierPackage",
    "CompatibilityEvidence",
    "Attestation",
  ],
  package_support: ["PackageExample"],
};

export const KNOWN_ASSET_KINDS = new Set(Object.values(ASSET_KINDS).flat());

export const PACKAGE_KINDS = ["WorldPackage", "WorldModelPackage", "OntologyPackage"] as const;

export const HUMAN_CARDS: Record<string, string> = {
  WorldPackage: "WORLD.md",
  WorldModelPackage: "WORLDMODEL.md",
  OntologyPackage: "ONTOLOGY.md",
};

export const API_VERSION = "openworld/v1alpha1";

/** Legacy manifest names (spec 8, revised): these at the package root make a package invalid. */
export const LEGACY_MANIFEST_NAMES = ["package.yaml", "world.yaml"];
