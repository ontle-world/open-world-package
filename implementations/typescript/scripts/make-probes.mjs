// Generates probes/: packages that exercise rules the official suite does not cover.
// Verdicts in probes/expected.yaml are THIS implementation's readings of the spec,
// not reference results; run the reference validator on them to find divergences.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { stringify } from "yaml";

const out = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "probes");
fs.rmSync(out, { recursive: true, force: true });
const expected = {};

const AV = "openworld/v1alpha1";
const view = (worldRef = "probe/w@0.1.0") => ({ apiVersion: AV, kind: "WorldViewProfile", metadata: { name: "v" }, spec: { worldRef } });
const compiler = (worldViewRef = "views/task.yaml", extra = {}) => ({
  apiVersion: AV, kind: "StateCompilerProfile", metadata: { name: "c" },
  spec: { worldViewRef, outputContract: "EffectiveWorldState", outputSchema: { fields: ["e.s"] }, ...extra },
});
const worldManifest = (specExtra = {}, worldExtra = {}, assets) => ({
  apiVersion: AV, kind: "WorldPackage", metadata: { namespace: "probe", name: "w", version: "0.1.0" },
  spec: {
    world: { description: "WORLD.md", definition: "Probe World.", defaultView: "views/task.yaml", defaultStateCompiler: "state/task.yaml", ...worldExtra },
    conformance: { profile: "stateful" },
    assets: assets ?? [
      { kind: "WorldViewProfile", path: "views/task.yaml" },
      { kind: "StateCompilerProfile", path: "state/task.yaml" },
    ],
    ...specExtra,
  },
});
const worldFiles = () => ({ "WORLD.md": "# Probe\n", "views/task.yaml": view(), "state/task.yaml": compiler() });

// Spec 5.1 ExternalRef, pinned by digest (was {provider: "x", repository} before ExternalRef was defined).
const xref = (name) => ({ provider: "https", uri: `https://example.org/${name}`, digest: `sha256:${"0".repeat(64)}` });

const G = "probe/world@0.1.0";
const evalProfile = (version = "1.0.0", extra = {}) => ({ apiVersion: AV, kind: "EvaluationProfile", metadata: { name: "ev", ...(version ? { version } : {}) }, spec: { ...extra } });
const evidence = (specOver = {}, scopeOver = {}) => ({
  apiVersion: AV, kind: "CompatibilityEvidence", metadata: { name: "e" },
  spec: { subject: "probe/m@0.1.0", evaluationProfile: "ev@1.0.0", scope: { worldRef: G, worldView: `${G}#views/task.yaml`, ...scopeOver }, result: { status: "illustrative" }, ...specOver },
});
const modelManifest = (wmOver = {}, assets, sgOver = {}) => ({
  apiVersion: AV, kind: "WorldModelPackage", metadata: { namespace: "probe", name: "m", version: "0.1.0" },
  spec: {
    worldModel: {
      roles: ["dynamics_prediction"],
      semanticGrounding: { worldRef: G, compatibleWorldViews: [`${G}#views/task.yaml`], compatibleStateCompilers: [`${G}#state/task.yaml`], ...sgOver },
      inputs: { contract: "EffectiveWorldState" },
      representation: { adapterRef: "models/adapter.yaml" },
      ...wmOver,
    },
    assets: assets ?? [
      { kind: "RepresentationAdapterProfile", path: "models/adapter.yaml" },
      { kind: "EvaluationProfile", path: "eval/profile.yaml" },
    ],
  },
});
const modelFiles = () => ({
  "WORLDMODEL.md": "# Probe model\n",
  "models/adapter.yaml": { apiVersion: AV, kind: "RepresentationAdapterProfile", metadata: { name: "a" }, spec: { source: "EffectiveWorldState", target: "identity" } },
  "eval/profile.yaml": evalProfile(),
});
const withEvidence = (ev, extraFiles = {}) => ({
  "owp.yaml": modelManifest({}, [
    { kind: "RepresentationAdapterProfile", path: "models/adapter.yaml" },
    { kind: "EvaluationProfile", path: "eval/profile.yaml" },
    { kind: "CompatibilityEvidence", path: "eval/evidence.yaml" },
    ...Object.keys(extraFiles).filter((f) => f.startsWith("eval/verifier")).map((p) => ({ kind: "VerifierPackage", path: p })),
  ]),
  ...modelFiles(),
  "eval/evidence.yaml": ev,
  ...extraFiles,
});

/**
 * Spec 5: local assets are discovered by their apiVersion and kind. A manifest entry with a path is dropped
 * when the probe supplies that file; entries for files the probe does not supply stay, so they are reported.
 */
