#!/usr/bin/env python3
"""Verify source-bound Cognitive Gateway/Core qualification evidence.

The verifier evaluates retained contracts and execution evidence. It does not
infer user intent from text, select models, alter runtime policy, or declare
release readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.runtime.evidence_identity import (  # noqa: E402
    load_runtime_evidence_identity,
)
from scripts.cognitive_runtime_acceptance import (  # noqa: E402
    _run_provenance,
    _simulator_report,
)

DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "cognitive_gateway_core_qualification_v1.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records_safe_idle(status: Any) -> bool:
    return bool(
        isinstance(status, dict)
        and status.get("safe_idle") is True
        and "active_task" in status
        and status.get("active_task") is None
        and status.get("emergency_stop") is False
        and status.get("fallen") is False
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        events.append(value)
    return events


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _event_by_type(
    events: list[dict[str, Any]],
    *,
    sid: str,
    event_type: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in events
        if str(item.get("sid") or "") == sid
        and str(item.get("event") or "") == event_type
    ]


def _goal_ids(event: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    terminal = event.get("terminal_plan")
    if isinstance(terminal, dict):
        values.update(str(item) for item in terminal.get("goal_ids") or [] if item)
    association = event.get("goal_association")
    if isinstance(association, dict):
        for goal in association.get("new_goals") or []:
            if isinstance(goal, dict) and goal.get("goal_id"):
                values.add(str(goal["goal_id"]))
    return values


def _target_goal_ids(event: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    association = event.get("goal_association")
    if not isinstance(association, dict):
        return values
    for item in association.get("associations") or []:
        if isinstance(item, dict):
            values.update(str(value) for value in item.get("target_goal_ids") or [] if value)
    return values


def _terminal_skills(event: dict[str, Any]) -> list[str]:
    terminal = event.get("terminal_plan")
    if not isinstance(terminal, dict):
        return []
    return [str(item) for item in terminal.get("skill_ids") or []]


def _validate_runtime_identity(
    identity: dict[str, Any],
    *,
    expected_revision: str | None,
) -> list[str]:
    errors: list[str] = []
    chromie = identity.get("chromie")
    runtime_profile = identity.get("runtime_profile")
    deployment = identity.get("deployment")
    manifests = identity.get("capability_manifests")
    if not isinstance(chromie, dict):
        return ["runtime identity has no Chromie object"]
    if chromie.get("dirty") is not False:
        errors.append("runtime identity does not record a clean Chromie worktree")
    revision = str(chromie.get("revision") or "")
    if expected_revision and revision != expected_revision:
        errors.append(
            f"runtime identity revision {revision!r} does not match expected {expected_revision!r}"
        )
    if not isinstance(runtime_profile, dict):
        errors.append("runtime identity has no runtime profile")
    else:
        if not runtime_profile.get("fingerprint"):
            errors.append("runtime identity has no runtime profile fingerprint")
        if not runtime_profile.get("sha256"):
            errors.append("runtime identity has no runtime profile digest")
        if not isinstance(runtime_profile.get("models"), dict):
            errors.append("runtime identity has no model topology")
    required_services = {
        "chromie-agent",
        "chromie-llm",
        "chromie-asr",
        "chromie-tts",
    }
    if not isinstance(deployment, dict) or deployment.get("complete") is not True:
        errors.append("runtime identity does not bind every required running service image")
    elif not isinstance(deployment.get("service_images"), dict):
        errors.append("runtime identity service image map is invalid")
    else:
        service_images = deployment["service_images"]
        missing_services = sorted(required_services - set(service_images))
        if missing_services:
            errors.append(
                "runtime identity is missing required services: "
                + ", ".join(missing_services)
            )
        for service in sorted(required_services.intersection(service_images)):
            item = service_images.get(service)
            if not isinstance(item, dict) or not str(item.get("image_id") or "").strip():
                errors.append(f"runtime identity has no immutable image ID for {service}")
        agent = service_images.get("chromie-agent")
        if isinstance(agent, dict) and isinstance(runtime_profile, dict):
            effective_runtime = agent.get("effective_runtime")
            if not isinstance(effective_runtime, dict):
                errors.append("runtime identity has no effective Agent runtime identity")
            elif effective_runtime.get("CHROMIE_RUNTIME_ENV_FINGERPRINT") != runtime_profile.get(
                "fingerprint"
            ):
                errors.append(
                    "running Agent runtime fingerprint does not match the retained profile"
                )
            effective_models = agent.get("effective_models")
            orchestrator_runtime = identity.get("orchestrator_runtime")
            launcher_models = (
                orchestrator_runtime.get("effective_models")
                if isinstance(orchestrator_runtime, dict)
                else None
            )
            if not isinstance(effective_models, dict):
                errors.append("runtime identity has no effective Agent model topology")
            elif not isinstance(launcher_models, dict) or not launcher_models:
                errors.append("runtime identity has no launcher-effective model topology")
            else:
                required_model_keys = {
                    "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL",
                    "AGENT_GOAL_INTERPRETER_MODEL",
                    "AGENT_GOAL_ASSOCIATION_MODEL",
                    "AGENT_FAST_PLANNER_MODEL",
                    "AGENT_DEEP_PLANNER_MODEL",
                    "AGENT_RESPONSE_COMPOSER_MODEL",
                    "AGENT_TOOL_RESULT_INTERPRETER_MODEL",
                }
                for key in sorted(required_model_keys):
                    expected = launcher_models.get(key)
                    actual = effective_models.get(key)
                    if not expected:
                        errors.append(
                            f"launcher-effective topology is missing model {key}"
                        )
                    elif actual != expected:
                        errors.append(
                            f"running Agent model {key} does not match the "
                            "launcher-effective topology"
                        )
    if not isinstance(manifests, list) or not manifests:
        errors.append("runtime identity has no capability manifest identity")
    else:
        for manifest in manifests:
            if not isinstance(manifest, dict) or not manifest.get("sha256"):
                errors.append("runtime identity contains an unbound capability manifest")
                break
    return errors


def _validate_turn(
    *,
    turn: dict[str, Any],
    sid: str,
    events: list[dict[str, Any]],
    identity_sha256: str,
    prior_turn_events: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    expectations = turn.get("expect")
    if not isinstance(expectations, dict):
        return {}, ["turn expectation must be an object"]
    gateway_events = _event_by_type(
        events,
        sid=sid,
        event_type="cognitive_gateway_admission",
    )
    runtime_events = _event_by_type(
        events,
        sid=sid,
        event_type="cognitive_runtime_resolution",
    )
    outcome_events = _event_by_type(
        events,
        sid=sid,
        event_type="cognitive_execution_outcome",
    )
    if len(gateway_events) != 1:
        errors.append(
            f"expected exactly one Gateway admission event, found {len(gateway_events)}"
        )
        gateway = gateway_events[-1] if gateway_events else {}
    else:
        gateway = gateway_events[0]

    expected_admission = expectations.get("gateway_admission")
    if expected_admission and gateway.get("admission") != expected_admission:
        errors.append(
            f"Gateway admission {gateway.get('admission')!r} != {expected_admission!r}"
        )
    reflex = gateway.get("reflex")
    if not isinstance(reflex, dict):
        reflex = {}
    expected_reflex_action = expectations.get("reflex_action")
    if expected_reflex_action and reflex.get("action") != expected_reflex_action:
        errors.append(
            f"reflex action {reflex.get('action')!r} != {expected_reflex_action!r}"
        )
    expected_cancellation_scope = expectations.get("cancellation_scope")
    if (
        expected_cancellation_scope
        and reflex.get("cancellation_scope") != expected_cancellation_scope
    ):
        errors.append(
            "cancellation scope "
            f"{reflex.get('cancellation_scope')!r} != {expected_cancellation_scope!r}"
        )
    reference = gateway.get("run_identity")
    if not isinstance(reference, dict) or reference.get("identity_sha256") != identity_sha256:
        errors.append("Gateway event is not bound to the retained runtime identity")

    core_entered = bool(expectations.get("core_entered"))
    if core_entered and len(runtime_events) != 1:
        errors.append(
            f"expected exactly one Core runtime event, found {len(runtime_events)}"
        )
    if not core_entered and runtime_events:
        errors.append("suppressed turn entered the Cognitive Core")
    runtime = runtime_events[-1] if runtime_events else {}
    if runtime:
        reference = runtime.get("run_identity")
        if not isinstance(reference, dict) or reference.get("identity_sha256") != identity_sha256:
            errors.append("Core runtime event is not bound to the retained runtime identity")
        if expectations.get("runtime_status") and runtime.get("status") != expectations.get(
            "runtime_status"
        ):
            errors.append(
                f"runtime status {runtime.get('status')!r} != {expectations.get('runtime_status')!r}"
            )
        if expectations.get("runtime_lane") and runtime.get("lane") != expectations.get(
            "runtime_lane"
        ):
            errors.append(
                f"runtime lane {runtime.get('lane')!r} != {expectations.get('runtime_lane')!r}"
            )
        expected_authority = expectations.get("core_authority")
        core_interpretation = runtime.get("core_interpretation")
        actual_authority = (
            core_interpretation.get("authority")
            if isinstance(core_interpretation, dict)
            else None
        )
        if expected_authority and actual_authority != expected_authority:
            errors.append(
                f"Core authority {actual_authority!r} != {expected_authority!r}"
            )
        terminal_skills = _terminal_skills(runtime)
        for skill in expectations.get("required_terminal_skills") or []:
            if skill not in terminal_skills:
                errors.append(f"required terminal skill {skill!r} is missing")
        for skill in expectations.get("forbidden_terminal_skills") or []:
            if skill in terminal_skills:
                errors.append(f"forbidden repeated terminal skill {skill!r} was planned")

    for context_type in expectations.get("required_context_reference_types") or []:
        if context_type not in set(gateway.get("context_reference_types") or []):
            errors.append(f"Gateway context is missing reference type {context_type!r}")

    if expectations.get("require_completed_outcome"):
        completed = False
        for outcome in outcome_events:
            reference = outcome.get("run_identity")
            if not isinstance(reference, dict) or reference.get("identity_sha256") != identity_sha256:
                errors.append("execution outcome is not bound to the retained runtime identity")
                continue
            bundle = outcome.get("outcome_bundle")
            if isinstance(bundle, dict) and bundle.get("aggregate_status") == "completed":
                completed = True
        if not completed:
            errors.append("turn has no completed execution outcome bundle")

    continuity_key = str(expectations.get("require_goal_continuity_from") or "")
    if continuity_key:
        prior = prior_turn_events.get(continuity_key)
        if prior is None:
            errors.append(f"continuity source turn {continuity_key!r} is unavailable")
        elif not runtime:
            errors.append("continuity turn has no Core runtime event")
        else:
            prior_runtime = prior.get("runtime") or {}
            prior_goals = _goal_ids(prior_runtime)
            targets = _target_goal_ids(runtime)
            if not prior_goals:
                errors.append("continuity source turn has no retained goal IDs")
            elif not prior_goals.intersection(targets):
                errors.append(
                    "follow-up Goal Association does not target the prior weather goal"
                )
            if gateway.get("conversation_id") != (prior.get("gateway") or {}).get(
                "conversation_id"
            ):
                errors.append("follow-up turn does not retain the same conversation ID")

    report = {
        "sid": sid,
        "gateway": gateway,
        "runtime": runtime,
        "outcome_count": len(outcome_events),
        "passed": not errors,
        "errors": errors,
    }
    return report, errors


def _validate_cancellation_summary(
    summary: dict[str, Any],
    *,
    summary_path: Path,
    expectations: dict[str, Any],
    identity_sha256: str,
    expected_chromie_revision: str | None,
    expected_soridormi_revision: str | None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    expected_command = str(expectations.get("command_text") or "")
    expected_interrupt = str(expectations.get("interrupt_text") or "")
    if summary.get("ok") is not True:
        errors.append("cancellation summary records one or more execution errors")
    if str(summary.get("text") or "") != expected_command:
        errors.append("cancellation command text does not match the manifest")
    interrupt = summary.get("interrupt")
    if not isinstance(interrupt, dict):
        interrupt = {}
        errors.append("cancellation summary has no interrupt evidence")
    if str(interrupt.get("text") or "") != expected_interrupt:
        errors.append("cancellation interrupt text does not match the manifest")
    expected_interrupt_sha = hashlib.sha256(expected_interrupt.encode("utf-8")).hexdigest()
    if interrupt.get("text_sha256") != expected_interrupt_sha:
        errors.append("cancellation interrupt text digest does not match the manifest")

    interaction = summary.get("interaction_response")
    interaction_id = (
        str(interaction.get("interaction_id") or "")
        if isinstance(interaction, dict)
        else ""
    )
    observation = interrupt.get("provider_observation_before_interrupt")
    requests = (
        observation.get("requests")
        if isinstance(observation, dict) and isinstance(observation.get("requests"), list)
        else []
    )
    required_skill = str(expectations.get("required_skill") or "")
    started_requests = [
        item
        for item in requests
        if isinstance(item, dict)
        and item.get("interaction_id") == interaction_id
        and item.get("skill_id") == required_skill
        and item.get("provider_started") is True
        and item.get("task_done") is False
    ]
    if expectations.get("provider_started_required") is True and not started_requests:
        errors.append("interrupt was not bound to a started required provider request")
    if started_requests and not any(item.get("source_goal_ids") for item in started_requests):
        errors.append("started cancellation request has no active semantic Goal binding")

    execution = summary.get("execution")
    execution_status = execution.get("status") if isinstance(execution, dict) else None
    expected_status = str(expectations.get("execution_status") or "")
    if expected_status and execution_status != expected_status:
        errors.append(
            f"cancellation execution status {execution_status!r} != {expected_status!r}"
        )
    results = (
        execution.get("results")
        if isinstance(execution, dict) and isinstance(execution.get("results"), list)
        else []
    )
    cancelled_results = [
        item
        for item in results
        if isinstance(item, dict)
        and item.get("skill_id") == required_skill
        and item.get("status") == "cancelled"
        and str(item.get("reason_code") or "").startswith("cancelled")
    ]
    if not cancelled_results:
        errors.append("required Soridormi request has no trusted cancelled result")

    status_before = summary.get("status_before")
    status_after = summary.get("status_after")
    for label, status in (("before", status_before), ("after", status_after)):
        if not isinstance(status, dict) or status.get("mode") != "sim" or status.get("backend") != "runtime":
            errors.append(f"cancellation {label} status is not Soridormi runtime sim")
    if expectations.get("safe_idle_required") is True:
        if not _records_safe_idle(status_before):
            errors.append("cancellation run lacks explicit safe idle before execution")
        if not _records_safe_idle(status_after):
            errors.append("cancellation run lacks explicit safe idle after interruption")

    provenance = _run_provenance(summary)
    if provenance.get("chromie_revision") != expected_chromie_revision:
        errors.append("cancellation Chromie revision does not match the evaluated source")
    if provenance.get("chromie_dirty") is not False:
        errors.append("cancellation run did not record a clean Chromie worktree")
    if provenance.get("soridormi_revision") != expected_soridormi_revision:
        errors.append("cancellation Soridormi revision does not match the expected source")
    if provenance.get("soridormi_checkout_revision") != expected_soridormi_revision:
        errors.append("cancellation run does not bind the paired Soridormi checkout")
    if provenance.get("soridormi_checkout_dirty") is not False:
        errors.append("cancellation run did not record a clean paired Soridormi checkout")
    if provenance.get("soridormi_source_binding") != "endpoint_reported_revision":
        errors.append("cancellation run lacks endpoint-reported Soridormi source binding")
    if provenance.get("soridormi_endpoint_revision") != expected_soridormi_revision:
        errors.append("cancellation endpoint revision does not match Soridormi source")
    if provenance.get("semantic_runtime_path") != "goal_driven_cognitive_runtime":
        errors.append("cancellation run did not use the Goal-Driven Cognitive Runtime")
    if provenance.get("cognitive_runtime_mode") != "apply":
        errors.append("cancellation run did not use cognitive runtime apply mode")
    if provenance.get("cognitive_runtime_selected_for_route") is not True:
        errors.append("cancellation run did not select the cognitive runtime")
    provenance_payload = summary.get("provenance")
    identity_ref = (
        provenance_payload.get("runtime_identity")
        if isinstance(provenance_payload, dict)
        else None
    )
    if (
        not isinstance(identity_ref, dict)
        or identity_ref.get("identity_sha256") != identity_sha256
        or identity_ref.get("complete") is not True
    ):
        errors.append("cancellation summary is not bound to the retained runtime identity")

    cognitive_events = Path(str(summary.get("cognitive_events") or ""))
    if not cognitive_events.is_absolute():
        cognitive_events = (summary_path.parent / cognitive_events).resolve()
    if not cognitive_events.is_file():
        errors.append("cancellation cognitive event file is missing")
        events: list[dict[str, Any]] = []
    else:
        events = _read_jsonl(cognitive_events)
    interrupt_sid = str(interrupt.get("sid") or "")
    gateway_events = _event_by_type(
        events,
        sid=interrupt_sid,
        event_type="cognitive_gateway_admission",
    )
    if len(gateway_events) != 1:
        errors.append(
            "cancellation interrupt requires exactly one Gateway admission event"
        )
        gateway = gateway_events[-1] if gateway_events else {}
    else:
        gateway = gateway_events[0]
    if gateway.get("admission") != expectations.get("gateway_admission"):
        errors.append("cancellation Gateway admission does not match the manifest")
    reflex = gateway.get("reflex") if isinstance(gateway.get("reflex"), dict) else {}
    if reflex.get("action") != expectations.get("reflex_action"):
        errors.append("cancellation reflex action does not match the manifest")
    if reflex.get("cancellation_scope") != expectations.get("cancellation_scope"):
        errors.append("cancellation scope does not match the manifest")
    identity_ref = gateway.get("run_identity")
    if not isinstance(identity_ref, dict) or identity_ref.get("identity_sha256") != identity_sha256:
        errors.append("cancellation Gateway event is not runtime-identity bound")
    runtime_events = _event_by_type(
        events,
        sid=interrupt_sid,
        event_type="cognitive_runtime_resolution",
    )
    if runtime_events:
        errors.append("deterministic cancellation interrupt entered ordinary Core planning")

    report = {
        "passed": not errors,
        "interaction_id": interaction_id,
        "provider_started_requests": started_requests,
        "execution_status": execution_status,
        "cancelled_results": cancelled_results,
        "safe_idle_before": _records_safe_idle(status_before),
        "safe_idle_after": _records_safe_idle(status_after),
        "gateway": gateway,
        "provenance": provenance,
        "errors": errors,
    }
    return report, errors


def _validate_human_review(
    review: dict[str, Any],
    *,
    manifest: dict[str, Any],
    identity_sha256: str,
    live_summary_path: Path,
    mujoco_summary_path: Path,
    cancellation_summary_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if review.get("schema_version") != 1:
        errors.append("human review schema_version must be 1")
    if review.get("qualification_id") != manifest.get("qualification_id"):
        errors.append("human review qualification ID does not match the manifest")
    if review.get("runtime_identity_sha256") != identity_sha256:
        errors.append("human review is not bound to the retained runtime identity")
    artifacts = review.get("artifact_sha256")
    expected_artifacts = {
        "live_summary": _file_sha256(live_summary_path),
        "mujoco_summary": _file_sha256(mujoco_summary_path),
        "cancellation_summary": _file_sha256(cancellation_summary_path),
    }
    if not isinstance(artifacts, dict):
        errors.append("human review has no artifact fingerprint map")
    else:
        for key, expected in expected_artifacts.items():
            if artifacts.get(key) != expected:
                errors.append(f"human review artifact fingerprint mismatch: {key}")
    if not str(review.get("reviewer") or "").strip():
        errors.append("human review has no reviewer identity")
    try:
        datetime.fromisoformat(str(review.get("reviewed_at") or "").replace("Z", "+00:00"))
    except ValueError:
        errors.append("human review reviewed_at is not a valid date-time")
    expectations = manifest.get("human_review_expectations")
    required_checks = (
        expectations.get("required_checks")
        if isinstance(expectations, dict)
        and isinstance(expectations.get("required_checks"), list)
        else []
    )
    checks = review.get("checks")
    if not isinstance(checks, dict):
        errors.append("human review has no qualitative checks")
        checks = {}
    for key in required_checks:
        if checks.get(key) != "pass":
            errors.append(f"human review check {key!r} is not pass")
    if review.get("decision") != "approve":
        errors.append("human review decision is not approve")
    return {
        "passed": not errors,
        "decision": review.get("decision"),
        "reviewer": review.get("reviewer"),
        "checks": checks,
        "findings": review.get("findings") or [],
        "errors": errors,
    }, errors


def verify(
    *,
    manifest_path: Path,
    live_summary_path: Path,
    runtime_identity_path: Path,
    cognitive_events_path: Path | None = None,
    mujoco_summary_path: Path | None = None,
    cancellation_summary_path: Path | None = None,
    human_review_path: Path | None = None,
    expected_chromie_revision: str | None = None,
    expected_soridormi_revision: str | None = None,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    summary = _read_json(live_summary_path)
    identity = load_runtime_evidence_identity(runtime_identity_path)
    if identity is None:
        raise ValueError("runtime identity is missing")
    if expected_chromie_revision is None:
        expected_chromie_revision = _git_revision()
    if expected_soridormi_revision is None:
        manifests = identity.get("capability_manifests")
        if isinstance(manifests, list):
            for item in manifests:
                if isinstance(item, dict) and item.get("upstream_revision"):
                    expected_soridormi_revision = str(item["upstream_revision"])
                    break

    events_path = cognitive_events_path or Path(str(summary.get("cognitive_events") or ""))
    if not events_path.is_absolute():
        events_path = (live_summary_path.parent / events_path).resolve()
    events = _read_jsonl(events_path)
    errors = _validate_runtime_identity(
        identity,
        expected_revision=expected_chromie_revision,
    )
    if summary.get("qualification_id") != manifest.get("qualification_id"):
        errors.append("live summary qualification ID does not match the manifest")
    if summary.get("ok") is not True:
        errors.append("live summary records one or more execution errors")
    summary_identity = summary.get("runtime_identity")
    if not isinstance(summary_identity, dict) or summary_identity.get(
        "identity_sha256"
    ) != identity["identity_sha256"]:
        errors.append("live summary is not bound to the retained runtime identity")

    scenario_summaries = {
        str(item.get("scenario_id")): item
        for item in summary.get("scenarios") or []
        if isinstance(item, dict) and item.get("scenario_id")
    }
    case_reports: list[dict[str, Any]] = []
    for scenario in manifest.get("scenarios") or []:
        if not isinstance(scenario, dict):
            errors.append("manifest scenario is not an object")
            continue
        scenario_id = str(scenario.get("scenario_id") or "")
        retained = scenario_summaries.get(scenario_id)
        if retained is None:
            errors.append(f"missing retained scenario {scenario_id!r}")
            continue
        retained_turns = {
            str(item.get("turn_key")): item
            for item in retained.get("turns") or []
            if isinstance(item, dict) and item.get("turn_key")
        }
        prior_events: dict[str, dict[str, Any]] = {}
        turn_reports: list[dict[str, Any]] = []
        scenario_errors: list[str] = []
        for turn in scenario.get("turns") or []:
            if not isinstance(turn, dict):
                scenario_errors.append("manifest turn is not an object")
                continue
            turn_key = str(turn.get("turn_key") or "")
            retained_turn = retained_turns.get(turn_key)
            if retained_turn is None:
                scenario_errors.append(f"missing retained turn {turn_key!r}")
                continue
            sid = str(retained_turn.get("sid") or "")
            expected_text_digest = hashlib.sha256(
                str(turn.get("text") or "").encode("utf-8")
            ).hexdigest()
            if retained_turn.get("text_sha256") != expected_text_digest:
                scenario_errors.append(
                    f"{turn_key}: retained text digest does not match the manifest"
                )
            report, turn_errors = _validate_turn(
                turn=turn,
                sid=sid,
                events=events,
                identity_sha256=identity["identity_sha256"],
                prior_turn_events=prior_events,
            )
            report["turn_key"] = turn_key
            report["text_sha256"] = retained_turn.get("text_sha256")
            turn_reports.append(report)
            scenario_errors.extend(f"{turn_key}: {item}" for item in turn_errors)
            prior_events[turn_key] = {
                "gateway": report.get("gateway") or {},
                "runtime": report.get("runtime") or {},
            }
        case_reports.append(
            {
                "scenario_id": scenario_id,
                "passed": not scenario_errors,
                "errors": scenario_errors,
                "turns": turn_reports,
            }
        )
        errors.extend(f"{scenario_id}: {item}" for item in scenario_errors)

    simulator = None
    simulator_required = bool(
        isinstance(manifest.get("simulator_expectations"), dict)
        and manifest["simulator_expectations"].get("required") is True
    )
    if mujoco_summary_path is None:
        if simulator_required:
            errors.append("required source-bound MuJoCo summary is missing")
    else:
        simulator_summary = _read_json(mujoco_summary_path)
        simulator = _simulator_report(
            simulator_summary,
            expected_chromie_revision=expected_chromie_revision,
            expected_soridormi_revision=expected_soridormi_revision,
        )
        if simulator is None or simulator.get("target_validated") is not True:
            errors.append("MuJoCo evidence is not source-bound target validation")
        else:
            simulator_expectations = manifest.get("simulator_expectations")
            if not isinstance(simulator_expectations, dict):
                simulator_expectations = {}
            cognitive = simulator_summary.get("cognitive_runtime")
            terminal = (
                cognitive.get("terminal_plan")
                if isinstance(cognitive, dict)
                and isinstance(cognitive.get("terminal_plan"), dict)
                else {}
            )
            terminal_skills = [str(item) for item in terminal.get("skill_ids") or []]
            minimum_skills = int(
                simulator_expectations.get("minimum_terminal_skill_count") or 0
            )
            if len(terminal_skills) < minimum_skills:
                errors.append(
                    "MuJoCo terminal plan contains "
                    f"{len(terminal_skills)} skills; expected at least {minimum_skills}"
                )
            for skill in simulator_expectations.get("required_terminal_skills") or []:
                if skill not in terminal_skills:
                    errors.append(
                        f"MuJoCo terminal plan is missing required skill {skill!r}"
                    )
            minimum_completed = int(
                simulator_expectations.get("minimum_completed_soridormi_results") or 0
            )
            if int(simulator.get("completed_soridormi_results") or 0) < minimum_completed:
                errors.append(
                    "MuJoCo evidence contains "
                    f"{simulator.get('completed_soridormi_results', 0)} completed "
                    f"Soridormi results; expected at least {minimum_completed}"
                )
            provenance = simulator_summary.get("provenance")
            runtime_reference = (
                provenance.get("runtime_identity")
                if isinstance(provenance, dict)
                else None
            )
            if (
                not isinstance(runtime_reference, dict)
                or runtime_reference.get("identity_sha256")
                != identity["identity_sha256"]
                or runtime_reference.get("complete") is not True
            ):
                errors.append(
                    "MuJoCo summary is not bound to the retained runtime identity"
                )

    cancellation = None
    cancellation_expectations = manifest.get("cancellation_expectations")
    cancellation_required = bool(
        isinstance(cancellation_expectations, dict)
        and cancellation_expectations.get("required") is True
    )
    if cancellation_summary_path is None:
        if cancellation_required:
            errors.append("required active-goal cancellation summary is missing")
    else:
        cancellation_summary = _read_json(cancellation_summary_path)
        cancellation, cancellation_errors = _validate_cancellation_summary(
            cancellation_summary,
            summary_path=cancellation_summary_path,
            expectations=(
                cancellation_expectations
                if isinstance(cancellation_expectations, dict)
                else {}
            ),
            identity_sha256=identity["identity_sha256"],
            expected_chromie_revision=expected_chromie_revision,
            expected_soridormi_revision=expected_soridormi_revision,
        )
        errors.extend(f"active_goal_cancellation: {item}" for item in cancellation_errors)

    human_review = None
    human_review_expectations = manifest.get("human_review_expectations")
    human_review_required = bool(
        isinstance(human_review_expectations, dict)
        and human_review_expectations.get("required") is True
    )
    if human_review_path is None:
        if human_review_required:
            errors.append("required fingerprint-bound human review is missing")
    elif mujoco_summary_path is None or cancellation_summary_path is None:
        errors.append(
            "human review cannot be validated without MuJoCo and cancellation summaries"
        )
    else:
        review_payload = _read_json(human_review_path)
        human_review, human_review_errors = _validate_human_review(
            review_payload,
            manifest=manifest,
            identity_sha256=identity["identity_sha256"],
            live_summary_path=live_summary_path,
            mujoco_summary_path=mujoco_summary_path,
            cancellation_summary_path=cancellation_summary_path,
        )
        errors.extend(f"human_review: {item}" for item in human_review_errors)

    required_scenarios = {
        str(item.get("scenario_id"))
        for item in manifest.get("scenarios") or []
        if isinstance(item, dict)
    }
    retained_scenarios = set(scenario_summaries)
    missing = sorted(required_scenarios - retained_scenarios)
    unexpected = sorted(retained_scenarios - required_scenarios)
    if missing:
        errors.append("missing scenarios: " + ", ".join(missing))
    if unexpected:
        errors.append("unexpected scenarios: " + ", ".join(unexpected))

    identity_valid = not _validate_runtime_identity(
        identity,
        expected_revision=expected_chromie_revision,
    )
    live_valid = all(item["passed"] for item in case_reports) and not missing and not unexpected
    simulator_valid = bool(simulator and simulator.get("target_validated") is True)
    cancellation_valid = bool(cancellation and cancellation.get("passed") is True)
    human_review_approved = bool(human_review and human_review.get("passed") is True)
    closure_eligible = bool(
        not errors
        and identity_valid
        and live_valid
        and simulator_valid
        and cancellation_valid
        and human_review_approved
    )

    return {
        "schema_version": 2,
        "qualification_id": manifest.get("qualification_id"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "runtime_identity_sha256": identity["identity_sha256"],
        "expected_provenance": {
            "chromie_revision": expected_chromie_revision,
            "soridormi_revision": expected_soridormi_revision,
        },
        "scenario_coverage": {
            "required": sorted(required_scenarios),
            "retained": sorted(retained_scenarios),
            "missing": missing,
            "unexpected": unexpected,
        },
        "live_text": {
            "passed": live_valid,
            "scenarios": case_reports,
        },
        "simulator": simulator,
        "active_goal_cancellation": cancellation,
        "human_review": human_review,
        "qualification": {
            "implementation_verified": True,
            "runtime_identity_valid": identity_valid,
            "live_text_target_validated": live_valid and identity_valid,
            "simulator_target_validated": simulator_valid,
            "active_goal_cancellation_target_validated": cancellation_valid,
            "human_review_approved": human_review_approved,
            "release_qualified": False,
            "human_review_required": True,
            "issue_closure_eligible": closure_eligible,
        },
        "errors": errors,
        "passed": not errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--live-summary", type=Path, required=True)
    parser.add_argument("--runtime-identity", type=Path, required=True)
    parser.add_argument("--cognitive-events", type=Path)
    parser.add_argument("--mujoco-summary", type=Path)
    parser.add_argument("--cancellation-summary", type=Path)
    parser.add_argument("--human-review", type=Path)
    parser.add_argument("--expected-chromie-revision")
    parser.add_argument("--expected-soridormi-revision")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify(
            manifest_path=args.manifest.expanduser().resolve(),
            live_summary_path=args.live_summary.expanduser().resolve(),
            runtime_identity_path=args.runtime_identity.expanduser().resolve(),
            cognitive_events_path=(
                args.cognitive_events.expanduser().resolve()
                if args.cognitive_events
                else None
            ),
            mujoco_summary_path=(
                args.mujoco_summary.expanduser().resolve()
                if args.mujoco_summary
                else None
            ),
            cancellation_summary_path=(
                args.cancellation_summary.expanduser().resolve()
                if args.cancellation_summary
                else None
            ),
            human_review_path=(
                args.human_review.expanduser().resolve()
                if args.human_review
                else None
            ),
            expected_chromie_revision=args.expected_chromie_revision,
            expected_soridormi_revision=args.expected_soridormi_revision,
        )
    except Exception as exc:
        print(f"[gateway-core-qualification][error] {exc}", file=sys.stderr)
        return 2
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
