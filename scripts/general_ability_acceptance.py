#!/usr/bin/env python3
"""Run claim-oriented general ability acceptance checks.

The manifest behind this runner groups representative scenarios by the general
robot ability they protect. A passing run is evidence for the selected claim
scope only; it is not a blanket statement that Chromie behaves correctly in all
live voice or robot conditions.
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

from scripts.behavior_scenarios import load_scenarios, run_scenarios_sync  # noqa: E402
from scripts.interaction_text_mujoco_check import parse_expected_arg, run_check  # noqa: E402

DEFAULT_MANIFEST = ROOT / "scenarios" / "general_ability_acceptance.json"
DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "general-ability"
LEVEL_A_CLAIM = (
    "Level A deterministic file-backed evidence only. This does not prove live "
    "services, microphone, speaker, simulator execution, or robot behavior."
)
LIVE_TEXT_PREVIEW_CLAIM = (
    "Live text preview evidence through Router, the selected semantic runtime, "
    "and Soridormi status preflight. This does not prove microphone, speaker, "
    "or executed motion."
)
LIVE_TEXT_EXECUTE_CLAIM = (
    "Live text-to-Soridormi simulator execution evidence. This does not prove "
    "microphone, speaker, or physical hardware behavior."
)


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


@dataclass(frozen=True)
class ScenarioRef:
    key: str
    rationale: str = ""


@dataclass(frozen=True)
class LiveCaseRef:
    case: TextScenarioCase
    rationale: str = ""


@dataclass(frozen=True)
class AbilityClass:
    ability_id: str
    title: str
    general_rule: str
    minimum_level_a_cases: int
    root_cause_boundaries: tuple[str, ...] = field(default_factory=tuple)
    level_a_scenarios: tuple[ScenarioRef, ...] = field(default_factory=tuple)
    live_text_cases: tuple[LiveCaseRef, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GeneralAbilityManifest:
    path: Path
    title: str
    claim_policy: dict[str, Any]
    ability_classes: tuple[AbilityClass, ...]


def acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


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


def _is_expressive_cue_skill(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata")
    return bool(
        isinstance(metadata, dict)
        and (
            metadata.get("source") in {"expressive_body_cue", "social_attention_plan"}
            or metadata.get("auxiliary_social_attention") is True
        )
    )


def _task_skill_ids(summary: dict[str, Any], *, allow_expressive_cues: bool) -> list[str]:
    return [
        str(item.get("skill_id") or "")
        for item in _skill_items(summary)
        if not (allow_expressive_cues and _is_expressive_cue_skill(item))
    ]


def validate_live_text_result(
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

    skills = {
        str(item.get("skill_id") or "")
        for item in _skill_items(summary)
    }
    task_skills = sorted(
        set(_task_skill_ids(
            summary,
            allow_expressive_cues=case.allow_expressive_cues,
        ))
    )
    if case.expect_no_skills and task_skills:
        errors.append(
            "interaction emitted Soridormi task skills, expected none: "
            + ", ".join(task_skills)
        )
    bad_skills = sorted(skills & set(case.forbidden_skills))
    if bad_skills:
        errors.append("forbidden skills emitted: " + ", ".join(bad_skills))
    return errors


def _scenario_ref(raw: Any) -> ScenarioRef:
    if isinstance(raw, str):
        return ScenarioRef(key=raw.strip())
    if not isinstance(raw, dict):
        raise ValueError("level_a_scenarios entries must be strings or objects")
    key = str(raw.get("key") or "").strip()
    if not key:
        raise ValueError("level_a_scenarios entry is missing key")
    return ScenarioRef(key=key, rationale=str(raw.get("rationale") or ""))


def _live_case(raw: dict[str, Any]) -> LiveCaseRef:
    case_id = str(raw.get("id") or raw.get("case_id") or "").strip()
    text = str(raw.get("text") or "").strip()
    if not case_id:
        raise ValueError("live_text_cases entry is missing id")
    if not text:
        raise ValueError(f"live_text_cases entry {case_id!r} is missing text")
    expected_args = tuple(
        item if isinstance(item, tuple) else parse_expected_arg(str(item))
        for item in raw.get("expected_args", raw.get("expect_arg", []))
    )
    case = TextScenarioCase(
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
    return LiveCaseRef(case=case, rationale=str(raw.get("rationale") or ""))


def _ability_class(raw: dict[str, Any]) -> AbilityClass:
    ability_id = str(raw.get("id") or "").strip()
    if not ability_id:
        raise ValueError("ability class is missing id")
    level_a = tuple(_scenario_ref(item) for item in raw.get("level_a_scenarios", []))
    live = tuple(
        _live_case(item)
        for item in raw.get("live_text_cases", [])
        if isinstance(item, dict)
    )
    return AbilityClass(
        ability_id=ability_id,
        title=str(raw.get("title") or ability_id),
        general_rule=str(raw.get("general_rule") or ""),
        minimum_level_a_cases=int(raw.get("minimum_level_a_cases", 1)),
        root_cause_boundaries=_tuple_of_strings(raw.get("root_cause_boundaries")),
        level_a_scenarios=level_a,
        live_text_cases=live,
    )


def load_manifest(path: Path = DEFAULT_MANIFEST) -> GeneralAbilityManifest:
    resolved = path.expanduser().resolve()
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("general ability manifest must contain one JSON object")
    if raw.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version {raw.get('schema_version')!r}")
    raw_classes = raw.get("ability_classes")
    if not isinstance(raw_classes, list) or not raw_classes:
        raise ValueError("manifest must contain a non-empty ability_classes list")
    return GeneralAbilityManifest(
        path=resolved,
        title=str(raw.get("title") or "General ability acceptance"),
        claim_policy=dict(raw.get("claim_policy") or {}),
        ability_classes=tuple(_ability_class(item) for item in raw_classes),
    )


def level_a_keys(classes: list[AbilityClass] | tuple[AbilityClass, ...]) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for ability in classes:
        for ref in ability.level_a_scenarios:
            if ref.key not in seen:
                keys.append(ref.key)
                seen.add(ref.key)
    return keys


def live_case_ids(classes: list[AbilityClass] | tuple[AbilityClass, ...]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for ability in classes:
        for ref in ability.live_text_cases:
            if ref.case.case_id not in seen:
                ids.append(ref.case.case_id)
                seen.add(ref.case.case_id)
    return ids


def select_ability_classes(
    manifest: GeneralAbilityManifest,
    selected: list[str] | tuple[str, ...],
) -> list[AbilityClass]:
    classes = list(manifest.ability_classes)
    if not selected:
        return classes
    wanted = set(selected)
    out = [item for item in classes if item.ability_id in wanted]
    missing = wanted - {item.ability_id for item in out}
    if missing:
        raise ValueError(f"unknown ability class: {', '.join(sorted(missing))}")
    return out


def validate_manifest(manifest: GeneralAbilityManifest) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for ability in manifest.ability_classes:
        if ability.ability_id in seen:
            errors.append(f"duplicate ability class id {ability.ability_id!r}")
        seen.add(ability.ability_id)
        if not ability.general_rule.strip():
            errors.append(f"{ability.ability_id}: general_rule is required")
        if len(ability.level_a_scenarios) < ability.minimum_level_a_cases:
            errors.append(
                f"{ability.ability_id}: has {len(ability.level_a_scenarios)} "
                f"Level A scenario(s), expected at least {ability.minimum_level_a_cases}"
            )
        if not ability.level_a_scenarios and not ability.live_text_cases:
            errors.append(f"{ability.ability_id}: no acceptance cases declared")

    keys = level_a_keys(manifest.ability_classes)
    if keys:
        try:
            load_scenarios(only=set(keys))
        except Exception as exc:
            errors.append(f"Level A scenario reference check failed: {exc}")
    return errors


def _class_case_index(classes: list[AbilityClass]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for ability in classes:
        for ref in ability.level_a_scenarios:
            index.setdefault(ref.key, []).append(
                {
                    "ability_class": ability.ability_id,
                    "rationale": ref.rationale,
                }
            )
    return index


def _filter_level_a_refs(
    ability: AbilityClass,
    only_cases: set[str],
) -> list[ScenarioRef]:
    if not only_cases:
        return list(ability.level_a_scenarios)
    refs = [
        ref
        for ref in ability.level_a_scenarios
        if ref.key in only_cases or ref.key.rsplit("/", 1)[-1] in only_cases
    ]
    return refs


def _selected_level_a_keys(classes: list[AbilityClass], only_cases: set[str]) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for ability in classes:
        for ref in _filter_level_a_refs(ability, only_cases):
            if ref.key not in seen:
                keys.append(ref.key)
                seen.add(ref.key)
    if only_cases:
        matched = seen | {key.rsplit("/", 1)[-1] for key in seen}
        missing = only_cases - matched
        if missing:
            raise ValueError(f"unknown selected case(s): {', '.join(sorted(missing))}")
    return keys


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evidence_root(args: argparse.Namespace, mode: str) -> Path:
    if args.evidence_dir:
        return Path(args.evidence_dir).expanduser().resolve()
    return (DEFAULT_EVIDENCE_ROOT / f"{acceptance_id()}-{mode}").resolve()


def _maybe_write_summary(
    args: argparse.Namespace,
    mode: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    if args.no_write:
        return summary
    root = _evidence_root(args, mode)
    root.mkdir(parents=True, exist_ok=True)
    summary = {**summary, "evidence_dir": str(root)}
    _write_json(root / "summary.json", summary)
    return summary


def manifest_summary(manifest: GeneralAbilityManifest) -> dict[str, Any]:
    errors = validate_manifest(manifest)
    return {
        "ok": not errors,
        "mode": "check",
        "manifest": str(manifest.path),
        "title": manifest.title,
        "errors": errors,
        "ability_class_count": len(manifest.ability_classes),
        "level_a_case_count": len(level_a_keys(manifest.ability_classes)),
        "live_text_case_count": len(live_case_ids(manifest.ability_classes)),
        "ability_classes": [
            {
                "id": ability.ability_id,
                "title": ability.title,
                "general_rule": ability.general_rule,
                "root_cause_boundaries": list(ability.root_cause_boundaries),
                "minimum_level_a_cases": ability.minimum_level_a_cases,
                "level_a_scenarios": [ref.key for ref in ability.level_a_scenarios],
                "live_text_cases": [ref.case.case_id for ref in ability.live_text_cases],
            }
            for ability in manifest.ability_classes
        ],
    }


def run_level_a(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.ability_manifest)
    manifest_errors = validate_manifest(manifest)
    selected_classes = select_ability_classes(manifest, args.ability_class)
    selected_keys = _selected_level_a_keys(selected_classes, set(args.only_case))
    if not selected_keys:
        raise ValueError("no Level A cases selected")

    scenarios = load_scenarios(only=set(selected_keys))
    report = run_scenarios_sync(scenarios)
    result_by_key = {
        str(item.get("key")): item
        for item in report.get("cases", [])
        if isinstance(item, dict)
    }

    ability_results: list[dict[str, Any]] = []
    for ability in selected_classes:
        refs = _filter_level_a_refs(ability, set(args.only_case))
        cases: list[dict[str, Any]] = []
        for ref in refs:
            result = result_by_key.get(ref.key, {})
            cases.append(
                {
                    "key": ref.key,
                    "ok": bool(result.get("ok")),
                    "rationale": ref.rationale,
                    "errors": list(result.get("errors") or []),
                }
            )
        if not cases:
            continue
        ability_results.append(
            {
                "id": ability.ability_id,
                "title": ability.title,
                "general_rule": ability.general_rule,
                "root_cause_boundaries": list(ability.root_cause_boundaries),
                "ok": all(item["ok"] for item in cases),
                "passed": sum(1 for item in cases if item["ok"]),
                "failed": sum(1 for item in cases if not item["ok"]),
                "cases": cases,
            }
        )

    errors = list(manifest_errors)
    errors.extend(
        f"{ability['id']} failed {ability['failed']} Level A case(s)"
        for ability in ability_results
        if ability["failed"]
    )
    summary = {
        "ok": not errors,
        "mode": "level-a",
        "evidence_level": "A",
        "claim_scope": LEVEL_A_CLAIM,
        "manifest": str(manifest.path),
        "errors": errors,
        "root_cause_report_required": any(item["failed"] for item in ability_results),
        "ability_class_count": len(ability_results),
        "case_count": len(selected_keys),
        "passed": int(report.get("passed", 0)),
        "failed": int(report.get("failed", 0)),
        "case_to_ability": _class_case_index(selected_classes),
        "ability_classes": ability_results,
        "scenario_report": report,
    }
    return _maybe_write_summary(args, "level-a", summary)


def _filter_live_refs(
    ability: AbilityClass,
    only_cases: set[str],
) -> list[LiveCaseRef]:
    if not only_cases:
        return list(ability.live_text_cases)
    return [
        ref
        for ref in ability.live_text_cases
        if ref.case.case_id in only_cases
    ]


def _selected_live_refs(
    classes: list[AbilityClass],
    only_cases: set[str],
) -> list[tuple[AbilityClass, LiveCaseRef]]:
    refs: list[tuple[AbilityClass, LiveCaseRef]] = []
    seen: set[str] = set()
    for ability in classes:
        for ref in _filter_live_refs(ability, only_cases):
            if ref.case.case_id not in seen:
                refs.append((ability, ref))
                seen.add(ref.case.case_id)
    if only_cases:
        missing = only_cases - seen
        if missing:
            raise ValueError(f"unknown selected live case(s): {', '.join(sorted(missing))}")
    return refs


def _live_case_namespace(
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
        manifest=args.soridormi_manifest,
        language=args.language,
        evidence_dir=str(evidence_dir),
        conversation_id=f"ga-live-{case.case_id}",
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
        reject_internal_speech=True,
        reject_speech_pattern=[],
        cognitive_runtime=args.goal_driven_runtime == "apply",
        cognitive_apply_lanes=args.cognitive_apply_lanes,
    )


async def run_live_text(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.ability_manifest)
    manifest_errors = validate_manifest(manifest)
    selected_classes = select_ability_classes(manifest, args.ability_class)
    selected_refs = _selected_live_refs(selected_classes, set(args.only_case))
    if not selected_refs:
        raise ValueError("no live text cases selected")

    root = _evidence_root(args, "live-text")
    if not args.no_write:
        root.mkdir(parents=True, exist_ok=True)

    case_results: list[dict[str, Any]] = []
    for index, (ability, ref) in enumerate(selected_refs, 1):
        case = ref.case
        case_dir = root / f"{index:02d}-{ability.ability_id}-{case.case_id}"
        print(
            f"[general-ability][live-text] {index}/{len(selected_refs)} "
            f"{ability.ability_id}/{case.case_id}",
            file=sys.stderr,
            flush=True,
        )
        try:
            result = await asyncio.wait_for(
                run_check(_live_case_namespace(args, case, case_dir)),
                timeout=args.case_timeout_s,
            )
            scenario_errors = validate_live_text_result(case, result)
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
        result["ability_class"] = ability.ability_id
        result["general_rule"] = ability.general_rule
        result["case_id"] = case.case_id
        result["description"] = case.description
        result["rationale"] = ref.rationale
        result["root_cause_boundaries"] = list(ability.root_cause_boundaries)
        if not args.no_write:
            _write_json(case_dir / "summary.json", result)
        case_results.append(result)

    ability_results: list[dict[str, Any]] = []
    for ability in selected_classes:
        cases = [
            {
                "case_id": item["case_id"],
                "ok": bool(item.get("ok")),
                "errors": list(item.get("errors") or []),
                "evidence_dir": item.get("evidence_dir"),
            }
            for item in case_results
            if item.get("ability_class") == ability.ability_id
        ]
        if not cases:
            continue
        ability_results.append(
            {
                "id": ability.ability_id,
                "title": ability.title,
                "general_rule": ability.general_rule,
                "root_cause_boundaries": list(ability.root_cause_boundaries),
                "ok": all(item["ok"] for item in cases),
                "passed": sum(1 for item in cases if item["ok"]),
                "failed": sum(1 for item in cases if not item["ok"]),
                "cases": cases,
            }
        )

    errors = list(manifest_errors)
    errors.extend(
        f"{ability['id']} failed {ability['failed']} live text case(s)"
        for ability in ability_results
        if ability["failed"]
    )
    summary = {
        "ok": not errors,
        "mode": "live-text",
        "evidence_level": "C" if args.execute else "C-preview",
        "claim_scope": LIVE_TEXT_EXECUTE_CLAIM if args.execute else LIVE_TEXT_PREVIEW_CLAIM,
        "manifest": str(manifest.path),
        "goal_driven_runtime": args.goal_driven_runtime,
        "cognitive_apply_lanes": (
            args.cognitive_apply_lanes
            if args.goal_driven_runtime == "apply"
            else ""
        ),
        "execute": args.execute,
        "speaker": args.speaker,
        "errors": errors,
        "root_cause_report_required": any(item["failed"] for item in ability_results),
        "ability_class_count": len(ability_results),
        "case_count": len(case_results),
        "passed": sum(1 for item in case_results if item.get("ok")),
        "failed": sum(1 for item in case_results if not item.get("ok")),
        "ability_classes": ability_results,
        "cases": case_results,
    }
    if args.no_write:
        return summary
    summary = {**summary, "evidence_dir": str(root)}
    _write_json(root / "summary.json", summary)
    return summary


def print_list(manifest: GeneralAbilityManifest) -> None:
    print(manifest.title)
    for ability in manifest.ability_classes:
        print(
            f"{ability.ability_id}: "
            f"{len(ability.level_a_scenarios)} Level A, "
            f"{len(ability.live_text_cases)} live text"
        )
        print(f"  {ability.general_rule}")


def print_summary(summary: dict[str, Any]) -> None:
    if summary.get("mode") == "check":
        status = "passed" if summary.get("ok") else "failed"
        print(
            "General ability manifest check "
            f"{status}: {summary.get('ability_class_count', 0)} ability classes, "
            f"{summary.get('level_a_case_count', 0)} Level A cases, "
            f"{summary.get('live_text_case_count', 0)} live text cases"
        )
        if summary.get("errors"):
            print("Errors:")
            for error in summary["errors"]:
                print(f"  - {error}")
        if summary.get("evidence_dir"):
            print(f"Evidence: {summary['evidence_dir']}")
        return

    print(
        "General ability acceptance: "
        f"{summary.get('passed', 0)}/{summary.get('case_count', 0)} passed "
        f"mode={summary.get('mode')} evidence={summary.get('evidence_level', 'manifest')}"
    )
    for ability in summary.get("ability_classes", []):
        if not isinstance(ability, dict):
            continue
        status = "PASS" if ability.get("ok") else "FAIL"
        print(
            f"  {status} {ability.get('id')}: "
            f"{ability.get('passed', 0)}/{ability.get('passed', 0) + ability.get('failed', 0)}"
        )
        if not ability.get("ok"):
            for case in ability.get("cases", []):
                if isinstance(case, dict) and not case.get("ok"):
                    print(f"    - {case.get('key') or case.get('case_id')}: {case.get('errors')}")
    if summary.get("errors"):
        print("Errors:")
        for error in summary["errors"]:
            print(f"  - {error}")
    if summary.get("evidence_dir"):
        print(f"Evidence: {summary['evidence_dir']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("check", "level-a", "live-text"),
        default="check",
        help="check validates the manifest; level-a runs deterministic scenarios; live-text uses deployed services.",
    )
    parser.add_argument(
        "--ability-manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="General ability manifest JSON.",
    )
    parser.add_argument(
        "--ability-class",
        action="append",
        default=[],
        help="Run one ability class id. Repeatable. Defaults to all classes.",
    )
    parser.add_argument(
        "--only-case",
        action="append",
        default=[],
        help="Run one scenario key, scenario id, or live case id. Repeatable.",
    )
    parser.add_argument("--list", action="store_true", help="List ability classes and exit.")
    parser.add_argument("--json", action="store_true", help="Print full JSON summary.")
    parser.add_argument("--no-write", action="store_true", help="Do not write an evidence summary.")
    parser.add_argument("--allow-failures", action="store_true", help="Return success even when checks fail.")
    parser.add_argument("--evidence-dir", help="Directory for retained evidence summary.")

    parser.add_argument("--router-url", default=os.getenv("ROUTER_URL", "http://127.0.0.1:8091"))
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument(
        "--soridormi-manifest",
        type=Path,
        default=ROOT / "capabilities" / "soridormi.json",
    )
    parser.add_argument("--language", default="en-US")
    parser.add_argument(
        "--goal-driven-runtime",
        choices=("off", "apply"),
        default="apply",
        help=(
            "Use the goal-association, Fast/Deep Planner, response-composer, "
            "and trusted runtime adapter for live-text cases (default: apply). "
            "Select off only for an explicit legacy Agent compatibility run."
        ),
    )
    parser.add_argument(
        "--cognitive-apply-lanes",
        default="chat,robot_action",
        help="Comma-separated goal-driven apply lanes for live-text cases.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute live text skills through Soridormi/MuJoCo.")
    parser.add_argument("--speaker", action="store_true", help="Play TTS for live text runs. Default is headless.")
    parser.add_argument("--allow-non-sim", action="store_true", help="Permit non-sim Soridormi mode under separate supervision.")
    parser.add_argument("--auto-confirm-sim", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--arg-tolerance", type=float, default=1e-6)
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=600.0,
        help=(
            "Session-completion timeout for live qualification. The default "
            "is intentionally long while model and architecture behavior are "
            "being validated."
        ),
    )
    parser.add_argument("--skill-timeout-s", type=float, default=120.0)
    parser.add_argument(
        "--case-timeout-s",
        type=float,
        default=1200.0,
        help=(
            "Outer timeout for one live case. This must exceed the complete "
            "Goal Association + Fast/Deep Planner + Response Composer path."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.ability_manifest)
        if args.list:
            print_list(manifest)
            return 0
        if args.mode == "check":
            summary = manifest_summary(manifest)
            summary = _maybe_write_summary(args, "check", summary)
        elif args.mode == "level-a":
            summary = run_level_a(args)
        else:
            summary = asyncio.run(run_live_text(args))
    except Exception as exc:
        print(f"[general-ability][error] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_summary(summary)
    return 0 if summary.get("ok") or args.allow_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