function discovered(files) {
  const m = files["owp.yaml"];
  if (!m || typeof m !== "object" || !Array.isArray(m.spec?.assets)) return files;
  const assets = m.spec.assets.filter((a) => !(a.path !== undefined && a.ref === undefined && a.kind !== "PackageExample" && a.path in files));
  const spec = { ...m.spec };
  if (assets.length) spec.assets = assets;
  else delete spec.assets;
  return { ...files, "owp.yaml": { ...m, spec } };
}

/** discovered() for every package in a tree of files (keys "<dir>/owp.yaml"). */
function discoveredTree(files) {
  const roots = Object.keys(files).filter((k) => k === "owp.yaml" || k.endsWith("/owp.yaml")).map((k) => k.slice(0, -"owp.yaml".length));
  let outFiles = { ...files };
  for (const pre of roots) {
    const sub = Object.fromEntries(Object.entries(outFiles).filter(([k]) => k.startsWith(pre)).map(([k, v]) => [k.slice(pre.length), v]));
    outFiles = { ...outFiles, [`${pre}owp.yaml`]: discovered(sub)["owp.yaml"] };
  }
  return outFiles;
}

function probe(id, files, exp) {
  files = discovered(files);
  const dir = path.join(out, "cases", id);
  for (const [rel, content] of Object.entries(files)) {
    const f = path.join(dir, rel);
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, typeof content === "string" ? content : stringify(content));
  }
  expected[id] = exp;
}

// --- Section 2/8: manifest and filesystem ---
probe("p-baseline-stateful", { "owp.yaml": worldManifest(), ...worldFiles() }, { valid: true, satisfiedProfile: "model-ready", rule: "baseline" });
probe("p-legacy-package-yaml", { "owp.yaml": worldManifest(), ...worldFiles(), "package.yaml": "name: legacy\n" }, { valid: false, satisfiedProfile: "model-ready", rule: "legacy manifest name next to owp.yaml (spec 8; names not listed)" });
probe("p-second-manifest-owp-yml", { "owp.yaml": worldManifest(), ...worldFiles(), "owp.yml": stringify(worldManifest()) }, { valid: false, satisfiedProfile: "model-ready", rule: "owp.yml is not a manifest; with an OWP apiVersion and a package kind it is a document of no asset kind (asset.kind, spec 5)" });
probe("p-missing-human-card", { "owp.yaml": worldManifest(), "views/task.yaml": view(), "state/task.yaml": compiler() }, { valid: false, satisfiedProfile: "model-ready", rule: "required human card (spec 8)" });
probe("p-namespace-with-slash", { "owp.yaml": { ...worldManifest(), metadata: { namespace: "a/b", name: "w", version: "0.1.0" } }, ...worldFiles(), "views/task.yaml": view("self") }, { valid: false, satisfiedProfile: "model-ready", rule: "identity <namespace>/<name>@<version> must be unambiguous (not stated in spec)" });
probe("p-version-not-semver", { "owp.yaml": { ...worldManifest(), metadata: { namespace: "probe", name: "w", version: "1.0" } }, ...worldFiles(), "views/task.yaml": view("self") }, { valid: false, satisfiedProfile: "model-ready", rule: "Version uses SemVer (spec 2)" });
probe("p-ontology-minimal", { "owp.yaml": { apiVersion: AV, kind: "OntologyPackage", metadata: { namespace: "probe", name: "o", version: "0.1.0" }, spec: {} }, "ONTOLOGY.md": "# O\n" }, { valid: false, rule: "Appendix A ontology.spec: OntologyPackage requires spec.ontology (round 3)" });

// --- Section 5/8: assets ---
probe("p-duplicate-asset-path", { "owp.yaml": worldManifest({}, {}, [
  { kind: "PackageExample", path: "examples/a.yaml" }, { kind: "PackageExample", path: "examples/a.yaml" }]), ...worldFiles(), "examples/a.yaml": "a: 1\n" },
  { valid: false, satisfiedProfile: "model-ready", rule: "a PackageExample path is listed once (spec 8)" });
probe("p-duplicate-asset-path-dotslash", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "WorldViewProfile", path: "./views/task.yaml" }]), ...worldFiles() },
  { valid: false, satisfiedProfile: "model-ready", rule: "duplicate detection after path normalization (unspecified)" });
probe("p-missing-asset-file", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "ScenarioProfile", path: "scenarios/missing.yaml" }]), ...worldFiles() },
  { valid: false, satisfiedProfile: "model-ready", rule: "local asset references must resolve (spec 8)" });
