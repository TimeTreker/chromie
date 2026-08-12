from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from orchestrator.runtime.interaction_ledger import InteractionLedger
from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
)
from shared.chromie_contracts.interaction import SkillRequest, SkillResult
from shared.chromie_contracts.interaction_ledger import InteractionLedgerEvent


class InteractionLedgerTests(unittest.TestCase):
    def test_playback_transitions_append_without_rewriting_prior_fact(self) -> None:
        ledger = InteractionLedger()
        lifecycle = PlaybackDeliveryLifecycle(
            interaction_event_sink=ledger.record_playback_event
        )
        lifecycle.register_turn_speech_event(
            session_id="sid",
            turn_id="turn-1",
            generation=2,
            orders=[4],
            normalized_text="好的，我往前走十五秒。",
            stage="pre_action",
            purpose="acknowledgement",
            source_goal_ids=["goal-walk"],
            canonical_plan_id="plan-walk",
            canonical_plan_fingerprint="f" * 64,
            claims=["acknowledgement"],
            must_not_claim_completion=True,
        )
        lifecycle.update_turn_speech_event_for_playback(
            generation=2,
            order=4,
            session_id="sid",
            started=True,
            reason="playback_start",
        )

        events = ledger.events("sid")
        self.assertEqual(
            [item.event_type for item in events],
            ["speech_scheduled", "speech_playback_started"],
        )
        self.assertEqual(events[0].state, "scheduled")
        context = ledger.context(
            "sid",
            goal_ids=["goal-walk"],
            turn_id="turn-1",
        )
        self.assertEqual(len(context.already_spoken), 1)
        self.assertEqual(context.pending_speech, [])
        self.assertEqual(context.already_spoken[0]["text"], "好的，我往前走十五秒。")

    def test_goal_projection_includes_only_bound_goal_and_same_turn_unbound_events(
        self,
    ) -> None:
        ledger = InteractionLedger()
        for speech_id, goal_ids, turn_id in (
            ("speech-walk", ["goal-walk"], "turn-1"),
            ("speech-weather", ["goal-weather"], "turn-1"),
            ("speech-fast", [], "turn-1"),
            ("speech-old-unbound", [], "turn-0"),
        ):
            ledger.record_playback_event(
                {
                    "event_id": speech_id,
                    "session_id": "sid",
                    "turn_id": turn_id,
                    "status": "playback_started",
                    "text": speech_id,
                    "source_goal_ids": goal_ids,
                }
            )

        context = ledger.context(
            "sid",
            goal_ids=["goal-walk"],
            turn_id="turn-1",
        )
        self.assertEqual(
            [item["subject_id"] for item in context.already_spoken],
            ["speech-walk", "speech-fast"],
        )

    def test_committed_request_remains_unresolved_until_trusted_outcome(self) -> None:
        ledger = InteractionLedger()
        request = SkillRequest(
            request_id="request-walk",
            skill_id="soridormi.walk_forward",
            args={"duration_s": 15},
            metadata={
                "canonical_plan_id": "plan-walk",
                "canonical_plan_fingerprint": "f" * 64,
                "source_goal_ids": ["goal-walk"],
                "execution_lane": "activity",
            },
        )
        ledger.record_committed_requests(
            session_id="sid",
            turn_id="turn-1",
            interaction_id="interaction-1",
            requests=[request],
        )
        pending = ledger.context("sid", goal_ids=["goal-walk"])
        self.assertEqual(
            pending.unresolved[0]["waiting_for"],
            "activity_terminal_result",
        )

        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-walk",
            turn_id="turn-1",
            interaction_id="interaction-1",
            canonical_plan_id="plan-walk",
            canonical_plan_fingerprint="f" * 64,
            canonical_goal_ids=["goal-walk"],
            aggregate_status="completed",
            evidence=[
                ExecutionEvidence(
                    evidence_id="evidence-walk",
                    request_id="request-walk",
                    step_id="step-walk",
                    skill_id="soridormi.walk_forward",
                    source_goal_ids=["goal-walk"],
                    status="completed",
                    metadata={"execution_lane": "activity"},
                )
            ],
            goal_outcomes=[
                GoalExecutionOutcome(
                    goal_id="goal-walk",
                    status="completed",
                    step_ids=["step-walk"],
                    evidence_ids=["evidence-walk"],
                    completed_step_ids=["step-walk"],
                    unresolved_step_ids=[],
                )
            ],
        )
        ledger.record_execution_outcome(bundle, session_id="sid")
        completed = ledger.context("sid", goal_ids=["goal-walk"])
        self.assertEqual(completed.unresolved, [])
        self.assertEqual(completed.activity[-1]["state"], "completed")
        self.assertIn(
            "evidence-walk",
            completed.activity[-1]["evidence_refs"],
        )

    def test_terminal_activity_cannot_be_authored_without_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            InteractionLedgerEvent(
                event_id="event-1",
                sequence=1,
                session_id="sid",
                owner="execution_closure",
                domain="activity",
                event_type="activity_completed",
                state="completed",
                subject_id="goal-walk",
                occurred_at=datetime.now(timezone.utc),
            )

    def test_social_result_replaces_committed_action_in_unresolved_projection(
        self,
    ) -> None:
        ledger = InteractionLedger()
        request = SkillRequest(
            request_id="social-look",
            skill_id="soridormi.look_at_person",
            args={},
            metadata={
                "auxiliary_social_attention": True,
                "source_goal_ids": ["goal-greet"],
            },
        )
        ledger.record_committed_requests(
            session_id="sid",
            turn_id="turn-1",
            interaction_id="interaction-1",
            requests=[request],
        )
        ledger.record_social_results(
            session_id="sid",
            turn_id="turn-1",
            interaction_id="interaction-1",
            requests=[request],
            results=[
                SkillResult(
                    request_id="social-look",
                    skill_id="soridormi.look_at_person",
                    status="completed",
                    provider_id="soridormi.mcp",
                )
            ],
        )

        context = ledger.context("sid", goal_ids=["goal-greet"])
        self.assertEqual(context.unresolved, [])
        self.assertEqual(
            context.social_decorations[-1]["event_type"],
            "social_decoration_completed",
        )

    def test_replay_is_idempotent_but_cannot_change_an_event(self) -> None:
        ledger = InteractionLedger()
        kwargs = {
            "session_id": "sid",
            "owner": "playback_delivery",
            "domain": "vocal",
            "event_type": "speech_scheduled",
            "state": "scheduled",
            "subject_id": "speech-1",
            "event_id": "event-1",
            "text": "hello",
        }
        first = ledger.append(**kwargs)
        second = ledger.append(**kwargs)
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "changed an immutable event"):
            ledger.append(**{**kwargs, "text": "different"})

    def test_returned_event_cannot_mutate_retained_nested_metadata(self) -> None:
        ledger = InteractionLedger()
        returned = ledger.append(
            session_id="sid",
            owner="cognitive_runtime",
            domain="cognition",
            event_type="goal_associated",
            state="resolved",
            subject_id="association-1",
            event_id="event-1",
            metadata={"relationships": ["new"]},
        )

        returned.metadata["relationships"].append("supersedes")

        self.assertEqual(
            ledger.events("sid")[0].metadata["relationships"],
            ["new"],
        )

    def test_eviction_does_not_allow_replay_to_rewrite_event_identity(self) -> None:
        ledger = InteractionLedger(max_events_per_session=16)
        original = {
            "session_id": "sid",
            "owner": "cognitive_runtime",
            "domain": "cognition",
            "event_type": "goal_associated",
            "state": "resolved",
            "subject_id": "association-0",
            "event_id": "event-0",
            "metadata": {"relationships": ["new"]},
        }
        first = ledger.append(**original)
        for index in range(1, 17):
            ledger.append(
                session_id="sid",
                owner="cognitive_runtime",
                domain="cognition",
                event_type="goal_associated",
                state="resolved",
                subject_id=f"association-{index}",
                event_id=f"event-{index}",
            )

        replay = ledger.append(**original)

        self.assertEqual(replay.sequence, first.sequence)
        self.assertEqual(len(ledger.events("sid")), 16)
        with self.assertRaisesRegex(ValueError, "changed an immutable event"):
            ledger.append(
                **{
                    **original,
                    "metadata": {"relationships": ["supersedes"]},
                }
            )


if __name__ == "__main__":
    unittest.main()
