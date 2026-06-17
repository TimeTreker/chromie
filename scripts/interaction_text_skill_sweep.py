#!/usr/bin/env python3
"""Sweep text-input interaction cases across Soridormi named skills.

This runner feeds natural-language text cases into the deployed Router and
Agent `/interaction` contract. By default it runs in preview mode: it validates
that text routes to the expected Soridormi skill requests without executing the
skills. Use `--execute` only against a supervised simulator endpoint.
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

DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "text-skill-sweep"


@dataclass(frozen=True)
class TextSkillCase:
    case_id: str
    text: str
    expected_skills: tuple[str, ...]
    expected_args: tuple[tuple[int, str, Any], ...] = field(default_factory=tuple)
    description: str = ""

    @property
    def covered_skills(self) -> set[str]:
        return set(self.expected_skills)


DEFAULT_CASES: tuple[TextSkillCase, ...] = (
    TextSkillCase(
        case_id="walk_velocity",
        text="walk ahead at 0.1 speed for 2 seconds",
        expected_skills=("soridormi.walk_velocity",),
        expected_args=(
            (0, "vx_mps", 0.1),
            (0, "duration_s", 2.0),
            (0, "yaw_radps", 0.0),
        ),
        description="Bounded forward velocity command.",
    ),
    TextSkillCase(
        case_id="walk_backward_velocity",
        text="walk backward at 0.03 speed for 1 second",
        expected_skills=("soridormi.walk_velocity",),
        expected_args=((0, "vx_mps", -0.03), (0, "duration_s", 1.0)),
        description="Backward text lowers to walk_velocity.",
    ),
    TextSkillCase(
        case_id="curve_walk",
        text="walk in a curve to the left at 0.08 speed for 2 seconds",
        expected_skills=("soridormi.curve_walk",),
        expected_args=(
            (0, "vx_mps", 0.08),
            (0, "yaw_radps", -0.1),
            (0, "duration_s", 2.0),
        ),
        description="Curved walk semantic route.",
    ),
    TextSkillCase(
        case_id="turn_in_place_left",
        text="turn left for 2 seconds",
        expected_skills=("soridormi.turn_in_place",),
        expected_args=((0, "yaw_radps", -0.12), (0, "duration_s", 2.0)),
        description="Left turn in place.",
    ),
    TextSkillCase(
        case_id="turn_in_place_right",
        text="turn right for 2 seconds",
        expected_skills=("soridormi.turn_in_place",),
        expected_args=((0, "yaw_radps", 0.12), (0, "duration_s", 2.0)),
        description="Right turn in place.",
    ),
    TextSkillCase(
        case_id="nod_yes",
        text="nod your head twice",
        expected_skills=("soridormi.nod_yes",),
        expected_args=(
            (0, "count", 2),
            (0, "amplitude", "small"),
            (0, "duration_s", 1.4),
        ),
        description="Scripted yes nod.",
    ),
    TextSkillCase(
        case_id="shake_no",
        text="shake your head twice",
        expected_skills=("soridormi.shake_no",),
        expected_args=(
            (0, "count", 2),
            (0, "amplitude", "small"),
            (0, "duration_s", 1.4),
        ),
        description="Scripted no shake.",
    ),
    TextSkillCase(
        case_id="neutral_head",
        text="return your head to neutral",
        expected_skills=("soridormi.neutral_head",),
        description="Neutral head pose via catalog/Agent selection.",
    ),
    TextSkillCase(
        case_id="look_direction",
        text="look left",
        expected_skills=("soridormi.look_direction",),
        description="Head look direction via catalog/Agent selection.",
    ),
    TextSkillCase(
        case_id="look_at_person",
        text="look at the person in front of you",
        expected_skills=("soridormi.look_at_person",),
        description="Look toward a person target.",
    ),
    TextSkillCase(
        case_id="bow",
        text="bow your head once",
        expected_skills=("soridormi.bow",),
        description="Head/neck-only bow.",
    ),
    TextSkillCase(
        case_id="express_attention",
        text="show an attentive listening gesture",
        expected_skills=("soridormi.express_attention",),
        description="Subtle scripted attention gesture.",
    ),
)


def acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _case_from_mapping(raw: dict[str, Any]) -> TextSkillCase:
    case_id = str(raw.get("id") or raw.get("case_id") or "").strip()
    text = str(raw.get("text") or "").strip()
    expected_skills = tuple(
        str(item).strip()
        for item in raw.get("expected_skills", raw.get("expect_skill", []))
        if str(item).strip()
    )
    expected_args = tuple(
        item
        if isinstance(item, tuple)
        else parse_expected_arg(str(item))
        for item in raw.get("expected_args", raw.get("expect_arg", []))
    )
    if not case_id:
        raise ValueError("skill sweep case is missing id")
    if not text:
        raise ValueError(f"skill sweep case {case_id!r} is missing text")
    if not expected_skills:
        raise ValueError(f"skill sweep case {case_id!r} has no expected_skills")
    return TextSkillCase(
        case_id=case_id,
        text=text,
        expected_skills=expected_skills,
        expected_args=expected_args,
        description=str(raw.get("description") or ""),
    )


def load_case_file(path: Path) -> list[TextSkillCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cases")
    if not isinstance(payload, list):
        raise ValueError("case file must be a list or an object with a cases list")
    return [_case_from_mapping(item) for item in payload]


def merge_cases(
    defaults: tuple[TextSkillCase, ...],
    extras: list[TextSkillCase],
) -> list[TextSkillCase]:
    merged: dict[str, TextSkillCase] = {case.case_id: case for case in defaults}
    for case in extras:
        merged[case.case_id] = case
    return list(merged.values())


def select_cases(cases: list[TextSkillCase], selected: list[str]) -> list[TextSkillCase]:
    if not selected:
        return cases
    wanted = set(selected)
    out = [
        case
        for case in cases
        if case.case_id in wanted or any(skill in wanted for skill in case.expected_skills)
    ]
    missing = wanted - {case.case_id for case in out} - {
        skill for case in out for skill in case.expected_skills
    }
    if missing:
        raise ValueError(f"unknown case id or skill id: {', '.join(sorted(missing))}")
    return out


async def live_soridormi_skills(
    *,
    manifest: Path,
    soridormi_mcp_url: str,
) -> tuple[set[str], dict[str, Any]]:
    os.environ["SORIDORMI_MCP_URL"] = soridormi_mcp_url
    from agent.app.capabilities.loader import build_configured_registry  # noqa: PLC0415
    from agent.app.tool_invocation import McpStreamableHttpInvoker  # noqa: PLC0415

    configured = build_configured_registry([str(manifest)])
    invoker = McpStreamableHttpInvoker(configured.registry)
    outcome = await invoker.invoke("soridormi.skill.list", {})
    if outcome.status != "success":
        raise RuntimeError(outcome.error or f"skill.list returned {outcome.status}")
    skills = outcome.output.get("skills")
    if not isinstance(skills, list):
        raise RuntimeError("skill.list returned no skills list")
    ids = {
        f"soridormi.{item['skill_id']}"
        for item in skills
        if isinstance(item, dict)
        and item.get("skill_id")
        and item.get("available", True) is not False
    }
    return ids, outcome.output


def uncovered_live_skills(
    cases: list[TextSkillCase],
    live_skill_ids: set[str],
) -> list[str]:
    covered = {skill for case in cases for skill in case.covered_skills}
    return sorted(live_skill_ids - covered)


def _case_namespace(
    args: argparse.Namespace,
    case: TextSkillCase,
    evidence_dir: Path,
) -> argparse.Namespace:
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
        require_speech=args.require_speech,
        expect_skill=list(case.expected_skills),
        expect_arg=list(case.expected_args),
        arg_tolerance=args.arg_tolerance,
        timeout_s=args.timeout_s,
        skill_timeout_s=args.skill_timeout_s,
    )


async def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    evidence_root = Path(args.evidence_dir or DEFAULT_EVIDENCE_ROOT / acceptance_id())
    evidence_root = evidence_root.expanduser().resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)

    extra_cases: list[TextSkillCase] = []
    for path in args.case_file:
        extra_cases.extend(load_case_file(Path(path)))
    cases = select_cases(merge_cases(DEFAULT_CASES, extra_cases), args.only)

    live_skill_ids: set[str] = set()
    live_catalog: dict[str, Any] | None = None
    live_inventory_error: str | None = None
    if not args.skip_live_inventory:
        try:
            live_skill_ids, live_catalog = await live_soridormi_skills(
                manifest=args.manifest,
                soridormi_mcp_url=args.soridormi_mcp_url,
            )
        except Exception as exc:
            live_inventory_error = f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"
            if args.require_live_inventory:
                raise

    case_summaries: list[dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        unavailable = sorted(set(case.expected_skills) - live_skill_ids) if live_skill_ids else []
        case_dir = evidence_root / f"{index:02d}-{case.case_id}"
        if unavailable and not args.run_unavailable:
            summary = {
                "ok": True,
                "skipped": True,
                "case_id": case.case_id,
                "text": case.text,
                "expected_skills": list(case.expected_skills),
                "unavailable_expected_skills": unavailable,
                "evidence_dir": str(case_dir),
            }
            case_summaries.append(summary)
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            continue

        case_args = _case_namespace(args, case, case_dir)
        try:
            result = await run_check(case_args)
        except Exception as exc:
            result = {
                "ok": False,
                "case_id": case.case_id,
                "text": case.text,
                "expected_skills": list(case.expected_skills),
                "evidence_dir": str(case_dir),
                "errors": [f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"],
            }
        result["case_id"] = case.case_id
        result["expected_skills"] = list(case.expected_skills)
        result["description"] = case.description
        case_summaries.append(result)

    untested = uncovered_live_skills(cases, live_skill_ids) if live_skill_ids else []
    errors = [
        f"case {item['case_id']} failed: {item.get('errors')}"
        for item in case_summaries
        if not item.get("ok")
    ]
    if live_inventory_error:
        errors.append(f"live inventory failed: {live_inventory_error}")
    if args.require_all_live and untested:
        errors.append(
            "live skills without text cases: " + ", ".join(untested)
        )

    summary = {
        "ok": not errors,
        "execute": args.execute,
        "speaker": args.speaker,
        "case_count": len(case_summaries),
        "passed": sum(1 for item in case_summaries if item.get("ok") and not item.get("skipped")),
        "skipped": sum(1 for item in case_summaries if item.get("skipped")),
        "failed": sum(1 for item in case_summaries if not item.get("ok")),
        "evidence_dir": str(evidence_root),
        "errors": errors,
        "live_inventory_error": live_inventory_error,
        "live_skill_ids": sorted(live_skill_ids),
        "untested_live_skill_ids": untested,
        "live_catalog_mode": (live_catalog or {}).get("mode") if live_catalog else None,
        "cases": case_summaries,
    }
    (evidence_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run text-input Router/Agent/Skill Runtime checks across Soridormi "
            "named-skill text cases."
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
    parser.add_argument("--case-file", action="append", default=[], help="JSON case file to add or override text cases.")
    parser.add_argument("--only", action="append", default=[], help="Run one case id or expected skill id. Repeatable.")
    parser.add_argument("--execute", action="store_true", help="Execute skills through Soridormi/MuJoCo. Default is preview-only.")
    parser.add_argument("--speaker", action="store_true", help="Play TTS during --execute runs. Default is headless.")
    parser.add_argument("--allow-non-sim", action="store_true", help="Permit non-sim Soridormi modes. Use only under supervision.")
    parser.add_argument("--auto-confirm-sim", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-speech", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--arg-tolerance", type=float, default=1e-6)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    parser.add_argument("--skill-timeout-s", type=float, default=120.0)
    parser.add_argument("--skip-live-inventory", action="store_true")
    parser.add_argument("--require-live-inventory", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-all-live", action="store_true", help="Fail if a live available skill has no text case.")
    parser.add_argument("--run-unavailable", action="store_true", help="Run cases even when live inventory does not list the expected skill.")
    parser.add_argument("--list-cases", action="store_true", help="Print built-in/default cases and exit.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.list_cases:
        print(
            json.dumps(
                [
                    {
                        "id": case.case_id,
                        "text": case.text,
                        "expected_skills": list(case.expected_skills),
                        "expected_args": [
                            f"{index}:{key}={json.dumps(value, ensure_ascii=False)}"
                            for index, key, value in case.expected_args
                        ],
                        "description": case.description,
                    }
                    for case in DEFAULT_CASES
                ],
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    try:
        summary = asyncio.run(run_sweep(args))
    except Exception as exc:
        print(f"[interaction-text-skill-sweep][error] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