probe("p-asset-path-escapes-root", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "ScenarioProfile", path: "../p-baseline-stateful/views/task.yaml" }]), ...worldFiles() },
  { valid: false, satisfiedProfile: "model-ready", rule: "asset paths are package-relative (unspecified)" });
probe("p-unknown-asset-kind", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "HologramProfile", path: "x/h.yaml" }]), ...worldFiles(),
  "x/h.yaml": { apiVersion: AV, kind: "HologramProfile", metadata: { name: "h" }, spec: {} } },
  { valid: false, satisfiedProfile: "model-ready", rule: "a discovered OWP document must name a known asset kind (asset.kind, spec 5); a manifest ref's kind stays open" });
probe("p-asset-path-and-ref", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "ModelArtifact", path: "views/task.yaml", ref: { provider: "hf" } }]), ...worldFiles() },
  { valid: false, satisfiedProfile: "model-ready", rule: "asset has exactly one of path/ref (schema oneOf)" });
probe("p-untyped-view-file", { "owp.yaml": worldManifest(), ...worldFiles(), "views/task.yaml": { spec: { worldRef: "probe/w@0.1.0" } } },
  { valid: false, satisfiedProfile: "descriptive", rule: "a file without an OWP apiVersion is not an asset, so defaultView names no View (spec 5)" });

// --- Section 6.1: profiles ---
probe("p-conformance-without-profile", { "owp.yaml": worldManifest({ conformance: {} }), ...worldFiles() }, { valid: true, satisfiedProfile: "model-ready", rule: "conformance: {} treated as descriptive (unspecified)" });
probe("p-descriptive-with-broken-default-view", { "owp.yaml": worldManifest({ conformance: { profile: "descriptive" } }, { defaultView: "views/missing.yaml" }), ...worldFiles() },
  { valid: true, satisfiedProfile: "descriptive", rule: "requirements of higher profiles are not checked when not declared" });
probe("p-default-view-not-listed", { "owp.yaml": worldManifest({ conformance: { profile: "viewable" } }, { defaultView: "views/other.yaml" }), ...worldFiles(), "views/other.yaml": view() },
  { valid: true, satisfiedProfile: "viewable", rule: "a View file is an asset without being listed (spec 5)" });
probe("p-default-view-dotslash", { "owp.yaml": worldManifest({}, { defaultView: "./views/task.yaml" }), ...worldFiles() },
  { valid: false, satisfiedProfile: "descriptive", rule: "paths are exact strings, no leading ./ (spec 3, round 3)" });
probe("p-view-worldref-not-a-ref", { "owp.yaml": worldManifest(), ...worldFiles(), "views/task.yaml": view("anything") },
  { valid: false, satisfiedProfile: "descriptive", rule: "View worldRef must be self or the package identity (spec 6.1 revised)" });
probe("p-second-compiler-unknown-view", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "StateCompilerProfile", path: "state/other.yaml" }]),
  ...worldFiles(), "state/other.yaml": compiler("views/missing.yaml") },
  { valid: false, satisfiedProfile: "viewable", rule: "EVERY local StateCompilerProfile names a local WorldViewProfile" });
probe("p-model-ready-outputschemaref", { "owp.yaml": worldManifest({ conformance: { profile: "model-ready" } }), ...worldFiles(),
  "state/task.yaml": { apiVersion: AV, kind: "StateCompilerProfile", metadata: { name: "c" }, spec: { worldViewRef: "views/task.yaml", outputContract: "EffectiveWorldState", outputSchemaRef: "schemas/ews.json" } },
  "schemas/ews.json": JSON.stringify({ type: "object", properties: { "entity.state": {} } }) },
  { valid: true, satisfiedProfile: "model-ready", rule: "outputSchemaRef names a JSON Schema whose top-level properties are the EWS fields (spec 12.1)" });
probe("p-action-ready-via-refs", { "owp.yaml": worldManifest({ conformance: { profile: "action-ready" } }, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" },
  { kind: "ActionBindingProfile", ref: xref("a") }, { kind: "CommitContract", ref: xref("c") }, { kind: "EffectVerificationProfile", ref: xref("e") }]), ...worldFiles() },
  { valid: true, satisfiedProfile: "action-ready", rule: "action-ready assets may be external refs? (unspecified)" });
probe("p-conformance-on-model-package", { "owp.yaml": { ...modelManifest(), spec: { ...modelManifest().spec, conformance: { profile: "stateful" } } }, ...modelFiles() },
  { valid: true, rule: "conformance on non-World package (schema: WorldPackage only; this impl warns)" });

