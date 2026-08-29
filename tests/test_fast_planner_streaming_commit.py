from __future__ import annotations

import json
from typing import Any

import pytest

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_prompt import (
    fast_advance_capability_prompt_projection,
    fast_advance_layered_prompt,
    fast_advance_semantic_capability_projection,
    fast_advance_streaming_capability_prompt_projection,
    fast_responsibility_decision_projection,
    fast_streaming_advance_system_prompt,
)
from agent.app.planner_schema import fast_streaming_advance_response_schema
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveStageFailure,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
    bind_presentation_commit_reference,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
)
from shared.chromie_contracts.plan import (
    FastPlannerStreamFailure,
    FastPlannerStreamTerminal,
    PresentationCommit,
)
from tests.test_cognitive_runtime_pr7 import (
    admitted_core,
    new_goal_association,
    respond_plan,
)


class _Catalog:
    def __init__(self, entries: list[CatalogCapability] | None = None) -> None:
        self.entries = list(entries or [])

    async def prompt_entries(self, *, scope: str, refresh: bool) -> list[Any]:
        del scope, refresh
        return self.entries


class _StreamingModel:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls = 0
        self.last_prompt: Any = None
        self.last_kwargs: dict[str, Any] = {}

    async def generate_stream(self, *args: Any, **kwargs: Any):
        self.last_prompt = args[0]
        self.last_kwargs = kwargs
        self.calls += 1
        for chunk in self.chunks:
            yield chunk

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        value = json.loads(text)
        assert isinstance(value, dict)
        return value


def _request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid="turn-stream",
        text="你好",
        language="zh-CN",
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref="reply",
                outcome="reply to the greeting",
                output_mode="speech",
                confidence=0.98,
            )
        ],
        interpretation_confidence=0.98,
        context={},
    )


def _valid_output() -> dict[str, Any]:
    return {
        "presentation_commit": {
            "activity": {
                "activity_id": "reply-now",
                "role": "complete_response",
                "text": "你好呀！",
                "timing": "parallel",
                "speech_act": "greeting",
                "source_responsibility_refs": ["reply"],
                "truth_stage": "context_grounded",
                "evidence_refs": [],
            },
            "auxiliary_activities": [],
        },
        "terminal_result": {
            "disposition": "respond",
            "coverage": "complete",
            "covered_responsibility_refs": ["reply"],
            "activities": [],
            "auxiliary_activities": [],
            "continuations": [],
            "confidence": 0.98,
            "unresolved": [],
            "reason_summary": "Greeting response is complete.",
        },
    }


def _wire_output(output: dict[str, Any]) -> str:
    return (
        "<presentation_commit>"
        + json.dumps(output["presentation_commit"], ensure_ascii=False)
        + "</presentation_commit>"
        + "<terminal_plan>"
        + json.dumps(output["terminal_result"], ensure_ascii=False)
        + "</terminal_plan>"
    )


def _body_request() -> tuple[CognitiveWorkRequest, CognitiveResponsibilityProposal]:
    responsibility = CognitiveResponsibilityProposal(
        local_ref="walk",
        outcome="walk forward for ten seconds",
        output_mode="body_action",
        bindings={"duration_s": 10},
        confidence=0.99,
    )
    return (
        CognitiveWorkRequest(
            sid="turn-stream-walk",
            text="向前走十秒",
            language="zh-CN",
            responsibilities=[responsibility],
            interpretation_confidence=0.99,
            context={},
        ),
        responsibility,
    )


def _walk_capability() -> dict[str, Any]:
    return {
        "capability_id": "soridormi.walk_forward",
        "description": "Walk the robot forward for the supplied duration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_s": {"type": "number", "minimum": 0.1},
            },
            "required": ["duration_s"],
            "additionalProperties": False,
        },
        "effects": ["locomotion"],
        "hints": {"semantic_type": "body_action"},
    }


def _walk_catalog_capability() -> CatalogCapability:
    return CatalogCapability(
        capability_id="soridormi.walk_forward",
        agent_id="capability_agent",
        description="Walk the robot forward for the supplied duration.",
        input_schema=_walk_capability()["input_schema"],
        effects=["locomotion"],
        available=True,
        interaction_executable=True,
        prompt_tier="common",
        hints={"semantic_type": "body_action"},
    )


