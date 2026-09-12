"""Issue #51: scripted primary replies through real Planner and Runtime boundaries.

The frozen bilingual episode supplies authoritative input, not a live forecast.
Providers and speech are in-process fakes; this is Level A evidence only.
"""

from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_context import completed_acquisition_goal_ids
from agent.app.planner_model_contract import PlannerModelOutput
from benchmarks.datasets.fast_planner_daily_life.deep_qualification import load_cases
from benchmarks.datasets.fast_planner_daily_life.qualification import (
    ReplayModel,
    StaticCatalog,
    materialize_catalog,
)
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    LocalSpeechCapabilityProvider,
    MockCapabilityProvider,
    RuntimeAuthorization,
    local_speech_definition,
)
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.outcome_reconciliation import ExecutionOutcomeReconciler
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.interaction import CapabilityResult
from shared.chromie_contracts.tool_result import canonical_value_sha256
from tests.capability_runtime_test_support import submit_and_wait_terminal
from tests.test_cognitive_runtime_pr7 import FakeRuntime

READ_SCHEMA = {
    "type": "object",
    "properties": {"rain_forecast": {"type": "boolean"}},
    "required": ["rain_forecast"],
    "additionalProperties": False,
}
WRITE_SCHEMA = {
    "type": "object",
    "properties": {"created": {"type": "boolean"}},
    "required": ["created"],
    "additionalProperties": False,
}


def scenario(language):
    case = next(case for case in load_cases() if case["id"].endswith(f"02_boundary_{language}"))
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    return request, materialize_catalog(case["input"])


def assessment(gid, *, partial=False):
    return {
        "score": 0.5 if partial else 1.0,
        "status": "partial" if partial else "exact",
        "satisfied_goal_ids": [] if partial else [gid],
        "unmet_goal_ids": [gid] if partial else [],
        "unmet_requirements": ["Decide the conditional reminder from fresh Evidence."]
        if partial
        else [],
        "rationale": "The read alone cannot resolve the conditional effect."
        if partial
        else "The proposed decision resolves the remaining obligation if delivered successfully.",
    }


def read_reply(request):
    gid = request.context["goal_association_resolution"]["new_goals"][0]["goal_id"]
    sat = assessment(gid, partial=True)
    return PlannerModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.99,
            "goal_summary": "Acquire the predicate before deciding the conditional effect.",
            "response_text": "",
            "plan_relation": "exact",
            "user_confirmation_required": False,
            "steps": [
                {
                    "step_id": "read-forecast",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "Hangzhou", "date": "2026-09-04", "period": "morning"},
                    "timing": "sequential",
                    "source_goal_ids": [gid],
                    "step_purpose": "acquire_information",
                    "expected_outcome": "Forecast establishes whether rain is predicted for the requested place and period.",
                }
            ],
            "goal_outcomes": {
                gid: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "step_ids": ["read-forecast"],
                    "satisfaction": sat,
                }
            },
            "goal_satisfaction": {
                **sat,
                "unmet_requirements": [
                    "The reminder decision remains deferred until the forecast is known."
                ],
            },
        }
    ).model_dump(mode="json")


def next_reply(request, rain):
    raw = read_reply(request)
    gid = next(iter(raw["goal_outcomes"]))
    sat = assessment(gid)
    text = (
        ("预报有雨，要创建带伞提醒吗？" if rain else "预报没有雨，所以无需创建带伞提醒。")
        if request.language.startswith("zh")
        else (
            "Rain is forecast. Shall I create the umbrella reminder?"
            if rain
            else "No rain is forecast, so no umbrella reminder is needed."
        )
    )
    raw.update(
        disposition="execute" if rain else "respond",
        response_text=text,
        goal_satisfaction=sat,
        user_confirmation_required=rain,
    )
    raw["steps"] = (
        [
            {
                "step_id": "create-reminder",
                "timing": "sequential",
                "capability_id": "chromie.reminder.create",
                "args": {
                    "due_at": "2026-09-04T07:30:00+08:00",
                    "reminder_text": "bring an umbrella",
                },
                "source_goal_ids": [gid],
                "step_purpose": "achieve_effect",
                "expected_outcome": "The requested reminder is created.",
            }
        ]
        if rain
        else []
    )
    raw["goal_outcomes"][gid].update(
        disposition=raw["disposition"],
        response_text="" if rain else text,
        satisfaction=sat,
        step_ids=["create-reminder"] if rain else [],
    )
    return PlannerModelOutput.model_validate(raw).model_dump(mode="json")


