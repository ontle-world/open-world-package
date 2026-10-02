#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m unittest discover -s tests -v

ontle validate examples/business/manufacturing-quality-world
ontle validate examples/business/quality-transition-world-model
ontle validate examples/physical-ai/mobile-manipulation-world
ontle validate examples/physical-ai/multimodal-action-world-model
ontle validate examples/business/sales-prioritization-world
ontle validate examples/ontology/quality-ontology
ontle validate examples/research/assay-optimization-world
ontle export examples/ontology/quality-ontology --format turtle >/dev/null
ontle export examples/ontology/quality-ontology --format jsonld >/dev/null

ontle validate --resolve --source examples examples/business/manufacturing-quality-world
ontle validate --resolve --source examples examples/business/quality-transition-world-model
ontle validate --resolve --source examples examples/physical-ai/multimodal-action-world-model

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ontle init demo-world --namespace smoke --destination "$TMP/demo-world"
ontle init demo-ontology --template ontology --namespace smoke --destination "$TMP/demo-ontology"
ontle init demo-model --template worldmodel --namespace smoke --destination "$TMP/demo-model" --world "$TMP/demo-world"
ontle init demo-vla --template worldmodel-multimodal --namespace smoke --destination "$TMP/demo-vla"
N="ontle new --package $TMP/demo-world"
$N SourceSystemSchemaProfile interfaces/mes.yaml
$N ScenarioProfile scenarios/smoke.yaml
$N WorldViewProfile views/smoke-view.yaml
$N StateCompilerProfile state/smoke-state.yaml
ontle new VerifierPackage eval/smoke-verifier.yaml --package "$TMP/demo-model"
ontle add extension acme/quality-extension@1.2.0 --path "$TMP/demo-world"
$N WorldViewProfile views/regional-view.yaml --specializes views/default.yaml
$N KnowledgeAsset knowledge/playbook.yaml
$N ArtifactContract artifacts/report.yaml
$N WorkPatternProfile patterns/triage.yaml
$N TaskSetProfile tasks/triage-task.yaml
$N ConsumerRepresentationProfile consumers/manager.yaml
$N ArtifactTemplate artifacts/templates/report-template.yaml
$N ActorProfile actors/manager.yaml
$N RoleProfile roles/manager-role.yaml
$N CapabilityContract capabilities/analysis.yaml
$N DelegationProfile delegations/manager-to-agent.yaml
ontle validate "$TMP/demo-world"
ontle validate "$TMP/demo-ontology"
ontle validate "$TMP/demo-model"
ontle validate "$TMP/demo-vla"
ontle inspect "$TMP/demo-world" --graph --resolved-views >/dev/null
ARCHIVE="$(ontle pack "$TMP/demo-world")"
ontle verify "$ARCHIVE"

# distribution: static index, resolution through it, detached evidence, catalogs
mkdir -p "$TMP/pub"
WORLD_ZIP="$(ontle pack examples/physical-ai/mobile-manipulation-world --output "$TMP/pub/world.owp.zip")"
MODEL_ZIP="$(ontle pack examples/physical-ai/multimodal-action-world-model --output "$TMP/pub/model.owp.zip")"
ontle index build "$WORLD_ZIP" "$MODEL_ZIP" --base "$TMP/pub" --output "$TMP/pub/index.json"
ontle validate --resolve --source "index:$TMP/pub/index.json" examples/physical-ai/multimodal-action-world-model
python - "$MODEL_ZIP" "$TMP/evidence.yaml" <<'PY'
import hashlib, sys, yaml
doc = yaml.safe_load(open("examples/physical-ai/multimodal-action-world-model/eval/evidence-reference-sim.yaml"))
doc["spec"]["subjectDigest"] = "sha256:" + hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()
yaml.safe_dump(doc, open(sys.argv[2], "w"), sort_keys=False)
PY
ontle evidence check "$TMP/evidence.yaml" --package "$MODEL_ZIP"
ontle catalog examples/business/manufacturing-quality-world --format dcat >/dev/null
ontle catalog examples/business/manufacturing-quality-world --format croissant >/dev/null
ontle catalog examples/physical-ai/multimodal-action-world-model --format hf-card >/dev/null

W=examples/business/manufacturing-quality-world
ontle ews compile "$W" --compiler state/quality-incident-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-05T00:00:00Z > "$TMP/quality-ews.yaml"
ontle ews check "$TMP/quality-ews.yaml" --world "$W"
ontle ews compile "$W" --compiler state/quality-incident-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-05T00:00:00Z --jsonld --source examples >/dev/null
if python -c "import rdflib" 2>/dev/null; then
  ontle kg extract "$W" --profile extraction/claim-context.yaml --param claimId=C-102 > "$TMP/kg-observations.yaml"
else
  cp "$W/examples/kg-observations.yaml" "$TMP/kg-observations.yaml"  # rdflib (rdf extra) not installed
fi
ontle ews compile "$W" --compiler state/quality-incident-compiler.yaml --observations "$W/examples/observations.yaml" --observations "$TMP/kg-observations.yaml" --as-of 2026-09-05T00:00:00Z > "$TMP/quality-kg-ews.yaml"
ontle ews check "$TMP/quality-kg-ews.yaml" --world "$W"
W=examples/physical-ai/mobile-manipulation-world
ontle ews compile "$W" --compiler state/pick-place-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-01T12:00:03Z > "$TMP/pick-place-ews.yaml"
ontle ews check "$TMP/pick-place-ews.yaml" --world "$W"
W=examples/business/sales-prioritization-world
ontle ews compile "$W" --compiler state/account-priority-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-15T00:00:00Z > "$TMP/sales-ews.yaml"
ontle ews check "$TMP/sales-ews.yaml" --world "$W"

echo "GOLDEN SMOKE PASS"
