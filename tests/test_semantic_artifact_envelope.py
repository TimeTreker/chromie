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
        authority="user_meaning_interpretation",
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
        {"result": "ok"}, artifact_kind="user_meaning_interpretation", artifact_id="turn-1",
        authority="user_meaning_interpretation", session_id="sid-1", turn_id="turn-1",
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
        "user_meaning_interpretation",
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
        "user_meaning_interpretation",
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
        from shared.chromie_contracts.interaction import CapabilityTrace, CapabilityTraceEvent

        trace = CapabilityTrace(
            interaction_id=bundle.interaction_id,
            request_id="request-provider-realization",
            capability_id="soridormi.turn_in_place",
            provider_id="soridormi.mcp",
            events=[CapabilityTraceEvent(
                type="provider_realization",
                data={
                    "semantic_args": {"direction": "left"},
                    "provider_args": {"yaw_radps": 0.12},
                    "semantic_facade_applied": True,
                },
            )],
        )
        recorder.record_outcome(
            bundle,
            sid="sid-artifact-outcome",
            final_response=None,
            delivery_status="not_required",
            goal_state_results=[{"goal_id": "goal-1", "state": "completed"}],
            capability_traces=[trace],
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["event"] == "cognitive_execution_outcome"
    packet = SemanticArtifactPacket.model_validate(payload["semantic_artifact_packets"][0])
    assert packet.ref.artifact_kind == "execution_outcome"
    assert packet.ref.artifact_id == bundle.outcome_id
    assert packet.payload == bundle.model_dump(mode="json", exclude_none=True)
    assert payload["goal_state_results"] == [{"goal_id": "goal-1", "state": "completed"}]
    assert payload["provider_realizations"] == [{
        "trace_id": trace.trace_id,
        "request_id": trace.request_id,
        "capability_id": "soridormi.turn_in_place",
        "provider_id": "soridormi.mcp",
        "timestamp": trace.events[0].timestamp.isoformat(),
        "semantic_args": {"direction": "left"},
        "provider_args": {"yaw_radps": 0.12},
        "semantic_facade_applied": True,
    }]


def test_work_request_binds_exact_user_turn_gi_and_responsibility_lineage() -> None:
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.semantic_artifact import (
        merge_semantic_artifact_lineage,
        semantic_artifact_ref,
    )

    core, envelope = admitted_core("walk left", sid="sid-lineage", language="en-US")
    lineage = merge_semantic_artifact_lineage(
        semantic_artifact_ref(envelope, artifact_kind="user_turn", artifact_id=envelope.turn_id),
        semantic_artifact_ref(core, artifact_kind="user_meaning_interpretation", artifact_id=core.turn_id),
        [
            semantic_artifact_ref(
                item,
                artifact_kind="responsibility",
                artifact_id=f"{core.turn_id}:{item.local_ref}",
            )
            for item in core.responsibilities
        ],
    )
    context = {
        "user_turn_envelope": envelope.model_dump(mode="json"),
        "core_interpretation": core.model_dump(mode="json"),
        "semantic_artifact_lineage": lineage.model_dump(mode="json"),
    }
    request = CognitiveWorkRequest(
        sid=envelope.session_id,
        text=envelope.normalized_input.text,
        language=envelope.normalized_input.language,
        responsibilities=list(core.responsibilities),
        interpretation_confidence=core.confidence,
        meaning_uncertainties=list(core.meaning_uncertainties),
        context=context,
    )
    assert request.semantic_artifact_lineage == lineage

    corrupted = core.model_dump(mode="json")
    corrupted["responsibilities"][0]["outcome"] = "walk right"
    with pytest.raises(ValueError, match="lineage digest mismatch"):
        CognitiveWorkRequest(
            sid=envelope.session_id,
            text=envelope.normalized_input.text,
            language=envelope.normalized_input.language,
            responsibilities=list(core.responsibilities),
            interpretation_confidence=core.confidence,
            meaning_uncertainties=list(core.meaning_uncertainties),
            context={**context, "core_interpretation": corrupted},
        )


def test_social_lineage_is_transport_metadata_not_model_prompt_content() -> None:
    from agent.app.social_cognition import social_cognition_prompt
    from shared.chromie_contracts.semantic_artifact import (
        merge_semantic_artifact_lineage,
        semantic_artifact_ref,
    )
    from shared.chromie_contracts.social_cognition import SocialCognitionRequest

    responsibility = CognitiveResponsibilityProposal(
        local_ref="r1", outcome="Respond to the greeting.", output_mode="speech", confidence=1.0,
    )
    lineage = merge_semantic_artifact_lineage(
        semantic_artifact_ref(
            responsibility,
            artifact_kind="responsibility",
            artifact_id="turn-prompt:r1",
        )
    )
    request = SocialCognitionRequest(
        request_id="sc-prompt-lineage",
        trigger="interpretation",
        source_refs=["turn-prompt"],
        responsibilities=[responsibility],
        source_turn={
            "schema_version": 1,
            "turn_id": "turn-prompt",
            "original_text": "hello",
            "original_text_sha256": "0" * 64,
            "language": "en-US",
            "authority": "read_only_source_provenance",
        },
        context={
            "interaction_context": {"events": [], "already_spoken": [], "pending_speech": []},
            "semantic_artifact_lineage": lineage.model_dump(mode="json"),
        },
    )
    prompt = social_cognition_prompt(request, [], num_ctx=8192)
    assert "semantic_artifact_lineage" not in prompt
    assert lineage.refs[0].payload_sha256 not in prompt


def test_plan_lineage_reaches_interaction_and_capability_runtime() -> None:
    import asyncio

    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from shared.chromie_contracts.semantic_artifact import (
        SemanticArtifactLineage,
        semantic_artifact_ref,
    )
    from tests.test_cognitive_runtime_pr7 import FakeRuntime, blink_definition, execute_plan

    plan = execute_plan()
    response = asyncio.run(
        CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])).build_execution_only_response(
            plan=plan,
            session_id="sid-plan-lineage",
            language="en-US",
            context={},
        )
    )
    expected = semantic_artifact_ref(
        plan, artifact_kind="planner_plan", artifact_id=plan.plan_id,
    )
    response_lineage = SemanticArtifactLineage.model_validate(
        response.metadata["semantic_artifact_lineage"]
    )
    response_lineage.require(expected)
    assert len(response.capabilities) == 1
    capability_lineage = SemanticArtifactLineage.model_validate(
        response.capabilities[0].metadata["semantic_artifact_lineage"]
    )
    capability_lineage.require(expected)


