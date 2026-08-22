from __future__ import annotations

import unittest
from types import MethodType

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.confirmation import ConfirmationDialogue
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse


class _AgentClient:
    def __init__(self) -> None:
        self.request: CognitiveWorkRequest | None = None

    async def resolve_goal_association(self, _session, *, request, timeout_ms=None):
        self.request = request
        goal_ids = request.context["pending_confirmation_scope"]["goal_ids"]
        return GoalAssociationResolution.model_validate(
            {"resolution_status": "resolved",
                "turn_id": "confirmation-reply",
                "associations": [
                    {
                        "association_id": "confirmation-association",
                        "relationship": "confirm",
                        "target_goal_ids": goal_ids,
                        "confidence": 0.99,
                    }
                ],
                "confidence": 0.99,
            }
        )


class ConfirmationGoalAssociationContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_uses_current_cognitive_work_request_contract(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.agent_client = _AgentClient()
        assistant.goal_association_timeout_ms = 2500
        assistant.build_context = lambda _sid: {"history": [{"role": "user", "text": "old"}]}
        assistant.session_log = lambda *_args, **_kwargs: None
        assistant._looks_zh = lambda _text: False

        async def get_http_session(_self):
            return object()

        assistant.get_http_session = MethodType(get_http_session, assistant)
        response = InteractionResponse(
            interaction_id="interaction-confirm",
            metadata={
                "confirmation_prompt": "Can I do that now?",
                "confirmation_prompt_source": "planner_wording_runtime_validated",
            },
            capabilities=[
                {
                    "request_id": "request-1",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1},
                    "metadata": {"source_goal_ids": ["goal-1"]},
                    "requires_confirmation": True,
                }
            ],
        )
        pending = ConfirmationDialogue(clock=lambda: 100.0).prepare(
            response,
            confirmed_request_ids={"request-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        meaning = await assistant._resolve_pending_confirmation_meaning(
            "yes",
            session_id="sid-1",
            pending=pending,
        )

        self.assertEqual(meaning, "confirm")
        request = assistant.agent_client.request
        self.assertIsInstance(request, CognitiveWorkRequest)
        assert request is not None
        self.assertEqual(request.text, "yes")
        self.assertEqual(request.responsibilities[0].outcome, "yes")
        self.assertEqual(
            request.context["pending_confirmation_scope"],
            {"confirmation_id": pending.confirmation_id, "goal_ids": ["goal-1"]},
        )
        self.assertNotIn("route_decision", request.model_dump(mode="json"))
