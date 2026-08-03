from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence

from benchmarks.contracts import ContractError
from benchmarks.regression.archive import load_json, materialize_source


@dataclass(frozen=True)
class ReplayScenario:
    scenario_id: str
    language: str
    turns: tuple[str, ...]
    primary_outcomes: tuple[str, ...]
    oracle_policy: Mapping[str, Any]
    review_rubric: Mapping[str, Any]

    def with_turns(self, turns: Sequence[str]) -> "ReplayScenario":
        normalized = tuple(str(turn).strip() for turn in turns if str(turn).strip())
        if not normalized:
            raise ContractError("a replay scenario must retain at least one turn")
        return ReplayScenario(
            scenario_id=self.scenario_id,
            language=self.language,
            turns=normalized,
            primary_outcomes=self.primary_outcomes,
            oracle_policy=dict(self.oracle_policy),
            review_rubric=dict(self.review_rubric),
        )


def _bundle_candidates(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("semantic-review-bundle.json")
        if path.is_file()
    ) + sorted(
        path for path in root.rglob("review-bundle.json") if path.is_file()
    )


def load_replay_scenario(source: Path, scenario_id: str) -> ReplayScenario:
    with materialize_source(source) as root:
        for path in _bundle_candidates(root):
            payload = load_json(path)
            scenarios = payload.get("scenarios")
            if not isinstance(scenarios, list):
                continue
            for item in scenarios:
                if not isinstance(item, Mapping) or item.get("scenario_id") != scenario_id:
                    continue
                scenario = item.get("scenario")
                if not isinstance(scenario, Mapping):
                    raise ContractError(f"{path}: scenario {scenario_id!r} has no normalized definition")
                inputs = scenario.get("inputs")
                expectations = scenario.get("expectations")
                if not isinstance(inputs, Mapping) or not isinstance(expectations, Mapping):
                    raise ContractError(f"{path}: scenario {scenario_id!r} is missing inputs or expectations")
                turns_value = inputs.get("turns")
                if isinstance(turns_value, list):
                    turns = tuple(str(value).strip() for value in turns_value if str(value).strip())
                else:
                    text = str(inputs.get("user_text") or "").strip()
                    turns = (text,) if text else ()
                language = str(inputs.get("language") or "").strip()
                if not turns or not language:
                    raise ContractError(f"{path}: scenario {scenario_id!r} is missing turns or language")
                policy = scenario.get("oracle_policy")
                if not isinstance(policy, Mapping):
                    policy = item.get("review_request", {}).get("oracle_policy", {})
                rubric = scenario.get("review_rubric")
                if not isinstance(rubric, Mapping):
                    rubric = {}
                return ReplayScenario(
                    scenario_id=scenario_id,
                    language=language,
                    turns=turns,
                    primary_outcomes=tuple(
                        str(value)
                        for value in expectations.get("primary_outcomes", [])
                        if str(value).strip()
                    ),
                    oracle_policy=dict(policy) if isinstance(policy, Mapping) else {},
                    review_rubric=dict(rubric),
                )
    raise ContractError(f"scenario {scenario_id!r} was not found in retained review bundles")


def replay_manifest(scenario: ReplayScenario) -> dict[str, Any]:
    language = scenario.language.casefold()
    speaker = "chromie_zh" if language.startswith("zh") else "chromie_en"
    return {
        "schema_version": 1,
        "qualification_id": f"replay-{scenario.scenario_id}",
        "transport_cases": [],
        "workflow_cases": [
            {
                "id": scenario.scenario_id,
                "language": scenario.language,
                "turns": list(scenario.turns),
                "speaker_id": speaker,
                "max_error_rate": 0.45,
                "primary_outcomes": list(scenario.primary_outcomes),
                "oracle_policy": dict(scenario.oracle_policy),
                "review_rubric": dict(scenario.review_rubric),
            }
        ],
    }


def write_replay_manifest(path: Path, scenario: ReplayScenario) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(replay_manifest(scenario), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def closed_loop_command(
    *,
    repo_root: Path,
    manifest_path: Path,
    output_dir: Path,
    scenario: ReplayScenario,
    capture: str,
    start_services: bool,
) -> list[str]:
    command = [
        "python",
        str(repo_root / "scripts" / "closed_loop_e2e.py"),
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir),
        "--workflow-only",
        "--capture",
        capture,
        "--languages",
        scenario.language.split("-", 1)[0],
        "--case",
        scenario.scenario_id,
    ]
    if start_services:
        command.append("--start-services")
    return command


