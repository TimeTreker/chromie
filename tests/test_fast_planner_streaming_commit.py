from __future__ import annotations
import json
from typing import Any
import pytest
from jsonschema import Draft202012Validator
from agent.app.capabilities.catalog import CatalogCapability
from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_model_contract import PlannerDTOContractError
from agent.app.planner_fast_validation import AuthoritativeGroundingValidationError, validate_fast_advance_output
from agent.app.planner_prompt import fast_advance_capability_prompt_projection, fast_advance_layered_prompt, fast_advance_semantic_capability_projection, fast_advance_streaming_capability_prompt_projection, fast_responsibility_decision_projection, fast_streaming_advance_system_prompt, planner_interaction_context_projection
from agent.app.planner_schema import fast_streaming_advance_response_schema
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter, CognitiveStageFailure, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
from shared.chromie_contracts.plan import FastPlannerAdvanceModelOutput, FastPlannerStreamFailure, FastPlannerStreamTerminal
from tests.test_cognitive_runtime_pr7 import admitted_core, new_goal_association, respond_plan

class _Catalog:

    def __init__(self, entries: list[CatalogCapability] | None=None) -> None:
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
    return CognitiveWorkRequest(sid='turn-stream', text='你好', language='zh-CN', responsibilities=[CognitiveResponsibilityProposal(local_ref='reply', outcome='reply to the greeting', output_mode='speech', confidence=0.98)], interpretation_confidence=0.98, context={})


def test_capability_argument_decoder_order_matches_sorted_catalog_recursively():
    arguments = {"type": "object", "properties": {
        "zeta": {"type": "number"},
        "alpha": {"type": "array", "items": {"type": "object", "properties": {
            "z": {"type": "number"}, "a": {"type": "string"}}, "required": ["z", "a"]}},
    }, "required": ["zeta", "alpha"], "additionalProperties": False}
    capability = {"capability_id": "test.object", "input_schema": arguments}
    schema = fast_streaming_advance_response_schema(["r1"], capabilities=[capability])
    found = []

    def visit(node):
        if isinstance(node, dict):
            properties = node.get("properties", {})
            if properties.get("capability_id", {}).get("enum") == ["test.object"]:
                found.append(properties["args"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    assert found
    for compiled in found:
        assert list(compiled["properties"]) == ["alpha", "zeta"]
        assert list(compiled["properties"]["alpha"]["items"]["properties"]) == ["a", "z"]
        example = {"zeta": 0.2, "alpha": [{"z": 10, "a": "same source value"}]}
        Draft202012Validator(arguments).validate(example)
        Draft202012Validator(compiled).validate(example)
    assert list(arguments["properties"]) == ["zeta", "alpha"]

def _valid_output() -> dict[str, Any]:
    return {"disposition": "respond", "coverage": "complete", "covered_responsibility_refs": ["reply"],
        "activities": [{"role": "complete_response", "activity_id": "greeting-need", "source_responsibility_refs": ["reply"],
            "timing": "parallel", "rationale": "An ordinary greeting can be returned from context."}],
        "continuations": [], "confidence": 1.0, "unresolved": [], "reason_summary": "Establish an ordinary greeting obligation."}


def _wire_output(payload):
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize("with_lookup", [False, True])
@pytest.mark.parametrize("source_kind", ["unresolved_meaning", "execution_input"])
@pytest.mark.parametrize("sources", [
    [], ["safe_default"], ["capability_schema"], ["authoritative_context"],
    ["authoritative_context", "safe_default"],
    ["authoritative_context", "capability_schema"],
    ["authoritative_context", "capability_schema", "trusted_observation", "trusted_query", "owner_preference", "safe_default"],
])
def test_native_clarification_requires_owned_resolution_sources(source_kind, sources, with_lookup):
    from agent.app.clients.sglang_protocol import build_sglang_chat_payload
    from agent.app.planner_schema import capability_lookup_response_schema
    from types import SimpleNamespace
    from agent.app.inference_compute import CognitionComputeClass
    from shared.chromie_contracts.core_interpretation import UserMeaningUncertainty
    from shared.chromie_contracts.plan import PlannerInformationGap

    responsibility = CognitiveResponsibilityProposal(local_ref="r1", outcome="Get weather for the requested place",
        output_mode="information", confidence=0.9)
    uncertainty = UserMeaningUncertainty(local_ref="u1", kind="referent", description="Which place", responsibility_refs=["r1"])
    capability = {"capability_id": "test.weather", "input_schema": {"type": "object",
        "properties": {"location": {"type": "string"}}, "required": ["location"]}}
    schema = fast_streaming_advance_response_schema(["r1"], responsibilities=[responsibility], capabilities=[capability],
        meaning_uncertainties=[uncertainty] if source_kind == "unresolved_meaning" else [])
    if with_lookup:
        schema = capability_lookup_response_schema(schema, [SimpleNamespace(capability_id="test.indexed")])
    gap = {"gap_id": "place", "description": "Which place", "required_for": ["location"],
        "preferred_resolution": "ask_user", "source_kind": source_kind,
        "source_reference": "Which place" if source_kind == "unresolved_meaning" else "test.weather",
        "resolution_sources_considered": sources}
    raw = {"disposition": "clarify", "coverage": "partial", "covered_responsibility_refs": ["r1"],
        "activities": [{"role": "clarification", "activity_id": "ask", "source_responsibility_refs": ["r1"],
                        "information_gaps": [gap]}],
        "continuations": [], "confidence": 0.9, "unresolved": ["Which place"], "reason_summary": "Missing place."}
    try:
        PlannerInformationGap.model_validate(gap)
        expected = True
    except ValueError:
        expected = False
    wire = build_sglang_chat_payload(model="fixed", messages=[], compute_class=CognitionComputeClass.REALTIME,
        options={}, response_format=schema, stream=True, priority_step=100)["response_format"]["json_schema"]["schema"]
    for contract in (schema, wire):
        assert Draft202012Validator(contract).is_valid(raw) == expected
    if expected and "capability_schema" in sources:
        # Source order is not semantic. The native decoder may choose an order,
        # but canonical validation must continue accepting existing valid DTOs.
        gap["resolution_sources_considered"] = list(reversed(sources))
        PlannerInformationGap.model_validate(gap)
        assert Draft202012Validator(schema).is_valid(raw)
        assert not Draft202012Validator(wire).is_valid(raw)
    if with_lookup:
        assert Draft202012Validator(wire).is_valid({"requested_capability_ids": ["test.indexed"]})
        assert not Draft202012Validator(wire).is_valid({"requested_capability_ids": ["unknown"]})


@pytest.mark.asyncio
@pytest.mark.parametrize('gap', ['actor', 'destination_location', '目标对象尚未确定'])
@pytest.mark.parametrize('preserve_gap', [False, True])
async def test_terminal_cannot_drop_gi_meaning_gap(gap: str, preserve_gap: bool) -> None:
    """Replay the laptop's accepted shake plan with unresolved WHAT contrasts."""
    responsibility = CognitiveResponsibilityProposal(local_ref='r1', outcome='shake head twice', output_mode='body_action', bindings={'count': 2}, confidence=0.5)
    request = CognitiveWorkRequest(sid='unresolved-shake', text='摇两下头。', language='zh-CN', responsibilities=[responsibility], meaning_uncertainties=[{"local_ref": "u1", "kind": "referent", "description": gap, "responsibility_refs": ["r1"]}], interpretation_confidence=0.5)
    output = {'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['r1'], 'activities': [{'role': 'capability', 'capability_id': 'soridormi.shake_no', 'activity_id': 'act_shake_head_twice', 'args': {'count': 2}, 'depends_on': [], 'source_responsibility_refs': ['r1']}], 'continuations': [], 'confidence': 1.0, 'unresolved': [], 'reason_summary': 'Execute head shake twice as requested'}
    if preserve_gap:
        output['disposition'] = 'clarify'
        output['coverage'] = 'partial'
        output['unresolved'] = [gap]
        output['activities'] = [{'activity_id': 'ask-meaning', 'role': 'clarification', 'source_responsibility_refs': ['r1'], 'information_gaps': [{'gap_id': 'missing-meaning', 'description': gap, 'required_for': [gap], 'preferred_resolution': 'ask_user', 'source_kind': 'unresolved_meaning', 'source_reference': gap, 'resolution_sources_considered': ['authoritative_context']}]}]
    model = _StreamingModel([_wire_output(output)])
    catalog = _Catalog([_nod_catalog_capability().model_copy(update={'capability_id': 'soridormi.shake_no', 'description': 'Shake head twice.'})])
    frames = [frame async for frame in FastPlannerResolver(model, catalog).stream_advance(request)]
    assert model.calls == 1
    if preserve_gap:
        assert isinstance(frames[-1], FastPlannerStreamTerminal)
        assert frames[-1].advance.disposition == 'clarify'
    else:
        assert isinstance(frames[-1], FastPlannerStreamFailure)
        assert frames[-1].failure_domain == 'model_contract'
        assert not frames[-1].retryable
        assert not any((isinstance(frame, FastPlannerStreamTerminal) for frame in frames))

@pytest.mark.parametrize('preserve_all', [False, True])
@pytest.mark.parametrize('independent', [False, True])
def test_meaning_gaps_preserve_independent_terminal_work(preserve_all: bool, independent: bool) -> None:
    responsibilities = [CognitiveResponsibilityProposal(local_ref=ref, outcome=outcome, output_mode='body_action', bindings={'count': 2}, confidence=0.9) for ref, outcome in [('r1', 'shake the indicated head twice'), ('r2', 'nod twice')]]
    request = CognitiveWorkRequest(sid='mixed-meaning', text='让那个摇两下头，你点两下头。', responsibilities=responsibilities, meaning_uncertainties=[{'local_ref': f'u{i}', 'kind': 'referent', 'description': name, 'responsibility_refs': ['r1']} for i, name in enumerate(['actor', 'target_identity'])])
    gaps = [{'gap_id': f'gap-{name}', 'description': name, 'blocking': True, 'resolved': False, 'required_for': [name], 'preferred_resolution': 'ask_user', 'source_kind': 'unresolved_meaning', 'source_reference': name, 'resolution_sources_considered': ['authoritative_context']} for name in ([item.description for item in request.meaning_uncertainties] if preserve_all else ['actor'])]
    raw = {'disposition': 'mixed', 'coverage': 'complete', 'covered_responsibility_refs': ['r1', 'r2'], 'activities': [{'activity_id': 'ask-meaning', 'role': 'clarification', 'source_responsibility_refs': ['r1'], 'information_gaps': gaps}, {'activity_id': 'nod', 'role': 'capability', 'capability_id': 'soridormi.nod_yes', 'args': {'count': 2}, 'depends_on': [], 'source_responsibility_refs': ['r2'] if independent else ['r1', 'r2']}], 'continuations': [], 'confidence': 0.9, 'unresolved': [item.description for item in request.meaning_uncertainties], 'reason_summary': 'Clarify the first request; perform the independent nod.'}
    capabilities = [_nod_catalog_capability().model_dump(mode='json')]
    output = FastPlannerAdvanceModelOutput.model_validate(raw)
    if preserve_all and independent:
        validate_fast_advance_output(output, request=request, responsibilities=responsibilities, capabilities=capabilities)
        schema = fast_streaming_advance_response_schema(['r1', 'r2'], responsibilities=responsibilities, capabilities=capabilities, meaning_uncertainties=request.meaning_uncertainties)
        Draft202012Validator(schema).validate(raw)
    else:
        with pytest.raises(AuthoritativeGroundingValidationError):
            validate_fast_advance_output(output, request=request, responsibilities=responsibilities, capabilities=capabilities)

def _body_request() -> tuple[CognitiveWorkRequest, CognitiveResponsibilityProposal]:
    responsibility = CognitiveResponsibilityProposal(local_ref='walk', outcome='walk forward for ten seconds', output_mode='body_action', bindings={'duration_s': 10}, confidence=0.99)
    return (CognitiveWorkRequest(sid='turn-stream-walk', text='向前走十秒', language='zh-CN', responsibilities=[responsibility], interpretation_confidence=0.99, context={}), responsibility)

def _walk_capability() -> dict[str, Any]:
    return {'capability_id': 'soridormi.walk_forward', 'description': 'Walk the robot forward for the supplied duration.', 'input_schema': {'type': 'object', 'properties': {'duration_s': {'type': 'number', 'minimum': 0.1}}, 'required': ['duration_s'], 'additionalProperties': False}, 'effects': ['locomotion'], 'hints': {'semantic_type': 'body_action'}}


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["zh_left", "zh_right", "en_literal", "en_case_only", "missing", "foreign_span"])
async def test_streamed_string_argument_mapping_preserves_source_ownership(variant):
    from shared.chromie_contracts.user_turn import user_turn_source_tokens

    literal = variant in {"en_literal", "en_case_only"}
    direction = "right" if variant == "zh_right" else "left"
    outcome = "turn left" if literal else ("向右转" if direction == "right" else "向左转")
    text = "Hello, turn left." if literal else "你好，" + outcome + "。"
    tokens = user_turn_source_tokens(text)
    start = next(item["ref"] for item in tokens if item["surface"] == ("turn" if literal else "向"))
    selected = next(item["ref"] for item in tokens if item["surface"] == ("left" if literal else "右" if direction == "right" else "左"))
    request = CognitiveWorkRequest(
        sid="source-owner", text=text, language="en-US" if literal else "zh-CN",
        interpretation_confidence=1,
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="turn", outcome="turn LEFT" if variant == "en_case_only" else outcome,
            output_mode="body_action", confidence=1,
            source_evidence={"source_start_token_ref": start, "source_end_token_ref": tokens[-1]["ref"]},
        )],
    )
    capability = CatalogCapability(
        capability_id="soridormi.turn_in_place", agent_id="capability_agent",
        description="Turn left or right in place.", available=True, interaction_executable=True,
        prompt_tier="common", effects=["locomotion"], hints={"semantic_type": "body_action"},
        input_schema={"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["left", "right"]},
            "duration_s": {"type": "number", "default": 2.0},
        }, "required": ["direction"], "additionalProperties": False},
    )
    sources = {} if literal or variant == "missing" else {"direction": {
        "source_start_token_ref": "t0" if variant == "foreign_span" else selected,
        "source_end_token_ref": "t0" if variant == "foreign_span" else selected,
    }}
    raw = {"activities": [{"role": "capability", "activity_id": "turn", "capability_id": capability.capability_id,
        "args": {"direction": direction}, "argument_sources": sources, "depends_on": [],
        "source_responsibility_refs": ["turn"]}], "disposition": "execute", "coverage": "complete",
        "covered_responsibility_refs": ["turn"], "continuations": [], "confidence": 1,
        "unresolved": [], "reason_summary": "Realize the requested turn."}
    model = _StreamingModel([json.dumps(raw)])
    events = [event async for event in FastPlannerResolver(model, _Catalog([capability])).stream_advance(request)]
    assert model.calls == 1
    assert len(events) == 1
    schema = model.last_kwargs["response_format"]
    for contract in (schema, {"$defs": schema.get("$defs", {}), "oneOf": schema["oneOf"]}):
        assert Draft202012Validator(contract).is_valid(raw) is (variant != "missing")
    if variant in {"missing", "foreign_span"}:
        assert isinstance(events[0], FastPlannerStreamFailure)
        assert events[0].failure_class == "fast_stream_contract_invalid"
        assert events[0].failure_stage == "before_commit"
    else:
        assert isinstance(events[0], FastPlannerStreamTerminal)
        activity, = events[0].advance.activities
        assert activity.args == {"direction": direction}
        assert {name: span.model_dump() for name, span in activity.argument_sources.items()} == sources

