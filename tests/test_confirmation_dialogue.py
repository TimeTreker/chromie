from __future__ import annotations

import unittest

from orchestrator.runtime.confirmation import (
    ConfirmationDialogue,
    confirmation_meaning_from_goal_association,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse


def _response() -> InteractionResponse:
    return InteractionResponse(
        interaction_id="interaction-confirm",
        skills=[
            {
                "request_id": "nod-1",
                "skill_id": "soridormi.nod_yes",
                "args": {"count": 2},
                "requires_confirmation": True,
            }
        ],
    )


class ConfirmationDialogueTests(unittest.TestCase):
    def test_goal_association_confirmation_requires_exact_pending_scope(self) -> None:
        def resolution(relationship: str, goal_ids: list[str]) -> GoalAssociationResolution:
            return GoalAssociationResolution.model_validate(
                {
                    "turn_id": "turn-confirm",
                    "associations": [
                        {
                            "association_id": "assoc-confirm",
                            "relationship": relationship,
                            "target_goal_ids": goal_ids,
                            "confidence": 0.99,
                        }
                    ],
                    "confidence": 0.99,
                }
            )

        pending = {"goal-walk", "goal-blink"}

        self.assertEqual(
            confirmation_meaning_from_goal_association(
                resolution("confirm", ["goal-walk", "goal-blink"]),
                pending_goal_ids=pending,
            ),
            "confirm",
        )
        self.assertEqual(
            confirmation_meaning_from_goal_association(
                resolution("reject", ["goal-walk", "goal-blink"]),
                pending_goal_ids=pending,
            ),
            "reject",
        )
        self.assertEqual(
            confirmation_meaning_from_goal_association(
                resolution("confirm", ["goal-walk"]),
                pending_goal_ids=pending,
            ),
            "ambiguous",
        )

    def test_begin_uses_semantic_alternative_prompt_override(self) -> None:
        dialogue = ConfirmationDialogue(ttl_s=20, clock=lambda: 100.0)

        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
            prompt_override="I cannot overlap those actions, but I can do them in sequence. Is that okay?",
        )

        self.assertEqual(
            pending.prompt,
            "I cannot overlap those actions, but I can do them in sequence. Is that okay?",
        )

    def test_approval_returns_exact_single_use_request(self) -> None:
        dialogue = ConfirmationDialogue(ttl_s=20, clock=lambda: 100.0)
        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        resolution = dialogue.resolve("confirm")
        replay = dialogue.resolve("confirm")

        self.assertEqual(resolution.decision, "approved")
        self.assertEqual(resolution.confirmed_request_ids, {"nod-1"})
        self.assertEqual(resolution.response, pending.response)
        self.assertEqual(resolution.fingerprint, pending.fingerprint)
        self.assertEqual(replay.decision, "not_confirmation")

    def test_typed_meaning_without_pending_confirmation_is_not_confirmation(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)

        self.assertEqual(dialogue.resolve("confirm").decision, "not_confirmation")
        self.assertEqual(dialogue.resolve("reject").decision, "not_confirmation")
        self.assertEqual(dialogue.resolve("ambiguous").decision, "not_confirmation")

    def test_denial_and_ambiguous_reply_never_return_request(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        denied = dialogue.resolve("reject")
        self.assertEqual(denied.decision, "denied")
        self.assertIsNone(denied.response)

        dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-2",
            conversation_id="conversation-1",
        )
        ambiguous = dialogue.resolve("ambiguous")
        self.assertEqual(ambiguous.decision, "ambiguous")
        self.assertIsNone(ambiguous.response)

    def test_remaining_ttl_uses_dialogue_clock(self) -> None:
        now = [100.0]
        dialogue = ConfirmationDialogue(ttl_s=20, clock=lambda: now[0])
        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        now[0] = 107.5

        self.assertEqual(dialogue.remaining_ttl_s(pending), 12.5)
        self.assertEqual(dialogue.remaining_ttl_s(), 12.5)

    def test_expired_or_changed_request_cannot_be_approved(self) -> None:
        now = [100.0]
        dialogue = ConfirmationDialogue(ttl_s=5, clock=lambda: now[0])
        dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )
        now[0] = 106.0

        self.assertEqual(dialogue.resolve("confirm").decision, "expired")

        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-2",
            conversation_id="conversation-1",
        )
        pending.response.skills[0].args["count"] = 3

        self.assertEqual(dialogue.resolve("confirm").decision, "ambiguous")

    def test_expected_confirmation_id_prevents_cross_request_authorization(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        resolution = dialogue.resolve(
            "confirm",
            expected_confirmation_id="confirm_replaced",
        )

        self.assertEqual(resolution.decision, "not_confirmation")
        self.assertEqual(dialogue.pending, pending)

    def test_fallback_prompt_is_natural_and_omits_runtime_internals(self) -> None:
        response = _response()
        response.skills[0].args["access_token"] = "do-not-speak"
        response.skills[0].args["nested"] = {
            "password": "also-do-not-speak",
        }
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)

        pending = dialogue.begin(
            response,
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        self.assertEqual(
            pending.prompt,
            "Would you like me to do that? Say “yes” and I’ll get started!",
        )
        self.assertNotIn("nod_yes", pending.prompt)
        self.assertNotIn("count", pending.prompt)
        self.assertNotIn("do-not-speak", pending.prompt)
        self.assertNotIn("also-do-not-speak", pending.prompt)
        self.assertEqual(ConfirmationDialogue(ttl_s=999).ttl_s, 300.0)


if __name__ == "__main__":
    unittest.main()