// --- Section 3/6: World Model ---
const { "models/adapter.yaml": _adapter, ...modelFilesWithoutAdapter } = modelFiles();
probe("p-model-no-adapter-asset", { "owp.yaml": modelManifest({}, [{ kind: "EvaluationProfile", path: "eval/profile.yaml" }]), ...modelFilesWithoutAdapter },
  { valid: false, rule: "Representation Adapter required (spec 8)" });
probe("p-model-adapterref-not-asset", { "owp.yaml": modelManifest({ representation: { adapterRef: "models/other.yaml" } }), ...modelFiles(), "models/other.yaml": "x: 1\n" },
  { valid: false, rule: "adapterRef MUST point to the packaged Representation Adapter (spec 6)" });
probe("p-model-inputs-wrong-contract", { "owp.yaml": modelManifest({ inputs: { contract: "RawObservations" } }), ...modelFiles() },
  { valid: false, rule: "inputs.contract MUST be EffectiveWorldState" });
probe("p-model-empty-roles", { "owp.yaml": modelManifest({ roles: [] }), ...modelFiles() }, { valid: false, rule: "roles (schema minItems 1)" });
probe("p-model-worldref-not-identity", { "owp.yaml": modelManifest({}, undefined, { worldRef: "world", compatibleWorldViews: ["world#views/task.yaml"], compatibleStateCompilers: ["world#state/task.yaml"] }), ...modelFiles() },
  { valid: false, rule: "worldRef form <namespace>/<name>@<version> (implied, not stated)" });
probe("p-model-grounding-dotslash-path", { "owp.yaml": modelManifest({}, undefined, { compatibleWorldViews: [`${G}#./views/task.yaml`] }), ...modelFiles() },
  { valid: false, rule: "<asset path> normal form (unspecified)" });
probe("p-model-grounding-empty-path", { "owp.yaml": modelManifest({}, undefined, { compatibleWorldViews: [`${G}#`] }), ...modelFiles() },
  { valid: false, rule: "<asset path> non-empty" });

// --- Section 9: evidence ---
probe("p-evidence-worldref-mismatch", withEvidence(evidence({}, { worldRef: "probe/other@0.1.0" })), { valid: false, rule: "scope.worldRef equals semanticGrounding.worldRef" });
probe("p-evidence-missing-worldview", withEvidence((() => { const e = evidence(); delete e.spec.scope.worldView; return e; })()), { valid: false, rule: "scope.worldView required" });
probe("p-evidence-missing-profile", withEvidence((() => { const e = evidence(); delete e.spec.evaluationProfile; return e; })()), { valid: false, rule: "evaluationProfile required" });
probe("p-evidence-unpinned-goldenset", withEvidence(evidence({ goldenSet: "gold@~1.0.0" })), { valid: false, rule: "goldenSet pinned" });
probe("p-evidence-unpinned-dataset", withEvidence(evidence({ dataset: "episodes@latest" })), { valid: false, rule: "dataset pinned" });
probe("p-evidence-verifier-version-mismatch", withEvidence(evidence({ verifier: "vf@0.2.0" }),
  { "eval/verifier.yaml": { apiVersion: AV, kind: "VerifierPackage", metadata: { name: "vf", version: "0.1.0" }, spec: {} } }),
  { valid: false, rule: "local VerifierPackage version must match" });
probe("p-evidence-profile-not-local", withEvidence(evidence({ evaluationProfile: "external-eval@3.0.0" })), { valid: true, rule: "version match only when packaged locally" });
probe("p-evidence-local-profile-unversioned", { ...withEvidence(evidence()), "eval/profile.yaml": evalProfile(null) },
  { valid: false, rule: "local EvaluationProfile without metadata.version cannot match a pinned reference (unspecified)" });
probe("p-evidence-subject-other-package", withEvidence(evidence({ subject: "someone/else@9.9.9" })), { valid: false, rule: "subject MUST equal the package identity (spec 9 revised)" });
probe("p-evidence-no-result", withEvidence((() => { const e = evidence(); delete e.spec.result; return e; })()), { valid: false, rule: "result required (schema)" });
probe("p-evidence-in-world-package", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "CompatibilityEvidence", path: "eval/evidence.yaml" }]),
  ...worldFiles(), "eval/evidence.yaml": evidence({}, { worldRef: "probe/w@0.1.0", worldView: "probe/w@0.1.0#views/does-not-exist.yaml" }) },
  { valid: true, satisfiedProfile: "model-ready", rule: "scope rules are defined only inside a WorldModelPackage" });