def _walk_catalog_capability() -> CatalogCapability:
    return CatalogCapability(capability_id='soridormi.walk_forward', agent_id='capability_agent', description='Walk the robot forward for the supplied duration.', input_schema=_walk_capability()['input_schema'], effects=['locomotion'], available=True, interaction_executable=True, prompt_tier='common', hints={'semantic_type': 'body_action'})

def _look_at_person_catalog_capability() -> CatalogCapability:
    return CatalogCapability(capability_id='soridormi.look_at_person', agent_id='capability_agent', description='Look at a person identified by a trusted target reference.', input_schema={'type': 'object', 'properties': {'target_ref': {'type': 'string', 'minLength': 1}}, 'required': ['target_ref'], 'additionalProperties': False}, effects=['physical_motion'], available=True, interaction_executable=True, prompt_tier='common', behavior_domains=['social_attention', 'orientation'], can_run_parallel=True, parallel_metadata_declared=True, exclusive_group='body.head', resource_claims=['body.head'], hints={'argument_realization': {'person_addressee_target': {'source_entity_type': 'addressee', 'planner_owned': True, 'arguments': ['target_ref'], 'minimum_arguments': 1, 'contract': 'Copy target_ref only from current trusted target evidence.'}}})

def _nod_catalog_capability() -> CatalogCapability:
    return CatalogCapability(capability_id='soridormi.nod_yes', agent_id='capability_agent', description='Perform a bounded affirmative head nod.', input_schema={'type': 'object', 'properties': {'count': {'type': 'integer', 'minimum': 1}}, 'required': ['count'], 'additionalProperties': False}, effects=['physical_motion'], available=True, interaction_executable=True, prompt_tier='common', can_run_parallel=True, parallel_metadata_declared=True, exclusive_group='body.head', resource_claims=['body.head'])

@pytest.mark.asyncio
async def test_nod_count_binding_evidence_wrapper_is_semantically_equal_to_scalar_arg() -> None:
    request = CognitiveWorkRequest(
        sid="nod-count-evidence-wrapper",
        text="nod your head 5 times, please",
        language="en-US",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="nod your head 5 times",
            output_mode="body_action",
            continuity_scope="goal",
            bindings={"count": {"value": 5, "source_evidence": "t3"}},
            confidence=1.0,
        )],
        interpretation_confidence=1.0,
    )
    raw = {
        "disposition": "execute",
        "coverage": "complete",
        "covered_responsibility_refs": ["r1"],
        "activities": [{
            "activity_id": "nod-five",
            "role": "capability",
            "capability_id": "soridormi.nod_yes",
            "args": {"count": 5},
            "depends_on": [],
            "source_responsibility_refs": ["r1"],
        }],
        "continuations": [],
        "confidence": 1.0,
        "unresolved": [],
        "reason_summary": "Perform exactly five nods.",
    }
    model = _StreamingModel([_wire_output(raw)])
    frames = [
        frame
        async for frame in FastPlannerResolver(
            model, _Catalog([_nod_catalog_capability()])
        ).stream_advance(request)
    ]

    assert isinstance(frames[-1], FastPlannerStreamTerminal)
    assert frames[-1].advance.activities[0].args == {"count": 5}
    assert request.responsibilities[0].bindings == {"count": 5}


