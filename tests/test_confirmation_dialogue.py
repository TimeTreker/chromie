from __future__ import annotations

import unittest

from orchestrator.runtime.confirmation import ConfirmationDialogue
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

        resolution = dialogue.resolve("Yes!")
        replay = dialogue.resolve("yes")

        self.assertEqual(resolution.decision, "approved")
        self.assertEqual(resolution.confirmed_request_ids, {"nod-1"})
        self.assertEqual(resolution.response, pending.response)
        self.assertEqual(resolution.fingerprint, pending.fingerprint)
        self.assertEqual(replay.decision, "no_pending")

    def test_operational_stop_without_pending_confirmation_reaches_router(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)

        self.assertEqual(dialogue.resolve("Stop!").decision, "not_confirmation")
        self.assertEqual(dialogue.resolve("Cancel.").decision, "not_confirmation")
        self.assertEqual(
            dialogue.resolve("Emergency stop!").decision,
            "not_confirmation",
        )

    def test_operational_interrupt_cancels_pending_and_reaches_router(self) -> None:
        for phrase in ("Stop!", "Cancel.", "Emergency stop!", "急停！"):
            with self.subTest(phrase=phrase):
                dialogue = ConfirmationDialogue(clock=lambda: 100.0)
                pending = dialogue.begin(
                    _response(),
                    confirmed_request_ids={"nod-1"},
                    origin_session_id="sid-1",
                    conversation_id="conversation-1",
                )

                resolution = dialogue.resolve(phrase)

                self.assertEqual(
                    resolution.decision,
                    "operational_interrupt",
                )
                self.assertEqual(
                    resolution.confirmation_id,
                    pending.confirmation_id,
                )
                self.assertIsNone(resolution.response)
                self.assertIsNone(dialogue.pending)
                self.assertEqual(dialogue.resolve("yes").decision, "no_pending")

    def test_denial_and_ambiguous_reply_never_return_request(self) -> None:
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-1",
            conversation_id="conversation-1",
        )

        denied = dialogue.resolve("No, thanks.")
        self.assertEqual(denied.decision, "denied")
        self.assertIsNone(denied.response)

        dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-2",
            conversation_id="conversation-1",
        )
        ambiguous = dialogue.resolve("yes, but do it three times")
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

        self.assertEqual(dialogue.resolve("yes").decision, "expired")

        pending = dialogue.begin(
            _response(),
            confirmed_request_ids={"nod-1"},
            origin_session_id="sid-2",
            conversation_id="conversation-1",
        )
        pending.response.skills[0].args["count"] = 3

        self.assertEqual(dialogue.resolve("yes").decision, "ambiguous")

    def test_prompt_is_action_specific_and_omits_sensitive_arguments(self) -> None:
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

        self.assertIn("nod yes", pending.prompt)
        self.assertIn('"count": 2', pending.prompt)
        self.assertNotIn("do-not-speak", pending.prompt)
        self.assertNotIn("also-do-not-speak", pending.prompt)
        self.assertEqual(ConfirmationDialogue(ttl_s=999).ttl_s, 300.0)


if __name__ == "__main__":
    unittest.main()