probe("p-eval-unversioned-standalone", { ...modelFiles(), "owp.yaml": modelManifest(), "eval/profile.yaml": evalProfile(null) }, { valid: true, rule: "metadata.version is SHOULD (warning)" });
probe("p-eval-supersedes-without-reason", { ...modelFiles(), "owp.yaml": modelManifest(), "eval/profile.yaml": evalProfile("0.2.0", { supersedes: "ev@0.1.0" }) },
  { valid: true, rule: "changedBecause is not validated in this alpha (spec 9 revised)" });
probe("p-eval-supersedes-newer", { ...modelFiles(), "owp.yaml": modelManifest(), "eval/profile.yaml": evalProfile("0.2.0", { supersedes: "ev@0.3.0", changedBecause: ["x"] }) },
  { valid: true, rule: "supersedes only needs to be pinned; ordering is not a rule (this impl warns)" });


// ===================== Round 2 probes (spec 8 bindings, 11, 12) =====================
const wfFields = ["a.latest", "b.all", "c.unbound"];
const ewsWorld = (compilerSpecOver = {}, id = "probe/ews@0.1.0") => {
  const [ns, rest] = id.split("/"); const [name, version] = rest.split("@");
  return {
    "owp.yaml": { apiVersion: AV, kind: "WorldPackage", metadata: { namespace: ns, name, version },
      spec: { world: { description: "WORLD.md", definition: "EWS probe World.", defaultView: "views/task.yaml", defaultStateCompiler: "state/task-compiler.yaml" },
        conformance: { profile: "model-ready" },
        assets: [{ kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task-compiler.yaml" }] } },
    "WORLD.md": "# EWS probe\n",
    "views/task.yaml": { apiVersion: AV, kind: "WorldViewProfile", metadata: { name: "v" }, spec: { worldRef: "self" } },
    "state/task-compiler.yaml": { apiVersion: AV, kind: "StateCompilerProfile", metadata: { name: "c" },
      spec: { worldViewRef: "views/task.yaml", outputContract: "EffectiveWorldState", outputSchema: { fields: wfFields },
        bindings: { "a.latest": { from: "sensor.a", value: "v", select: "latest" }, "b.all": { from: "sensor.b", value: "v", select: "all" } },
        traceRequired: true, ...compilerSpecOver } },
  };
};
const prefixed = (pre, files) => Object.fromEntries(Object.entries(files).map(([k, v]) => [`${pre}/${k}`, v]));
const obsSet = (list) => ({ apiVersion: AV, kind: "ObservationSet", spec: { observations: list } });
const ewsDoc = (specOver) => ({ apiVersion: AV, kind: "EffectiveWorldState", spec: {
  worldRef: "probe/ews@0.1.0", worldView: "probe/ews@0.1.0#views/task.yaml", stateCompiler: "probe/ews@0.1.0#state/task-compiler.yaml",
  context: { asOf: "2026-01-01T00:00:10Z" }, state: { "a.latest": 1, "b.all": ["b"] }, unresolved: {}, missing: ["c.unbound"],
  provenance: { "a.latest": ["o1"], "b.all": ["o2"] }, ...specOver } });

// spec 8/12.2: bindings checked at declared stateful+; this impl does not let them lower satisfiedProfile.
probe("p2-bindings-bad-key-declared-model-ready", ewsWorld({ bindings: { "zzz": { from: "x", value: "v" } } }),
  { valid: false, satisfiedProfile: "viewable", rule: "malformed binding fails stateful for declared and satisfied profile (spec 6.1, round 3)" });
probe("p2-bindings-bad-key-declared-descriptive", (() => { const f = ewsWorld({ bindings: { "zzz": { from: "x", value: "v" } } }); f["owp.yaml"].spec.conformance.profile = "descriptive"; return f; })(),
  { valid: true, satisfiedProfile: "viewable", rule: "not declared stateful: valid, but satisfied profile drops (spec 6.1, round 3)" });
probe("p2-bindings-bad-select", ewsWorld({ bindings: { "a.latest": { from: "sensor.a", value: "v", select: "first" } } }),
  { valid: false, satisfiedProfile: "viewable", rule: "select is latest|all; fails stateful (round 3)" });
probe("p2-namespaced-asset-kind", { "owp.yaml": worldManifest({ dependencies: [{ ref: "acme/ext@1.0.0", as: "acme" }] }, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "acme:Hologram", path: "x/h.yaml" }]), ...worldFiles(),
  "x/h.yaml": { apiVersion: AV, kind: "acme:Hologram", metadata: { name: "h" }, spec: { extensions: { acme: { depth: 3 } } } } },
  { valid: true, satisfiedProfile: "model-ready", rule: "extension kinds <name>:<Kind> are accepted when <name> is declared with as (spec 13; was: any namespaced kind)" });
probe("p2-package-example-unparseable", { "owp.yaml": worldManifest({}, {}, [
  { kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }, { kind: "PackageExample", path: "examples/bad.yaml" }]), ...worldFiles(),
  "examples/bad.yaml": "a: [unclosed\n" },
  { valid: false, satisfiedProfile: "model-ready", rule: "PackageExample YAML must parse (spec 8; was: not parsed)" });
probe("p2-dependency-range", { "owp.yaml": { ...worldManifest(), spec: { ...worldManifest().spec, dependencies: ["probe/base@^1.0.0"] } }, ...worldFiles() },
  { valid: false, satisfiedProfile: "model-ready", rule: "ranges are not allowed in spec.dependencies (checked without --resolve in this impl)" });
probe("p2-identity-invalid-but-view-matches", { "owp.yaml": { ...worldManifest(), metadata: { namespace: "probe", name: "w", version: "0.1" } }, ...worldFiles(), "views/task.yaml": view("probe/w@0.1") },
  { valid: false, satisfiedProfile: "model-ready", rule: "View worldRef compared with the raw identity even when version is not SemVer (unspecified)" });

// ---- resolution probes
const resWorld = (id, extraSpec = {}) => {
  const [ns, rest] = id.split("/"); const [name, version] = rest.split("@");
  return { "owp.yaml": { apiVersion: AV, kind: "WorldPackage", metadata: { namespace: ns, name, version },
      spec: { world: { description: "WORLD.md", definition: "d", defaultView: "views/task.yaml", defaultStateCompiler: "state/task.yaml" },
        conformance: { profile: "stateful" }, assets: [{ kind: "WorldViewProfile", path: "views/task.yaml" }, { kind: "StateCompilerProfile", path: "state/task.yaml" }], ...extraSpec } },
    "WORLD.md": "# w\n", "views/task.yaml": view("self"), "state/task.yaml": compiler() };
};
const resModel = (deps, sgOver = {}) => {
  const m = modelManifest({}, undefined, sgOver);
  m.spec.dependencies = deps;
  return { "owp.yaml": m, ...modelFiles() };
};
const resolution = {};
function rprobe(id, root, packages, exp) {
  const dir = path.join(out, "resolution", id);
  for (const [rel, content] of Object.entries(discoveredTree({ ...prefixed("root", root), ...prefixed("packages", packages) }))) {
    const f = path.join(dir, rel);
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, typeof content === "string" ? content : stringify(content));
  }
  if (!Object.keys(packages).length) fs.mkdirSync(path.join(dir, "packages"), { recursive: true });
  resolution[id] = exp;
}
rprobe("r-baseline", resModel([G]), prefixed("world", resWorld(G)), { valid: true, rule: "baseline" });
rprobe("r-diamond-same-version", resModel([G, "probe/tax@1.0.0"]), {
  ...prefixed("world", resWorld(G, { dependencies: ["probe/tax@1.0.0"] })),
  ...prefixed("tax", { "owp.yaml": { apiVersion: AV, kind: "WorldPackage", metadata: { namespace: "probe", name: "tax", version: "1.0.0" }, spec: { world: { definition: "t" } } }, "WORLD.md": "# t\n" }) },
  { valid: true, rule: "the same exact version reached twice is not a conflict" });
rprobe("r-depends-on-itself", resModel([G, "probe/m@0.1.0"]), prefixed("world", resWorld(G)), { valid: false, rule: "a package depending on its own identity is a cycle" });
rprobe("r-root-other-version", resModel([G, "probe/m@0.2.0"]), {
  ...prefixed("world", resWorld(G)),
  ...prefixed("m2", { "owp.yaml": { apiVersion: AV, kind: "OntologyPackage", metadata: { namespace: "probe", name: "m", version: "0.2.0" }, spec: {} }, "ONTOLOGY.md": "# o\n" }) },
  { valid: false, rule: "the root's own name at another version is a conflict (is the root part of the closure?)" });
rprobe("r-deep-three-levels", resModel([G]), prefixed("a/b/c/world", resWorld(G)), { valid: false, rule: "directory sources scan at most two levels below" });
rprobe("r-two-levels", resModel([G]), prefixed("a/world", resWorld(G)), { valid: true, rule: "packages two levels below the source are found" });
rprobe("r-mapping-source", (() => { const r = resModel([{ ref: G, source: "../elsewhere" }]); r["../elsewhere/world/owp.yaml"] = resWorld(G)["owp.yaml"]; r["../elsewhere/world/WORLD.md"] = "# w\n"; r["../elsewhere/world/views/task.yaml"] = view("self"); r["../elsewhere/world/state/task.yaml"] = compiler(); return r; })(), {},
  { valid: true, rule: "{ref, source} relative source resolved against the declaring package directory (unspecified)" });
rprobe("r-transitive-model-bad", resModel([G, "probe/m2@0.1.0"]), {
  ...prefixed("world", resWorld(G)),
  ...prefixed("m2", (() => { const x = resModel([G], { compatibleWorldViews: [`${G}#views/nope.yaml`] }); x["owp.yaml"].metadata.name = "m2"; return x; })()) },
  { valid: false, rule: "cross-package rules apply to every WorldModelPackage in the closure? (unspecified)" });
rprobe("r-world-not-worldpackage", resModel([G]), prefixed("world", { "owp.yaml": { apiVersion: AV, kind: "OntologyPackage", metadata: { namespace: "probe", name: "world", version: "0.1.0" }, spec: {} }, "ONTOLOGY.md": "# o\n" }),
  { valid: false, rule: "worldRef must resolve to a WorldPackage" });
rprobe("r-compiler-view-listed-with-dotslash", resModel([G]), prefixed("world", { ...resWorld(G), "state/task.yaml": compiler("./views/task.yaml") }),
  { valid: false, rule: "compiler worldViewRef compared exactly with compatible View paths; also invalid at stateful in this impl? (normalization unspecified for local paths)" });

// ---- EWS compile probes
const ewsCompile = {};
function eprobe(id, worldFiles, observations, asOf, expectedEws, exp) {
  const dir = path.join(out, "ews", id);
  const files = { ...prefixed("world", worldFiles), "observations.yaml": observations, ...(expectedEws ? { "expected-ews.yaml": expectedEws } : {}) };
  for (const [rel, content] of Object.entries(files)) {
    const f = path.join(dir, rel);
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, typeof content === "string" ? content : stringify(content));
  }
  ewsCompile[id] = { compiler: "state/task-compiler.yaml", asOf, ...exp };
}
const T = (s) => `2026-01-01T00:00:0${s}Z`;
eprobe("e-null-value-is-candidate", ewsWorld(), obsSet([{ id: "o1", type: "sensor.a", observedAt: T(1), values: { v: null } }]), T(9),
  ewsDoc({ context: { asOf: T(9) }, state: { "a.latest": null }, missing: ["b.all", "c.unbound"], provenance: { "a.latest": ["o1"] } }),
  { rule: "a values key present with null is a candidate (key presence)" });
