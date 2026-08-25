#!/usr/bin/env python3
"""File-backed behavior scenario loading, execution, and reporting.

The scenarios here are Level A regression evidence: deterministic module and
dependency-light integration checks. They do not call live services, run
microphones/speakers, execute simulator motion, or ask an LLM to judge results.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_gateway import CognitiveGateway
from orchestrator.runtime.input_session_runtime import input_session_runtime_for
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.interaction_coordinator import (
    CapabilityInteractionDispatch,
    InteractionRuntimeCoordinator,
)
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.session import SessionTracker
from orchestrator.runtime.capability_runtime import (
    LocalSpeechCapabilityProvider,
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityRuntime,
    CapabilityRuntimeResult,
    RuntimeAuthorization,
    local_speech_definition,
)
from orchestrator.runtime.soridormi_capability_provider import (
    SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    MEDIA_CAPABILITY_IDS,
    CapabilityResult,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    media_capability_output_schema,
    vocal_performance_output_schema,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CoreInterpretationResult,
)
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerFirstResponse,
)
from shared.chromie_contracts.reflex import CancellationDirective
from shared.chromie_contracts.planner_response import PlannerResponseProjection
from shared.chromie_contracts.plan import canonical_plan_fingerprint
from shared.chromie_contracts.semantic_task import ResponsePlan
from agent.app.cognitive_core.goal_interpreter.errors import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import OllamaGoalInterpreter
from agent.app.cognitive_core.goal_interpreter.schema import (
    GoalInterpretationDecision,
    GoalInterpretationRequest,
)

DEFAULT_SCENARIO_ROOT = ROOT / "scenarios"
DEFAULT_REPORT_ROOT = ROOT / ".chromie" / "reports" / "behavior-scenarios"
SUPPORTED_SUITES = {
    "goal_interpretation", "cognitive_core_dialogue",
    "cognitive_runtime", "cognitive_turn_loop",
}


@dataclass(frozen=True)
class BehaviorScenario:
    path: Path
    scenario_id: str
    suite: str
    level: str
    text: str = ""
    language: str | None = None
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    stub: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    turns: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        return f"{self.suite}/{self.scenario_id}"


class _GoalInterpretationLlm:
    def __init__(self, decision: GoalInterpretationDecision | None) -> None:
        self.decision = decision
        self.calls = 0
        self.stages: list[str] = []

    async def interpret_goal(
        self, request: GoalInterpretationRequest
    ) -> GoalInterpretationDecision:
        self.calls += 1
        self.stages.append("goal_interpretation")
        if self.decision is None:
            raise AssertionError(f"Goal Interpretation model should not be called for {request.text!r}")
        return self.decision


class _ScriptedGoalInterpreter(OllamaGoalInterpreter):
    """Run the bounded Goal Interpretation transaction with scripted model output.

    The primary interpretation, optional one DTO repair, normalization, and
    deterministic validators run through ``OllamaGoalInterpreter.interpret_goal()``.
    Only the external model completion is replaced by a file-backed script.
    """

    def __init__(
        self,
        script: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            ollama_url="http://scenario.invalid",
            model="scenario-fast-goal-interpreter",
            timeout_ms=1000,
            num_predict=160,
        )
        self.script = [dict(item) for item in script]
        self.calls = 0
        self.stages: list[str] = []

    async def _chat_logged(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request: GoalInterpretationRequest | None = None,
    ) -> dict[str, Any]:
        del payload, request
        self.calls += 1
        self.stages.append(stage)
        if not self.script:
            raise AssertionError(f"unexpected model stage {stage!r}; script exhausted")
        item = self.script.pop(0)
        expected_stage = str(item.get("stage") or "").strip()
        if expected_stage and expected_stage != stage:
            raise AssertionError(
                f"model stage {stage!r}, expected scripted stage {expected_stage!r}"
            )
        if item.get("error"):
            raise RuntimeError(str(item["error"]))
        if "content" in item:
            content = str(item.get("content") or "")
        else:
            decision = item.get("decision")
            if not isinstance(decision, dict):
                raise AssertionError(
                    f"scripted stage {stage!r} requires decision object or content"
                )
            content = json.dumps(decision, ensure_ascii=False, separators=(",", ":"))
        return {
            "model": "scenario-model",
            "message": {"content": content},
            "done": True,
            "done_reason": "stop",
        }


class _CognitiveScenarioRuntime:
    def __init__(self, capabilities: list[dict[str, Any]]) -> None:
        self.definitions: dict[str, CapabilityDefinition] = {}
        for item in capabilities:
            capability_id = str(
                item.get("capability_id") or item.get("capability_id") or ""
            )
            raw_output_schema = item.get("output_schema")
            if raw_output_schema is None and capability_id.startswith("soridormi."):
                # These fixtures model the upstream Soridormi catalog. Chromie's
                # production catalog adapter owns the stable named-skill result
                # envelope, so reproduce that materialization here instead of
                # requiring every scenario to duplicate an adapter-owned schema.
                raw_output_schema = SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA
            elif (
                raw_output_schema is None
                and capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
            ):
                raw_output_schema = vocal_performance_output_schema()
            elif (
                raw_output_schema is None
                and capability_id in MEDIA_CAPABILITY_IDS.values()
            ):
                raw_output_schema = media_capability_output_schema()
            definition = CapabilityDefinition(
                capability_id=capability_id,
                version=str(item.get("version") or "0.1.0"),
                provider_id=str(item.get("provider_id") or "scenario.provider"),
                description=str(item.get("description") or ""),
                input_schema=dict(item.get("input_schema") or {}),
                output_schema=dict(raw_output_schema or {}),
                available=bool(item.get("available", True)),
                unavailable_reason=item.get("unavailable_reason"),
                requires_confirmation=bool(item.get("requires_confirmation", False)),
                interruptible=bool(item.get("interruptible", True)),
                can_run_parallel=bool(item.get("can_run_parallel", True)),
                exclusive_group=(str(item.get("exclusive_group") or "").strip() or None),
                timeout_ms=int(item.get("timeout_ms", 30000)),
                metadata={
                    "resource_claims": list(item.get("resource_claims") or []),
                    **dict(item.get("metadata") or {}),
                },
            )
            self.definitions[definition.capability_id] = definition

    async def ensure_capability_definitions(self, capability_ids: list[str]) -> None:
        missing = [capability_id for capability_id in capability_ids if capability_id not in self.definitions]
        if missing:
            raise ValueError("unknown scenario capabilities: " + ",".join(missing))

    def capability_definition(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self.definitions[capability_id]
        except KeyError as exc:
            raise ValueError(f"unknown scenario capability {capability_id!r}") from exc


class _CognitiveTurnEvidenceRecorder:
    def __init__(self) -> None:
        self.outcomes: list[dict[str, Any]] = []

    def record_outcome(self, bundle: Any, **kwargs: Any) -> None:
        self.outcomes.append({"bundle": bundle, **kwargs})


class _BlockingScenarioProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        started: asyncio.Event,
        cancelled_request_ids: list[str],
    ) -> None:
        self.provider_id = provider_id
        self.started = started
        self.cancelled_request_ids = cancelled_request_ids

    async def execute(
        self,
        request: Any,
        definition: CapabilityDefinition,
        context: Any,
    ) -> CapabilityResult:
        del definition, context
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError(
            f"blocking scenario request unexpectedly resumed: {request.request_id}"
        )

    async def cancel(
        self,
        request: Any,
        definition: CapabilityDefinition,
        context: Any,
    ) -> None:
        del definition, context
        self.cancelled_request_ids.append(request.request_id)


class _CognitiveTurnScenarioRuntime:
    """Deterministic execution boundary for Level A turn-loop scenarios."""

    def __init__(self, stub: dict[str, Any]) -> None:
        catalog = _CognitiveScenarioRuntime(
            list(stub.get("capabilities") or [])
        )
        self.definitions = catalog.definitions
        self.stub = stub
        self.mode = str(stub.get("execution_mode") or "scripted")
        self.calls: list[InteractionResponse] = []
        self.provider_started = asyncio.Event()
        self.cancelled_request_ids: list[str] = []
        self.on_effectful_done: Any = None
        self.soridormi_invoker = None
        self.runtime: CapabilityRuntime | None = None
        if self.mode == "active_cancel":
            registry = CapabilityRegistry()
            registry.register(local_speech_definition())
            for definition in self.definitions.values():
                registry.register(definition)
            self.runtime = CapabilityRuntime(registry)
            self.runtime.register_provider(
                LocalSpeechCapabilityProvider(
                    lambda _args: {
                        "scheduled": True,
                        "playback_started": True,
                        "spoken": True,
                    }
                )
            )
            for provider_id in sorted(
                {item.provider_id for item in self.definitions.values()}
            ):
                self.runtime.register_provider(
                    _BlockingScenarioProvider(
                        provider_id,
                        started=self.provider_started,
                        cancelled_request_ids=self.cancelled_request_ids,
                    )
                )

    async def ensure_capability_definitions(self, capability_ids: list[str]) -> None:
        missing = [
            capability_id for capability_id in capability_ids
            if capability_id not in self.definitions
        ]
        if missing:
            raise ValueError(
                "unknown cognitive-turn scenario capabilities: "
                + ",".join(missing)
            )

    def capability_definition(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self.definitions[capability_id]
        except KeyError as exc:
            raise ValueError(
                f"unknown cognitive-turn scenario capability {capability_id!r}"
            ) from exc

    def apply_current_schema_overrides(self) -> None:
        raw = self.stub.get("current_output_schemas") or {}
        if not isinstance(raw, dict):
            raise ValueError("stub.current_output_schemas must be an object")
        for capability_id, schema in raw.items():
            if capability_id not in self.definitions:
                raise ValueError(
                    f"current schema override references unknown capability {capability_id!r}"
                )
            if not isinstance(schema, dict):
                raise ValueError(
                    f"current schema override for {capability_id!r} must be an object"
                )
            updated = self.definitions[capability_id].model_copy(
                deep=True,
                update={"output_schema": dict(schema)},
            )
            self.definitions[capability_id] = updated
            if self.runtime is not None:
                self.runtime.registry.upsert(updated)

    def _scripted_terminal_result(
        self,
        response: InteractionResponse,
    ) -> CapabilityRuntimeResult:
        plan_requests = [
            request
            for request in response.capabilities
            if request.metadata.get("source")
            == "goal_driven_canonical_plan"
        ]
        if not plan_requests:
            return CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id=item.id,
                        capability_id="chromie.speak",
                        status="completed",
                        provider_id="chromie.local_speech",
                        output={"playback_started": True},
                    )
                    for item in response.speech
                ],
            )
        if self.mode == "provider_exception_before_results":
            return CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="failed",
            )

        requests_by_step = {
            str(request.metadata.get("step_id") or ""): request
            for request in plan_requests
        }
        results: list[CapabilityResult] = []
        for raw in self.stub.get("results") or []:
            if not isinstance(raw, dict):
                raise ValueError("stub.results entries must be objects")
            step_id = str(raw.get("step_id") or "").strip()
            request = requests_by_step.get(step_id)
            if request is None:
                raise ValueError(
                    f"scripted result references unknown step {step_id!r}"
                )
            results.append(
                CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=request.capability_version,
                    status=str(raw.get("status") or "completed"),
                    provider_id=self.capability_definition(
                        request.capability_id
                    ).provider_id,
                    output=dict(raw.get("output") or {}),
                    reason_code=raw.get("reason_code"),
                    message=str(raw.get("message") or ""),
                )
            )
        status = str(
            self.stub.get("runtime_status")
            or (
                "completed"
                if results
                and all(item.status == "completed" for item in results)
                else "failed"
            )
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status=status,
            results=results,
        )
        if self.on_effectful_done is not None:
            self.on_effectful_done()
        return execution

    async def submit_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> CapabilityInteractionDispatch:
        del session_id
        self.calls.append(response)
        plan_requests = [
            request
            for request in response.capabilities
            if request.metadata.get("source")
            == "goal_driven_canonical_plan"
        ]
        if self.mode == "active_cancel" and plan_requests:
            if self.runtime is None:  # pragma: no cover - construction guard
                raise AssertionError("active-cancel runtime was not initialized")
            receipt = await self.runtime.submit(
                response,
                authorization=RuntimeAuthorization(
                    confirmed_request_ids=set(confirmed_request_ids or ())
                ),
            )
            return CapabilityInteractionDispatch(
                source_response=response,
                runtime_response=response,
                receipt=receipt,
                immediate_execution=None,
                preexecuted_results=[],
                preexecuted_traces=[],
            )
        execution = self._scripted_terminal_result(response)
        return CapabilityInteractionDispatch(
            source_response=response,
            runtime_response=response,
            receipt=None,
            immediate_execution=execution,
            preexecuted_results=[],
            preexecuted_traces=[],
        )

    async def wait_dispatch(
        self,
        dispatch: CapabilityInteractionDispatch,
    ) -> CapabilityRuntimeResult:
        if dispatch.immediate_execution is not None:
            return dispatch.immediate_execution
        if self.runtime is None or dispatch.receipt is None:
            raise RuntimeError("scenario dispatch has no Runtime receipt")
        return await self.runtime.wait_terminal(dispatch.receipt)

    async def cancel_all(self) -> None:
        if self.runtime is not None:
            await self.runtime.cancel_all()

    async def cancel_scope(
        self,
        directive: CancellationDirective,
    ) -> Any:
        if self.runtime is None:
            raise AssertionError("scoped-cancel runtime was not initialized")
        return await self.runtime.cancel_scope(directive)


class _CognitiveScenarioClient:
    def __init__(self, stub: dict[str, Any]) -> None:
        self.stub = stub
        self.deep_plans = list(stub.get("deep_plans") or [])
        self.calls: list[str] = []

    async def resolve_fast_first_response(
        self, *args: Any, **kwargs: Any
    ) -> FastPlannerFirstResponse:
        del args
        request = kwargs["request"]
        # File-backed Level A scenarios do not fabricate model-authored speech.
        # Live-text evidence covers the real first-response Planner phase.
        return FastPlannerFirstResponse(
            turn_id=str(request.sid),
            activity=None,
            metadata={"semantic_authority": "level_a_fixture"},
        )

    async def resolve_goal_association(self, *args: Any, **kwargs: Any) -> GoalAssociationResolution:
        del args
        self.calls.append("goal_association")
        request = kwargs["request"]
        raw = json.loads(json.dumps(self.stub["goal_association"]))
        raw["turn_id"] = str(request.context.get("turn_id") or request.sid)
        raw.setdefault("resolution_status", "resolved")
        refs = [item.local_ref for item in request.responsibilities]
        for index, goal in enumerate(raw.get("new_goals") or []):
            if not goal.get("source_responsibility_refs") and refs:
                goal["source_responsibility_refs"] = [refs[min(index, len(refs) - 1)]]
        for association in raw.get("associations") or []:
            if not association.get("source_responsibility_refs") and refs:
                association["source_responsibility_refs"] = [refs[0]]
        return GoalAssociationResolution.model_validate(raw)

    async def resolve_fast_advance(self, *args: Any, **kwargs: Any) -> FastPlannerAdvance:
        del args
        self.calls.append("fast_advance")
        request = kwargs["request"]
        return FastPlannerAdvance(
            turn_id=str(request.sid),
            disposition="unavailable",
            coverage="uncertain",
            covered_responsibility_refs=[
                item.local_ref for item in request.responsibilities
            ],
            confidence=0.99,
            reason_summary=(
                "The retained scenario supplies its canonical post-GA Fast Plan."
            ),
        )

    async def resolve_fast_plan(self, *args: Any, **kwargs: Any) -> CanonicalPlan:
        del args, kwargs
        self.calls.append("fast_plan")
        return CanonicalPlan.model_validate(self.stub["fast_plan"])

    async def resolve_deep_plan(self, *args: Any, **kwargs: Any) -> CanonicalPlan:
        del args
        self.calls.append("deep_plan")
        if not self.deep_plans:
            raise AssertionError("cognitive scenario deep-plan script exhausted")
        return CanonicalPlan.model_validate(self.deep_plans.pop(0))

def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError(f"expected string or list of strings, got {type(value).__name__}")


def _turn_text(turn: dict[str, Any], *, scenario_key: str, index: int) -> str:
    text = turn.get("ask")
    input_payload = turn.get("input")
    if (text is None or str(text).strip() == "") and isinstance(input_payload, dict):
        text = input_payload.get("text")
    text = str(text or "").strip()
    if not text:
        raise ValueError(f"{scenario_key}: turns[{index}].ask or input.text is required")
    return text


def _turn_language(turn: dict[str, Any], fallback: str | None = None) -> str | None:
    language = turn.get("language")
    input_payload = turn.get("input")
    if language is None and isinstance(input_payload, dict):
        language = input_payload.get("language")
    return str(language).strip() if language else fallback


def _text_contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(phrase.lower() in lower or phrase in text for phrase in phrases)


def _text_contains_all(text: str, phrases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return all(phrase.lower() in lower or phrase in text for phrase in phrases)


def _validate_dialogue_turns(
    raw_turns: Any,
    *,
    path: Path,
    scenario_id: str,
    suite: str = "dialogue",
) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ValueError(f"{path}: dialogue scenarios require a non-empty turns list")
    turns: list[dict[str, Any]] = []
    scenario_key = f"{suite}/{scenario_id}"
    for index, item in enumerate(raw_turns):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: turns[{index}] must be an object")
        _turn_text(item, scenario_key=scenario_key, index=index)
        stub = item.get("stub") or {}
        expect = item.get("expect") or {}
        if not isinstance(stub, dict) or not isinstance(expect, dict):
            raise ValueError(f"{path}: turns[{index}].stub and expect must be objects")
        turns.append(item)
    return tuple(turns)


def load_scenario_file(path: Path) -> BehaviorScenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: scenario file must contain one JSON object")
    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"{path}: unsupported schema_version {schema_version!r}")
    scenario_id = str(raw.get("id") or "").strip()
    suite = str(raw.get("suite") or "").strip()
    if not scenario_id:
        raise ValueError(f"{path}: missing id")
    if suite not in SUPPORTED_SUITES:
        raise ValueError(f"{path}: unsupported suite {suite!r}")
    if path.stem != scenario_id:
        raise ValueError(f"{path}: file stem must match scenario id {scenario_id!r}")
    stub = raw.get("stub") or {}
    expect = raw.get("expect") or {}
    if not isinstance(stub, dict) or not isinstance(expect, dict):
        raise ValueError(f"{path}: stub and expect must be objects")

    if suite == "cognitive_core_dialogue":
        turns = _validate_dialogue_turns(
            raw.get("turns"),
            path=path,
            scenario_id=scenario_id,
            suite=suite,
        )
        return BehaviorScenario(
            path=path,
            scenario_id=scenario_id,
            suite=suite,
            level=str(raw.get("level") or "integration").strip() or "integration",
            description=str(raw.get("description") or ""),
            tags=_tuple_of_strings(raw.get("tags")),
            text=_turn_text(turns[0], scenario_key=f"{suite}/{scenario_id}", index=0),
            language=_turn_language(turns[0]),
            stub=stub,
            expect=expect,
            turns=turns,
        )

    input_payload = raw.get("input")
    if not isinstance(input_payload, dict):
        raise ValueError(f"{path}: input must be an object")
    text = str(input_payload.get("text") or "").strip()
    if not text:
        raise ValueError(f"{path}: input.text is required")
    return BehaviorScenario(
        path=path,
        scenario_id=scenario_id,
        suite=suite,
        level=str(raw.get("level") or "module").strip() or "module",
        description=str(raw.get("description") or ""),
        tags=_tuple_of_strings(raw.get("tags")),
        text=text,
        language=input_payload.get("language"),
        stub=stub,
        expect=expect,
    )


def discover_scenario_files(
    root: Path = DEFAULT_SCENARIO_ROOT,
    *,
    suites: set[str] | None = None,
) -> list[Path]:
    suites = suites or set(SUPPORTED_SUITES)
    files: list[Path] = []
    for suite in sorted(suites):
        if suite not in SUPPORTED_SUITES:
            raise ValueError(f"unsupported suite {suite!r}")
        files.extend(sorted((root / suite).glob("*.json")))
    return files


def load_scenarios(
    root: Path = DEFAULT_SCENARIO_ROOT,
    *,
    suites: set[str] | None = None,
    only: set[str] | None = None,
) -> list[BehaviorScenario]:
    scenarios = [load_scenario_file(path) for path in discover_scenario_files(root, suites=suites)]
    seen: set[str] = set()
    for scenario in scenarios:
        if scenario.key in seen:
            raise ValueError(f"duplicate scenario key {scenario.key!r}")
        seen.add(scenario.key)
    if not only:
        return scenarios
    selected = [
        scenario
        for scenario in scenarios
        if scenario.scenario_id in only or scenario.key in only
    ]
    missing = only - {item.scenario_id for item in scenarios} - {item.key for item in scenarios}
    if missing:
        raise ValueError(f"unknown scenario id: {', '.join(sorted(missing))}")
    return selected


def _goal_interpretation_decision_from_stub(
    scenario: BehaviorScenario,
) -> GoalInterpretationDecision | None:
    raw = scenario.stub.get("llm_decision")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{scenario.key}: stub.llm_decision must be an object or null")
    return GoalInterpretationDecision.model_validate(raw)


def _goal_interpretation_script_from_stub(
    scenario_key: str,
    stub: dict[str, Any],
) -> list[dict[str, Any]] | None:
    raw = stub.get("llm_script")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{scenario_key}: stub.llm_script must be a non-empty list")
    script: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"{scenario_key}: stub.llm_script[{index}] must be an object"
            )
        script.append(dict(item))
    return script


def _expect_equal(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if expected is not None and actual != expected:
        errors.append(f"{label}={actual!r}, expected {expected!r}")


def _evaluate_goal_interpretation_expectations(
    scenario: BehaviorScenario,
    *,
    decision: GoalInterpretationDecision,
    llm_calls: int,
    llm_stages: list[str] | None = None,
    expect: dict[str, Any] | None = None,
) -> list[str]:
    expect = expect if isinstance(expect, dict) else scenario.expect
    errors: list[str] = []
    _expect_equal(errors, "confidence", decision.confidence, expect.get("confidence"))
    _expect_equal(errors, "unresolved", decision.unresolved, expect.get("unresolved"))
    _expect_equal(errors, "llm_calls", llm_calls, expect.get("llm_calls"))
    expected_stages = _tuple_of_strings(expect.get("llm_stages"))
    if expected_stages and list(expected_stages) != list(llm_stages or []):
        errors.append(
            f"llm_stages={list(llm_stages or [])!r}, expected {list(expected_stages)!r}"
        )
    expected_responsibilities = expect.get("responsibilities")
    if expected_responsibilities is not None:
        if not isinstance(expected_responsibilities, list):
            errors.append("expect.responsibilities must be a list")
        else:
            actual_responsibilities = list(decision.responsibilities or [])
            if len(actual_responsibilities) != len(expected_responsibilities):
                errors.append(
                    "responsibilities "
                    f"count={len(actual_responsibilities)}, expected "
                    f"{len(expected_responsibilities)}; actual="
                    f"{[item.model_dump(mode='json') for item in actual_responsibilities]!r}"
                )
            for index, expected_responsibility in enumerate(expected_responsibilities):
                if index >= len(actual_responsibilities) or not isinstance(
                    expected_responsibility, dict
                ):
                    continue
                actual = actual_responsibilities[index]
                for field in (
                    "local_ref",
                    "outcome",
                    "relationship",
                    "target_goal_ids",
                    "resolved_gap_ids",
                    "confidence",
                ):
                    if field in expected_responsibility:
                        _expect_equal(
                            errors,
                            f"responsibilities[{index}].{field}",
                            getattr(actual, field),
                            expected_responsibility[field],
                        )
                expected_bindings = expected_responsibility.get("bindings")
                if isinstance(expected_bindings, dict):
                    for key, value in expected_bindings.items():
                        if actual.bindings.get(key) != value:
                            errors.append(
                                f"responsibilities[{index}].bindings[{key!r}]="
                                f"{actual.bindings.get(key)!r}, expected {value!r}"
                            )
    return errors


def _scenario_goal_interpreter_from_stub(
    scenario_key: str,
    stub: dict[str, Any],
    *,
    fallback_decision: GoalInterpretationDecision | None = None,
) -> _GoalInterpretationLlm | _ScriptedGoalInterpreter:
    script = _goal_interpretation_script_from_stub(scenario_key, stub)
    if script is not None:
        return _ScriptedGoalInterpreter(script)
    raw_decision = stub.get("llm_decision")
    if raw_decision is None:
        return _GoalInterpretationLlm(fallback_decision)
    if not isinstance(raw_decision, dict):
        raise ValueError(f"{scenario_key}: stub.llm_decision must be an object or null")
    return _GoalInterpretationLlm(
        GoalInterpretationDecision.model_validate(raw_decision)
    )


async def _run_goal_interpretation_turn(
    *,
    scenario: BehaviorScenario,
    text: str,
    language: str | None,
    context: dict[str, Any] | None,
    stub: dict[str, Any],
) -> tuple[
    GoalInterpretationDecision | InterpretationUnavailableError,
    _GoalInterpretationLlm | _ScriptedGoalInterpreter,
]:
    from agent.app.cognitive_core.goal_interpreter import engine as main

    interpreter = _scenario_goal_interpreter_from_stub(
        scenario.key,
        stub,
        fallback_decision=_goal_interpretation_decision_from_stub(scenario),
    )
    with patch.object(main, "goal_interpreter", interpreter):
        try:
            decision = await main.interpret_goal(
                GoalInterpretationRequest(
                    sid=scenario.scenario_id,
                    text=text,
                    language=language,
                    context=dict(context or {}),
                )
            )
        except InterpretationUnavailableError as exc:
            decision = exc
    return decision, interpreter


def _evaluate_interpretation_unavailable_expectations(
    *,
    expect: dict[str, Any],
    unavailable: InterpretationUnavailableError,
    llm_calls: int,
    llm_stages: list[str],
) -> list[str]:
    errors: list[str] = []
    _expect_equal(
        errors,
        "status",
        "interpretation_unavailable",
        expect.get("status"),
    )
    _expect_equal(errors, "llm_calls", llm_calls, expect.get("llm_calls"))
    expected_stages = _tuple_of_strings(expect.get("llm_stages"))
    if expected_stages and list(expected_stages) != list(llm_stages):
        errors.append(
            f"llm_stages={list(llm_stages)!r}, expected {list(expected_stages)!r}"
        )
    reason_contains = _tuple_of_strings(expect.get("failure_reason_contains"))
    for phrase in reason_contains:
        if phrase not in unavailable.reason:
            errors.append(
                f"failure reason missing {phrase!r}: {unavailable.reason!r}"
            )
    if expect.get("status") != "interpretation_unavailable":
        errors.append(
            "unexpected interpretation_unavailable outcome: " + unavailable.reason
        )
    return errors


async def evaluate_goal_interpretation_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    context = scenario.stub.get("context") or {}
    if not isinstance(context, dict):
        raise ValueError(f"{scenario.key}: stub.context must be an object")
    decision, interpreter = await _run_goal_interpretation_turn(
        scenario=scenario,
        text=scenario.text,
        language=scenario.language,
        context=context,
        stub=scenario.stub,
    )

    if isinstance(decision, InterpretationUnavailableError):
        errors = _evaluate_interpretation_unavailable_expectations(
            expect=scenario.expect,
            unavailable=decision,
            llm_calls=interpreter.calls,
            llm_stages=interpreter.stages,
        )
        return {
            "ok": not errors,
            "errors": errors,
            "actual": {
                "status": "interpretation_unavailable",
                "reason": decision.reason,
                "llm_calls": interpreter.calls,
                "llm_stages": list(interpreter.stages),
            },
        }

    errors = _evaluate_goal_interpretation_expectations(
        scenario,
        decision=decision,
        llm_calls=interpreter.calls,
        llm_stages=interpreter.stages,
    )
    return {
        "ok": not errors,
        "errors": errors,
        "actual": {
            "confidence": decision.confidence,
            "unresolved": list(decision.unresolved),
            "llm_calls": interpreter.calls,
            "llm_stages": list(interpreter.stages),
            "responsibilities": [
                item.model_dump(mode="json", exclude_none=True)
                for item in decision.responsibilities
            ],
        },
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_safe_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _context_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "history": _json_safe_copy(snapshot.get("history") or []),
        "session_memory": _json_safe_copy(snapshot.get("session_memory") or {}),
        "current_task_context": _json_safe_copy(snapshot.get("current_task_context")),
    }


def _merged_turn_stub(scenario: BehaviorScenario, turn: dict[str, Any]) -> dict[str, Any]:
    base = dict(scenario.stub)
    turn_stub = turn.get("stub") or {}
    if not isinstance(turn_stub, dict):
        raise ValueError(f"{scenario.key}: turn.stub must be an object")
    return {**base, **turn_stub}


def _turn_context(scenario: BehaviorScenario, turn: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    scenario_context = scenario.stub.get("context")
    turn_stub = turn.get("stub") or {}
    turn_context = turn_stub.get("context") if isinstance(turn_stub, dict) else None
    if isinstance(scenario_context, dict):
        context.update(scenario_context)
    if isinstance(turn_context, dict):
        context.update(turn_context)
    context.setdefault("conversation_id", snapshot.get("conversation_id"))
    context.setdefault("session_memory", snapshot.get("session_memory") or {})
    context.setdefault("current_task_context", snapshot.get("current_task_context"))
    context.setdefault("active_task_contexts", snapshot.get("active_task_contexts") or [])
    context.setdefault("active_pending_tasks", snapshot.get("active_pending_tasks") or [])
    return context


def _evaluate_context_expectations(
    errors: list[str],
    expect: dict[str, Any],
    *,
    pre_snapshot: dict[str, Any],
    post_snapshot: dict[str, Any],
) -> None:
    pre_history_text = _json_text(pre_snapshot.get("history") or [])
    post_history_text = _json_text(post_snapshot.get("history") or [])
    session_memory_text = _json_text(pre_snapshot.get("session_memory") or {})
    post_session_memory_text = _json_text(post_snapshot.get("session_memory") or {})
    pre_session_memory = pre_snapshot.get("session_memory") or {}
    post_session_memory = post_snapshot.get("session_memory") or {}
    extracted_memory_text = _json_text(
        pre_session_memory.get("extracted_memory") if isinstance(pre_session_memory, dict) else []
    )
    post_extracted_memory_text = _json_text(
        post_session_memory.get("extracted_memory") if isinstance(post_session_memory, dict) else []
    )
    memory_summary_text = str(
        pre_session_memory.get("memory_summary") if isinstance(pre_session_memory, dict) else ""
    )
    post_memory_summary_text = str(
        post_session_memory.get("memory_summary") if isinstance(post_session_memory, dict) else ""
    )
    current_task = post_snapshot.get("current_task_context") or {}
    current_task_text = _json_text(current_task)

    history_contains = _tuple_of_strings(expect.get("history_contains"))
    if history_contains and not _text_contains_all(pre_history_text, history_contains):
        errors.append(
            f"pre-turn history missing required phrases {list(history_contains)!r}: {pre_history_text!r}"
        )
    history_any = _tuple_of_strings(expect.get("history_any"))
    if history_any and not _text_contains_any(pre_history_text, history_any):
        errors.append(
            f"pre-turn history missing any expected phrase {list(history_any)!r}: {pre_history_text!r}"
        )
    session_contains = _tuple_of_strings(expect.get("session_memory_contains"))
    if session_contains and not _text_contains_all(session_memory_text, session_contains):
        errors.append(
            f"pre-turn session memory missing phrases {list(session_contains)!r}: {session_memory_text!r}"
        )
    post_history_contains = _tuple_of_strings(expect.get("post_history_contains"))
    if post_history_contains and not _text_contains_all(post_history_text, post_history_contains):
        errors.append(
            f"post-turn history missing phrases {list(post_history_contains)!r}: {post_history_text!r}"
        )
    post_session_contains = _tuple_of_strings(expect.get("post_session_memory_contains"))
    if post_session_contains and not _text_contains_all(post_session_memory_text, post_session_contains):
        errors.append(
            f"post-turn session memory missing phrases {list(post_session_contains)!r}: {post_session_memory_text!r}"
        )
    extracted_contains = _tuple_of_strings(expect.get("extracted_memory_contains"))
    if extracted_contains and not _text_contains_all(extracted_memory_text, extracted_contains):
        errors.append(
            f"pre-turn extracted memory missing phrases {list(extracted_contains)!r}: {extracted_memory_text!r}"
        )
    post_extracted_contains = _tuple_of_strings(expect.get("post_extracted_memory_contains"))
    if post_extracted_contains and not _text_contains_all(post_extracted_memory_text, post_extracted_contains):
        errors.append(
            f"post-turn extracted memory missing phrases {list(post_extracted_contains)!r}: {post_extracted_memory_text!r}"
        )
    memory_summary_contains = _tuple_of_strings(expect.get("memory_summary_contains"))
    if memory_summary_contains and not _text_contains_all(memory_summary_text, memory_summary_contains):
        errors.append(
            f"pre-turn memory summary missing phrases {list(memory_summary_contains)!r}: {memory_summary_text!r}"
        )
    post_memory_summary_contains = _tuple_of_strings(expect.get("post_memory_summary_contains"))
    if post_memory_summary_contains and not _text_contains_all(post_memory_summary_text, post_memory_summary_contains):
        errors.append(
            f"post-turn memory summary missing phrases {list(post_memory_summary_contains)!r}: {post_memory_summary_text!r}"
        )
    task_contains = _tuple_of_strings(expect.get("current_task_context_contains"))
    if task_contains and not _text_contains_all(current_task_text, task_contains):
        errors.append(
            f"current task context missing phrases {list(task_contains)!r}: {current_task_text!r}"
        )


async def evaluate_cognitive_core_dialogue_scenario(
    scenario: BehaviorScenario,
) -> dict[str, Any]:
    manager = ConversationStateManager(
        base_conversation_id=scenario.scenario_id,
        max_turns=int(scenario.stub.get("max_turns", 12)),
        max_pending_tasks=int(scenario.stub.get("max_pending_tasks", 8)),
        task_store_enabled=False,
    )
    turn_reports: list[dict[str, Any]] = []
    all_errors: list[str] = []

    for index, turn in enumerate(scenario.turns):
        turn_id = str(turn.get("id") or f"turn_{index + 1}")
        text = _turn_text(turn, scenario_key=scenario.key, index=index)
        language = _turn_language(turn, scenario.language)
        manager.prepare_for_user_text(text, sid=turn_id)
        pre_snapshot = manager.snapshot()
        stub = _merged_turn_stub(scenario, turn)
        context = _turn_context(scenario, turn, pre_snapshot)
        context.setdefault("history", pre_snapshot.get("history") or [])
        context.setdefault(
            "active_task_snapshots",
            pre_snapshot.get("active_task_snapshots") or [],
        )

        decision, interpreter = await _run_goal_interpretation_turn(
            scenario=scenario,
            text=text,
            language=language,
            context=context,
            stub=stub,
        )
        expect = turn.get("expect") or {}
        if isinstance(decision, InterpretationUnavailableError):
            errors = _evaluate_interpretation_unavailable_expectations(
                expect=expect if isinstance(expect, dict) else {},
                unavailable=decision,
                llm_calls=interpreter.calls,
                llm_stages=interpreter.stages,
            )
            all_errors.extend(f"{turn_id}: {error}" for error in errors)
            turn_reports.append(
                {
                    "id": turn_id,
                    "ok": not errors,
                    "errors": errors,
                    "actual": {
                        "status": "interpretation_unavailable",
                        "reason": decision.reason,
                        "llm_calls": interpreter.calls,
                        "llm_stages": list(interpreter.stages),
                    },
                }
            )
            continue
        errors = _evaluate_goal_interpretation_expectations(
            scenario,
            decision=decision,
            llm_calls=interpreter.calls,
            llm_stages=interpreter.stages,
            expect=expect if isinstance(expect, dict) else {},
        )

        manager.record_user_turn(
            turn_id,
            text,
            metadata={
                "goal_interpretation": decision.model_dump(
                    mode="json", exclude_none=True
                )
            },
        )
        post_snapshot = manager.snapshot()
        if isinstance(expect, dict):
            _evaluate_context_expectations(
                errors,
                expect,
                pre_snapshot=_context_report(pre_snapshot),
                post_snapshot=_context_report(post_snapshot),
            )

        if errors:
            all_errors.extend(f"{turn_id}: {error}" for error in errors)
        turn_reports.append(
            {
                "id": turn_id,
                "ask": text,
                "ok": not errors,
                "errors": errors,
                "interpretation": {
                    "confidence": decision.confidence,
                    "unresolved": list(decision.unresolved),
                    "responsibilities": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in decision.responsibilities
                    ],
                },
                "llm_stages": list(interpreter.stages),
                "pre_context": _context_report(pre_snapshot),
                "post_context": _context_report(post_snapshot),
            }
        )

    return {
        "ok": not all_errors,
        "errors": all_errors,
        "actual": {"turn_count": len(turn_reports), "turns": turn_reports},
    }


async def evaluate_cognitive_runtime_scenario(
    scenario: BehaviorScenario,
) -> dict[str, Any]:
    stub = scenario.stub
    client = _CognitiveScenarioClient(stub)
    runtime = _CognitiveScenarioRuntime(list(stub.get("capabilities") or []))
    mode = str(stub.get("mode") or "report_only")
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=client,
        adapter=CanonicalPlanRuntimeAdapter(runtime),
        policy=CognitiveRuntimePolicy(mode=mode),
    )
    gateway = CognitiveGateway()
    capture = gateway.capture(
        scenario.text,
        session_id=scenario.scenario_id,
        conversation_id=f"level-a-{scenario.scenario_id}",
        channel="text",
        language=scenario.language or "en-US",
    )
    envelope = gateway.for_direct(
        capture,
        context=dict(stub.get("context") or {"history": []}),
        source="level_a.cognitive_runtime",
        reason="deterministic Level A scenario input",
    )
    goal_candidates = list(
        (stub.get("goal_association") or {}).get("new_goals") or []
    )
    responsibilities = [
        CognitiveResponsibilityProposal(
            local_ref=f"r{index}",
            outcome=str(item.get("description") or scenario.text),
            output_mode=(
                "information"
                if str((item.get("metadata") or {}).get("resource_kind") or "") == "information"
                else (
                    "body_action"
                    if str((item.get("metadata") or {}).get("output_mode") or "") == "body_action"
                    else "stateful_effect"
                )
            ),
            confidence=float(
                (stub.get("goal_association") or {}).get("confidence", 0.9)
            ),
        )
        for index, item in enumerate(goal_candidates, start=1)
        if isinstance(item, dict)
    ]
    if not responsibilities:
        responsibilities = [
            CognitiveResponsibilityProposal(
                local_ref="r1",
                outcome=scenario.text,
                output_mode="stateful_effect",
                confidence=0.9,
            )
        ]
    core_interpretation = CoreInterpretationResult(
        turn_id=envelope.turn_id,
        session_id=envelope.session_id,
        confidence=min(item.confidence for item in responsibilities),
        language=envelope.normalized_input.language,
        responsibilities=responsibilities,
    )
    resolution = await coordinator.resolve(
        object(),
        text=scenario.text,
        sid=scenario.scenario_id,
        core_interpretation=core_interpretation,
        context=dict(stub.get("context") or {"history": []}),
        history=list((stub.get("context") or {}).get("history") or []),
        language=envelope.normalized_input.language,
        turn_envelope=envelope,
    )
    terminal = resolution.terminal_plan
    interaction = resolution.interaction_response
    goal_outcomes = (
        [
            {
                "goal_id": item.goal_id,
                "disposition": item.disposition,
                "coverage": item.coverage,
                "step_ids": list(item.step_ids),
            }
            for item in terminal.goal_outcomes
        ]
        if terminal is not None
        else []
    )
    speech_items = list(interaction.speech) if interaction else []
    speech_covers_goal_ids: list[str] = []
    for item in speech_items:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        for goal_id in metadata.get("covers_goal_ids") or []:
            goal_id = str(goal_id)
            if goal_id and goal_id not in speech_covers_goal_ids:
                speech_covers_goal_ids.append(goal_id)
    actual = {
        "status": resolution.status,
        "fallback_reason": resolution.fallback_reason,
        "planner_tier": terminal.planner_tier if terminal is not None else None,
        "disposition": terminal.disposition if terminal is not None else None,
        "coverage": terminal.coverage if terminal is not None else None,
        "goal_outcomes": goal_outcomes,
        "capability_ids": [item.capability_id for item in interaction.capabilities] if interaction else [],
        "capability_args": [item.args for item in interaction.capabilities] if interaction else [],
        "capability_timings": [item.timing for item in interaction.capabilities] if interaction else [],
        "capability_source_goal_ids": [
            list(item.metadata.get("source_goal_ids") or [])
            for item in interaction.capabilities
        ] if interaction else [],
        "capability_execution_lanes": [
            str(item.metadata.get("execution_lane") or "")
            for item in interaction.capabilities
        ] if interaction else [],
        "interaction_status": interaction.status if interaction else None,
        "speech_texts": [item.text for item in speech_items],
        "confirmation_prompt": (
            str(interaction.metadata.get("confirmation_prompt") or "")
            if interaction
            else ""
        ),
        "speech_covers_goal_ids": speech_covers_goal_ids,
        "requires_confirmation": interaction.requires_confirmation if interaction else False,
        "calls": list(client.calls),
    }
    expect = scenario.expect
    errors: list[str] = []
    for key in ("status", "planner_tier", "disposition", "coverage"):
        if key in expect and actual[key] != expect[key]:
            errors.append(f"{key}={actual[key]!r}, expected {expect[key]!r}")
    if "goal_outcomes" in expect and actual["goal_outcomes"] != list(expect["goal_outcomes"]):
        errors.append(
            f"goal_outcomes={actual['goal_outcomes']!r}, "
            f"expected {list(expect['goal_outcomes'])!r}"
        )
    expected_capability_ids = expect.get("capability_ids")
    if expected_capability_ids is None and "capability_ids" in expect:
        expected_capability_ids = expect["capability_ids"]
    if (
        expected_capability_ids is not None
        and actual["capability_ids"] != list(expected_capability_ids)
    ):
        errors.append(
            "capability_ids="
            f"{actual['capability_ids']!r}, expected {list(expected_capability_ids)!r}"
        )
    compatibility_keys = {
        "capability_args": "skill_args",
        "capability_timings": "skill_timings",
        "capability_source_goal_ids": "skill_source_goal_ids",
        "capability_execution_lanes": "skill_execution_lanes",
        "speech_covers_goal_ids": "speech_covers_goal_ids",
    }
    for key, legacy_key in compatibility_keys.items():
        expected_value = expect.get(key)
        if expected_value is None and legacy_key in expect:
            expected_value = expect[legacy_key]
        if expected_value is not None and actual[key] != list(expected_value):
            errors.append(f"{key}={actual[key]!r}, expected {list(expect[key])!r}")
    if "interaction_status" in expect and actual["interaction_status"] != expect["interaction_status"]:
        errors.append(
            f"interaction_status={actual['interaction_status']!r}, "
            f"expected {expect['interaction_status']!r}"
        )
    speech_text = "\n".join(actual["speech_texts"])
    for phrase in expect.get("speech_contains_all") or []:
        if str(phrase).casefold() not in speech_text.casefold():
            errors.append(f"speech missing required phrase {phrase!r}: {speech_text!r}")
    for phrase in expect.get("speech_forbids_all") or []:
        if str(phrase).casefold() in speech_text.casefold():
            errors.append(f"speech contains forbidden phrase {phrase!r}: {speech_text!r}")
    speech_any = list(expect.get("speech_contains_any") or [])
    if speech_any and not any(
        str(phrase).casefold() in speech_text.casefold() for phrase in speech_any
    ):
        errors.append(
            f"speech missing any expected phrase {speech_any!r}: {speech_text!r}"
        )
    if "requires_confirmation" in expect and actual["requires_confirmation"] is not bool(expect["requires_confirmation"]):
        errors.append(
            "requires_confirmation="
            f"{actual['requires_confirmation']!r}, expected {bool(expect['requires_confirmation'])!r}"
        )
    if expect.get("confirmation_prompt_matches_speech") is True:
        if (
            not actual["confirmation_prompt"]
            or actual["confirmation_prompt"] not in actual["speech_texts"]
        ):
            errors.append(
                "confirmation_prompt is not one of the authoritative speech stages: "
                f"{actual['confirmation_prompt']!r} not in {actual['speech_texts']!r}"
            )
    if "calls" in expect and actual["calls"] != list(expect["calls"]):
        errors.append(f"calls={actual['calls']!r}, expected {list(expect['calls'])!r}")
    return {"ok": not errors, "errors": errors, "actual": actual}


async def evaluate_cognitive_turn_loop_scenario(
    scenario: BehaviorScenario,
) -> dict[str, Any]:
    """Exercise the deterministic post-execution loop without live services."""

    stub = scenario.stub
    if str(stub.get("execution_mode") or "") == "overlapping_turns":
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        release_first = asyncio.Event()
        events: list[str] = []

        class _Sessions:
            state = {"sid-first": {}, "sid-second": {}}

        async def handle(
            self: VoiceAssistant,
            text: str,
            session_id: str,
        ) -> None:
            del self, text
            events.append(f"started:{session_id}")
            if session_id == "sid-first":
                first_started.set()
                try:
                    await release_first.wait()
                except asyncio.CancelledError:
                    events.append("cancelled:sid-first")
                    raise
            else:
                second_started.set()
            events.append(f"completed:{session_id}")

        assistant.active_turn_task = None
        assistant.active_turn_tasks = {}
        assistant.active_reflex_task = None
        assistant.concurrent_protective_reflex_tasks = set()
        assistant._protective_reflex_failure = False
        assistant._pending_turn_after_reflex = deque()
        assistant.sessions = _Sessions()
        assistant.handle_routed_text = MethodType(handle, assistant)
        assistant.session_log = lambda *args, **kwargs: None
        assistant.maybe_session_done = lambda *args, **kwargs: None

        input_runtime = input_session_runtime_for(assistant)
        input_runtime._launch_routed_turn(
            "Check the first person's request.",
            "sid-first",
        )
        first_task = assistant.active_turn_task
        if first_task is None:
            raise AssertionError("first routed turn was not launched")
        await asyncio.wait_for(first_started.wait(), timeout=1.0)

        input_runtime._launch_routed_turn(
            "Handle the second person's independent request.",
            "sid-second",
        )
        second_task = assistant.active_turn_task
        if second_task is None or second_task is first_task:
            raise AssertionError("second routed turn was not launched independently")
        await asyncio.wait_for(second_started.wait(), timeout=1.0)
        await asyncio.wait_for(asyncio.shield(second_task), timeout=1.0)
        await asyncio.sleep(0)

        first_cancelled_before_release = first_task.cancelled()
        release_first.set()
        await asyncio.gather(first_task, return_exceptions=True)
        await asyncio.sleep(0)
        active_turns = getattr(assistant, "active_turn_tasks", {})
        actual = {
            "first_started": first_started.is_set(),
            "second_started": second_started.is_set(),
            "first_cancelled": (
                first_cancelled_before_release
                or "cancelled:sid-first" in events
            ),
            "first_completed": "completed:sid-first" in events,
            "second_completed": "completed:sid-second" in events,
            "active_turn_count": len(active_turns),
        }
        errors = [
            f"{key}={actual.get(key)!r}, expected {expected!r}"
            for key, expected in scenario.expect.items()
            if actual.get(key) != expected
        ]
        return {"ok": not errors, "errors": errors, "actual": actual}

    plan = CanonicalPlan.model_validate(stub["plan"])
    runtime = _CognitiveTurnScenarioRuntime(stub)
    sessions = SessionTracker(enabled=True)
    session_id = sessions.create()
    gateway = CognitiveGateway()
    capture = gateway.capture(
        scenario.text,
        session_id=session_id,
        conversation_id="level-a-cognitive-turn-loop",
        channel="text",
    )
    envelope = gateway.for_direct(
        capture,
        context={"history": []},
        source="level_a.cognitive_turn_loop",
        reason="deterministic Level A scenario input",
    )
    response_plan_raw = stub.get("response_plan") or {
        "pre_action": {
            "text": "I will run the requested checks.",
            "speech_act": "inform",
            "commitment_state": "evaluating",
            "must_not_claim_completion": True,
            "covers_goal_ids": plan.goal_ids,
        }
    }
    planner_response = PlannerResponseProjection(
        projection_id=f"planner_response-{scenario.scenario_id}",
        canonical_plan_id=plan.plan_id,
        canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
        canonical_plan=plan,
        response_plan=ResponsePlan.model_validate(response_plan_raw),
        confidence=0.99,
        rationale="deterministic Level A turn-loop Planner response projection",
    )
    response = await CanonicalPlanRuntimeAdapter(runtime).build_response(
        plan=plan,
        planner_response=planner_response,
        session_id=session_id,
        language=scenario.language or "en-US",
        context={"history": []},
    )
    response = response.model_copy(
        deep=True,
        update={
            "metadata": {
                **response.metadata,
                **gateway.metadata(envelope),
            }
        },
    )
    runtime.apply_current_schema_overrides()

    manager = ConversationStateManager(
        base_conversation_id="level-a-cognitive-turn-loop"
    )
    manager.apply_goal_association_resolution(
        {
            "turn_id": envelope.turn_id,
            "resolution_status": "resolved",
            "new_goals": [
                {
                    "goal_id": goal_id,
                    "description": f"Complete {goal_id}.",
                    "source_text": scenario.text,
                }
                for goal_id in plan.goal_ids
            ],
            "confidence": 0.99,
            "reason_summary": "Deterministic scenario goals.",
        },
        sid=session_id,
        user_text=scenario.text,
        atomic=True,
    )
    manager.record_interaction_response(session_id, response)

    evidence = _CognitiveTurnEvidenceRecorder()
    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.interaction_runtime = runtime
    assistant.playback_generation = 7
    assistant.sessions = sessions
    assistant.conversation_state = manager
    assistant.cognitive_evidence = evidence
    session_events: list[str] = []
    assistant.session_log = (
        lambda _sid, message, *args: session_events.append(
            message % args if args else message
        )
    )
    assistant.maybe_session_done = lambda *args, **kwargs: None
    assistant._record_experience = lambda **kwargs: None
    assistant._prepared_interaction_response_for_record = (
        lambda prepared, **kwargs: prepared
    )

    planner_reentry_speech = stub.get("planner_reentry_speech")
    if isinstance(planner_reentry_speech, list):
        async def scripted_planner_reentry(self: Any, **kwargs: Any) -> InteractionResponse:
            del self
            goal_ids = [str(item) for item in kwargs.get("goal_ids") or []]
            phase = str(kwargs.get("phase") or "")
            context_updates = kwargs.get("context_updates") or {}
            truth = context_updates.get("trusted_execution_outcome")
            if not isinstance(truth, dict):
                raise AssertionError("Planner re-entry did not receive trusted execution truth")
            if [item.get("goal_id") for item in truth.get("goal_outcomes") or []] != goal_ids:
                raise AssertionError("Planner re-entry Goal truth does not match bound Goals")
            evidence = list(kwargs.get("repeat_check_evidence") or [])
            evidence_ids = [item.evidence_id for item in evidence]
            speech = []
            for index, row in enumerate(planner_reentry_speech, start=1):
                if not isinstance(row, dict):
                    raise ValueError("stub.planner_reentry_speech entries must be objects")
                goal_id = str(row.get("goal_id") or "").strip()
                text = str(row.get("text") or "").strip()
                if goal_id not in goal_ids or not text:
                    raise ValueError("Planner re-entry speech requires bound goal_id and text")
                speech.append(
                    InteractionSpeech(
                        id=f"scenario-planner-result-{index}",
                        text=text,
                        timing="immediate",
                        style=str(row.get("style") or "brief"),
                        priority="normal",
                        interruptible=True,
                        metadata={
                            "source": "scenario_planner_evidence_reentry",
                            "truth_stage": "post_evidence",
                            "covers_goal_ids": [goal_id],
                            "goal_status": str(row.get("goal_status") or ""),
                            "evidence_refs": evidence_ids,
                            "wait_for_playback_start": True,
                            "playback_start_required_for_delivery": True,
                        },
                    )
                )
            return InteractionResponse(
                interaction_id=f"planner-result-{scenario.scenario_id}",
                status="ok",
                speech=speech,
                capabilities=[],
                requires_confirmation=False,
                metadata={
                    "source": "scenario_planner_evidence_reentry",
                    "phase": phase,
                    "source_goal_ids": goal_ids,
                    "evidence_refs": evidence_ids,
                },
            )

        assistant._planner_state_reentry_response = MethodType(
            scripted_planner_reentry,
            assistant,
        )

    stop_envelope = None
    cancellation_receipt = None
    if runtime.mode == "stale_final":
        runtime.on_effectful_done = lambda: setattr(
            assistant,
            "playback_generation",
            assistant.playback_generation + 1,
        )

    async def launch_detached_result_task() -> asyncio.Task[CapabilityRuntimeResult]:
        before = set(getattr(assistant, "active_cognitive_runtime_tasks", {}))
        await assistant._dispatch_detached_interaction(
            response,
            session_id,
            confirmed_request_ids=None,
            reset_playback=False,
            mark_session_done=False,
        )
        current = getattr(assistant, "active_cognitive_runtime_tasks", {})
        created = [task for task in current if task not in before]
        if len(created) != 1:
            raise AssertionError(
                f"expected one detached result task, found {len(created)}"
            )
        return created[0]

    execution_task = await launch_detached_result_task()
    if runtime.mode == "active_cancel":
        await asyncio.wait_for(runtime.provider_started.wait(), timeout=1.0)
        stop_text = str(stub.get("stop_text") or "Stop now.")
        stop_capture = gateway.capture(
            stop_text,
            session_id=f"{session_id}-stop",
            conversation_id=envelope.conversation_id,
            channel="text",
        )
        stop_envelope = gateway.for_reflex(
            stop_capture,
            context={"active_goal_snapshots": plan.goal_ids},
        )
        assistant.playback_generation += 1
        cancellation_receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id=stop_envelope.turn_id,
                requested_scope=stop_envelope.reflex.cancellation_scope,
                foreground_interaction_id=response.interaction_id,
                reason=stop_envelope.reflex.reason,
            )
        )
    execution = await execution_task

    if len(evidence.outcomes) != 1:
        raise AssertionError(
            "cognitive turn produced "
            f"{len(evidence.outcomes)} outcome evidence records; "
            f"closure_status={response.metadata.get('cognitive_turn_closure_status')!r} "
            f"outcome_error={response.metadata.get('execution_outcome_error')!r} "
            f"execution_status={execution.status!r} events={session_events!r}"
        )
    retained = evidence.outcomes[0]
    bundle = retained["bundle"]
    final_response = retained.get("final_response")
    final_speech = list(final_response.speech) if final_response else []
    contexts = {
        str(item.get("semantic_goal", {}).get("goal_id") or ""): item
        for item in manager.snapshot()["task_contexts"]
    }
    request_step_ids = {
        request.request_id: str(request.metadata.get("step_id") or "")
        for request in response.capabilities
    }
    execution_by_request_id = {
        result.request_id: result for result in execution.results
    }

    def cancellation_step_ids(request_ids: Any) -> list[str]:
        return [
            request_step_ids.get(request_id, request_id)
            for request_id in request_ids
        ]

    actual = {
        "admission": envelope.admission,
        "original_input_preserved": (
            envelope.original_input.text == scenario.text
        ),
        "turn_identity_preserved": (
            response.metadata.get("turn_id")
            == envelope.turn_id
            == bundle.turn_id
        ),
        "runtime_status": execution.status,
        "aggregate_status": bundle.aggregate_status,
        "evidence_statuses": [
            item.status for item in bundle.evidence
        ],
        "goal_statuses": [
            item.status for item in bundle.goal_outcomes
        ],
        "observation_statuses": [
            item.observation.status if item.observation is not None else None
            for item in bundle.evidence
        ],
        "schema_gate_reasons": [
            str(item.metadata.get("output_schema_gate_reason") or "")
            for item in bundle.evidence
        ],
        "goal_state_statuses": [
            contexts[goal_id]["status"] for goal_id in plan.goal_ids
        ],
        "goal_state_outcome_statuses": [
            contexts[goal_id]["metadata"]["execution_outcome_status"]
            for goal_id in plan.goal_ids
        ],
        "closure_status": response.metadata.get(
            "cognitive_turn_closure_status"
        ),
        "delivery_status": retained.get("delivery_status"),
        "suppression_reason": retained.get("suppression_reason"),
        "final_response_absent": final_response is None,
        "final_speech_only": bool(
            final_response is not None and not final_response.capabilities
        ),
        "final_speech_count": len(final_speech),
        "final_speech_texts": [item.text for item in final_speech],
        "final_goal_statuses": [
            item.metadata.get("goal_status") for item in final_speech
        ],
        "final_capability_ids": (
            [item.capability_id for item in final_response.capabilities]
            if final_response is not None
            else []
        ),
        "runtime_call_count": len(runtime.calls),
        "stop_admission": (
            stop_envelope.admission if stop_envelope is not None else None
        ),
        "stop_reflex_action": (
            stop_envelope.reflex.action
            if stop_envelope is not None
            else None
        ),
        "stop_cancellation_scope": (
            stop_envelope.reflex.cancellation_scope
            if stop_envelope is not None
            else None
        ),
        "cancel_selected_request_ids": (
            [item.request_id for item in cancellation_receipt.selected_request_bindings]
            if cancellation_receipt is not None
            else []
        ),
        "cancel_queued_request_ids": (
            [item.request_id for item in cancellation_receipt.queued_request_bindings]
            if cancellation_receipt is not None
            else []
        ),
        "cancel_selected_step_ids": (
            cancellation_step_ids([item.request_id for item in cancellation_receipt.selected_request_bindings])
            if cancellation_receipt is not None
            else []
        ),
        "cancel_queued_step_ids": (
            cancellation_step_ids([item.request_id for item in cancellation_receipt.queued_request_bindings])
            if cancellation_receipt is not None
            else []
        ),
        "plan_reason_codes": [
            (
                execution_by_request_id[request.request_id].reason_code
                if request.request_id in execution_by_request_id
                else None
            )
            for request in response.capabilities
            if request.metadata.get("source")
            == "goal_driven_canonical_plan"
        ],
        "provider_cancelled_request_ids": list(
            runtime.cancelled_request_ids
        ),
        "provider_cancelled_step_ids": [
            next(
                (
                    str(request.metadata.get("step_id") or "")
                    for request in response.capabilities
                    if request.request_id == request_id
                ),
                request_id,
            )
            for request_id in runtime.cancelled_request_ids
        ],
    }
    errors: list[str] = []
    exact_keys = (
        "admission",
        "original_input_preserved",
        "turn_identity_preserved",
        "runtime_status",
        "aggregate_status",
        "evidence_statuses",
        "goal_statuses",
        "observation_statuses",
        "schema_gate_reasons",
        "goal_state_statuses",
        "goal_state_outcome_statuses",
        "closure_status",
        "delivery_status",
        "suppression_reason",
        "final_response_absent",
        "final_speech_only",
        "final_speech_count",
        "final_goal_statuses",
        "final_capability_ids",
        "runtime_call_count",
        "stop_admission",
        "stop_reflex_action",
        "stop_cancellation_scope",
        "cancel_selected_request_ids",
        "cancel_queued_request_ids",
        "cancel_selected_step_ids",
        "cancel_queued_step_ids",
        "plan_reason_codes",
        "provider_cancelled_request_ids",
        "provider_cancelled_step_ids",
    )
    for key in exact_keys:
        if key in scenario.expect and actual[key] != scenario.expect[key]:
            errors.append(
                f"{key}={actual[key]!r}, expected {scenario.expect[key]!r}"
            )
    final_text = "\n".join(actual["final_speech_texts"])
    for phrase in scenario.expect.get("final_speech_contains_all") or []:
        if str(phrase).casefold() not in final_text.casefold():
            errors.append(
                f"final speech missing {phrase!r}: {final_text!r}"
            )
    for phrase in scenario.expect.get("final_speech_forbid") or []:
        if str(phrase).casefold() in final_text.casefold():
            errors.append(
                f"final speech exposed forbidden text {phrase!r}: "
                f"{final_text!r}"
            )
    return {"ok": not errors, "errors": errors, "actual": actual}


async def evaluate_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    if scenario.suite == "goal_interpretation":
        return await evaluate_goal_interpretation_scenario(scenario)
    if scenario.suite == "cognitive_core_dialogue":
        return await evaluate_cognitive_core_dialogue_scenario(scenario)
    if scenario.suite == "cognitive_runtime":
        return await evaluate_cognitive_runtime_scenario(scenario)
    if scenario.suite == "cognitive_turn_loop":
        return await evaluate_cognitive_turn_loop_scenario(scenario)
    raise ValueError(f"unsupported suite {scenario.suite!r}")


async def run_scenarios(scenarios: list[BehaviorScenario]) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    cases: list[dict[str, Any]] = []
    for scenario in scenarios:
        try:
            evaluation = await evaluate_scenario(scenario)
        except Exception as exc:
            evaluation = {
                "ok": False,
                "errors": [f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"],
                "actual": {},
            }
        cases.append(
            {
                "id": scenario.scenario_id,
                "key": scenario.key,
                "suite": scenario.suite,
                "level": scenario.level,
                "description": scenario.description,
                "text": scenario.text,
                "tags": list(scenario.tags),
                "path": str(scenario.path.relative_to(ROOT)),
                "expect": scenario.expect,
                **evaluation,
            }
        )
    passed = sum(1 for case in cases if case.get("ok"))
    failed = len(cases) - passed
    return {
        "schema_version": 1,
        "ok": failed == 0,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "passed": passed,
        "failed": failed,
        "suites": sorted({case["suite"] for case in cases}),
        "cases": cases,
    }


def compare_reports(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    current_cases = {case["key"]: case for case in current.get("cases", [])}
    baseline_cases = {case["key"]: case for case in baseline.get("cases", [])}
    current_keys = set(current_cases)
    baseline_keys = set(baseline_cases)
    regressions = sorted(
        key
        for key in current_keys & baseline_keys
        if baseline_cases[key].get("ok") and not current_cases[key].get("ok")
    )
    improvements = sorted(
        key
        for key in current_keys & baseline_keys
        if not baseline_cases[key].get("ok") and current_cases[key].get("ok")
    )
    unchanged_failures = sorted(
        key
        for key in current_keys & baseline_keys
        if not baseline_cases[key].get("ok") and not current_cases[key].get("ok")
    )
    return {
        "baseline_case_count": len(baseline_cases),
        "current_case_count": len(current_cases),
        "regressions": regressions,
        "improvements": improvements,
        "unchanged_failures": unchanged_failures,
        "new_cases": sorted(current_keys - baseline_keys),
        "removed_cases": sorted(baseline_keys - current_keys),
    }


def write_report(report: dict[str, Any], *, report_dir: Path = DEFAULT_REPORT_ROOT) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = report_dir / run_id / "summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def run_scenarios_sync(scenarios: list[BehaviorScenario]) -> dict[str, Any]:
    return asyncio.run(run_scenarios(scenarios))
