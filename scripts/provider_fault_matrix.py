#!/usr/bin/env python3
"""Run the deterministic Chromie-side Soridormi provider fault matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult

MATRIX_VERSION = "1.0"


@dataclass(frozen=True)
class FaultScenario:
    scenario_id: str
    expected_status: str
    expected_body_status: str | None
    expected_reason: str | None
    expected_speech: tuple[str, ...]
    expected_calls: tuple[str, ...]
    request_timeout_ms: int | None = None
    operator_cancel: bool = False


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    passed: bool
    expected_status: str
    actual_status: str
    expected_body_status: str | None
    actual_body_status: str | None
    expected_reason: str | None
    actual_reason: str | None
    expected_speech: tuple[str, ...]
    actual_speech: tuple[str, ...]
    expected_calls: tuple[str, ...]
    actual_calls: tuple[str, ...]


STANDARD_CALLS = (
    "soridormi.skill.list",
    "soridormi.skill.create_plan",
    "soridormi.safety.monitor_motion",
    "soridormi.skill.execute_plan",
)
CANCEL_CALLS = (*STANDARD_CALLS, "soridormi.motion.cancel")
GENERIC_FAILURE = ("I could not complete that movement safely.",)
TIMEOUT_FAILURE = (
    "The movement timed out, and I could not confirm it completed safely.",
)
SAFETY_FAILURE = (
    "The safety check did not pass, so I did not perform that movement.",
)

SCENARIOS = (
    FaultScenario(
        "success",
        "completed",
        "completed",
        None,
        ("Done.",),
        STANDARD_CALLS,
    ),
    FaultScenario(
        "plan_timeout",
        "failed",
        "timed_out",
        "plan_timeout",
        TIMEOUT_FAILURE,
        STANDARD_CALLS[:2],
    ),
    FaultScenario(
        "plan_disconnect",
        "failed",
        "failed",
        "plan_failed_retryable",
        GENERIC_FAILURE,
        STANDARD_CALLS[:2],
    ),
    FaultScenario(
        "malformed_plan",
        "failed",
        "failed",
        "invalid_plan_response",
        GENERIC_FAILURE,
        STANDARD_CALLS[:2],
    ),
    FaultScenario(
        "monitor_refused",
        "failed",
        "refused",
        "safety_monitor_refused",
        SAFETY_FAILURE,
        STANDARD_CALLS[:3],
    ),
    FaultScenario(
        "monitor_timeout",
        "failed",
        "timed_out",
        "monitor_timeout",
        TIMEOUT_FAILURE,
        STANDARD_CALLS[:3],
    ),
    FaultScenario(
        "execute_incomplete",
        "failed",
        "failed",
        "execution_incomplete",
        GENERIC_FAILURE,
        STANDARD_CALLS,
    ),
    FaultScenario(
        "execute_skill_mismatch",
        "failed",
        "failed",
        "execution_skill_mismatch",
        GENERIC_FAILURE,
        STANDARD_CALLS,
    ),
    FaultScenario(
        "execute_timeout",
        "failed",
        "timed_out",
        "execute_timeout",
        TIMEOUT_FAILURE,
        STANDARD_CALLS,
    ),
    FaultScenario(
        "execute_disconnect",
        "failed",
        "failed",
        "execute_failed_retryable",
        GENERIC_FAILURE,
        STANDARD_CALLS,
    ),
    FaultScenario(
        "runtime_timeout_cancel",
        "failed",
        "timed_out",
        "timeout",
        TIMEOUT_FAILURE,
        CANCEL_CALLS,
        request_timeout_ms=10,
    ),
    FaultScenario(
        "operator_cancel",
        "cancelled",
        None,
        None,
        ("Starting.",),
        CANCEL_CALLS,
        operator_cancel=True,
    ),
)
SCENARIOS_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}


class ScenarioInvoker:
    def __init__(self, scenario: FaultScenario) -> None:
        self.scenario = scenario
        self.calls: list[str] = []
        self.execute_started = asyncio.Event()

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append(tool_name)
        scenario_id = self.scenario.scenario_id
        if tool_name == "soridormi.skill.list":
            return ToolCallOutcome.success(
                {
                    "mode": "sim",
                    "skills": [
                        {
                            "skill_id": "nod_yes",
                            "available": True,
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "count": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 3,
                                    }
                                },
                                "additionalProperties": False,
                            },
                            "interruptible": True,
                        }
                    ],
                }
            )
        if tool_name == "soridormi.skill.create_plan":
            if scenario_id == "plan_timeout":
                return ToolCallOutcome(status="timeout", error="injected plan timeout")
            if scenario_id == "plan_disconnect":
                return ToolCallOutcome.failed(
                    "injected plan disconnect",
                    retryable=True,
                )
            if scenario_id == "malformed_plan":
                return ToolCallOutcome.success({"skill_id": "nod_yes"})
            return ToolCallOutcome.success({"plan_id": "plan-fault-matrix"})
        if tool_name == "soridormi.safety.monitor_motion":
            if scenario_id == "monitor_refused":
                return ToolCallOutcome.success(
                    {"ok": False, "event": "injected blocked workspace"}
                )
            if scenario_id == "monitor_timeout":
                return ToolCallOutcome(
                    status="timeout",
                    error="injected monitor timeout",
                )
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            self.execute_started.set()
            if scenario_id in {"runtime_timeout_cancel", "operator_cancel"}:
                await asyncio.sleep(5)
            if scenario_id == "execute_incomplete":
                return ToolCallOutcome.success(
                    {"completed": False, "skill_id": "nod_yes"}
                )
            if scenario_id == "execute_skill_mismatch":
                return ToolCallOutcome.success(
                    {"completed": True, "skill_id": "wave_hand"}
                )
            if scenario_id == "execute_timeout":
                return ToolCallOutcome(
                    status="timeout",
                    error="injected execute timeout",
                )
            if scenario_id == "execute_disconnect":
                return ToolCallOutcome.failed(
                    "injected execute disconnect",
                    retryable=True,
                )
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": "nod_yes"}
            )
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


async def run_scenario(scenario: FaultScenario) -> ScenarioResult:
    spoken: list[str] = []
    invoker = ScenarioInvoker(scenario)
    coordinator = InteractionRuntimeCoordinator(
        lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
        soridormi_invoker=invoker,
    )
    speech = [{"text": "Done.", "timing": "after_skills"}]
    if scenario.operator_cancel:
        speech.insert(0, {"text": "Starting.", "timing": "immediate"})
    response = InteractionResponse(
        interaction_id=f"fault-matrix-{scenario.scenario_id}",
        speech=speech,
        skills=[
            {
                "request_id": "fault-matrix-request",
                "skill_id": "soridormi.nod_yes",
                "args": {"count": 2},
                "timeout_ms": scenario.request_timeout_ms,
            }
        ],
        metadata={"language": "en-US", "fault_scenario": scenario.scenario_id},
    )
    task = asyncio.create_task(
        coordinator.execute(response, session_id=f"fault-{scenario.scenario_id}")
    )
    if scenario.operator_cancel:
        await asyncio.wait_for(invoker.execute_started.wait(), timeout=1)
        task.cancel()
    execution = await task
    body_result = next(
        (
            result
            for result in execution.results
            if result.skill_id.startswith("soridormi.")
        ),
        None,
    )
    actual_body_status = body_result.status if body_result else None
    actual_reason = body_result.reason_code if body_result else None
    actual_speech = tuple(spoken)
    actual_calls = tuple(invoker.calls)
    passed = (
        execution.status == scenario.expected_status
        and actual_body_status == scenario.expected_body_status
        and actual_reason == scenario.expected_reason
        and actual_speech == scenario.expected_speech
        and actual_calls == scenario.expected_calls
    )
    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        passed=passed,
        expected_status=scenario.expected_status,
        actual_status=execution.status,
        expected_body_status=scenario.expected_body_status,
        actual_body_status=actual_body_status,
        expected_reason=scenario.expected_reason,
        actual_reason=actual_reason,
        expected_speech=scenario.expected_speech,
        actual_speech=actual_speech,
        expected_calls=scenario.expected_calls,
        actual_calls=actual_calls,
    )


async def run_matrix(
    scenario_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    selected = (
        list(SCENARIOS)
        if not scenario_ids
        else [SCENARIOS_BY_ID[scenario_id] for scenario_id in scenario_ids]
    )
    results = [await run_scenario(scenario) for scenario in selected]
    return {
        "matrix_version": MATRIX_VERSION,
        "passed": all(result.passed for result in results),
        "scenario_count": len(results),
        "results": [asdict(result) for result in results],
    }


def parse_scenario_ids(raw: str) -> list[str] | None:
    if raw.strip().lower() == "all":
        return None
    selected = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in selected if item not in SCENARIOS_BY_ID]
    if unknown:
        raise ValueError(f"unknown fault scenario(s): {', '.join(unknown)}")
    if not selected:
        raise ValueError("at least one fault scenario is required")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        default="all",
        help="Comma-separated scenario IDs or 'all'.",
    )
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()
    try:
        selected = parse_scenario_ids(args.scenarios)
    except ValueError as exc:
        parser.error(str(exc))
    payload = asyncio.run(run_matrix(selected))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