def _blink_social_catalog_capability() -> CatalogCapability:
    return CatalogCapability(capability_id='soridormi.blink_eyes', agent_id='capability_agent', description='Blink as an optional visual social expression.', input_schema={'type': 'object', 'properties': {'count': {'type': 'integer', 'minimum': 1, 'default': 2}}, 'additionalProperties': False}, effects=['visual_expression'], available=True, interaction_executable=True, prompt_tier='common', behavior_domains=['social_attention', 'facial_expression'], can_run_parallel=True, parallel_metadata_declared=True, exclusive_group='visual.eyes', resource_claims=['visual.eyes'])

def _look_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(sid='turn-stream-look', text='看着我三秒', language='zh-CN', responsibilities=[CognitiveResponsibilityProposal(local_ref='look', outcome='look at the addressee', output_mode='body_action', body_effect_family='gaze_or_orientation', bindings={'addressee': '我'}, confidence=1.0)], interpretation_confidence=1.0, context={'active_user_target': {'source': 'live_perception', 'target_ref': 'current_speaker', 'relative_direction': 'front', 'confidence': 1.0, 'evidence_refs': ['scenario:current-speaker']}})

def _look_output(*, target_ref: str) -> dict[str, Any]:
    return {'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['look'], 'activities': [{'role': 'capability', 'capability_id': 'soridormi.look_at_person', 'activity_id': 'look-at-speaker', 'args': {'target_ref': target_ref}, 'depends_on': [], 'source_responsibility_refs': ['look']}], 'continuations': [], 'confidence': 1.0, 'unresolved': [], 'reason_summary': 'Look at the trusted current speaker target.'}

def _structured_resource_catalog_capability() -> CatalogCapability:
    realization = {'physical_resource_entity': {'source_entity_type': 'entity', 'planner_owned': True, 'arguments': ['resource'], 'minimum_arguments': 1, 'contract': 'Conserve the exact entity inside resource.'}, 'physical_resource_location': {'source_entity_type': 'location', 'planner_owned': True, 'arguments': ['source'], 'minimum_arguments': 1, 'contract': 'Conserve the exact location inside source.'}, 'physical_resource_distance': {'source_entity_type': 'distance', 'planner_owned': True, 'arguments': ['source'], 'minimum_arguments': 1, 'contract': 'Conserve the exact distance inside source.'}, 'physical_resource_recipient': {'source_entity_type': 'recipient', 'planner_owned': True, 'arguments': ['recipient'], 'minimum_arguments': 1, 'contract': 'Conserve the exact recipient inside recipient.'}}
    return CatalogCapability(capability_id='soridormi.acquire_and_deliver_resource', agent_id='capability_agent', description='Acquire and deliver a physical resource.', input_schema={'type': 'object', 'properties': {'resource': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['physical_object']}, 'description': {'type': 'string', 'minLength': 1}}, 'required': ['kind', 'description'], 'additionalProperties': False}, 'source': {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['known']}, 'description': {'type': 'string'}, 'bindings': {'type': 'object'}}, 'required': ['status'], 'additionalProperties': False}, 'recipient': {'type': 'object', 'properties': {'description': {'type': 'string', 'minLength': 1}}, 'required': ['description'], 'additionalProperties': False}}, 'required': ['resource', 'source', 'recipient'], 'additionalProperties': False}, effects=['physical_motion', 'resource_delivery'], available=True, interaction_executable=True, prompt_tier='common', hints={'semantic_scope': {'responsibility_type': 'acquire_and_deliver_resource', 'resource_kinds': ['physical_object']}, 'argument_realization': realization})


def _provider_owned_structured_resource_capability() -> CatalogCapability:
    capability = _structured_resource_catalog_capability()
    return capability.model_copy(update={
        "hints": {
            **capability.hints,
            "resource_contract": {
                "provider_owns": ["source_resolution", "navigation", "perception"],
            },
        },
    })

def _weather_information_catalog_capability() -> CatalogCapability:
    return CatalogCapability(
        capability_id='chromie.weather.lookup',
        agent_id='capability_agent',
        description='Look up weather information.',
        input_schema={
            'type': 'object',
            'properties': {'location': {'type': 'string'}},
            'required': ['location'],
            'additionalProperties': False,
        },
        effects=['external_grounded_information'],
        available=True,
        interaction_executable=True,
        prompt_tier='common',
        hints={
            'semantic_scope': {
                'domain': 'weather_forecast',
                'responsibility_type': 'acquire_and_deliver_resource',
                'resource_kinds': ['information'],
            }
        },
    )


def _structured_resource_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(sid='turn-stream-resource', text='there is a bottle of milk ahead of you about 50 meters, please bring it to me', language='en-US', responsibilities=[CognitiveResponsibilityProposal(local_ref='fetch', outcome='acquire and deliver the resource', output_mode='body_action', body_effect_family='task_physical_effect', bindings={'entity': 'bottle of milk', 'location': 'ahead of you about 50 meters', 'distance': 50, 'recipient': 'me'}, confidence=1.0)], interpretation_confidence=1.0)

def _structured_resource_output(*, recipient: str='me') -> dict[str, Any]:
    return {'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['fetch'], 'activities': [{'role': 'capability', 'capability_id': 'soridormi.acquire_and_deliver_resource', 'activity_id': 'fetch-milk', 'args': {'resource': {'kind': 'physical_object', 'description': 'bottle of milk'}, 'source': {'status': 'known', 'description': 'ahead of you about 50 meters', 'bindings': {'distance': 50}}, 'recipient': {'description': recipient}}, 'depends_on': [], 'source_responsibility_refs': ['fetch']}], 'continuations': [], 'confidence': 1.0, 'unresolved': [], 'reason_summary': 'Acquire the resource and deliver it.'}



def test_planner_interaction_context_drops_prior_turn_delivery_as_completion_evidence() -> None:
    context = {
        "already_spoken": [{"text": "current-turn answer", "turn_id": "turn-current"}],
        "pending_speech": [],
        "prior_delivered_speech": [{"text": "older answer must not satisfy this turn", "turn_id": "turn-old"}],
    }
    projected = planner_interaction_context_projection(context)
    assert projected["already_spoken"] == context["already_spoken"]
    assert projected["pending_speech"] == []
    assert "prior_delivered_speech" not in projected
    assert "prior_delivered_speech" in context


def test_fast_stream_prompt_hides_prior_turn_delivered_words_but_keeps_current_delivery_state() -> None:
    current = _structured_resource_request()
    current.context["interaction_context"] = {
        "already_spoken": [{"text": "CURRENT DELIVERY MARKER", "turn_id": current.sid}],
        "prior_delivered_speech": [{"text": "OLD DELIVERY MARKER", "turn_id": "older-turn"}],
    }
    prompt = str(fast_advance_layered_prompt(
        current, responsibilities=current.responsibilities, capabilities=[]
    ))
    assert "CURRENT DELIVERY MARKER" in prompt
    assert "OLD DELIVERY MARKER" not in prompt
    assert "prior-turn delivered speech are context only" in prompt


def _contextual_structured_resource_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid="turn-context-resource",
        text="I would appreciate it if you can bring it to me.",
        language="en-US",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="fetch",
            outcome="bring the bottle of milk to the user",
            output_mode="body_action",
            body_effect_family="task_physical_effect",
            continuity_scope="goal",
            bindings={
                "entity": {
                    "confidence": 1.0, "entity_type": "object", "name": "entity",
                    "value": {
                        "confidence": 1.0, "entity_type": "object",
                        "name": "milk_bottle", "value": "bottle of milk",
                    },
                },
                "location": {
                    "confidence": 1.0, "entity_type": "location", "name": "location",
                    "value": "in front of you",
                },
                "distance": {
                    "confidence": 1.0, "entity_type": "distance", "name": "distance",
                    "value": {
                        "confidence": 1.0, "entity_type": "measurement",
                        "name": "distance", "value": 50, "unit": "meters",
                    },
                },
                "recipient": {
                    "confidence": 1.0, "entity_type": "person", "name": "recipient",
                    "value": "user",
                },
            },
            confidence=1.0,
        )],
        interpretation_confidence=1.0,
    )


