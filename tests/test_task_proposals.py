from __future__ import annotations

import unittest

from orchestrator.runtime.task_proposals import annotate_task_proposal_ledger
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.task_proposal import TaskProposalLedger


class TaskProposalLedgerTests(unittest.TestCase):
    def test_route_effect_task_without_skill_is_not_committed(self) -> None:
        response = InteractionResponse(
            speech=[{"text": "I will hold still."}],
            metadata={
                "route_task_list": [
                    {
                        "id": "quick_intent:0:task.execute_skill",
                        "source_stage": "quick_intent",
                        "kind": "action",
                        "task_type": "task.execute_skill",
                        "capability_id": "look_at_window",
                        "priority": "normal",
                    }
                ]
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = annotated.metadata["task_proposal_ledger"]
        route_proposal = ledger["proposals"][0]

        self.assertEqual(route_proposal["state"], "not_committed")
        self.assertEqual(route_proposal["skill_id"], "soridormi.look_at_window")
        self.assertIn("requires an InteractionResponse skill", route_proposal["reason"])
        self.assertEqual(ledger["summary"]["not_committed_effectful_count"], 1)
        self.assertEqual(ledger["summary"]["states"]["committed"], 1)

    def test_shared_route_task_proposals_are_consumed_before_legacy_task_list(self) -> None:
        response = InteractionResponse(
            speech=[{"text": "I will hold still."}],
            metadata={
                "route_task_proposals": [
                    {
                        "id": "quick_intent:0:task.execute_skill",
                        "source": "quick_intent",
                        "proposal_kind": "action",
                        "task_type": "task.execute_skill",
                        "state": "advisory",
                        "reason": "router proposal awaiting Orchestrator merge and commit",
                        "effectful": True,
                        "priority": "normal",
                        "sequence": 0,
                        "skill_id": "soridormi.look_at_window",
                    }
                ],
                "route_task_list": [
                    {
                        "id": "legacy:0:speech.answer",
                        "source_stage": "legacy",
                        "kind": "task",
                        "task_type": "speech.answer",
                    }
                ],
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        proposals = annotated.metadata["task_proposal_ledger"]["proposals"]

        self.assertEqual(proposals[0]["id"], "quick_intent:0:task.execute_skill")
        self.assertEqual(proposals[0]["state"], "not_committed")
        self.assertEqual(proposals[0]["skill_id"], "soridormi.look_at_window")
        self.assertNotIn("legacy:0:speech.answer", {item["id"] for item in proposals})

    def test_matching_interaction_skill_commits_route_proposal(self) -> None:
        response = InteractionResponse(
            skills=[
                {
                    "request_id": "look-1",
                    "skill_id": "soridormi.look_at_person",
                    "args": {"target": "user"},
                }
            ],
            metadata={
                "route_task_list": [
                    {
                        "id": "quick_intent:0:task.execute_skill",
                        "source_stage": "quick_intent",
                        "kind": "action",
                        "task_type": "task.execute_skill",
                        "capability_id": "look_at_person",
                    }
                ]
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        proposals = annotated.metadata["task_proposal_ledger"]["proposals"]

        self.assertEqual(proposals[0]["state"], "committed")
        self.assertEqual(proposals[0]["committed_by"], "interaction_response.skill")
        self.assertEqual(proposals[1]["state"], "committed")
        self.assertEqual(proposals[1]["request_id"], "look-1")

    def test_committed_skill_proposal_includes_static_preflight_status(self) -> None:
        response = InteractionResponse(
            skills=[
                {
                    "request_id": "nod-1",
                    "skill_id": "soridormi.nod_yes",
                }
            ],
            metadata={
                "preflight_validation": {
                    "summary": {"checked_skill_count": 1, "pending_count": 1},
                    "items": [
                        {
                            "request_id": "nod-1",
                            "skill_id": "soridormi.nod_yes",
                            "status": "needs_confirmation",
                            "reason_code": "confirmation_required",
                            "world_feasibility": "unknown_until_runtime",
                        }
                    ],
                }
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = annotated.metadata["task_proposal_ledger"]
        proposal = ledger["proposals"][0]

        self.assertEqual(proposal["state"], "committed")
        self.assertEqual(proposal["preflight"]["status"], "needs_confirmation")
        self.assertEqual(
            ledger["summary"]["preflight_statuses"],
            {"needs_confirmation": 1},
        )

    def test_agent_task_proposals_replace_fallback_committed_entries(self) -> None:
        response = InteractionResponse(
            speech=[
                {
                    "id": "speech-1",
                    "text": "Okay.",
                    "timing": "immediate",
                }
            ],
            skills=[
                {
                    "request_id": "nod-1",
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                    "timing": "parallel",
                }
            ],
            metadata={
                "agent_task_proposals": [
                    {
                        "id": "agent:speech:speech-1",
                        "source": "conversation_agent",
                        "proposal_kind": "speech",
                        "task_type": "speech.speak",
                        "skill_id": "chromie.speak",
                        "state": "committed",
                        "reason": "Agent speech committed to InteractionResponse",
                        "effectful": False,
                        "priority": "normal",
                        "sequence": 0,
                        "speech_id": "speech-1",
                        "timing": "immediate",
                        "text_chars": 5,
                    },
                    {
                        "id": "agent:skill:nod-1",
                        "source": "capability_agent",
                        "proposal_kind": "skill",
                        "task_type": "task.execute_skill",
                        "skill_id": "soridormi.nod_yes",
                        "request_id": "nod-1",
                        "state": "committed",
                        "reason": "Agent skill committed to InteractionResponse",
                        "effectful": True,
                        "priority": "normal",
                        "sequence": 1,
                        "timing": "parallel",
                        "requires_confirmation": False,
                    },
                ]
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = TaskProposalLedger.model_validate(
            annotated.metadata["task_proposal_ledger"]
        )
        proposal_ids = {proposal.id for proposal in ledger.proposals}

        self.assertEqual(
            proposal_ids,
            {"agent:speech:speech-1", "agent:skill:nod-1"},
        )
        self.assertFalse(
            any(item.startswith("interaction_response:") for item in proposal_ids)
        )
        self.assertEqual(ledger.summary.states, {"committed": 2})
        self.assertEqual(ledger.summary.committed_effectful_count, 1)

    def test_deepthinking_rejected_tasks_are_audited(self) -> None:
        response = InteractionResponse(
            speech=[{"text": "I cannot safely turn that into an action."}],
            metadata={
                "deepthinking_rejected_tasks": [
                    {
                        "task_type": "task.execute_skill",
                        "skill_id": "invented.jump",
                        "reason": "unknown skill",
                    }
                ]
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = annotated.metadata["task_proposal_ledger"]
        rejected = [
            proposal for proposal in ledger["proposals"] if proposal["state"] == "rejected"
        ]

        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reason"], "unknown skill")
        self.assertEqual(ledger["summary"]["states"]["rejected"], 1)

    def test_deepthinking_shared_task_proposals_are_merged_once(self) -> None:
        response = InteractionResponse(
            speech=[{"text": "I cannot safely turn that into an action."}],
            metadata={
                "deepthinking_task_proposals": [
                    {
                        "id": "deepthinking:0:speech.speak",
                        "source": "deepthinking",
                        "proposal_kind": "speech",
                        "task_type": "speech.speak",
                        "state": "committed",
                        "reason": "deepthinking speech task",
                        "effectful": False,
                        "priority": "normal",
                        "sequence": 0,
                        "skill_id": "chromie.speak",
                    },
                    {
                        "id": "deepthinking:1:task.execute_skill",
                        "source": "deepthinking",
                        "proposal_kind": "skill",
                        "task_type": "task.execute_skill",
                        "state": "rejected",
                        "reason": "not_available_interaction_executable_candidate",
                        "effectful": True,
                        "priority": "normal",
                        "sequence": 1,
                        "skill_id": "soridormi.jump",
                    },
                ],
                "deepthinking_rejected_tasks": [
                    {
                        "task_type": "task.execute_skill",
                        "skill_id": "soridormi.jump",
                        "reason": "legacy duplicate should not be emitted",
                    }
                ],
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = annotated.metadata["task_proposal_ledger"]
        rejected = [
            proposal for proposal in ledger["proposals"] if proposal["state"] == "rejected"
        ]

        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["id"], "deepthinking:1:task.execute_skill")
        self.assertEqual(ledger["summary"]["states"]["rejected"], 1)
        self.assertEqual(ledger["summary"]["sources"]["deepthinking"], 2)

    def test_superseded_task_proposals_are_schema_validated(self) -> None:
        response = InteractionResponse(
            speech=[{"text": "I will hold still."}],
            metadata={
                "superseded_task_proposals": [
                    {
                        "id": "quick_intent:0:task.execute_skill",
                        "source": "quick_intent",
                        "kind": "action",
                        "task_type": "task.execute_skill",
                        "skill_id": "look_at_window",
                        "reason": "later warning interpretation superseded window gaze",
                        "superseded_by": "deep_reconciler:hold",
                    }
                ]
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = TaskProposalLedger.model_validate(
            annotated.metadata["task_proposal_ledger"]
        )
        superseded = [
            proposal for proposal in ledger.proposals if proposal.state == "superseded"
        ]

        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded[0].skill_id, "soridormi.look_at_window")
        self.assertEqual(superseded[0].superseded_by, "deep_reconciler:hold")
        self.assertEqual(ledger.summary.superseded_count, 1)
        self.assertEqual(
            annotated.metadata["task_proposal_ledger"]["summary"]["states"]["superseded"],
            1,
        )

    def test_revised_task_proposals_add_replacement_and_superseded_marker(self) -> None:
        response = InteractionResponse(
            speech=[
                {
                    "id": "speech-repair",
                    "text": "Sorry, I misunderstood that. I will hold still.",
                }
            ],
            metadata={
                "route_task_proposals": [
                    {
                        "id": "quick_intent:0:task.execute_skill",
                        "source": "quick_intent",
                        "proposal_kind": "action",
                        "task_type": "task.execute_skill",
                        "state": "advisory",
                        "reason": "quick router misread warning as a window gaze request",
                        "effectful": True,
                        "priority": "high",
                        "sequence": 0,
                        "skill_id": "soridormi.look_at_window",
                    }
                ],
                "revised_task_proposals": [
                    {
                        "id": "deep_reconciler:0:speech.speak",
                        "source": "deep_reconciler",
                        "proposal_kind": "speech",
                        "task_type": "speech.speak",
                        "skill_id": "chromie.speak",
                        "speech_id": "speech-repair",
                        "state": "committed",
                        "reason": "warning repair speech replaces window gaze",
                        "effectful": False,
                        "priority": "high",
                        "sequence": 1,
                        "supersedes_id": "quick_intent:0:task.execute_skill",
                        "superseded_task_type": "task.execute_skill",
                        "superseded_skill_id": "soridormi.look_at_window",
                        "superseded_reason": "later warning interpretation superseded window gaze",
                        "superseded_effectful": True,
                    }
                ],
            },
        )

        annotated = annotate_task_proposal_ledger(response)
        ledger = TaskProposalLedger.model_validate(
            annotated.metadata["task_proposal_ledger"]
        )
        proposals_by_id = {proposal.id: proposal for proposal in ledger.proposals}

        self.assertEqual(
            proposals_by_id["quick_intent:0:task.execute_skill"].state,
            "not_committed",
        )
        replacement = proposals_by_id["deep_reconciler:0:speech.speak"]
        self.assertEqual(replacement.state, "committed")
        self.assertEqual(replacement.skill_id, "chromie.speak")
        self.assertEqual(
            replacement.metadata["supersedes"],
            "quick_intent:0:task.execute_skill",
        )
        superseded = proposals_by_id["quick_intent:0:task.execute_skill:superseded"]
        self.assertEqual(superseded.state, "superseded")
        self.assertEqual(superseded.skill_id, "soridormi.look_at_window")
        self.assertEqual(superseded.superseded_by, "deep_reconciler:0:speech.speak")
        self.assertEqual(ledger.summary.superseded_count, 1)
        self.assertEqual(ledger.summary.states["superseded"], 1)
        self.assertEqual(ledger.summary.not_committed_effectful_count, 2)


if __name__ == "__main__":
    unittest.main()
