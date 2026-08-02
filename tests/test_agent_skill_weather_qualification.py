from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_agent_skill_weather_qualification import verify

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "agent_skill_weather_qualification_v1.json"
)


def _provenance(skill_id: str, role: str = "fast_planner") -> dict:
    token = skill_id.rsplit(".", 1)[-1]
    return {
        "selection_id": f"selection-{token}",
        "disclosure_id": f"disclosure-{token}",
        "disclosure_digest": "a" * 64,
        "selected_by_agent_role": role,
        "agent_skill_id": skill_id,
        "version": "1.0.0",
        "projection": role,
        "content_digest": "b" * 64,
        "projection_digest": "c" * 64,
        "relevant_goal_ids": ["goal-weather"],
        "selection_rationale": "Relevant method.",
        "selection_confidence": 0.95,
    }


def _gateway(sid: str, identity: str) -> dict:
    return {
        "schema_version": 2,
        "event": "cognitive_gateway_admission",
        "sid": sid,
        "turn_id": sid,
        "admission": "admit",
        "run_identity": {"identity_sha256": identity, "complete": True},
    }


def _runtime(
    sid: str,
    identity: str,
    *,
    lane: str,
    capabilities: list[str],
    goal_ids: list[str],
    targets: list[str] | None = None,
    skills: list[str] | None = None,
    binding_location: str | None = None,
) -> dict:
    new_goals = []
    if not targets:
        for item in goal_ids:
            goal = {"goal_id": item}
            if binding_location is not None:
                goal["object"] = {
                    "bindings": {
                        "location": {
                            "name": "location",
                            "entity_type": "place",
                            "value": binding_location,
                            "confidence": 1.0,
                        }
                    }
                }
            new_goals.append(goal)
    return {
        "schema_version": 2,
        "event": "cognitive_runtime_resolution",
        "sid": sid,
        "turn_id": sid,
        "run_identity": {"identity_sha256": identity, "complete": True},
        "status": "applied",
        "lane": lane,
        "terminal_plan": {
            "plan_id": f"plan-{sid}",
            "goal_ids": goal_ids,
            "capability_ids": capabilities,
            "selected_agent_skills": [
                _provenance(item) for item in (skills or [])
            ],
        },
        "composition": {
            "status": "resolved",
            "safe_read_semantic_review": (
                {
                    "attempted": True,
                    "succeeded": True,
                    "strategy": "model_owned_pre_evidence_speech_review",
                }
                if "chromie.weather.lookup" in capabilities
                else None
            ),
        },
        "goal_association": {
            "associations": (
                [
                    {
                        "association_id": f"association-{sid}",
                        "relationship": "continue",
                        "target_goal_ids": targets,
                    }
                ]
                if targets
                else []
            ),
            "new_goals": new_goals,
        },
    }


def _outcome(
    sid: str,
    identity: str,
    location: str,
    *,
    request_location: str,
    provider_query: str = "neixiang",
    provider_admin1: str = "Henan",
) -> dict:
    return {
        "schema_version": 2,
        "event": "cognitive_execution_outcome",
        "sid": sid,
        "turn_id": sid,
        "run_identity": {"identity_sha256": identity, "complete": True},
        "outcome_bundle": {
            "aggregate_status": "completed",
            "evidence": [
                {
                    "capability_id": "chromie.weather.lookup",
                    "status": "completed",
                    "provider_id": "chromie.local.weather",
                    "metadata": {
                        "request_args": {"location": request_location},
                        "provider_execution": {
                            "provider_resolution": {
                                "requested_location": request_location,
                                "provider_query": provider_query,
                                "matched_location": location,
                                "matched_admin1": provider_admin1,
                                "matched_country": "China",
                            }
                        },
                    },
                    "observation": {
                        "status": "available",
                        "schema_validated": True,
                        "data": {
                            "location": location,
                            "source": "Open-Meteo",
                            "condition": "No rain",
                        },
                    },
                }
            ],
        },
    }