def _look_at_person_catalog_capability() -> CatalogCapability:
    return CatalogCapability(
        capability_id="soridormi.look_at_person",
        agent_id="capability_agent",
        description="Look at a person identified by a trusted target reference.",
        input_schema={
            "type": "object",
            "properties": {
                "target_ref": {"type": "string", "minLength": 1},
            },
            "required": ["target_ref"],
            "additionalProperties": False,
        },
        effects=["physical_motion"],
        available=True,
        interaction_executable=True,
        prompt_tier="common",
        behavior_domains=["social_attention", "orientation"],
        can_run_parallel=True,
        parallel_metadata_declared=True,
        exclusive_group="body.head",
        resource_claims=["body.head"],
        hints={
            "argument_realization": {
                "person_addressee_target": {
                    "source_entity_type": "addressee",
                    "planner_owned": True,
                    "arguments": ["target_ref"],
                    "minimum_arguments": 1,
                    "contract": (
                        "Copy target_ref only from current trusted target evidence."
                    ),
                }
            }
        },
    )


def _nod_catalog_capability() -> CatalogCapability:
    return CatalogCapability(
        capability_id="soridormi.nod_yes",
        agent_id="capability_agent",
        description="Perform a bounded affirmative head nod.",
        input_schema={
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1}},
            "required": ["count"],
            "additionalProperties": False,
        },
        effects=["physical_motion"],
        available=True,
        interaction_executable=True,
        prompt_tier="common",
        can_run_parallel=True,
        parallel_metadata_declared=True,
        exclusive_group="body.head",
        resource_claims=["body.head"],
    )


def _blink_social_catalog_capability() -> CatalogCapability:
    return CatalogCapability(
        capability_id="soridormi.blink_eyes",
        agent_id="capability_agent",
        description="Blink as an optional visual social expression.",
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "default": 2}
            },
            "additionalProperties": False,
        },
        effects=["visual_expression"],
        available=True,
        interaction_executable=True,
        prompt_tier="common",
        behavior_domains=["social_attention"],
        can_run_parallel=True,
        parallel_metadata_declared=True,
        exclusive_group="visual.eyes",
        resource_claims=["visual.eyes"],
    )


def _look_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid="turn-stream-look",
        text="看着我三秒",
        language="zh-CN",
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref="look",
                outcome="look at the addressee",
                output_mode="body_action",
                bindings={"addressee": "我"},
                confidence=1.0,
            )
        ],
        interpretation_confidence=1.0,
        context={
            "active_user_target": {
                "source": "live_perception",
                "target_ref": "current_speaker",
                "relative_direction": "front",
                "confidence": 1.0,
                "evidence_refs": ["scenario:current-speaker"],
            }
        },
    )


def _look_output(*, target_ref: str) -> dict[str, Any]:
    return {
        "presentation_commit": {
            "activity": None,
            "auxiliary_activities": [],
        },
        "terminal_result": {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["look"],
            "activities": [
                {
                    "role": "capability",
                    "capability_id": "soridormi.look_at_person",
                    "activity_id": "look-at-speaker",
                    "args": {"target_ref": target_ref},
                    "timing": "sequential",
                    "source_responsibility_refs": ["look"],
                }
            ],
            "auxiliary_activities": [],
            "continuations": [],
            "confidence": 1.0,
            "unresolved": [],
            "reason_summary": "Look at the trusted current speaker target.",
        },
    }


def _structured_resource_catalog_capability() -> CatalogCapability:
    realization = {
        "physical_resource_entity": {
            "source_entity_type": "entity",
            "planner_owned": True,
            "arguments": ["resource"],
            "minimum_arguments": 1,
            "contract": "Conserve the exact entity inside resource.",
        },
        "physical_resource_location": {
            "source_entity_type": "location",
            "planner_owned": True,
            "arguments": ["source"],
            "minimum_arguments": 1,
            "contract": "Conserve the exact location inside source.",
        },
        "physical_resource_distance": {
            "source_entity_type": "distance",
            "planner_owned": True,
            "arguments": ["source"],
            "minimum_arguments": 1,
            "contract": "Conserve the exact distance inside source.",
        },
        "physical_resource_recipient": {
            "source_entity_type": "recipient",
            "planner_owned": True,
            "arguments": ["recipient"],
            "minimum_arguments": 1,
            "contract": "Conserve the exact recipient inside recipient.",
        },
    }
    return CatalogCapability(
        capability_id="soridormi.acquire_and_deliver_resource",
        agent_id="capability_agent",
        description="Acquire and deliver a physical resource.",
        input_schema={
            "type": "object",
            "properties": {
                "resource": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["physical_object"]},
                        "description": {"type": "string", "minLength": 1},
                    },
                    "required": ["kind", "description"],
                    "additionalProperties": False,
                },
                "source": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["known"]},
                        "description": {"type": "string"},
                        "bindings": {"type": "object"},
                    },
                    "required": ["status"],
                    "additionalProperties": False,
                },
                "recipient": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "minLength": 1},
                    },
                    "required": ["description"],
                    "additionalProperties": False,
                },
            },
            "required": ["resource", "source", "recipient"],
            "additionalProperties": False,
        },
        effects=["physical_motion", "resource_delivery"],
        available=True,
        interaction_executable=True,
        prompt_tier="common",
        hints={
            "semantic_scope": {
                "responsibility_type": "acquire_and_deliver_resource",
                "resource_kinds": ["physical_object"],
            },
            "argument_realization": realization,
        },
    )


