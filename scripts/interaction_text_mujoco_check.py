#!/usr/bin/env python3
"""Text-to-MuJoCo interaction check without microphone or ASR.

This runner feeds user text directly into the deployed Router and Agent
``/interaction`` contract, executes the resulting structured response through
the host trusted Skill Runtime, and optionally plays Chromie speech through the
configured speaker. It is a simulator/live-integration check, not supervised
microphone evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "text-mujoco"
DEFAULT_TEXT = (
    "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, "
    "then turn left"
)


def acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_scalar(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def parse_expected_arg(raw: str) -> tuple[int, str, Any]:
    """Parse ``INDEX:KEY=VALUE`` expectation syntax."""

    try:
        index_text, assignment = raw.split(":", 1)
        key, value = assignment.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected args must use INDEX:KEY=VALUE syntax"
        ) from exc
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("expected arg key must not be empty")
    try:
        index = int(index_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected arg index must be an integer") from exc
    if index < 0:
        raise argparse.ArgumentTypeError("expected arg index must be non-negative")
    return index, key, _parse_scalar(value.strip())


def _numbers_close(left: Any, right: Any, *, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def validate_contract(
    *,
    route: Any,
    response: Any,
    expected_route: str | None,
    expected_skills: list[str],
    expect_no_skills: bool,
    expected_args: list[tuple[int, str, Any]],
    arg_tolerance: float,
) -> list[str]:
    errors: list[str] = []
    route_actions = [
        str(item.get("capability_id") or "")
        for item in getattr(route, "actions", [])
    ]
    skills = [
        item
        for item in getattr(response, "skills", [])
        if str(item.skill_id).startswith("soridormi.")
    ]
    skill_ids = [item.skill_id for item in skills]

    if expected_route and route.route != expected_route:
        errors.append(f"route={route.route!r}, expected {expected_route!r}")

    if expected_skills:
        if route.route != "robot_action":
            errors.append(f"route={route.route!r}, expected 'robot_action'")
        if route_actions != expected_skills:
            errors.append(
                "router actions mismatch: "
                f"expected {expected_skills!r}, got {route_actions!r}"
            )
        if skill_ids != expected_skills:
            errors.append(
                "interaction skills mismatch: "
                f"expected {expected_skills!r}, got {skill_ids!r}"
            )

    if expect_no_skills:
        if route_actions:
            errors.append(f"router emitted Soridormi actions, expected none: {route_actions!r}")
        if skill_ids:
            errors.append(f"interaction emitted Soridormi skills, expected none: {skill_ids!r}")

    for index, key, expected in expected_args:
        if index >= len(skills):
            errors.append(
                f"expected arg {index}:{key}={expected!r}, "
                f"but only {len(skills)} Soridormi skill(s) were emitted"
            )
            continue
        actual = skills[index].args.get(key)
        if not _numbers_close(actual, expected, tolerance=arg_tolerance):
            errors.append(
                f"arg mismatch for skill[{index}] {skills[index].skill_id} "
                f"{key}: expected {expected!r}, got {actual!r}"
            )
    return errors


def safe_idle_errors(status: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if status.get("active_task") is not None:
        errors.append(f"active_task is not idle: {status.get('active_task')!r}")
    if status.get("emergency_stop") is not False:
        errors.append(f"emergency_stop is not false: {status.get('emergency_stop')!r}")
    if status.get("fallen") is True:
        errors.append("robot reports fallen=true")
    return errors


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _exception_text(exc: BaseException) -> str:
    return f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"


def _apply_soridormi_skill_timeout(response: Any, timeout_s: float | None) -> Any:
    if timeout_s is None or timeout_s <= 0:
        return response
    timeout_ms = int(timeout_s * 1000)
    skills = [
        skill.model_copy(
            update={"timeout_ms": max(int(skill.timeout_ms or 0), timeout_ms)}
        )
        if str(skill.skill_id).startswith("soridormi.")
        else skill
        for skill in response.skills
    ]
    return response.model_copy(deep=True, update={"skills": skills})


def _configure_environment(args: argparse.Namespace, evidence_dir: Path) -> None:
    os.environ["ROUTER_URL"] = args.router_url
    os.environ["AGENT_URL"] = args.agent_url
    os.environ["ORCH_ENABLE_ROUTER"] = "1"
    os.environ["ORCH_ENABLE_AGENT"] = "1"
    os.environ["ORCH_ENABLE_INTERACTION_RESPONSE"] = "1"
    os.environ["ORCH_ENABLE_SORIDORMI_SKILLS"] = "1"
    os.environ["ORCH_AUTO_CONFIRM_SIM_SKILLS"] = "1" if args.auto_confirm_sim else "0"
    os.environ["ORCH_AUDIO_INPUT_MODE"] = "stdin"
    os.environ["ORCH_AUDIO_OUTPUT_MODE"] = "device" if args.speaker else "discard"
    if not args.speaker:
        os.environ.setdefault("ORCH_DISCARD_PLAYBACK_REALTIME", "0")
    os.environ["ORCH_SORIDORMI_MANIFEST"] = str(args.manifest)
    os.environ["ORCH_EVENT_LOG_PATH"] = str(evidence_dir / "events.jsonl")
    os.environ["RECORDINGS_DIR"] = str(evidence_dir / "recordings")
    os.environ["ORCH_SESSION_TIMING_LOGS"] = "1"
    if args.soridormi_mcp_url:
        os.environ["SORIDORMI_MCP_URL"] = args.soridormi_mcp_url


async def _invoke_soridormi_status(invoker: Any) -> dict[str, Any]:
    outcome = await invoker.invoke("soridormi.robot.get_status", {})
    if outcome.status != "success":
        raise RuntimeError(
            outcome.error or f"Soridormi status returned {outcome.status}"
        )
    if not isinstance(outcome.output, dict):
        raise RuntimeError("Soridormi status output is not an object")
    return outcome.output


async def wait_for_session_done(assistant: Any, sid: str, *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = assistant.sessions.state.get(sid) or {}
        if state.get("done_logged"):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"session {sid} did not finish within {timeout_s:.1f}s")


async def run_check(args: argparse.Namespace) -> dict[str, Any]:
    evidence_dir = Path(args.evidence_dir or DEFAULT_EVIDENCE_ROOT / acceptance_id())
    evidence_dir = evidence_dir.expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _configure_environment(args, evidence_dir)

    # Import after environment defaults are set; the Orchestrator module loads
    # .env.runtime on import but does not override already-exported values.
    from orchestrator.orchestrator import VoiceAssistant  # noqa: PLC0415

    assistant = VoiceAssistant()
    errors: list[str] = []
    execution_payload: dict[str, Any] | None = None
    status_before: dict[str, Any] | None = None
    status_after: dict[str, Any] | None = None

    try:
        session = await assistant.get_http_session()
        router_health = await assistant.router_client.health(session)
        agent_health = await assistant.agent_client.health(session)
        _write_json(evidence_dir / "router_health.json", router_health)
        _write_json(evidence_dir / "agent_health.json", agent_health)

        if "soridormi" not in set(agent_health.get("capability_sources") or []):
            errors.append(
                "Agent service did not load the Soridormi manifest. "
                "Start Chromie with AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json."
            )

        invoker = assistant.interaction_runtime.soridormi_invoker
        if invoker is None:
            raise RuntimeError("Soridormi Skill Runtime invoker is not configured")

        status_before = await _invoke_soridormi_status(invoker)
        _write_json(evidence_dir / "status_before.json", status_before)
        if not args.allow_non_sim and status_before.get("mode") != "sim":
            errors.append(
                "Refusing to execute because Soridormi mode is "
                f"{status_before.get('mode')!r}; pass --allow-non-sim only for "
                "a separately supervised non-sim run."
            )
        errors.extend(safe_idle_errors(status_before))

        sid = assistant.create_session()
        context = assistant.build_context(sid)
        robot_state = dict(context.get("robot_state") or {})
        robot_state.update(
            {
                "emergency_stop": bool(status_before.get("emergency_stop")),
                "mode": status_before.get("mode"),
                "backend": status_before.get("backend"),
            }
        )
        context["robot_state"] = robot_state

        route = await assistant.router_client.route(
            session,
            text=args.text,
            sid=sid,
            language=args.language,
            context=context,
        )
        _write_json(evidence_dir / "route.json", route.model_dump(mode="json"))
        assistant.session_log(
            sid,
            "text_check_route_done: route=%s intent=%s source=%s actions=%s",
            route.route,
            route.intent,
            route.source,
            len(route.actions),
        )

        response = await assistant.agent_client.run_interaction(
            session,
            text=args.text,
            route_decision=route,
            sid=sid,
            context=context,
            history=context.get("history", []),
        )
        response = response.model_copy(
            deep=True,
            update={
                "metadata": {
                    **response.metadata,
                    "language": route.language,
                }
            },
        )
        response = _apply_soridormi_skill_timeout(response, args.skill_timeout_s)
        _write_json(
            evidence_dir / "interaction_response.json",
            response.model_dump(mode="json"),
        )
        assistant.session_log(
            sid,
            "text_check_interaction_done: status=%s speech=%s skills=%s confirmation=%s",
            response.status,
            len(response.speech),
            len(response.skills),
            response.requires_confirmation,
        )

        errors.extend(
            validate_contract(
                route=route,
                response=response,
                expected_route=args.expect_route,
                expected_skills=args.expect_skill,
                expect_no_skills=args.expect_no_skills,
                expected_args=args.expect_arg,
                arg_tolerance=args.arg_tolerance,
            )
        )

        if response.requires_confirmation and not args.auto_confirm_sim:
            errors.append(
                "InteractionResponse requires confirmation, but this text check "
                "does not collect a spoken confirmation reply."
            )

        if not errors and not args.preview_only:
            execution = await assistant.execute_interaction_response(response, sid)
            if execution is None:
                raise RuntimeError("Interaction execution returned no result")
            execution_payload = execution.model_dump(mode="json")
            _write_json(evidence_dir / "execution.json", execution_payload)
            if execution.status != "completed":
                errors.append(f"Skill Runtime status was {execution.status!r}")
            body_results = [
                result
                for result in execution.results
                if result.skill_id.startswith("soridormi.")
            ]
            for result in body_results:
                if result.status != "completed":
                    errors.append(
                        f"{result.skill_id} ended with status {result.status!r}: "
                        f"{result.reason_code or result.message}"
                    )
            try:
                await wait_for_session_done(assistant, sid, timeout_s=args.timeout_s)
            except Exception as exc:
                errors.append(f"session completion wait failed: {_exception_text(exc)}")

            try:
                status_after = await _invoke_soridormi_status(invoker)
            except Exception as exc:
                errors.append(f"post-run Soridormi status probe failed: {_exception_text(exc)}")
                _write_json(
                    evidence_dir / "status_after_error.json",
                    {"error": _exception_text(exc)},
                )
            else:
                _write_json(evidence_dir / "status_after.json", status_after)
                errors.extend(safe_idle_errors(status_after))

            session_state = assistant.sessions.state.get(sid) or {}
            if args.require_speech and int(session_state.get("scheduled_tts", 0)) < 1:
                errors.append("no TTS speech was scheduled")
            if args.require_speech and int(session_state.get("failed_tts", 0)) > 0:
                errors.append(f"TTS failed {session_state.get('failed_tts')} time(s)")

        summary = {
            "ok": not errors,
            "text": args.text,
            "sid": sid,
            "speaker": args.speaker,
            "preview_only": args.preview_only,
            "skill_timeout_s": args.skill_timeout_s,
            "evidence_dir": str(evidence_dir),
            "errors": errors,
            "route": route.model_dump(mode="json"),
            "interaction_response": response.model_dump(mode="json"),
            "execution": execution_payload,
            "status_before": status_before,
            "status_after": status_after,
            "session_state": assistant.sessions.state.get(sid),
        }
        _write_json(evidence_dir / "summary.json", summary)
        return summary
    finally:
        await assistant.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run text -> Router -> Agent /interaction -> Skill Runtime -> "
            "Soridormi/MuJoCo without microphone or ASR."
        )
    )
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    parser.add_argument("--router-url", default=os.getenv("ROUTER_URL", "http://127.0.0.1:8091"))
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "capabilities" / "soridormi.json")
    parser.add_argument("--language", default=None)
    parser.add_argument("--evidence-dir")
    parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Play Chromie TTS through the configured speaker; use --no-speaker for headless checks.",
    )
    parser.add_argument("--preview-only", action="store_true", help="Route and validate /interaction without executing Soridormi skills.")
    parser.add_argument("--allow-non-sim", action="store_true", help="Permit non-sim Soridormi modes. Use only under separate supervision.")
    parser.add_argument("--auto-confirm-sim", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-speech", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--expect-route",
        choices=[
            "chat",
            "deep_thought",
            "robot_action",
            "tool",
            "memory",
            "clarify",
            "interrupt",
            "ignore",
        ],
    )
    parser.add_argument("--expect-no-skills", action="store_true", help="Require no Soridormi actions or skills.")
    parser.add_argument("--expect-skill", action="append", default=[])
    parser.add_argument(
        "--expect-arg",
        action="append",
        type=parse_expected_arg,
        default=[],
        metavar="INDEX:KEY=VALUE",
    )
    parser.add_argument("--arg-tolerance", type=float, default=1e-6)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    parser.add_argument(
        "--skill-timeout-s",
        type=float,
        default=120.0,
        help=(
            "Per-Soridormi-skill timeout used by this live diagnostic runner. "
            "Set to 0 to use catalog/default skill timeouts unchanged."
        ),
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.expect_no_skills and args.expect_skill:
        parser.error("--expect-no-skills cannot be combined with --expect-skill")
    try:
        summary = asyncio.run(run_check(args))
    except Exception as exc:
        print(f"[interaction-text-mujoco][error] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
