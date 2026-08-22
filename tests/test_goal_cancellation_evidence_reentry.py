from __future__ import annotations

import asyncio
import unittest

from agent.app.planner_context import goal_cancellation_evidence_reentry_goal_ids
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.confirmation import ConfirmationDialogue
from orchestrator.runtime.named_goal_cancellation import _build_confirmation_remainder
from shared.chromie_contracts.control import GoalCancellationEvidence
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.plan import CanonicalPlan


class GoalCancellationEvidenceReentryTests(unittest.TestCase):
    def test_evidence_binding_admits_only_exact_referenced_goal_scope(self) -> None:
        evidence = GoalCancellationEvidence.create(
            source_turn_id="turn-cancel",
            target_goal_ids=["goal-a"],
            status="cancelled",
            goal_state_reconciled=True,
            confirmation_state_reconciled=True,
            reason_code="cancelled",
        )
        context = {
            "trusted_goal_cancellation_evidence": [evidence.model_dump(mode="json")],
            "goal_cancellation_reentry": {
                "source_goal_ids": ["goal-a"],
                "evidence_refs": [evidence.evidence_id],
            },
        }
        self.assertEqual(
            goal_cancellation_evidence_reentry_goal_ids(context),
            {"goal-a"},
        )
        context["goal_cancellation_reentry"]["evidence_refs"] = ["wrong"]
        self.assertEqual(goal_cancellation_evidence_reentry_goal_ids(context), set())

    def test_cancelling_one_confirmation_goal_revokes_whole_token_without_host_remainder(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        response = InteractionResponse(
            interaction_id="interaction-confirm",
            capabilities=[
                {
                    "request_id": "request-a",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                    "requires_confirmation": True,
                    "metadata": {"source_goal_ids": ["goal-a"]},
                },
                {
                    "request_id": "request-b",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "requires_confirmation": True,
                    "metadata": {"source_goal_ids": ["goal-b"]},
                },
            ],
            metadata={
                "confirmation_prompt": "Can I do those now?",
                "confirmation_prompt_source": "planner_wording_runtime_validated",
            },
        )
        pending = dialogue.begin(
            response,
            confirmed_request_ids={"request-a", "request-b"},
            origin_session_id="sid",
            conversation_id="conversation",
        )

        replacement, transition = _build_confirmation_remainder(
            confirmation_dialogue=dialogue,
            target_goal_ids={"goal-a"},
        )

        self.assertIsNone(replacement)
        self.assertEqual(transition["old_confirmation_id"], pending.confirmation_id)
        self.assertTrue(transition["revoked_entire_confirmation"])
        self.assertEqual(transition["released_confirmation_goal_ids"], ["goal-b"])
        self.assertIsNone(transition["replacement"])
        self.assertNotIn("replacement_confirmation_prompt", transition)

    def test_cancellation_reentry_delegates_to_existing_planner_state_entry(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        captured = {}

        async def state_reentry(**kwargs):
            captured.update(kwargs)
            return InteractionResponse(
                speech=[{"text": "Okay, that one is stopped.", "timing": "immediate"}],
                metadata={"source": "planner"},
            )

        assistant._planner_state_reentry_response = state_reentry
        evidence = GoalCancellationEvidence.create(
            source_turn_id="turn-cancel",
            target_goal_ids=["goal-a"],
            status="cancelled",
            goal_state_reconciled=True,
            confirmation_state_reconciled=True,
            reason_code="cancelled",
        )
        plan = CanonicalPlan.model_validate(
            {
                "plan_id": "plan-a",
                "planner_tier": "fast",
                "disposition": "respond",
                "coverage": "complete",
                "confidence": 0.95,
                "goal_ids": ["goal-a", "goal-b"],
                "response_text": "Prior planner response.",
                "steps": [],
                "goal_outcomes": [
                    {
                        "goal_id": "goal-a",
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "Prior response for A.",
                    },
                    {
                        "goal_id": "goal-b",
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "Prior response for B.",
                    },
                ],
            }
        )

        result = asyncio.run(
            assistant._planner_state_reentry_response(
                source_response=InteractionResponse(metadata={"source": "planner"}),
                canonical_plan=plan,
                user_request="Cancel the nod.",
                language="en-US",
                goal_ids=["goal-a", "goal-b"],
                evidence_goal_ids=["goal-a"],
                evidence_refs=[evidence.evidence_id],
                session_id="sid",
                phase="goal_cancellation_reentry",
                context_updates={
                    "trusted_goal_cancellation_evidence": [
                        evidence.model_dump(mode="json")
                    ],
                    "goal_cancellation_reentry": {
                        "phase": "goal_cancellation_reentry",
                        "source_goal_ids": ["goal-a"],
                        "evidence_refs": [evidence.evidence_id],
                        "planner_authority": "planner",
                    },
                },
                fast_workflow_stage="fast_planner_goal_cancellation_reentry",
                deep_workflow_stage="planner_deep_pass_goal_cancellation_reentry",
                response_source="fast_planner_goal_cancellation_reentry",
            )
        )

        self.assertIsNotNone(result)
        self.assertEqual(captured["goal_ids"], ["goal-a", "goal-b"])
        self.assertEqual(captured["evidence_goal_ids"], ["goal-a"])
        self.assertEqual(
            captured["context_updates"]["trusted_goal_cancellation_evidence"][0]["status"],
            "cancelled",
        )
        self.assertEqual(
            captured["response_source"],
            "fast_planner_goal_cancellation_reentry",
        )


if __name__ == "__main__":
    unittest.main()