class CheckedReply(ReplayModel):
    async def generate(self, prompt, **kwargs):
        value = await super().generate(prompt, **kwargs)
        Draft202012Validator(kwargs["response_format"]).validate(value)
        return value


async def resolve(request, catalog, raw, tier="deep"):
    model = CheckedReply(json.dumps(raw))
    cls = FastPlannerResolver if tier == "fast" else DeepPlannerResolver
    result = await cls(model, StaticCatalog(catalog)).resolve(request)
    assert model.calls == 1
    return result


class EpisodeProvider(MockCapabilityProvider):
    def __init__(self, rain):
        super().__init__("episode")
        self.rain = rain

    async def execute(self, request, definition, context):
        self.calls.append(request)
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            status="completed",
            output={"rain_forecast": self.rain}
            if request.capability_id == "chromie.weather.lookup"
            else {"created": True},
        )


def episode_runtime(catalog, rain):
    definitions = [
        CapabilityDefinition(
            capability_id=item["capability_id"],
            provider_id="episode",
            input_schema=item["input_schema"],
            output_schema=READ_SCHEMA
            if item["capability_id"] == "chromie.weather.lookup"
            else WRITE_SCHEMA,
            requires_confirmation=item.get("requires_confirmation", False),
            metadata={
                "safety_class": item.get("safety_class", ""),
                "effects": item.get("effects", []),
            },
        )
        for item in catalog
        if item["capability_id"] in {"chromie.weather.lookup", "chromie.reminder.create"}
    ]
    definitions.append(local_speech_definition())
    runtime = FakeRuntime(definitions)
    provider = EpisodeProvider(rain)
    runtime.runtime.register_provider(provider)
    # Scripted playback receipt; never audio or physical speaker evidence.
    runtime.runtime.register_provider(
        LocalSpeechCapabilityProvider(
            lambda _args: {"played": True, "playback_started": True, "voice_released": True}
        )
    )
    return runtime, provider


def record_bundle(manager, response, plan, results, sid):
    bundle = ExecutionOutcomeReconciler().build(
        turn_id=response.metadata["turn_id"],
        interaction_id=response.interaction_id,
        plan=plan,
        requests=response.capabilities,
        results=results,
        output_schemas={
            req.request_id: READ_SCHEMA
            if req.capability_id == "chromie.weather.lookup"
            else WRITE_SCHEMA
            for req in response.capabilities
        },
    )
    manager.record_execution_outcome_bundle(bundle, sid=sid)
    manager.reconcile_execution_outcome_responsibilities(bundle, sid=sid)
    return bundle


def status(manager, gid):
    return manager._goal_responsibility_status(manager._task_context_by_goal_id(gid))


async def begin_episode(language, rain):
    request, catalog = scenario(language)
    plan = await resolve(request, catalog, read_reply(request))
    assert plan.disposition == "execute", plan.metadata
    runtime, provider = episode_runtime(catalog, rain)
    adapter = CanonicalPlanRuntimeAdapter(runtime)
    response = await adapter.build_execution_only_response(
        plan=plan, session_id=request.sid, language=request.language
    )
    response.metadata.update(
        turn_id=request.sid,
        goal_association=request.context["goal_association_resolution"],
        goal_interpretation={
            "responsibilities": [r.model_dump(mode="json") for r in request.responsibilities]
        },
        user_turn_envelope={
            "turn_id": request.sid,
            "original_input": {"text": request.text},
            "normalized_input": {"text": request.text, "language": request.language},
        },
    )
    manager = ConversationStateManager(base_conversation_id=f"issue51-{language}-{rain}")
    manager.apply_goal_association_resolution(
        request.context["goal_association_resolution"],
        sid=request.sid,
        user_text=request.text,
        atomic=True,
    )
    manager.record_interaction_response(request.sid, response)
    execution = await submit_and_wait_terminal(runtime.runtime, response)
    bundle = record_bundle(manager, response, plan, execution.results, request.sid)
    gid = plan.goal_ids[0]
    assert bundle.aggregate_status == "completed"
    assert bundle.goal_outcomes[0].requires_planner_continuation
    assert status(manager, gid) == "open"
    return request, catalog, plan, runtime, provider, adapter, response, manager, bundle


