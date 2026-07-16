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
import re
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
INTERNAL_SPEECH_PATTERNS = [
    r"\bTask Split\b",
    r"\bKey Risk\b",
    r"\bNext Step\b",
    r"\bExecute\s+soridormi\.",
    r"\bsoridormi\.[A-Za-z0-9_.-]+",
    r"\bchromie\.[A-Za-z0-9_.-]+",
]


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
        if route_actions and route_actions != expected_skills:
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


def validate_speech_contract(
    response: Any,
    reject_patterns: list[str],
) -> list[str]:
    errors: list[str] = []
    if not reject_patterns:
        return errors
    compiled = [
        (pattern, re.compile(pattern, flags=re.IGNORECASE))
        for pattern in reject_patterns
    ]
    for index, item in enumerate(getattr(response, "speech", [])):
        text = str(getattr(item, "text", "") or "")
        for pattern, regex in compiled:
            if regex.search(text):
                preview = text.replace("\n", " ")[:220]
                errors.append(
                    f"speech[{index}] matched forbidden pattern {pattern!r}: "
                    f"{preview!r}"
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


def should_require_tts_speech(route: Any, *, require_speech: bool) -> bool:
    if not require_speech:
        return False
    if getattr(route, "route", "") == "interrupt":
        return False
    if getattr(route, "should_speak", True) is False:
        return False
    return True


def _short_capability_id(item: dict[str, Any]) -> str:
    capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
    return capability_id or "unknown"


def _describe_task(item: dict[str, Any], index: int) -> str:
    stage = str(item.get("source_stage") or "?")
    task_type = str(item.get("task_type") or "?")
    priority = str(item.get("priority") or "normal")
    bits = [f"{index}:{stage}:{task_type}", f"priority={priority}"]
    capability_id = str(item.get("capability_id") or "").strip()
    if capability_id:
        bits.append(f"skill={capability_id}")
    action_type = str(item.get("action_type") or "").strip()
    if action_type:
        bits.append(f"action={action_type}")
    status = str(item.get("status") or "").strip()
    if status and status != "proposed":
        bits.append(f"status={status}")
    return " ".join(bits)


def build_debug_summary(
    *,
    route: Any,
    response: Any,
    errors: list[str],
) -> dict[str, Any]:
    route_metadata = getattr(route, "metadata", {}) or {}
    route_actions = [
        _short_capability_id(item)
        for item in getattr(route, "actions", [])
        if isinstance(item, dict)
    ]
    candidates = [
        _short_capability_id(item)
        for item in getattr(route, "candidate_capabilities", [])[:5]
        if isinstance(item, dict)
    ]
    task_list = [
        _describe_task(item, index)
        for index, item in enumerate(route_metadata.get("task_list") or [])
        if isinstance(item, dict)
    ]
    stages = []
    for stage in route_metadata.get("route_stage_outputs") or []:
        if not isinstance(stage, dict):
            continue
        tasks = stage.get("tasks") or []
        stages.append(
            "{stage}:{status} route={route} intent={intent} tasks={count}".format(
                stage=stage.get("stage") or "?",
                status=stage.get("status") or "?",
                route=stage.get("route") or "-",
                intent=stage.get("intent") or "-",
                count=len(tasks) if isinstance(tasks, list) else 0,
            )
        )
    skills = [
        str(item.skill_id)
        for item in getattr(response, "skills", [])
        if str(item.skill_id).startswith("soridormi.")
    ]
    speech = [str(item.text) for item in getattr(response, "speech", [])]
    return {
        "route": (
            f"route={getattr(route, 'route', '?')} "
            f"intent={getattr(route, 'intent', '?')} "
            f"source={getattr(route, 'source', '?')} "
            f"confidence={float(getattr(route, 'confidence', 0.0)):.2f} "
            f"actions={len(route_actions)}"
        ),
        "route_actions": route_actions,
        "candidate_capabilities": candidates,
        "stages": stages,
        "task_list": task_list,
        "skills": skills,
        "speech_items": len(speech),
        "speech_preview": speech[0][:160] if speech else "",
        "errors": list(errors),
    }


def print_debug_summary(debug_summary: dict[str, Any]) -> None:
    print(f"[interaction-text-mujoco][debug] {debug_summary['route']}", file=sys.stderr)
    if debug_summary.get("stages"):
        print(
            "[interaction-text-mujoco][debug] stages: "
            + " | ".join(debug_summary["stages"]),
            file=sys.stderr,
        )
    if debug_summary.get("task_list"):
        print("[interaction-text-mujoco][debug] task_list:", file=sys.stderr)
        for item in debug_summary["task_list"]:
            print(f"[interaction-text-mujoco][debug]   - {item}", file=sys.stderr)
    if debug_summary.get("route_actions"):
        print(
            "[interaction-text-mujoco][debug] route_actions: "
            + ", ".join(debug_summary["route_actions"]),
            file=sys.stderr,
        )
    if debug_summary.get("skills"):
        print(
            "[interaction-text-mujoco][debug] emitted_skills: "
            + ", ".join(debug_summary["skills"]),
            file=sys.stderr,
        )
    else:
        print("[interaction-text-mujoco][debug] emitted_skills: none", file=sys.stderr)
    if debug_summary.get("speech_items"):
        print(
            f"[interaction-text-mujoco][debug] speech_items: {debug_summary['speech_items']} "
            f"preview={debug_summary.get('speech_preview', '')!r}",
            file=sys.stderr,
        )
    if debug_summary.get("errors"):
        print(
            "[interaction-text-mujoco][debug] errors: "
            + " | ".join(debug_summary["errors"]),
            file=sys.stderr,
        )


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
    conversation_id = str(getattr(args, "conversation_id", "") or "").strip()
    if conversation_id:
        os.environ["ORCH_CONVERSATION_ID"] = conversation_id
    if args.cognitive_runtime:
        os.environ["ORCH_COGNITIVE_RUNTIME_MODE"] = "apply"
        os.environ["ORCH_COGNITIVE_APPLY_LANES"] = args.cognitive_apply_lanes
        os.environ["ORCH_COGNITIVE_FALLBACK_POLICY"] = "fail_closed"
        os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"] = "1"
        os.environ["ORCH_COGNITIVE_EVIDENCE_PATH"] = str(
            evidence_dir / "cognitive_runtime_events.jsonl"
        )
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
    timings_ms: dict[str, float] = {}
    total_start = time.perf_counter()
    execution_payload: dict[str, Any] | None = None
    status_before: dict[str, Any] | None = None
    status_after: dict[str, Any] | None = None

    try:
        health_start = time.perf_counter()
        session = await assistant.get_http_session()
        router_health = await assistant.router_client.health(session)
        agent_health = await assistant.agent_client.health(session)
        timings_ms["health_ms"] = (time.perf_counter() - health_start) * 1000.0
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

        status_before_start = time.perf_counter()
        status_before = await _invoke_soridormi_status(invoker)
        timings_ms["status_before_ms"] = (
            time.perf_counter() - status_before_start
        ) * 1000.0
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

        route_start = time.perf_counter()
        route = await assistant.router_client.route(
            session,
            text=args.text,
            sid=sid,
            language=args.language,
            context=context,
        )
        route_ms = (time.perf_counter() - route_start) * 1000.0
        timings_ms["route_ms"] = route_ms
        _write_json(evidence_dir / "route.json", route.model_dump(mode="json"))
        assistant.session_log(
            sid,
            "text_check_route_done: route=%s intent=%s source=%s actions=%s route_ms=%.1f",
            route.route,
            route.intent,
            route.source,
            len(route.actions),
            route_ms,
        )

        agent_start = time.perf_counter()
        cognitive_resolution_payload: dict[str, Any] | None = None
        if args.cognitive_runtime:
            cognitive_resolution = await assistant._run_cognitive_runtime_pipeline(
                session,
                user_text=args.text,
                session_id=sid,
                context=context,
                decision=route,
                record_evidence=False,
            )
            cognitive_resolution_payload = cognitive_resolution.model_dump(
                mode="json", exclude_none=True
            )
            _write_json(
                evidence_dir / "cognitive_runtime_resolution.json",
                cognitive_resolution_payload,
            )
            if (
                cognitive_resolution.status != "applied"
                or cognitive_resolution.interaction_response is None
            ):
                errors.append(
                    "goal-driven runtime did not produce an applied interaction: "
                    f"status={cognitive_resolution.status!r} "
                    f"reason={cognitive_resolution.fallback_reason!r}"
                )
                response = assistant._host_speech_response(
                    "Goal-driven runtime did not produce an executable interaction.",
                    style="warning",
                    source="cognitive_text_check_failure",
                )
            else:
                response = cognitive_resolution.interaction_response.model_copy(deep=True)
                response = assistant.interaction_runtime.prepare_response(
                    response, session_id=sid
                )
                goal_state_results = assistant._apply_cognitive_goal_state(
                    cognitive_resolution,
                    session_id=sid,
                    user_text=args.text,
                    decision=route,
                )
                response.metadata = {
                    **response.metadata,
                    "goal_state_results": goal_state_results,
                    "cognitive_runtime_resolution": assistant._cognitive_resolution_summary(
                        cognitive_resolution
                    ),
                }
                cognitive_resolution.goal_state_results = goal_state_results
                cognitive_resolution.metadata = {
                    **cognitive_resolution.metadata,
                    "host_commit_status": "prepared_and_goal_state_committed",
                }
            assistant._record_cognitive_runtime_evidence(
                cognitive_resolution, session_id=sid, user_text=args.text
            )
        else:
            response = await assistant.agent_client.run_interaction(
                session,
                text=args.text,
                route_decision=route,
                sid=sid,
                context=context,
                history=context.get("history", []),
            )
        agent_ms = (time.perf_counter() - agent_start) * 1000.0
        timings_ms["agent_ms"] = agent_ms
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
            "text_check_interaction_done: status=%s speech=%s skills=%s confirmation=%s agent_ms=%.1f",
            response.status,
            len(response.speech),
            len(response.skills),
            response.requires_confirmation,
            agent_ms,
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
        reject_speech_patterns = list(getattr(args, "reject_speech_pattern", []) or [])
        if bool(getattr(args, "reject_internal_speech", False)):
            reject_speech_patterns = INTERNAL_SPEECH_PATTERNS + reject_speech_patterns
        errors.extend(validate_speech_contract(response, reject_speech_patterns))

        if response.requires_confirmation and not args.auto_confirm_sim:
            errors.append(
                "InteractionResponse requires confirmation, but this text check "
                "does not collect a spoken confirmation reply."
            )

        if not errors and not args.preview_only:
            execution_start = time.perf_counter()
            execution = await assistant.execute_interaction_response(response, sid)
            timings_ms["execution_ms"] = (
                time.perf_counter() - execution_start
            ) * 1000.0
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
                status_after_start = time.perf_counter()
                status_after = await _invoke_soridormi_status(invoker)
            except Exception as exc:
                errors.append(f"post-run Soridormi status probe failed: {_exception_text(exc)}")
                _write_json(
                    evidence_dir / "status_after_error.json",
                    {"error": _exception_text(exc)},
                )
            else:
                timings_ms["status_after_ms"] = (
                    time.perf_counter() - status_after_start
                ) * 1000.0
                _write_json(evidence_dir / "status_after.json", status_after)
                errors.extend(safe_idle_errors(status_after))

            session_state = assistant.sessions.state.get(sid) or {}
            require_tts = should_require_tts_speech(
                route,
                require_speech=args.require_speech,
            )
            if require_tts and int(session_state.get("scheduled_tts", 0)) < 1:
                errors.append("no TTS speech was scheduled")
            if require_tts and int(session_state.get("failed_tts", 0)) > 0:
                errors.append(f"TTS failed {session_state.get('failed_tts')} time(s)")

        debug_summary = build_debug_summary(
            route=route,
            response=response,
            errors=errors,
        )
        summary = {
            "ok": not errors,
            "text": args.text,
            "sid": sid,
            "speaker": args.speaker,
            "preview_only": args.preview_only,
            "skill_timeout_s": args.skill_timeout_s,
            "evidence_dir": str(evidence_dir),
            "timings_ms": {
                **{name: round(value, 1) for name, value in timings_ms.items()},
                "total_ms": round((time.perf_counter() - total_start) * 1000.0, 1),
            },
            "debug_summary": debug_summary,
            "errors": errors,
            "route": route.model_dump(mode="json"),
            "interaction_response": response.model_dump(mode="json"),
            "cognitive_runtime": cognitive_resolution_payload,
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
        "--conversation-id",
        default="",
        help=(
            "Optional isolated conversation ID. Live acceptance supplies one per case "
            "to prevent retained goal state from leaking between cases."
        ),
    )
    parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Play Chromie TTS through the configured speaker; use --no-speaker for headless checks.",
    )
    parser.add_argument(
        "--cognitive-runtime",
        action="store_true",
        help=(
            "Use the PR7 goal-association, Fast/Deep Planner, response-composer, "
            "and trusted runtime adapter instead of the legacy Agent /interaction path."
        ),
    )
    parser.add_argument(
        "--cognitive-apply-lanes",
        default="chat,robot_action",
        help="Comma-separated PR7 apply lanes used with --cognitive-runtime.",
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
        help="Optional post-run assertion; this is not sent to Router or Agent.",
    )
    parser.add_argument(
        "--expect-no-skills",
        action="store_true",
        help="Optional post-run assertion that no Soridormi skills were emitted.",
    )
    parser.add_argument(
        "--expect-skill",
        action="append",
        default=[],
        help="Optional post-run assertion for the exact Soridormi skill sequence.",
    )
    parser.add_argument(
        "--expect-arg",
        action="append",
        type=parse_expected_arg,
        default=[],
        metavar="INDEX:KEY=VALUE",
        help="Optional post-run assertion for a selected emitted skill argument.",
    )
    parser.add_argument("--arg-tolerance", type=float, default=1e-6)
    parser.add_argument(
        "--reject-internal-speech",
        action="store_true",
        help=(
            "Fail if TTS text leaks internal planner labels or model-facing "
            "skill IDs such as Task Split, Key Risk, Next Step, or soridormi.*."
        ),
    )
    parser.add_argument(
        "--reject-speech-pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="Additional case-insensitive regex that must not appear in emitted speech.",
    )
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
    print_debug_summary(summary["debug_summary"])
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
