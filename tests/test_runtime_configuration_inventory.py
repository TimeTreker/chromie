from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.runtime_configuration_inventory import build_inventory, discover


ROOT = Path(__file__).resolve().parents[1]


class RuntimeConfigurationInventoryTests(unittest.TestCase):
    def test_discovery_excludes_virtual_environments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "orchestrator" / "runtime.py"
            source.parent.mkdir(parents=True)
            source.write_text('os.getenv("OWNED_SETTING")\n', encoding="utf-8")
            ignored = root / "orchestrator" / ".venv" / "lib" / "dependency.py"
            ignored.parent.mkdir(parents=True)
            ignored.write_text('os.getenv("DEPENDENCY_SETTING")\n', encoding="utf-8")

            keys, owners, _ = discover(root)

        self.assertEqual(keys, {"OWNED_SETTING"})
        self.assertEqual(owners["OWNED_SETTING"], {"orchestrator/runtime.py"})

    def test_inventory_covers_discovered_keys_with_declared_categories(self) -> None:
        inventory = build_inventory(ROOT)
        entries = inventory["entries"]
        keys = [entry["key"] for entry in entries]
        self.assertEqual(keys, sorted(set(keys)))
        # Alias removal may legitimately shrink the surface; guard the maintained
        # inventory from accidental collapse without rewarding compatibility growth.
        self.assertGreaterEqual(len(entries), 370)
        self.assertEqual(inventory["summary"]["compatibility_aliases"], 0)
        self.assertEqual(
            {entry["category"] for entry in entries},
            {
                "acceptance_override",
                "profile_constant",
                "public_choice",
                "service_internal",
            },
        )
        self.assertEqual(inventory["maintained_modes"], [
            "qualification",
            "services",
            "speech",
            "voice_mujoco",
        ])

    def test_committed_inventory_is_current(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/runtime_configuration_inventory.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("modes=4", completed.stdout)

    def test_public_switch_and_alias_ratchets_are_bounded(self) -> None:
        payload = json.loads(
            (ROOT / "config" / "runtime_configuration_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        summary = payload["summary"]
        self.assertLessEqual(summary["public_boolean_choices"], 1)
        self.assertEqual(summary["compatibility_aliases"], 0)
        public = {
            entry["key"]
            for entry in payload["entries"]
            if entry["category"] == "public_choice"
        }
        self.assertIn("CHROMIE_OPERATOR_MODE", public)
        self.assertIn("ORCH_INPUT_DEVICE", public)
        self.assertNotIn("ORCH_ENABLE_SORIDORMI_CAPABILITIES", public)

    def test_maintained_gate_checks_configuration_inventory(self) -> None:
        script = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn(
            "python scripts/runtime_configuration_inventory.py --check",
            script,
        )

    def test_launchers_select_owned_operator_modes(self) -> None:
        expected = {
            "scripts/start_services.sh": "services",
            "scripts/start_orchestrator.sh": "speech",
            "scripts/start_chromie.sh": "voice_mujoco",
            "scripts/run_target_evidence_closure.py": "qualification",
        }
        for raw_path, mode in expected.items():
            with self.subTest(path=raw_path):
                text = (ROOT / raw_path).read_text(encoding="utf-8")
                self.assertIn("CHROMIE_OPERATOR_MODE", text)
                self.assertIn(mode, text)


if __name__ == "__main__":
    unittest.main()
