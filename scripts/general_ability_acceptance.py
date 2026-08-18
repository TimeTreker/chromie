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
import fcntl
import hashlib
import json
import os
import sys
from contextlib import contextmanager
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
    run_check_sequence,
)
from scripts.outcome_observations import (  # noqa: E402
    collect_llm_integrity_violations,
    collect_observations,
    load_behavior_map,
    observation_type_for_capability,
    validate_expected_observations,
)
DEFAULT_MANIFEST = ROOT / "scenarios" / "general_ability_acceptance.json"
DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "general-ability"
LEVEL_A_CLAIM = (
    "Level A deterministic file-backed evidence only. This does not prove live "
    "services, microphone, speaker, simulator execution, or robot behavior."
)
LIVE_TEXT_PREVIEW_CLAIM = (
    "Live text preview evidence through Cognitive Gateway and the selected semantic runtime, "
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
    language: str = ""
    expected_routes: tuple[str, ...] = field(default_factory=tuple)
    expected_capabilities: tuple[str, ...] = field(default_factory=tuple)
    expected_args: tuple[tuple[int, str, Any], ...] = field(default_factory=tuple)
    expect_no_capabilities: bool = False
    expected_speech_all: tuple[str, ...] = field(default_factory=tuple)
    expected_speech_any: tuple[str, ...] = field(default_factory=tuple)
    forbidden_speech_any: tuple[str, ...] = field(default_factory=tuple)
    forbidden_capabilities: tuple[str, ...] = field(default_factory=tuple)
    allow_expressive_cues: bool = True
    require_speech: bool = True
    require_fast_speech: bool = False
    forbid_fast_speech: bool = False
    expected_fast_speech_purposes: tuple[str, ...] = field(default_factory=tuple)
    require_social_attention_opportunity: bool = False
    require_fast_planner_evidence_reentry: bool = False
    require_pre_ga_safe_capability_dispatch: bool = False
    require_canonical_work_reconciliation: bool = False
    max_warm_gi_handoff_to_fast_commit_ms: float = 0.0
    max_warm_fast_commit_to_playback_start_ms: float = 0.0
    expected_terminal_planner_tier: str = ""
    expected_fast_planner_path: str = ""
    expect_deep_planner_invoked: bool | None = None
    expect_no_fast_contract_failure: bool = False
    expected_observations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    expected_observation_sequence: tuple[str, ...] = field(default_factory=tuple)
    min_new_goal_count: int = 0
    min_goal_outcome_count: int = 0
    forbidden_plan_agent_skills: tuple[str, ...] = field(default_factory=tuple)
    require_llm_integrity: bool = True
    description: str = ""
    turns: tuple["TextScenarioCase", ...] = field(default_factory=tuple)


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


@contextmanager
def _exclusive_orchestrator_lock() -> Any:
    """Prevent a qualification Host from competing with the operator Host."""

    lock_path = Path(
        os.getenv("ORCH_LOCK_FILE", "/tmp/chromie-orchestrator.lock")
    ).expanduser()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "live-text qualification requires the exclusive Host lock; "
                f"another Orchestrator is running: {lock_path}"
            ) from exc
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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


def _capability_items(summary: dict[str, Any]) -> list[dict[str, Any]]:
    response = summary.get("interaction_response")
    if not isinstance(response, dict):
        return []
    capabilities = response.get("capabilities")
    if not isinstance(capabilities, list):
        return []
    return [
        item
        for item in capabilities
        if isinstance(item, dict)
        and str(item.get("capability_id") or "").strip()
    ]


def _fast_progress_activities(summary: dict[str, Any]) -> list[dict[str, Any]]:
    cognitive = summary.get("cognitive_runtime")
    if not isinstance(cognitive, dict):
        return []
    advance = cognitive.get("fast_advance")
    if not isinstance(advance, dict):
        metadata = cognitive.get("metadata")
        advance = (
            metadata.get("fast_planner_advance")
            if isinstance(metadata, dict)
            else None
        )
    if not isinstance(advance, dict):
        return []
    return [
        item
        for item in advance.get("activities") or []
        if isinstance(item, dict)
        and item.get("role") == "progress"
        and str(item.get("speech_act") or "").strip()
    ]


