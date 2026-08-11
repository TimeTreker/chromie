from __future__ import annotations

from orchestrator.runtime.situation import build_situation_projection
from shared.chromie_contracts.situation import SituationProjection


def test_situation_projection_is_bounded_reference_only_and_reconstructable() -> None:
    context = {
        "active_goal_snapshots": [
            {
                "goal_id": "goal-water",
                "open_information_gaps": [
                    {
                        "gap_id": "target-container",
                        "description": "Which cup?",
                        "preferred_resolution": "ask_user",
                        "resolved": False,
                    }
                ],
            }
        ],
        "discourse_focus": ["ref-user", "ref-blue-cup"],
        "recent_tool_evidence": [
            {
                "evidence_id": "evidence-camera-1",
                "source": "interaction_camera_observation",
                "payload": {"large": "authoritative evidence stays outside Situation"},
            }
        ],
    }

    first = build_situation_projection(
        context=context,
        turn_id="turn-1",
        lane="robot_action",
        intent="bring cup",
        progress_candidate_ids=["progress-1"],
    )
    rebuilt = build_situation_projection(
        context=context,
        turn_id="turn-1",
        lane="robot_action",
        intent="bring cup",
        progress_candidate_ids=["progress-1"],
    )

    assert first == rebuilt
    assert first.focus_goal_ids == ["goal-water"]
    assert first.discourse_focus_ids == ["ref-user", "ref-blue-cup"]
    assert first.unresolved_conditions[0].condition_id == "target-container"
    assert first.progress_candidate_ids == ["progress-1"]
    assert first.evidence_refs[0].reference_id == "evidence-camera-1"
    projection = first.prompt_projection()
    assert "payload" not in str(projection)
    assert SituationProjection.model_validate(projection) == first


def test_situation_revision_can_change_focus_without_mutating_source_context() -> None:
    context = {
        "active_goal_snapshots": [{"goal_id": "goal-old"}],
        "discourse_focus": ["ref-one"],
    }

    before = build_situation_projection(
        context=context,
        turn_id="turn-2",
        lane="chat",
        intent="correct target",
        revision=1,
    )
    after = build_situation_projection(
        context=context,
        turn_id="turn-2",
        lane="chat",
        intent="correct target",
        focus_goal_ids=["goal-new"],
        revision=2,
    )

    assert before.focus_goal_ids == ["goal-old"]
    assert after.focus_goal_ids == ["goal-new"]
    assert before.digest != after.digest
    assert context["active_goal_snapshots"][0]["goal_id"] == "goal-old"
