#!/usr/bin/env python3
"""File-backed behavior scenario loading, execution, and reporting.

The scenarios here are Level A regression evidence: deterministic module and
dependency-light integration checks. They do not call live services, run
microphones/speakers, execute simulator motion, or ask an LLM to judge results.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch, CapabilitySearchResult
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest
from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteDecision, RouteRequest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO_ROOT = ROOT / "scenarios"
DEFAULT_REPORT_ROOT = ROOT / ".chromie" / "reports" / "behavior-scenarios"
SUPPORTED_SUITES = {"router", "interaction"}


@dataclass(frozen=True)
class BehaviorScenario:
    path: Path
    scenario_id: str
    suite: str
    level: str
    text: str
    language: str | None = None
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    stub: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)

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


def _text_contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(phrase.lower() in lower or phrase in text for phrase in phrases)


def _text_contains_all(text: str, phrases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return all(phrase.lower() in lower or phrase in text for phrase in phrases)


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
    input_payload = raw.get("input")
    if not isinstance(input_payload, dict):
        raise ValueError(f"{path}: input must be an object")
    text = str(input_payload.get("text") or "").strip()
    if not text:
        raise ValueError(f"{path}: input.text is required")
    stub = raw.get("stub") or {}
    expect = raw.get("expect") or {}
    if not isinstance(stub, dict) or not isinstance(expect, dict):
        raise ValueError(f"{path}: stub and expect must be objects")
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


def _evaluate_interaction_expectations(
    scenario: BehaviorScenario,
    *,
    speech: str,
    skill_ids: list[str],
    requires_confirmation: bool,
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
    expected_confirmation = expect.get("requires_confirmation")
    _expect_equal(errors, "requires_confirmation", requires_confirmation, expected_confirmation)
    return errors


async def evaluate_interaction_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    route_decision = scenario.stub.get("route_decision")
    if not isinstance(route_decision, dict):
        raise ValueError(f"{scenario.key}: stub.route_decision is required")
    catalog_capabilities = scenario.stub.get("catalog_capabilities")
    if catalog_capabilities is not None and not isinstance(catalog_capabilities, list):
        raise ValueError(f"{scenario.key}: stub.catalog_capabilities must be a list")
    ollama_reply = scenario.stub.get("ollama_reply")
    services = AgentServices(
        ollama=_AgentOllama(ollama_reply),  # type: ignore[arg-type]
        use_llm=ollama_reply is not None,
        max_speak_chars=int(scenario.stub.get("max_speak_chars", 160)),
        capability_catalog=_AgentCatalog(catalog_capabilities),  # type: ignore[arg-type]
        expressive_body_cues=str(scenario.stub.get("expressive_body_cues") or "off"),
    )
    response = await InteractionRuntime(services).run(
        AgentRunRequest.model_validate(
            {
                "sid": scenario.scenario_id,
                "text": scenario.text,
                "language": scenario.language,
                "route_decision": route_decision,
            }
        )
    )
    speech = _speech_text(response)
    skill_ids = [skill.skill_id for skill in response.skills]
    errors = _evaluate_interaction_expectations(
        scenario,
        speech=speech,
        skill_ids=skill_ids,
        requires_confirmation=response.requires_confirmation,
    )
    return {
        "ok": not errors,
        "errors": errors,
        "actual": {
            "speech": speech,
            "skills": skill_ids,
            "requires_confirmation": response.requires_confirmation,
            "status": response.status,
        },
    }


async def evaluate_scenario(scenario: BehaviorScenario) -> dict[str, Any]:
    if scenario.suite == "router":
        return await evaluate_router_scenario(scenario)
    if scenario.suite == "interaction":
        return await evaluate_interaction_scenario(scenario)
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