def _contextual_structured_resource_output() -> dict[str, Any]:
    return {
        "disposition": "execute",
        "coverage": "complete",
        "covered_responsibility_refs": ["fetch"],
        "activities": [{
            "role": "capability",
            "capability_id": "soridormi.acquire_and_deliver_resource",
            "activity_id": "fetch-context-milk",
            "args": {
                "resource": {"kind": "physical_object", "description": "bottle of milk"},
                "source": {
                    "status": "known",
                    "description": "in front of you",
                    "bindings": {
                        "location": "in front of you",
                        "distance": {"value": 50, "unit": "meters"},
                    },
                },
                "recipient": {"description": "user"},
            },
            "depends_on": [],
            "source_responsibility_refs": ["fetch"],
        }],
        "continuations": [],
        "confidence": 1.0,
        "unresolved": [],
        "reason_summary": "Acquire the context-resolved resource and deliver it.",
    }


def _contextual_resource_with_source_role_bindings() -> CognitiveWorkRequest:
    request = _contextual_structured_resource_request()
    responsibility = request.responsibilities[0]
    bindings = dict(responsibility.bindings)
    bindings["source_location"] = bindings.pop("location")
    bindings["source_distance"] = bindings.pop("distance")
    return request.model_copy(update={
        "responsibilities": [responsibility.model_copy(update={"bindings": bindings})],
    })


def test_fast_schema_forbids_current_turn_source_spans_for_binding_grounded_resource_args() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import _source_tokens

    request = _contextual_structured_resource_request()
    schema = fast_streaming_advance_response_schema(
        ["fetch"],
        responsibilities=request.responsibilities,
        capabilities=[_structured_resource_catalog_capability().model_dump(mode="json")],
        source_token_refs=[item["ref"] for item in _source_tokens(request.text)],
        language=request.language,
    )
    activity = schema["properties"]["activities"]["items"]["oneOf"][0]
    argument_sources = activity["properties"]["argument_sources"]
    assert argument_sources["properties"] == {}
    assert argument_sources["additionalProperties"] is False


def test_fast_schema_forbids_false_source_span_for_inherited_source_role_bindings() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import _source_tokens

    request = _contextual_resource_with_source_role_bindings()
    capability = _provider_owned_structured_resource_capability().model_dump(mode="json")
    schema = fast_streaming_advance_response_schema(
        ["fetch"], responsibilities=request.responsibilities,
        capabilities=[capability],
        meaning_uncertainties=[],
        source_token_refs=[item["ref"] for item in _source_tokens(request.text)],
        language=request.language,
    )
    activity = schema["properties"]["activities"]["items"]
    assert activity["properties"]["role"]["enum"] == ["capability"]
    assert "clarify" not in schema["properties"]["disposition"]["enum"]
    assert activity["properties"]["argument_sources"]["properties"] == {}
    source_bindings = activity["properties"]["args"]["properties"]["source"]["properties"]["bindings"]
    assert source_bindings["properties"]["distance"] == {"enum": [{"value": 50, "unit": "meters"}]}
    assert source_bindings["required"] == ["distance"]
    valid = _contextual_structured_resource_output()
    assert Draft202012Validator(schema).is_valid(valid)
    wrong_shape = json.loads(json.dumps(valid))
    wrong_shape["activities"][0]["args"]["source"]["bindings"]["distance"] = "50 meters"
    assert not Draft202012Validator(schema).is_valid(wrong_shape)
    invalid = json.loads(json.dumps(valid))
    invalid["activities"][0]["argument_sources"] = {
        "source": {"source_start_token_ref": "t4", "source_end_token_ref": "t10"},
    }
    assert not Draft202012Validator(schema).is_valid(invalid)


def test_fast_schema_does_not_offer_provider_owned_resource_as_missing_input() -> None:
    request = _contextual_resource_with_source_role_bindings()
    schema = fast_streaming_advance_response_schema(
        ["fetch"], responsibilities=request.responsibilities,
        capabilities=[
            _provider_owned_structured_resource_capability().model_dump(mode="json"),
            _nod_catalog_capability().model_dump(mode="json"),
        ],
        meaning_uncertainties=[],
        language=request.language,
    )
    clarification = schema["properties"]["activities"]["items"]["oneOf"][-1]
    gap = clarification["properties"]["information_gaps"]["items"]
    allowed = {
        reference
        for variant in gap.get("oneOf", [gap])
        for reference in variant["properties"]["source_reference"].get("enum", [])
    }
    assert "soridormi.acquire_and_deliver_resource" not in allowed


def test_fast_host_rejects_current_turn_citation_for_inherited_source_role_bindings() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import _source_tokens

    request = _contextual_resource_with_source_role_bindings()
    end_ref = _source_tokens(request.text)[-1]["ref"]
    responsibility = CognitiveResponsibilityProposal.model_validate({
        **request.responsibilities[0].model_dump(mode="json"),
        "source_evidence": {"source_start_token_ref": "t0", "source_end_token_ref": end_ref},
    })
    request = request.model_copy(update={"responsibilities": [responsibility]})
    invalid = _contextual_structured_resource_output()
    invalid["activities"][0]["argument_sources"] = {
        "source": {"source_start_token_ref": "t4", "source_end_token_ref": end_ref},
    }
    with pytest.raises(AuthoritativeGroundingValidationError, match="binding-grounded argument"):
        validate_fast_advance_output(
            FastPlannerAdvanceModelOutput.model_validate(invalid),
            request=request, responsibilities=request.responsibilities,
            capabilities=[_structured_resource_catalog_capability().model_dump(mode="json")],
        )


@pytest.mark.asyncio
async def test_fast_stream_accepts_contextual_resource_bindings_without_fake_current_turn_spans() -> None:
    request = _contextual_structured_resource_request()
    assert request.responsibilities[0].bindings == {
        "entity": "bottle of milk",
        "location": "in front of you",
        "distance": {"value": 50, "unit": "meters"},
        "recipient": "user",
    }
    model = _StreamingModel([_wire_output(_contextual_structured_resource_output())])
    frames = [
        frame
        async for frame in FastPlannerResolver(
            model, _Catalog([_structured_resource_catalog_capability()])
        ).stream_advance(request)
    ]

    assert isinstance(frames[-1], FastPlannerStreamTerminal), frames[-1]
    activity = frames[-1].advance.activities[0]
    assert activity.capability_id == "soridormi.acquire_and_deliver_resource"
    assert activity.argument_sources == {}
    assert activity.args["recipient"]["description"] == "user"
    assert activity.args["source"]["bindings"]["distance"] == {
        "value": 50, "unit": "meters"
    }


@pytest.mark.asyncio
async def test_fast_stream_accepts_inherited_source_role_bindings_without_span() -> None:
    request = _contextual_resource_with_source_role_bindings()
    model = _StreamingModel([_wire_output(_contextual_structured_resource_output())])
    frames = [
        frame async for frame in FastPlannerResolver(
            model, _Catalog([_structured_resource_catalog_capability()])
        ).stream_advance(request)
    ]
    assert isinstance(frames[-1], FastPlannerStreamTerminal), frames[-1]
    assert frames[-1].advance.activities[0].argument_sources == {}

@pytest.mark.asyncio
async def test_fast_stream_filters_incompatible_information_capability_before_generation() -> None:
    request = _structured_resource_request()
    model = _StreamingModel([_wire_output(_structured_resource_output())])
    frames = [
        frame
        async for frame in FastPlannerResolver(
            model,
            _Catalog([
                _structured_resource_catalog_capability(),
                _weather_information_catalog_capability(),
                _blink_social_catalog_capability(),
            ]),
        ).stream_advance(request)
    ]

    assert isinstance(frames[-1], FastPlannerStreamTerminal)
    schema_text = json.dumps(model.last_kwargs['response_format'], ensure_ascii=False)
    assert 'soridormi.acquire_and_deliver_resource' in schema_text
    assert 'chromie.weather.lookup' not in schema_text
    assert 'soridormi.blink_eyes' in schema_text


@pytest.mark.asyncio
async def test_fast_stream_keeps_body_capabilities_across_social_domain_labels() -> None:
    request = CognitiveWorkRequest(
        sid="turn-stream-blink",
        text="blink twice",
        language="en-US",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="blink",
            outcome="blink twice",
            output_mode="body_action",
            body_effect_family="social_expression",
            bindings={"count": 2},
            confidence=1.0,
        )],
        interpretation_confidence=1.0,
    )
    raw = {
        "disposition": "execute",
        "coverage": "complete",
        "covered_responsibility_refs": ["blink"],
        "activities": [{
            "role": "capability",
            "capability_id": "soridormi.blink_eyes",
            "activity_id": "blink-twice",
            "args": {"count": 2},
            "depends_on": [],
            "source_responsibility_refs": ["blink"],
        }],
        "continuations": [],
        "confidence": 1.0,
        "unresolved": [],
        "reason_summary": "Blink twice as explicitly requested.",
    }
    model = _StreamingModel([_wire_output(raw)])
    frames = [
        frame
        async for frame in FastPlannerResolver(
            model,
            _Catalog([
                _blink_social_catalog_capability(),
                _structured_resource_catalog_capability(),
            ]),
        ).stream_advance(request)
    ]
    assert isinstance(frames[-1], FastPlannerStreamTerminal)
    schema_text = json.dumps(model.last_kwargs["response_format"], ensure_ascii=False)
    assert "soridormi.blink_eyes" in schema_text
    assert "soridormi.acquire_and_deliver_resource" in schema_text


