from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_runtime_structure as checker

CONFIG, ROOT, check = checker.CONFIG, checker.ROOT, checker.check


class RuntimeStructureRatchetTests(unittest.TestCase):
    def test_current_tree_satisfies_runtime_structure_ratchets(self) -> None:
        self.assertEqual(check(), [])

    def test_maintained_gate_checks_runtime_structure(self) -> None:
        script = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn("python scripts/check_runtime_structure.py", script)

    def probe(self, source: str, baseline: int | None = None) -> tuple[int, str]:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        if baseline is not None:
            config["voice_assistant"]["size_baselines"] = dict.fromkeys(
                ("method_count", "property_count", "init_lines", "init_self_attributes"),
                baseline,
            )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "rules.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            source_path = root / config["voice_assistant"]["path"]
            source_path.parent.mkdir(parents=True)
            source_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with (
                mock.patch.object(checker, "ROOT", root),
                mock.patch.object(checker, "CONFIG", config_path),
                contextlib.redirect_stdout(output),
            ):
                status = checker.main()
        return status, output.getvalue()

    def current_source(self, init_text: str = "", methods: str = "") -> str:
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
        lines = source.splitlines(keepends=True)
        lines[class_node.end_lineno:class_node.end_lineno] = [methods]
        lines[init.body[0].lineno - 1:init.body[0].lineno - 1] = [init_text]
        return "".join(lines)

    def test_size_growth_is_reported_without_rejecting_owned_source(self) -> None:
        variants = (
            ("init_lines", "        # Comment one.\n        # Comment two.\n", ""),
            ("init_self_attributes", "        self.probe_a = self.probe_b = self.probe_c = None\n", ""),
            ("method_count", "", "\n    def probe_one(self):\n        return None\n\n    def probe_two(self):\n        return None\n"),
            ("property_count", "", "\n    @property\n    def probe_property(self):\n        return None\n"),
        )
        for metric, init_text, methods in variants:
            with self.subTest(metric=metric):
                source = self.current_source(init_text, methods)
                if metric == "init_lines":
                    self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(self.current_source())))
                status, output = self.probe(source)
                self.assertEqual(status, 0, output)
                self.assertIn(metric + "=", output)
                self.assertIn("delta=+", output)
                self.assertIn("informational", output)

    def test_ownership_violations_block_above_and_below_size_baselines(self) -> None:
        variants = (
            (self.current_source("        self.active_turn_task = None\n"), "lifecycle-owned state"),
            (self.current_source().replace("self.input_turn_lifecycle =", "self.probe_lifecycle =", 1), "must own collaborator"),
            (self.current_source(methods="\n    def _build_direct_llm_prompt(self):\n        return None\n"), "legacy semantic compatibility methods"),
            (self.current_source(methods="\n    def probe(self):\n        return self.process_llm_tts()\n"), "legacy direct-LLM semantic calls"),
        )
        for source, error in variants:
            for baseline in (0, 10000):
                with self.subTest(error=error, baseline=baseline):
                    status, output = self.probe(source, baseline)
                    self.assertEqual(status, 1, output)
                    self.assertIn(error, output)
                    self.assertIn("informational", output)

    def test_malformed_measurement_baseline_is_not_silently_ignored(self) -> None:
        status, output = self.probe(self.current_source(), baseline=-1)
        self.assertEqual(status, 1, output)
        self.assertIn("size_baselines.method_count", output)


if __name__ == "__main__":
    unittest.main()
