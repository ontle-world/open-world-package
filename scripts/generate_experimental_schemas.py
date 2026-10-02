"""Regenerate schemas/experimental/*.schema.json from the field tables in src/ontle/experimental.py,
and the schemas of standard kinds whose tables live in src/ontle/structure.py.

Run from the repository root after changing an experimental kind:

    PYTHONPATH=src python scripts/generate_experimental_schemas.py

tests/test_structure.py checks that tables and schemas define the same fields.
"""
import json
import re
from pathlib import Path

from ontle import experimental, structure

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "schemas" / "owp-manifest.schema.json").read_text(encoding="utf-8"))

STRING_LISTS = {
    "workPatterns", "worldRefs", "worldViews", "knowledge", "worldModels", "capabilities", "workflows", "artifacts",
    "evaluationRefs", "semanticRoles", "requiredContracts", "optionalCapabilities", "formats", "destinations",
    "policyRefs", "validationRefs", "inputs", "sourceBindings", "required", "optional", "artifactContractRefs",
    "capabilityRefs", "feasibleActions", "includes", "modalities", "interfaceRefs", "roles", "objectiveRefs", "id",
    "inputContracts", "outputContracts", "governanceRefs", "sourceRefs", "evidenceRefs", "allowedOperations",
    "triggers", "nodes", "roleRefs", "memberOf", "actions", "decisions", "responsibilities", "accountabilities",
    "permittedActions", "by", "to", "when", "actors", "workPatternRefs", "scenarios", "skills", "tools",
}
STRING_LISTS |= {"assumptions", "constraints", "outcomeRefs", "requiredInputs", "changedBecause", "include", "exclude"}
BOOLEANS = {"approvalRequired", "multi"}
ANY = {"metrics", "tasks", "checks", "threshold", "confidence", "rubric", "effect"}
STANDARD = {
    "WorldViewProfile": ("WORLD_VIEW_PROFILE", ["worldRef"]),
    "EvaluationProfile": ("EVALUATION_PROFILE", []),
    "ScenarioProfile": ("SCENARIO_PROFILE", []),
    "CapabilityContract": ("CAPABILITY_CONTRACT", []),
}
INTEGERS = {"maxIterations"}
DESCRIPTIONS = {
    "parameters": "Parameter name -> {type: string|number|boolean}.",
    "values": "Observation values key -> result column.",
}


def convert(node, key=None):
    if node is None:
        if key in ANY:
            return {}
        if key in STRING_LISTS:
            return {"type": "array", "items": {"type": "string"}}
        if key in BOOLEANS:
            return {"type": "boolean"}
        if key in INTEGERS:
            return {"type": "integer", "minimum": 1}
        return {"type": "string"}
    if node is structure.EXTERNAL_REF:
        return {"$ref": "#/$defs/externalRef"}
    if node.get("type") == "array":
        return {"type": "array", "items": convert(node["items"])}
    if node.get("open"):
        return {"type": "object", "description": DESCRIPTIONS.get(key, "Open container: keys are not checked.")}
    props = {k: convert(v, k) for k, v in node["fields"].items()}
    if node["extensions"]:
        props["extensions"] = {"$ref": "#/$defs/extensions"}
    return {"type": "object", "properties": props, "additionalProperties": False}


def file_name(kind: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", kind).lower() + ".schema.json"


def main() -> None:
    out_dir = ROOT / "schemas" / "experimental"
    for kind, table in experimental.TABLES.items():
        schema = convert(table)
        schema["properties"]["apiVersion"] = {"const": "openworld/v1alpha1"}
        schema["properties"]["kind"] = {"const": kind}
        schema["required"] = ["spec"]  # apiVersion and kind are inherited from owp.yaml and the asset entry (spec section 5)
        doc = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:owp:schema:experimental:{kind}:v1alpha1",
            "title": f"{kind} (experimental)",
            "description": "Experimental asset kind (spec Appendix C). Violations are warnings, not errors.",
            **schema,
            "$defs": {"extensions": MANIFEST["$defs"]["extensions"], "externalRef": MANIFEST["$defs"]["externalRef"]},
        }
        (out_dir / file_name(kind)).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(file_name(kind))
    for kind, (table_name, spec_required) in STANDARD.items():
        schema = convert(getattr(structure, table_name))
        schema["properties"]["apiVersion"] = {"const": "openworld/v1alpha1"}
        schema["properties"]["kind"] = {"const": kind}
        schema["required"] = ["spec"]
        if spec_required:
            schema["properties"]["spec"]["required"] = spec_required
        doc = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:owp:schema:{file_name(kind).removesuffix('.schema.json')}:v1alpha1",
            "title": kind,
            "description": f"{kind} (spec sections 8 and 15). Fields listed in spec Appendix C.4 remain experimental: accepted, with warnings only from their checks.",
            **schema,
            "$defs": {"extensions": MANIFEST["$defs"]["extensions"]},
        }
        (ROOT / "schemas" / file_name(kind)).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(file_name(kind))


if __name__ == "__main__":
    main()