def _structured_resource_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid="turn-stream-resource",
        text=(
            "there is a bottle of milk ahead of you about 50 meters, "
            "please bring it to me"
        ),
        language="en-US",
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref="fetch",
                outcome="acquire and deliver the resource",
                output_mode="body_action",
                bindings={
                    "entity": "bottle of milk",
                    "location": "ahead of you about 50 meters",
                    "distance": 50,
                    "recipient": "me",
                },
                confidence=1.0,
            )
        ],
        interpretation_confidence=1.0,
    )


def _structured_resource_output(*, recipient: str = "me") -> dict[str, Any]:
    return {
        "presentation_commit": {"activity": None, "auxiliary_activities": []},
        "terminal_result": {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["fetch"],
            "activities": [
                {
                    "role": "capability",
                    "capability_id": "soridormi.acquire_and_deliver_resource",
                    "activity_id": "fetch-milk",
                    "args": {
                        "resource": {
                            "kind": "physical_object",
                            "description": "bottle of milk",
                        },
                        "source": {
                            "status": "known",
                            "description": "ahead of you about 50 meters",
                            "bindings": {"distance": 50},
                        },
                        "recipient": {"description": recipient},
                    },
                    "timing": "sequential",
                    "source_responsibility_refs": ["fetch"],
                }
            ],
            "auxiliary_activities": [],
            "continuations": [],
            "confidence": 1.0,
            "unresolved": [],
            "reason_summary": "Acquire the resource and deliver it.",
        },
    }


def test_stream_prompt_teaches_exact_field_placement_and_two_frame_stop() -> None:
    request, responsibility = _body_request()
    capability = _walk_capability()
    response_schema = fast_streaming_advance_response_schema(
        [responsibility.local_ref],
        responsibilities=[responsibility],
        capabilities=[capability],
        auxiliary_social_capabilities=[],
        interpretation_unresolved=[],
        language="zh-CN",
    )

    projection = fast_advance_capability_prompt_projection([capability])
    semantic_projection = fast_advance_semantic_capability_projection([capability])
    streaming_projection = fast_advance_streaming_capability_prompt_projection(
        [capability]
    )
    prompt = str(
        fast_advance_layered_prompt(
            request,
            responsibilities=[responsibility],
            capabilities=[capability],
            response_schema=response_schema,
        )
    )
    system = fast_streaming_advance_system_prompt()

    assert "args_schema" in projection[0]
    assert "arguments" not in projection[0]
    assert "args_schema" not in semantic_projection[0]
    assert streaming_projection[0]["args_schema"] == capability["input_schema"]
    assert "AUTHORITATIVE FAST DECISION TABLE" in prompt
    assert "single exact argument authority" in prompt
    assert "reason_summary exists only once, at terminal_plan.reason_summary" in prompt
    assert "Never use arguments, effects, resource_claims" in prompt
    assert "perform_action for an embodied, media, vocal, or state-changing effect" in prompt
    assert "FINAL DECISION CHECKLIST" in prompt
    assert "A lone parallel Activity is always invalid" in prompt
    assert "never invent speech only to anchor optional decoration" in prompt
    assert "requested blink r1" in prompt
    assert "Stop immediately after" in prompt
    assert "EXACT MODEL-VISIBLE TAGGED WIRE FORMAT" in prompt
    assert "<presentation_commit>" in prompt
    assert "<terminal_plan>" in prompt
    assert json.dumps(
        response_schema["properties"]["presentation_commit"],
        ensure_ascii=False,
        separators=(",", ":"),
    ) in prompt
    assert "top-level JSON document" in system
    assert "repeated frame" in system