@pytest.mark.asyncio
async def test_fast_planner_rejects_invalid_argument_source_in_compound_work() -> None:
    request, capabilities, raw, _ = _compound_body_case("walk_nod_turn")
    raw["activities"][1]["argument_sources"]["count"]["source_end_token_ref"] = "t999"
    model = _StreamingModel([_wire_output(raw)])
    frames = [
        frame
        async for frame in FastPlannerResolver(model, _Catalog(capabilities)).stream_advance(request)
    ]
    assert isinstance(frames[-1], FastPlannerStreamFailure)
    assert frames[-1].failure_class == "fast_stream_contract_invalid"
    assert frames[-1].failure_stage == "before_commit"
    assert "not valid under any of the given schemas" in frames[-1].reason



def test_fast_decision_projection_localizes_coverage_bindings_and_relations() -> None:
    look = CognitiveResponsibilityProposal(local_ref='r1', outcome='look at the person', output_mode='body_action', bindings={'entity': 'me', 'parallel_with': ['r2']}, confidence=1.0)
    blink = CognitiveResponsibilityProposal(local_ref='r2', outcome='blink twice', output_mode='body_action', bindings={'count': 2, 'parallel_with': 'r1'}, confidence=1.0)
    projection = fast_responsibility_decision_projection([look, blink])
    assert projection == [
        {"ref": "r1", "outcome": "look at the person", "output_mode": "body_action", "source_evidence": None},
        {"ref": "r2", "outcome": "blink twice", "output_mode": "body_action", "source_evidence": None},
    ]

@pytest.mark.asyncio
async def test_declared_addressee_target_realization_accepts_exact_trusted_ref() -> None:
    model = _StreamingModel([_wire_output(_look_output(target_ref='current_speaker'))])
    resolver = FastPlannerResolver(model, _Catalog([_look_at_person_catalog_capability()]))
    frames = [frame async for frame in resolver.stream_advance(_look_request())]
    assert isinstance(frames[0], FastPlannerStreamTerminal)
    assert frames[0].advance.activities[0].args == {'target_ref': 'current_speaker'}
    assert 'Trusted semantic target evidence JSON' in str(model.last_prompt)
    assert 'person_addressee_target' in str(model.last_prompt)

@pytest.mark.asyncio
async def test_required_target_ref_uses_trusted_evidence_without_binding_mapping() -> None:
    capability = _look_at_person_catalog_capability().model_copy(update={'hints': {}})
    model = _StreamingModel([_wire_output(_look_output(target_ref='current_speaker'))])
    resolver = FastPlannerResolver(model, _Catalog([capability]))
    frames = [frame async for frame in resolver.stream_advance(_look_request())]
    assert isinstance(frames[0], FastPlannerStreamTerminal)
    assert frames[0].advance.activities[0].args['target_ref'] == 'current_speaker'

@pytest.mark.asyncio
async def test_declared_target_realization_rejects_mismatched_trusted_ref() -> None:
    resolver = FastPlannerResolver(_StreamingModel([_wire_output(_look_output(target_ref='invented_person'))]), _Catalog([_look_at_person_catalog_capability()]))
    frames = [frame async for frame in resolver.stream_advance(_look_request())]
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert frames[0].failure_stage == 'before_commit'
    assert 'must copy exact current trusted target evidence' in frames[0].reason

@pytest.mark.asyncio
async def test_declared_structured_resource_realization_accepts_exact_gi_values() -> None:
    resolver = FastPlannerResolver(_StreamingModel([_wire_output(_structured_resource_output())]), _Catalog([_structured_resource_catalog_capability()]))
    frames = [frame async for frame in resolver.stream_advance(_structured_resource_request())]
    assert isinstance(frames[0], FastPlannerStreamTerminal)
    args = frames[0].advance.activities[0].args
    assert args['resource']['description'] == 'bottle of milk'
    assert args['source']['bindings']['distance'] == 50
    assert args['recipient']['description'] == 'me'

@pytest.mark.asyncio
async def test_declared_structured_resource_realization_rejects_lost_gi_value() -> None:
    resolver = FastPlannerResolver(_StreamingModel([_wire_output(_structured_resource_output(recipient='requester'))]), _Catalog([_structured_resource_catalog_capability()]))
    frames = [frame async for frame in resolver.stream_advance(_structured_resource_request())]
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert 'structured resource realization omitted exact UMI bindings' in frames[0].reason
    assert 'recipient=recipient' in frames[0].reason


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [1, 2, 7, 31])
async def test_one_complete_work_decision_is_released_only_after_provider_closes(chunks):
    payload = _wire_output(_valid_output())
    closed = False
    class Provider:
        async def generate_stream(self, *args, **kwargs):
            nonlocal closed
            try:
                for offset in range(0, len(payload), chunks):
                    yield payload[offset:offset + chunks]
            finally:
                closed = True
    stream = FastPlannerResolver(Provider(), _Catalog()).stream_advance(_request())
    result = await anext(stream)
    assert closed
    assert isinstance(result, FastPlannerStreamTerminal)
    assert len(result.advance.activities) == 1
    assert result.advance.activities[0].role == "complete_response"
    assert not hasattr(result.advance.activities[0], "text")
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    "", "invalid", "[]", "{", '{"disposition":',
    '{"disposition":"execute","disposition":"respond"}',
    '{"confidence":NaN}', '{"confidence":Infinity}',
    '{"activities":[{"activity_id":"a","activity_id":"b"}]}',
    _wire_output(_valid_output()) + " trailing", _wire_output(_valid_output())[:-1],
])
async def test_ambiguous_incomplete_or_nonfinite_stream_releases_no_work(bad):
    model = _StreamingModel([bad])
    frames = [frame async for frame in FastPlannerResolver(model, _Catalog()).stream_advance(_request())]
    assert model.calls == 1
    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert frames[0].failure_stage == "before_commit"
    assert frames[0].presentation_commit_id is None
    assert not frames[0].retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("text", "Hello"), ("speech_act", "greeting"), ("auxiliary_activities", [])])
async def test_work_model_cannot_author_sc_words_or_expression(field, value):
    output = _valid_output()
    output["activities"][0][field] = value
    frames = [frame async for frame in FastPlannerResolver(_StreamingModel([_wire_output(output)]), _Catalog()).stream_advance(_request())]
    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamFailure)


@pytest.mark.asyncio
async def test_provider_failure_after_valid_json_still_releases_no_work():
    class Provider:
        async def generate_stream(self, *args, **kwargs):
            yield _wire_output(_valid_output())
            raise RuntimeError("provider stream integrity failed before termination")
    frames = [frame async for frame in FastPlannerResolver(Provider(), _Catalog()).stream_advance(_request())]
    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert "provider stream integrity" in frames[0].reason


@pytest.mark.parametrize("parallel", [False, True])
def test_native_work_schema_requires_dependencies_not_timing(parallel):
    request, responsibility = _body_request()
    capability = {**_walk_capability(), "can_run_parallel": parallel}
    schema = fast_streaming_advance_response_schema([responsibility.local_ref], responsibilities=[responsibility], capabilities=[capability])
    walk = {"role": "capability", "activity_id": "walk", "capability_id": capability["capability_id"],
            "args": {"duration_s": 10}, "source_responsibility_refs": ["walk"]}

    def errors(activity):
        output = {"disposition": "execute", "coverage": "complete", "covered_responsibility_refs": ["walk"],
            "activities": [activity], "continuations": [], "confidence": 1, "unresolved": [],
            "reason_summary": "Direct walk."}
        return list(Draft202012Validator(schema).iter_errors(output))

    # Order and concurrency are WorkDAG dependencies, whatever the provider's parallel support.
    assert not errors({**walk, "depends_on": []})
    assert errors(walk)
    assert errors({**walk, "depends_on": [], "timing": "parallel"})


@pytest.mark.parametrize("relation", ["before", "precedes", "after", "follows", "parallel_with"])
@pytest.mark.parametrize("list_binding", [False, True])
def test_typed_source_relation_is_checked_on_work_dependencies(relation, list_binding):
    from agent.app.planner_fast_validation import (
        FastAdvanceMechanicalSchedulingError, validate_fast_advance_output,
    )
    from shared.chromie_contracts.plan import FastPlannerAdvanceModelOutput

    responsibilities = [CognitiveResponsibilityProposal(
        local_ref=ref, outcome="walk forward for ten seconds", output_mode="body_action", confidence=1,
        bindings={"duration_s": 10, **({relation: ["second"] if list_binding else "second"} if ref == "first" else {})},
    ) for ref in ("first", "second")]
    request = CognitiveWorkRequest(sid="typed-relation", text="walk forward for ten seconds", language="en-US",
        responsibilities=responsibilities, interpretation_confidence=1, context={})
    capability = {**_walk_capability(), "can_run_parallel": True, "parallel_metadata_declared": True}

    def validate(order, dependent):
        activities = []
        for index, ref in enumerate(order):
            activities.append({"role": "capability", "activity_id": ref, "capability_id": capability["capability_id"],
                "args": {"duration_s": 10}, "source_responsibility_refs": [ref],
                "depends_on": [order[0]] if dependent and index == 1 else []})
        output = FastPlannerAdvanceModelOutput.model_validate({"disposition": "execute", "coverage": "complete",
            "covered_responsibility_refs": ["first", "second"], "activities": activities, "continuations": [],
            "confidence": 1, "unresolved": [], "reason_summary": "Typed relation."})
        validate_fast_advance_output(output, request=request, responsibilities=responsibilities, capabilities=[capability])

    order = ("second", "first") if relation in {"after", "follows"} else ("first", "second")
    ordered = relation != "parallel_with"
    validate(order, dependent=ordered)  # the relation as dependencies (or their absence)
    with pytest.raises(FastAdvanceMechanicalSchedulingError, match="typed Responsibility"):
        validate(order, dependent=not ordered)


