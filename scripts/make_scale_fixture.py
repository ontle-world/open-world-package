#!/usr/bin/env python3
"""A synthetic plant at test scale: an ontology (T-box), a World with a knowledge graph (A-box) and observations, and a
World Model grounded in it. Deterministic for a seed; no real data.

    python scripts/make_scale_fixture.py <dir> [--seed N] [--equipment N] [--lots N]

writes <dir>/plant-ontology, <dir>/plant-world, and <dir>/plant-model, and returns (from Python) the facts the tests
compare with: term and individual counts, and the EWS values computed directly from the generated observations,
independently of the State Compiler.

Default size: 52 classes and 6 enum types with 66 properties (T-box); about 1,000 individuals and 3,000 triples
(A-box); about 2,000 observations.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

NS = "https://w3id.org/scale-fixture/plant#"
ABOX = "https://w3id.org/scale-fixture/plant/id/"
AS_OF = "2026-09-10T00:00:00Z"
STATES = ["running", "idle", "down", "maintenance"]
SEVERITIES = ["low", "medium", "high", "critical"]
LOT_STATUSES = ["planned", "in_process", "on_hold", "released", "scrapped"]
RESULTS = ["pass", "fail"]

# class -> parent; the hierarchy the ontology declares
CLASSES = {
    "Thing": None, "Site": "Thing", "Area": "Thing", "Line": "Thing", "Cell": "Thing",
    "Asset": "Thing", "Equipment": "Asset", "Press": "Equipment", "Robot": "Equipment", "Conveyor": "Equipment",
    "Oven": "Equipment", "Furnace": "Equipment", "CncMachine": "Equipment", "Welder": "Equipment", "PaintBooth": "Equipment",
    "InspectionStation": "Equipment", "Packager": "Equipment",
    "Component": "Asset", "Motor": "Component", "Sensor": "Component", "Die": "Component", "Spindle": "Component",
    "Gripper": "Component", "Bearing": "Component", "Valve": "Component",
    "Material": "Thing", "RawMaterial": "Material", "WorkInProgress": "Material", "FinishedGood": "Material",
    "Lot": "Thing", "Order": "Thing", "WorkOrder": "Order", "MaintenanceOrder": "Order", "CustomerOrder": "Order",
    "Event": "Thing", "Alarm": "Event", "Downtime": "Event", "Changeover": "Event", "QualityEvent": "Event",
    "Inspection": "Thing", "Defect": "Thing", "Claim": "Thing", "Capa": "Thing",
    "Person": "Thing", "Operator": "Person", "Technician": "Person", "Shift": "Thing",
    "Organization": "Thing", "Supplier": "Organization", "Customer": "Organization", "Product": "Thing", "Recipe": "Thing",
}
ENUMS = {
    "EquipmentState": STATES, "Severity": SEVERITIES, "LotStatus": LOT_STATUSES, "InspectionResult": RESULTS,
    "OrderStatus": ["open", "released", "closed"], "ShiftName": ["day", "swing", "night"],
}
# property -> (domain class, range); a range that is a class or an enum type of this ontology, an xsd type, or None
PROPERTIES = {
    "name": ("Thing", "xsd:string"), "code": ("Thing", "xsd:string"),
    "inArea": ("Line", "Area"), "inSite": ("Area", "Site"), "inLine": ("Cell", "Line"), "locatedIn": ("Equipment", "Line"),
    "hasComponent": ("Equipment", "Component"), "operatingState": ("Equipment", "EquipmentState"),
    "alarmCount24h": ("Equipment", "xsd:integer"), "criticalAlarmCount24h": ("Equipment", "xsd:integer"),
    "maxTemperature": ("Equipment", "xsd:decimal"), "meanVibration": ("Equipment", "xsd:decimal"), "riskLevel": ("Equipment", "xsd:string"),
    "ratedPower": ("Motor", "xsd:decimal"), "measures": ("Sensor", "xsd:string"), "tonnage": ("Press", "xsd:integer"),
    "payload": ("Robot", "xsd:decimal"), "maxTemp": ("Oven", "xsd:decimal"), "spindleSpeed": ("Spindle", "xsd:integer"),
    "producedOn": ("Lot", "Equipment"), "forOrder": ("Lot", "WorkOrder"), "consumes": ("Lot", "RawMaterial"),
    "ofProduct": ("Lot", "Product"), "lotStatus": ("Lot", "LotStatus"), "lotSize": ("Lot", "xsd:integer"),
    "failedInspectionCount": ("Lot", "xsd:integer"), "inspectionCount": ("Lot", "xsd:integer"), "qualityDecision": ("Lot", "xsd:string"),
    "suppliedBy": ("RawMaterial", "Supplier"), "grade": ("RawMaterial", "xsd:string"),
    "orderStatus": ("Order", "OrderStatus"), "dueDate": ("Order", "xsd:date"), "forCustomer": ("CustomerOrder", "Customer"),
    "targets": ("MaintenanceOrder", "Equipment"), "followsRecipe": ("WorkOrder", "Recipe"), "makes": ("Recipe", "Product"),
    "raisedOn": ("Event", "Equipment"), "severity": ("Event", "Severity"), "startedAt": ("Event", "xsd:dateTime"),
    "durationMinutes": ("Downtime", "xsd:integer"), "alarmCode": ("Alarm", "xsd:string"),
    "inspects": ("Inspection", "Lot"), "result": ("Inspection", "InspectionResult"), "inspectedAt": ("Inspection", "InspectionStation"),
    "finds": ("Inspection", "Defect"), "defectType": ("Defect", "xsd:string"),
    "affectsLot": ("Claim", "Lot"), "raisedBy": ("Claim", "Customer"), "addresses": ("Capa", "Claim"), "ownedBy": ("Capa", "Person"),
    "worksShift": ("Operator", "Shift"), "shiftName": ("Shift", "ShiftName"), "certifiedFor": ("Technician", "Equipment"),
    "operates": ("Operator", "Equipment"), "contact": ("Organization", "xsd:string"), "country": ("Organization", "xsd:string"),
    "sku": ("Product", "xsd:string"), "version": ("Recipe", "xsd:string"), "changesOver": ("Changeover", "Recipe"),
    "detectedBy": ("QualityEvent", "Sensor"), "mountedOn": ("Component", "Equipment"), "serial": ("Asset", "xsd:string"),
    "installedOn": ("Asset", "xsd:date"), "manufacturer": ("Asset", "Supplier"),
}
EQUIPMENT_KINDS = ["Press", "Robot", "Conveyor", "Oven", "Furnace", "CncMachine", "Welder", "PaintBooth", "InspectionStation", "Packager"]
COMPONENT_KINDS = ["Motor", "Sensor", "Die", "Spindle", "Gripper", "Bearing", "Valve"]


def ts(base: datetime, minutes: int) -> str:
    return (base - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def card(title: str, scope: str) -> str:
    return (f"# {title}\n\n## Scope\n\n{scope}\n\n## Sources\n\nGenerated by scripts/make_scale_fixture.py; no real data.\n\n"
            "## Use it for\n\n- Testing the toolchain at scale.\n\n## Limitations\n\nSynthetic.\n\n## Versions\n\n- 0.1.0: generated.\n")


def dump(data: Any) -> str:
    """YAML is a superset of JSON: the documents are written as JSON, which every YAML 1.2 reader reads."""
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def make(out: Path, seed: int = 7, equipment: int = 120, lots: int = 200) -> dict[str, Any]:
    rng = random.Random(seed)
    as_of = datetime(2026, 9, 10, tzinfo=timezone.utc)
    out.mkdir(parents=True, exist_ok=True)

    # ---- T-box: plant-ontology -----------------------------------------------------------------------------
    types = []
    for cls, parent in CLASSES.items():
        props = [{"id": f"p:{p}", **({"range": f"p:{r}" if not r.startswith("xsd:") else r} if r else {})}
                 for p, (d, r) in PROPERTIES.items() if d == cls]
        types.append({"id": f"p:{cls}", "label": {"en": cls}, **({"subClassOf": f"p:{parent}"} if parent else {}),
                      **({"properties": props} if props else {})})
    for enum, values in ENUMS.items():
        types.append({"id": f"p:{enum}", "enum": values})
    onto = out / "plant-ontology"
    write(onto / "owp.yaml", dump({
        "apiVersion": "openworld/v1alpha1", "kind": "OntologyPackage",
        "metadata": {"namespace": "scale", "name": "plant-ontology", "version": "0.1.0", "title": "Synthetic Plant Ontology",
                     "description": "Synthetic T-box for scale tests.", "license": "Apache-2.0"},
        "spec": {"ontology": {"description": "ONTOLOGY.md", "iri": NS, "prefixes": {"p": NS, "xsd": "http://www.w3.org/2001/XMLSchema#"},
                              "entrypoints": [{"path": "semantics/core.yaml", "format": "owp-yaml", "role": "schema"}]},
                 "conformance": {"profile": "schema"}}}))
    write(onto / "ONTOLOGY.md", card("Synthetic Plant Ontology", "A synthetic plant vocabulary: sites, lines, equipment, lots, events."))
    write(onto / "semantics" / "core.yaml", dump({"apiVersion": "openworld/v1alpha1", "kind": "SemanticProfile",
                                                   "metadata": {"name": "plant-core"}, "spec": {"types": types}}))

    # ---- A-box: the plant as a knowledge graph -------------------------------------------------------------
    triples: list[str] = []
    individuals: dict[str, str] = {}

    def node(kind: str, key: str, **props: Any) -> str:
        iri = f"{kind.lower()}-{key}"
        individuals[iri] = kind
        triples.append(f"<{ABOX}{iri}> a p:{kind} .")
        for p, v in props.items():
            values = v if isinstance(v, list) else [v]
            for x in values:
                obj = f"<{ABOX}{x}>" if isinstance(x, str) and x.startswith("@") is False and x in individuals else json.dumps(x)
                triples.append(f"<{ABOX}{iri}> p:{p} {obj} .")
        return iri

    sites = [node("Site", f"S{i}", name=f"Site {i}") for i in range(1, 4)]
    areas = [node("Area", f"A{i}", inSite=sites[i % 3]) for i in range(1, 7)]
    lines = [node("Line", f"L{i:02d}", inArea=areas[i % 6]) for i in range(1, 13)]
    suppliers = [node("Supplier", f"V{i:02d}", name=f"Supplier {i}", country=rng.choice(["KR", "DE", "JP", "US"])) for i in range(1, 31)]
    customers = [node("Customer", f"C{i:02d}", name=f"Customer {i}") for i in range(1, 21)]
    products = [node("Product", f"P{i:02d}", sku=f"SKU-{i:03d}") for i in range(1, 16)]
    recipes = [node("Recipe", f"R{i:02d}", makes=products[i % 15], version="1.0") for i in range(1, 21)]
    shifts = [node("Shift", n, shiftName=n) for n in ENUMS["ShiftName"]]
    raws = [node("RawMaterial", f"M{i:03d}", suppliedBy=rng.choice(suppliers), grade=rng.choice("ABC")) for i in range(1, 61)]
    eq_ids = []
    for i in range(1, equipment + 1):
        kind = EQUIPMENT_KINDS[i % len(EQUIPMENT_KINDS)]
        eid = f"EQ-{i:03d}"
        comps = [node(COMPONENT_KINDS[(i + j) % len(COMPONENT_KINDS)], f"{eid}-{j}", serial=f"SN{i:03d}{j}") for j in range(2)]
        node(kind, eid, locatedIn=lines[i % 12], hasComponent=comps, manufacturer=rng.choice(suppliers), serial=f"SN{i:03d}")
        individuals[f"equipment-{eid}"] = kind
        triples[-0:]  # the equipment's IRI is <kind>-<id>; the subject IRI the World binds is equipment-<id>, typed below
        triples.append(f"<{ABOX}equipment-{eid}> a p:{kind} ; p:locatedIn <{ABOX}{lines[i % 12]}> .")
        eq_ids.append(eid)
    for i in range(1, 51):
        node("Operator", f"O{i:02d}", worksShift=rng.choice(shifts), operates=f"equipment-{rng.choice(eq_ids)}")
    orders = [node("WorkOrder", f"WO{i:03d}", followsRecipe=rng.choice(recipes), orderStatus=rng.choice(ENUMS["OrderStatus"]))
              for i in range(1, 101)]
    lot_ids = []
    for i in range(1, lots + 1):
        lid = f"LOT-{i:04d}"
        lot_ids.append(lid)
        node("Lot", lid, producedOn=f"equipment-{rng.choice(eq_ids)}", forOrder=rng.choice(orders), consumes=rng.choice(raws),
             ofProduct=rng.choice(products), lotSize=rng.randint(50, 500))
    for i in range(1, 41):
        claim = node("Claim", f"CL{i:03d}", affectsLot=f"lot-{rng.choice(lot_ids)}", raisedBy=rng.choice(customers))
        if i % 2:
            node("Capa", f"CA{i:03d}", addresses=claim)
    world = out / "plant-world"
    write(world / "kg" / "plant.ttl", f"@prefix p: <{NS}> .\n# Synthetic plant A-box; no real plant.\n" + "\n".join(triples) + "\n")

    # ---- observations and the expected EWS, computed here -------------------------------------------------
    obs: list[dict[str, Any]] = []
    expected: dict[str, dict[str, Any]] = {f: {} for f in (
        "equipment.state", "equipment.alarms_24h", "equipment.critical_alarms_24h", "equipment.temp_max_6h",
        "equipment.vibration_mean_6h", "equipment.risk", "lot.status", "lot.inspections", "lot.failed_inspections", "lot.quality_risk")}

    def add(otype: str, subject: str, minutes: int, values: dict[str, Any], units: dict[str, str] | None = None) -> None:
        o = {"id": f"{otype.lower()}-{len(obs) + 1:05d}", "type": otype, "subject": subject, "observedAt": ts(as_of, minutes), "values": values}
        if units:
            o["units"] = units
        obs.append(o)

    for eid in eq_ids:
        times = sorted(rng.sample(range(5, 2800), 2), reverse=True)  # distinct times: the newest state is unambiguous
        states = [rng.choice(STATES) for _ in times]
        for minutes, state in zip(times, states):
            add("MES.equipment_state", eid, minutes, {"state": state})
        expected["equipment.state"][eid] = states[-1]
        alarms = crit = 0
        for _ in range(rng.randint(0, 6)):
            minutes = rng.randint(1, 2880)  # two days; the field counts the last 24 hours
            sev = rng.choice(SEVERITIES)
            add("OT.alarm", eid, minutes, {"code": f"A{rng.randint(100, 199)}", "severity": sev})
            if minutes < 1440:
                alarms += 1
                crit += sev in ("high", "critical")
        expected["equipment.alarms_24h"][eid] = alarms
        expected["equipment.critical_alarms_24h"][eid] = crit
        expected["equipment.risk"][eid] = "high" if crit >= 3 else "elevated" if crit >= 1 else "normal"
        temps, vibs = [], []
        for _ in range(rng.randint(1, 4)):
            minutes = rng.randint(1, 600)
            t, v = rng.randint(20, 120), rng.randint(1, 40)
            add("OT.temperature", eid, minutes, {"celsius": t}, {"celsius": "Cel"})
            add("OT.vibration", eid, minutes, {"mm_s": v}, {"mm_s": "mm/s"})
            if minutes < 360:
                temps.append((minutes, t))
                vibs.append((minutes, v))
        if temps:
            expected["equipment.temp_max_6h"][eid] = max(t for _, t in temps)
            expected["equipment.vibration_mean_6h"][eid] = sum(v for _, v in vibs) / len(vibs)
    for lid in lot_ids:
        times = sorted(rng.sample(range(5, 4000), 2), reverse=True)
        statuses = [rng.choice(LOT_STATUSES) for _ in times]
        for minutes, status in zip(times, statuses):
            add("MES.lot", lid, minutes, {"status": status})
        expected["lot.status"][lid] = statuses[-1]
        results = [rng.choice(RESULTS) for _ in range(rng.randint(0, 3))]
        for r in results:
            add("QMS.inspection", lid, rng.randint(1, 4000), {"result": r, "station": f"equipment-{rng.choice(eq_ids)}"})
        failed = results.count("fail")
        expected["lot.inspections"][lid] = len(results)
        expected["lot.failed_inspections"][lid] = failed
        expected["lot.quality_risk"][lid] = "hold" if failed >= 2 else "watch" if failed == 1 else "release"
    # A per-subject aggregate has a value only for subjects with at least one candidate (spec 12.3, 12.4), and `where`
    # limits the candidates: drop the zeros the compiler leaves out. A classification is missing where its input is.
    def has(otype: str, subject: str, since: str | None = None, **match: Any) -> bool:
        return any(o["type"] == otype and o["subject"] == subject and (since is None or o["observedAt"] > since)
                   and all(o["values"].get(k) in v for k, v in match.items()) for o in obs)
    day = ts(as_of, 1440)
    keep = {
        "equipment.alarms_24h": lambda k: has("OT.alarm", k, day),
        "equipment.critical_alarms_24h": lambda k: has("OT.alarm", k, day, severity=("high", "critical")),
        "equipment.risk": lambda k: has("OT.alarm", k, day, severity=("high", "critical")),
        "lot.inspections": lambda k: has("QMS.inspection", k),
        "lot.failed_inspections": lambda k: has("QMS.inspection", k, result=("fail",)),
        "lot.quality_risk": lambda k: has("QMS.inspection", k, result=("fail",)),
    }
    for f, present in keep.items():
        expected[f] = {k: v for k, v in expected[f].items() if present(k)}

    # ---- the World -----------------------------------------------------------------------------------------
    names = ["equipment", "lot", "line", "alarm", "inspection", "claim", "capa", "work_order", "raw_material", "operator"]
    write(world / "owp.yaml", dump({
        "apiVersion": "openworld/v1alpha1", "kind": "WorldPackage",
        "metadata": {"namespace": "scale", "name": "plant-world", "version": "0.1.0", "title": "Synthetic Plant World",
                     "description": "Synthetic plant at scale for tests: equipment health and lot quality.", "license": "Apache-2.0"},
        "spec": {"dependencies": ["scale/plant-ontology@0.1.0"], "domains": ["manufacturing"],
                 "world": {"description": "WORLD.md", "definition": "A synthetic plant: equipment, lots, inspections, alarms.",
                           "boundary": {"included": names}, "defaultView": "views/equipment-health.yaml",
                           "defaultStateCompiler": "state/equipment-health.yaml", "semanticBinding": "semantics/plant-terms.yaml"},
                 "conformance": {"profile": "model-ready"},
                 "assets": [{"kind": "PackageExample", "path": "examples/observations.yaml"}]}}))
    write(world / "WORLD.md", card("Synthetic Plant World", "Equipment health and lot quality of a synthetic plant."))
    view = lambda name, task, include, extra=None: dump({"apiVersion": "openworld/v1alpha1", "kind": "WorldViewProfile",
                                                         "metadata": {"name": name},
                                                         "spec": {"purpose": {"task": task}, **({"projection": {"include": include}} if include else {}), **(extra or {})}})
    write(world / "views" / "equipment-health.yaml", view("equipment-health", "monitor_equipment", ["equipment", "alarm", "line"]))
    write(world / "views" / "lot-quality.yaml", view("lot-quality", "release_lots", ["lot", "inspection", "claim", "capa"]))
    write(world / "views" / "plant-overview.yaml", view("plant-overview", "review_plant", None,
                                                        {"composes": ["views/equipment-health.yaml", "views/lot-quality.yaml"]}))
    compiler = lambda name, view_path, fields, bindings, units=None: dump({
        "apiVersion": "openworld/v1alpha1", "kind": "StateCompilerProfile", "metadata": {"name": name},
        "spec": {"worldViewRef": view_path, "outputContract": "EffectiveWorldState",
                 "outputSchema": {"fields": fields, "perSubject": fields,
                                  "latent": [f for f in fields if "aggregate" in bindings[f] or "classify" in bindings[f]],
                                  **({"units": units} if units else {})},
                 "bindings": bindings, "traceRequired": True}})
    eq_fields = ["equipment.state", "equipment.alarms_24h", "equipment.critical_alarms_24h", "equipment.temp_max_6h",
                 "equipment.vibration_mean_6h", "equipment.risk"]
    write(world / "state" / "equipment-health.yaml", compiler("equipment-health", "views/equipment-health.yaml", eq_fields, {
        "equipment.state": {"from": "MES.equipment_state", "value": "state", "select": "latest"},
        "equipment.alarms_24h": {"aggregate": {"from": "OT.alarm", "value": "code", "function": "count", "window": "PT24H"}},
        "equipment.critical_alarms_24h": {"aggregate": {"from": "OT.alarm", "value": "code", "function": "count", "window": "PT24H",
                                                        "where": {"severity": {"in": ["high", "critical"]}}}},
        "equipment.temp_max_6h": {"aggregate": {"from": "OT.temperature", "value": "celsius", "function": "max", "window": "PT6H"}},
        "equipment.vibration_mean_6h": {"aggregate": {"from": "OT.vibration", "value": "mm_s", "function": "mean", "window": "PT6H"}},
        "equipment.risk": {"classify": {"input": "equipment.critical_alarms_24h", "criterion": {
            "id": "alarm-escalation", "version": "1.0.0",
            "rules": [{"when": {"gte": 3}, "label": "high"}, {"when": {"gte": 1}, "label": "elevated"}], "otherwise": "normal"}}},
    }, {"equipment.alarms_24h": "{alarm}", "equipment.critical_alarms_24h": "{alarm}", "equipment.temp_max_6h": "Cel",
        "equipment.vibration_mean_6h": "mm/s"}))
    lot_fields = ["lot.status", "lot.inspections", "lot.failed_inspections", "lot.quality_risk"]
    write(world / "state" / "lot-quality.yaml", compiler("lot-quality", "views/lot-quality.yaml", lot_fields, {
        "lot.status": {"from": "MES.lot", "value": "status", "select": "latest"},
        "lot.inspections": {"aggregate": {"from": "QMS.inspection", "value": "result", "function": "count"}},
        "lot.failed_inspections": {"aggregate": {"from": "QMS.inspection", "value": "result", "function": "count",
                                                 "where": {"result": {"eq": "fail"}}}},
        "lot.quality_risk": {"classify": {"input": "lot.failed_inspections", "criterion": {
            "id": "lot-release", "version": "1.0.0",
            "rules": [{"when": {"gte": 2}, "label": "hold"}, {"when": {"gte": 1}, "label": "watch"}], "otherwise": "release"}}},
    }))
    write(world / "semantics" / "plant-terms.yaml", dump({
        "apiVersion": "openworld/v1alpha1", "kind": "SemanticBinding", "metadata": {"name": "plant-terms"},
        "spec": {
            "terms": {"equipment": "p:Equipment", "lot": "p:Lot", "line": "p:Line", "alarm": "p:Alarm", "inspection": "p:Inspection",
                      "claim": "p:Claim", "capa": "p:Capa", "work_order": "p:WorkOrder", "raw_material": "p:RawMaterial",
                      "operator": "p:Operator"},
            "fields": {
                "equipment.state": {"class": "p:Equipment", "path": ["p:operatingState"]},
                "equipment.alarms_24h": {"class": "p:Equipment", "path": ["p:alarmCount24h"]},
                "equipment.critical_alarms_24h": {"class": "p:Equipment", "path": ["p:criticalAlarmCount24h"]},
                "equipment.temp_max_6h": {"class": "p:Equipment", "path": ["p:maxTemperature"]},
                "equipment.vibration_mean_6h": {"class": "p:Equipment", "path": ["p:meanVibration"]},
                "equipment.risk": {"class": "p:Equipment", "path": ["p:riskLevel"]},
                "lot.status": {"class": "p:Lot", "path": ["p:lotStatus"]},
                "lot.inspections": {"class": "p:Lot", "path": ["p:inspectionCount"]},
                "lot.failed_inspections": {"class": "p:Lot", "path": ["p:failedInspectionCount"]},
                "lot.quality_risk": {"class": "p:Lot", "path": ["p:qualityDecision"]}},
            "observationTypes": {"MES.equipment_state": "p:Equipment", "OT.alarm": "p:Equipment", "OT.temperature": "p:Equipment",
                                 "OT.vibration": "p:Equipment", "MES.lot": "p:Lot", "QMS.inspection": "p:Lot"},
            "subjects": {"MES.equipment_state": {"base": f"{ABOX}equipment-"}, "MES.lot": {"base": f"{ABOX}lot-"}}}}))
    write(world / "knowledge" / "plant-kg.yaml", dump({
        "apiVersion": "openworld/v1alpha1", "kind": "KnowledgeAsset", "metadata": {"name": "plant-kg", "version": "0.1.0"},
        "spec": {"roles": ["graph"], "representation": "graph", "format": "turtle",
                 "conformsTo": {"ontology": "scale/plant-ontology@0.1.0"}, "content": {"path": "kg/plant.ttl"}}}))
    write(world / "examples" / "observations.yaml", dump({"apiVersion": "openworld/v1alpha1", "kind": "ObservationSet",
                                                          "spec": {"observations": obs}}))

    # ---- a World Model grounded in the equipment-health View -----------------------------------------------
    model = out / "plant-model"
    write(model / "owp.yaml", dump({
        "apiVersion": "openworld/v1alpha1", "kind": "WorldModelPackage",
        "metadata": {"namespace": "scale", "name": "plant-model", "version": "0.1.0", "title": "Synthetic Equipment Health Model",
                     "description": "Synthetic model contract for scale tests.", "license": "Apache-2.0"},
        "spec": {"dependencies": ["scale/plant-world@0.1.0"],
                 "worldModel": {"description": "WORLDMODEL.md", "roles": ["state_estimation", "outcome_prediction"],
                                "semanticGrounding": {"worldRef": "scale/plant-world@0.1.0",
                                                      "compatibleWorldViews": ["scale/plant-world@0.1.0#views/equipment-health.yaml"],
                                                      "compatibleStateCompilers": ["scale/plant-world@0.1.0#state/equipment-health.yaml"]},
                                "inputs": {"contract": "EffectiveWorldState"},
                                "representation": {"adapterRef": "models/adapter.yaml"}, "outputs": ["failure_risk"]}}}))
    write(model / "WORLDMODEL.md", card("Synthetic Equipment Health Model", "A model contract grounded in the equipment-health View."))
    write(model / "models" / "adapter.yaml", dump({"apiVersion": "openworld/v1alpha1", "kind": "RepresentationAdapterProfile",
                                                   "metadata": {"name": "adapter"},
                                                   "spec": {"source": "EffectiveWorldState", "target": "feature_vector",
                                                            "preserves": ["semantic_identity", "units"]}}))
    write(model / "models" / "model-artifact.yaml", dump({"apiVersion": "openworld/v1alpha1", "kind": "ModelArtifact",
                                                          "metadata": {"name": "model-artifact"},
                                                          "spec": {"implementationStatus": "unbound", "artifactRef": {"status": "unbound"}}}))
    write(model / "eval" / "basic.yaml", dump({"apiVersion": "openworld/v1alpha1", "kind": "EvaluationProfile",
                                               "metadata": {"name": "health-basic", "version": "0.1.0"}, "spec": {"metrics": ["auroc"]}}))

    return {
        "classes": len(CLASSES), "enums": len(ENUMS), "properties": len(PROPERTIES), "individuals": len(individuals),
        "triples": sum(t.count(" .") for t in triples), "observations": len(obs), "equipment": eq_ids, "lots": lot_ids,
        "asOf": AS_OF, "expected": expected,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--equipment", type=int, default=120)
    ap.add_argument("--lots", type=int, default=200)
    args = ap.parse_args()
    facts = make(Path(args.out), args.seed, args.equipment, args.lots)
    print(json.dumps({k: v for k, v in facts.items() if k not in ("expected", "equipment", "lots")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
