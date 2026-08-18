from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from orchestrator.runtime.cognitive_runtime import (
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from shared.chromie_contracts.social_attention import (
    SocialAttentionActivityAnchor,
    SocialAttentionActivityRealization,
    SocialAttentionPlan,
)


class _SocialClient:
    async def resolve_social_attention(self, _session, **_kwargs):
        return SocialAttentionPlan(decision="none", reason="No cue is needed.")


class _SocialAdapter:
    social_attention_mode = "on"

    @staticmethod
    def recent_auxiliary_behavior_evidence(_sid):
        return []

    @staticmethod
    async def execute_social_attention_event(**_kwargs):
        return {
            "status": "not_executed",
            "decision": "none",
            "materialized_count": 0,
            "request_ids": [],
            "reasons": ["planner_selected_none"],
        }


class SocialAttentionAttachmentContractTests(unittest.IsolatedAsyncioTestCase):
    def _coordinator(self, events):
        def sink(_sid, **payload):
            events.append(payload)

        return GoalDrivenRuntimeCoordinator(
            agent_client=_SocialClient(),
            adapter=_SocialAdapter(),
            policy=CognitiveRuntimePolicy(mode="apply"),
            workflow_stage_sink=sink,
        )

    async def test_opportunity_is_background_and_attached_to_main_activity(self) -> None:
        events = []
        coordinator = self._coordinator(events)
        coordinator._drain_social_attention_events = lambda _key: asyncio.sleep(0)
        activity = SocialAttentionActivityAnchor(
            activity_id="greeting",
            phase="ready",
            summary="Say hello.",
            realization=SocialAttentionActivityRealization(
                execution_lanes=["vocal"],
                vocal_modes=["speech"],
                execution_item_ids=["speech-greeting"],
            ),
        )

        coordinator._queue_social_attention_for_activity(
            object(),
            activity=activity,
            text="hello",
            sid="session",
            turn_id="turn",
            language="en-US",
            context={},
            history=[],
        )
        await asyncio.sleep(0)

        queued = next(item for item in events if item["stage"] == "social_attention_opportunity")
        self.assertEqual(queued["status"], "queued")
        self.assertTrue(queued["metadata"]["attached_to_main_activity"])
        self.assertFalse(queued["output_payload"]["blocks_main_activity"])

    async def test_none_decision_and_execution_are_retained(self) -> None:
        events = []
        coordinator = self._coordinator(events)
        activity = SocialAttentionActivityAnchor(
            activity_id="answer",
            phase="ready",
            summary="Answer the user.",
            realization=SocialAttentionActivityRealization(
                execution_lanes=["vocal"],
                vocal_modes=["speech"],
                execution_item_ids=["speech-answer"],
            ),
        )

        outcome = await coordinator._run_social_attention_event(
            object(),
            event="primary_activity_ready",
            text="question",
            sid="session",
            turn_id="turn",
            language="en-US",
            context={"social_attention_primary_activity": activity.model_dump(mode="json")},
            history=[],
        )

        self.assertEqual(outcome["decision"], "none")
        stages = [item["stage"] for item in events]
        self.assertIn("social_attention_decision", stages)
        self.assertIn("social_attention_execution", stages)


if __name__ == "__main__":
    unittest.main()
