from __future__ import annotations

import unittest

from orchestrator.runtime.confirmation import (
    ConfirmationDialogue,
    confirmation_meaning_from_goal_association,
    reconcile_revoked_confirmation_for_reflex,
    revoke_pending_confirmation_for_reflex,
    revoked_confirmation_evidence_for_reflex,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse


def _response() -> InteractionResponse:
    return InteractionResponse(
        interaction_id="interaction-confirm",
        capabilities=[
            {
                "request_id": "nod-1",
                "capability_id": "soridormi.nod_yes",
                "args": {"count": 2},
                "requires_confirmation": True,
            }
        ],
    )


class ConfirmationDialogueTests(unittest.TestCase):
    def test_goal_association_confirmation_requires_exact_pending_scope(self) -> None:
        def resolution(relationship: str, goal_ids: list[str]) -> GoalAssociationResolution:
            return GoalAssociationResolution.model_validate(
                {"resolution_status": "resolved",
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
        pending.response.capabilities[0].args["count"] = 3

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


    def test_fixed_reflex_confirmation_policy_is_scope_bound_and_conservative(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        pending = dialogue.begin(
            InteractionResponse(
                interaction_id="interaction-mixed",
                capabilities=[
                    {"request_id": "move", "capability_id": "soridormi.walk"},
                    {"request_id": "read", "capability_id": "chromie.weather"},
                ],
            ),
            confirmed_request_ids={"move", "read"},
            origin_session_id="sid",
            conversation_id="conversation",
        )

        class Definition:
            def __init__(self, *domains: str) -> None:
                self.cancellation_domains = domains

        class Registry:
            def get(self, capability_id: str) -> Definition:
                if capability_id == "soridormi.walk":
                    return Definition("embodied_motion")
                return Definition()

        self.assertIsNone(
            revoke_pending_confirmation_for_reflex(
                dialogue,
                cancellation_scope="output_only",
                interaction_registry=Registry(),
            )
        )
        self.assertIs(dialogue.pending, pending)

        revoked = revoke_pending_confirmation_for_reflex(
            dialogue,
            cancellation_scope="embodied_motion",
            interaction_registry=Registry(),
        )
        self.assertIs(revoked, pending)
        self.assertIsNone(dialogue.pending)

        evidence = revoked_confirmation_evidence_for_reflex(
            revoked,
            cancellation_scope="embodied_motion",
            interaction_registry=Registry(),
        )
        self.assertEqual(evidence["motion_request_ids"], ["move"])
        self.assertTrue(evidence["confirmation_scope_widened"])
        self.assertEqual(
            evidence["widening_reason"],
            "shared_confirmation_token_revoked_conservatively",
        )

    def test_reconcile_revoked_confirmation_is_bookkeeping_only(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid",
            conversation_id="conversation",
        )
        revoked = dialogue.cancel()
        assert revoked is pending

        class Definition:
            cancellation_domains = ("embodied_motion",)

        class Registry:
            def get(self, capability_id: str) -> Definition:
                return Definition()

        class ConversationState:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def resolve_confirmation_scope(
                self, *, confirmation_id: str, decision: str
            ) -> bool:
                self.calls.append((confirmation_id, decision))
                return True

        state = ConversationState()
        logs: list[str] = []

        evidence = reconcile_revoked_confirmation_for_reflex(
            revoked,
            conversation_state=state,
            session_id="sid",
            cancellation_scope="current_interaction",
            interaction_registry=Registry(),
            session_log=lambda sid, message, *args: logs.append(message % args),
        )

        self.assertEqual(
            state.calls,
            [(pending.confirmation_id, "operational_interrupt")],
        )
        self.assertEqual(evidence["confirmation_id"], pending.confirmation_id)
        self.assertTrue(logs)

    def test_fallback_prompt_is_natural_and_omits_runtime_internals(self) -> None:
        response = _response()
        response.capabilities[0].args["access_token"] = "do-not-speak"
        response.capabilities[0].args["nested"] = {
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
