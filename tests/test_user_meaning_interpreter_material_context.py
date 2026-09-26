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

    assert "current-turn material context belongs to the same responsibility" in prompt
    assert "declarative, descriptive or locative clause" in prompt
    assert "object/resource" in prompt
    assert "source/location" in prompt
    assert "recipient/target" in prompt
    assert "use bindings sparsely for semantic facts" in prompt
    assert "never put provider arguments, defaults or execution realization" in prompt


def test_user_meaning_interpreter_uses_native_json_binding_values() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "a primitive count is `count: 6`" in prompt
    assert "not a mini-schema" in prompt
    assert "measured value together with its unit" in prompt


def test_primitive_binding_type_wrapper_is_representation_only() -> None:
    from shared.chromie_contracts.core_interpretation import (
        CognitiveResponsibilityProposal,
        responsibility_binding_material_value,
    )

    proposal = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="nod your head 6 times",
        bindings={"count": {"value": 6, "type": "integer"}},
        output_mode="body_action",
        continuity_scope="goal",
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

    assert "source_evidence span must cover every current-turn material clause" in prompt
    assert "never cite only the final command/question clause" in prompt
    assert "determines what, where, which, whom or under what" in prompt
    assert "semantic conservation, not a capability rule" in prompt



def test_nested_umi_binding_descriptors_normalize_to_material_values() -> None:
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
        output_mode="body_action",
        body_effect_family="task_physical_effect",
        continuity_scope="goal",
        confidence=1.0,
    )

    assert proposal.bindings == {
        "entity": "bottle of milk",
        "recipient": "user",
        "distance": {"value": 50, "unit": "meters"},
    }


def test_user_meaning_interpreter_requires_contextual_resource_source_bindings() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "those still-applicable source facts are part of the current what and must be" in prompt
    assert "present in this responsibility's bindings" in prompt
    assert "cognitive_requests" in prompt and "reason_summary" in prompt
    assert "source_evidence still cites only the current" in prompt
    assert "turn and must never be widened or fabricated" in prompt
    assert 'recipient: "user"' in prompt
    assert 'entity: "bottle of milk"' in prompt

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
            "status": "open",
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


def test_user_meaning_interpreter_memory_is_meaning_scoped_not_world_state_authority() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "umi receives\nonly its meaning-scoped projection" in prompt
    assert 'what does this expression mean?' in prompt
    assert "remembered object location" in prompt
    assert "planner/world evidence" in prompt
    assert "current explicit user wording outranks conflicting memory" in prompt
