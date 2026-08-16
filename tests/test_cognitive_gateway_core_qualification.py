from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.runtime.evidence_identity import canonical_json_sha256
from scripts.cognitive_gateway_core_live_text import _configure_environment
from scripts.verify_cognitive_gateway_core_qualification import verify

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "cognitive_gateway_core_qualification_v1.json"
)


def write_identity(path: Path) -> dict:
    payload = {
        "schema_version": 1,
        "captured_at": "2026-07-27T00:00:00+00:00",
        "evidence_claim": "runtime_identity_only",
        "chromie": {
            "revision": "chromie-current",
            "dirty": False,
        },
        "runtime_profile": {
            "fingerprint": "runtime-fingerprint",
            "sha256": "a" * 64,
            "models": {"AGENT_GOAL_INTERPRETER_MODEL": "qwen3:4b"},
        },
        "orchestrator_runtime": {
            "effective_models": {
                "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL": "qwen3:4b",
                "AGENT_GOAL_INTERPRETER_MODEL": "qwen3:4b",
                "AGENT_GOAL_ASSOCIATION_MODEL": "qwen3:4b",
                "AGENT_FAST_PLANNER_MODEL": "qwen3:4b",
                "AGENT_DEEP_PLANNER_MODEL": "qwen3:4b",
                "AGENT_RESPONSE_COMPOSER_MODEL": "qwen3:4b",
                "AGENT_TOOL_RESULT_INTERPRETER_MODEL": "qwen3:4b",
            }
        },
        "capability_manifests": [
            {
                "path": "capabilities/soridormi.json",
                "sha256": "b" * 64,
                "upstream_revision": "soridormi-current",
            }
        ],
        "deployment": {
            "complete": True,
            "service_images": {
                "chromie-agent": {
                    "image_id": "sha256:agent",
                    "effective_runtime": {
                        "CHROMIE_RUNTIME_ENV_FINGERPRINT": "runtime-fingerprint"
                    },
                    "effective_models": {
                        "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL": "qwen3:4b",
                        "AGENT_GOAL_INTERPRETER_MODEL": "qwen3:4b",
                        "AGENT_GOAL_ASSOCIATION_MODEL": "qwen3:4b",
                        "AGENT_FAST_PLANNER_MODEL": "qwen3:4b",
                        "AGENT_DEEP_PLANNER_MODEL": "qwen3:4b",
                        "AGENT_RESPONSE_COMPOSER_MODEL": "qwen3:4b",
                        "AGENT_TOOL_RESULT_INTERPRETER_MODEL": "qwen3:4b",
                    },
                },
                "chromie-llm": {"image_id": "sha256:llm"},
                "chromie-asr": {"image_id": "sha256:asr"},
                "chromie-tts": {"image_id": "sha256:tts"},
            },
        },
        "qualification": {
            "source_clean": True,
            "deployment_complete": True,
            "release_qualified": False,
            "human_review_required": True,
        },
    }
    payload["identity_sha256"] = canonical_json_sha256(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def gateway_event(
    sid: str,
    conversation: str,
    admission: str,
    identity: str,
    refs=None,
    *,
    reflex_action: str = "continue",
    cancellation_scope: str = "none",
):
    return {
        "schema_version": 2,
        "event": "cognitive_gateway_admission",
        "sid": sid,
        "turn_id": sid,
        "conversation_id": conversation,
        "admission": admission,
        "reflex": {
            "action": reflex_action,
            "cancellation_scope": cancellation_scope,
        },
        "context_reference_types": list(refs or []),
        "run_identity": {"identity_sha256": identity, "complete": True},
    }


def runtime_event(
    sid: str,
    conversation: str,
    identity: str,
    *,
    lane: str,
    capabilities=None,
    goal_ids=None,
    targets=None,
):
    associations = []
    if targets:
        associations.append(
            {
                "association_id": f"assoc-{sid}",
                "relationship": "continue",
                "target_goal_ids": list(targets),
            }
        )
    return {
        "schema_version": 2,
        "event": "cognitive_runtime_resolution",
        "sid": sid,
        "turn_id": sid,
        "conversation_id": conversation,
        "run_identity": {"identity_sha256": identity, "complete": True},
        "status": "applied",
        "lane": lane,
        "core_interpretation": {"authority": "goal_driven_cognitive_core"},
        "terminal_plan": {
            "goal_ids": list(goal_ids or []),
            "capability_ids": list(capabilities or []),
        },
        "goal_association": {
            "associations": associations,
            "new_goals": [
                {"goal_id": goal_id} for goal_id in list(goal_ids or [])
            ] if not targets else [],
        },
    }


class CognitiveGatewayCoreQualificationTests(unittest.TestCase):
    def test_live_text_runner_bootstraps_generated_runtime_profile(self) -> None:
        def load_profile() -> None:
            os.environ.setdefault("ORCH_GOAL_ASSOCIATION_TIMEOUT_MS", "150000")
            os.environ.setdefault("ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS", "900000")
            os.environ.setdefault("OLLAMA_MODEL", "gemma4:12b")

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {}, clear=True),
            patch(
                "orchestrator.orchestrator.load_runtime_environment",
                side_effect=load_profile,
            ) as load_runtime_environment,
        ):
            args = argparse.Namespace(
                agent_url="http://127.0.0.1:8092",
                runtime_identity=Path(temp_dir) / "runtime-identity.json",
                speaker=False,
            )

            _configure_environment(args, Path(temp_dir))

            load_runtime_environment.assert_called_once_with()
            self.assertEqual(
                os.environ["ORCH_GOAL_ASSOCIATION_TIMEOUT_MS"], "150000"
            )
            self.assertEqual(
                os.environ["ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS"], "900000"
            )
            self.assertEqual(os.environ["OLLAMA_MODEL"], "gemma4:12b")
            self.assertEqual(os.environ["ORCH_AUDIO_INPUT_MODE"], "stdin")
            self.assertEqual(os.environ["ORCH_AUDIO_OUTPUT_MODE"], "discard")

    def build_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        identity_path = root / "runtime-identity.json"
        identity = write_identity(identity_path)
        digest = identity["identity_sha256"]
        events = [
            gateway_event("sid-ambient", "conv-ambient", "suppress", digest),
            gateway_event(
                "sid-stop",
                "conv-stop",
                "reflex_and_admit",
                digest,
                reflex_action="interrupt",
                cancellation_scope="current_interaction",
            ),
            gateway_event("sid-direct", "conv-direct", "admit", digest),
            runtime_event(
                "sid-direct", "conv-direct", digest, lane="chat", goal_ids=["goal-direct"]
            ),
            gateway_event("sid-self", "conv-self", "admit", digest),
            runtime_event(
                "sid-self", "conv-self", digest, lane="chat", goal_ids=["goal-self"]
            ),
            gateway_event("sid-weather-1", "conv-weather", "admit", digest),
            runtime_event(
                "sid-weather-1",
                "conv-weather",
                digest,
                lane="tool",
                capabilities=["chromie.weather.lookup"],
                goal_ids=["goal-weather"],
            ),
            {
                "schema_version": 2,
                "event": "cognitive_execution_outcome",
                "sid": "sid-weather-1",
                "turn_id": "sid-weather-1",
                "run_identity": {"identity_sha256": digest, "complete": True},
                "outcome_bundle": {"aggregate_status": "completed"},
            },
            gateway_event(
                "sid-weather-2",
                "conv-weather",
                "admit",
                digest,
                refs=["recent_tool_evidence"],
            ),
            runtime_event(
                "sid-weather-2",
                "conv-weather",
                digest,
                lane="chat",
                capabilities=[],
                targets=["goal-weather"],
            ),
        ]
        events_path = root / "cognitive-events.jsonl"
        events_path.write_text(
            "".join(json.dumps(item) + "\n" for item in events),
            encoding="utf-8",
        )
        def retained(turn_key: str, sid: str, text: str) -> dict:
            return {
                "turn_key": turn_key,
                "sid": sid,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "session_state": {
                    "scheduled_tts": 1,
                    "played_tts": 1,
                    "failed_tts": 0,
                    "skipped_tts": 0,
                    "workflow_events": [
                        {
                            "event": "capability_result",
                            "severity": "info",
                            "message": (
                                "capability_result: request_id=speech-fixture "
                                "capability_id=chromie.speak status=completed"
                            ),
                        }
                    ],
                },
            }

        summary = {
            "schema_version": 1,
            "qualification_id": "cognitive_gateway_core_entry_v1",
            "ok": True,
            "runtime_identity": {"identity_sha256": digest},
            "cognitive_events": str(events_path),
            "scenarios": [
                {
                    "scenario_id": "inactive_ambient_suppression",
                    "turns": [
                        retained(
                            "ambient",
                            "sid-ambient",
                            "The build server finished compiling at nine.",
                        )
                    ],
                },
                {
                    "scenario_id": "deterministic_stop_reflex",
                    "turns": [retained("stop", "sid-stop", "Stop.")],
                },
                {
                    "scenario_id": "direct_question_admission",
                    "turns": [
                        retained(
                            "direct_question",
                            "sid-direct",
                            "Chromie, what can you do?",
                        )
                    ],
                },
                {
                    "scenario_id": "natural_self_identity",
                    "turns": [
                        retained(
                            "self_identity",
                            "sid-self",
                            "你好，你是谁呀？",
                        )
                    ],
                },
                {
                    "scenario_id": "beijing_weather_tool_continuity",
                    "turns": [
                        retained(
                            "weather_initial",
                            "sid-weather-1",
                            "你好，今天北京天气热不热？",
                        ),
                        retained(
                            "weather_followup",
                            "sid-weather-2",
                            "那到底是热还是不热呢？",
                        ),
                    ],
                },
            ],
        }
        summary_path = root / "summary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        return identity_path, events_path, summary_path

    def test_live_text_qualification_passes_with_bound_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity_path, events_path, summary_path = self.build_fixture(root)
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary_path,
                runtime_identity_path=identity_path,
                cognitive_events_path=events_path,
                expected_chromie_revision="chromie-current",
                expected_soridormi_revision="soridormi-current",
            )
        self.assertFalse(report["passed"])
        self.assertTrue(report["qualification"]["live_text_target_validated"])
        self.assertFalse(report["qualification"]["issue_closure_eligible"])
        self.assertIn(
            "required source-bound MuJoCo summary is missing",
            report["errors"],
        )
        self.assertIn(
            "required active-goal cancellation summary is missing",
            report["errors"],
        )
        self.assertFalse(report["qualification"]["release_qualified"])

    def test_repeated_weather_lookup_fails_continuity_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity_path, events_path, summary_path = self.build_fixture(root)
            events = [json.loads(line) for line in events_path.read_text().splitlines()]
            for event in events:
                if event.get("sid") == "sid-weather-2" and event.get("event") == "cognitive_runtime_resolution":
                    event["terminal_plan"]["capability_ids"] = ["chromie.weather.lookup"]
            events_path.write_text(
                "".join(json.dumps(item) + "\n" for item in events),
                encoding="utf-8",
            )
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary_path,
                runtime_identity_path=identity_path,
                cognitive_events_path=events_path,
                expected_chromie_revision="chromie-current",
                expected_soridormi_revision="soridormi-current",
            )
        self.assertFalse(report["passed"])
        self.assertIn("forbidden repeated terminal capability", "\n".join(report["errors"]))

    def test_required_speech_turn_rejects_scheduled_but_skipped_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity_path, events_path, summary_path = self.build_fixture(root)
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            direct = next(
                item
                for item in manifest["scenarios"]
                if item["scenario_id"] == "direct_question_admission"
            )
            direct["turns"][0]["expect"]["require_delivered_speech"] = True
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            retained_direct = next(
                item
                for item in summary["scenarios"]
                if item["scenario_id"] == "direct_question_admission"
            )["turns"][0]
            retained_direct["session_state"] = {
                "scheduled_tts": 3,
                "played_tts": 0,
                "failed_tts": 0,
                "skipped_tts": 3,
                "workflow_events": [],
            }
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            report = verify(
                manifest_path=manifest_path,
                live_summary_path=summary_path,
                runtime_identity_path=identity_path,
                cognitive_events_path=events_path,
                expected_chromie_revision="chromie-current",
                expected_soridormi_revision="soridormi-current",
            )

        self.assertFalse(report["live_text"]["passed"])
        self.assertIn("required speech delivery", "\n".join(report["errors"]))

    def test_runtime_agent_fingerprint_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity_path, events_path, summary_path = self.build_fixture(root)
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            identity["deployment"]["service_images"]["chromie-agent"][
                "effective_runtime"
            ]["CHROMIE_RUNTIME_ENV_FINGERPRINT"] = "wrong"
            identity.pop("identity_sha256")
            identity["identity_sha256"] = canonical_json_sha256(identity)
            identity_path.write_text(json.dumps(identity), encoding="utf-8")
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary_path,
                runtime_identity_path=identity_path,
                cognitive_events_path=events_path,
                expected_chromie_revision="chromie-current",
                expected_soridormi_revision="soridormi-current",
            )
        self.assertFalse(report["passed"])
        self.assertIn(
            "running Agent runtime fingerprint does not match",
            "\n".join(report["errors"]),
        )

    def test_complete_bound_bundle_makes_issue_closure_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity_path, events_path, summary_path = self.build_fixture(root)
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            digest = identity["identity_sha256"]
            mujoco_path = root / "mujoco-summary.json"
            mujoco_path.write_text(
                json.dumps(
                    {
                        "cognitive_runtime": {
                            "terminal_plan": {
                                "steps": [
                                    {"capability_id": "soridormi.walk_velocity"},
                                    {"capability_id": "soridormi.nod_yes"},
                                    {"capability_id": "soridormi.turn_in_place"},
                                ]
                            }
                        },
                        "provenance": {
                            "runtime_identity": {
                                "identity_sha256": digest,
                                "complete": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            cancellation_events = root / "cancellation-events.jsonl"
            cancellation_events.write_text(
                json.dumps(
                    gateway_event(
                        "sid-active-stop",
                        "conv-active-cancel",
                        "reflex_and_admit",
                        digest,
                        reflex_action="interrupt",
                        cancellation_scope="current_interaction",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            cancellation_path = root / "cancellation-summary.json"
            cancellation_path.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "text": "Walk forward at 0.2 meters per second for 20 seconds.",
                        "interaction_response": {
                            "interaction_id": "interaction-active-cancel"
                        },
                        "interrupt": {
                            "text": "Stop.",
                            "text_sha256": hashlib.sha256(
                                b"Stop."
                            ).hexdigest(),
                            "sid": "sid-active-stop",
                            "provider_observation_before_interrupt": {
                                "requests": [
                                    {
                                        "interaction_id": "interaction-active-cancel",
                                        "request_id": "request-walk",
                                        "capability_id": "soridormi.walk_velocity",
                                        "provider_id": "soridormi.mcp",
                                        "source_goal_ids": ["goal-walk"],
                                        "provider_started": True,
                                        "task_done": False,
                                    }
                                ]
                            },
                        },
                        "execution": {
                            "status": "cancelled",
                            "results": [
                                {
                                    "request_id": "request-walk",
                                    "capability_id": "soridormi.walk_velocity",
                                    "status": "cancelled",
                                    "reason_code": "cancelled_current_interaction",
                                }
                            ],
                        },
                        "status_before": {
                            "mode": "sim",
                            "backend": "runtime",
                            "safe_idle": True,
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                        "status_after": {
                            "mode": "sim",
                            "backend": "runtime",
                            "safe_idle": True,
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                        "cognitive_events": str(cancellation_events),
                        "provenance": {
                            "chromie": {
                                "revision": "chromie-current",
                                "dirty": False,
                            },
                            "soridormi": {
                                "upstream_revision": "soridormi-current",
                                "checkout_revision": "soridormi-current",
                                "checkout_dirty": False,
                                "source_binding": "endpoint_reported_revision",
                                "endpoint_revision": "soridormi-current",
                            },
                            "semantic_runtime": {
                                "path": "goal_driven_cognitive_runtime",
                                "configured_cognitive_runtime_mode": "apply",
                                "cognitive_runtime_selected_for_route": True,
                            },
                            "runtime_identity": {
                                "identity_sha256": digest,
                                "complete": True,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            review_path = root / "human-review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "qualification_id": "cognitive_gateway_core_entry_v1",
                        "runtime_identity_sha256": digest,
                        "artifact_sha256": {
                            "live_summary": hashlib.sha256(
                                summary_path.read_bytes()
                            ).hexdigest(),
                            "mujoco_summary": hashlib.sha256(
                                mujoco_path.read_bytes()
                            ).hexdigest(),
                            "cancellation_summary": hashlib.sha256(
                                cancellation_path.read_bytes()
                            ).hexdigest(),
                        },
                        "reviewer": "reviewer-one",
                        "reviewed_at": "2026-07-27T12:00:00+00:00",
                        "decision": "approve",
                        "checks": {
                            "gateway_attention_quality": "pass",
                            "direct_answer_quality": "pass",
                            "tool_continuity_quality": "pass",
                            "cancellation_feedback_quality": "pass",
                            "no_internal_contract_leakage": "pass",
                            "person_identity_consistency": "pass",
                            "age_appropriate_natural_voice": "pass",
                            "direct_answer_before_detail": "pass",
                            "no_internal_workflow_narration": "pass",
                            "greeting_naturalness_and_context_fit": "pass",
                            "safe_read_speech_tool_parallelism": "pass",
                            "recoverable_lookup_argument_binding": "pass",
                            "tool_result_pointer_grounding": "pass",
                        },
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "scripts.verify_cognitive_gateway_core_qualification._simulator_report",
                return_value={
                    "target_validated": True,
                    "completed_soridormi_results": 3,
                },
            ):
                report = verify(
                    manifest_path=MANIFEST,
                    live_summary_path=summary_path,
                    runtime_identity_path=identity_path,
                    cognitive_events_path=events_path,
                    mujoco_summary_path=mujoco_path,
                    cancellation_summary_path=cancellation_path,
                    human_review_path=review_path,
                    expected_chromie_revision="chromie-current",
                    expected_soridormi_revision="soridormi-current",
                )
        self.assertTrue(report["passed"], report["errors"])
        self.assertTrue(
            report["qualification"]["active_goal_cancellation_target_validated"]
        )
        self.assertTrue(report["qualification"]["human_review_approved"])
        self.assertTrue(report["qualification"]["issue_closure_eligible"])
        self.assertFalse(report["qualification"]["release_qualified"])



if __name__ == "__main__":
    unittest.main()
