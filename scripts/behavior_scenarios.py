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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch, CapabilitySearchResult
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteDecision, RouteRequest

DEFAULT_SCENARIO_ROOT = ROOT / "scenarios"
DEFAULT_REPORT_ROOT = ROOT / ".chromie" / "reports" / "behavior-scenarios"
SUPPORTED_SUITES = {"router", "interaction", "dialogue"}


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


class _RouterCatalog:
    def __init__(self, result: CapabilityCatalogResult) -> None:
        self.result = result

    async def search(self, **kwargs: Any) -> CapabilityCatalogResult:
        del kwargs
        return self.result


class _RouterLlm:
    def __init__(self, decision: RouteDecision | None) -> None:
        self.decision = decision
        self.calls = 0

    async def route(self, request: RouteRequest) -> RouteDecision:
        self.calls += 1
        if self.decision is None:
            raise AssertionError(f"LLM router should not be called for {request.text!r}")
        return self.decision


class _AgentCatalog:
    def __init__(self, capabilities: list[dict[str, Any]] | None = None) -> None:
        self.capabilities = capabilities or [
            {
                "capability_id": "soridormi.walk_velocity",
                "description": "Bounded walking velocity.",
                "score": 0.92,
            },
            {
                "capability_id": "soridormi.nod_yes",
                "description": "Visible nod yes.",
                "score": 0.85,
            },
            {
                "capability_id": "soridormi.blink_eyes",
                "description": "Blink robot eyes.",
                "score": 0.78,
            },
        ]

    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=bool(self.capabilities),
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=42,
            matches=[
                CapabilityMatch(
                    capability_id=str(item.get("capability_id") or ""),
                    agent_id=str(item.get("agent_id") or "soridormi.skill"),
                    description=str(item.get("description") or ""),
                    input_schema=dict(item.get("input_schema") or {}),
                    effects=list(item.get("effects") or ["physical_motion"]),
                    safety_class=str(item.get("safety_class") or "physical_motion"),
                    interaction_executable=bool(item.get("interaction_executable", True)),
                    requires_confirmation=bool(item.get("requires_confirmation", True)),
                    route=str(item.get("route") or "robot_action"),
                    score=float(item.get("score", 0.9)),
                    metadata=dict(item.get("metadata") or {"mode": "sim"}),
                )
                for item in self.capabilities
                if item.get("capability_id")
            ],
        )


class _AgentOllama:
    def __init__(self, reply: str | dict[str, Any] | None) -> None:
        self.reply = reply

    async def generate(self, prompt: str, **kwargs: Any) -> str | dict[str, Any]:
        del prompt, kwargs
        if self.reply is None:
            raise AssertionError("LLM should not be called for this interaction scenario")
        return self.reply


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