def run_replay(
    scenario: ReplayScenario,
    *,
    repo_root: Path,
    output_dir: Path,
    capture: str = "auto",
    start_services: bool = False,
    timeout_s: float = 2400.0,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "replay-manifest.json"
    write_replay_manifest(manifest_path, scenario)
    command = closed_loop_command(
        repo_root=repo_root,
        manifest_path=manifest_path,
        output_dir=output_dir / "evidence",
        scenario=scenario,
        capture=capture,
        start_services=start_services,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError(f"scenario replay failed to execute: {exc}") from exc
    (output_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    summary_path = output_dir / "evidence" / "summary.json"
    if not summary_path.is_file():
        raise ContractError(
            f"scenario replay produced no summary (exit {completed.returncode})"
        )
    summary = load_json(summary_path)
    return {
        "schema_version": 1,
        "scenario_id": scenario.scenario_id,
        "turns": list(scenario.turns),
        "command": command,
        "command_shell": shlex.join(command),
        "returncode": completed.returncode,
        "summary": summary,
        "output_dir": str(output_dir),
    }


def mechanical_failure_reproduced(result: Mapping[str, Any]) -> bool:
    summary = result.get("summary")
    return isinstance(summary, Mapping) and summary.get("mechanical_passed") is False


def command_oracle(command: Sequence[str], result: Mapping[str, Any], *, timeout_s: float = 120.0) -> tuple[bool, str | None]:
    if not command:
        raise ContractError("oracle command must not be empty")
    try:
        completed = subprocess.run(
            list(command),
            input=json.dumps(result, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError(f"failure oracle command failed: {exc}") from exc
    if completed.returncode != 0:
        raise ContractError(
            f"failure oracle exited {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError(f"failure oracle returned invalid JSON: {exc}") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("failure_reproduced"), bool):
        raise ContractError("failure oracle must return {\"failure_reproduced\": boolean}")
    detail = payload.get("detail")
    return bool(payload["failure_reproduced"]), str(detail) if detail is not None else None


def minimize_turns(
    turns: Sequence[str],
    predicate: Callable[[tuple[str, ...]], bool],
) -> tuple[str, ...]:
    current = tuple(turns)
    if not current:
        raise ContractError("cannot minimize an empty turn sequence")
    if not predicate(current):
        raise ContractError("the original turn sequence does not reproduce the failure")
    granularity = 2
    while len(current) >= 2:
        chunk_size = max(1, (len(current) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(current), chunk_size):
            candidate = current[:start] + current[start + chunk_size :]
            if not candidate:
                continue
            if predicate(candidate):
                current = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(current):
            break
        granularity = min(len(current), granularity * 2)
    return current


def minimize_replay(
    scenario: ReplayScenario,
    *,
    repo_root: Path,
    output_dir: Path,
    capture: str,
    start_services: bool,
    timeout_s: float,
    oracle_command: Sequence[str] | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    counter = 0

    def predicate(turns: tuple[str, ...]) -> bool:
        nonlocal counter
        counter += 1
        attempt_dir = output_dir / "attempts" / f"{counter:03d}"
        result = run_replay(
            scenario.with_turns(turns),
            repo_root=repo_root,
            output_dir=attempt_dir,
            capture=capture,
            start_services=start_services and counter == 1,
            timeout_s=timeout_s,
        )
        if oracle_command:
            reproduced, detail = command_oracle(oracle_command, result)
        else:
            reproduced = mechanical_failure_reproduced(result)
            detail = None
        attempts.append(
            {
                "attempt": counter,
                "turns": list(turns),
                "failure_reproduced": reproduced,
                "detail": detail,
                "output_dir": str(attempt_dir),
            }
        )
        return reproduced

    minimized = minimize_turns(scenario.turns, predicate)
    report = {
        "schema_version": 1,
        "kind": "chromie_failure_minimization",
        "scenario_id": scenario.scenario_id,
        "original_turns": list(scenario.turns),
        "minimized_turns": list(minimized),
        "removed_turn_count": len(scenario.turns) - len(minimized),
        "oracle": "external_command" if oracle_command else "mechanical_failure",
        "attempts": attempts,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "minimization-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_replay_manifest(output_dir / "minimized-manifest.json", scenario.with_turns(minimized))
    return report