def test_native_work_timing_keeps_escalation_when_no_provider_can_honor_concurrency():
    responsibilities = [CognitiveResponsibilityProposal(
        local_ref=ref, outcome="perform bounded action", output_mode="body_action", confidence=1,
        bindings={"parallel_with": "second"} if ref == "first" else {},
    ) for ref in ("first", "second")]
    capability = {**_walk_capability(), "can_run_parallel": False}
    schema = fast_streaming_advance_response_schema(
        [item.local_ref for item in responsibilities], responsibilities=responsibilities, capabilities=[capability])
    for timing in ("parallel", "sequential"):
        act = {"role": "capability", "activity_id": "one", "capability_id": capability["capability_id"],
               "args": {"duration_s": 10}, "timing": timing, "source_responsibility_refs": ["first"]}
        assert list(Draft202012Validator(schema["properties"]["activities"]["items"]).iter_errors(act))
    escalation = {"activities": [], "disposition": "escalate", "coverage": "uncertain",
        "covered_responsibility_refs": ["first", "second"], "confidence": 1,
        "continuations": ["deep_planner"],
        "unresolved": ["Concurrent composition unavailable."], "reason_summary": "Requires deeper source-based planning."}
    Draft202012Validator(schema).validate(escalation)


@pytest.mark.parametrize("count", [1, 2, 3, 6])
def test_fast_native_visible_work_bounds_conserve_all_existing_response_assignments(count):
    from agent.app.planner_schema import fast_multi_goal_response_schema
    ids = [f"goal-{i}" for i in range(count)]
    schema = fast_multi_goal_response_schema(
        expected_goal_ids=ids, allowed_capability_ids=["test.action"],
        capability_input_schemas={"test.action": {"type": "object", "properties": {}}},
        response_only=False, response_goal_ids=ids)
    fields = schema["properties"]
    assert fields["steps"]["maxItems"] == 0
    assert "execute" not in fields["disposition"]["enum"]
    for goal in ids:
        outcome = fields["goal_outcomes"]["properties"][goal]["properties"]
        assert "execute" not in outcome["disposition"]["enum"]
        assert outcome["step_ids"]["maxItems"] == 0
    # An independent effect Goal keeps execution representable in the same DTO.
    mixed = fast_multi_goal_response_schema(
        expected_goal_ids=[*ids, "effect"][:6], allowed_capability_ids=["test.action"],
        capability_input_schemas={"test.action": {"type": "object", "properties": {}}},
        response_goal_ids=ids[:5], effectful_goal_ids=["effect"] if count < 6 else [])
    if count < 6:
        assert mixed["properties"]["steps"]["maxItems"] >= 1
        assert "execute" in mixed["properties"]["goal_outcomes"]["properties"]["effect"]["properties"]["disposition"]["enum"]


@pytest.mark.parametrize("mode", ["styled_speech", "recitation", "singing", "humming", "nonverbal_vocalization"])
@pytest.mark.parametrize("provider_modes", [None, ["speech"], ["speech", "styled_speech", "recitation", "singing", "humming", "nonverbal_vocalization"]])
def test_native_advance_preserves_vocal_source_mode_without_redirecting_body_work(mode, provider_modes):
    from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID, vocal_performance_input_schema
    responsibilities = [
        CognitiveResponsibilityProposal(local_ref="voice", outcome="perform requested vocal effect", output_mode=mode, confidence=1),
        CognitiveResponsibilityProposal(local_ref="body", outcome="walk for 10 seconds", output_mode="body_action", confidence=1),
    ]
    capabilities = [_walk_capability()]
    if provider_modes is not None:
        capabilities.append({"capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
            "input_schema": vocal_performance_input_schema(provider_modes), "can_run_parallel": True})
    schema = fast_streaming_advance_response_schema(
        [x.local_ref for x in responsibilities], responsibilities=responsibilities, capabilities=capabilities)
    validator = Draft202012Validator(schema["properties"]["activities"]["items"])
    body = {"role": "capability", "activity_id": "act", "capability_id": capabilities[0]["capability_id"],
        "args": {"duration_s": 10}, "argument_sources": {"duration_s": {"source_start_token_ref": "t0", "source_end_token_ref": "t1"}},
        "depends_on": [], "source_responsibility_refs": ["body"]}
    validator.validate(body)
    assert not validator.is_valid({**body, "source_responsibility_refs": ["voice"]})
    for candidate_mode in ["speech", "styled_speech", "recitation", "singing", "humming", "nonverbal_vocalization"]:
        vocal = {**body, "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
            "argument_sources": {},
            "args": {"text": "authored performance", "mode": candidate_mode}, "source_responsibility_refs": ["voice"]}
        assert validator.is_valid(vocal) == (provider_modes is not None and mode in provider_modes and candidate_mode == mode)
    # An unavailable mode can still delegate its unresolved work without inventing another effect.
    Draft202012Validator(schema).validate({"activities": [], "disposition": "escalate", "coverage": "uncertain",
        "covered_responsibility_refs": ["voice", "body"], "confidence": 0.5, "continuations": ["deep_planner"],
        "unresolved": ["Requested composition needs deeper planning."], "reason_summary": "Unresolved composition."})


