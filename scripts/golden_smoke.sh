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

ontle validate --resolve --source examples examples/business/quality-transition-world-model
ontle validate --resolve --source examples examples/physical-ai/multimodal-action-world-model

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ontle init demo-world --namespace smoke --destination "$TMP/demo-world"
ontle init demo-ontology --template ontology --namespace smoke --destination "$TMP/demo-ontology"
ontle init demo-model --template worldmodel --namespace smoke --destination "$TMP/demo-model"
ontle init demo-vla --template worldmodel-multimodal --namespace smoke --destination "$TMP/demo-vla"
ontle add source mes --path "$TMP/demo-world"
ontle add scenario smoke --path "$TMP/demo-world"
ontle add view smoke-view --path "$TMP/demo-world"
ontle add compiler smoke-state --path "$TMP/demo-world"
ontle add verifier smoke-verifier --path "$TMP/demo-model"
ontle add extension acme/quality-extension@1.2.0 --path "$TMP/demo-world"
ontle add view regional-view --specializes views/default.yaml --path "$TMP/demo-world"
ontle add knowledge playbook --path "$TMP/demo-world"
ontle add artifact report --path "$TMP/demo-world"
ontle add pattern triage --path "$TMP/demo-world"
ontle add task triage-task --path "$TMP/demo-world"
ontle add consumer manager --path "$TMP/demo-world"
ontle add template report-template --path "$TMP/demo-world"
ontle validate "$TMP/demo-world"
ontle validate "$TMP/demo-ontology"
ontle validate "$TMP/demo-model"
ontle validate "$TMP/demo-vla"
ontle inspect "$TMP/demo-world" --graph --resolved-views >/dev/null
ARCHIVE="$(ontle pack "$TMP/demo-world")"
ontle verify "$ARCHIVE"

W=examples/business/manufacturing-quality-world
ontle ews compile "$W" --compiler state/quality-incident-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-05T00:00:00Z > "$TMP/quality-ews.yaml"
ontle ews check "$TMP/quality-ews.yaml" --world "$W"
W=examples/physical-ai/mobile-manipulation-world
ontle ews compile "$W" --compiler state/pick-place-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-01T12:00:03Z > "$TMP/pick-place-ews.yaml"
ontle ews check "$TMP/pick-place-ews.yaml" --world "$W"
W=examples/business/sales-prioritization-world
ontle ews compile "$W" --compiler state/account-priority-compiler.yaml --observations "$W/examples/observations.yaml" --as-of 2026-09-15T00:00:00Z > "$TMP/sales-ews.yaml"
ontle ews check "$TMP/sales-ews.yaml" --world "$W"

echo "GOLDEN SMOKE PASS"
