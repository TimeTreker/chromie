#!/usr/bin/env python3
"""Verify source-bound live Agent Skill selection and weather execution evidence.

The verifier reads retained runtime events after execution. It does not select
Agent Skills, infer user intent, alter runtime policy, approve human review, or
promote the bundle to release evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "agent_skill_weather_qualification_v1.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        events.append(value)
    return events


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(root: Path = ROOT) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _events_for(
    events: Iterable[dict[str, Any]],
    *,
    sid: str,
    event_type: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in events
        if item.get("sid") == sid and item.get("event") == event_type
    ]


def _ordered_contains(actual: list[str], required: list[str]) -> bool:
    if not required:
        return True
    cursor = 0
    for item in actual:
        if item == required[cursor]:
            cursor += 1
            if cursor == len(required):
                return True
    return False


def _plan_skill_ids(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return []
    values = plan.get("selected_agent_skills")
    if not isinstance(values, list):
        return []
    return [
        str(item.get("agent_skill_id") or "").strip()
        for item in values
        if isinstance(item, dict) and str(item.get("agent_skill_id") or "").strip()
    ]


def _validate_provenance(plan: Any, errors: list[str], *, label: str) -> None:
    if not isinstance(plan, dict):
        return
    values = plan.get("selected_agent_skills")
    if not isinstance(values, list):
        return
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append(f"{label}: Agent Skill provenance {index} is not an object")
            continue
        for field in (
            "selection_id",
            "disclosure_id",
            "disclosure_digest",
            "selected_by_agent_role",
            "agent_skill_id",
            "version",
            "projection",
            "content_digest",
            "projection_digest",
        ):
            if not str(item.get(field) or "").strip():
                errors.append(f"{label}: Agent Skill provenance is missing {field}")
        forbidden = {"content", "source", "path", "package_path", "projection_content"}
        leaked = sorted(forbidden.intersection(item))
        if leaked:
            errors.append(
                f"{label}: Agent Skill provenance leaks content/path fields: {', '.join(leaked)}"
            )


def _capability_ids(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return []
    values = plan.get("capability_ids")
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _goal_ids(plan: Any) -> set[str]:
    if not isinstance(plan, dict):
        return set()
    values = plan.get("goal_ids")
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def _target_goal_ids(runtime_event: dict[str, Any]) -> set[str]:
    association = runtime_event.get("goal_association")
    if not isinstance(association, dict):
        return set()
    values: set[str] = set()
    items = association.get("associations")
    if not isinstance(items, list):
        return values
    for item in items:
        if not isinstance(item, dict):
            continue
        targets = item.get("target_goal_ids")
        if isinstance(targets, list):
            values.update(str(value).strip() for value in targets if str(value).strip())
    return values


def _validate_weather_observation(
    outcome: dict[str, Any] | None,
    expectation: dict[str, Any],
    *,
    capability_id: str,
    errors: list[str],
    label: str,
) -> None:
    if outcome is None:
        errors.append(f"{label}: required execution outcome is missing")
        return
    bundle = outcome.get("outcome_bundle")
    if not isinstance(bundle, dict):
        errors.append(f"{label}: execution outcome bundle is missing")
        return
    if bundle.get("aggregate_status") != "completed":
        errors.append(
            f"{label}: execution aggregate status is {bundle.get('aggregate_status')!r}, expected 'completed'"
        )
    evidence = bundle.get("evidence")
    if not isinstance(evidence, list):
        errors.append(f"{label}: execution evidence is missing")
        return
    matches = [
        item
        for item in evidence
        if isinstance(item, dict) and item.get("capability_id") == capability_id
    ]
    if not matches:
        errors.append(f"{label}: no {capability_id} execution evidence was retained")
        return
    completed = [item for item in matches if item.get("status") == "completed"]
    if not completed:
        errors.append(f"{label}: {capability_id} did not complete")
        return
    item = completed[-1]
    if not str(item.get("provider_id") or "").strip():
        errors.append(f"{label}: completed weather evidence has no provider_id")
    observation = item.get("observation")
    if not isinstance(observation, dict):
        errors.append(f"{label}: completed weather evidence has no observation")
        return
    if observation.get("status") != "available" or observation.get("schema_validated") is not True:
        errors.append(f"{label}: weather observation is not available and schema validated")
        return
    data = observation.get("data")
    if not isinstance(data, dict):
        errors.append(f"{label}: weather observation data is missing")
        return
    location = str(data.get("location") or "")
    required_terms = expectation.get("location_contains_any")
    if isinstance(required_terms, list) and required_terms:
        if not any(str(term) in location for term in required_terms):
            errors.append(
                f"{label}: weather location {location!r} does not contain any required locality"
            )
    forbidden_terms = expectation.get("forbid_location_contains")
    if isinstance(forbidden_terms, list):
        for term in forbidden_terms:
            if str(term) and str(term) in location:
                errors.append(
                    f"{label}: weather location {location!r} contains forbidden locality {term!r}"
                )
    if expectation.get("require_source") is True and not str(data.get("source") or "").strip():
        errors.append(f"{label}: weather observation has no source identity")


def _turn_map(summary: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    scenarios = summary.get("scenarios")
    if not isinstance(scenarios, list):
        return mapped
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("scenario_id") or "")
        turns = scenario.get("turns")
        if not isinstance(turns, list):
            continue
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            key = str(turn.get("turn_key") or "")
            if scenario_id and key:
                mapped[(scenario_id, key)] = turn
    return mapped


def _validate_review(
    review_path: Path | None,
    *,
    manifest: dict[str, Any],
    runtime_identity_path: Path,
    live_summary_path: Path,
    cognitive_events_path: Path,
    errors: list[str],
) -> bool:
    if review_path is None or not review_path.is_file():
        return False
    review = _read_json(review_path)
    if review.get("qualification_id") != manifest.get("qualification_id"):
        errors.append("human review qualification_id does not match the manifest")
    artifact_sha = review.get("artifact_sha256")
    expected = {
        "runtime_identity": _sha256(runtime_identity_path),
        "live_summary": _sha256(live_summary_path),
        "cognitive_events": _sha256(cognitive_events_path),
    }
    if not isinstance(artifact_sha, dict):
        errors.append("human review has no artifact_sha256 map")
    else:
        for name, digest in expected.items():
            if artifact_sha.get(name) != digest:
                errors.append(f"human review fingerprint mismatch for {name}")
    checks = review.get("checks")
    required_checks = manifest.get("human_review_checks")
    if not isinstance(checks, dict):
        errors.append("human review checks must be an object")
    elif isinstance(required_checks, list):
        for check in required_checks:
            if checks.get(str(check)) != "approved":
                errors.append(f"human review check {check!r} is not approved")
    if review.get("decision") != "approved":
        errors.append("human review decision is not approved")
    if not str(review.get("reviewer") or "").strip():
        errors.append("human review has no reviewer identity")
    return not errors


def verify(
    *,
    manifest_path: Path,
    live_summary_path: Path,
    runtime_identity_path: Path,
    cognitive_events_path: Path | None = None,
    human_review_path: Path | None = None,
    expected_chromie_revision: str | None = None,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    summary = _read_json(live_summary_path)
    identity = _read_json(runtime_identity_path)
    errors: list[str] = []
    warnings: list[str] = []

    if manifest.get("schema_version") != 1:
        errors.append("unsupported Agent Skill/weather qualification manifest")
    if manifest.get("runtime_policy_authority") is not False:
        errors.append("qualification manifest must deny runtime policy authority")
    if manifest.get("release_qualification_automatic") is not False:
        errors.append("qualification manifest must deny automatic release qualification")
    if summary.get("qualification_id") != manifest.get("qualification_id"):
        errors.append("live summary qualification_id does not match the manifest")
    if summary.get("ok") is not True:
        errors.append("live summary reports one or more runner errors")

    identity_digest = str(identity.get("identity_sha256") or "")
    summary_identity = summary.get("runtime_identity")
    if not identity_digest:
        errors.append("runtime identity has no identity_sha256")
    if not isinstance(summary_identity, dict) or summary_identity.get("identity_sha256") != identity_digest:
        errors.append("live summary is not bound to the retained runtime identity")
    qualification = identity.get("qualification")
    if not isinstance(qualification, dict):
        errors.append("runtime identity has no qualification state")
    else:
        if qualification.get("source_clean") is not True:
            errors.append("runtime identity is not source clean")
        if qualification.get("deployment_complete") is not True:
            errors.append("runtime identity deployment is incomplete")
    chromie = identity.get("chromie")
    revision = chromie.get("revision") if isinstance(chromie, dict) else None
    expected_revision = expected_chromie_revision or _git_revision()
    if expected_revision and revision != expected_revision:
        errors.append(
            f"runtime identity revision {revision!r} does not match expected {expected_revision!r}"
        )

    if cognitive_events_path is None:
        raw_path = summary.get("cognitive_events")
        cognitive_events_path = Path(str(raw_path)).expanduser().resolve() if raw_path else None
    if cognitive_events_path is None or not cognitive_events_path.is_file():
        errors.append("retained cognitive events are missing")
        events: list[dict[str, Any]] = []
    else:
        events = _read_jsonl(cognitive_events_path)

    turns = _turn_map(summary)
    scenario_goal_ids: dict[tuple[str, str], set[str]] = {}
    weather_capability = str(manifest.get("required_weather_capability_id") or "")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("qualification manifest scenarios must be a list")
        scenarios = []

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("scenario_id") or "")
        manifest_turns = scenario.get("turns")
        if not scenario_id or not isinstance(manifest_turns, list):
            errors.append("qualification scenario is malformed")
            continue
        for turn_spec in manifest_turns:
            if not isinstance(turn_spec, dict):
                continue
            turn_key = str(turn_spec.get("turn_key") or "")
            label = f"{scenario_id}/{turn_key}"
            retained = turns.get((scenario_id, turn_key))
            if retained is None:
                errors.append(f"{label}: retained turn is missing")
                continue
            sid = str(retained.get("sid") or "")
            if not sid:
                errors.append(f"{label}: retained turn has no sid")
                continue
            expected_text = str(turn_spec.get("text") or "")
            expected_text_sha = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
            if retained.get("text_sha256") != expected_text_sha:
                errors.append(f"{label}: retained text digest does not match the manifest")
            gateway = _events_for(events, sid=sid, event_type="cognitive_gateway_admission")
            runtime = _events_for(events, sid=sid, event_type="cognitive_runtime_resolution")
            outcome = _events_for(events, sid=sid, event_type="cognitive_execution_outcome")
            if len(gateway) != 1:
                errors.append(f"{label}: expected one Gateway admission event, found {len(gateway)}")
                gateway_event: dict[str, Any] = {}
            else:
                gateway_event = gateway[0]
            expectation = turn_spec.get("expect")
            expectation = expectation if isinstance(expectation, dict) else {}
            admission = expectation.get("admission")
            if admission and gateway_event.get("admission") != admission:
                errors.append(
                    f"{label}: admission {gateway_event.get('admission')!r} != {admission!r}"
                )
            requires_runtime = any(
                key in expectation
                for key in (
                    "runtime_lane",
                    "required_agent_skill_ids",
                    "required_capability_ids",
                    "forbidden_capability_ids",
                    "must_target_prior_goal_from_turn",
                    "weather_observation",
                )
            )
            if requires_runtime and len(runtime) != 1:
                errors.append(f"{label}: expected one runtime event, found {len(runtime)}")
                continue
            if not runtime:
                continue
            runtime_event = runtime[0]
            if runtime_event.get("run_identity", {}).get("identity_sha256") != identity_digest:
                errors.append(f"{label}: runtime event identity does not match")
            expected_lane = expectation.get("runtime_lane")
            if expected_lane and runtime_event.get("lane") != expected_lane:
                errors.append(
                    f"{label}: runtime lane {runtime_event.get('lane')!r} != {expected_lane!r}"
                )
            plan = runtime_event.get("terminal_plan")
            _validate_provenance(plan, errors, label=label)
            actual_skills = _plan_skill_ids(plan)
            required_skills = expectation.get("required_agent_skill_ids")
            if isinstance(required_skills, list):
                normalized = [str(item) for item in required_skills]
                if not _ordered_contains(actual_skills, normalized):
                    errors.append(
                        f"{label}: selected Agent Skills {actual_skills!r} do not contain {normalized!r} in order"
                    )
            actual_capabilities = _capability_ids(plan)
            required_capabilities = expectation.get("required_capability_ids")
            if isinstance(required_capabilities, list):
                missing = [str(item) for item in required_capabilities if str(item) not in actual_capabilities]
                if missing:
                    errors.append(f"{label}: missing required Capabilities: {', '.join(missing)}")
            forbidden_capabilities = expectation.get("forbidden_capability_ids")
            if isinstance(forbidden_capabilities, list):
                forbidden_hits = [
                    str(item) for item in forbidden_capabilities if str(item) in actual_capabilities
                ]
                if forbidden_hits:
                    errors.append(
                        f"{label}: forbidden Capabilities were planned: {', '.join(forbidden_hits)}"
                    )
            goals = _goal_ids(plan)
            scenario_goal_ids[(scenario_id, turn_key)] = goals
            prior_turn = expectation.get("must_target_prior_goal_from_turn")
            if isinstance(prior_turn, str) and prior_turn:
                prior_goals = scenario_goal_ids.get((scenario_id, prior_turn), set())
                targets = _target_goal_ids(runtime_event)
                if not prior_goals:
                    errors.append(f"{label}: prior turn {prior_turn!r} has no retained Goal IDs")
                elif not targets.intersection(prior_goals):
                    errors.append(
                        f"{label}: Goal Association does not target the prior weather Goal"
                    )
            weather_expectation = expectation.get("weather_observation")
            if isinstance(weather_expectation, dict):
                _validate_weather_observation(
                    outcome[-1] if outcome else None,
                    weather_expectation,
                    capability_id=weather_capability,
                    errors=errors,
                    label=label,
                )

    automated_errors = list(errors)
    automated_validated = not automated_errors
    review_errors: list[str] = []
    review_approved = False
    if automated_validated:
        review_approved = _validate_review(
            human_review_path,
            manifest=manifest,
            runtime_identity_path=runtime_identity_path,
            live_summary_path=live_summary_path,
            cognitive_events_path=cognitive_events_path,
            errors=review_errors,
        )
    errors.extend(review_errors)
    if automated_validated and human_review_path is None:
        warnings.append("human review is still required before track closure")

    eligible = automated_validated and review_approved and not errors
    return {
        "schema_version": 1,
        "qualification_id": manifest.get("qualification_id"),
        "passed": eligible,
        "errors": errors,
        "warnings": warnings,
        "runtime_identity_sha256": identity_digest,
        "artifacts": {
            "runtime_identity": str(runtime_identity_path),
            "live_summary": str(live_summary_path),
            "cognitive_events": str(cognitive_events_path),
            "human_review": str(human_review_path) if human_review_path else None,
        },
        "qualification": {
            "live_agent_skill_selection_validated": automated_validated,
            "provider_backed_weather_validated": automated_validated,
            "human_review_approved": review_approved,
            "track_closure_eligible": eligible,
            "release_qualified": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--live-summary", type=Path, required=True)
    parser.add_argument("--runtime-identity", type=Path, required=True)
    parser.add_argument("--cognitive-events", type=Path)
    parser.add_argument("--human-review", type=Path)
    parser.add_argument("--expected-chromie-revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-pending-review",
        action="store_true",
        help="Return success when automatic live validation passes but human review is still pending.",
    )
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
            human_review_path=(
                args.human_review.expanduser().resolve()
                if args.human_review
                else None
            ),
            expected_chromie_revision=args.expected_chromie_revision,
        )
    except Exception as exc:
        print(f"[agent-skill-weather-verifier][error] {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report["passed"]:
        return 0
    if (
        args.allow_pending_review
        and report.get("qualification", {}).get("live_agent_skill_selection_validated") is True
        and report.get("qualification", {}).get("provider_backed_weather_validated") is True
    ):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