def test_stream_prompt_exposes_trusted_target_for_primary_capability_grounding() -> None:
    request, responsibility = _body_request()
    request.context["planner_auxiliary_social_context"] = {
        "eligible_capabilities": [],
        "target_evidence": {
            "available": True,
            "source": "live_perception",
            "target": {
                "target_ref": "current_speaker",
                "relative_direction": "front",
                "confidence": 1.0,
            },
        },
        "social_interaction_style": {},
        "recent_auxiliary_behavior_evidence": [],
        "max_activities": 0,
    }
    response_schema = fast_streaming_advance_response_schema(
        [responsibility.local_ref],
        responsibilities=[responsibility],
        capabilities=[_walk_capability()],
        auxiliary_social_capabilities=[],
        interpretation_unresolved=[],
        language="zh-CN",
    )

    prompt = str(
        fast_advance_layered_prompt(
            request,
            responsibilities=[responsibility],
            capabilities=[_walk_capability()],
            response_schema=response_schema,
        )
    )

    assert "Trusted semantic target evidence JSON" in prompt
    assert "current_speaker" in prompt
    assert "Copy the supplied target_ref exactly" in prompt
    assert "infer yaw/pitch" in prompt


def test_fast_decision_projection_localizes_coverage_bindings_and_relations() -> None:
    look = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="look at the person",
        output_mode="body_action",
        bindings={"entity": "me", "parallel_with": ["r2"]},
        confidence=1.0,
    )
    blink = CognitiveResponsibilityProposal(
        local_ref="r2",
        outcome="blink twice",
        output_mode="body_action",
        bindings={"count": 2, "parallel_with": "r1"},
        confidence=1.0,
    )

    projection = fast_responsibility_decision_projection([look, blink])

    assert projection == [
        {
            "ref": "r1",
            "outcome": "look at the person",
            "output_mode": "body_action",
            "semantic_bindings": {"entity": "me"},
            "relations": {"before": [], "after": [], "parallel_with": ["r2"]},
            "goal_relationship": "new",
            "target_goal_ids": [],
            "terminal_owner_required": True,
        },
        {
            "ref": "r2",
            "outcome": "blink twice",
            "output_mode": "body_action",
            "semantic_bindings": {"count": 2},
            "relations": {"before": [], "after": [], "parallel_with": ["r1"]},
            "goal_relationship": "new",
            "target_goal_ids": [],
            "terminal_owner_required": True,
        },
    ]


def test_stream_schema_keeps_ordered_speech_in_terminal_and_compacts_args() -> None:
    body = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="nod twice",
        output_mode="body_action",
        bindings={"count": 2},
        confidence=1.0,
    )
    speech = CognitiveResponsibilityProposal(
        local_ref="r2",
        outcome="say hello",
        output_mode="speech",
        bindings={"after": ["r1"]},
        confidence=1.0,
    )
    schema = fast_streaming_advance_response_schema(
        ["r1", "r2"],
        responsibilities=[body, speech],
        capabilities=[_walk_capability()],
        auxiliary_social_capabilities=[],
        interpretation_unresolved=[],
        language="en-US",
    )

    activity_choices = schema["properties"]["presentation_commit"]["properties"][
        "activity"
    ]["anyOf"]
    assert not any(
        "progress_kind" not in branch.get("properties", {})
        and "text" in branch.get("properties", {})
        for branch in activity_choices
    )
    terminal = schema["properties"]["terminal_result"]
    terminal_branches = terminal["properties"]["activities"]["items"]["oneOf"]
    capability_branch = next(
        branch
        for branch in terminal_branches
        if branch.get("properties", {}).get("role", {}).get("enum")
        == ["capability"]
    )
    assert capability_branch["properties"]["args"] == {
        "type": "object",
        "additionalProperties": True,
    }
    complete_response_branch = next(
        branch
        for branch in terminal_branches
        if branch.get("properties", {}).get("role", {}).get("enum")
        == ["complete_response"]
    )
    assert complete_response_branch["properties"]["source_responsibility_refs"][
        "items"
    ]["enum"] == ["r2"]
    assert terminal["properties"]["auxiliary_activities"] == {
        "type": "array",
        "enum": [[]],
    }