async def reenter(request, catalog, plan, adapter, response, bundle, raw):
    class Client:
        seen = None

        async def resolve_fast_plan(self, _session, *, request, timeout_ms):
            self.seen = request
            return await resolve(request, catalog, raw, "fast")

    client = Client()
    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = client
    assistant.cognitive_runtime_policy = SimpleNamespace(
        fast_planner_timeout_ms=3000, deep_planner_timeout_ms=6000
    )
    assistant.cognitive_runtime = GoalDrivenRuntimeCoordinator(
        agent_client=client, adapter=adapter, policy=CognitiveRuntimePolicy(mode="apply")
    )
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.build_context = lambda _sid: copy.deepcopy(request.context)
    assistant._cognitive_core_authority_context = lambda context, **_kwargs: context

    async def get_session():
        return object()

    assistant.get_http_session = get_session
    result = await assistant._plan_evidence_bound_capability_result_response(
        source_response=response, bundle=bundle, plan=plan, session_id=request.sid
    )
    return result, client.seen


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("tier", ["fast", "deep"])
def test_partial_acquisition_is_complete_current_work(language, tier):
    async def run():
        request, catalog = scenario(language)
        raw = read_reply(request)
        if tier == "fast":
            # Exercise Fast admission with a declared common read; the original
            # Deep episode intentionally keeps this read rare.
            catalog = [
                {**item, "prompt_tier": "common"}
                if item["capability_id"] == "chromie.weather.lookup"
                else item
                for item in catalog
            ]
        plan = await resolve(request, catalog, raw, tier)
        assert plan.disposition == "execute", plan.metadata
        assert plan.goal_satisfaction.score == 0.5
        assert (
            plan.goal_satisfaction.unmet_requirements
            == raw["goal_satisfaction"]["unmet_requirements"]
        )
        assert (
            plan.goal_outcomes[0].satisfaction.unmet_requirements
            == raw["goal_outcomes"][plan.goal_ids[0]]["satisfaction"]["unmet_requirements"]
        )

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("rain", [True, False])
def test_conditional_episode_read_evidence_decision_and_terminal_delivery(language, rain):
    async def run():
        (
            request,
            catalog,
            plan,
            runtime,
            provider,
            adapter,
            response,
            manager,
            bundle,
        ) = await begin_episode(language, rain)
        next_response, seen = await reenter(
            request, catalog, plan, adapter, response, bundle, next_reply(request, rain)
        )
        assert next_response is not None
        # The ordinary dispatch caller supplies the admitted turn identity.
        next_response.metadata["turn_id"] = seen.sid
        assert seen.planner_reentry_scope.source_plan_id == plan.plan_id
        assert seen.context["trusted_terminal_evidence"][0]["data"] == {"rain_forecast": rain}
        assert (
            seen.context["canonical_plan_resolution"]["goal_satisfaction"]["unmet_goal_ids"]
            == plan.goal_ids
        )
        assert completed_acquisition_goal_ids(
            seen.context, reentry_scope=seen.planner_reentry_scope
        ) == set(plan.goal_ids)
        assert status(manager, plan.goal_ids[0]) == "open"
        # Both depths can express the new primary decision from this exact packet.
        deep = await resolve(seen, catalog, next_reply(request, rain), "deep")
        assert deep.disposition == ("execute" if rain else "respond"), deep.metadata
        if rain:
            assert next_response.requires_confirmation
            # Confirmation is independently enforced even if speech is omitted.
            write_only = next_response.model_copy(update={"speech": []})
            with pytest.raises(ValueError, match="requires confirmation"):
                await submit_and_wait_terminal(runtime.runtime, write_only)
            assert not any(
                call.capability_id == "chromie.reminder.create" for call in provider.calls
            )
            manager.record_interaction_response(
                request.sid,
                next_response,
                confirmed_request_ids={r.request_id for r in next_response.capabilities},
            )
            executed = await submit_and_wait_terminal(
                runtime.runtime,
                write_only,
                authorization=RuntimeAuthorization(
                    confirmed_request_ids={r.request_id for r in next_response.capabilities}
                ),
            )
            next_plan = deep.model_validate(next_response.metadata["canonical_plan"])
            record_bundle(manager, next_response, next_plan, executed.results, request.sid)
            assert [call.capability_id for call in provider.calls] == [
                "chromie.weather.lookup",
                "chromie.reminder.create",
            ]
        else:
            assert not next_response.capabilities
            manager.record_interaction_response(request.sid, next_response)
            assert status(manager, plan.goal_ids[0]) == "open"
            assert next_response.speech
            delivered = await submit_and_wait_terminal(runtime.runtime, next_response)
            assert delivered.results and all(
                item.status == "completed" for item in delivered.results
            )
            for item in delivered.results:
                manager.update_pending_task_status_for_request_id(
                    request_id=item.request_id, status=item.status
                )
            assert [call.capability_id for call in provider.calls] == ["chromie.weather.lookup"]
        assert status(manager, plan.goal_ids[0]) == "satisfied"

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_expected",
        "missing_arg",
        "weak_effect",
        "relabelled_write",
        "exact_relabelled_write",
        "premature_write",
        "erased_aggregate",
    ],
)
def test_acquisition_exception_cannot_admit_incomplete_or_effectful_work(mutation):
    async def run():
        request, catalog = scenario("en")
        raw = read_reply(request)
        gid = next(iter(raw["goal_outcomes"]))
        if mutation == "missing_expected":
            raw["steps"][0]["expected_outcome"] = ""
        elif mutation == "missing_arg":
            del raw["steps"][0]["args"]["date"]
        elif mutation == "weak_effect":
            raw["steps"][0]["step_purpose"] = "achieve_effect"
        elif mutation in {"relabelled_write", "exact_relabelled_write"}:
            raw["steps"] = next_reply(request, True)["steps"]
            raw["steps"][0]["step_purpose"] = "acquire_information"
            raw["goal_outcomes"][gid]["step_ids"] = ["create-reminder"]
            if mutation == "exact_relabelled_write":
                raw["goal_satisfaction"] = assessment(gid)
                raw["goal_outcomes"][gid]["satisfaction"] = assessment(gid)
        elif mutation == "premature_write":
            raw["steps"] += next_reply(request, True)["steps"]
            raw["goal_outcomes"][gid]["step_ids"].append("create-reminder")
        else:
            raw["goal_satisfaction"] = assessment(gid)
        for tier in ["fast", "deep"]:
            cls = FastPlannerResolver if tier == "fast" else DeepPlannerResolver
            model = ReplayModel(json.dumps(raw))
            result = await cls(model, StaticCatalog(catalog)).resolve(request.model_copy(deep=True))
            assert result.disposition not in {"execute", "respond"}, (mutation, tier, result)

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    ["missing", "failed", "invalid_observation", "mismatched_data", "stale_plan", "removed_stage"],
)
def test_unqualified_acquisition_evidence_cannot_establish_either_branch(mutation):
    async def run():
        (
            request,
            catalog,
            plan,
            runtime,
            provider,
            adapter,
            response,
            manager,
            bundle,
        ) = await begin_episode("en", True)
        _, seen = await reenter(
            request, catalog, plan, adapter, response, bundle, next_reply(request, True)
        )
        context = seen.context
        if mutation == "missing":
            context["execution_outcome_bundle"] = None
        elif mutation == "failed":
            context["execution_outcome_bundle"]["evidence"][0]["status"] = "failed"
        elif mutation == "invalid_observation":
            context["execution_outcome_bundle"]["evidence"][0]["observation"][
                "schema_validated"
            ] = False
        elif mutation == "mismatched_data":
            context["trusted_terminal_evidence"][0]["data"] = {"rain_forecast": False}
            context["trusted_terminal_evidence"][0]["output_sha256"] = canonical_value_sha256(
                {"rain_forecast": False}
            )
        elif mutation == "stale_plan":
            context["execution_outcome_bundle"]["canonical_plan_id"] = "obsolete-plan"
        else:
            context["execution_outcome_bundle"]["goal_outcomes"][0]["acquisition_step_ids"] = []
        assert not completed_acquisition_goal_ids(context, reentry_scope=seen.planner_reentry_scope)
        for rain in [True, False]:
            for tier, cls in [("fast", FastPlannerResolver), ("deep", DeepPlannerResolver)]:
                result = await cls(
                    ReplayModel(json.dumps(next_reply(request, rain))), StaticCatalog(catalog)
                ).resolve(seen.model_copy(deep=True))
                assert result.disposition not in {"execute", "respond"}, (
                    mutation,
                    tier,
                    rain,
                    result,
                )
        assert status(manager, plan.goal_ids[0]) == "open"

    asyncio.run(run())