def test_live_turn_lineage_reaches_final_interaction_without_model_bookkeeping() -> None:
    import asyncio

    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter,
        CognitiveRuntimePolicy,
        GoalDrivenRuntimeCoordinator,
    )
    from shared.chromie_contracts.semantic_artifact import SemanticArtifactLineage
    from tests.test_cognitive_runtime_pr7 import (
        FakeRuntime,
        ScriptedClient,
        admitted_core,
        new_goal_association,
        respond_plan,
    )

    client = ScriptedClient(
        association=new_goal_association(),
        fast_plans=[respond_plan()],
    )
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=client,
        adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    core, envelope = admitted_core("hello", sid="sid-live-lineage", language="zh-CN")
    result = asyncio.run(
        coordinator.resolve(
            object(),
            text="hello",
            sid="sid-live-lineage",
            core_interpretation=core,
            context={"history": [], "active_goal_snapshots": []},
            history=[],
            language="zh-CN",
            turn_envelope=envelope,
        )
    )

    assert result.status == "applied"
    assert result.interaction_response is not None
    lineage = SemanticArtifactLineage.model_validate(
        result.interaction_response.metadata["semantic_artifact_lineage"]
    )
    assert {item.artifact_kind for item in lineage.refs} == {
        "user_turn",
        "user_meaning_interpretation",
        "responsibility",
        "goal_association",
        "goal",
        "planner_plan",
        "social_cognition",
        "communicative_act",
    }
