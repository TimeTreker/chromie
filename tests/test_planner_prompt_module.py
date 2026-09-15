from __future__ import annotations

import asyncio
import copy
import json

import pytest

from agent.app import deep_planner, fast_planner, planner_prompt
from tests.cognitive_work_test_support import cognitive_work_request
from agent.app.planner_context import planner_goal_context
from benchmarks.datasets.fast_planner_daily_life.qualification import StaticCatalog
from shared.chromie_contracts.goal import GoalAssociation, GoalAssociationResolution
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.plan import FastPlannerStreamFailure


def test_planner_prompt_module_stays_projection_only() -> None:
    namespace = vars(planner_prompt)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "CanonicalPlan",
        "CapabilityRuntime",
        "GoalAssociationResolution",
        "validate_planner_model_output",
        "materialize_planner_metadata",
    ):
        assert forbidden not in namespace

    assert planner_prompt.fast_plan_prompt.__module__ == "agent.app.planner_prompt"
    assert planner_prompt.deep_plan_prompt.__module__ == "agent.app.planner_prompt"
    assert planner_prompt.fast_streaming_advance_system_prompt.__module__ == (
        "agent.app.planner_prompt"
    )

def test_fast_and_deep_resolvers_do_not_reown_prompt_mechanics() -> None:
    for resolver, removed in (
        (
            fast_planner.FastPlannerResolver,
            (
                "_first_response_truth_system_prompt",
                "_first_response_truth_prompt",
                "_first_response_system_prompt",
                "_first_response_prompt",
                "_prompt",
                "_advance_layered_prompt",
                "_advance_capability_prompt_projection",
                "_advance_system_prompt",
                "_layered_prompt",
                "_system_prompt",
                "_repair_system_prompt",
            ),
        ),
        (
            deep_planner.DeepPlannerResolver,
            (
                "_prompt",
                "_layered_prompt",
                "_prioritize_capability_contracts",
                "_prompt_capability_contract",
                "_system_prompt",
                "_revision_system_prompt",
            ),
        ),
    ):
        for name in removed:
            assert not hasattr(resolver, name)

def test_fast_prompt_keeps_supportive_speech_grounded() -> None:
    request = cognitive_work_request(
        sid="supportive-speech-grounding",
        text="Please encourage me.",
        language="en-US",
        context={
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": "goal-encouragement",
                        "description": "Give one encouraging sentence.",
                        "metadata": {"output_mode": "speech"},
                    },
                    {
                        "goal_id": "goal-blink",
                        "description": "Blink twice.",
                        "metadata": {"output_mode": "body_action"},
                    },
                ],
            }
        },
    )

    prompt = planner_prompt.fast_plan_prompt(request, [], response_schema={})

    assert "SC will compose the actual words" in prompt
    assert "supplied context/Evidence" in prompt



def _retained_request(*, count=1, language="en-US", detail="Explain this topic."):
    goals = [
        SemanticGoal(
            goal_id=f"goal-{index}", description=f"{detail} REQUIRED_DETAIL_{index}",
            source_text=detail, success_criteria=[detail],
            object={"bindings": {"topic": f"topic-{index}"}},
            constraints={"answer_shape": "comparison"},
            metadata={"output_mode": "speech"},
        ) for index in range(count)
    ]
    association = GoalAssociationResolution(
        turn_id="required-inputs", resolution_status="resolved", confidence=1.0,
        associations=[GoalAssociation(
            association_id=f"association-{index}", relationship="continue",
            target_goal_ids=[goal.goal_id], confidence=1.0,
        ) for index, goal in enumerate(goals)],
    )
    return cognitive_work_request(
        sid="required-inputs", text="Continue." if language == "en-US" else "继续。",
        language=language,
        context={
            "goal_association_resolution": association.model_dump(mode="json"),
            "active_goal_snapshots": [
                {"goal_id": goal.goal_id, "goal": goal.model_dump(mode="json", exclude_defaults=True)}
                for goal in goals
            ],
        },
    )


def _render_required(request, variant):
    kwargs = {"response_schema": {}}
    if variant.startswith("deep"):
        kwargs["expected_goal_ids"] = list(planner_goal_context(request.context).expected_goal_ids)
    return str(getattr(planner_prompt, variant)(request, [], **kwargs))