def test_reconciliation_rejects_rewritten_stage_under_same_outcome_identity():
    async def run():
        request, _, plan, _, _, _, _, manager, bundle = await begin_episode("en", True)
        changed = bundle.model_copy(deep=True)
        changed.goal_outcomes[0].acquisition_step_ids = []
        changed.goal_outcomes[0].planned_satisfaction = None
        with pytest.raises(ValueError, match="exact recorded outcome"):
            manager.reconcile_execution_outcome_responsibilities(changed, sid=request.sid)
        assert status(manager, plan.goal_ids[0]) == "open"
        with pytest.raises(ValidationError, match="acquisition step IDs"):
            bundle.goal_outcomes[0].model_validate(
                {**bundle.goal_outcomes[0].model_dump(), "acquisition_step_ids": ["foreign-step"]}
            )

    asyncio.run(run())


@pytest.mark.parametrize("weak_sibling", [False, True])
def test_acquisition_does_not_waive_sibling_adequacy_or_complete_it(weak_sibling):
    from agent.app.planner_deep_validation import deep_plan_validation_errors
    from agent.app.planner_fast_validation import qualify_fast_canonical_plan
    from shared.chromie_contracts.plan import CanonicalPlan

    async def run():
        request, catalog = scenario("en")
        plan = await resolve(request, catalog, read_reply(request))
        gid = plan.goal_ids[0]
        sibling = "goal-independent-reminder"
        raw = plan.model_dump(mode="json")
        raw["goal_ids"].append(sibling)
        write = next_reply(request, True)["steps"][0]
        write["source_goal_ids"] = [sibling]
        raw["steps"].append(write)
        raw["goal_outcomes"].append(
            {
                "goal_id": sibling,
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["create-reminder"],
                "satisfaction": assessment(sibling, partial=weak_sibling),
            }
        )
        raw["metadata"]["user_confirmation_required"] = True
        raw["response_text"] = "Shall I create the independently requested reminder?"
        if weak_sibling:
            raw["goal_satisfaction"]["unmet_goal_ids"].append(sibling)
        else:
            raw["goal_satisfaction"]["satisfied_goal_ids"].append(sibling)
        mixed = CanonicalPlan.model_validate(raw)
        errors = deep_plan_validation_errors(
            mixed,
            catalog,
            expected_goal_ids=mixed.goal_ids,
            authoritative_goals=[],
            requires_execution=True,
            min_goal_satisfaction=0.75,
        )
        fast = qualify_fast_canonical_plan(
            mixed,
            capability_payload=catalog,
            expected_goal_ids_for_turn=mixed.goal_ids,
            authoritative_goals=[],
            evidence_reentry_goal_ids=set(),
        )
        assert fast.accepted is not weak_sibling
        assert bool(errors) is weak_sibling
        if weak_sibling:
            assert errors[0]["goal_id"] == sibling
            return
        runtime, provider = episode_runtime(catalog, True)
        response = await CanonicalPlanRuntimeAdapter(runtime).build_planner_owned_response(
            plan=mixed, session_id=request.sid, language=request.language
        )
        response.metadata["turn_id"] = request.sid
        manager = ConversationStateManager(base_conversation_id="issue51-siblings")
        ga = copy.deepcopy(request.context["goal_association_resolution"])
        other = copy.deepcopy(ga["new_goals"][0])
        other.update(
            goal_id=sibling,
            description="Create the independently requested reminder.",
            source_responsibility_refs=["r2"],
        )
        ga["new_goals"].append(other)
        manager.apply_goal_association_resolution(
            ga, sid=request.sid, user_text=request.text, atomic=True
        )
        confirmed = {r.request_id for r in response.capabilities}
        manager.record_interaction_response(request.sid, response, confirmed_request_ids=confirmed)
        result = await submit_and_wait_terminal(
            runtime.runtime,
            response.model_copy(update={"speech": []}),
            authorization=RuntimeAuthorization(confirmed_request_ids=confirmed),
        )
        record_bundle(manager, response, mixed, result.results, request.sid)
        assert len(provider.calls) == 2
        assert status(manager, gid) == "open"
        assert status(manager, sibling) == "satisfied"

    asyncio.run(run())