def _retained(turn_key: str, sid: str, text: str) -> dict:
    return {
        "turn_key": turn_key,
        "sid": sid,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


class AgentSkillWeatherQualificationTests(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        bad_location: bool = False,
        omit_base: bool = False,
        bad_provider_query: bool = False,
        bad_canonical_location: bool = False,
        evidence_on_correction: bool = False,
    ):
        identity_path = root / "runtime-identity.json"
        identity = {
            "schema_version": 1,
            "identity_sha256": "identity-digest",
            "chromie": {"revision": "chromie-current", "dirty": False},
            "qualification": {"source_clean": True, "deployment_complete": True},
        }
        identity_path.write_text(json.dumps(identity), encoding="utf-8")
        summary_path = root / "summary.json"
        summary = {
            "schema_version": 1,
            "qualification_id": "chromie.agent-skill-weather.source-bound.v1",
            "ok": True,
            "runtime_identity": {"identity_sha256": "identity-digest"},
            "cognitive_events": str(root / "cognitive-events.jsonl"),
            "scenarios": [
                {
                    "scenario_id": "neixiang_weather_and_exact_followup",
                    "turns": [
                        _retained("weather_initial", "sid-weather-1", "河南省内乡县现在下雨了吗？"),
                        _retained(
                            "weather_followup",
                            "sid-weather-2",
                            "刚才那个天气结果，简单告诉我现在有没有下雨。",
                        ),
                    ],
                },
                {
                    "scenario_id": "chongqing_correction_to_neixiang_reference",
                    "turns": [
                        _retained("chongqing_initial", "sid-correction-1", "今天重庆热不热？"),
                        _retained(
                            "location_correction",
                            "sid-correction-2",
                            "不是重庆，我说的是内乡。",
                        ),
                        _retained(
                            "resolved_reference_weather",
                            "sid-correction-3",
                            "今天那边下雨了吗？",
                        ),
                    ],
                },
            ],
        }
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        skills = ["chromie.weather-information"]
        if not omit_base:
            skills.insert(0, "chromie.grounded-external-information")
        events = [
            _gateway("sid-weather-1", "identity-digest"),
            _runtime(
                "sid-weather-1",
                "identity-digest",
                lane="tool",
                capabilities=["chromie.weather.lookup"],
                goal_ids=["goal-weather"],
                skills=skills,
            ),
            _outcome(
                "sid-weather-1",
                "identity-digest",
                "内乡县",
                request_location=(
                    "河南省南阳市" if bad_canonical_location else "河南省内乡县"
                ),
                provider_query=("henan neixiang" if bad_provider_query else "neixiang"),
            ),
            _gateway("sid-weather-2", "identity-digest"),
            _runtime(
                "sid-weather-2",
                "identity-digest",
                lane="chat",
                capabilities=[],
                goal_ids=["goal-weather"],
                targets=["goal-weather"],
            ),
            _gateway("sid-correction-1", "identity-digest"),
            _runtime(
                "sid-correction-1",
                "identity-digest",
                lane="tool",
                capabilities=["chromie.weather.lookup"],
                goal_ids=["goal-chongqing"],
                skills=skills,
            ),
            _gateway("sid-correction-2", "identity-digest"),
            _runtime(
                "sid-correction-2",
                "identity-digest",
                lane="tool" if evidence_on_correction else "chat",
                capabilities=(
                    ["chromie.weather.lookup"] if evidence_on_correction else []
                ),
                goal_ids=["goal-neixiang-correction"],
                skills=skills if evidence_on_correction else None,
                binding_location="内乡",
            ),
            *(
                [
                    _outcome(
                        "sid-correction-2",
                        "identity-digest",
                        "河南省内乡县",
                        request_location="内乡",
                    )
                ]
                if evidence_on_correction
                else []
            ),
            _gateway("sid-correction-3", "identity-digest"),
            _runtime(
                "sid-correction-3",
                "identity-digest",
                lane="chat" if evidence_on_correction else "tool",
                capabilities=(
                    [] if evidence_on_correction else ["chromie.weather.lookup"]
                ),
                goal_ids=["goal-neixiang-correction"],
                targets=["goal-neixiang-correction"],
                skills=skills,
            ),
            *(
                []
                if evidence_on_correction
                else [
                    _outcome(
                        "sid-correction-3",
                        "identity-digest",
                        "重庆" if bad_location else "河南省内乡县",
                        request_location="内乡",
                        provider_query=(
                            "henan neixiang" if bad_provider_query else "neixiang"
                        ),
                    )
                ]
            ),
        ]
        events_path = root / "cognitive-events.jsonl"
        events_path.write_text(
            "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8"
        )
        return identity_path, summary_path, events_path

    def _approved_review(
        self,
        root: Path,
        identity: Path,
        summary: Path,
        events: Path,
    ) -> Path:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        review = {
            "schema_version": 1,
            "qualification_id": manifest["qualification_id"],
            "reviewer": "reviewer",
            "reviewed_at": "2026-07-30T00:00:00+00:00",
            "decision": "approved",
            "artifact_sha256": {
                "runtime_identity": digest(identity),
                "live_summary": digest(summary),
                "cognitive_events": digest(events),
            },
            "checks": {item: "approved" for item in manifest["human_review_checks"]},
            "findings": [],
        }
        path = root / "human-review.json"
        path.write_text(json.dumps(review), encoding="utf-8")
        return path

    def test_complete_source_bound_bundle_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root)
            review = self._approved_review(root, identity, summary, events)
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                human_review_path=review,
                expected_chromie_revision="chromie-current",
            )
        self.assertTrue(report["passed"])
        self.assertTrue(report["qualification"]["track_closure_eligible"])
        self.assertFalse(report["qualification"]["release_qualified"])

    def test_automatic_evidence_stays_pending_without_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root)
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(report["passed"])
        self.assertTrue(
            report["qualification"]["live_agent_skill_selection_validated"]
        )
        self.assertFalse(report["qualification"]["human_review_approved"])

    def test_missing_grounded_base_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root, omit_base=True)
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(
            report["qualification"]["live_agent_skill_selection_validated"]
        )
        self.assertIn("do not contain", "\n".join(report["errors"]))

    def test_chongqing_result_cannot_satisfy_neixiang_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root, bad_location=True)
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(
            report["qualification"]["provider_backed_weather_validated"]
        )
        self.assertIn("forbidden locality", "\n".join(report["errors"]))

    def test_correction_turn_weather_can_ground_reference_followup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(
                root, evidence_on_correction=True
            )
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertTrue(
            report["qualification"]["live_agent_skill_selection_validated"]
        )
        self.assertTrue(
            report["qualification"]["provider_backed_weather_validated"]
        )

    def test_stale_chongqing_fast_speech_fails_reference_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root)
            summary_payload = json.loads(summary.read_text(encoding="utf-8"))
            reference_turn = summary_payload["scenarios"][1]["turns"][2]
            reference_turn["session_state"] = {
                "workflow_events": [
                    {
                        "event": "tts_schedule",
                        "message": (
                            "tts_schedule: order=0 chars=19 text='好的，我马上查一下"
                            "今天重庆的天气情况。'"
                        ),
                    }
                ]
            }
            summary.write_text(json.dumps(summary_payload), encoding="utf-8")
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(
            report["qualification"]["live_agent_skill_selection_validated"]
        )
        self.assertIn("user-visible speech", "\n".join(report["errors"]))

    def test_provider_query_must_be_the_provider_native_neixiang_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root, bad_provider_query=True)
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(
            report["qualification"]["provider_backed_weather_validated"]
        )
        self.assertIn("provider weather query", "\n".join(report["errors"]))

    def test_weather_turn_requires_model_owned_safe_read_review_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root)
            payloads = [
                json.loads(line)
                for line in events.read_text(encoding="utf-8").splitlines()
            ]
            for payload in payloads:
                if (
                    payload.get("sid") == "sid-weather-1"
                    and payload.get("event") == "cognitive_runtime_resolution"
                ):
                    payload["composition"]["safe_read_semantic_review"] = None
                    break
            events.write_text(
                "".join(json.dumps(item) + "\n" for item in payloads),
                encoding="utf-8",
            )
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(
            report["qualification"]["live_agent_skill_selection_validated"]
        )
        self.assertIn("semantic review evidence is missing", "\n".join(report["errors"]))

    def test_required_runtime_turn_must_finish_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(root)
            payloads = [
                json.loads(line)
                for line in events.read_text(encoding="utf-8").splitlines()
            ]
            for payload in payloads:
                if (
                    payload.get("sid") == "sid-weather-2"
                    and payload.get("event") == "cognitive_runtime_resolution"
                ):
                    payload["status"] = "error"
                    payload["lane"] = "unsupported"
                    break
            events.write_text(
                "".join(json.dumps(item) + "\n" for item in payloads),
                encoding="utf-8",
            )
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )

        self.assertFalse(
            report["qualification"]["live_agent_skill_selection_validated"]
        )
        self.assertIn(
            "runtime status 'error' is not 'applied'",
            "\n".join(report["errors"]),
        )

    def test_canonical_location_is_not_rewritten_to_provider_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, summary, events = self._fixture(
                root, bad_canonical_location=True
            )
            report = verify(
                manifest_path=MANIFEST,
                live_summary_path=summary,
                runtime_identity_path=identity,
                cognitive_events_path=events,
                expected_chromie_revision="chromie-current",
            )
        self.assertFalse(
            report["qualification"]["provider_backed_weather_validated"]
        )
        self.assertIn(
            "canonical weather request location", "\n".join(report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