eprobe("e-deep-equal-tie", ewsWorld(), obsSet([
  { id: "o1", type: "sensor.a", observedAt: T(1), values: { v: { x: 1, y: 2 } } },
  { id: "o2", type: "sensor.a", observedAt: T(1), values: { v: { y: 2, x: 1 } } }]), T(9),
  ewsDoc({ context: { asOf: T(9) }, state: { "a.latest": { x: 1, y: 2 } }, missing: ["b.all", "c.unbound"], provenance: { "a.latest": ["o1", "o2"] } }),
  { rule: "mapping values compare structurally (key order irrelevant)" });
eprobe("e-numeric-equality-1-vs-1.0", ewsWorld(), obsSet([
  { id: "o1", type: "sensor.a", observedAt: T(1), values: { v: 1 } },
  { id: "o2", type: "sensor.a", observedAt: T(1), values: { v: 1.0 } }]), T(9),
  ewsDoc({ context: { asOf: T(9) }, state: { "a.latest": 1 }, missing: ["b.all", "c.unbound"], provenance: { "a.latest": ["o1", "o2"] } }),
  { rule: "1 and 1.0 are equal values (YAML/JSON numeric equality; unspecified across languages)" });
eprobe("e-id-order-codepoint", ewsWorld(), obsSet([
  { id: "b", type: "sensor.b", observedAt: T(1), values: { v: 2 } },
  { id: "B", type: "sensor.b", observedAt: T(1), values: { v: 1 } },
  { id: "o10", type: "sensor.b", observedAt: T(1), values: { v: 4 } },
  { id: "o9", type: "sensor.b", observedAt: T(1), values: { v: 3 } }]), T(9),
  ewsDoc({ context: { asOf: T(9) }, state: { "b.all": [1, 2, 4, 3] }, missing: ["a.latest", "c.unbound"], provenance: { "b.all": ["B", "b", "o10", "o9"] } }),
  { rule: "id tie-break is plain code-point string order (unspecified: locale/natural order would differ)" });