@pytest.mark.parametrize("terminal", ["cancelled", "refused", "superseded"])
def test_late_acquisition_evidence_preserves_semantic_terminal_state(terminal):
    async def run():
        request, _, plan, _, _, _, _, manager, bundle = await begin_episode("en", True)
        context = manager._task_context_by_goal_id(plan.goal_ids[0])
        manager._set_goal_responsibility_status(context, terminal, source="test_owner_decision")
        manager.reconcile_execution_outcome_responsibilities(bundle, sid=request.sid)
        assert status(manager, plan.goal_ids[0]) == terminal

    asyncio.run(run())


def test_partial_response_delivery_cannot_erase_deferred_obligation():
    async def run():
        request, catalog, plan, _, _, adapter, response, manager, bundle = await begin_episode(
            "en", False
        )
        followup, _ = await reenter(
            request, catalog, plan, adapter, response, bundle, next_reply(request, False)
        )
        # Exercise the delivery owner directly with a partial canonical response;
        # normal Fast admission separately rejects this as a final answer.
        canonical = followup.metadata["canonical_plan"]
        gid = plan.goal_ids[0]
        canonical["goal_satisfaction"] = assessment(gid, partial=True)
        canonical["goal_outcomes"][0]["satisfaction"] = assessment(gid, partial=True)
        manager.record_interaction_response(request.sid, followup)
        for speech in followup.speech:
            manager.update_pending_task_status_for_request_id(
                request_id=speech.id, status="completed"
            )
        assert status(manager, gid) == "open"

    asyncio.run(run())


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("reentry", [False, True])
def test_fast_exact_confirmation_requires_primary_question(language, reentry):
    async def run():
        from agent.app.planner_fast_validation import qualify_fast_canonical_plan
        from benchmarks.datasets.fast_planner_daily_life.qualification import (
            load_cases as load_fast_cases,
        )

        if reentry:
            request, catalog, source, _, _, adapter, response, _, bundle = await begin_episode(
                language, True
            )
            _, request = await reenter(
                request, catalog, source, adapter, response, bundle, next_reply(request, True)
            )
            raw = next_reply(request, True)
        else:
            case = next(
                c
                for c in load_fast_cases()
                if c["id"].endswith(f"confirmation_proposal_22_supported_{language}")
            )
            request = CognitiveWorkRequest.model_validate(case["input"]["request"])
            catalog = materialize_catalog(case["input"])
            raw = next_reply(request, True)
            raw["steps"][0]["args"] = {
                "reminder_text": "带上蓝色笔记本"
                if language == "zh"
                else "bring the blue notebook",
                "due_at": "2026-09-03T18:30:00+08:00",
            }
            raw["response_text"] = (
                "要创建今天18:30带上蓝色笔记本的提醒吗？"
                if language == "zh"
                else "Shall I create today's 6:30 p.m. reminder to bring the blue notebook?"
            )
        plan = await resolve(request, catalog, raw, "fast")
        assert plan.disposition == "execute", plan.metadata
        assert plan.metadata["plan_relation"] == "exact"
        runtime, provider = episode_runtime(catalog, True)
        response = await CanonicalPlanRuntimeAdapter(runtime).build_planner_owned_response(
            plan=plan,
            session_id=request.sid,
            language=request.language,
            context=request.context,
        )
        assert response.requires_confirmation
        assert response.speech
        assert not provider.calls
        # The emitted Schema now admits the exact question and rejects its absence.
        missing = copy.deepcopy(raw)
        missing["response_text"] = ""
        rejected = await resolve(request, catalog, missing, "fast")
        assert rejected.disposition != "execute"
        # The Host independently rejects whitespace or a forged false model flag.
        for flag in (True, False):
            invalid = plan.model_copy(
                update={
                    "response_text": "   ",
                    "metadata": {**plan.metadata, "user_confirmation_required": flag},
                }
            )
            qualified = qualify_fast_canonical_plan(
                invalid,
                capability_payload=catalog,
                expected_goal_ids_for_turn=plan.goal_ids,
                authoritative_goals=[],
                evidence_reentry_goal_ids=set(),
            )
            assert not qualified.accepted
            assert qualified.reason == "confirmation_question_missing"

    asyncio.run(run())
