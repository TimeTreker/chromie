from __future__ import annotations

from agent.app.planner_fast_validation import _drop_redundant_unbound_schema_default
from agent.app.planner_prompt import (
    EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
    fast_advance_streaming_capability_prompt_projection,
)


def test_exact_unbound_optional_schema_default_is_removed_from_model_authored_args() -> None:
    args = {
        "direction": "left",
        "turn_rate_radps": 0.12,
        "duration_s": 2.0,
        "count": 1,
    }

    for parameter, schema in (
        ("turn_rate_radps", {"type": "number", "default": 0.12}),
        ("duration_s", {"type": "number", "default": 2.0}),
        ("count", {"type": "integer", "default": 1}),
    ):
        assert _drop_redundant_unbound_schema_default(
            args,
            parameter=parameter,
            parameter_schema=schema,
            required_inputs={"direction"},
        )

    assert args == {"direction": "left"}


def test_nondefault_unbound_optional_value_remains_for_fail_closed_rejection() -> None:
    args = {"direction": "left", "turn_rate_radps": 0.01}

    assert not _drop_redundant_unbound_schema_default(
        args,
        parameter="turn_rate_radps",
        parameter_schema={"type": "number", "default": 0.12},
        required_inputs={"direction"},
    )
    assert args == {"direction": "left", "turn_rate_radps": 0.01}


def test_required_input_is_never_removed_even_when_schema_has_a_default() -> None:
    args = {"direction": "left"}

    assert not _drop_redundant_unbound_schema_default(
        args,
        parameter="direction",
        parameter_schema={"type": "string", "enum": ["left", "right"], "default": "left"},
        required_inputs={"direction"},
    )
    assert args == {"direction": "left"}



def test_integrated_fast_validation_drops_exact_unbound_optional_default_after_grounding() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.schema import UserMeaningInterpretationRequest
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import OllamaUserMeaningInterpreter
    from agent.app.planner_fast_validation import validate_fast_advance_output
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.plan import FastPlannerAdvanceModelOutput

    text = "turn left"
    decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
        UserMeaningInterpretationRequest(text=text),
        '{"confidence":1.0,"responsibilities":[{"local_ref":"r1","outcome":"turn left","output_mode":"body_action","continuity_scope":"goal","confidence":1.0,"source_evidence":{"source_start_token_ref":"t0","source_end_token_ref":"t1"}}],"meaning_uncertainties":[]}',
    )
    request = CognitiveWorkRequest(
        sid="default-owner", text=text, responsibilities=decision.responsibilities,
        interpretation_confidence=1.0,
    )
    capability = {
        "capability_id": "test.turn",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["left", "right"]},
                "duration_s": {"type": "number", "default": 2.0},
                "turn_rate_radps": {"type": "number", "default": 0.12},
            },
            "required": ["direction"],
            "additionalProperties": False,
        },
    }
    raw = {
        "disposition": "execute",
        "coverage": "complete",
        "covered_responsibility_refs": ["r1"],
        "activities": [{
            "role": "capability",
            "activity_id": "turn",
            "capability_id": "test.turn",
            "args": {"direction": "left", "duration_s": 2.0, "turn_rate_radps": 0.12},
            "argument_sources": {
                "direction": {"source_start_token_ref": "t1", "source_end_token_ref": "t1"}
            },
            "timing": "sequential",
            "source_responsibility_refs": ["r1"],
        }],
        "continuations": [],
        "confidence": 1.0,
        "unresolved": [],
        "reason_summary": "Turn left.",
    }
    output = FastPlannerAdvanceModelOutput.model_validate(raw)

    validate_fast_advance_output(
        output, request=request, responsibilities=list(request.responsibilities),
        capabilities=[capability],
    )

    assert output.activities[0].args == {"direction": "left"}


def test_integrated_fast_validation_keeps_nondefault_unbound_override_fail_closed() -> None:
    from agent.app.cognitive_core.user_meaning_interpreter.schema import UserMeaningInterpretationRequest
    from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import OllamaUserMeaningInterpreter
    from agent.app.planner_fast_validation import (
        AuthoritativeGroundingValidationError,
        validate_fast_advance_output,
    )
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.plan import FastPlannerAdvanceModelOutput

    text = "turn left"
    decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
        UserMeaningInterpretationRequest(text=text),
        '{"confidence":1.0,"responsibilities":[{"local_ref":"r1","outcome":"turn left","output_mode":"body_action","continuity_scope":"goal","confidence":1.0,"source_evidence":{"source_start_token_ref":"t0","source_end_token_ref":"t1"}}],"meaning_uncertainties":[]}',
    )
    request = CognitiveWorkRequest(
        sid="default-owner-nondefault", text=text, responsibilities=decision.responsibilities,
        interpretation_confidence=1.0,
    )
    capability = {
        "capability_id": "test.turn",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["left", "right"]},
                "turn_rate_radps": {"type": "number", "default": 0.12},
            },
            "required": ["direction"],
            "additionalProperties": False,
        },
    }
    raw = {
        "disposition": "execute",
        "coverage": "complete",
        "covered_responsibility_refs": ["r1"],
        "activities": [{
            "role": "capability",
            "activity_id": "turn",
            "capability_id": "test.turn",
            "args": {"direction": "left", "turn_rate_radps": 0.01},
            "argument_sources": {
                "direction": {"source_start_token_ref": "t1", "source_end_token_ref": "t1"}
            },
            "timing": "sequential",
            "source_responsibility_refs": ["r1"],
        }],
        "continuations": [],
        "confidence": 1.0,
        "unresolved": [],
        "reason_summary": "Turn left.",
    }
    output = FastPlannerAdvanceModelOutput.model_validate(raw)

    with __import__("pytest").raises(AuthoritativeGroundingValidationError):
        validate_fast_advance_output(
            output, request=request, responsibilities=list(request.responsibilities),
            capabilities=[capability],
        )

    assert output.activities[0].args["turn_rate_radps"] == 0.01

def test_planner_prompt_assigns_schema_defaults_to_trusted_runtime_not_model_work() -> None:
    prompt = EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT.lower()

    assert "omit every optional input" in prompt
    assert "even when its schema declares a default" in prompt
    assert "do not copy, choose, modify or restate schema defaults" in prompt
    assert "do not replace omission with a minimum, maximum, conservative, guessed" in prompt
    assert "provider realization applies declared defaults" in prompt
    assert "use their declared schema_default" not in prompt


def test_fast_streaming_prompt_hides_optional_default_value_but_preserves_override_contract() -> None:
    capability = {
        "capability_id": "test.turn",
        "description": "Turn left or right.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["left", "right"]},
                "turn_rate_radps": {
                    "type": "number",
                    "minimum": 0.01,
                    "maximum": 0.2,
                    "default": 0.12,
                },
            },
            "required": ["direction"],
            "additionalProperties": False,
        },
    }
    before = capability["input_schema"]["properties"]["turn_rate_radps"].copy()

    projected, = fast_advance_streaming_capability_prompt_projection([capability])
    rate = projected["args_schema"]["properties"]["turn_rate_radps"]

    assert "default" not in rate
    assert rate["x-chromie-default-owner"] == "trusted_runtime"
    assert rate["minimum"] == 0.01 and rate["maximum"] == 0.2
    assert "omit unless" in rate["description"].lower()
    assert projected["args_schema"]["required"] == ["direction"]
    assert capability["input_schema"]["properties"]["turn_rate_radps"] == before