eprobe("e-opaque-compiler", ewsWorld({ bindings: undefined }), obsSet([]), T(9), null, { error: true, rule: "a compiler without bindings cannot be compiled declaratively (refusal is this impl's reading)" });
eprobe("e-invalid-calendar-date", ewsWorld(), obsSet([{ id: "o1", type: "sensor.a", observedAt: "2026-02-30T00:00:00Z", values: { v: 1 } }]), T(9), null,
  { error: true, rule: "pattern-valid but impossible timestamp (unspecified)" });
eprobe("e-unquoted-timestamp", ewsWorld(), "apiVersion: openworld/v1alpha1\nkind: ObservationSet\nspec:\n  observations:\n  - id: o1\n    type: sensor.a\n    observedAt: 2026-01-01T00:00:01Z\n    values: {v: 1}\n", T(9),
  ewsDoc({ context: { asOf: T(9) }, state: { "a.latest": 1 }, missing: ["b.all", "c.unbound"], provenance: { "a.latest": ["o1"] } }),
  { rule: "unquoted YAML timestamps (SHOULD quote): YAML 1.1 parsers yield a datetime, YAML 1.2 a string" });
eprobe("e-extra-unknown-type-ignored", ewsWorld(), obsSet([{ id: "o1", type: "other", observedAt: T(1), values: { v: 1 } }]), T(9),
  ewsDoc({ context: { asOf: T(9) }, state: {}, missing: ["a.latest", "b.all", "c.unbound"], provenance: {} }),
  { rule: "observations of unbound types are ignored" });

