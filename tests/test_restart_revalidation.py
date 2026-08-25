from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.runtime.named_goal_cancellation import (
    NamedGoalCancellationClosureError,
    dispatch_named_goal_cancellation,
)
from orchestrator.runtime.situation import build_situation_projection
from shared.chromie_contracts.goal import GoalAssociationResolution


class _NoDispatchRuntime:
    def __init__(self) -> None:
        self.calls = 0

    async def cancel_scope(self, _directive):
        self.calls += 1
        raise AssertionError("stale restored runtime binding must not dispatch")


class RestartRevalidationTests(unittest.TestCase):
    @staticmethod
    def _create_open_goal(manager: ConversationStateManager) -> None:
        results = manager.apply_goal_association_resolution({'resolution_status': 'resolved', 'turn_id': 'turn-create', 'new_goals': [{'goal_id': 'goal-walk', 'description': 'Walk forward after confirmation.', 'source_text': 'Walk forward when I confirm.'}], 'confidence': 1.0}, sid='sid-create', user_text='Walk forward when I confirm.', atomic=True)
        assert all(item.get("applied") for item in results)

    def test_restart_restores_responsibility_but_revalidates_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "task_contexts.json"
            manager = ConversationStateManager(
                base_conversation_id="restart",
                task_store_enabled=True,
                task_store_path=store_path,
            )
            self._create_open_goal(manager)
            context = manager._task_contexts[-1]
            context["status"] = "running"
            context["commitment_state"] = "executing"
            context["plan_status"] = "committed"
            context["confirmation"] = {
                "status": "pending",
                "confirmation_id": "confirm-old",
                "request_ids": ["request-walk"],
            }
            context["situation"] = {"must_not_persist": True}
            context["metadata"].update(
                {
                    "interaction_id": "interaction-old",
                    "canonical_plan_id": "plan-old",
                    "canonical_plan_fingerprint": "f" * 64,
                    "remaining_request_ids": ["request-walk"],
                    "request_statuses": {"request-walk": "running"},
                    "confirmation_id": "confirm-old",
                    "confirmation_request_ids": ["request-walk"],
                    "confirmation_pending": True,
                    "situation": {"must_not_persist": True},
                    "cognitive_opportunities": [{"ephemeral": True}],
                    "reflection_resolutions": [{"ephemeral": True}],
                    "provider_status": {"available": True},
                    "robot_state": {"location": "stale"},
                }
            )
            self.assertTrue(manager.persist_task_contexts())

            payload = json.loads(store_path.read_text(encoding="utf-8"))
            persisted = payload["task_contexts"][0]
            self.assertNotIn("situation", persisted)
            for key in (
                "situation",
                "cognitive_opportunities",
                "reflection_resolutions",
                "provider_status",
                "robot_state",
            ):
                self.assertNotIn(key, persisted["metadata"])

            restored = ConversationStateManager(
                base_conversation_id="restart",
                task_store_enabled=True,
                task_store_path=store_path,
            )
            restored_context = restored.snapshot()["current_task_context"]
            self.assertEqual(restored_context["status"], "recoverable")
            self.assertEqual(restored_context["commitment_state"], "evaluating")
            self.assertEqual(restored_context["plan_status"], "revalidation_required")
            self.assertIsNone(restored_context["confirmation"])
            self.assertEqual(
                restored.active_goal_snapshots()[0]["responsibility_status"],
                "open",
            )
            metadata = restored_context["metadata"]
            self.assertTrue(metadata["runtime_revalidation_required"])
            self.assertEqual(metadata["remaining_request_ids"], [])
            self.assertEqual(metadata["request_statuses"], {})
            self.assertEqual(
                metadata["recovery_previous_remaining_request_ids"],
                ["request-walk"],
            )
            self.assertEqual(
                metadata["recovery_previous_confirmation"]["confirmation_id"],
                "confirm-old",
            )
            self.assertEqual(metadata["canonical_plan_id"], "plan-old")

            binding = restored.goal_cancellation_bindings(["goal-walk"])[0]
            self.assertTrue(binding["requires_revalidation"])
            self.assertFalse(binding["requires_runtime_dispatch"])
            self.assertEqual(
                binding["revalidation_reason"],
                "restored_runtime_binding_requires_fresh_provider_state",
            )

            fresh_context = {
                "active_goal_snapshots": restored.active_goal_snapshots(),
                "discourse_focus": restored.discourse_focus(),
                "recent_tool_evidence": [],
            }
            situation = build_situation_projection(
                context=fresh_context,
                turn_id="turn-after-restart",
                revision=1,
            )
            self.assertEqual(situation.focus_goal_ids, ["goal-walk"])
            self.assertEqual(situation.revision, 1)
            self.assertNotIn("must_not_persist", json.dumps(situation.prompt_projection()))


    def test_revalidation_candidate_retains_exact_responsibility_seed_and_clears_stale_runtime_binding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "task_contexts.json"
            manager = ConversationStateManager(
                base_conversation_id="restart-seed",
                task_store_enabled=True,
                task_store_path=store_path,
            )
            results = manager.apply_goal_association_resolution(
                {
                    "resolution_status": "resolved",
                    "turn_id": "turn-create",
                    "new_goals": [
                        {
                            "goal_id": "goal-walk",
                            "description": "Walk forward.",
                            "source_text": "Walk forward.",
                            "source_responsibility_refs": ["resp-walk"],
                        }
                    ],
                    "confidence": 1.0,
                },
                sid="sid-create",
                user_text="Walk forward.",
                atomic=True,
            )
            self.assertTrue(all(item.get("applied") for item in results))
            responsibility = {
                "local_ref": "resp-walk",
                "outcome": "Walk forward.",
                "output_mode": "body_action",
                "confidence": 1.0,
            }
            retained = manager._planner_reentry_responsibilities(
                result_metadata={
                    "goal_interpretation": {"responsibilities": [responsibility]}
                },
                goal_id="goal-walk",
            )
            self.assertEqual(retained, [responsibility])

            context = manager._task_contexts[-1]
            context["status"] = "running"
            context["commitment_state"] = "executing"
            context["plan_status"] = "committed"
            context["metadata"].update(
                {
                    "canonical_plan_id": "plan-old",
                    "canonical_plan_fingerprint": "f" * 64,
                    "planned_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "request_id": "request-walk",
                        }
                    ],
                    "planner_reentry_responsibilities": retained,
                    "planner_reentry_language": "en-US",
                }
            )
            self.assertTrue(manager.persist_task_contexts())

            restored = ConversationStateManager(
                base_conversation_id="restart-seed",
                task_store_enabled=True,
                task_store_path=store_path,
            )
            candidates = restored.runtime_revalidation_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["goal_id"], "goal-walk")
            self.assertEqual(
                candidates[0]["capability_ids"], ["soridormi.walk_forward"]
            )
            self.assertEqual(candidates[0]["responsibilities"], [responsibility])

            source_ref = "runtime-state:restart:goal-walk:1"
            completed = restored.complete_runtime_revalidation(
                ["goal-walk"], source_ref=source_ref
            )
            self.assertEqual(completed, ["goal-walk"])
            binding = restored.goal_cancellation_bindings(["goal-walk"])[0]
            self.assertFalse(binding["requires_revalidation"])
            self.assertFalse(binding["requires_runtime_dispatch"])
            self.assertEqual(binding["request_ids"], [])
            restored_context = restored.snapshot()["current_task_context"]
            self.assertEqual(restored_context["status"], "planning")
            self.assertEqual(restored_context["plan_status"], "revalidated")
            self.assertEqual(
                restored_context["metadata"]["runtime_revalidation_source_ref"],
                source_ref,
            )
            self.assertEqual(
                restored_context["metadata"]["recovery_previous_canonical_plan_id"],
                "plan-old",
            )

    def test_terminal_responsibilities_are_not_restored(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "task_contexts.json"
            manager = ConversationStateManager(
                task_store_enabled=True,
                task_store_path=store_path,
            )
            self._create_open_goal(manager)
            manager._set_goal_responsibility_status(
                manager._task_contexts[-1],
                "satisfied",
                source="test",
            )
            self.assertTrue(manager.persist_task_contexts())
            payload = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["task_contexts"], [])



if __name__ == "__main__":
    unittest.main()
