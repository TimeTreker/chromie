#!/usr/bin/env python3
"""Run complex natural-language text scenarios against Chromie's interaction path.

The cases in this suite are meant to look like user speech after ASR. Expected
routes, skills, and speech snippets are checked after Chromie has already routed
and planned from the text; they are not prompt hints.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.interaction_text_mujoco_check import (  # noqa: E402
    parse_expected_arg,
    run_check,
)

DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "text-scenarios"
EXPRESSIVE_CUE_METADATA_SOURCE = "expressive_body_cue"


@dataclass(frozen=True)
class TextScenarioCase:
    case_id: str
    text: str
    expected_routes: tuple[str, ...] = field(default_factory=tuple)
    expected_skills: tuple[str, ...] = field(default_factory=tuple)
    expected_args: tuple[tuple[int, str, Any], ...] = field(default_factory=tuple)
    expect_no_skills: bool = False
    expected_speech_all: tuple[str, ...] = field(default_factory=tuple)
    expected_speech_any: tuple[str, ...] = field(default_factory=tuple)
    forbidden_speech_any: tuple[str, ...] = field(default_factory=tuple)
    forbidden_skills: tuple[str, ...] = field(default_factory=tuple)
    allow_expressive_cues: bool = True
    require_speech: bool = True
    description: str = ""


DEFAULT_CASES: tuple[TextScenarioCase, ...] = (
    TextScenarioCase(
        case_id="false_belief_sun_shape",
        text="I think the sun is not a round sphere, do you think so?",
        expected_routes=("chat", "deep_thought"),
        expect_no_skills=True,
        expected_speech_all=("sun",),
        expected_speech_any=("sphere", "round"),
        description="Correct a false/scientific belief without moving the body.",
    ),
    TextScenarioCase(
        case_id="compliment_self_image",
        text="You look beautiful, don't you?",
        expected_routes=("chat",),
        expect_no_skills=True,
        expected_speech_any=("thank", "appreciate", "kind", "nice"),
        description="Handle a compliment socially without treating it as a body task.",
    ),
    TextScenarioCase(
        case_id="go_ahead_joke_not_walk",
        text="Go ahead and tell me a short joke about robots.",
        expected_routes=("chat",),
        expect_no_skills=True,
        expected_speech_any=("robot", "joke", "why"),
        forbidden_skills=("soridormi.walk_velocity", "soridormi.turn_in_place"),
        description="Discourse marker 'go ahead' should not become locomotion.",
    ),
    TextScenarioCase(
        case_id="compliment_plus_eye_blink",
        text="You look beautiful. Please blink your eyes twice.",
        expected_routes=("robot_action",),
        expected_skills=("soridormi.blink_eyes",),
        expected_args=((0, "count", 2),),
        expected_speech_any=("blink", "eyes", "thank"),
        description="Mixed social speech plus one visual-expression ability.",
    ),
    TextScenarioCase(
        case_id="compound_walk_head_eye",
        text=(
            "Please walk forward at 0.20 for 10 seconds, "
            "then turn your head right and blink your eyes."
        ),
        expected_routes=("robot_action",),
        expected_skills=(
            "soridormi.walk_velocity",
            "soridormi.look_at_person",
            "soridormi.blink_eyes",
        ),
        expected_args=(
            (0, "vx_mps", 0.2),
            (0, "duration_s", 10.0),
        ),
        expected_speech_any=("walk", "head", "blink"),
        description="Compound body/head/eyes request should plan multiple skills.",
    ),
    TextScenarioCase(
        case_id="unsupported_flying_delivery",
        text="Can you fly to the moon and bring me a rock?",
        expect_no_skills=True,
        expected_speech_any=("can't", "cannot", "not able", "don't have", "sorry"),
        forbidden_skills=("soridormi.walk_velocity", "soridormi.turn_in_place"),
        description="Unsupported physical capability should be refused without motion.",
    ),
    TextScenarioCase(
        case_id="ambiguous_move_there",
        text="Can you move over there a little?",
        expect_no_skills=True,
        expected_speech_any=("where", "which", "clarify", "specific", "can't"),
        description="Ambiguous location reference should ask/decline rather than execute.",
    ),
    TextScenarioCase(
        case_id="deep_thought_memory_plan",
        text="Please think carefully and split the work to add long-term memory to Chromie.",
        expected_routes=("deep_thought",),
        expect_no_skills=True,
        expected_speech_any=("think", "plan", "memory", "split"),
        description="Complex implementation request should trigger deepthinking.",
    ),
    TextScenarioCase(
        case_id="emergency_stop",
        text="Stop moving right now.",
        expected_routes=("interrupt",),
        expect_no_skills=True,
        require_speech=False,
        description="Operational stop stays deterministic and emits no Soridormi skill.",
    ),
    TextScenarioCase(
        case_id="zh_false_belief_sun_shape",
        text="我觉得太阳不是圆球，你同意吗？",
        expected_routes=("chat",),
        expect_no_skills=True,
        expected_speech_any=("太阳", "它", "圆", "球"),
        description="Chinese false-belief discussion should stay conversational.",
    ),
)


def acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _case_from_mapping(raw: dict[str, Any]) -> TextScenarioCase:
    case_id = str(raw.get("id") or raw.get("case_id") or "").strip()
    text = str(raw.get("text") or "").strip()
    if not case_id:
        raise ValueError("text scenario case is missing id")
    if not text:
        raise ValueError(f"text scenario case {case_id!r} is missing text")
    expected_args = tuple(
        item
        if isinstance(item, tuple)
        else parse_expected_arg(str(item))
        for item in raw.get("expected_args", raw.get("expect_arg", []))
    )
    return TextScenarioCase(
        case_id=case_id,
        text=text,
        expected_routes=_tuple_of_strings(
            raw.get("expected_routes", raw.get("expected_route"))
        ),
        expected_skills=_tuple_of_strings(
            raw.get("expected_skills", raw.get("expect_skill"))
        ),
        expected_args=expected_args,
        expect_no_skills=bool(raw.get("expect_no_skills", False)),
        expected_speech_all=_tuple_of_strings(raw.get("expected_speech_all")),
        expected_speech_any=_tuple_of_strings(raw.get("expected_speech_any")),
        forbidden_speech_any=_tuple_of_strings(raw.get("forbidden_speech_any")),
        forbidden_skills=_tuple_of_strings(raw.get("forbidden_skills")),
        allow_expressive_cues=bool(raw.get("allow_expressive_cues", True)),
        require_speech=bool(raw.get("require_speech", True)),
        description=str(raw.get("description") or ""),
    )


def load_case_file(path: Path) -> list[TextScenarioCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cases")
    if not isinstance(payload, list):
        raise ValueError("case file must be a list or an object with a cases list")
    return [_case_from_mapping(item) for item in payload]


def merge_cases(
    defaults: tuple[TextScenarioCase, ...],
    extras: list[TextScenarioCase],
) -> list[TextScenarioCase]:
    merged: dict[str, TextScenarioCase] = {case.case_id: case for case in defaults}
    for case in extras:
        merged[case.case_id] = case
    return list(merged.values())


def select_cases(cases: list[TextScenarioCase], selected: list[str]) -> list[TextScenarioCase]:
    if not selected:
        return cases
    wanted = set(selected)
    out = [case for case in cases if case.case_id in wanted]
    missing = wanted - {case.case_id for case in out}
    if missing:
        raise ValueError(f"unknown scenario id: {', '.join(sorted(missing))}")
    return out


def _speech_text(summary: dict[str, Any]) -> str:
    response = summary.get("interaction_response")
    if not isinstance(response, dict):
        return ""
    speech = response.get("speech")
    if not isinstance(speech, list):
        return ""
    return "\n".join(
        str(item.get("text") or "")
        for item in speech
        if isinstance(item, dict)
    )


def _skill_items(summary: dict[str, Any]) -> list[dict[str, Any]]:
    response = summary.get("interaction_response")
    if not isinstance(response, dict):
        return []
    skills = response.get("skills")
    if not isinstance(skills, list):
        return []
    return [
        item
        for item in skills
        if isinstance(item, dict)
        and str(item.get("skill_id") or "").startswith("soridormi.")
    ]


def _skill_ids(summary: dict[str, Any]) -> list[str]:
    return [str(item.get("skill_id") or "") for item in _skill_items(summary)]


def _is_expressive_cue_skill(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata")
    return (
        isinstance(metadata, dict)
        and metadata.get("source") == EXPRESSIVE_CUE_METADATA_SOURCE
    )


def _task_skill_ids(summary: dict[str, Any], *, allow_expressive_cues: bool) -> list[str]:
    return [
        str(item.get("skill_id") or "")
        for item in _skill_items(summary)
        if not (allow_expressive_cues and _is_expressive_cue_skill(item))
    ]


def validate_scenario_result(
    case: TextScenarioCase,
    summary: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    route = summary.get("route")
    actual_route = route.get("route") if isinstance(route, dict) else None
    if case.expected_routes and actual_route not in case.expected_routes:
        errors.append(
            f"route={actual_route!r}, expected one of {list(case.expected_routes)!r}"
        )

    speech = _speech_text(summary)
    speech_lower = speech.lower()
    for phrase in case.expected_speech_all:
        if phrase.lower() not in speech_lower and phrase not in speech:
            errors.append(f"speech missing required phrase {phrase!r}")
    if case.expected_speech_any and not any(
        phrase.lower() in speech_lower or phrase in speech
        for phrase in case.expected_speech_any
    ):
        errors.append(
            "speech missing any expected phrase: "
            + ", ".join(repr(item) for item in case.expected_speech_any)
        )
    forbidden = [
        phrase
        for phrase in case.forbidden_speech_any
        if phrase.lower() in speech_lower or phrase in speech
    ]
    if forbidden:
        errors.append("speech contained forbidden phrase(s): " + ", ".join(forbidden))

    skills = set(_skill_ids(summary))
    task_skills = sorted(set(_task_skill_ids(
        summary,
        allow_expressive_cues=case.allow_expressive_cues,
    )))
    if case.expect_no_skills and task_skills:
        errors.append("interaction emitted Soridormi task skills, expected none: " + ", ".join(task_skills))
    bad_skills = sorted(skills & set(case.forbidden_skills))
    if bad_skills:
        errors.append("forbidden skills emitted: " + ", ".join(bad_skills))
    return errors


def _case_namespace(
    args: argparse.Namespace,
    case: TextScenarioCase,
    evidence_dir: Path,
) -> argparse.Namespace:
    expected_route = case.expected_routes[0] if len(case.expected_routes) == 1 else None
    return argparse.Namespace(
        text=case.text,
        router_url=args.router_url,
        agent_url=args.agent_url,
        soridormi_mcp_url=args.soridormi_mcp_url,
        manifest=args.manifest,
        language=args.language,
        evidence_dir=str(evidence_dir),
        speaker=args.speaker,
        preview_only=not args.execute,
        allow_non_sim=args.allow_non_sim,
        auto_confirm_sim=args.auto_confirm_sim,
        require_speech=case.require_speech,
        expect_route=expected_route,
        expect_no_skills=case.expect_no_skills and not case.allow_expressive_cues,
        expect_skill=list(case.expected_skills),
        expect_arg=list(case.expected_args),
        arg_tolerance=args.arg_tolerance,
        timeout_s=args.timeout_s,
        skill_timeout_s=args.skill_timeout_s,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    evidence_root = Path(args.evidence_dir or DEFAULT_EVIDENCE_ROOT / acceptance_id())
    evidence_root = evidence_root.expanduser().resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)

    extra_cases: list[TextScenarioCase] = []
    for path in args.case_file:
        extra_cases.extend(load_case_file(Path(path)))
    cases = select_cases(merge_cases(DEFAULT_CASES, extra_cases), args.only)

    case_summaries: list[dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        case_dir = evidence_root / f"{index:02d}-{case.case_id}"
        try:
            result = await run_check(_case_namespace(args, case, case_dir))
            scenario_errors = validate_scenario_result(case, result)
            if scenario_errors:
                result["errors"] = list(result.get("errors") or []) + scenario_errors
                result["ok"] = False
        except Exception as exc:
            result = {
                "ok": False,
                "case_id": case.case_id,
                "text": case.text,
                "evidence_dir": str(case_dir),
                "errors": [f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"],
            }
        result["case_id"] = case.case_id
        result["description"] = case.description
        result["expected_routes"] = list(case.expected_routes)
        result["expected_skills"] = list(case.expected_skills)
        result["expected_speech_all"] = list(case.expected_speech_all)
        result["expected_speech_any"] = list(case.expected_speech_any)
        _write_json(case_dir / "summary.json", result)
        case_summaries.append(result)

    errors = [
        f"case {item['case_id']} failed: {item.get('errors')}"
        for item in case_summaries
        if not item.get("ok")
    ]
    summary = {
        "ok": not errors,
        "execute": args.execute,
        "speaker": args.speaker,
        "case_count": len(case_summaries),
        "passed": sum(1 for item in case_summaries if item.get("ok")),
        "failed": sum(1 for item in case_summaries if not item.get("ok")),
        "evidence_dir": str(evidence_root),
        "errors": errors,
        "cases": case_summaries,
    }
    _write_json(evidence_root / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run complex natural-language Router/Agent text scenarios. "
            "Defaults are preview-only and headless."
        )
    )
    parser.add_argument("--router-url", default=os.getenv("ROUTER_URL", "http://127.0.0.1:8091"))
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "capabilities" / "soridormi.json")
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--case-file", action="append", default=[], help="JSON case file to add or override scenarios.")
    parser.add_argument("--only", action="append", default=[], help="Run one scenario id. Repeatable.")
    parser.add_argument("--execute", action="store_true", help="Execute emitted skills through Soridormi/MuJoCo. Default is preview-only.")
    parser.add_argument("--speaker", action="store_true", help="Play TTS during runs. Default is headless.")
    parser.add_argument("--allow-non-sim", action="store_true", help="Permit non-sim Soridormi modes. Use only under supervision.")
    parser.add_argument("--auto-confirm-sim", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--arg-tolerance", type=float, default=1e-6)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    parser.add_argument("--skill-timeout-s", type=float, default=120.0)
    parser.add_argument("--list-cases", action="store_true", help="Print built-in scenarios and exit.")
    return parser


def _case_json(case: TextScenarioCase) -> dict[str, Any]:
    return {
        "id": case.case_id,
        "text": case.text,
        "expected_routes": list(case.expected_routes),
        "expected_skills": list(case.expected_skills),
        "expected_args": [
            f"{index}:{key}={json.dumps(value, ensure_ascii=False)}"
            for index, key, value in case.expected_args
        ],
        "expect_no_skills": case.expect_no_skills,
        "expected_speech_all": list(case.expected_speech_all),
        "expected_speech_any": list(case.expected_speech_any),
        "forbidden_skills": list(case.forbidden_skills),
        "allow_expressive_cues": case.allow_expressive_cues,
        "require_speech": case.require_speech,
        "description": case.description,
    }


def main() -> int:
    args = build_parser().parse_args()
    if args.list_cases:
        print(
            json.dumps(
                [_case_json(case) for case in DEFAULT_CASES],
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    try:
        summary = asyncio.run(run_suite(args))
    except Exception as exc:
        print(f"[interaction-text-scenario-suite][error] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
