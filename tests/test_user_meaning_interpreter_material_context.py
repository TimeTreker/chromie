from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT = (
    ROOT
    / "agent"
    / "app"
    / "cognitive_core"
    / "user_meaning_interpreter"
    / "prompts"
    / "user_meaning_interpreter_system.txt"
)


def test_user_meaning_interpreter_preserves_same_turn_material_context() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "preserve every material object" in prompt
    assert "a report, feeling, correction, confirmation" in prompt
    assert "object, person, place" in prompt
    assert "quantity, unit" in prompt
    assert "condition, negation" in prompt
    assert "write complete human meanings in responsibilities[].outcome" in prompt
    assert "no output_mode, body_effect_family, continuity_scope, bindings" in prompt


def test_user_meaning_interpreter_keeps_material_values_in_complete_meaning() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "ordering or concurrency relation" in prompt
    assert "planner owns conversion, freshness and answer-source choices" in prompt


def test_primitive_binding_type_wrapper_is_representation_only() -> None:
    from shared.chromie_contracts.core_interpretation import (
        CognitiveResponsibilityProposal,
        responsibility_binding_material_value,
    )

    proposal = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="nod your head 6 times",
        bindings={"count": {"value": 6, "type": "integer"}},


        confidence=1.0,
        source_evidence={
            "source_start_token_ref": "t0",
            "source_end_token_ref": "t6",
        },
    )
    assert proposal.bindings == {"count": 6}

    measured = {"value": 50, "unit": "m", "type": "distance"}
    assert responsibility_binding_material_value(measured) == measured

    mismatched = {"value": "6", "type": "integer"}
    assert responsibility_binding_material_value(mismatched) == mismatched


def test_user_meaning_interpreter_source_span_covers_material_clauses_not_only_command() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "source_evidence cites the first and last authoritative current-turn token" in prompt
    assert "context-derived meaning stays context-derived" in prompt
    assert "token on which it depends" in prompt
    assert "do not fabricate current-turn citations for earlier words" in prompt



def test_retained_responsibility_binding_descriptors_normalize_to_material_values() -> None:
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal

    proposal = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="bring the bottle of milk to the user",
        bindings={
            "entity": {
                "confidence": 1.0,
                "entity_type": "object",
                "name": "entity",
                "value": {
                    "confidence": 1.0,
                    "entity_type": "object",
                    "name": "milk_bottle",
                    "value": "bottle of milk",
                },
            },
            "recipient": {
                "confidence": 1.0,
                "entity_type": "person",
                "name": "recipient",
                "value": "user",
            },
            "distance": {
                "confidence": 1.0,
                "entity_type": "distance",
                "name": "distance",
                "value": {
                    "confidence": 1.0,
                    "entity_type": "measurement",
                    "name": "distance",
                    "value": 50,
                    "unit": "meters",
                },
            },
        },



        confidence=1.0,
    )

    assert proposal.bindings == {
        "entity": "bottle of milk",
        "recipient": "user",
        "distance": {"value": 50, "unit": "meters"},
    }


def test_user_meaning_interpreter_preserves_contextual_resource_meaning() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "include the resolved subject, need and still-applicable constraints" in prompt
    assert "in the outcome itself" in prompt
    assert "cognitive_requests" in prompt and "do not author reasons" in prompt
    assert "authoritative current-turn token" in prompt
    assert "do not fabricate current-turn citations for earlier words" in prompt

def test_user_meaning_interpreter_goal_context_is_semantic_without_canonical_identity() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import (
        _compact_goal_meaning_context,
    )

    context = {
        "user_meaning_goal_context": [
            {
                "goal_id": "goal-secret-id",
                "goal_version": 7,
                "task_id": "task-secret-id",
                "responsibility_status": "open",
                "goal": {
                    "goal_id": "goal-secret-id",
                    "version": 7,
                    "description": "Check whether Chongqing will be hot tonight.",
                    "object": {"bindings": {"location": {"value": "重庆"}}},
                    "constraints": {"time_scope": "今晚"},
                    "metadata": {"output_mode": "information"},
                },
                "last_user_update": "重庆今晚热不热？",
                "open_information_gaps": [],
            }
        ],
        # Recent terminal Goals belong to GA candidate retrieval, not ambient UMI context.
        "recent_goal_snapshots": [
            {"goal_id": "terminal-goal", "description": "An unrelated finished task."}
        ],
    }

    projected = _compact_goal_meaning_context(context)

    assert projected == [
        {
            "description": "Check whether Chongqing will be hot tonight.",
            "object": {"bindings": {"location": "重庆"}},
            "constraints": {"time_scope": "今晚"},
            "output_mode": "information",
            "pending_clarification": [],
            "last_user_update": "重庆今晚热不热？",
        }
    ]
    serialized = str(projected)
    assert "goal-secret-id" not in serialized
    assert "task-secret-id" not in serialized
    assert "terminal-goal" not in serialized


def test_task_completion_does_not_reauthor_the_human_meaning_context() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import (
        _compact_goal_meaning_context,
    )

    snapshots = [
        {"goal": {"description": "Help with the person's stated need.",
                  "constraints": {"recipient": "user"}},
         "last_user_update": "Please help with that."},
    ]
    expected = _compact_goal_meaning_context({"user_meaning_goal_context": snapshots})
    for status in ("open", "satisfied", "failed", "cancelled"):
        snapshot = {**snapshots[0], "responsibility_status": status,
                    "goal": {**snapshots[0]["goal"], "responsibility_status": status}}
        assert _compact_goal_meaning_context({"user_meaning_goal_context": [snapshot]}) == expected


def test_user_meaning_interpreter_memory_is_meaning_scoped_not_world_state_authority() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "what the current human expression means" in prompt
    assert 'current explicit wording overrides older context' in prompt
    assert "an older goal, memory entry, perception or assistant statement is context" in prompt
    assert "never a new user command or proof of execution" in prompt
    assert "do not select an object merely because it is visible" in prompt
