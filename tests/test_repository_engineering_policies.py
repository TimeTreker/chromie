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


    def test_host_semantic_delegation_and_phrase_agents_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            deep = root / "orchestrator" / "runtime" / "deepthinking_policy.py"
            deep.parent.mkdir(parents=True)
            deep.write_text("class DeepThinkingDelegationPolicy: pass\n", encoding="utf-8")
            runtime = root / "agent" / "app" / "runtime.py"
            runtime.parent.mkdir(parents=True)
            runtime.write_text("MotionPlannerAgent = object\n", encoding="utf-8")
            catalog = root / "agent" / "app" / "capabilities" / "catalog.py"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                "_STOP_WORDS = {'please'}\n"
                "def _semantic_action_score(): pass\n",
                encoding="utf-8",
            )
            validator = root / "agent" / "app" / "capabilities" / "validator.py"
            validator.write_text(
                "def normalize_enum_string(value): return {'quickly': 'quick'}.get(value, value)\n",
                encoding="utf-8",
            )
            interpreter = (
                root
                / "agent"
                / "app"
                / "cognitive_core"
                / "goal_interpreter"
                / "model_interpreter.py"
            )
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text(
                "weather_semantics_require_tool_route = True\n", encoding="utf-8"
            )
            coordinator = root / "orchestrator" / "runtime" / "interaction_coordinator.py"
            coordinator.parent.mkdir(parents=True, exist_ok=True)
            coordinator.write_text(
                "def _truth_reconciliation_message(): pass\n", encoding="utf-8"
            )
            conversation_state = root / "orchestrator" / "runtime" / "conversation_state.py"
            conversation_state.write_text(
                "DEFAULT_FOLLOWUP_PHRASES = ('that',)\n"
                "def is_followup_reference(text): return text in DEFAULT_FOLLOWUP_PHRASES\n",
                encoding="utf-8",
            )
            tool = root / "agent" / "app" / "agents" / "tool.py"
            tool.parent.mkdir(parents=True, exist_ok=True)
            tool.write_text(
                "async def run(services, query): return await services.weather_client.lookup(query)\n",
                encoding="utf-8",
            )
            memory = root / "agent" / "app" / "agents" / "memory.py"
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text(
                "import re\n"
                "class MemoryAgent:\n"
                "    def run(self, request):\n"
                "        return re.sub('remember', '', request.text)\n"
                "    acknowledgement = 'I will remember that.'\n",
                encoding="utf-8",
            )
            speaker = root / "agent" / "app" / "agents" / "speaker.py"
            speaker.write_text(
                "class SpeakerAgent:\n"
                "    def _default_speech(self): return 'I understand.'\n",
                encoding="utf-8",
            )
            conversation = root / "agent" / "app" / "agents" / "conversation.py"
            conversation.write_text(
                "import re\n"
                "class ConversationAgent:\n"
                "    ACTION_PHRASES = ('walk', 'blink')\n"
                "    bad_prefixes = ('assistant:',)\n"
                "    def _fallback_reply(self): return 'That sounds tiring.'\n",
                encoding="utf-8",
            )
            schema = root / "agent" / "app" / "cognitive_core" / "goal_interpreter" / "schema.py"
            schema.parent.mkdir(parents=True, exist_ok=True)
            schema.write_text(
                'decision.speak_first = "What do you mean?"\n',
                encoding="utf-8",
            )
            agent_schema = root / "agent" / "app" / "schema.py"
            agent_schema.parent.mkdir(parents=True, exist_ok=True)
            agent_schema.write_text(
                "def reject_contract_marker_as_spoken_text(): pass\n",
                encoding="utf-8",
            )

            findings = policies.audit_semantic_authority_boundaries(root)

        rule_ids = {item.rule_id for item in findings}
        self.assertIn(policies.RULE_HOST_SEMANTIC_AUTHORITY, rule_ids)
        self.assertIn(policies.RULE_LEGACY_PHRASE_AGENTS, rule_ids)
        self.assertIn(policies.RULE_MEMORY_MODEL_AUTHORED, rule_ids)
        symbols = {item.symbol for item in findings}
        self.assertIn("_STOP_WORDS", symbols)
        self.assertIn("normalize_enum_string", symbols)
        self.assertIn("reject_contract_marker_as_spoken_text", symbols)
        self.assertIn("ACTION_PHRASES", symbols)

    def test_model_facing_skill_id_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "shared" / "chromie_contracts" / "social_attention.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "class SocialAttentionBehavior:\n"
                "    skill_id: str | None = None\n",
                encoding="utf-8",
            )

            findings = policies.audit_canonical_capability_identity(root)

        self.assertIn(
            policies.RULE_CANONICAL_CAPABILITY_ID,
            {item.rule_id for item in findings},
        )

    def test_retired_capability_runtime_execute_api_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "orchestrator" / "runtime" / "capability_runtime.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "class CapabilityRuntime:\n"
                "    async def submit(self): pass\n"
                "    async def wait_terminal(self): pass\n"
                "    async def execute(self): pass\n",
                encoding="utf-8",
            )

            findings = policies.audit_canonical_capability_identity(root)

        self.assertTrue(
            any(item.symbol == "CapabilityRuntime.execute" for item in findings),
            findings,
        )

    def test_detached_capability_boundary_and_retired_aggregate_apis_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coordinator = root / "orchestrator" / "runtime" / "interaction_coordinator.py"
            coordinator.parent.mkdir(parents=True)
            coordinator.write_text(
                "class InteractionRuntimeCoordinator:\n"
                "    async def execute(self): pass\n",
                encoding="utf-8",
            )
            orchestrator = root / "orchestrator" / "orchestrator.py"
            orchestrator.write_text(
                "class VoiceAssistant:\n"
                "    async def execute_interaction_response(self): pass\n",
                encoding="utf-8",
            )

            findings = policies.audit_canonical_capability_identity(root)

        symbols = {item.symbol for item in findings}
        self.assertIn("InteractionRuntimeCoordinator.execute", symbols)
        self.assertIn("VoiceAssistant.execute_interaction_response", symbols)
        self.assertIn(
            "InteractionRuntimeCoordinator.submit_response",
            symbols,
        )
        self.assertIn(
            "InteractionRuntimeCoordinator.wait_dispatch",
            symbols,
        )
        self.assertIn(
            "VoiceAssistant._dispatch_detached_interaction",
            symbols,
        )
        self.assertIn(
            "VoiceAssistant._consume_detached_cognitive_dispatch",
            symbols,
        )
        self.assertIn(
            "VoiceAssistant._reenter_cognition_for_terminal_capability",
            symbols,
        )

    def test_parallel_capability_event_manager_authority_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "orchestrator" / "runtime" / "capability_runtime.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "class CapabilityIdentityModel: pass\n"
                "class CapabilityRuntimeEvent(CapabilityIdentityModel): pass\n"
                "class CapabilityRuntime:\n"
                "    async def submit(self): pass\n"
                "    async def wait_terminal(self): pass\n"
                "    async def runtime_events_after(self): pass\n"
                "    async def wait_runtime_event(self): pass\n"
                "class EventManager: pass\n",
                encoding="utf-8",
            )

            findings = policies.audit_canonical_capability_identity(root)

        self.assertTrue(
            any(item.symbol == "EventManager" for item in findings),
            findings,
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