def test_ordered_terminal_speech_can_own_distinct_social_decoration() -> None:
    body = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="nod twice",
        output_mode="body_action",
        bindings={"count": 2},
        confidence=1.0,
    )
    speech = CognitiveResponsibilityProposal(
        local_ref="r2",
        outcome="say hello",
        output_mode="speech",
        bindings={"after": ["r1"]},
        confidence=1.0,
    )
    auxiliary = {
        "capability_id": "soridormi.blink_eyes",
        "description": "Blink as an optional visual social expression.",
        "input_schema": _blink_social_catalog_capability().input_schema,
    }
    schema = fast_streaming_advance_response_schema(
        ["r1", "r2"],
        responsibilities=[body, speech],
        capabilities=[],
        auxiliary_social_capabilities=[auxiliary],
        interpretation_unresolved=[],
        language="en-US",
    )

    presentation_auxiliary = schema["properties"]["presentation_commit"][
        "properties"
    ]["auxiliary_activities"]
    terminal_auxiliary = schema["properties"]["terminal_result"]["properties"][
        "auxiliary_activities"
    ]

    assert presentation_auxiliary["maxItems"] == 1
    assert terminal_auxiliary["maxItems"] == 1
    assert "soridormi.blink_eyes" in json.dumps(terminal_auxiliary)


def test_stream_schema_exposes_only_reachable_phase_specific_branches() -> None:
    _, responsibility = _body_request()
    schema = fast_streaming_advance_response_schema(
        [responsibility.local_ref],
        responsibilities=[responsibility],
        capabilities=[_walk_capability()],
        auxiliary_social_capabilities=[],
        interpretation_unresolved=[],
        language="zh-CN",
    )

    presentation = schema["properties"]["presentation_commit"]
    terminal = schema["properties"]["terminal_result"]
    terminal_items = terminal["properties"]["activities"]["items"]
    serialized = json.dumps(schema)

    assert "$defs" not in schema
    assert "$ref" not in serialized
    assert len(serialized) < 8000
    assert "reason_summary" not in json.dumps(presentation)
    assert "reason_summary" in terminal["properties"]
    assert "allOf" not in terminal
    assert "discriminator" not in terminal_items
    assert presentation["properties"]["auxiliary_activities"]["enum"] == [[]]
    assert terminal["properties"]["auxiliary_activities"]["enum"] == [[]]
    capability_branch = next(
        branch
        for branch in terminal_items["oneOf"]
        if branch.get("properties", {}).get("role", {}).get("enum")
        == ["capability"]
    )
    assert "timing" in capability_branch["required"]


@pytest.mark.asyncio
async def test_commit_is_emitted_before_terminal_from_one_model_call() -> None:
    payload = _wire_output(_valid_output())
    boundary = payload.index("</presentation_commit>") + len(
        "</presentation_commit>"
    )
    model = _StreamingModel([payload[:boundary], payload[boundary:]])
    resolver = FastPlannerResolver(model, _Catalog())  # type: ignore[arg-type]

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert model.calls == 1
    assert model.last_kwargs["response_format"] == "text"
    assert "EXACT MODEL-VISIBLE TAGGED WIRE FORMAT" in str(model.last_prompt)
    assert isinstance(frames[0], PresentationCommit)
    assert frames[0].activity is not None
    assert frames[0].activity.text == "你好呀！"
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    assert frames[1].presentation_commit_id == frames[0].commit_id
    assert frames[1].advance.activities[0] == frames[0].activity
    assert frames[1].advance.metadata["semantic_result_call_count"] == 1


@pytest.mark.asyncio
async def test_failure_after_commit_preserves_commit_and_blocks_terminal_work() -> None:
    payload = _wire_output(_valid_output())
    boundary = payload.index("</presentation_commit>") + len(
        "</presentation_commit>"
    )
    model = _StreamingModel([payload[:boundary], "<terminal_plan>{"])
    resolver = FastPlannerResolver(model, _Catalog())  # type: ignore[arg-type]

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert frames[1].failure_stage == "after_commit"
    assert frames[1].presentation_commit_id == frames[0].commit_id
    assert not any(isinstance(frame, FastPlannerStreamTerminal) for frame in frames)


