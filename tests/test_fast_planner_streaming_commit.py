from __future__ import annotations
import json
from typing import Any
import pytest
from jsonschema import Draft202012Validator
from agent.app.capabilities.catalog import CatalogCapability
from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_model_contract import PlannerDTOContractError
from agent.app.planner_fast_validation import AuthoritativeGroundingValidationError, validate_fast_advance_output
from agent.app.planner_prompt import fast_advance_capability_prompt_projection, fast_advance_layered_prompt, fast_advance_semantic_capability_projection, fast_advance_streaming_capability_prompt_projection, fast_responsibility_decision_projection, fast_streaming_advance_system_prompt
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
    output = {'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['r1'], 'activities': [{'role': 'capability', 'capability_id': 'soridormi.shake_no', 'activity_id': 'act_shake_head_twice', 'args': {'count': 2}, 'timing': 'sequential', 'source_responsibility_refs': ['r1']}], 'continuations': [], 'confidence': 1.0, 'unresolved': [], 'reason_summary': 'Execute head shake twice as requested'}
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
    raw = {'disposition': 'mixed', 'coverage': 'complete', 'covered_responsibility_refs': ['r1', 'r2'], 'activities': [{'activity_id': 'ask-meaning', 'role': 'clarification', 'source_responsibility_refs': ['r1'], 'information_gaps': gaps}, {'activity_id': 'nod', 'role': 'capability', 'capability_id': 'soridormi.nod_yes', 'args': {'count': 2}, 'timing': 'sequential', 'source_responsibility_refs': ['r2'] if independent else ['r1', 'r2']}], 'continuations': [], 'confidence': 0.9, 'unresolved': [item.description for item in request.meaning_uncertainties], 'reason_summary': 'Clarify the first request; perform the independent nod.'}
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
        "args": {"direction": direction}, "argument_sources": sources, "timing": "sequential",
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
            "timing": "sequential",
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
    return CatalogCapability(capability_id='soridormi.blink_eyes', agent_id='capability_agent', description='Blink as an optional visual social expression.', input_schema={'type': 'object', 'properties': {'count': {'type': 'integer', 'minimum': 1, 'default': 2}}, 'additionalProperties': False}, effects=['visual_expression'], available=True, interaction_executable=True, prompt_tier='common', behavior_domains=['social_attention'], can_run_parallel=True, parallel_metadata_declared=True, exclusive_group='visual.eyes', resource_claims=['visual.eyes'])

def _look_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(sid='turn-stream-look', text='看着我三秒', language='zh-CN', responsibilities=[CognitiveResponsibilityProposal(local_ref='look', outcome='look at the addressee', output_mode='body_action', bindings={'addressee': '我'}, confidence=1.0)], interpretation_confidence=1.0, context={'active_user_target': {'source': 'live_perception', 'target_ref': 'current_speaker', 'relative_direction': 'front', 'confidence': 1.0, 'evidence_refs': ['scenario:current-speaker']}})

def _look_output(*, target_ref: str) -> dict[str, Any]:
    return {'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['look'], 'activities': [{'role': 'capability', 'capability_id': 'soridormi.look_at_person', 'activity_id': 'look-at-speaker', 'args': {'target_ref': target_ref}, 'timing': 'sequential', 'source_responsibility_refs': ['look']}], 'continuations': [], 'confidence': 1.0, 'unresolved': [], 'reason_summary': 'Look at the trusted current speaker target.'}

def _structured_resource_catalog_capability() -> CatalogCapability:
    realization = {'physical_resource_entity': {'source_entity_type': 'entity', 'planner_owned': True, 'arguments': ['resource'], 'minimum_arguments': 1, 'contract': 'Conserve the exact entity inside resource.'}, 'physical_resource_location': {'source_entity_type': 'location', 'planner_owned': True, 'arguments': ['source'], 'minimum_arguments': 1, 'contract': 'Conserve the exact location inside source.'}, 'physical_resource_distance': {'source_entity_type': 'distance', 'planner_owned': True, 'arguments': ['source'], 'minimum_arguments': 1, 'contract': 'Conserve the exact distance inside source.'}, 'physical_resource_recipient': {'source_entity_type': 'recipient', 'planner_owned': True, 'arguments': ['recipient'], 'minimum_arguments': 1, 'contract': 'Conserve the exact recipient inside recipient.'}}
    return CatalogCapability(capability_id='soridormi.acquire_and_deliver_resource', agent_id='capability_agent', description='Acquire and deliver a physical resource.', input_schema={'type': 'object', 'properties': {'resource': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['physical_object']}, 'description': {'type': 'string', 'minLength': 1}}, 'required': ['kind', 'description'], 'additionalProperties': False}, 'source': {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['known']}, 'description': {'type': 'string'}, 'bindings': {'type': 'object'}}, 'required': ['status'], 'additionalProperties': False}, 'recipient': {'type': 'object', 'properties': {'description': {'type': 'string', 'minLength': 1}}, 'required': ['description'], 'additionalProperties': False}}, 'required': ['resource', 'source', 'recipient'], 'additionalProperties': False}, effects=['physical_motion', 'resource_delivery'], available=True, interaction_executable=True, prompt_tier='common', hints={'semantic_scope': {'responsibility_type': 'acquire_and_deliver_resource', 'resource_kinds': ['physical_object']}, 'argument_realization': realization})