def _validate_dialogue_turns(raw_turns: Any, *, path: Path, scenario_id: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ValueError(f"{path}: dialogue scenarios require a non-empty turns list")
    turns: list[dict[str, Any]] = []
    scenario_key = f"dialogue/{scenario_id}"
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

    if suite == "dialogue":
        turns = _validate_dialogue_turns(raw.get("turns"), path=path, scenario_id=scenario_id)
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


def _router_catalog_from_stub(scenario: BehaviorScenario) -> CapabilityCatalogResult:
    catalog = scenario.stub.get("catalog") or {}
    if not isinstance(catalog, dict):
        raise ValueError(f"{scenario.key}: stub.catalog must be an object")
    capabilities = catalog.get("capabilities") or []
    matches = [
        {
            "capability_id": str(item.get("capability_id") or ""),
            "agent_id": str(item.get("agent_id") or "soridormi.skill"),
            "description": str(item.get("description") or ""),
            "score": float(item.get("score", 0.9)),
            "available": bool(item.get("available", True)),
            "interaction_executable": bool(item.get("interaction_executable", True)),
        }
        for item in capabilities
        if isinstance(item, dict) and item.get("capability_id")
    ]
    return CapabilityCatalogResult(
        query=str(catalog.get("query") or scenario.text),
        matched=bool(catalog.get("matched", bool(matches))),
        suggested_route=str(catalog.get("suggested_route") or "robot_action"),
        suggested_agents=list(catalog.get("suggested_agents") or ["capability_agent", "safety_agent", "speaker_agent"]),
        catalog_version=int(catalog.get("catalog_version", 0)),
        matches=matches,
    )


def _router_decision_from_stub(scenario: BehaviorScenario) -> RouteDecision | None:
    raw = scenario.stub.get("llm_decision")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{scenario.key}: stub.llm_decision must be an object or null")
    return RouteDecision.model_validate(raw)


def _task_types_from_decision(decision: RouteDecision) -> list[str]:
    return [
        str(item.get("task_type") or "")
        for item in decision.metadata.get("task_list", [])
        if isinstance(item, dict)
    ]


def _expect_equal(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if expected is not None and actual != expected:
        errors.append(f"{label}={actual!r}, expected {expected!r}")


def _evaluate_router_expectations(
    scenario: BehaviorScenario,
    *,
    decision: RouteDecision,
    llm_calls: int,
) -> list[str]:
    expect = scenario.expect
    errors: list[str] = []
    _expect_equal(errors, "route", decision.route, expect.get("route"))
    _expect_equal(errors, "intent", decision.intent, expect.get("intent"))
    _expect_equal(errors, "source", decision.source, expect.get("source"))
    _expect_equal(errors, "llm_calls", llm_calls, expect.get("llm_calls"))
    _expect_equal(errors, "interrupt_current", decision.interrupt_current, expect.get("interrupt_current"))
    _expect_equal(errors, "should_speak", decision.should_speak, expect.get("should_speak"))

    task_types = _task_types_from_decision(decision)
    for item in _tuple_of_strings(expect.get("task_types_include")):
        if item not in task_types:
            errors.append(f"missing task_type {item!r}; actual={task_types!r}")
    for item in _tuple_of_strings(expect.get("task_types_forbid")):
        if item in task_types:
            errors.append(f"forbidden task_type {item!r} present")
    for key in _tuple_of_strings(expect.get("metadata_false")):
        if decision.metadata.get(key) is not False:
            errors.append(f"metadata {key!r}={decision.metadata.get(key)!r}, expected False")
    for key in _tuple_of_strings(expect.get("metadata_true")):
        if decision.metadata.get(key) is not True:
            errors.append(f"metadata {key!r}={decision.metadata.get(key)!r}, expected True")
    metadata_json = json.dumps(decision.metadata, ensure_ascii=False, sort_keys=True, default=str)
    for phrase in _tuple_of_strings(expect.get("metadata_json_contains")):
        if phrase not in metadata_json:
            errors.append(f"metadata JSON missing phrase {phrase!r}: {metadata_json!r}")
    for phrase in _tuple_of_strings(expect.get("metadata_json_forbid")):
        if phrase in metadata_json:
            errors.append(f"metadata JSON contained forbidden phrase {phrase!r}")
    return errors


async def evaluate_router_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    from router.app import main

    llm = _RouterLlm(_router_decision_from_stub(scenario))
    mode = str(scenario.stub.get("router_mode") or "hybrid")
    with patch.object(main.settings, "mode", mode), patch.object(
        main,
        "capability_catalog",
        _RouterCatalog(_router_catalog_from_stub(scenario)),
    ), patch.object(main, "llm_router", llm):
        decision = await main.route(
            RouteRequest(text=scenario.text, language=scenario.language)
        )

    task_types = _task_types_from_decision(decision)
    errors = _evaluate_router_expectations(
        scenario,
        decision=decision,
        llm_calls=llm.calls,
    )
    return {
        "ok": not errors,
        "errors": errors,
        "actual": {
            "route": decision.route,
            "intent": decision.intent,
            "source": decision.source,
            "confidence": decision.confidence,
            "interrupt_current": decision.interrupt_current,
            "should_speak": decision.should_speak,
            "llm_calls": llm.calls,
            "task_types": task_types,
            "metadata": decision.metadata,
        },
    }


def _speech_text(response: Any) -> str:
    return "\n".join(item.text for item in response.speech)


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


def _evaluate_interaction_expectations(
    scenario: BehaviorScenario,
    *,
    speech: str,
    skill_ids: list[str],
    skill_args: list[dict[str, Any]],
    requires_confirmation: bool,
    status: str,
    metadata: dict[str, Any],
) -> list[str]:
    expect = scenario.expect
    errors: list[str] = []
    speech_all = _tuple_of_strings(expect.get("speech_all"))
    speech_any = _tuple_of_strings(expect.get("speech_any"))
    speech_forbid = _tuple_of_strings(expect.get("forbidden_speech_any"))
    if speech_all and not _text_contains_all(speech, speech_all):
        errors.append(f"speech missing required phrases {list(speech_all)!r}: {speech!r}")
    if speech_any and not _text_contains_any(speech, speech_any):
        errors.append(f"speech missing any expected phrase {list(speech_any)!r}: {speech!r}")
    forbidden = [
        phrase for phrase in speech_forbid if _text_contains_any(speech, (phrase,))
    ]
    if forbidden:
        errors.append(f"speech contained forbidden phrases {forbidden!r}: {speech!r}")

    expected_skills = _tuple_of_strings(expect.get("skills"))
    if bool(expect.get("no_skills", False)) and skill_ids:
        errors.append(f"skills={skill_ids!r}, expected none")
    if expected_skills and skill_ids != list(expected_skills):
        errors.append(f"skills={skill_ids!r}, expected {list(expected_skills)!r}")
    for skill_id in _tuple_of_strings(expect.get("forbidden_skills")):
        if skill_id in skill_ids:
            errors.append(f"forbidden skill {skill_id!r} emitted")
    expected_skill_args = expect.get("skill_args")
    if expected_skill_args is not None and skill_args != expected_skill_args:
        errors.append(f"skill_args={skill_args!r}, expected {expected_skill_args!r}")
    expected_confirmation = expect.get("requires_confirmation")
    _expect_equal(errors, "requires_confirmation", requires_confirmation, expected_confirmation)
    _expect_equal(errors, "status", status, expect.get("status"))
    for key in _tuple_of_strings(expect.get("metadata_true")):
        if metadata.get(key) is not True:
            errors.append(f"metadata {key!r}={metadata.get(key)!r}, expected True")
    for key in _tuple_of_strings(expect.get("metadata_false")):
        if metadata.get(key) is not False:
            errors.append(f"metadata {key!r}={metadata.get(key)!r}, expected False")
    metadata_json = _json_text(metadata)
    for phrase in _tuple_of_strings(expect.get("metadata_json_contains")):
        if phrase not in metadata_json:
            errors.append(f"metadata JSON missing phrase {phrase!r}: {metadata_json!r}")
    for phrase in _tuple_of_strings(expect.get("metadata_json_forbid")):
        if phrase in metadata_json:
            errors.append(f"metadata JSON contained forbidden phrase {phrase!r}: {metadata_json!r}")
    return errors


def _route_proposal_metadata_for_response(decision: RouteDecision) -> dict[str, Any]:
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    out: dict[str, Any] = {
        "route_final": decision.route,
        "route_intent": decision.intent,
        "route_source": decision.source,
        "route_confidence": decision.confidence,
    }
    route_stage_outputs = metadata.get("route_stage_outputs")
    if isinstance(route_stage_outputs, list):
        out["route_stage_outputs"] = route_stage_outputs
    task_proposals = metadata.get("task_proposals")
    if isinstance(task_proposals, list):
        out["route_task_proposals"] = task_proposals
    task_list = metadata.get("task_list")
    if isinstance(task_list, list):
        out["route_task_list"] = task_list
    route_merge = metadata.get("route_merge")
    if isinstance(route_merge, dict):
        out["route_merge"] = route_merge
    superseded = metadata.get("superseded_task_proposals")
    if isinstance(superseded, list):
        out["superseded_task_proposals"] = superseded
    revised = metadata.get("revised_task_proposals")
    if isinstance(revised, list):
        out["revised_task_proposals"] = revised
    revisions = metadata.get("task_proposal_revisions")
    if isinstance(revisions, list):
        out["task_proposal_revisions"] = revisions
    if metadata.get("truth_reconciled") is True:
        out["truth_reconciled"] = True
    truth_reason = metadata.get("truth_reconciliation_reason")
    if isinstance(truth_reason, str) and truth_reason.strip():
        out["truth_reconciliation_reason"] = truth_reason.strip()
    return out


async def _run_interaction_turn(
    *,
    scenario_key: str,
    scenario_id: str,
    text: str,
    language: str | None,
    stub: dict[str, Any],
    context: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> Any:
    route_decision = stub.get("route_decision")
    if not isinstance(route_decision, dict):
        raise ValueError(f"{scenario_key}: stub.route_decision is required")
    catalog_capabilities = stub.get("catalog_capabilities")
    if catalog_capabilities is not None and not isinstance(catalog_capabilities, list):
        raise ValueError(f"{scenario_key}: stub.catalog_capabilities must be a list")
    ollama_reply = stub.get("ollama_reply")
    reviewer_reply = stub.get("reviewer_reply")
    services = AgentServices(
        ollama=_AgentOllama(ollama_reply),  # type: ignore[arg-type]
        response_reviewer=(
            _AgentOllama(reviewer_reply) if reviewer_reply is not None else None
        ),  # type: ignore[arg-type]
        use_llm=ollama_reply is not None,
        max_speak_chars=int(stub.get("max_speak_chars", 160)),
        capability_catalog=_AgentCatalog(catalog_capabilities),  # type: ignore[arg-type]
        expressive_body_cues=str(stub.get("expressive_body_cues") or "off"),
        require_capability_plan_review=bool(stub.get("require_capability_plan_review", False)),
    )
    request = AgentRunRequest.model_validate(
        {
            "sid": scenario_id,
            "text": text,
            "language": language,
            "route_decision": route_decision,
            "context": context or {},
            "history": history or [],
        }
    )
    response = await InteractionRuntime(services).run(request)
    if bool(stub.get("host_prepare_response", False)):
        response = response.model_copy(
            deep=True,
            update={
                "metadata": {
                    **response.metadata,
                    **_route_proposal_metadata_for_response(request.route_decision),
                }
            },
        )
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"status": "scheduled"})
        response = coordinator.prepare_response(response, session_id=scenario_id)
    return response


def _interaction_actual(response: Any) -> dict[str, Any]:
    speech = _speech_text(response)
    skill_ids = [skill.skill_id for skill in response.skills]
    skill_args = [skill.args for skill in response.skills]
    return {
        "speech": speech,
        "skills": skill_ids,
        "skill_args": skill_args,
        "requires_confirmation": response.requires_confirmation,
        "status": response.status,
        "metadata": response.metadata,
    }


async def evaluate_interaction_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    response = await _run_interaction_turn(
        scenario_key=scenario.key,
        scenario_id=scenario.scenario_id,
        text=scenario.text,
        language=scenario.language,
        stub=scenario.stub,
    )
    speech = _speech_text(response)
    skill_ids = [skill.skill_id for skill in response.skills]
    skill_args = [skill.args for skill in response.skills]
    errors = _evaluate_interaction_expectations(
        scenario,
        speech=speech,
        skill_ids=skill_ids,
        skill_args=skill_args,
        requires_confirmation=response.requires_confirmation,
        status=response.status,
        metadata=response.metadata,
    )
    return {
        "ok": not errors,
        "errors": errors,
        "actual": _interaction_actual(response),
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
    task_contains = _tuple_of_strings(expect.get("current_task_context_contains"))
    if task_contains and not _text_contains_all(current_task_text, task_contains):
        errors.append(
            f"current task context missing phrases {list(task_contains)!r}: {current_task_text!r}"
        )


def _route_metadata_for_state(route_decision: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(route_decision.get("metadata") or {})
    if route_decision.get("source") is not None:
        metadata.setdefault("source", route_decision.get("source"))
    if route_decision.get("confidence") is not None:
        metadata.setdefault("confidence", route_decision.get("confidence"))
    return metadata


async def evaluate_dialogue_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
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
        turn_key = f"{scenario.key}#{turn_id}"
        text = _turn_text(turn, scenario_key=scenario.key, index=index)
        language = _turn_language(turn, scenario.language)
        manager.prepare_for_user_text(text, sid=turn_id)
        pre_snapshot = manager.snapshot()
        pre_context_report = _context_report(pre_snapshot)
        stub = _merged_turn_stub(scenario, turn)
        response = await _run_interaction_turn(
            scenario_key=turn_key,
            scenario_id=f"{scenario.scenario_id}:{turn_id}",
            text=text,
            language=language,
            stub=stub,
            context=_turn_context(scenario, turn, pre_snapshot),
            history=manager.get_history(),
        )
        actual = _interaction_actual(response)
        route_decision = stub["route_decision"]
        route_metadata = _route_metadata_for_state(route_decision)
        manager.record_user_turn(
            turn_id,
            text,
            route=str(route_decision.get("route") or ""),
            intent=str(route_decision.get("intent") or ""),
            metadata=route_metadata,
        )
        manager.record_agent_result(turn_id, response)
        post_snapshot = manager.snapshot()
        post_context_report = _context_report(post_snapshot)

        expect = turn.get("expect") or {}
        errors: list[str] = []
        # Use the turn-local expectations for dialogue-specific checks and for
        # any interaction assertions that differ from the scenario default.
        if isinstance(expect, dict):
            turn_scenario = BehaviorScenario(
                path=scenario.path,
                scenario_id=f"{scenario.scenario_id}:{turn_id}",
                suite="interaction",
                level=scenario.level,
                text=text,
                language=language,
                expect=expect,
            )
            errors = _evaluate_interaction_expectations(
                turn_scenario,
                speech=actual["speech"],
                skill_ids=actual["skills"],
                skill_args=actual["skill_args"],
                requires_confirmation=actual["requires_confirmation"],
                status=actual["status"],
                metadata=actual["metadata"],
            )
            _evaluate_context_expectations(
                errors,
                expect,
                pre_snapshot=pre_context_report,
                post_snapshot=post_context_report,
            )
        if errors:
            all_errors.extend(f"{turn_id}: {error}" for error in errors)
        turn_reports.append(
            {
                "id": turn_id,
                "ask": text,
                "ok": not errors,
                "errors": errors,
                "actual": actual,
                "pre_context": pre_context_report,
                "post_context": post_context_report,
            }
        )

    return {
        "ok": not all_errors,
        "errors": all_errors,
        "actual": {
            "turn_count": len(turn_reports),
            "turns": turn_reports,
        },
    }


async def evaluate_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    if scenario.suite == "router":
        return await evaluate_router_scenario(scenario)
    if scenario.suite == "interaction":
        return await evaluate_interaction_scenario(scenario)
    if scenario.suite == "dialogue":
        return await evaluate_dialogue_scenario(scenario)
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
