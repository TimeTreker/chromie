import unittest
from dataclasses import dataclass, field
from typing import Any

from agent.app.social_attention import (
    SocialAttentionContextBuilder,
    SocialAttentionPlanner,
    SocialAttentionServices,
)
from shared.chromie_contracts.social_attention import SocialAttentionRequest


@dataclass
class _Capability:
    capability_id: str
    behavior_domains: list[str] = field(default_factory=lambda: ["social_attention"])
    available: bool = True
    interaction_executable: bool = True
    requires_confirmation: bool = False
    can_run_parallel: bool = True
    parallel_metadata_declared: bool = True
    input_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "behavior_domains": list(self.behavior_domains),
            "available": self.available,
            "interaction_executable": self.interaction_executable,
            "requires_confirmation": self.requires_confirmation,
            "can_run_parallel": self.can_run_parallel,
            "parallel_metadata_declared": self.parallel_metadata_declared,
            "input_schema": dict(self.input_schema),
            "metadata": dict(self.metadata),
        }


class _Catalog:
    def __init__(self, items: list[_Capability]) -> None:
        self.items = items

    def entries(self) -> list[_Capability]:
        return list(self.items)

    async def get_capability(self, capability_id: str) -> _Capability | None:
        return next((item for item in self.items if item.capability_id == capability_id), None)


class _Ollama:
    timeout_ms = 500

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        return dict(self.result)


def _request(*, context: dict[str, Any] | None = None) -> SocialAttentionRequest:
    return SocialAttentionRequest.model_validate(
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "event": "primary_activity_ready",
            "primary_activity": {
                "activity_id": "greet-user",
                "phase": "ready",
                "summary": "greet the user",
                "goal_ids": ["goal-1"],
                "realization": {"execution_lanes": ["vocal"], "vocal_modes": ["speech"]},
            },
            "text": "hello",
            "language": "en-US",
            "context": context or {},
        }
    )


class SocialAttentionCurrentArchitectureTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_builder_projects_only_eligible_auxiliary_candidates(self) -> None:
        catalog = _Catalog(
            [
                _Capability("soridormi.blink_eyes"),
                _Capability("soridormi.nod_yes", requires_confirmation=True),
                _Capability("soridormi.gaze", input_schema={"yaw_rad": {"type": "number"}}),
                _Capability("soridormi.walk", behavior_domains=["locomotion"]),
            ]
        )
        request = _request(
            context={
                "mind": {"social_interaction_style": {"owner_approved": True, "tone": "gentle"}},
                "recent_auxiliary_behavior_evidence": [{"id": i} for i in range(20)],
                "social_attention_interaction_state": {"primary_capability_ids": ["soridormi.walk"]},
                "perceived_user_target": {"target_ref": "user", "confidence": 0.9},
            }
        )
        services = SocialAttentionServices(capability_catalog=catalog)
        await SocialAttentionContextBuilder(services).prepare(request)

        self.assertEqual(
            [item["capability_id"] for item in request.context["social_attention_candidates"]],
            ["soridormi.blink_eyes"],
        )
        self.assertEqual(request.context["social_interaction_style"]["tone"], "gentle")
        self.assertEqual(len(request.context["recent_auxiliary_behavior_evidence"]), 12)
        self.assertTrue(request.context["social_attention_target_evidence"]["available"])

    async def test_off_mode_exposes_policy_but_no_candidates(self) -> None:
        request = _request()
        services = SocialAttentionServices(
            social_attention_mode="off",
            capability_catalog=_Catalog([_Capability("soridormi.blink_eyes")]),
        )
        await SocialAttentionContextBuilder(services).prepare(request)
        self.assertFalse(request.context["social_attention_policy"]["planning_enabled"])
        self.assertNotIn("social_attention_candidates", request.context)

    async def test_planner_is_activity_scoped_and_candidate_constrained(self) -> None:
        client = _Ollama(
            {
                "decision": "express",
                "target": {"target_ref": "user", "source": "conversation_context", "confidence": 0.8},
                "behaviors": [{"capability_id": "soridormi.blink_eyes", "args": {}, "timing": "parallel"}],
                "confidence": 0.8,
                "reason": "subtle acknowledgement",
            }
        )
        services = SocialAttentionServices(social_attention_ollama=client)
        request = _request(
            context={"social_attention_candidates": [{"capability_id": "soridormi.blink_eyes"}]}
        )
        plan = await SocialAttentionPlanner(services).plan(request)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.behaviors[0].capability_id, "soridormi.blink_eyes")
        call = client.calls[0]
        self.assertIn("greet the user", call["prompt"])
        behavior_schema = call["response_format"]["$defs"]["SocialAttentionBehavior"]
        self.assertEqual(
            behavior_schema["properties"]["capability_id"]["enum"],
            ["soridormi.blink_eyes"],
        )

    async def test_planner_failure_is_fail_soft(self) -> None:
        client = _Ollama(RuntimeError("model unavailable"))
        request = _request(
            context={"social_attention_candidates": [{"capability_id": "soridormi.blink_eyes"}]}
        )
        plan = await SocialAttentionPlanner(
            SocialAttentionServices(social_attention_ollama=client)
        ).plan(request)
        self.assertIsNone(plan)
        self.assertEqual(request.context["social_attention_failure"]["stage"], "social_attention")


if __name__ == "__main__":
    unittest.main()
