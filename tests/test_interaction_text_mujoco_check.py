from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field

from scripts.interaction_text_mujoco_check import (
    INTERNAL_SPEECH_PATTERNS,
    _apply_soridormi_skill_timeout,
    _configure_environment,
    _endpoint_source_revision,
    _planner_communication_already_scheduled,
    build_parser,
    build_debug_summary,
    collect_run_provenance,
    dispatch_initial_reflex,
    parse_expected_arg,
    record_execution_bindings,
    required_speech_delivery_errors,
    safe_idle_errors,
    should_require_tts_speech,
    validate_contract,
    validate_speech_contract,
    wait_for_provider_started,
    wait_for_session_done,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.reflex import ReflexFilter


class InteractionTextMujocoCheckTests(unittest.TestCase):

    def test_live_dispatch_preserves_prior_fast_planner_communication(self) -> None:
        self.assertTrue(
            _planner_communication_already_scheduled(
                SimpleNamespace(metadata={"fast_vocal_activity_ids": ["progress-1"]})
            )
        )
        self.assertFalse(
            _planner_communication_already_scheduled(
                SimpleNamespace(metadata={"fast_vocal_activity_ids": []})
            )
        )

    def test_initial_reflex_uses_production_dispatch_and_retains_scope(self) -> None:
        outcome = ReflexFilter().evaluate("停止音乐。")

        class ConversationState:
            history: list[dict[str, object]] = []

            def get_history(self) -> list[dict[str, object]]:
                return list(self.history)

        class Assistant:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str]] = []
                self.sessions = SimpleNamespace(
                    state={"sid-reflex": {"done_logged": False}}
                )
                self.conversation_state = ConversationState()

            async def handle_routed_text(
                self,
                text: str,
                sid: str,
                *,
                channel: str,
            ) -> None:
                self.calls.append((text, sid, channel))
                self.conversation_state.history = [
                    {
                        "role": "user",
                        "text": text,
                        "metadata": {
                            "source": "cognitive_gateway_reflex",
                            "reflex_outcome": outcome.model_dump(mode="json"),
                            "cancellation_dispatch_receipt": {
                                "requested_scope": "media_output",
                            },
                        },
                    }
                ]
                self.sessions.state[sid]["done_logged"] = True

        assistant = Assistant()
        reflex, response, evidence, errors = asyncio.run(
            dispatch_initial_reflex(
                assistant=assistant,
                text="停止音乐。",
                sid="sid-reflex",
                turn_capture=SimpleNamespace(reflex_candidate=outcome),
                timeout_s=1.0,
            )
        )

        self.assertEqual(
            assistant.calls,
            [("停止音乐。", "sid-reflex", "text")],
        )
        self.assertEqual(errors, [])
        self.assertEqual(reflex["action"], "interrupt")
        self.assertEqual(reflex["trigger"], "stop_command")
        self.assertEqual(reflex["cancellation_scope"], "media_output")
        self.assertFalse(response.speech)
        self.assertFalse(response.capabilities)
        self.assertTrue(evidence["goal_interpretation_bypassed"])

    def test_goal_driven_runtime_is_the_only_runtime(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args([])
        self.assertTrue(parsed.cognitive_runtime)
        self.assertNotIn("--no-cognitive-runtime", parser._option_string_actions)
        self.assertEqual(
            build_parser()
            .parse_args(["--soridormi-repo", "/tmp/soridormi-checkout"])
            .soridormi_repo,
            "/tmp/soridormi-checkout",
        )
        cancellation = build_parser().parse_args(
            ["--interrupt-text", "Stop.", "--expect-cancelled"]
        )
        self.assertEqual(cancellation.interrupt_text, "Stop.")
        self.assertTrue(cancellation.expect_cancelled)
        self.assertEqual(cancellation.interrupt_capability_prefix, "soridormi.")

    def test_endpoint_source_revision_accepts_direct_and_nested_status(self) -> None:
        self.assertEqual(
            _endpoint_source_revision({"source_revision": "soridormi-direct"}),
            "soridormi-direct",
        )
        self.assertEqual(
            _endpoint_source_revision(
                {"provider": {"git_revision": "soridormi-nested"}}
            ),
            "soridormi-nested",
        )
        self.assertIsNone(_endpoint_source_revision({"mode": "sim"}))

    def test_run_provenance_records_source_manifest_and_selected_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            manifest = root / "soridormi.json"
            manifest.write_text(
                '{"metadata":{"upstream_commit":"soridormi-abc"}}',
                encoding="utf-8",
            )
            soridormi_repo = root / "soridormi-checkout"
            with patch(
                "scripts.interaction_text_mujoco_check._git_text",
                side_effect=[
                    "chromie-def",
                    " M scripts/example.py",
                    "soridormi-abc",
                    "",
                ],
            ):
                provenance = collect_run_provenance(
                    manifest=manifest,
                    cognitive_runtime=True,
                    soridormi_repo=soridormi_repo,
                    root=root,
                )

        self.assertEqual(provenance["chromie"]["revision"], "chromie-def")
        self.assertEqual(provenance["chromie"]["version"], "1.2.3")
        self.assertTrue(provenance["chromie"]["dirty"])
        self.assertEqual(
            provenance["soridormi"]["upstream_revision"],
            "soridormi-abc",
        )
        self.assertEqual(
            provenance["soridormi"]["checkout"],
            str(soridormi_repo.resolve()),
        )
        self.assertEqual(
            provenance["soridormi"]["checkout_revision"],
            "soridormi-abc",
        )
        self.assertFalse(provenance["soridormi"]["checkout_dirty"])
        self.assertEqual(
            provenance["semantic_runtime"],
            {
                "path": "goal_driven_cognitive_runtime",
                "configured_cognitive_runtime_mode": "apply",
                "cognitive_runtime_selected": True,
            },
        )

    def test_run_provenance_names_the_reflex_path_without_claiming_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "soridormi.json"
            manifest.write_text("{}", encoding="utf-8")
            with patch(
                "scripts.interaction_text_mujoco_check._git_text",
                return_value=None,
            ):
                provenance = collect_run_provenance(
                    manifest=manifest,
                    cognitive_runtime=True,
                    cognitive_runtime_selected=False,
                    semantic_runtime_path="cognitive_gateway_reflex",
                    root=root,
                )

        semantic = provenance["semantic_runtime"]
        self.assertEqual(semantic["path"], "cognitive_gateway_reflex")
        self.assertFalse(semantic["cognitive_runtime_selected"])

    def test_voice_mujoco_wrapper_uses_the_canonical_runtime(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "run_voice_mujoco_text_case.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn("--cognitive-runtime", source)
        self.assertNotIn("--legacy-agent-runtime", source)
        self.assertIn("--grant-confirmation", source)
        self.assertNotIn("auto-confirm" + "-sim", source)

    def test_configure_environment_uses_isolated_conversation_id(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {}, clear=True),
            patch(
                "orchestrator.orchestrator.load_runtime_environment"
            ) as load_runtime_environment,
        ):
            args = argparse.Namespace(
                agent_url="http://127.0.0.1:8092",
                grant_confirmation=True,
                speaker=False,
                manifest=Path("capabilities/soridormi.json"),
                cognitive_runtime=True,
                soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                conversation_id="ga-live-case-one",
            )

            _configure_environment(args, Path(temp_dir))

            load_runtime_environment.assert_called_once_with()
            self.assertEqual(os.environ["ORCH_CONVERSATION_ID"], "ga-live-case-one")
            self.assertEqual(os.environ["ORCH_COGNITIVE_RUNTIME_MODE"], "apply")
            self.assertEqual(os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"], "1")

    def test_configure_environment_retains_loaded_qualification_budgets(self) -> None:
        def load_profile() -> None:
            os.environ.setdefault("ORCH_GOAL_ASSOCIATION_TIMEOUT_MS", "150000")
            os.environ.setdefault("ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS", "600000")

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {}, clear=True),
            patch(
                "orchestrator.orchestrator.load_runtime_environment",
                side_effect=load_profile,
            ),
        ):
            args = argparse.Namespace(
                agent_url="http://127.0.0.1:8092",
                grant_confirmation=True,
                speaker=False,
                manifest=Path("capabilities/soridormi.json"),
                cognitive_runtime=True,
                soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                conversation_id="ga-live-budget-check",
            )

            _configure_environment(args, Path(temp_dir))

            self.assertEqual(os.environ["ORCH_GOAL_ASSOCIATION_TIMEOUT_MS"], "150000")
            self.assertEqual(os.environ["ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS"], "600000")

    def test_parse_expected_arg_accepts_json_scalars(self) -> None:
        self.assertEqual(parse_expected_arg("0:vx_mps=0.2"), (0, "vx_mps", 0.2))
        self.assertEqual(parse_expected_arg("1:count=2"), (1, "count", 2))
        self.assertEqual(parse_expected_arg("2:label=left"), (2, "label", "left"))

    def test_parse_expected_arg_rejects_bad_shape(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_expected_arg("vx_mps=0.2")

    @staticmethod
    def _interpretation(*, confidence: float = 0.99) -> dict[str, object]:
        return {
            "confidence": confidence,
            "responsibilities": [
                {
                    "local_ref": "resp-1",
                    "outcome": "Complete the requested outcome.",
                    "output_mode": "body_action",
                }
            ],
            "unresolved": [],
        }

    def test_validate_contract_checks_ordered_skills_and_args(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "capabilities": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "args": {
                            "vx_mps": 0.2,
                            "vy_mps": 0.0,
                            "yaw_radps": 0.0,
                            "duration_s": 10.0,
                        },
                        "timing": "sequential",
                    },
                    {"capability_id": "soridormi.nod_yes", "args": {"count": 2}},
                    {
                        "capability_id": "soridormi.turn_in_place",
                        "args": {"yaw_radps": 0.12},
                    },
                ]
            }
        )
        errors = validate_contract(
            interpretation=self._interpretation(),
            response=response,
            expected_capabilities=[
                "soridormi.walk_velocity",
                "soridormi.nod_yes",
                "soridormi.turn_in_place",
            ],
            expect_no_capabilities=False,
            expected_args=[
                (0, "vx_mps", 0.2),
                (0, "duration_s", 10.0),
                (1, "count", 2),
                (2, "yaw_radps", 0.12),
            ],
            arg_tolerance=1e-6,
        )
        self.assertEqual(errors, [])

    def test_validate_contract_accepts_planner_capabilities_without_gi_actions(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "capabilities": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                    },
                    {"capability_id": "soridormi.blink_eyes", "args": {"count": 2}},
                ]
            }
        )
        errors = validate_contract(
            interpretation=self._interpretation(confidence=0.81),
            response=response,
            expected_capabilities=["soridormi.walk_velocity", "soridormi.blink_eyes"],
            expect_no_capabilities=False,
            expected_args=[(0, "vx_mps", 0.2), (1, "count", 2)],
            arg_tolerance=1e-6,
        )
        self.assertEqual(errors, [])

    def test_validate_contract_accepts_exact_local_tool_skill(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "capabilities": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "args": {"location": "chongqing", "period": "night"},
                    }
                ]
            }
        )
        errors = validate_contract(
            interpretation=self._interpretation(),
            response=response,
            expected_capabilities=["chromie.weather.lookup"],
            expect_no_capabilities=False,
            expected_args=[(0, "location", "chongqing"), (0, "period", "night")],
            arg_tolerance=1e-6,
        )
        self.assertEqual(errors, [])

    def test_build_debug_summary_describes_responsibilities_and_skills(self) -> None:
        interpretation = {
            "confidence": 0.87,
            "responsibilities": [
                {"outcome": "Walk forward.", "output_mode": "body_action"},
                {"outcome": "Blink twice.", "output_mode": "body_action"},
            ],
            "unresolved": [],
        }
        response = InteractionResponse.model_validate(
            {
                "capabilities": [
                    {"capability_id": "soridormi.blink_eyes", "args": {"count": 2}}
                ],
                "speech": [{"text": "Okay.", "timing": "immediate"}],
            }
        )
        summary = build_debug_summary(
            interpretation=interpretation,
            response=response,
            errors=["example failure"],
        )
        self.assertIn("responsibilities=2", summary["interpretation"])
        self.assertEqual(summary["responsibility_outcomes"], ["Walk forward.", "Blink twice."])
        self.assertEqual(summary["capabilities"], ["soridormi.blink_eyes"])
        self.assertEqual(summary["speech_items"], 1)
        self.assertEqual(summary["errors"], ["example failure"])

    def test_validate_contract_reports_capability_and_argument_mismatch(self) -> None:
        errors = validate_contract(
            interpretation=self._interpretation(confidence=0.5),
            response=InteractionResponse(),
            expected_capabilities=["soridormi.walk_velocity"],
            expect_no_capabilities=False,
            expected_args=[(0, "vx_mps", 0.2)],
            arg_tolerance=1e-6,
        )
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("interaction capabilities mismatch" in item for item in errors))

    def test_validate_contract_accepts_conversation_without_execution_capabilities(self) -> None:
        response = InteractionResponse.model_validate(
            {"speech": [{"text": "Here is a short answer.", "timing": "immediate"}]}
        )
        errors = validate_contract(
            interpretation=self._interpretation(confidence=0.91),
            response=response,
            expected_capabilities=[],
            expect_no_capabilities=True,
            expected_args=[],
            arg_tolerance=1e-6,
        )
        self.assertEqual(errors, [])

    def test_validate_speech_contract_rejects_internal_planner_leakage(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "speech": [
                    {
                        "text": (
                            "I'll walk forward quickly. Task Split: 1. "
                            "Execute soridormi.walk_forward now."
                        ),
                        "timing": "immediate",
                    }
                ]
            }
        )

        errors = validate_speech_contract(response, INTERNAL_SPEECH_PATTERNS)

        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("Task Split" in item for item in errors))
        self.assertTrue(any("soridormi" in item for item in errors))

    def test_validate_speech_contract_allows_natural_spoken_text(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "speech": [
                    {
                        "text": "Walking forward now. I will stop if anything looks unsafe.",
                        "timing": "immediate",
                    }
                ]
            }
        )

        errors = validate_speech_contract(response, INTERNAL_SPEECH_PATTERNS)

        self.assertEqual(errors, [])

    def test_safe_idle_errors_require_idle_non_emergency_status(self) -> None:
        self.assertEqual(
            safe_idle_errors(
                {
                    "safe_idle": True,
                    "active_task": None,
                    "emergency_stop": False,
                    "fallen": False,
                }
            ),
            [],
        )
        self.assertEqual(
            len(
                safe_idle_errors(
                    {
                        "safe_idle": False,
                        "active_task": {"plan_id": "x"},
                        "emergency_stop": True,
                        "fallen": True,
                    }
                )
            ),
            4,
        )

    def test_tts_speech_requirement_is_explicit_harness_policy(self) -> None:
        self.assertTrue(should_require_tts_speech(require_speech=True))
        self.assertFalse(should_require_tts_speech(require_speech=False))

    def test_required_speech_delivery_rejects_skipped_undelivered_speech(self) -> None:
        errors = required_speech_delivery_errors(
            {
                "scheduled_tts": 3,
                "played_tts": 0,
                "failed_tts": 0,
                "skipped_tts": 3,
                "workflow_events": [],
            }
        )

        self.assertTrue(any("skipped" in item for item in errors))
        self.assertTrue(any("incomplete" in item for item in errors))

    def test_required_speech_delivery_rejects_failed_speak_execution(self) -> None:
        errors = required_speech_delivery_errors(
            {
                "scheduled_tts": 1,
                "played_tts": 1,
                "failed_tts": 0,
                "skipped_tts": 0,
                "workflow_events": [
                    {
                        "event": "capability_result",
                        "severity": "error",
                        "message": (
                            "capability_result: request_id=speech-1 "
                            "capability_id=chromie.speak status=failed "
                            "reason=playback_not_started"
                        ),
                    }
                ],
            }
        )

        self.assertTrue(any("chromie.speak" in item for item in errors))

    def test_interrupted_execution_allows_stale_speech_suppression(self) -> None:
        errors = required_speech_delivery_errors(
            {
                "scheduled_tts": 2,
                "played_tts": 1,
                "failed_tts": 0,
                "skipped_tts": 1,
                "interrupted": True,
                "workflow_events": [],
            },
            allow_interrupted=True,
        )

        self.assertEqual(errors, [])

    def test_apply_soridormi_timeout_sets_request_timeouts(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "capabilities": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                        "timing": "sequential",
                    },
                    {
                        "capability_id": "chromie.unrelated",
                        "args": {},
                        "timing": "sequential",
                        "timeout_ms": 1000,
                    },
                ]
            }
        )

        updated = _apply_soridormi_skill_timeout(response, 120.0)

        self.assertEqual(updated.capabilities[0].timeout_ms, 120000)
        self.assertEqual(updated.capabilities[1].timeout_ms, 1000)


class ProviderStartObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_capability_runtime_empty_execution_observation_is_bounded(self) -> None:
        from orchestrator.runtime.capability_runtime import CapabilityRegistry, CapabilityRuntime

        observation = await CapabilityRuntime(CapabilityRegistry()).execution_observation()
        self.assertEqual(observation.open_interaction_ids, [])
        self.assertEqual(observation.executing_interaction_ids, [])
        self.assertEqual(observation.requests, [])

    async def test_wait_for_provider_started_returns_bound_observation(self) -> None:
        from orchestrator.runtime.capability_runtime import (
            CapabilityRuntimeExecutionObservation,
            CapabilityRuntimeRequestObservation,
        )

        class Runtime:
            async def execution_observation(self):
                return CapabilityRuntimeExecutionObservation(
                    captured_at="2026-07-27T00:00:00+00:00",
                    open_interaction_ids=["interaction-1"],
                    executing_interaction_ids=["interaction-1"],
                    requests=[
                        CapabilityRuntimeRequestObservation(
                            interaction_id="interaction-1",
                            request_id="request-1",
                            capability_id="soridormi.walk_velocity",
                            provider_id="soridormi.mcp",
                            source_goal_ids=["goal-1"],
                            provider_started=True,
                            task_done=False,
                        )
                    ],
                )

        observation = await wait_for_provider_started(
            Runtime(),
            interaction_id="interaction-1",
            skill_prefix="soridormi.",
            timeout_s=0.2,
        )
        self.assertEqual(
            observation["requests"][0]["source_goal_ids"],
            ["goal-1"],
        )

    async def test_wait_for_provider_started_accepts_runtime_coordinator(self) -> None:
        from orchestrator.runtime.capability_runtime import (
            CapabilityRuntimeExecutionObservation,
            CapabilityRuntimeRequestObservation,
        )

        class Runtime:
            async def execution_observation(self):
                return CapabilityRuntimeExecutionObservation(
                    captured_at="2026-07-31T00:00:00+00:00",
                    open_interaction_ids=["interaction-1"],
                    executing_interaction_ids=["interaction-1"],
                    requests=[
                        CapabilityRuntimeRequestObservation(
                            interaction_id="interaction-1",
                            request_id="request-1",
                            capability_id="soridormi.walk_velocity",
                            provider_id="soridormi.mcp",
                            source_goal_ids=["goal-1"],
                            provider_started=True,
                            task_done=False,
                        )
                    ],
                )

        class Coordinator:
            runtime = Runtime()

        observation = await wait_for_provider_started(
            Coordinator(),
            interaction_id="interaction-1",
            skill_prefix="soridormi.",
            timeout_s=0.2,
        )
        self.assertEqual(observation["requests"][0]["provider_id"], "soridormi.mcp")

    async def test_wait_for_provider_started_rejects_missing_observer(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "observation is unavailable"):
            await wait_for_provider_started(
                object(),
                interaction_id="interaction-1",
                skill_prefix="soridormi.",
                timeout_s=0.01,
            )


class ExecutionBindingTests(unittest.TestCase):
    def test_acceptance_execution_records_exact_host_binding_first(self) -> None:
        calls: list[tuple[str, object, set[str] | None]] = []

        class ConversationState:
            def record_interaction_response(
                self,
                sid: str,
                response: object,
                *,
                confirmed_request_ids: set[str] | None,
            ) -> None:
                calls.append((sid, response, confirmed_request_ids))

        class Assistant:
            conversation_state = ConversationState()

        response = object()
        record_execution_bindings(
            Assistant(),
            response,
            sid="sid-1",
            confirmed_request_ids={"request-1"},
        )

        self.assertEqual(calls, [("sid-1", response, {"request-1"})])


class SessionCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_interrupt_is_a_terminal_session_state(self) -> None:
        class Sessions:
            state = {
                "sid-1": {
                    "done_logged": False,
                    "interrupted": True,
                    "llm_done": True,
                }
            }

        class Assistant:
            sessions = Sessions()

        terminal = await wait_for_session_done(
            Assistant(),
            "sid-1",
            timeout_s=0.01,
            allow_interrupted=True,
        )

        self.assertEqual(terminal, "interrupted")


if __name__ == "__main__":
    unittest.main()