def _structured_resource_request() -> CognitiveWorkRequest:
    return CognitiveWorkRequest(sid='turn-stream-resource', text='there is a bottle of milk ahead of you about 50 meters, please bring it to me', language='en-US', responsibilities=[CognitiveResponsibilityProposal(local_ref='fetch', outcome='acquire and deliver the resource', output_mode='body_action', bindings={'entity': 'bottle of milk', 'location': 'ahead of you about 50 meters', 'distance': 50, 'recipient': 'me'}, confidence=1.0)], interpretation_confidence=1.0)

def _structured_resource_output(*, recipient: str='me') -> dict[str, Any]:
    return {'disposition': 'execute', 'coverage': 'complete', 'covered_responsibility_refs': ['fetch'], 'activities': [{'role': 'capability', 'capability_id': 'soridormi.acquire_and_deliver_resource', 'activity_id': 'fetch-milk', 'args': {'resource': {'kind': 'physical_object', 'description': 'bottle of milk'}, 'source': {'status': 'known', 'description': 'ahead of you about 50 meters', 'bindings': {'distance': 50}}, 'recipient': {'description': recipient}}, 'timing': 'sequential', 'source_responsibility_refs': ['fetch']}], 'continuations': [], 'confidence': 1.0, 'unresolved': [], 'reason_summary': 'Acquire the resource and deliver it.'}

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
def test_native_work_schema_conserves_declared_parallel_permission(parallel):
    request, responsibility = _body_request()
    capability = {**_walk_capability(), "can_run_parallel": parallel}
    schema = fast_streaming_advance_response_schema([responsibility.local_ref], responsibilities=[responsibility], capabilities=[capability])
    output = {"disposition": "execute", "coverage": "complete", "covered_responsibility_refs": ["walk"],
        "activities": [{"role": "capability", "activity_id": "walk", "capability_id": capability["capability_id"],
            "args": {"duration_s": 10}, "timing": "parallel", "source_responsibility_refs": ["walk"]}],
        "continuations": [], "confidence": 1, "unresolved": [], "reason_summary": "Direct walk."}
    errors = list(Draft202012Validator(schema).iter_errors(output))
    assert bool(errors) is not parallel


@pytest.mark.parametrize("relation", ["before", "precedes", "after", "follows", "parallel_with"])
@pytest.mark.parametrize("list_binding", [False, True])
def test_native_work_timing_preserves_both_ends_of_typed_source_relation(relation, list_binding):
    responsibilities = [CognitiveResponsibilityProposal(
        local_ref=ref, outcome="perform bounded action for 10 seconds", output_mode="body_action", confidence=1,
        bindings={relation: ["second"] if list_binding else "second"} if ref == "first" else {},
    ) for ref in ("first", "second", "independent")]
    capability = {**_walk_capability(), "can_run_parallel": True}
    schema = fast_streaming_advance_response_schema(
        [item.local_ref for item in responsibilities], responsibilities=responsibilities, capabilities=[capability])
    expected = "parallel" if relation == "parallel_with" else "sequential"
    for ref in ("first", "second", "independent"):
        for timing in ("sequential", "parallel"):
            act = {"role": "capability", "activity_id": ref, "capability_id": capability["capability_id"],
                   "args": {"duration_s": 10}, "argument_sources": {"duration_s": {"source_start_token_ref": "t0", "source_end_token_ref": "t1"}},
                   "timing": timing, "source_responsibility_refs": [ref]}
            # Exercise the exact compiled item union, including native branches.
            errors = list(Draft202012Validator(schema["properties"]["activities"]["items"]).iter_errors(act))
            assert bool(errors) == (ref != "independent" and timing != expected)


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
        "timing": "sequential", "source_responsibility_refs": ["body"]}
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
        "args": {"text": "authored performance", "mode": "singing"}, "timing": "parallel", "source_responsibility_refs": ["song1", "song2"]}
    validator.validate(act)
    assert not validator.is_valid({**act, "source_responsibility_refs": ["song1", "hum"]})
    validator.validate({**act, "args": {**act["args"], "mode": "humming"}, "source_responsibility_refs": ["hum"]})


def test_native_vocal_work_with_empty_catalog_cannot_invent_a_provider():
    source = CognitiveResponsibilityProposal(local_ref="song", outcome="sing", output_mode="singing", confidence=1)
    schema = fast_streaming_advance_response_schema([source.local_ref], responsibilities=[source], capabilities=[])
    act = {"role": "capability", "activity_id": "voice", "capability_id": "unavailable.provider",
        "args": {"mode": "singing", "text": "performance"}, "timing": "sequential", "source_responsibility_refs": ["song"]}
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
            "args": {"duration_s": 10}, "timing": "sequential", "source_responsibility_refs": [source.local_ref]}] if work else [],
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
                           "args": {}, "source_responsibility_refs": ["r1"], "timing": "sequential"}],
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
