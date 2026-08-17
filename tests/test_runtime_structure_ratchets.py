from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts.check_runtime_structure import CONFIG, ROOT, check


class RuntimeStructureRatchetTests(unittest.TestCase):
    def test_current_tree_satisfies_runtime_structure_ratchets(self) -> None:
        self.assertEqual(check(), [])

    def test_maintained_gate_checks_runtime_structure(self) -> None:
        script = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn("python scripts/check_runtime_structure.py", script)

    def test_legacy_direct_semantic_surface_is_forbidden(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))["voice_assistant"]
        tree = ast.parse((ROOT / config["path"]).read_text(encoding="utf-8"))
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == config["class_name"]
        )
        method_names = {
            node.name
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(set(config["forbidden_methods"]).isdisjoint(method_names))


    def test_lifecycle_aliases_are_not_initialized_on_composition_root(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))["voice_assistant"]
        source = (ROOT / config["path"]).read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == config["class_name"]
        )
        init = next(
            node
            for node in class_node.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        assigned = {
            item.attr
            for node in ast.walk(init)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            for item in ast.walk(target)
            if isinstance(item, ast.Attribute)
            and isinstance(item.value, ast.Name)
            and item.value.id == "self"
        }
        self.assertFalse(assigned & set(config["forbidden_init_state_attributes"]))


if __name__ == "__main__":
    unittest.main()