@pytest.mark.asyncio
async def test_terminal_cannot_duplicate_or_reword_committed_speech() -> None:
    output = _valid_output()
    output["terminal_result"]["activities"] = [
        {
            **output["presentation_commit"]["activity"],
            "activity_id": "second-reply",
            "text": "另一个回答",
        }
    ]
    payload = _wire_output(output)
    model = _StreamingModel([payload])
    resolver = FastPlannerResolver(model, _Catalog())  # type: ignore[arg-type]

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert frames[1].failure_stage == "after_commit"
    assert "duplicated presentation speech" in frames[1].reason


@pytest.mark.asyncio
async def test_ordered_requested_speech_is_authored_once_after_terminal_work() -> None:
    body = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="walk forward for ten seconds",
        output_mode="body_action",
        bindings={"duration_s": 10},
        confidence=1.0,
    )
    speech = CognitiveResponsibilityProposal(
        local_ref="r2",
        outcome="say hello",
        output_mode="speech",
        bindings={"after": ["r1"]},
        confidence=1.0,
    )
    request = CognitiveWorkRequest(
        sid="turn-ordered-work-speech",
        text="向前走十秒，再说你好",
        language="zh-CN",
        responsibilities=[body, speech],
        interpretation_confidence=1.0,
        context={},
    )
    output = {
        "presentation_commit": {
            "activity": None,
            "auxiliary_activities": [],
        },
        "terminal_result": {
            "disposition": "mixed",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1", "r2"],
            "activities": [
                {
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "activity_id": "walk-first",
                    "args": {"duration_s": 10},
                    "timing": "sequential",
                    "source_responsibility_refs": ["r1"],
                },
                {
                    "role": "complete_response",
                    "activity_id": "say-after-walk",
                    "text": "你好！",
                    "timing": "sequential",
                    "speech_act": "respond",
                    "source_responsibility_refs": ["r2"],
                    "truth_stage": "context_grounded",
                    "evidence_refs": [],
                },
            ],
            "auxiliary_activities": [],
            "continuations": [],
            "confidence": 1.0,
            "unresolved": [],
            "reason_summary": "Complete the requested work in order.",
        },
    }
    resolver = FastPlannerResolver(
        _StreamingModel([_wire_output(output)]),
        _Catalog([_walk_catalog_capability()]),  # type: ignore[arg-type]
    )

    frames = [frame async for frame in resolver.stream_advance(request)]

    assert isinstance(frames[0], PresentationCommit)
    assert frames[0].activity is None
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    assert [activity.role for activity in frames[1].advance.activities] == [
        "capability",
        "complete_response",
    ]
    assert [activity.timing for activity in frames[1].advance.activities] == [
        "sequential",
        "sequential",
    ]


@pytest.mark.asyncio
async def test_ordered_terminal_response_retains_its_own_social_decoration() -> None:
    body = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="nod twice",
        output_mode="body_action",
        bindings={"count": 2},
        confidence=1.0,
    )
    speech = CognitiveResponsibilityProposal(
        local_ref="r2",
        outcome="say hello",
        output_mode="speech",
        bindings={"after": ["r1"]},
        confidence=1.0,
    )
    request = CognitiveWorkRequest(
        sid="turn-ordered-nod-speech-decoration",
        text="点两下头，然后跟我说声你好",
        language="zh-CN",
        responsibilities=[body, speech],
        interpretation_confidence=1.0,
        context={},
    )
    output = {
        "presentation_commit": {
            "activity": None,
            "auxiliary_activities": [],
        },
        "terminal_result": {
            "disposition": "mixed",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1", "r2"],
            "activities": [
                {
                    "role": "capability",
                    "capability_id": "soridormi.nod_yes",
                    "activity_id": "nod-first",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_responsibility_refs": ["r1"],
                },
                {
                    "role": "complete_response",
                    "activity_id": "hello-after-nod",
                    "text": "你好呀！",
                    "timing": "sequential",
                    "speech_act": "respond",
                    "source_responsibility_refs": ["r2"],
                    "truth_stage": "context_grounded",
                    "evidence_refs": [],
                },
            ],
            "auxiliary_activities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "auxiliary_activity_id": "blink-with-hello",
                    "anchor_kind": "communicative_act",
                    "anchor_id": "hello-after-nod",
                    "args": {"count": 2},
                    "execution_role": "social_decoration",
                    "timing": "parallel",
                    "social_function": "engagement",
                    "target": {"source": "none"},
                }
            ],
            "continuations": [],
            "confidence": 1.0,
            "unresolved": [],
            "reason_summary": "Nod first, then greet with optional expression.",
        },
    }
    resolver = FastPlannerResolver(
        _StreamingModel([_wire_output(output)]),
        _Catalog(
            [
                _nod_catalog_capability(),
                _blink_social_catalog_capability(),
            ]
        ),  # type: ignore[arg-type]
    )

    frames = [frame async for frame in resolver.stream_advance(request)]

    assert isinstance(frames[0], PresentationCommit)
    assert frames[0].activity is None
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    assert frames[1].advance.auxiliary_activities[0].anchor_id == "hello-after-nod"


