import json
import re
import unittest
from pathlib import Path

from ontle import experimental, structure

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def _resolve(schema, root):
    while isinstance(schema, dict) and "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        schema = node
    if isinstance(schema, dict) and "oneOf" in schema:  # dependency: string or mapping
        objects = [_resolve(s, root) for s in schema["oneOf"]]
        objects = [s for s in objects if s.get("type") == "object"]
        if len(objects) == 1:
            return objects[0]
    return schema


class StructureMatchesJsonSchema(unittest.TestCase):
    """The reference field tables (src/ontle/structure.py) and schemas/ define the same fields."""

    def compare(self, node, schema, root, path):
        schema = _resolve(schema, root)
        if node is None:
            return
        if node["type"] == "array":
            self.assertEqual(schema.get("type"), "array", path)
            self.compare(node["items"], schema["items"], root, path + "[]")
            return
        if node.get("open"):
            self.assertNotEqual(schema.get("additionalProperties"), False, f"{path} is open in the table but closed in the schema")
            return
        self.assertIs(schema.get("additionalProperties"), False, f"{path} is closed in the table but open in the schema")
        props = dict(schema.get("properties", {}))
        has_ext = props.pop("extensions", None) is not None
        self.assertEqual(has_ext, node["extensions"], f"{path}: extensions block allowed in one but not the other")
        self.assertEqual(set(props), set(node["fields"]), path or "(root)")
        for key, sub in node["fields"].items():
            self.compare(sub, props[key], root, f"{path}.{key}" if path else key)

    def test_tables(self):
        for name, table in (
            ("owp-manifest", structure.MANIFEST),
            ("compatibility-evidence", structure.COMPATIBILITY_EVIDENCE),
            ("observation-set", structure.OBSERVATION_SET),
            ("effective-world-state", structure.EFFECTIVE_WORLD_STATE),
        ):
            with self.subTest(schema=name):
                schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
                self.compare(table, schema, schema, "")

    def test_experimental_tables(self):
        for kind, table in experimental.TABLES.items():
            name = re.sub(r"(?<!^)(?=[A-Z])", "-", kind).lower()
            with self.subTest(kind=kind):
                schema = json.loads((SCHEMAS / "experimental" / f"{name}.schema.json").read_text(encoding="utf-8"))
                self.compare(table, schema, schema, "")


if __name__ == "__main__":
    unittest.main()