// ---- EWS check probes
const ewsCheck = {};
function cprobe(id, worldFiles, ews, exp) {
  const dir = path.join(out, "ews-check", id);
  for (const [rel, content] of Object.entries({ ...prefixed("world", worldFiles), "ews.yaml": ews })) {
    const f = path.join(dir, rel);
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, typeof content === "string" ? content : stringify(content));
  }
  ewsCheck[id] = exp;
}
cprobe("c-baseline", ewsWorld(), ewsDoc({}), { valid: true, rule: "baseline" });
cprobe("c-unresolved-duplicates", ewsWorld(), ewsDoc({ state: { "b.all": ["b"] }, unresolved: { "a.latest": [1, 1] } }), { valid: false, rule: "two equal alternatives are not two alternatives (unspecified)" });
cprobe("c-provenance-for-missing", ewsWorld(), ewsDoc({ provenance: { "a.latest": ["o1"], "b.all": ["o2"], "c.unbound": ["o3"] } }), { valid: false, rule: "provenance only for state/unresolved fields" });
cprobe("c-no-trace-required", ewsWorld({ traceRequired: false }), ewsDoc({ provenance: {} }), { valid: true, rule: "provenance optional without traceRequired" });
cprobe("c-worldref-self", ewsWorld(), ewsDoc({ worldRef: "self" }), { valid: false, rule: "EWS worldRef must be the identity, not self" });
cprobe("c-schema-ref-only-compiler", { ...ewsWorld({ outputSchema: undefined, outputSchemaRef: "schemas/ews.json", bindings: undefined }),
  "schemas/ews.json": JSON.stringify({ type: "object", properties: { "a.latest": {}, "b.all": {}, "c.unbound": {} } }) }, ewsDoc({}),
  { valid: true, rule: "outputSchemaRef-only compilers take their EWS fields from the schema's properties (spec 12.1)" });
cprobe("c-missing-omitted", ewsWorld(), (() => { const d = ewsDoc({ state: { "a.latest": 1, "b.all": ["b"] } }); delete d.spec.missing; delete d.spec.unresolved; d.spec.state["c.unbound"] = null; d.spec.provenance["c.unbound"] = ["o3"]; return d; })(),
  { valid: true, rule: "a field with null value in state counts as present (unspecified)" });
cprobe("c-bad-asof", ewsWorld(), ewsDoc({ context: { asOf: "2026-01-01 00:00:10" } }), { valid: false, rule: "asOf must be UTC form" });
fs.writeFileSync(path.join(out, "expected.yaml"), "# Verdicts of owp-validator-ts (clean-room), NOT reference results.\n" + stringify({ suite: "owp-cleanroom-probes", cases: expected, resolutionCases: resolution, ewsCases: ewsCompile, ewsCheckCases: ewsCheck }));
console.log(`wrote ${Object.keys(expected).length} probes to ${out}`);