def test_native_advance_keeps_distinct_and_shared_vocal_mode_composition():
    from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID, vocal_performance_input_schema
    responsibilities = [CognitiveResponsibilityProposal(local_ref=ref, outcome="requested vocal performance", output_mode=mode, confidence=1)
        for ref, mode in [("song1", "singing"), ("song2", "singing"), ("hum", "humming")]]
    schema = fast_streaming_advance_response_schema([x.local_ref for x in responsibilities], responsibilities=responsibilities,
        capabilities=[{"capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID, "input_schema": vocal_performance_input_schema(), "can_run_parallel": True}])
    validator = Draft202012Validator(schema["properties"]["activities"]["items"])
    act = {"role": "capability", "activity_id": "voice", "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
        "args": {"text": "authored performance", "mode": "singing"}, "depends_on": [], "source_responsibility_refs": ["song1", "song2"]}
    validator.validate(act)
    assert not validator.is_valid({**act, "source_responsibility_refs": ["song1", "hum"]})
    validator.validate({**act, "args": {**act["args"], "mode": "humming"}, "source_responsibility_refs": ["hum"]})


def test_native_vocal_work_with_empty_catalog_cannot_invent_a_provider():
    source = CognitiveResponsibilityProposal(local_ref="song", outcome="sing", output_mode="singing", confidence=1)
    schema = fast_streaming_advance_response_schema([source.local_ref], responsibilities=[source], capabilities=[])
    act = {"role": "capability", "activity_id": "voice", "capability_id": "unavailable.provider",
        "args": {"mode": "singing", "text": "performance"}, "depends_on": [], "source_responsibility_refs": ["song"]}
    assert not Draft202012Validator(schema["properties"]["activities"]["items"]).is_valid(act)
    Draft202012Validator(schema).validate({"activities": [], "disposition": "escalate", "coverage": "uncertain",
        "covered_responsibility_refs": ["song"], "confidence": 0.5, "continuations": ["deep_planner"],
        "unresolved": ["No qualified vocal provider."], "reason_summary": "Need source-based deeper planning."})


@pytest.mark.parametrize("disposition,coverage,continuations,work,valid", [
    ("execute", "complete", [], True, True),
    ("execute", "partial", ["deep_planner"], True, False),
    ("execute", "complete", ["deep_planner"], True, False),
    ("execute", "partial", [], True, False),
    ("mixed", "partial", [], True, False),
    ("escalate", "uncertain", ["deep_planner"], False, True),
    ("escalate", "partial", ["deep_planner"], True, False),
    ("escalate", "uncertain", [], False, False),
    ("escalate", "complete", ["deep_planner"], False, False),
])
def test_native_decision_alternatives_preserve_execution_delegation_boundary(disposition, coverage, continuations, work, valid):
    request, source = _body_request()
    capability = _walk_capability()
    schema = fast_streaming_advance_response_schema([source.local_ref], responsibilities=[source], capabilities=[capability])
    output = {"disposition": disposition, "coverage": coverage, "covered_responsibility_refs": [source.local_ref],
        "activities": [{"role": "capability", "activity_id": "walk", "capability_id": capability["capability_id"],
            "args": {"duration_s": 10}, "depends_on": [], "source_responsibility_refs": [source.local_ref]}] if work else [],
        "continuations": continuations, "confidence": 1, "unresolved": [], "reason_summary": "Bounded Work decision."}
    # Exercise the native alternatives independently of the Host's conditional
    # allOf checks, which the deployed decoder does not enforce.
    assert Draft202012Validator({"oneOf": schema["oneOf"]}).is_valid(output) == valid
    assert Draft202012Validator(schema).is_valid(output) == valid


def test_planner_authority_forbids_confirmation_only_complete_response_for_work() -> None:
    system = fast_streaming_advance_system_prompt()
    assert "Do not create respond or a complete_response merely to acknowledge" in system
    request = CognitiveWorkRequest(
        sid="turn-physical-compound",
        text="walk, nod, then turn left",
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref="r1",
                outcome="walk, nod, then turn left",
                output_mode="body_action",
                confidence=1.0,
            )
        ],
        interpretation_confidence=1.0,
    )
    prompt = fast_advance_layered_prompt(
        request, responsibilities=request.responsibilities, capabilities=[]
    ).render()
    assert "Never add complete_response just to acknowledge" in prompt


@pytest.mark.parametrize("resource_contract,location", [
    ({}, "hints"),
    ({"provider_role": "acquire_information"}, "hints"),
    ({"provider_role": "acquire_information"}, "metadata"),
    ({"plan_provides": ["resource_acquired"], "final_delivery_owner": "planner_communicative_activity"}, "hints"),
    ({"plan_provides": ["resource_acquired", "resource_delivered"]}, "hints"),
])
@pytest.mark.parametrize("purpose", [None, "achieve_effect", "acquire_information"])
def test_fast_decoder_purpose_matches_provider_normalization(resource_contract, location, purpose):
    from agent.app.planner_fast_validation import normalize_fast_capability_activity_purpose

    definition = {"capability_id": "test.provider", "input_schema": {"type": "object", "properties": {}},
                  location: {"resource_contract": resource_contract}}
    responsibility = CognitiveResponsibilityProposal(local_ref="r1", outcome="Complete the requested work",
                                                       output_mode="body_action", confidence=1.0)
    raw = {"activities": [{"role": "capability", "capability_id": "test.provider", "activity_id": "step",
                           "args": {}, "source_responsibility_refs": ["r1"], "depends_on": []}],
           "disposition": "execute", "coverage": "complete", "covered_responsibility_refs": ["r1"],
           "continuations": [], "confidence": 1.0, "unresolved": [], "reason_summary": "Realize the owned effect."}
    if purpose is not None:
        raw["activities"][0]["step_purpose"] = purpose
    output = FastPlannerAdvanceModelOutput.model_validate(raw)
    try:
        normalize_fast_capability_activity_purpose(output, capabilities=[definition])
        expected = True
    except PlannerDTOContractError:
        expected = False
    schema = fast_streaming_advance_response_schema(["r1"], responsibilities=[responsibility], capabilities=[definition])
    assert Draft202012Validator(schema).is_valid(raw) == expected


@pytest.mark.parametrize("start,end", [(0, 0), (0, 10), (9, 10), (10, 10), (10, 9), (10, 0), (0, 11)])
def test_fast_decoder_source_span_matches_immutable_token_order(start, end):
    from shared.chromie_contracts.user_turn import user_turn_source_span_schema
    from shared.chromie_contracts.user_turn import UserTurnSourceSpan, resolve_user_turn_source_span, user_turn_source_tokens

    source = "walk ahead slowly then stop and look at the blue door"
    tokens = user_turn_source_tokens(source)
    span = UserTurnSourceSpan(source_start_token_ref=f"t{start}", source_end_token_ref=f"t{end}")
    try:
        resolve_user_turn_source_span(source, span)
        expected = True
    except ValueError:
        expected = False
    contract = user_turn_source_span_schema([token["ref"] for token in tokens])
    assert Draft202012Validator(contract).is_valid(span.model_dump()) == expected


def _compound_body_case(variant: str) -> tuple[CognitiveWorkRequest, list[CatalogCapability], dict[str, Any], bool]:
    """Requested compound effects and independent mechanical rejection contrasts."""
    from shared.chromie_contracts.user_turn import user_turn_source_tokens

    def capability(capability_id, description, properties, domains, effects):
        return CatalogCapability(
            capability_id=capability_id, agent_id='capability_agent', description=description,
            input_schema={'type': 'object', 'properties': properties, 'additionalProperties': False},
            effects=effects, behavior_domains=domains, available=True, interaction_executable=True,
            prompt_tier='common', can_run_parallel=True, parallel_metadata_declared=True,
            exclusive_group='body.primary_motion', resource_claims=['body.primary_motion'],
        )

    caps = [
        capability('soridormi.walk_velocity', 'Walk at requested speed for requested duration',
                   {'duration_s': {'type': 'number', 'minimum': .1, 'default': 1},
                    'vx_mps': {'type': 'number', 'default': .15}}, ['locomotion'], ['physical_motion']),
        capability('soridormi.walk_forward', 'Walk forward',
                   {'duration_s': {'type': 'number', 'minimum': .1, 'default': 1}}, ['locomotion'], ['physical_motion']),
        capability('soridormi.nod_yes', 'Nod the head',
                   {'count': {'type': 'integer', 'minimum': 1, 'maximum': 8, 'default': 2}},
                   ['social_attention'], ['physical_motion']),
        capability('soridormi.blink_eyes', 'Blink the eyes',
                   {'count': {'type': 'integer', 'minimum': 1, 'maximum': 8, 'default': 2}},
                   ['social_attention', 'facial_expression'], ['visual_expression']),
        capability('soridormi.turn_in_place', 'Turn in place',
                   {'direction': {'type': 'string', 'enum': ['left', 'right'], 'default': 'left'}},
                   ['locomotion'], ['physical_motion']),
        capability('soridormi.look_direction', 'Look in the requested direction',
                   {'direction': {'type': 'string', 'enum': ['front', 'left', 'right'], 'default': 'front'}},
                   ['orientation', 'social_attention'], ['physical_motion']),
    ]
    text = 'Walk forward one second, then blink twice.'
    family = 'task_physical_effect'
    mode = 'body_action'
    specs = [('walk', 'soridormi.walk_forward', {'duration_s': 1}, {'duration_s': 'one'}),
             ('blink', 'soridormi.blink_eyes', {'count': 2}, {'count': 'twice'})]
    expected = variant in {'walk_nod_turn', 'walk_blink', 'look_walk', 'nod_only'}
    if variant in {'walk_nod_turn', 'unavailable_nod'}:
        text = 'walk ahead at 0.2 speed for 10 seconds then nod head twice then turn left'
        specs = [('walk', 'soridormi.walk_velocity', {'vx_mps': .2, 'duration_s': 10},
                  {'vx_mps': '0.2', 'duration_s': '10'}),
                 ('nod', 'soridormi.nod_yes', {'count': 2}, {'count': 'twice'}),
                 ('turn', 'soridormi.turn_in_place', {'direction': 'left'}, {'direction': 'left'})]
    elif variant == 'look_walk':
        text = 'look front then walk forward'; family = 'gaze_or_orientation'
        specs = [('look', 'soridormi.look_direction', {'direction': 'front'}, {'direction': 'front'}),
                 ('walk', 'soridormi.walk_forward', {}, {})]
    elif variant == 'nod_only':
        text = 'nod twice'; family = 'social_expression'
        specs = [('nod', 'soridormi.nod_yes', {'count': 2}, {'count': 'twice'})]
    elif variant in {'speech_gesture', 'information_gesture'}:
        mode = 'speech' if variant == 'speech_gesture' else 'information'
        text = 'answer who you are' if mode == 'speech' else 'report the current time'
        specs = [('nod', 'soridormi.nod_yes', {}, {})]
    elif variant == 'foreign_span':
        text = 'walk forward then nod twice'
        specs = [('walk', 'soridormi.walk_forward', {}, {}),
                 ('nod', 'soridormi.nod_yes', {'count': 2}, {'count': 'twice'})]
    tokens = user_turn_source_tokens(text)

    def span(surface):
        start = text.index(surface); end = start + len(surface)
        contained = [t for t in tokens if t['start'] >= start and t['end'] <= end]
        return {'source_start_token_ref': contained[0]['ref'], 'source_end_token_ref': contained[-1]['ref']}

    responsibility = CognitiveResponsibilityProposal(
        local_ref='r1', outcome=text, output_mode=mode,
        body_effect_family=family if mode == 'body_action' else None,
        source_evidence={'source_start_token_ref': tokens[0]['ref'], 'source_end_token_ref': tokens[-1]['ref']},
        confidence=1.0,
    )
    responsibilities = [responsibility]
    if variant == 'foreign_span':
        responsibility = CognitiveResponsibilityProposal.model_validate({
            **responsibility.model_dump(), 'outcome': 'walk forward',
            'source_evidence': span('walk forward'),
        })
        responsibilities = [responsibility]
        responsibilities.append(CognitiveResponsibilityProposal(
            local_ref='r2', outcome='nod twice', output_mode='body_action', body_effect_family='social_expression',
            source_evidence=span('nod twice'), confidence=1,
        ))
    request = CognitiveWorkRequest(sid='compound-body-contrast', text=text, language='en-US',
        responsibilities=responsibilities, interpretation_confidence=1)
    raw = {'disposition': 'execute', 'coverage': 'complete',
        'covered_responsibility_refs': [r.local_ref for r in responsibilities],
        'activities': [{'role': 'capability', 'activity_id': aid, 'capability_id': cid,
                        'args': args, 'argument_sources': {k: span(v) for k, v in sources.items()},
                        'source_responsibility_refs': ['r1'], 'depends_on': [],
                        'reason_summary': 'Realize the effect in the accepted source responsibility.'}
                       for aid, cid, args, sources in specs],
        'continuations': [], 'confidence': 1, 'unresolved': [], 'reason_summary': 'Complete requested work.'}
    if variant == 'unknown_ref':
        raw['activities'][1]['source_responsibility_refs'] = ['unknown']
    elif variant == 'parallel_resource_conflict':
        for item in raw['activities']: item['timing'] = 'parallel'
    elif variant == 'unavailable_nod':
        caps = [c.model_copy(update={'available': False}) if c.capability_id == 'soridormi.nod_yes' else c for c in caps]
    elif variant == 'auxiliary_field':
        raw['auxiliary_activities'] = [{'capability_id': 'soridormi.nod_yes', 'execution_role': 'social_decoration'}]
    elif variant == 'invalid_count':
        raw['activities'][1]['args']['count'] = 0
    return request, caps, raw, expected


@pytest.mark.asyncio
@pytest.mark.parametrize('variant', [
    'walk_nod_turn', 'walk_blink', 'look_walk', 'nod_only', 'speech_gesture', 'information_gesture',
    'unknown_ref', 'foreign_span', 'parallel_resource_conflict', 'unavailable_nod', 'auxiliary_field', 'invalid_count',
])
async def test_compound_body_work_keeps_one_responsibility_and_mechanical_guards(variant):
    request, caps, raw, expected = _compound_body_case(variant)
    model = _StreamingModel([_wire_output(raw)])
    frames = [f async for f in FastPlannerResolver(model, _Catalog(caps)).stream_advance(request)]
    assert model.calls == 1
    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamTerminal) is expected, frames[0]
    if expected:
        activities = frames[0].advance.activities
        assert [a.capability_id for a in activities] == [a['capability_id'] for a in raw['activities']]
        assert [a.args for a in activities] == [a['args'] for a in raw['activities']]
        assert all(a.source_responsibility_refs == ['r1'] for a in activities)
    else:
        assert isinstance(frames[0], FastPlannerStreamFailure)
        assert frames[0].failure_stage == 'before_commit'


