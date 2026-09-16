from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.runtime.cognitive_runtime import (
    CognitiveEvidenceRecorder,
    CognitiveRuntimeResolution,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CoreInterpretationResult,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.semantic_artifact import (
    SemanticArtifactPacket,
    semantic_artifact_packet,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.social_cognition import SocialCognitionResolution
from tests.test_cognitive_runtime_pr7 import admitted_core, respond_plan
from tests.test_execution_outcome_truth import _bundle as execution_bundle
from tests.test_execution_outcome_truth import _plan as execution_plan


def test_semantic_artifact_packet_detects_payload_mutation() -> None:
    parent = semantic_artifact_packet(
        {"text": "hello"},
        artifact_kind="user_turn",
        artifact_id="turn-1",
        authority="cognitive_gateway",
        session_id="sid-1",
        turn_id="turn-1",
    )
    packet = semantic_artifact_packet(
        {"outcome": "say hello"},
        artifact_kind="responsibility",
        artifact_id="turn-1:r1",
        authority="goal_interpretation",
        session_id="sid-1",
        turn_id="turn-1",
        parent_refs=[parent.ref],
    )
    assert packet.envelope.parent_refs == (parent.ref,)

    raw = packet.model_dump(mode="json")
    raw["payload"]["outcome"] = "different meaning"
    with pytest.raises(ValueError, match="payload does not match envelope digest"):
        SemanticArtifactPacket.model_validate(raw)


def test_semantic_artifact_parent_refs_are_deduplicated() -> None:
    parent = semantic_artifact_packet(
        {"text": "hello"}, artifact_kind="user_turn", artifact_id="turn-1",
        authority="cognitive_gateway", session_id="sid-1", turn_id="turn-1",
    )
    packet = semantic_artifact_packet(
        {"result": "ok"}, artifact_kind="goal_interpretation", artifact_id="turn-1",
        authority="goal_interpretation", session_id="sid-1", turn_id="turn-1",
        parent_refs=[parent.ref, parent.ref],
    )
    assert packet.envelope.parent_refs == (parent.ref,)


def test_cognitive_evidence_archives_semantic_artifact_lineage() -> None:
    core, envelope = admitted_core("hello", sid="sid-artifacts", language="en-US")
    responsibility = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Respond to the greeting.",
        output_mode="speech",
        confidence=0.95,
        source_evidence={
            "source_start_token_ref": "t0",
            "source_end_token_ref": "t0",
        },
    )
    core = CoreInterpretationResult(
        turn_id=envelope.turn_id,
        session_id=envelope.session_id,
        confidence=0.95,
        language="en-US",
        responsibilities=[responsibility],
    )
    association = GoalAssociationResolution(
        turn_id=envelope.turn_id,
        resolution_status="resolved",
        new_goals=[
            SemanticGoal(
                goal_id="goal-hello",
                description="Respond to the greeting.",
                source_text="hello",
                source_responsibility_refs=["r1"],
                metadata={"output_mode": "speech"},
            )
        ],
        confidence=0.95,
        reason_summary="New greeting Goal.",
    )
    plan = respond_plan("goal-hello")
    social = SocialCognitionResolution(
        request_id="sc-hello",
        snapshot_digest="a" * 64,
        disposition="communicate",
        activities=[
            {
                "activity_id": "talk-hello",
                "text": "Hi!",
                "function": "respond",
                "truth_stage": "context_grounded",
                "source_responsibility_refs": ["r1"],
                "source_goal_ids": ["goal-hello"],
            }
        ],
        reason_summary="A greeting deserves a response.",
        model_call_count=1,
    )
    interaction = InteractionResponse(
        interaction_id="interaction-hello",
        metadata={"social_cognition_resolution": social.model_dump(mode="json")},
    )
    resolution = CognitiveRuntimeResolution(
        mode="report_only",
        status="report_only",
        turn_envelope=envelope,
        goal_association=association,
        fast_plan=plan,
        terminal_plan=plan,
        interaction_response=interaction,
        metadata={"core_interpretation": core.model_dump(mode="json")},
    )

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        recorder = CognitiveEvidenceRecorder(path, include_text=True)
        recorder.record(resolution, sid=envelope.session_id, text="hello")
        payload = json.loads(path.read_text(encoding="utf-8"))

    packets = [
        SemanticArtifactPacket.model_validate(item)
        for item in payload["semantic_artifact_packets"]
    ]
    by_kind = {}
    for packet in packets:
        by_kind.setdefault(packet.ref.artifact_kind, []).append(packet)

    assert set(by_kind) == {
        "user_turn",
        "goal_interpretation",
        "responsibility",
        "goal_association",
        "goal",
        "planner_plan",
        "social_cognition",
        "communicative_act",
    }
    responsibility_packet = by_kind["responsibility"][0]
    assert {item.artifact_kind for item in responsibility_packet.envelope.parent_refs} == {
        "user_turn",
        "goal_interpretation",
    }
    goal_packet = by_kind["goal"][0]
    assert {item.artifact_kind for item in goal_packet.envelope.parent_refs} == {
        "goal_association",
        "responsibility",
    }
    talk_packet = by_kind["communicative_act"][0]
    assert {item.artifact_kind for item in talk_packet.envelope.parent_refs} == {
        "social_cognition",
        "responsibility",
        "goal",
    }


def test_cognitive_evidence_keeps_full_packets_behind_text_retention_policy() -> None:
    core, envelope = admitted_core("private hello", sid="sid-private-artifacts", language="en-US")
    resolution = CognitiveRuntimeResolution(
        mode="report_only", status="report_only", turn_envelope=envelope,
        metadata={"core_interpretation": core.model_dump(mode="json")},
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        recorder = CognitiveEvidenceRecorder(path, include_text=False)
        recorder.record(resolution, sid=envelope.session_id, text="private hello")
        payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["semantic_artifact_envelopes"]
    assert "semantic_artifact_packets" not in payload


def test_terminal_execution_outcome_lands_as_immutable_artifact() -> None:
    plan = execution_plan([("goal-1", ["completed"])], plan_id="plan-artifact-outcome")
    bundle = execution_bundle(plan, [("goal-1", ["completed"])])
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        recorder = CognitiveEvidenceRecorder(path, include_text=True)
        recorder.record_outcome(
            bundle,
            sid="sid-artifact-outcome",
            final_response=None,
            delivery_status="not_required",
            goal_state_results=[{"goal_id": "goal-1", "state": "completed"}],
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["event"] == "cognitive_execution_outcome"
    packet = SemanticArtifactPacket.model_validate(payload["semantic_artifact_packets"][0])
    assert packet.ref.artifact_kind == "execution_outcome"
    assert packet.ref.artifact_id == bundle.outcome_id
    assert packet.payload == bundle.model_dump(mode="json", exclude_none=True)
    assert payload["goal_state_results"] == [{"goal_id": "goal-1", "state": "completed"}]
