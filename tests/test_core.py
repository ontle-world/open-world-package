import tempfile
import unittest
from pathlib import Path

import yaml

from ontle.core import deterministic_pack, inspect_package, validate_package, verify_archive
from ontle.scaffold import add_extension, init_project, new_asset


class OntleTests(unittest.TestCase):
    def test_generated_files_point_editors_at_schemas(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            view = new_asset(p, "WorldViewProfile", "views/manager.yaml")
            add_extension(p, "acme/quality-extension@1.2.0")
            self.assertTrue((p / "owp.yaml").read_text().startswith("# yaml-language-server: $schema=") )
            self.assertIn("world-view-profile.schema.json", view.read_text().splitlines()[0])
            self.assertNotIn("null", view.read_text())

    def test_validate_folds_consequences_of_a_misspelt_field(self):
        from ontle.cli import fold_errors
        result = validate_package(Path(__file__).resolve().parent.parent / "conformance" / "cases" / "manifest-unknown-field")
        lines = fold_errors(result.errors)
        self.assertEqual(len(lines), len(result.errors))
        self.assertTrue(lines[0].startswith("ERROR: schema.unknown-field:"))

    def test_assets_are_found_by_apiversion_and_kind(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            before = (p / "owp.yaml").read_text()
            (p / "scenarios").mkdir()
            (p / "scenarios" / "s.yaml").write_text("apiVersion: openworld/v1alpha1\nkind: ScenarioProfile\nmetadata: {name: s}\nspec: {objective: x}\n")
            (p / "notes.yaml").write_text("just: data\n")
            self.assertTrue(validate_package(p).valid)
            self.assertEqual(inspect_package(p)["asset_count"], 5)  # view, compiler, two examples, scenario
            self.assertEqual((p / "owp.yaml").read_text(), before)

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

    def test_init_titles_the_package_from_its_name(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("cafe-world", "test", "minimal", Path(td) / "w")
            self.assertEqual(yaml.safe_load((p / "owp.yaml").read_text())["metadata"]["title"], "Cafe World")
            self.assertEqual((p / "WORLD.md").read_text().splitlines()[0], "# Cafe World")

    def test_init_world_model_grounded_in_a_world(self):
        from ontle.core import OWPError
        from ontle.resolve import validate_resolved
        with tempfile.TemporaryDirectory() as td:
            world = init_project("cafe-world", "lab", "minimal", Path(td) / "src" / "cafe-world")
            for template in ("worldmodel", "worldmodel-multimodal"):
                with self.subTest(template=template):
                    model = init_project("cafe-model", "lab", template, Path(td) / template, world=str(world))
                    spec = yaml.safe_load((model / "owp.yaml").read_text())["spec"]
                    self.assertEqual(spec["dependencies"], ["lab/cafe-world@0.1.0"])
                    self.assertEqual(spec["worldModel"]["semanticGrounding"]["compatibleWorldViews"],
                                     ["lab/cafe-world@0.1.0#views/default.yaml"])
                    result, _ = validate_resolved(model, [str(Path(td) / "src")])
                    self.assertTrue(result.valid, result.errors)
            with self.assertRaises(OWPError):
                init_project("w", "lab", "minimal", Path(td) / "w", world="lab/cafe-world@0.1.0")
            with self.assertRaises(OWPError):
                init_project("m", "lab", "worldmodel", Path(td) / "m", world="not-a-world")

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

    def test_new_writes_skeletons_that_validate(self):
        from ontle.core import OWPError
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            before = (p / "owp.yaml").read_text()
            for kind, rel in [("SourceSystemSchemaProfile", "interfaces/source.yaml"), ("ActionBindingProfile", "interfaces/action.yaml"),
                              ("WorldViewProfile", "views/operator.yaml"), ("StateCompilerProfile", "state/operator.yaml")]:
                target = new_asset(p, kind, rel)
                doc = yaml.safe_load(target.read_text())
                self.assertEqual((doc["apiVersion"], doc["kind"], doc["metadata"]["name"]), ("openworld/v1alpha1", kind, target.stem))
            new_asset(p, "WorldViewProfile", "views/regional.yaml", specializes="views/default.yaml")
            new_asset(p, "WorldViewProfile", "views/combined.yaml", composes=["views/default.yaml", "views/regional.yaml"])
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)
            self.assertFalse([w for w in result.warnings if w.startswith("experimental.")], result.warnings)
            self.assertEqual((p / "owp.yaml").read_text(), before)
            for kind, rel in [("NotAKind", "x.yaml"), ("WorldViewProfile", "views/operator.yaml"), ("WorldViewProfile", "../x.yaml"),
                              ("PackageExample", "examples/x.yaml")]:
                with self.assertRaises(OWPError):
                    new_asset(p, kind, rel)

    def test_composed_view_resolves_to_the_union(self):
        from ontle import experimental
        from ontle.core import local_assets
        case = Path(__file__).resolve().parent.parent / "conformance" / "cases" / "view-composes"
        kinds, docs = local_assets(case, {})
        resolved = experimental.resolve_view("views/plant.yaml", docs, kinds)
        self.assertEqual(resolved["projection"], {"timeScope": "last_quarter", "include": ["lot", "inspection", "equipment", "work_order"]})
        self.assertEqual(resolved["purpose"], {"task": "plant_review"})
        self.assertEqual(resolved["conditioning"], {"authorityScope": "read_only"})
        self.assertNotIn("composes", resolved)

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
            (p / "examples" / "observations.yaml").unlink()
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("does not exist" in e for e in result.errors))

    def test_multimodal_without_adapter_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-vla", "test", "worldmodel-multimodal", Path(td) / "demo-vla")
            (p / "models" / "adapter.yaml").unlink()
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("RepresentationAdapterProfile" in e for e in result.errors))

    def test_generic_worldmodel_without_adapter_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            (p / "models" / "adapter.yaml").unlink()
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("RepresentationAdapterProfile" in e for e in result.errors))

    def test_world_without_view_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            (p / "views" / "default.yaml").unlink()
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("WorldViewProfile" in e for e in result.errors))

    def test_descriptive_world_needs_no_view_or_compiler(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            manifest = p / "owp.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["spec"]["conformance"]["profile"] = "descriptive"
            (p / "views" / "default.yaml").unlink()
            (p / "state" / "default-compiler.yaml").unlink()
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
            self.assertTrue(validate_package(p).valid)  # the starter's compiler declares its fields
            compiler = p / "state" / "default-compiler.yaml"
            cdata = yaml.safe_load(compiler.read_text(encoding="utf-8"))
            del cdata["spec"]["outputSchema"], cdata["spec"]["bindings"]
            compiler.write_text(yaml.safe_dump(cdata, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertFalse(result.valid)
            self.assertTrue(any("outputSchema" in e for e in result.errors))
            cdata["spec"]["outputSchema"] = {"fields": ["item.state"]}
            compiler.write_text(yaml.safe_dump(cdata, sort_keys=False), encoding="utf-8")
            result = validate_package(p)
            self.assertTrue(result.valid, result.errors)

    def test_add_eval_and_verifier_are_versioned(self):
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo-model", "test", "worldmodel", Path(td) / "demo-model")
            for kind in ["EvaluationProfile", "VerifierProfile"]:
                target = new_asset(p, kind, f"eval/{kind.lower()}.yaml")
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

    def test_owpignore_patterns(self):
        from ontle.ignore import is_ignored, parse_ignore
        rules = parse_ignore("# comment\n\ndrafts/\n/notes.yaml\n*.wip.yaml\n!keep.wip.yaml\ncache/**\nscratch-[0-9].yaml\nlogs/**/*.yaml\n")
        cases = {
            "drafts/v.yaml": True, "views/drafts/v.yaml": True, "drafts": False,  # a directory pattern skips a file named drafts
            "notes.yaml": True, "views/notes.yaml": False,
            "views/a.wip.yaml": True, "views/keep.wip.yaml": False,
            "cache/a/b.yaml": True, "scratch-1.yaml": True, "scratch-x.yaml": False,
            "logs/a.yaml": True, "logs/x/y/a.yaml": True, "logs/a.json": False, "views/v.yaml": False,
        }
        for rel, expected in cases.items():
            self.assertEqual(is_ignored(rules, rel), expected, rel)
        self.assertTrue(is_ignored(parse_ignore("drafts/\n!drafts/keep.yaml\n"), "drafts/keep.yaml"))  # no re-include under an excluded directory

    def test_pack_leaves_out_owpignore_paths(self):
        import zipfile
        from ontle.core import OWPError
        with tempfile.TemporaryDirectory() as td:
            p = init_project("demo", "test", "minimal", Path(td) / "demo")
            (p / "drafts").mkdir()
            (p / "drafts" / "v.yaml").write_text("apiVersion: openworld/v1alpha1\nkind: NotAKind\n")
            (p / ".owpignore").write_text("drafts/\nowp.yaml\n")  # owp.yaml cannot be excluded
            self.assertTrue(validate_package(p).valid)
            archive = deterministic_pack(p, Path(td) / "demo.owp.zip")
            with zipfile.ZipFile(archive, "r") as zf:
                names = zf.namelist()
            self.assertIn("owp.yaml", names)
            self.assertNotIn(".owpignore", names)  # dot paths are not package files
            self.assertFalse(any(n.startswith("drafts/") for n in names))
            (p / ".owpignore").write_text("drafts/\nWORLD.md\n")  # the manifest's world description is then missing
            with self.assertRaisesRegex(OWPError, "without the files .owpignore excludes"):
                deterministic_pack(p, Path(td) / "broken.owp.zip")


class JavaScriptValueRules(unittest.TestCase):
    """Rules read values as the TypeScript implementation does (ontle.values)."""

    def test_whitespace_is_the_javascript_set(self):
        from ontle.values import nonempty_str, trim
        self.assertFalse(nonempty_str("\ufeff\u3000 "))
        self.assertTrue(nonempty_str("\x1c"))  # not whitespace in JavaScript, although str.isspace() says it is
        self.assertEqual(trim("\u00a0a b\u2028"), "a b")

    def test_identity_text_is_javascript_string(self):
        from ontle.values import js_string
        self.assertEqual([js_string(v) for v in (1152921504606846976, 1e-7, 3.0, None, True, [1, None])],
                         ["1152921504606847000", "1e-7", "3", "null", "true", "1,"])

    def test_semver_digits_are_ascii(self):
        from ontle.core import PACKAGE_REF_RE, SEMVER_RE
        for version in ("0.1.1\u0663", "\uff11.0.0"):
            self.assertIsNone(SEMVER_RE.match(version))
            self.assertIsNone(PACKAGE_REF_RE.match(f"a/b@{version}"))

    def test_timestamps_from_year_zero(self):
        from ontle.ews import _shift, _valid_timestamp
        self.assertTrue(_valid_timestamp("0000-02-29T00:00:10Z"))
        self.assertFalse(_valid_timestamp("0100-02-29T00:00:00Z"))
        self.assertEqual(_shift("0000-03-01T00:00:00Z", 86400), "0000-02-29T00:00:00Z")
        self.assertFalse(_valid_timestamp("2026-01-01T00:00:0\u0661Z"))


if __name__ == "__main__":
    unittest.main()