@pytest.mark.asyncio
async def test_declared_addressee_target_realization_accepts_exact_trusted_ref() -> None:
    model = _StreamingModel([_wire_output(_look_output(target_ref="current_speaker"))])
    resolver = FastPlannerResolver(
        model,
        _Catalog([_look_at_person_catalog_capability()]),  # type: ignore[arg-type]
    )

    frames = [frame async for frame in resolver.stream_advance(_look_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    assert frames[1].advance.activities[0].args == {
        "target_ref": "current_speaker"
    }
    assert "Trusted semantic target evidence JSON" in str(model.last_prompt)
    assert "person_addressee_target" in str(model.last_prompt)


@pytest.mark.asyncio
async def test_required_target_ref_uses_trusted_evidence_without_binding_mapping() -> None:
    capability = _look_at_person_catalog_capability().model_copy(
        update={"hints": {}}
    )
    model = _StreamingModel([_wire_output(_look_output(target_ref="current_speaker"))])
    resolver = FastPlannerResolver(
        model,
        _Catalog([capability]),  # type: ignore[arg-type]
    )

    frames = [frame async for frame in resolver.stream_advance(_look_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    assert frames[1].advance.activities[0].args["target_ref"] == "current_speaker"


@pytest.mark.asyncio
async def test_declared_target_realization_rejects_mismatched_trusted_ref() -> None:
    resolver = FastPlannerResolver(
        _StreamingModel([_wire_output(_look_output(target_ref="invented_person"))]),
        _Catalog([_look_at_person_catalog_capability()]),  # type: ignore[arg-type]
    )

    frames = [frame async for frame in resolver.stream_advance(_look_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert frames[1].failure_stage == "after_commit"
    assert "must copy exact current trusted target evidence" in frames[1].reason


@pytest.mark.asyncio
async def test_declared_structured_resource_realization_accepts_exact_gi_values() -> None:
    resolver = FastPlannerResolver(
        _StreamingModel([_wire_output(_structured_resource_output())]),
        _Catalog([_structured_resource_catalog_capability()]),  # type: ignore[arg-type]
    )

    frames = [
        frame async for frame in resolver.stream_advance(_structured_resource_request())
    ]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    args = frames[1].advance.activities[0].args
    assert args["resource"]["description"] == "bottle of milk"
    assert args["source"]["bindings"]["distance"] == 50
    assert args["recipient"]["description"] == "me"


@pytest.mark.asyncio
async def test_declared_structured_resource_realization_rejects_lost_gi_value() -> None:
    resolver = FastPlannerResolver(
        _StreamingModel(
            [_wire_output(_structured_resource_output(recipient="requester"))]
        ),
        _Catalog([_structured_resource_catalog_capability()]),  # type: ignore[arg-type]
    )

    frames = [
        frame async for frame in resolver.stream_advance(_structured_resource_request())
    ]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert "structured resource realization omitted exact GI bindings" in frames[1].reason
    assert "recipient=recipient" in frames[1].reason


@pytest.mark.asyncio
async def test_terminal_before_commit_fails_silently() -> None:
    payload = (
        "<terminal_plan>"
        + json.dumps(_valid_output()["terminal_result"], ensure_ascii=False)
        + "</terminal_plan>"
    )
    resolver = FastPlannerResolver(  # type: ignore[arg-type]
        _StreamingModel([payload]),
        _Catalog(),
    )

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert frames[0].failure_stage == "before_commit"
    assert frames[0].presentation_commit_id is None


@pytest.mark.asyncio
async def test_content_after_terminal_frame_fails_after_preserving_commit() -> None:
    payload = _wire_output(_valid_output()) + "unexpected trailing text"
    resolver = FastPlannerResolver(  # type: ignore[arg-type]
        _StreamingModel([payload]),
        _Catalog(),
    )

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert frames[1].failure_stage == "after_commit"
    assert "after </terminal_plan>" in frames[1].reason


@pytest.mark.asyncio
async def test_unclosed_presentation_frame_never_commits() -> None:
    payload = (
        "<presentation_commit>"
        + json.dumps(_valid_output()["presentation_commit"], ensure_ascii=False)
    )
    resolver = FastPlannerResolver(  # type: ignore[arg-type]
        _StreamingModel([payload]),
        _Catalog(),
    )

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert frames[0].failure_stage == "before_commit"
    assert frames[0].presentation_commit_id is None


@pytest.mark.asyncio
async def test_duplicate_presentation_frame_is_rejected_after_first_commit() -> None:
    output = _valid_output()
    presentation = (
        "<presentation_commit>"
        + json.dumps(output["presentation_commit"], ensure_ascii=False)
        + "</presentation_commit>"
    )
    payload = presentation + presentation + (
        "<terminal_plan>"
        + json.dumps(output["terminal_result"], ensure_ascii=False)
        + "</terminal_plan>"
    )
    resolver = FastPlannerResolver(  # type: ignore[arg-type]
        _StreamingModel([payload]),
        _Catalog(),
    )

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert frames[1].failure_stage == "after_commit"
    assert "<terminal_plan>" in frames[1].reason


def test_presentation_commit_cannot_contain_work_or_unanchored_decoration() -> None:
    with pytest.raises(ValueError):
        PresentationCommit.model_validate(
            {
                "commit_id": "commit",
                "turn_id": "turn",
                "activity": None,
                "auxiliary_activities": [
                    {
                        "auxiliary_activity_id": "body-work",
                        "anchor_kind": "plan_step",
                        "anchor_id": "step",
                        "capability_id": "soridormi.nod",
                    }
                ],
            }
        )


def test_every_terminal_plan_binds_the_exact_stream_commit() -> None:
    bound = bind_presentation_commit_reference(
        respond_plan(),
        commit_id="commit-terminal-plan",
    )
    assert bound.metadata["presentation_commit_id"] == "commit-terminal-plan"

    with pytest.raises(CognitiveStageFailure):
        bind_presentation_commit_reference(
            bound,
            commit_id="different-commit",
        )


@pytest.mark.asyncio
async def test_runtime_keeps_committed_speech_but_never_dispatches_work_after_failure() -> None:
    commit = PresentationCommit(
        commit_id="commit-runtime-failure",
        turn_id="turn-runtime-failure",
        activity={
            "activity_id": "progress-runtime-failure",
            "role": "progress",
            "text": "我来处理。",
            "progress_kind": "acknowledge_work",
            "source_responsibility_refs": ["r1"],
        },
    )

    class Client:
        async def resolve_goal_association(self, *args: Any, **kwargs: Any):
            del args, kwargs
            return new_goal_association()

        async def stream_fast_advance(self, *args: Any, **kwargs: Any):
            del args, kwargs
            yield commit
            yield FastPlannerStreamFailure(
                turn_id=commit.turn_id,
                failure_stage="after_commit",
                presentation_commit_id=commit.commit_id,
                failure_class="stream_provider_error",
                failure_domain="inference_transport",
            )

    class Runtime:
        def __init__(self) -> None:
            self.spoken: list[str] = []
            self.work_dispatch_count = 0

        async def start_fast_planner_communicative_act(
            self,
            activity: Any,
            **kwargs: Any,
        ) -> object:
            del kwargs
            self.spoken.append(activity.text)
            return object()

        async def start_fast_planner_capability_activities(
            self,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            del args, kwargs
            self.work_dispatch_count += 1

    runtime = Runtime()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Client(),  # type: ignore[arg-type]
        adapter=CanonicalPlanRuntimeAdapter(runtime),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    core, envelope = admitted_core(
        "处理一下",
        sid=commit.turn_id,
        language="zh-CN",
    )

    resolution = await coordinator.resolve(
        object(),
        text="处理一下",
        sid=commit.turn_id,
        core_interpretation=core,
        turn_envelope=envelope,
        context={"history": []},
        history=[],
        language="zh-CN",
    )

    assert resolution.status == "error"
    assert runtime.spoken == ["我来处理。"]
    assert runtime.work_dispatch_count == 0
    assert resolution.metadata["failure_stage"] == "fast_planner_stream"
    assert resolution.metadata["presentation_commit"]["commit_id"] == commit.commit_id
