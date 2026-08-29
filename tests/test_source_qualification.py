from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_source_qualification import Gate, SourceQualificationError, load_contract, run_gate


class SourceQualificationTests(unittest.TestCase):
    def test_contract_has_unique_gates_and_explicit_target_exclusions(self) -> None:
        gates, exclusions = load_contract(Path("config/source_qualification.json"))
        self.assertEqual(len(gates), len({gate.gate_id for gate in gates}))
        gate_ids = {gate.gate_id for gate in gates}
        self.assertIn("mypy", gate_ids)
        self.assertIn("maintained_tests", gate_ids)
        self.assertIn("semantic_authority", gate_ids)
        self.assertIn("audit_remediation_regression", gate_ids)
        self.assertIn("current_revision_cognition_regression", gate_ids)
        self.assertIn("general_ability_level_a", gate_ids)
        self.assertIn("provider_fault_matrix_level_a", gate_ids)
        self.assertIn("release qualification", exclusions)

    def test_every_declared_python_test_target_exists(self) -> None:
        gates, _exclusions = load_contract(Path("config/source_qualification.json"))
        missing = sorted(
            argument
            for gate in gates
            for argument in gate.argv
            if argument.startswith("tests/")
            and argument.endswith(".py")
            and not Path(argument).is_file()
        )
        self.assertEqual(missing, [])

    def test_missing_dependency_is_blocked_not_passed(self) -> None:
        gate = Gate(
            gate_id="missing-static-tool",
            argv=("{python}", "-c", "import sys; print('tool unavailable'); sys.exit(2)"),
            dependency="tool==1",
        )
        result = run_gate(gate)
        self.assertEqual(result["status"], "unavailable")

    def test_non_dependency_failure_is_failed(self) -> None:
        gate = Gate(
            gate_id="failing-source-check",
            argv=("{python}", "-c", "import sys; sys.exit(1)"),
        )
        result = run_gate(gate)
        self.assertEqual(result["status"], "failed")

    def test_invalid_contract_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"schema_version": "1.0", "gates": []}))
            with self.assertRaises(SourceQualificationError):
                load_contract(path)


if __name__ == "__main__":
    unittest.main()
