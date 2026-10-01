import tempfile
import unittest
from pathlib import Path

import yaml

from ontle.core import deterministic_pack, inspect_package, validate_package, verify_archive
from ontle.scaffold import add_extension, init_project, add_asset


class OntleTests(unittest.TestCase):
    def test_add_extension_declares_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            name = add_extension(p, "acme/quality-extension@1.2.0", must_understand=True)
            self.assertEqual(name, "quality")
            manifest = yaml.safe_load((p / "owp.yaml").read_text(encoding="utf-8"))
            manifest["spec"]["extensions"] = {"quality": {"plantCode": "P-07"}}
            (p / "owp.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(inspect_package(p)["extensions"],
                             [{"name": "quality", "ref": "acme/quality-extension@1.2.0", "mustUnderstand": True}])
            with self.assertRaises(Exception):
                add_extension(p, "acme/other-extension@1.0.0", "quality")

    def test_templates_single_source(self):
        from ontle.scaffold import TEMPLATES, _template_dir
        for name in TEMPLATES:
            self.assertTrue(_template_dir(name).joinpath("owp.yaml").is_file(), name)
        self.assertFalse((Path(__file__).resolve().parents[1] / "templates").exists(),
                         "starter templates belong in src/ontle/templates/ only")

    def test_init_minimal_validates(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertTrue((p / "views" / "default.yaml").exists())
            self.assertTrue((p / "state" / "default-compiler.yaml").exists())

    def test_init_enterprise_validates(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "enterprise", Path(td) / "demo")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)


    def test_init_ontology_validates(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-ontology", "test", "ontology", Path(td) / "demo-ontology")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertTrue((p / "ONTOLOGY.md").exists())

    def test_init_generic_worldmodel_validates(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertTrue((p / "models" / "adapter.yaml").exists())

    def test_init_multimodal_worldmodel_has_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-vla", "test", "worldmodel-multimodal", Path(td) / "demo-vla")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertTrue((p / "models" / "adapter.yaml").exists())

    def test_add_interface_assets_updates_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            for kind in ["source", "observation", "action", "commit", "effect"]:
                add_asset(p, kind, kind)
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            for name in ["source", "observation", "action", "commit", "effect"]:
                self.assertTrue((p / "interfaces" / f"{name}.yaml").exists())

    def test_add_view_and_compiler_assets_updates_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            add_asset(p, "view", "operator-view")
            add_asset(p, "compiler", "operator-state")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertTrue((p / "views" / "operator-view.yaml").exists())
            self.assertTrue((p / "state" / "operator-state.yaml").exists())

    def test_deterministic_pack_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            a = deterministic_pack(p, Path(td) / "a.owp.zip")
            b = deterministic_pack(p, Path(td) / "b.owp.zip")
            self.assertEqual(a.read_bytes(), b.read_bytes())
            ok, errors = verify_archive(a)
            self.assertTrue(ok, errors)

    def test_missing_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            result = validate_package(Path(td))
            self.assertFalse(result.valid)
            self.assertTrue(any("missing owp.yaml" in e for e in result.errors))

    def test_legacy_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            (p / "package.yaml").write_text("legacy: true\n", encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("legacy manifest" in e for e in result.errors))

    def test_bad_semver_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            manifest = p / "owp.yaml"
            text = manifest.read_text(encoding="utf-8").replace("version: 0.1.0", "version: latest")
            manifest.write_text(text, encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("SemVer" in e for e in result.errors))

    def test_missing_asset_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            (p / "examples" / "basic.yaml").unlink()
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("does not exist" in e for e in result.errors))

    def test_asset_kind_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            target = add_asset(p, "source", "erp")
            data = yaml.safe_load(target.read_text(encoding="utf-8"))
            data["kind"] = "ActionBindingProfile"
            target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("asset kind mismatch" in e for e in result.errors))

    def test_multimodal_without_adapter_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-vla", "test", "worldmodel-multimodal", Path(td) / "demo-vla")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["assets"] = [a for a in data["spec"]["assets"] if a["kind"] != "RepresentationAdapterProfile"]
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("RepresentationAdapterProfile" in e for e in result.errors))

    def test_generic_worldmodel_without_adapter_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["assets"] = [a for a in data["spec"]["assets"] if a["kind"] != "RepresentationAdapterProfile"]
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("RepresentationAdapterProfile" in e for e in result.errors))

    def test_world_without_view_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["assets"] = [a for a in data["spec"]["assets"] if a["kind"] != "WorldViewProfile"]
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("WorldViewProfile" in e for e in result.errors))

    def test_descriptive_world_needs_no_view_or_compiler(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["conformance"]["profile"] = "descriptive"
            data["spec"]["assets"] = [a for a in data["spec"]["assets"] if a["kind"] not in {"WorldViewProfile", "StateCompilerProfile"}]
            for key in ("defaultView", "defaultStateCompiler"):
                data["spec"]["world"].pop(key)
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)

    def test_model_ready_requires_ews_schema(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["conformance"]["profile"] = "model-ready"
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("outputSchema" in e for e in result.errors))
            compiler = p / "state" / "default-compiler.yaml"
            cdata = yaml.safe_load(compiler.read_text(encoding="utf-8"))
            cdata["spec"]["outputSchema"] = {"fields": ["entity.state"]}
            compiler.write_text(yaml.safe_dump(cdata, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)

    def test_add_eval_and_verifier_are_versioned(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            for kind in ["eval", "verifier"]:
                target = add_asset(p, kind, f"{kind}-v")
                self.assertEqual(yaml.safe_load(target.read_text(encoding="utf-8"))["metadata"]["version"], "0.1.0")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(result.warnings, [])

    def test_worldmodel_without_compatible_view_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["worldModel"]["semanticGrounding"].pop("compatibleWorldViews", None)
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("compatibleWorldViews" in e for e in result.errors))

    def test_worldmodel_without_compatible_compiler_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["worldModel"]["semanticGrounding"].pop("compatibleStateCompilers", None)
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("compatibleStateCompilers" in e for e in result.errors))

    def test_world_default_compiler_must_bind_default_view(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            compiler = p / "state" / "default-compiler.yaml"
            data = yaml.safe_load(compiler.read_text(encoding="utf-8"))
            data["spec"]["worldViewRef"] = "views/other.yaml"
            compiler.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("worldViewRef" in e for e in result.errors))

    def test_worldmodel_requires_ews_input_and_adapter_ref(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["worldModel"]["inputs"]["contract"] = "raw_tensor"
            data["spec"]["worldModel"]["representation"].pop("adapterRef", None)
            manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("EffectiveWorldState" in e for e in result.errors))
            self.assertTrue(any("adapterRef" in e for e in result.errors))

    def test_pack_excludes_tool_state(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            archive = deterministic_pack(p, Path(td) / "demo.owp.zip")
            with zipfile.ZipFile(archive, "r") as zf:
                self.assertFalse(any(name.startswith(".ontle/") for name in zf.namelist()))


if __name__ == "__main__":
    unittest.main()
