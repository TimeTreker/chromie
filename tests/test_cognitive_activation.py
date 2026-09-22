from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from agent.app.cognitive_activation import CognitiveActivationResolver
from orchestrator.runtime.cognitive_activation import _compact_activation_state, resolve_cognitive_activation
from shared.chromie_contracts.cognitive_activation import (
    CognitiveActivationContext,
    CognitiveActivationDecision,
)
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal


class Model:
    def __init__(self, output):
        self.output = output
        self.calls = 0
        self.kwargs = None

    async def generate(self, prompt, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return self.output


def planner_request() -> CognitiveActivationContext:
    responsibility = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Check the weather.",
        output_mode="information",
        continuity_scope="goal",
        confidence=1.0,
    )
    return CognitiveActivationContext(
        request_id="activation:evidence-1",
        trigger="execution_outcome",
        allowed_authorities=["planner"],
        goal_ids=["goal-weather"],
        responsibility_refs=["r1"],
        source_refs=["evidence-1"],
        responsibilities=[responsibility],
        state={"existing_work_activities": []},
    )


def test_activation_model_can_request_exact_existing_authority() -> None:
    request = planner_request()
    model = Model({
        "cognitive_requests": [{
            "authority": "planner",
            "goal_ids": ["goal-weather"],
            "responsibility_refs": ["r1"],
            "source_refs": ["evidence-1"],
            "reason_summary": "Fresh Evidence changes remaining Work reasoning.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should reconsider the current Goal.",
    })
    result = asyncio.run(CognitiveActivationResolver(model).resolve(request))
    assert [item.authority for item in result.cognitive_requests] == ["planner"]
    assert model.calls == 1
    schema = model.kwargs["response_format"]
    selection = schema["$defs"]["CognitiveActivationSelection"]
    assert selection["properties"]["authority"]["enum"] == ["planner"]
    assert selection["required"] == [
        "authority", "goal_ids", "responsibility_refs", "source_refs", "reason_summary",
    ]
    assert selection["properties"]["goal_ids"]["const"] == ["goal-weather"]
    assert selection["properties"]["responsibility_refs"]["const"] == ["r1"]
    assert selection["properties"]["source_refs"]["const"] == ["evidence-1"]


def test_activation_model_can_choose_no_further_cognition() -> None:
    result = asyncio.run(CognitiveActivationResolver(Model({
        "cognitive_requests": [],
        "confidence": 0.9,
        "reason_summary": "The trusted state change needs no further cognition.",
    })).resolve(planner_request()))
    assert result.cognitive_requests == []


def test_activation_decision_cannot_widen_scope_or_authority() -> None:
    request = planner_request()
    with pytest.raises(ValueError, match="unavailable authority"):
        CognitiveActivationDecision(
            cognitive_requests=[{
                "authority": "social_cognition",
                "goal_ids": ["goal-weather"],
                "responsibility_refs": ["r1"],
                "source_refs": ["evidence-1"],
            }],
            confidence=1.0,
            reason_summary="bad",
        ).validate_request(request)
    with pytest.raises(ValueError, match="widened Goal scope"):
        CognitiveActivationDecision(
            cognitive_requests=[{
                "authority": "planner",
                "goal_ids": ["goal-other"],
                "responsibility_refs": ["r1"],
                "source_refs": ["evidence-1"],
            }],
            confidence=1.0,
            reason_summary="bad",
        ).validate_request(request)


def test_cognitive_activation_endpoint_is_exposed() -> None:
    from agent.app.main import app

    assert "/cognitive-activation" in {route.path for route in app.routes}


def test_activation_prompt_treats_fresh_information_evidence_as_remaining_obligation() -> None:
    request = planner_request().model_copy(update={
        "state": {
            "trusted_state_change": {
                "trusted_terminal_evidence": [{
                    "evidence_id": "evidence-1",
                    "tool_id": "chromie.weather.lookup",
                    "status": "completed",
                    "data": {"temperature_c": 25, "forecast": "x" * 10000},
                }]
            }
        }
    })
    model = Model({
        "cognitive_requests": [{
            "authority": "planner",
            "goal_ids": ["goal-weather"],
            "responsibility_refs": ["r1"],
            "source_refs": ["evidence-1"],
            "reason_summary": "Fresh information Evidence requires result reasoning.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should establish the remaining answer obligation.",
    })
    asyncio.run(CognitiveActivationResolver(model).resolve(request))
    assert "acquisition completion is not the same" in model.kwargs["system"]
    assert "delivering the requested information" in model.kwargs["system"]


def test_compact_activation_state_drops_large_owner_envelopes_but_retains_lifecycle() -> None:
    compact = _compact_activation_state({
        "goal_association": {
            "resolution_status": "resolved",
            "reason_summary": "x" * 20000,
            "new_goals": [{
                "goal_id": "goal-weather",
                "description": "Check weather",
                "source_responsibility_refs": ["r1"],
                "metadata": {"huge": "x" * 20000},
            }],
        },
        "canonical_plan": {
            "plan_id": "plan-weather", "disposition": "execute",
            "coverage": "complete", "goal_ids": ["goal-weather"],
            "goal_satisfaction": {"status": "partial", "score": 0.5,
                                  "unmet_requirements": ["Deliver the acquired information."]},
            "response_text": "x" * 20000,
            "steps": [{"step_id": "lookup", "capability_id": "chromie.weather.lookup",
                       "source_goal_ids": ["goal-weather"], "step_purpose": "acquire_information",
                       "args": {"huge": "x" * 20000}}],
        },
        "existing_work_activities": [{
            "activity_id": "lookup", "capability_id": "chromie.weather.lookup",
            "status": "completed", "provider_blob": "x" * 20000,
        }],
        "trusted_state_change": {
            "trusted_execution_outcome": {
                "outcome_id": "outcome-1", "aggregate_status": "completed",
                "goal_outcomes": [{"goal_id": "goal-weather", "status": "completed",
                                   "acquisition_step_ids": ["lookup"],
                                   "planned_satisfaction": {"status": "partial", "score": 0.5,
                                                            "unmet_requirements": ["Deliver the acquired information."]},
                                   "evidence_ids": ["evidence-1"], "huge": "x" * 20000}],
            },
            "trusted_terminal_evidence": [{
                "evidence_id": "evidence-1", "tool_id": "chromie.weather.lookup",
                "status": "completed", "data": {"huge": "x" * 20000},
            }],
        },
    })
    import json
    encoded = json.dumps(compact, ensure_ascii=False)
    assert len(encoded) < 5000
    assert "response_text" not in encoded
    assert "provider_blob" not in encoded
    assert '"aggregate_status": "completed"' in encoded
    assert '"evidence_id": "evidence-1"' in encoded
    assert compact["canonical_plan"]["steps"][0]["step_purpose"] == "acquire_information"
    assert compact["canonical_plan"]["goal_satisfaction"]["status"] == "partial"
    outcome = compact["trusted_state_change"]["trusted_execution_outcome"]["goal_outcomes"][0]
    assert outcome["acquisition_step_ids"] == ["lookup"]
    assert outcome["planned_satisfaction"]["unmet_requirements"] == ["Deliver the acquired information."]


def test_activation_decoder_requires_exact_trusted_scope_fields() -> None:
    request = planner_request()
    schema = CognitiveActivationResolver.response_schema(request)
    validator = Draft202012Validator(schema)
    omitted_scope = {
        "cognitive_requests": [{
            "authority": "planner",
            "reason_summary": "Fresh Evidence requires Planner continuation.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should reconsider the open information Goal.",
    }
    assert not validator.is_valid(omitted_scope)
    exact = {
        "cognitive_requests": [{
            "authority": "planner",
            "goal_ids": ["goal-weather"],
            "responsibility_refs": ["r1"],
            "source_refs": ["evidence-1"],
            "reason_summary": "Fresh Evidence requires Planner continuation.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should reconsider the open information Goal.",
    }
    assert validator.is_valid(exact)


@pytest.mark.parametrize("goal_count", [1, 8, 9, 16])
@pytest.mark.parametrize("reverse", [False, True])
def test_host_activation_preserves_entire_reentry_scope(goal_count, reverse):
    goals = [f"goal:{i}" for i in range(goal_count)]
    states = [{"goal_id": goal, "work_status": "failed" if i == goal_count - 1 else "completed"}
              for i, goal in enumerate(goals)]
    if reverse:
        goals.reverse()
        states.reverse()
    sources = [f"evidence:{i}" for i in range(32)]
    calls = []

    async def resolve(session, *, request, **kwargs):
        calls.append(request)
        return CognitiveActivationDecision(cognitive_requests=[{
            "authority": "planner", "goal_ids": request.goal_ids, "source_refs": request.source_refs,
        }], confidence=1.0)

    async def session():
        return None

    host = SimpleNamespace(agent_client=SimpleNamespace(resolve_cognitive_activation=resolve), get_http_session=session)
    decision = asyncio.run(resolve_cognitive_activation(host, trigger="post_execution",
        allowed_authorities=["planner"], goal_ids=goals, source_refs=sources, state={"goal_state": states}))
    assert len(calls) == 1 and decision is not None
    assert calls[0].goal_ids == decision.cognitive_requests[0].goal_ids == goals
    assert calls[0].source_refs == decision.cognitive_requests[0].source_refs == sources
    assert calls[0].state["goal_state"] == states


@pytest.mark.parametrize("overflow", ["goals", "sources", "responsibilities"])
def test_host_activation_rejects_over_scope_before_calling_model(overflow):
    calls, logs = [], []

    async def resolve(*args, **kwargs):
        calls.append(kwargs)
        return CognitiveActivationDecision(cognitive_requests=[], confidence=1.0)

    async def session():
        return None

    host = SimpleNamespace(agent_client=SimpleNamespace(resolve_cognitive_activation=resolve),
                           get_http_session=session, session_log=lambda *args: logs.append(args))
    result = asyncio.run(resolve_cognitive_activation(host, trigger="post_execution", allowed_authorities=["planner"],
        goal_ids=[f"goal:{i}" for i in range(17 if overflow == "goals" else 1)],
        source_refs=[f"source:{i}" for i in range(33 if overflow == "sources" else 1)],
        responsibilities=[CognitiveResponsibilityProposal(local_ref=f"r{i}", outcome="A requested outcome", confidence=1.0)
                          for i in range(13 if overflow == "responsibilities" else 1)]))
    assert result is None and not calls
    assert any("cognitive_activation_failed" in str(row) for row in logs)


def test_activation_projection_retains_tail_lifecycle_and_disclosure_safe_social_context():
    state = {
        "goal_state": [{"goal_id": f"goal:{i}", "work_status": "completed"} for i in range(16)],
        "existing_work_activities": [{"activity_id": f"work:{i}", "state": "completed"} for i in range(24)],
        "trusted_state_change": {"trusted_terminal_evidence": [
            {"evidence_id": f"evidence:{i}", "status": "completed"} for i in range(32)]},
        "memory_summary": "A disclosure-safe shared experience selected by Memory.",
        "relational_memory_selection": {"audience_refs": ["person:1"]},
        "interaction_context": {"pending_speech": [{"activity_id": "greeting", "state": "queued"}]},
    }
    state["goal_state"][-1]["work_status"] = "failed"
    state["existing_work_activities"][-1]["state"] = "failed"
    state["trusted_state_change"]["trusted_terminal_evidence"][-1]["status"] = "failed"
    assert _compact_activation_state(state) == state


def test_activation_host_rejects_partial_source_scope():
    request = planner_request().model_copy(update={"source_refs": ["evidence-1", "evidence-2"]})
    decision = CognitiveActivationDecision(cognitive_requests=[{
        "authority": "planner", "goal_ids": request.goal_ids,
        "responsibility_refs": request.responsibility_refs, "source_refs": ["evidence-1"],
    }], confidence=1.0)
    with pytest.raises(ValueError, match="exact source scope"):
        decision.validate_request(request)


@pytest.mark.parametrize("provider", ["ollama", "sglang"])
def test_complete_activation_packet_over_budget_never_reaches_inference(provider):
    from unittest.mock import AsyncMock, patch
    import httpx
    from agent.app.clients.ollama_client import OllamaClient, OllamaGenerationError
    from agent.app.clients.sglang_client import SGLangClient

    current = planner_request().model_copy(update={"state": _compact_activation_state({
        "memory_summary": "disclosure-safe material context " * 3000,
    })})
    client_type = SGLangClient if provider == "sglang" else OllamaClient
    model = client_type(base_url="http://unused.invalid/v1", model="test-model", purpose="cognitive_activation", timeout_ms=1000)
    transport = AsyncMock()
    transport.__aenter__.return_value = transport
    transport.post.return_value = httpx.Response(200, json={"count": 10000, "tokens": [1] * 10000, "max_model_len": 4096},
        request=httpx.Request("POST", "http://unused.invalid/v1/tokenize"))
    with patch(f"agent.app.clients.{provider}_client.httpx.AsyncClient", return_value=transport) as http:
        with pytest.raises(OllamaGenerationError) as caught:
            asyncio.run(CognitiveActivationResolver(model).resolve(current))
        assert caught.value.failure_class == "prompt_budget_exceeded"
        if provider == "sglang":
            transport.post.assert_awaited_once()
            assert transport.post.call_args.args[0].endswith("/tokenize")
        else:
            http.assert_not_called()
