from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_repository_policies.py"

spec = importlib.util.spec_from_file_location("check_repository_policies", CHECKER)
if spec is None or spec.loader is None:  # pragma: no cover - import invariant
    raise RuntimeError("cannot load repository policy checker")
policies = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policies
spec.loader.exec_module(policies)


class RepositoryEngineeringPolicyTests(unittest.TestCase):
    def test_current_repository_passes_canonical_policy_gate(self) -> None:
        findings, suppressed = policies.audit_repository(ROOT)
        self.assertEqual(findings, [])
        self.assertEqual(suppressed, 0)

    def test_production_assert_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "app" / "bad.py"
            path.parent.mkdir(parents=True)
            path.write_text("def run(value):\n    assert value\n", encoding="utf-8")

            findings = policies.audit_python_policies(root)

        self.assertIn(policies.RULE_PRODUCTION_ASSERT, {item.rule_id for item in findings})

    def test_trivially_silent_broad_exception_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "orchestrator" / "bad.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "def run(items):\n"
                "    for item in items:\n"
                "        try:\n"
                "            use(item)\n"
                "        except Exception:\n"
                "            continue\n",
                encoding="utf-8",
            )

            findings = policies.audit_python_policies(root)

        self.assertIn(
            policies.RULE_SILENT_BROAD_EXCEPTION,
            {item.rule_id for item in findings},
        )

    def test_dynamic_execution_and_shell_true_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "tools" / "bad.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "import subprocess\n"
                "def run(command):\n"
                "    eval(command)\n"
                "    subprocess.run(command, shell=True)\n",
                encoding="utf-8",
            )

            findings = policies.audit_python_policies(root)

        rule_ids = {item.rule_id for item in findings}
        self.assertIn(policies.RULE_DYNAMIC_EXECUTION, rule_ids)
        self.assertIn(policies.RULE_UNSAFE_SHELL, rule_ids)

    def test_low_level_actuation_field_is_rejected_from_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "shared" / "chromie_contracts" / "bad.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "class ModelRequest:\n    motor_targets: list[float]\n",
                encoding="utf-8",
            )

            findings = policies.audit_model_contract_fields(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, policies.RULE_LOW_LEVEL_CONTRACT)
        self.assertEqual(findings[0].symbol, "ModelRequest.motor_targets")

    def test_wildcard_compose_publication_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n"
                "  agent:\n"
                "    ports:\n"
                "      - \"8092:8092\"\n",
                encoding="utf-8",
            )

            findings = policies.audit_compose_policy(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, policies.RULE_LOCAL_EXPOSURE)

    def test_agent_skill_execution_authority_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "app" / "agent_skills" / "loader.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "import subprocess\n"
                "class AgentSkillRegistry:\n"
                "    def execute(self):\n"
                "        return subprocess.run(['true'])\n",
                encoding="utf-8",
            )

            findings = policies.audit_agent_skill_authority(root)

        self.assertGreaterEqual(len(findings), 2)
        self.assertEqual(
            {item.rule_id for item in findings},
            {policies.RULE_AGENT_SKILL_AUTHORITY},
        )

    def test_host_phrase_selection_and_missing_model_call_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "app" / "agent_skills" / "selection.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "class AgentSkillSelectionService:\n"
                "    async def select(self, request):\n"
                "        return None\n"
                "    def _discover_candidates(self, request):\n"
                "        if 'weather' in request.text:\n"
                "            return ('weather',)\n"
                "        return ()\n",
                encoding="utf-8",
            )

            findings = policies.audit_agent_skill_selection(root)

        self.assertGreaterEqual(len(findings), 2)
        self.assertEqual(
            {item.rule_id for item in findings},
            {policies.RULE_AGENT_SKILL_SELECTION},
        )

    def test_reviewed_exception_is_exact_and_stale_exception_fails(self) -> None:
        finding = policies.PolicyFinding(
            rule_id=policies.RULE_PRODUCTION_ASSERT,
            path="agent/app/example.py",
            line=10,
            symbol="run",
            message="example",
        )
        exception = policies.PolicyException(
            rule_id=policies.RULE_PRODUCTION_ASSERT,
            path="agent/app/example.py",
            symbol="run",
            reason="Temporary compatibility boundary reviewed by the owner.",
            remove_when="Remove when the external compatibility caller is migrated.",
        )

        remaining, suppressed = policies.apply_policy_exceptions(
            [finding],
            [exception],
            exception_path="config/repository_policy_exceptions.json",
        )
        stale, stale_suppressed = policies.apply_policy_exceptions(
            [],
            [exception],
            exception_path="config/repository_policy_exceptions.json",
        )

        self.assertEqual(remaining, [])
        self.assertEqual(suppressed, 1)
        self.assertEqual(stale_suppressed, 0)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].rule_id, policies.RULE_STALE_EXCEPTION)

    def test_exception_registry_rejects_wildcards_and_weak_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "exceptions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "exceptions": [
                            {
                                "rule_id": policies.RULE_PRODUCTION_ASSERT,
                                "path": "../*.py",
                                "symbol": "*",
                                "reason": "temporary",
                                "remove_when": "later",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            exceptions, findings = policies.load_policy_exceptions(path, root)

        self.assertEqual(exceptions, [])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, policies.RULE_EXCEPTION_CONFIG)

    def test_cli_json_output_is_machine_readable(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CHECKER), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["findings"], [])

    def test_maintained_test_entrypoint_runs_policy_checker(self) -> None:
        text = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn("python scripts/check_repository_policies.py", text)


if __name__ == "__main__":
    unittest.main()