def _is_expressive_cue_capability(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata")
    return bool(
        isinstance(metadata, dict)
        and (
            metadata.get("source") in {"expressive_body_cue", "social_attention_plan"}
            or metadata.get("auxiliary_social_attention") is True
        )
    )


def _task_capability_ids(summary: dict[str, Any], *, allow_expressive_cues: bool) -> list[str]:
    return [
        str(item.get("capability_id") or "")
        for item in _capability_items(summary)
        if not (allow_expressive_cues and _is_expressive_cue_capability(item))
    ]


def _plan_agent_skill_ids(cognitive: dict[str, Any]) -> set[str]:
    selected: set[str] = set()
    for key in ("fast_plan", "terminal_plan"):
        plan = cognitive.get(key)
        if not isinstance(plan, dict):
            continue
        for item in plan.get("selected_agent_skills") or []:
            if not isinstance(item, dict):
                continue
            agent_skill_id = str(item.get("agent_skill_id") or "").strip()
            if agent_skill_id:
                selected.add(agent_skill_id)
    return selected


def _provenance_attachment_rejected(cognitive: dict[str, Any]) -> bool:
    for key in ("fast_plan", "terminal_plan"):
        plan = cognitive.get(key)
        if not isinstance(plan, dict):
            continue
        metadata = plan.get("metadata")
        if not isinstance(metadata, dict):
            continue
        attachment = metadata.get("agent_skill_provenance_attachment")
        if isinstance(attachment, dict) and attachment.get("status") == "rejected":
            return True
    return False


def _structured_case_metrics(
    case: TextScenarioCase,
    summary: dict[str, Any],
) -> dict[str, Any]:
    cognitive = summary.get("cognitive_runtime")
    if not isinstance(cognitive, dict):
        cognitive = {}
    association = cognitive.get("goal_association")
    if not isinstance(association, dict):
        association = {}
    terminal_plan = cognitive.get("terminal_plan")
    if not isinstance(terminal_plan, dict):
        terminal_plan = {}
    new_goals = association.get("new_goals")
    if not isinstance(new_goals, list):
        new_goals = []
    goal_outcomes = terminal_plan.get("goal_outcomes")
    if not isinstance(goal_outcomes, list):
        goal_outcomes = []
    selected_agent_skills = _plan_agent_skill_ids(cognitive)
    forbidden_selected = sorted(
        selected_agent_skills.intersection(case.forbidden_plan_agent_skills)
    )
    user_outcome = summary.get("user_outcome")
    if not isinstance(user_outcome, dict):
        user_outcome = {}
    llm_integrity = user_outcome.get("llm_integrity")
    if not isinstance(llm_integrity, dict):
        llm_integrity = {}
    violations = llm_integrity.get("violations")
    if not isinstance(violations, list):
        violations = []
    status_after = summary.get("status_after")
    safe_idle = (
        None
        if bool(summary.get("preview_only"))
        else bool(
            isinstance(status_after, dict)
            and status_after.get("safe_idle") is True
            and status_after.get("active_task") is None
            and status_after.get("emergency_stop") is False
            and status_after.get("fallen") is False
        )
    )
    omission_rates: list[float] = []
    if case.min_new_goal_count:
        omission_rates.append(
            max(
                0.0,
                (case.min_new_goal_count - len(new_goals))
                / case.min_new_goal_count,
            )
        )
    if case.min_goal_outcome_count:
        omission_rates.append(
            max(
                0.0,
                (case.min_goal_outcome_count - len(goal_outcomes))
                / case.min_goal_outcome_count,
            )
        )
    goal_omission_rate = max(omission_rates, default=0.0)
    runtime_metadata = cognitive.get("metadata")
    if not isinstance(runtime_metadata, dict):
        runtime_metadata = {}
    runtime_status = str(cognitive.get("status") or "").strip()
    runtime_failure_stage = str(
        runtime_metadata.get("failure_stage")
        or runtime_metadata.get("stage")
        or ""
    ).strip()
    runtime_failure_class = str(
        runtime_metadata.get("failure_class") or ""
    ).strip()
    runtime_integrity_failed = runtime_status in {"error", "failed"}
    return {
        "new_goal_count": len(new_goals),
        "required_new_goal_count": case.min_new_goal_count,
        "goal_outcome_count": len(goal_outcomes),
        "required_goal_outcome_count": case.min_goal_outcome_count,
        "goal_omission_rate": round(goal_omission_rate, 4),
        "selected_plan_agent_skills": sorted(selected_agent_skills),
        "forbidden_plan_agent_skills": list(case.forbidden_plan_agent_skills),
        "forbidden_plan_agent_skill_count": len(forbidden_selected),
        "forbidden_plan_agent_skills_selected": forbidden_selected,
        "provenance_attachment_rejected": _provenance_attachment_rejected(
            cognitive
        ),
        "llm_integrity_failure_count": len(violations),
        "runtime_status": runtime_status,
        "runtime_failure_stage": runtime_failure_stage,
        "runtime_failure_class": runtime_failure_class,
        "runtime_integrity_failed": runtime_integrity_failed,
        "safe_idle": safe_idle,
    }


def _elapsed_ms(value: Any) -> float | None:
    try:
        elapsed = float(value)
    except (TypeError, ValueError):
        return None
    return elapsed if elapsed >= 0 else None


def _fast_response_timing_evidence(summary: dict[str, Any]) -> dict[str, Any]:
    """Retain exact anchors and recomputable fast-response timing intervals."""

    session_state = summary.get("session_state")
    if not isinstance(session_state, dict):
        session_state = {}
    stages = [
        item
        for item in session_state.get("cognitive_workflow_stages") or []
        if isinstance(item, dict)
    ]
    events = [
        item
        for item in session_state.get("workflow_events") or []
        if isinstance(item, dict)
    ]
    fast_stage = next(
        (
            item
            for item in stages
            if item.get("stage") == "fast_planner_first_response"
        ),
        {},
    )
    fast_start = _elapsed_ms(fast_stage.get("started_elapsed_ms"))
    fast_finish = _elapsed_ms(fast_stage.get("finished_elapsed_ms"))
    fast_duration = _elapsed_ms(fast_stage.get("duration_ms"))

    def first_event(name: str, *, not_before: float | None = None) -> float | None:
        values = [
            value
            for item in events
            if item.get("event") == name
            and (value := _elapsed_ms(item.get("elapsed_ms"))) is not None
            and (not_before is None or value >= not_before)
        ]
        return min(values, default=None)

    top_timings = summary.get("timings_ms")
    if not isinstance(top_timings, dict):
        top_timings = {}
    goal_interpretation_duration = _elapsed_ms(
        top_timings.get("goal_interpretation_ms")
    )
    session_start = first_event("session_start")
    interpretation_done = first_event("text_check_goal_interpretation_done")
    tts_schedule = first_event("tts_schedule", not_before=fast_finish)
    first_provider_pcm = first_event(
        "tts_first_provider_pcm",
        not_before=fast_finish,
    )
    playback_start = first_event("playback_start", not_before=fast_finish)

    def interval(start: float | None, finish: float | None) -> float | None:
        if start is None or finish is None or finish < start:
            return None
        return round(finish - start, 3)

    duration_sum = None
    if goal_interpretation_duration is not None and fast_duration is not None:
        duration_sum = round(goal_interpretation_duration + fast_duration, 3)
    return {
        "schema_version": 1,
        "clock": "session_relative_monotonic_elapsed_ms",
        "fast_first_response_status": str(fast_stage.get("status") or ""),
        "transport_evidence": (
            "speaker_enabled_playback_start"
            if summary.get("speaker") is True
            else "headless_or_discard_playback_start"
        ),
        "raw": {
            "session_start_elapsed_ms": session_start,
            "goal_interpretation_done_elapsed_ms": interpretation_done,
            "goal_interpretation_duration_ms": goal_interpretation_duration,
            "fast_first_response_started_elapsed_ms": fast_start,
            "fast_first_response_finished_elapsed_ms": fast_finish,
            "fast_first_response_duration_ms": fast_duration,
            "first_tts_schedule_elapsed_ms": tts_schedule,
            "first_tts_provider_pcm_elapsed_ms": first_provider_pcm,
            "first_playback_start_elapsed_ms": playback_start,
        },
        "derived": {
            "gi_handoff_to_fast_commit_ms": interval(fast_start, fast_finish),
            "fast_commit_to_tts_schedule_ms": interval(fast_finish, tts_schedule),
            "fast_commit_to_first_provider_pcm_ms": interval(
                fast_finish,
                first_provider_pcm,
            ),
            "fast_commit_to_playback_start_ms": interval(
                fast_finish,
                playback_start,
            ),
            "session_start_to_fast_commit_ms": interval(
                session_start,
                fast_finish,
            ),
            "goal_interpretation_plus_fast_duration_ms": duration_sum,
        },
        "claim_limits": {
            "audible_speaker_proven": summary.get("speaker") is True,
            "duration_sum_is_absolute_anchor": False,
        },
    }


def diagnostic_evaluation(
    case: TextScenarioCase,
    summary: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Build an objective scorecard without granting scoring runtime authority."""

    metrics = _structured_case_metrics(case, summary)
    user_outcome = summary.get("user_outcome")
    user_outcome_ok = bool(
        isinstance(user_outcome, dict) and user_outcome.get("ok") is True
    )
    axes = {
        "user_outcome": 100 if user_outcome_ok and not errors else max(0, 100 - 25 * len(errors)),
        "goal_coverage": (
            100
            if metrics["goal_omission_rate"] == 0.0
            else round(100 * (1.0 - metrics["goal_omission_rate"]))
        ),
        "stale_state_isolation": (
            0
            if metrics["forbidden_plan_agent_skill_count"]
            or metrics["provenance_attachment_rejected"]
            else 100
        ),
        "llm_integrity": (
            0 if metrics["llm_integrity_failure_count"] else 100
        ),
        "runtime_integrity": (
            0 if metrics["runtime_integrity_failed"] else 100
        ),
        "execution_safety": (
            100 if metrics["safe_idle"] in {None, True} else 0
        ),
    }
    earliest_boundary = "none_observed"
    if metrics["runtime_integrity_failed"]:
        stage = metrics["runtime_failure_stage"] or "unknown_stage"
        earliest_boundary = f"cognitive_runtime:{stage}"
    elif metrics["llm_integrity_failure_count"]:
        earliest_boundary = "cognitive_model_stage"
    elif metrics["new_goal_count"] < metrics["required_new_goal_count"]:
        earliest_boundary = "goal_association"
    elif (
        metrics["forbidden_plan_agent_skill_count"]
        or metrics["provenance_attachment_rejected"]
    ):
        earliest_boundary = "agent_skill_selection_or_provenance"
    elif metrics["goal_outcome_count"] < metrics["required_goal_outcome_count"]:
        earliest_boundary = "planner_contract"
    elif metrics["safe_idle"] is False:
        earliest_boundary = "capability_runtime_or_provider"
    elif errors:
        earliest_boundary = "response_or_user_outcome_boundary"
    overall_score = round(sum(axes.values()) / len(axes))
    if metrics["runtime_integrity_failed"] or metrics["llm_integrity_failure_count"]:
        overall_score = min(overall_score, 40)
    return {
        "passed": not errors,
        "overall_score": overall_score,
        "hard_gate_failures": list(errors),
        "axes": axes,
        "metrics": metrics,
        "earliest_suspect_boundary": earliest_boundary,
        "root_cause_report_required": bool(errors),
        "scoring_authority": "acceptance_only_not_runtime_policy",
    }


def validate_live_text_result(
    case: TextScenarioCase,
    summary: dict[str, Any],
    *,
    assertion_scope: str = "user-outcome",
) -> list[str]:
    errors: list[str] = []
    behavior_map = load_behavior_map()
    observations = collect_observations(summary, behavior_map=behavior_map)
    summary["user_outcome"] = {
        "assertion_scope": assertion_scope,
        "observations": observations,
    }
    if case.require_llm_integrity:
        violations = collect_llm_integrity_violations(summary)
        summary["user_outcome"]["llm_integrity"] = {
            "ok": not violations,
            "violations": violations,
        }
        if violations:
            errors.append(
                "LLM integrity gate failed: "
                + ", ".join(
                    str(item.get("event") or item.get("failure_class") or "unknown")
                    for item in violations
                )
            )
    route = summary.get("route")
    actual_route = route.get("route") if isinstance(route, dict) else None
    internal_diagnostics: list[str] = []
    if case.expected_routes and actual_route not in case.expected_routes:
        message = f"route={actual_route!r}, expected one of {list(case.expected_routes)!r}"
        if assertion_scope == "full":
            errors.append(message)
        else:
            internal_diagnostics.append(message)

    fast_speech = route.get("fast_speech") if isinstance(route, dict) else None
    fast_progress = _fast_progress_activities(summary)
    legacy_fast_speech_present = (
        isinstance(fast_speech, dict)
        and bool(str(fast_speech.get("text") or "").strip())
    )
    if case.forbid_fast_speech and (
        legacy_fast_speech_present or fast_progress
    ):
        errors.append("Core emitted forbidden pre-effect progress speech")
    if case.require_fast_speech:
        if legacy_fast_speech_present:
            purpose = str(fast_speech.get("purpose") or "").strip()
            if (
                case.expected_fast_speech_purposes
                and purpose not in case.expected_fast_speech_purposes
            ):
                errors.append(
                    "fast_speech purpose mismatch: expected one of "
                    f"{list(case.expected_fast_speech_purposes)!r}, got {purpose!r}"
                )
            if fast_speech.get("must_not_claim_completion") is not True:
                errors.append(
                    "fast_speech did not retain must_not_claim_completion=true"
                )
        elif fast_progress:
            purposes = {
                str(item.get("speech_act") or "").strip()
                for item in fast_progress
            }
            if (
                case.expected_fast_speech_purposes
                and not purposes.intersection(case.expected_fast_speech_purposes)
            ):
                errors.append(
                    "Fast progress Communicative Act purpose mismatch: expected one of "
                    f"{list(case.expected_fast_speech_purposes)!r}, got "
                    f"{sorted(purposes)!r}"
                )
            cognitive = summary.get("cognitive_runtime")
            metadata = (
                cognitive.get("metadata")
                if isinstance(cognitive, dict)
                and isinstance(cognitive.get("metadata"), dict)
                else {}
            )
            realization_status = str(
                metadata.get("fast_communicative_realization_status") or ""
            )
            if (
                not bool(summary.get("preview_only"))
                and realization_status != "planner_owned"
            ):
                errors.append(
                    "Fast progress Communicative Act was not retained as Planner-owned "
                    "before execution"
                )
        else:
            errors.append(
                "Core omitted the required pending-work progress Communicative Act"
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

    capabilities = {
        str(item.get("capability_id") or "")
        for item in _capability_items(summary)
    }
    task_capabilities = sorted(
        set(_task_capability_ids(
            summary,
            allow_expressive_cues=case.allow_expressive_cues,
        ))
    )
    if case.expect_no_capabilities and task_capabilities:
        errors.append(
            "interaction emitted Soridormi task capabilities, expected none: "
            + ", ".join(task_capabilities)
        )
    bad_capabilities = sorted(capabilities & set(case.forbidden_capabilities))
    if bad_capabilities:
        errors.append("forbidden capabilities emitted: " + ", ".join(bad_capabilities))

    expected_observations = [dict(item) for item in case.expected_observations]
    if not expected_observations and case.expected_capabilities:
        expected_arg_by_index: dict[int, dict[str, Any]] = {}
        for index, key, value in case.expected_args:
            expected_arg_by_index.setdefault(index, {})[key] = value
        expected_observations = [
            {
                "type": observation_type_for_capability(capability_id, behavior_map),
                "args": expected_arg_by_index.get(index, {}),
                "min_occurrences": 1,
            }
            for index, capability_id in enumerate(case.expected_capabilities)
        ]
    if not bool(summary.get("preview_only")):
        for expected in expected_observations:
            expected.setdefault("status", "completed")
    errors.extend(
        validate_expected_observations(
            observations,
            expected_observations,
            sequence=list(case.expected_observation_sequence),
        )
    )

    cognitive = summary.get("cognitive_runtime")
    if not isinstance(cognitive, dict):
        cognitive = {}
    terminal_plan = cognitive.get("terminal_plan")
    if not isinstance(terminal_plan, dict):
        terminal_plan = {}
    runtime_metadata = cognitive.get("metadata")
    if not isinstance(runtime_metadata, dict):
        runtime_metadata = {}
    timings = cognitive.get("timings_ms")
    if not isinstance(timings, dict):
        timings = {}
    session_state = summary.get("session_state")
    if not isinstance(session_state, dict):
        session_state = {}
    workflow_stages = [
        item
        for item in session_state.get("cognitive_workflow_stages") or []
        if isinstance(item, dict)
    ]
    if case.require_social_attention_opportunity:
        opportunity_count = int(
            runtime_metadata.get("social_attention_opportunity_count") or 0
        )
        retained_opportunity = any(
            item.get("stage") == "social_attention_opportunity"
            and (item.get("metadata") or {}).get("attached_to_main_activity") is True
            for item in workflow_stages
        )
        if opportunity_count < 1 and not retained_opportunity:
            errors.append(
                "Social Attention opportunity was not attached to the fast Main Activity"
            )
    if (
        case.require_fast_planner_evidence_reentry
        and not bool(summary.get("preview_only"))
        and not any(
            item.get("stage") == "fast_planner_evidence_reentry"
            and item.get("status") == "resolved"
            for item in workflow_stages
        )
    ):
        errors.append(
            "terminal Capability Evidence did not reactivate Fast Planner"
        )
    if (
        case.require_pre_ga_safe_capability_dispatch
        and not bool(summary.get("preview_only"))
        and not str(
            runtime_metadata.get("fast_capability_activity_status") or ""
        ).startswith("completed_before_canonical_dispatch")
    ):
        errors.append(
            "safe Capability did not use the pre-GA Fast Activity dispatch path"
        )
    if (
        case.require_canonical_work_reconciliation
        and not bool(summary.get("preview_only"))
        and runtime_metadata.get("work_reconciliation_required") is not True
    ):
        errors.append(
            "canonical Fast Planner Work reconciliation did not run"
        )
    timing_evidence = _fast_response_timing_evidence(summary)
    summary["fast_response_timing_evidence"] = timing_evidence
    timing_derived = timing_evidence["derived"]
    if case.max_warm_gi_handoff_to_fast_commit_ms > 0:
        planner_commit_ms = timing_derived["gi_handoff_to_fast_commit_ms"]
        if (
            timing_evidence["fast_first_response_status"] != "accepted"
            or planner_commit_ms is None
        ):
            errors.append(
                "validated-GI-handoff to Fast-Planner commitment timing is missing"
            )
        elif planner_commit_ms > case.max_warm_gi_handoff_to_fast_commit_ms:
            errors.append(
                "validated-GI-handoff to Fast-Planner commitment exceeded target: "
                f"{planner_commit_ms:.1f}ms > "
                f"{case.max_warm_gi_handoff_to_fast_commit_ms:.1f}ms"
            )
    if (
        case.max_warm_fast_commit_to_playback_start_ms > 0
        and not bool(summary.get("preview_only"))
    ):
        playback_ms = timing_derived["fast_commit_to_playback_start_ms"]
        if playback_ms is None:
            errors.append(
                "Fast-Planner commitment to first-playback-start timing is missing"
            )
        elif playback_ms > case.max_warm_fast_commit_to_playback_start_ms:
            errors.append(
                "Fast-Planner commitment to first playback start exceeded target: "
                f"{playback_ms:.1f}ms > "
                f"{case.max_warm_fast_commit_to_playback_start_ms:.1f}ms"
            )
    structured_metrics = _structured_case_metrics(case, summary)
    if structured_metrics["runtime_integrity_failed"]:
        detail = ":".join(
            item
            for item in (
                structured_metrics["runtime_failure_stage"],
                structured_metrics["runtime_failure_class"],
            )
            if item
        )
        errors.append(
            "cognitive runtime reported a hard failure"
            + (f": {detail}" if detail else "")
        )
    if structured_metrics["new_goal_count"] < case.min_new_goal_count:
        errors.append(
            "Goal Association omitted independent responsibilities: "
            f"expected at least {case.min_new_goal_count} new Goals, got "
            f"{structured_metrics['new_goal_count']}"
        )
    if structured_metrics["goal_outcome_count"] < case.min_goal_outcome_count:
        errors.append(
            "terminal Plan omitted per-Goal outcomes: "
            f"expected at least {case.min_goal_outcome_count}, got "
            f"{structured_metrics['goal_outcome_count']}"
        )
    if structured_metrics["forbidden_plan_agent_skills_selected"]:
        errors.append(
            "stale or unrelated Agent Skill provenance selected: "
            + ", ".join(
                structured_metrics["forbidden_plan_agent_skills_selected"]
            )
        )
    if structured_metrics["provenance_attachment_rejected"]:
        errors.append("planner Agent Skill provenance attachment was rejected")

    def record_internal(message: str) -> None:
        if assertion_scope == "full":
            errors.append(message)
        else:
            internal_diagnostics.append(message)

    if case.expected_terminal_planner_tier:
        actual_tier = str(terminal_plan.get("planner_tier") or "")
        if actual_tier != case.expected_terminal_planner_tier:
            record_internal(
                "terminal planner tier mismatch: "
                f"expected {case.expected_terminal_planner_tier!r}, got {actual_tier!r}"
            )
    if case.expected_fast_planner_path:
        actual_path = str(runtime_metadata.get("fast_planner_path") or "")
        if actual_path != case.expected_fast_planner_path:
            record_internal(
                "Fast Planner path mismatch: "
                f"expected {case.expected_fast_planner_path!r}, got {actual_path!r}"
            )
    if case.expect_deep_planner_invoked is not None:
        actual_invoked = bool(
            runtime_metadata.get("deep_planner_invoked")
            or "deep_planner" in timings
        )
        if actual_invoked is not case.expect_deep_planner_invoked:
            record_internal(
                "Deep Planner invocation mismatch: "
                f"expected {case.expect_deep_planner_invoked}, got {actual_invoked}"
            )
    if case.expect_no_fast_contract_failure:
        stage_diagnostics = runtime_metadata.get("stage_diagnostics")
        if not isinstance(stage_diagnostics, list):
            stage_diagnostics = []
        fast_failures = [
            item
            for item in stage_diagnostics
            if isinstance(item, dict)
            and item.get("stage") == "fast_planner"
            and item.get("failure_class")
        ]
        if runtime_metadata.get("fast_planner_path") == "contract_failure" or fast_failures:
            record_internal("Fast Planner contract failure remained in retained evidence")
    summary["user_outcome"]["internal_diagnostics"] = internal_diagnostics
    summary["user_outcome"]["ok"] = not errors
    summary["diagnostic_evaluation"] = diagnostic_evaluation(
        case,
        summary,
        errors,
    )
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


def _text_scenario_case(
    raw: dict[str, Any],
    *,
    fallback_case_id: str = "",
) -> TextScenarioCase:
    case_id = str(
        raw.get("id") or raw.get("case_id") or fallback_case_id
    ).strip()
    text = str(raw.get("text") or "").strip()
    if not case_id:
        raise ValueError("live text turn is missing id")
    if not text:
        raise ValueError(f"live text turn {case_id!r} is missing text")
    retired_latency_fields = {
        "max_warm_fast_response_commit_ms",
        "max_warm_first_playback_start_ms",
    }.intersection(raw)
    if retired_latency_fields:
        raise ValueError(
            "live text turn uses retired ambiguous latency field(s): "
            + ", ".join(sorted(retired_latency_fields))
        )
    expected_args = tuple(
        item if isinstance(item, tuple) else parse_expected_arg(str(item))
        for item in raw.get("expected_args", raw.get("expect_arg", []))
    )
    return TextScenarioCase(
        case_id=case_id,
        text=text,
        language=str(raw.get("language") or "").strip(),
        expected_routes=_tuple_of_strings(
            raw.get("expected_routes", raw.get("expected_route"))
        ),
        expected_capabilities=_tuple_of_strings(
            raw.get("expected_capabilities", raw.get("expect_capability"))
        ),
        expected_args=expected_args,
        expect_no_capabilities=bool(raw.get("expect_no_capabilities", False)),
        expected_speech_all=_tuple_of_strings(raw.get("expected_speech_all")),
        expected_speech_any=_tuple_of_strings(raw.get("expected_speech_any")),
        forbidden_speech_any=_tuple_of_strings(raw.get("forbidden_speech_any")),
        forbidden_capabilities=_tuple_of_strings(raw.get("forbidden_capabilities")),
        allow_expressive_cues=bool(raw.get("allow_expressive_cues", True)),
        require_speech=bool(raw.get("require_speech", True)),
        require_fast_speech=bool(raw.get("require_fast_speech", False)),
        forbid_fast_speech=bool(raw.get("forbid_fast_speech", False)),
        expected_fast_speech_purposes=_tuple_of_strings(
            raw.get("expected_fast_speech_purposes")
        ),
        require_social_attention_opportunity=bool(
            raw.get("require_social_attention_opportunity", False)
        ),
        require_fast_planner_evidence_reentry=bool(
            raw.get("require_fast_planner_evidence_reentry", False)
        ),
        require_pre_ga_safe_capability_dispatch=bool(
            raw.get("require_pre_ga_safe_capability_dispatch", False)
        ),
        require_canonical_work_reconciliation=bool(
            raw.get("require_canonical_work_reconciliation", False)
        ),
        max_warm_gi_handoff_to_fast_commit_ms=max(
            0.0,
            float(raw.get("max_warm_gi_handoff_to_fast_commit_ms", 0.0)),
        ),
        max_warm_fast_commit_to_playback_start_ms=max(
            0.0,
            float(
                raw.get("max_warm_fast_commit_to_playback_start_ms", 0.0)
            ),
        ),
        expected_terminal_planner_tier=str(
            raw.get("expected_terminal_planner_tier") or ""
        ).strip(),
        expected_fast_planner_path=str(
            raw.get("expected_fast_planner_path") or ""
        ).strip(),
        expect_deep_planner_invoked=(
            bool(raw.get("expect_deep_planner_invoked"))
            if "expect_deep_planner_invoked" in raw
            else None
        ),
        expect_no_fast_contract_failure=bool(
            raw.get("expect_no_fast_contract_failure", False)
        ),
        expected_observations=tuple(
            dict(item)
            for item in raw.get("expected_observations", [])
            if isinstance(item, dict)
        ),
        expected_observation_sequence=_tuple_of_strings(
            raw.get("expected_observation_sequence")
        ),
        min_new_goal_count=max(0, int(raw.get("min_new_goal_count", 0))),
        min_goal_outcome_count=max(
            0,
            int(raw.get("min_goal_outcome_count", 0)),
        ),
        forbidden_plan_agent_skills=_tuple_of_strings(
            raw.get("forbidden_plan_agent_skills")
        ),
        require_llm_integrity=bool(raw.get("require_llm_integrity", True)),
        description=str(raw.get("description") or ""),
    )


def _live_case(raw: dict[str, Any]) -> LiveCaseRef:
    case_id = str(raw.get("id") or raw.get("case_id") or "").strip()
    if not case_id:
        raise ValueError("live_text_cases entry is missing id")
    raw_turns = raw.get("turns")
    if raw_turns is not None:
        if not isinstance(raw_turns, list) or not raw_turns:
            raise ValueError(
                f"live_text_cases entry {case_id!r} turns must be a non-empty array"
            )
        turns = tuple(
            _text_scenario_case(
                item,
                fallback_case_id=f"{case_id}_turn_{index}",
            )
            for index, item in enumerate(raw_turns, 1)
            if isinstance(item, dict)
        )
        if len(turns) != len(raw_turns):
            raise ValueError(
                f"live_text_cases entry {case_id!r} contains a non-object turn"
            )
        case = TextScenarioCase(
            case_id=case_id,
            text="",
            language=str(raw.get("language") or "").strip(),
            description=str(raw.get("description") or ""),
            turns=turns,
        )
    else:
        case = _text_scenario_case(raw)
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


def validate_manifest(
    manifest: GeneralAbilityManifest,
    *,
    validate_level_a_sources: bool = True,
) -> list[str]:
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
        for ref in ability.live_text_cases:
            for case in (ref.case, *ref.case.turns):
                if case.require_fast_speech and case.forbid_fast_speech:
                    errors.append(
                        f"{ability.ability_id}/{case.case_id}: fast speech "
                        "cannot be both required and forbidden"
                    )
                if case.forbid_fast_speech and case.expected_fast_speech_purposes:
                    errors.append(
                        f"{ability.ability_id}/{case.case_id}: forbidden fast "
                        "speech cannot declare expected purposes"
                    )

    keys = level_a_keys(manifest.ability_classes)
    if keys and validate_level_a_sources:
        try:
            from scripts.behavior_scenarios import load_scenarios  # noqa: PLC0415

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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_reviewer_packet(
    *,
    root: Path,
    run_summary: dict[str, Any],
    runtime_identity_path: Path,
) -> dict[str, Any]:
    """Write a bounded, digest-bound packet suitable for later sanitization."""

    packet = root / "reviewer-packet"
    packet.mkdir(parents=True, exist_ok=True)
    runtime_identity = _load_json_object(runtime_identity_path)
    runtime_identity_copy = packet / "runtime-identity.json"
    _write_json(runtime_identity_copy, runtime_identity)

    case_summaries: list[dict[str, Any]] = []
    timelines: list[dict[str, Any]] = []
    for item in run_summary.get("cases") or []:
        if not isinstance(item, dict):
            continue
        timing = item.get("fast_response_timing_evidence")
        if not isinstance(timing, dict):
            timing = _fast_response_timing_evidence(item)
        case_id = str(item.get("case_id") or "")
        case_summaries.append(
            {
                "case_id": case_id,
                "ability_class": str(item.get("ability_class") or ""),
                "ok": bool(item.get("ok")),
                "errors": list(item.get("errors") or []),
                "diagnostic_evaluation": item.get("diagnostic_evaluation") or {},
                "timing_evidence": timing,
            }
        )
        timelines.append({"case_id": case_id, **timing})

    runtime_profile = runtime_identity.get("runtime_profile")
    if not isinstance(runtime_profile, dict):
        runtime_profile = {}
    source_identity = runtime_identity.get("chromie")
    if not isinstance(source_identity, dict):
        source_identity = {}
    bounded_summary = {
        "schema_version": 1,
        "kind": "chromie_general_ability_reviewer_summary",
        "ok": bool(run_summary.get("ok")),
        "mode": run_summary.get("mode"),
        "evidence_level": run_summary.get("evidence_level"),
        "claim_scope": run_summary.get("claim_scope"),
        "input_channel": "injected_text",
        "exclusive_host_lock": bool(
            run_summary.get("exclusive_host_lock")
        ),
        "execute": bool(run_summary.get("execute")),
        "speaker": bool(run_summary.get("speaker")),
        "assertion_scope": run_summary.get("assertion_scope"),
        "goal_driven_runtime": run_summary.get("goal_driven_runtime"),
        "cognitive_apply_lanes": run_summary.get("cognitive_apply_lanes"),
        "source_identity": source_identity,
        "runtime_identity_sha256": runtime_identity.get("identity_sha256"),
        "runtime_profile": {
            "active_profile": runtime_profile.get("active_profile"),
            "active_validation_profile": runtime_profile.get(
                "active_validation_profile"
            ),
            "fingerprint": runtime_profile.get("fingerprint"),
            "sha256": runtime_profile.get("sha256"),
        },
        "passed": int(run_summary.get("passed") or 0),
        "failed": int(run_summary.get("failed") or 0),
        "errors": list(run_summary.get("errors") or []),
        "cases": case_summaries,
        "claim_limits": {
            "physical_microphone_proven": False,
            "audible_speaker_proven": run_summary.get("speaker") is True,
            "physical_robot_proven": False,
            "source_clean": source_identity.get("dirty") is False,
        },
    }
    summary_path = packet / "summary.json"
    timeline_path = packet / "timeline.json"
    collection_report_path = packet / "collection-report.json"
    _write_json(summary_path, bounded_summary)
    _write_json(
        timeline_path,
        {
            "schema_version": 1,
            "clock": "session_relative_monotonic_elapsed_ms",
            "cases": timelines,
        },
    )
    _write_json(
        collection_report_path,
        {
            "schema_version": 1,
            "kind": "chromie_general_ability_reviewer_collection",
            "ok": bounded_summary["ok"],
            "evidence_level": bounded_summary["evidence_level"],
            "runtime_identity_sha256": bounded_summary[
                "runtime_identity_sha256"
            ],
            "case_ids": [item["case_id"] for item in case_summaries],
            "human_review_required": True,
        },
    )

    artifact_paths = [
        summary_path,
        timeline_path,
        runtime_identity_copy,
        collection_report_path,
    ]
    manifest_path = packet / "manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "kind": "chromie_general_ability_reviewer_packet",
            "source_revision": source_identity.get("revision"),
            "source_tree_sha256": source_identity.get("source_tree_sha256"),
            "runtime_identity_sha256": runtime_identity.get("identity_sha256"),
            "artifacts": [
                {
                    "path": path.name,
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
                for path in artifact_paths
            ],
            "external_transfer": {
                "requires_separate_sanitized_copy": True,
                "human_review_required": True,
            },
        },
    )
    checksum_paths = [*artifact_paths, manifest_path]
    checksum_path = packet / "SHA256SUMS"
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in checksum_paths
        ),
        encoding="utf-8",
    )
    return {
        "path": str(packet),
        "manifest_sha256": _sha256_file(manifest_path),
        "file_count": len(checksum_paths) + 1,
        "sanitized_copy_required_for_external_transfer": True,
    }


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
    from scripts.behavior_scenarios import (  # noqa: PLC0415
        load_scenarios,
        run_scenarios_sync,
    )

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
    *,
    conversation_id: str | None = None,
) -> argparse.Namespace:
    expected_route = case.expected_routes[0] if len(case.expected_routes) == 1 else None
    return argparse.Namespace(
        text=case.text,
        agent_url=args.agent_url,
        soridormi_mcp_url=args.soridormi_mcp_url,
        soridormi_repo=args.soridormi_repo,
        manifest=args.soridormi_manifest,
        language=case.language or args.language,
        evidence_dir=str(evidence_dir),
        runtime_identity=args.runtime_identity,
        conversation_id=conversation_id or f"ga-live-{case.case_id}",
        speaker=args.speaker,
        preview_only=not args.execute,
        allow_non_sim=args.allow_non_sim,
        grant_confirmation=args.grant_confirmation,
        require_speech=case.require_speech,
        expect_route=expected_route if args.assertion_scope == "full" else None,
        expect_no_capabilities=case.expect_no_capabilities and not case.allow_expressive_cues,
        expect_capability=list(case.expected_capabilities) if args.assertion_scope == "full" else [],
        expect_arg=list(case.expected_args) if args.assertion_scope == "full" else [],
        arg_tolerance=args.arg_tolerance,
        timeout_s=args.timeout_s,
        interrupt_text="",
        interrupt_capability_prefix="soridormi.",
        interrupt_start_timeout_s=30.0,
        expect_cancelled=False,
        capability_timeout_s=args.capability_timeout_s,
        reject_internal_speech=True,
        reject_speech_pattern=[],
        cognitive_runtime=args.goal_driven_runtime == "apply",
        cognitive_apply_lanes=args.cognitive_apply_lanes,
    )


def _validated_live_turn(
    case: TextScenarioCase,
    result: dict[str, Any],
    *,
    assertion_scope: str,
) -> dict[str, Any]:
    scenario_errors = validate_live_text_result(
        case,
        result,
        assertion_scope=assertion_scope,
    )
    combined_errors = list(result.get("errors") or [])
    combined_errors.extend(
        error for error in scenario_errors if error not in combined_errors
    )
    result["errors"] = combined_errors
    result["ok"] = not combined_errors
    user_outcome = result.get("user_outcome")
    if isinstance(user_outcome, dict):
        user_outcome["ok"] = not combined_errors
    result["diagnostic_evaluation"] = diagnostic_evaluation(
        case,
        result,
        combined_errors,
    )
    result["turn_id"] = case.case_id
    result["description"] = case.description
    return result


def _episode_diagnostic_evaluation(
    turn_results: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    evaluations = [
        item.get("diagnostic_evaluation")
        for item in turn_results
        if isinstance(item.get("diagnostic_evaluation"), dict)
    ]
    scores = [int(item.get("overall_score", 0)) for item in evaluations]
    earliest = "none_observed"
    for item in evaluations:
        boundary = str(item.get("earliest_suspect_boundary") or "")
        if boundary and boundary != "none_observed":
            earliest = boundary
            break
    return {
        "passed": not errors,
        "overall_score": round(sum(scores) / len(scores)) if scores else 0,
        "hard_gate_failures": list(errors),
        "metrics": {
            "turn_count": len(turn_results),
            "passed_turn_count": sum(1 for item in turn_results if item.get("ok")),
            "failed_turn_count": sum(1 for item in turn_results if not item.get("ok")),
            "user_outcome_accuracy": round(
                sum(1 for item in turn_results if item.get("ok"))
                / len(turn_results),
                4,
            )
            if turn_results
            else 0.0,
        },
        "turn_scores": [
            {
                "turn_id": result.get("turn_id"),
                "score": evaluation.get("overall_score"),
                "passed": evaluation.get("passed"),
                "earliest_suspect_boundary": evaluation.get(
                    "earliest_suspect_boundary"
                ),
            }
            for result, evaluation in zip(turn_results, evaluations)
        ],
        "earliest_suspect_boundary": earliest,
        "root_cause_report_required": bool(errors),
        "scoring_authority": "acceptance_only_not_runtime_policy",
    }


async def _run_live_case(
    args: argparse.Namespace,
    case: TextScenarioCase,
    case_dir: Path,
) -> dict[str, Any]:
    if not case.turns:
        result = await run_check(_live_case_namespace(args, case, case_dir))
        return _validated_live_turn(
            case,
            result,
            assertion_scope=args.assertion_scope,
        )

    conversation_id = f"ga-live-{case.case_id}"
    namespaces = [
        _live_case_namespace(
            args,
            turn,
            case_dir / f"{index:02d}-{turn.case_id}",
            conversation_id=conversation_id,
        )
        for index, turn in enumerate(case.turns, 1)
    ]
    raw_results = await run_check_sequence(namespaces, evidence_dir=case_dir)
    turn_results: list[dict[str, Any]] = []
    episode_errors: list[str] = []
    for index, turn in enumerate(case.turns):
        if index >= len(raw_results):
            message = (
                f"{turn.case_id}: not run because an earlier live turn failed"
            )
            episode_errors.append(message)
            turn_results.append(
                {
                    "ok": False,
                    "turn_id": turn.case_id,
                    "text": turn.text,
                    "errors": [message],
                    "diagnostic_evaluation": {
                        "passed": False,
                        "overall_score": 0,
                        "hard_gate_failures": [message],
                        "earliest_suspect_boundary": "earlier_turn_failure",
                        "root_cause_report_required": True,
                        "scoring_authority": "acceptance_only_not_runtime_policy",
                    },
                }
            )
            continue
        result = _validated_live_turn(
            turn,
            raw_results[index],
            assertion_scope=args.assertion_scope,
        )
        turn_results.append(result)
        episode_errors.extend(
            f"{turn.case_id}: {error}" for error in result.get("errors") or []
        )
    return {
        "ok": not episode_errors,
        "case_id": case.case_id,
        "text": [turn.text for turn in case.turns],
        "evidence_dir": str(case_dir),
        "conversation_id": conversation_id,
        "errors": episode_errors,
        "turns": turn_results,
        "diagnostic_evaluation": _episode_diagnostic_evaluation(
            turn_results,
            episode_errors,
        ),
    }


async def run_live_text(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.ability_manifest)
    manifest_errors = validate_manifest(
        manifest,
        validate_level_a_sources=False,
    )
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
                _run_live_case(args, case, case_dir),
                timeout=args.case_timeout_s,
            )
        except Exception as exc:
            result = {
                "ok": False,
                "case_id": case.case_id,
                "text": (
                    [turn.text for turn in case.turns]
                    if case.turns
                    else case.text
                ),
                "evidence_dir": str(case_dir),
                "errors": [f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"],
                "diagnostic_evaluation": {
                    "passed": False,
                    "overall_score": 0,
                    "hard_gate_failures": [
                        f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"
                    ],
                    "earliest_suspect_boundary": "live_acceptance_harness",
                    "root_cause_report_required": True,
                    "scoring_authority": "acceptance_only_not_runtime_policy",
                },
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
                "score": (
                    item.get("diagnostic_evaluation") or {}
                ).get("overall_score"),
                "earliest_suspect_boundary": (
                    item.get("diagnostic_evaluation") or {}
                ).get("earliest_suspect_boundary"),
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
        "input_channel": "injected_text",
        "exclusive_host_lock": True,
        "manifest": str(manifest.path),
        "goal_driven_runtime": args.goal_driven_runtime,
        "assertion_scope": args.assertion_scope,
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
    summary["reviewer_packet"] = _write_reviewer_packet(
        root=root,
        run_summary=summary,
        runtime_identity_path=Path(args.runtime_identity).expanduser().resolve(),
    )
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
    parser.add_argument(
        "--runtime-identity",
        type=Path,
        default=ROOT / ".chromie" / "evidence" / "runtime-identity.json",
        help=(
            "Optional digest-bound deployment identity attached to retained "
            "live-text and simulator evidence."
        ),
    )

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
    parser.add_argument(
        "--soridormi-repo",
        default=os.getenv("SORIDORMI_REPO", ""),
        help=(
            "Declared paired Soridormi Git checkout recorded for diagnostic "
            "provenance; this does not identify the source executing behind the "
            "MCP endpoint."
        ),
    )
    parser.add_argument("--language", default="en-US")
    parser.add_argument(
        "--goal-driven-runtime",
        choices=("off", "apply"),
        default="apply",
        help=(
            "Use Goal Association, Fast/Deep Planner-owned communication, "
            "and trusted runtime adapter for live-text cases (default: apply). "
            "Select off only for an explicit legacy Agent compatibility run."
        ),
    )
    parser.add_argument(
        "--cognitive-apply-lanes",
        default="chat,memory,robot_action,tool",
        help="Comma-separated goal-driven apply lanes for live-text cases.",
    )
    parser.add_argument(
        "--assertion-scope",
        choices=("user-outcome", "full"),
        default="user-outcome",
        help=(
            "user-outcome validates observable behavior and LLM integrity while "
            "retaining internal routes/planners as diagnostics; full also enforces "
            "implementation-path expectations."
        ),
    )
    parser.add_argument("--execute", action="store_true", help="Execute live text capabilities through Soridormi/MuJoCo.")
    parser.add_argument("--speaker", action="store_true", help="Play TTS for live text runs. Default is headless.")
    parser.add_argument("--allow-non-sim", action="store_true", help="Permit non-sim Soridormi mode under separate supervision.")
    parser.add_argument(
        "--grant-confirmation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Grant provider/Host-declared confirmation requirements in the "
            "supervised live-text harness, independent of backend type."
        ),
    )
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
    parser.add_argument("--capability-timeout-s", type=float, default=120.0)
    parser.add_argument(
        "--case-timeout-s",
        type=float,
        default=1200.0,
        help=(
            "Outer timeout for one live case. This must exceed the complete "
            "Goal Association + Fast/Deep Planner path."
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
            with _exclusive_orchestrator_lock():
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
