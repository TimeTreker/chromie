from __future__ import annotations

import json
from typing import Any

import pytest

from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_prompt import (
    fast_advance_capability_prompt_projection,
    fast_advance_layered_prompt,
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
    async def prompt_entries(self, *, scope: str, refresh: bool) -> list[Any]:
        del scope, refresh
        return []


class _StreamingModel:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls = 0

    async def generate_stream(self, *args: Any, **kwargs: Any):
        del args, kwargs
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


def test_stream_prompt_teaches_exact_field_placement_and_one_object_stop() -> None:
    request, responsibility = _body_request()
    capability = _walk_capability()

    projection = fast_advance_capability_prompt_projection([capability])
    prompt = str(
        fast_advance_layered_prompt(
            request,
            responsibilities=[responsibility],
            capabilities=[capability],
        )
    )
    system = fast_streaming_advance_system_prompt()

    assert "args_schema" in projection[0]
    assert "arguments" not in projection[0]
    assert "reason_summary exists only once, at terminal_result.reason_summary" in prompt
    assert "Never use arguments, effects, resource_claims" in prompt
    assert "perform_action for an embodied, media, vocal, or state-changing effect" in prompt
    assert "Stop immediately after" in prompt
    assert "repeated object" in system


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

    definitions = schema["$defs"]
    presentation = schema["properties"]["presentation_commit"]
    terminal = schema["properties"]["terminal_result"]
    terminal_items = terminal["properties"]["activities"]["items"]

    assert "Presentation_FastPlannerCompleteResponseAct" not in definitions
    assert "Terminal_FastPlannerProgressAct" not in definitions
    assert "Terminal_FastPlannerCompleteResponseAct" not in definitions
    assert "reason_summary" not in json.dumps(presentation)
    assert all(
        "reason_summary" not in value.get("properties", {})
        for value in definitions.values()
        if isinstance(value, dict)
    )
    assert "reason_summary" in terminal["properties"]
    assert "allOf" not in terminal
    assert "discriminator" not in terminal_items

    refs: set[str] = set()

    def collect_refs(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                refs.add(ref.rsplit("/", 1)[-1])
            for value in node.values():
                collect_refs(value)
        elif isinstance(node, list):
            for value in node:
                collect_refs(value)

    collect_refs(schema)
    assert refs <= set(definitions)


@pytest.mark.asyncio
async def test_commit_is_emitted_before_terminal_from_one_model_call() -> None:
    payload = json.dumps(_valid_output(), ensure_ascii=False)
    boundary = payload.index('}, "terminal_result"') + 1
    model = _StreamingModel([payload[:boundary], payload[boundary:]])
    resolver = FastPlannerResolver(model, _Catalog())  # type: ignore[arg-type]

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert model.calls == 1
    assert isinstance(frames[0], PresentationCommit)
    assert frames[0].activity is not None
    assert frames[0].activity.text == "你好呀！"
    assert isinstance(frames[1], FastPlannerStreamTerminal)
    assert frames[1].presentation_commit_id == frames[0].commit_id
    assert frames[1].advance.activities[0] == frames[0].activity
    assert frames[1].advance.metadata["semantic_result_call_count"] == 1


@pytest.mark.asyncio
async def test_failure_after_commit_preserves_commit_and_blocks_terminal_work() -> None:
    payload = json.dumps(_valid_output(), ensure_ascii=False)
    boundary = payload.index('}, "terminal_result"') + 1
    model = _StreamingModel([payload[:boundary], ', "terminal_result": {'])
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
    payload = json.dumps(output, ensure_ascii=False)
    model = _StreamingModel([payload])
    resolver = FastPlannerResolver(model, _Catalog())  # type: ignore[arg-type]

    frames = [frame async for frame in resolver.stream_advance(_request())]

    assert isinstance(frames[0], PresentationCommit)
    assert isinstance(frames[1], FastPlannerStreamFailure)
    assert frames[1].failure_stage == "after_commit"
    assert "duplicated presentation speech" in frames[1].reason


@pytest.mark.asyncio
async def test_terminal_before_commit_fails_silently() -> None:
    payload = json.dumps(
        {"terminal_result": _valid_output()["terminal_result"]},
        ensure_ascii=False,
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