@pytest.mark.parametrize("variant", ["fast_plan_prompt", "fast_layered_prompt", "fast_advance_layered_prompt"])
def test_fast_catalog_is_lossless_with_transport_owned_budget(variant):
    from unittest.mock import patch
    from agent.app.clients.ollama_client import OllamaClient, OllamaGenerationError

    request = _retained_request(count=1)
    catalog = [{"capability_id": f"provider.action_{index}", "description": "Exact applicability. " * 50,
                "input_schema": {"type": "object", "properties": {"duration_s": {"type": "number", "maximum": 20}}}}
               for index in range(20)]
    encoded = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert len(encoded) > 17041
    if variant == "fast_advance_layered_prompt":
        prompt = planner_prompt.fast_advance_layered_prompt(
            request, capabilities=catalog, responsibilities=request.responsibilities, response_schema={},
        )
        encoded = json.dumps(planner_prompt.fast_advance_streaming_capability_prompt_projection(catalog),
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        prompt = getattr(planner_prompt, variant)(request, catalog, response_schema={})
    assert encoded in str(prompt)
    with patch("agent.app.clients.ollama_client.httpx.AsyncClient") as http:
        with pytest.raises(OllamaGenerationError) as rejected:
            asyncio.run(OllamaClient(base_url="http://unused.invalid", model="fixed-test-model", purpose="fast_planner").generate(
                prompt, options={"num_ctx": 4096, "num_predict": 1024},
            ))
    assert rejected.value.failure_class == "prompt_budget_exceeded"
    http.assert_not_called()


@pytest.mark.parametrize("variant", ["fast_plan_prompt", "fast_layered_prompt", "deep_plan_prompt", "deep_layered_prompt"])
@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
@pytest.mark.parametrize("oversized", [False, True])
def test_all_retained_goal_meanings_survive_large_sections(variant, language, oversized):
    detail = ("Keep each qualification. " if language == "en-US" else "保留每个限定条件。") * (60 if oversized else 1)
    request = _retained_request(count=8, language=language, detail=detail)
    expected = list(planner_goal_context(request.context).authoritative_goals)
    original = copy.deepcopy(request)
    prompt = _render_required(request, variant)
    label = "FINAL CANONICAL GOALS JSON"
    actual, _ = json.JSONDecoder().raw_decode(prompt.split(label + ":\n")[-1])
    assert actual == expected
    assert len(actual) == 8
    assert request == original


@pytest.mark.parametrize("variant", ["fast_plan_prompt", "fast_layered_prompt", "deep_plan_prompt", "deep_layered_prompt"])
@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("goal_count", [1, 2])
@pytest.mark.parametrize("field,label,fast_budget,deep_budget,is_list", [
    ("trusted_terminal_evidence", "Host-bound terminal Evidence JSON", 6000, 6000, True),
    ("canonical_plan_resolution", "Authoritative source Plan JSON for exact re-entry correlation", 5000, 5000, False),
    ("trusted_execution_outcome", "Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning)", 5000, 5000, False),
    ("planner_reentry_expectations", "Prior Planner-authored step expectations JSON (prospective hypotheses, never Evidence)", 3600, 3600, True),
    ("trusted_goal_cancellation_evidence", "Host-bound Goal cancellation Evidence JSON", 3200, 3200, True),
    ("active_task_snapshots", "Active and recoverable task bindings JSON", 5000, 6000, True),
    ("existing_work_activities", "Existing retained or provisional Runtime Activities JSON", 3500, 4000, True),
    ("interaction_context", "Goal-scoped Interaction Context JSON", 7000, 8000, False),
    ("verified_tool_memory_index", "Verified tool-memory index JSON (provenance and bound arguments only; no result contents)", 5000, 6000, True),
])
def test_required_planner_sections_keep_exact_boundary_payloads(
    variant, language, offset, goal_count, field, label, fast_budget, deep_budget, is_list,
):
    request = _retained_request(count=goal_count, language=language)
    budget = deep_budget if variant.startswith("deep") else fast_budget
    record = {"correlation": "stable-id", "data": ""}
    payload = [record, {"correlation": "last-id"}] if is_list else record
    empty_size = len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    record["data"] = ("界" if language == "zh-CN" else "x") * (budget + offset - empty_size)
    request.context[field] = payload
    prompt = _render_required(request, variant)
    actual, _ = json.JSONDecoder().raw_decode(prompt.split(label + ":\n")[-1])
    assert actual == payload



@pytest.mark.parametrize("tier,field", [
    ("fast", "interaction_context"), ("deep", "interaction_context"),
    ("stream", "interaction_context"), ("fast", "trusted_terminal_evidence"),
    ("deep", "trusted_terminal_evidence"),
])
@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
def test_whole_request_budget_rejection_prevents_generation_and_partial_commit(tier, language, field):
    request = _retained_request(count=8, language=language)
    from unittest.mock import patch
    from agent.app.clients.ollama_client import OllamaClient

    # Required context renders losslessly; the actual configured request budget
    # remains enforced by the production client before any generation or commit.
    request.context[field] = {"correlation": "x" * 20000} if field == "interaction_context" else [{"data": "x" * 20000}]
    model = OllamaClient(base_url="http://unused.invalid", model="fixed-test-model", purpose="fast_planner" if tier == "stream" else tier + "_planner")
    catalog = StaticCatalog([])
    with patch("agent.app.clients.ollama_client.httpx.AsyncClient") as http:
        if tier == "stream":
            async def stream():
                return [frame async for frame in fast_planner.FastPlannerResolver(model, catalog, num_ctx=4096).stream_advance(request)]
            frames = asyncio.run(stream())
            assert len(frames) == 1 and isinstance(frames[0], FastPlannerStreamFailure)
            assert frames[0].failure_stage == "before_commit"
            assert frames[0].presentation_commit_id is None
            assert frames[0].failure_domain == "llm_budget"
            assert frames[0].retryable is False
        else:
            resolver = (fast_planner.FastPlannerResolver if tier == "fast" else deep_planner.DeepPlannerResolver)(model, catalog, num_ctx=4096)
            result = asyncio.run(resolver.resolve(request))
            assert result.goal_ids == [f"goal-{index}" for index in range(8)]
            assert result.steps == [] and result.response_text == ""
            assert result.goal_outcomes == []
            assert result.coverage == "uncertain"
            assert result.metadata["failure_class"] == "prompt_budget_exceeded"
            assert result.metadata["failure_domain"] == "llm_budget"
            assert result.metadata["retryable"] is False
            if tier == "fast":
                assert result.metadata["path_classification"] == "contract_failure"
        http.assert_not_called()



@pytest.mark.parametrize("language", ["en-US", "zh-CN"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_streaming_interaction_identity_survives_old_character_boundary(language, offset):
    request = _retained_request(language=language)
    payload = {"delivered_text": "", "activity_id": "last-delivery"}
    overhead = len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    payload["delivered_text"] = ("界" if language == "zh-CN" else "x") * (1200 + offset - overhead)
    request.context["interaction_context"] = payload
    def render():
        return str(planner_prompt.fast_advance_layered_prompt(
            request, responsibilities=request.responsibilities, capabilities=[], response_schema={},
        ))
    # Verify complete values, including the final delivery identity.
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) in render()


def test_streaming_capability_applicability_and_resource_tail_are_exact():
    capability = {
        "capability_id": "test.complete_contract",
        "description": "Keep this scope. " * 40,
        "resource_claims": [f"resource-{i}" for i in range(13)],
        "effects": [f"effect-{i}" for i in range(13)],
        "input_schema": {"type": "object", "properties": {"choice": {"enum": list(range(13))}}},
        "hints": {
            "when_to_use": "Apply this condition. " * 50,
            "when_not_to_use": "Never omit this limit. " * 50,
            "semantic_scope": {"supported_temporal_scopes": [f"scope-{i}" for i in range(13)]},
            "resource_contract": {"plan_requires": [f"state-{i}" for i in range(13)]},
            "argument_realization": {"object": {"contract": "Exact contract. " * 70, "arguments": [f"arg-{i}" for i in range(13)]}},
        },
    }
    projected, = planner_prompt.fast_advance_streaming_capability_prompt_projection([capability])
    for key in ("description", "resource_claims", "effects"):
        assert projected[key] == capability[key]
    for key, value in capability["hints"].items():
        assert projected[key] == value
    assert projected["args_schema"] == capability["input_schema"]
    deep = planner_prompt.prompt_capability_contract(capability)
    assert deep["when_to_use"] == capability["hints"]["when_to_use"]
    assert deep["when_not_to_use"] == capability["hints"]["when_not_to_use"]

def test_delivered_evidence_keeps_late_qualifier_and_all_goal_bindings():
    from agent.app.planner_context import evidence_bound_dialogue
    text = "Measured result. " * 100 + "Only valid under the final condition."
    goal_ids = [f"goal-{i}" for i in range(9)]
    plan_id = "plan-" + "x" * 201
    history = [{"role": "assistant", "text": text, "metadata": {
        "evidence_bound": True, "source": "evidence_bound_tool_result_interpretation",
        "canonical_plan_id": plan_id, "source_goal_ids": goal_ids,
    }}]
    projected, = evidence_bound_dialogue({}, fallback_history=history)
    assert projected["text"] == text
    assert projected["source_goal_ids"] == goal_ids
    assert projected["canonical_plan_id"] == plan_id


@pytest.mark.parametrize("count", [1, 2])
def test_deep_goal_snapshots_allocate_capacity_for_each_admitted_goal(count):
    request = _retained_request(count=count, detail="Keep this source qualification. " * 17)
    snapshots = request.context["active_goal_snapshots"]
    prompt = _render_required(request, "deep_plan_prompt")
    actual, _ = json.JSONDecoder().raw_decode(prompt.split("Active goals JSON:\n")[1])
    assert actual == snapshots
    if count > 1:
        assert len(json.dumps(snapshots)) > 3200
    # A larger Goal preserves every qualification within the whole request.
    oversized = _retained_request(count=1, detail="qualification " * 500)
    prompt = _render_required(oversized, "deep_plan_prompt")
    actual, _ = json.JSONDecoder().raw_decode(prompt.split("Active goals JSON:\n")[1])
    assert actual == oversized.context["active_goal_snapshots"]


@pytest.mark.parametrize("stage", ["advance", "fast", "deep"])
def test_planner_source_handoff_survives_transport_without_truncation(stage):
    import hashlib
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest

    original = '  重庆：今天还是明天？\n' + ('保留标点、空格与原文。  ' * 180) + '\nlast detail: café ☔  '
    request = cognitive_work_request(
        sid="original-turn", text=original, outcome="Discuss the supplied comparison.",
        context={"user_turn_envelope": {"turn_id": "original-turn",
            "original_input": {"text": original}},
            "goal_association_resolution": {"associations": [], "new_goals": [{
                "goal_id": "goal-source", "description": "Discuss the supplied comparison.",
                "metadata": {"output_mode": "speech"}, "bindings": [],
            }]}},
    )
    transported = CognitiveWorkRequest.model_validate_json(request.model_dump_json())
    if stage == "advance":
        prompt = planner_prompt.fast_advance_layered_prompt(
            transported, responsibilities=transported.responsibilities, capabilities=[],
        )
    elif stage == "fast":
        prompt = planner_prompt.fast_plan_prompt(transported, [], response_schema={})
    else:
        prompt = planner_prompt.deep_plan_prompt(transported, [], response_schema={}, expected_goal_ids=["goal-source"])
    tail = str(prompt).split("IMMUTABLE SOURCE TURN JSON", 1)[1]
    header, body = tail.split("\n", 1)
    source, _ = json.JSONDecoder().raw_decode(body)
    assert source["original_text"] == original
    assert source["original_text_sha256"] == hashlib.sha256(original.encode()).hexdigest()
    assert source["turn_id"] == "original-turn"
    assert source["authority"] == "read_only_source_provenance"
    assert ("GI Responsibilities" if stage == "advance" else "FINAL CANONICAL GOALS") in header
    assert str(prompt).count(json.dumps(original, ensure_ascii=False)) == 1