def _compound_count_case(variant: str):
    request, caps, raw, _ = _compound_body_case('walk_nod_turn')
    request = request.model_copy(update={'responsibilities': [request.responsibilities[0].model_copy(update={'bindings': {'count': 2}})]})
    raw['activities'][1]['argument_sources'] = {}
    raw['activities'][2]['args']['count'] = 1
    caps[4] = caps[4].model_copy(update={'input_schema': {'type': 'object', 'properties': {
        **caps[4].input_schema['properties'], 'count': {'type': 'integer', 'minimum': 1, 'maximum': 8, 'default': 1}},
        'additionalProperties': False}})
    expected = variant in {'compound_defaults', 'omitted_turn_default', 'matching_turn_count', 'distinct_explicit_count'}
    if variant in {'matching_turn_count', 'distinct_explicit_count'}:
        from shared.chromie_contracts.user_turn import user_turn_source_tokens
        text = request.text + (' twice' if variant == 'matching_turn_count' else ' 3 times')
        tokens = user_turn_source_tokens(text)
        source = type(request.responsibilities[0]).model_validate({
            **request.responsibilities[0].model_dump(), 'outcome': text,
            'source_evidence': {'source_start_token_ref': tokens[0]['ref'], 'source_end_token_ref': tokens[-1]['ref']}})
        request = request.model_copy(update={'text': text, 'responsibilities': [source]})
    if variant == 'omitted_turn_default':
        raw['activities'][2]['args'].pop('count')
    elif variant == 'matching_turn_count':
        raw['activities'][2]['args']['count'] = 2
    elif variant == 'distinct_explicit_count':
        raw['activities'][2]['args']['count'] = 3
        count_token = next(t['ref'] for t in tokens if t['surface'] == '3')
        raw['activities'][2]['argument_sources']['count'] = {'source_start_token_ref': count_token, 'source_end_token_ref': count_token}
    elif variant == 'missing_count':
        raw['activities'][1]['args'].pop('count')
    elif variant == 'wrong_nod_count':
        raw['activities'][1]['args']['count'] = 3
    elif variant == 'nondefault_turn_count':
        raw['activities'][2]['args']['count'] = 3
    elif variant == 'duration_masks_count':
        raw['activities'] = [raw['activities'][0]]
        raw['activities'][0]['args'] = {'duration_s': 2}
        raw['activities'][0]['argument_sources'] = {}
    elif variant == 'single_wrong_count':
        raw['activities'] = [raw['activities'][1]]
        raw['activities'][0]['args']['count'] = 1
    elif variant == 'foreign_argument_source':
        raw['activities'][0]['argument_sources']['duration_s']['source_end_token_ref'] = 't999'
    return request, caps, raw, expected


@pytest.mark.asyncio
@pytest.mark.parametrize('variant', ['compound_defaults', 'omitted_turn_default', 'matching_turn_count', 'distinct_explicit_count',
    'missing_count', 'wrong_nod_count', 'nondefault_turn_count', 'duration_masks_count',
    'single_wrong_count', 'foreign_argument_source'])
async def test_compound_count_stays_in_declared_parameters(variant):
    request, caps, raw, expected = _compound_count_case(variant)
    model = _StreamingModel([_wire_output(raw)])
    frames = [f async for f in FastPlannerResolver(model, _Catalog(caps)).stream_advance(request)]
    assert model.calls == 1
    assert isinstance(frames[-1], FastPlannerStreamTerminal) == expected
    if expected:
        assert [a.capability_id for a in frames[-1].advance.activities] == [a['capability_id'] for a in raw['activities']]
    else:
        assert frames[-1].failure_stage == 'before_commit'


@pytest.mark.asyncio
@pytest.mark.parametrize('variant', ['translated_missing', 'translated_cited', 'literal', 'case_only',
    'selected_value_missing', 'selected_literal', 'bound_value', 'foreign_source', 'invalid_enum'])
async def test_required_enum_source_matches_selected_value_and_original_turn(variant):
    from shared.chromie_contracts.user_turn import user_turn_source_tokens

    text, outcome, value = '向右转。', 'turn right', 'right'
    cited, bindings, owned = None, {}, None
    expected = variant in {'translated_cited', 'literal', 'case_only', 'selected_literal', 'bound_value'}
    if variant == 'translated_cited':
        cited = '右'
    elif variant == 'literal':
        text = outcome = 'turn right'
    elif variant == 'case_only':
        text = 'Turn Right'
    elif variant in {'selected_value_missing', 'selected_literal'}:
        text, outcome = 'right was the old direction; now turn left', 'turn left'
        value = 'left' if variant == 'selected_literal' else 'right'
    elif variant == 'bound_value':
        bindings = {'direction': 'right'}
    elif variant == 'foreign_source':
        text, outcome, owned, cited = '向左转。另一个要求向右转。', 'turn left', '向左转。', '右'
    elif variant == 'invalid_enum':
        text = outcome = 'turn up'
        value = 'up'
    tokens = user_turn_source_tokens(text)

    def span(surface):
        start = text.index(surface)
        found = [t for t in tokens if start <= t['start'] and t['end'] <= start + len(surface)]
        return {'source_start_token_ref': found[0]['ref'], 'source_end_token_ref': found[-1]['ref']}

    responsibility = CognitiveResponsibilityProposal(local_ref='r1', outcome=outcome,
        output_mode='body_action', body_effect_family='task_physical_effect', confidence=1,
        source_evidence=span(owned or text), bindings=bindings)
    request = CognitiveWorkRequest(sid='enum-source-contract', text=text, responsibilities=[responsibility],
        interpretation_confidence=1)
    capability = CatalogCapability(capability_id='soridormi.turn_in_place', agent_id='capability_agent',
        description='Turn in place', input_schema={'type': 'object',
            'properties': {'direction': {'type': 'string', 'enum': ['left', 'right']}},
            'required': ['direction'], 'additionalProperties': False}, behavior_domains=['locomotion'],
        effects=['physical_motion'], available=True, interaction_executable=True, prompt_tier='common')
    raw = {'activities': [{'role': 'capability', 'activity_id': 'turn',
        'capability_id': capability.capability_id, 'args': {'direction': value},
        'argument_sources': {'direction': span(cited)} if cited else {},
        'source_responsibility_refs': ['r1'], 'depends_on': []}],
        'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['r1'],
        'continuations': [], 'confidence': 1, 'unresolved': [], 'reason_summary': 'Realize owned turn.'}
    model = _StreamingModel([_wire_output(raw)])
    frames = [f async for f in FastPlannerResolver(model, _Catalog([capability])).stream_advance(request)]
    assert model.calls == 1
    assert Draft202012Validator(model.last_kwargs['response_format']).is_valid(raw) == (
        expected or variant == 'foreign_source')
    assert isinstance(frames[-1], FastPlannerStreamTerminal) == expected
    if not expected:
        assert frames[-1].failure_stage == 'before_commit'
