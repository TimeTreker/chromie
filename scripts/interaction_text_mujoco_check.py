#!/usr/bin/env python3
"""Text-to-MuJoCo interaction check without microphone or ASR.

This runner feeds user text into the deployed Cognitive Core and, by default, the
maintained goal-driven cognitive runtime. It executes the resulting structured
response through the host Trusted Capability Runtime and optionally plays Chromie
speech through the configured speaker. An explicit legacy Agent ``/interaction``
compatibility mode remains available. This is a simulator/live-integration
check, not supervised microphone evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.runtime.evidence_identity import (
    load_runtime_evidence_identity,
)
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
    expected_capabilities: list[str],
    expect_no_capabilities: bool,
    expected_args: list[tuple[int, str, Any]],
    arg_tolerance: float,
) -> list[str]:
    errors: list[str] = []
    route_actions = [
        str(item.get("capability_id") or "")
        for item in getattr(route, "actions", [])
    ]
    capabilities = [
        item
        for item in getattr(response, "capabilities", [])
        if str(item.capability_id) != "chromie.speak"
    ]
    capability_ids = [item.capability_id for item in capabilities]

    if expected_route and route.route != expected_route:
        errors.append(f"route={route.route!r}, expected {expected_route!r}")

    if expected_capabilities:
        expects_only_soridormi = all(
            capability_id.startswith("soridormi.") for capability_id in expected_capabilities
        )
        if expects_only_soridormi and route.route != "robot_action":
            errors.append(f"route={route.route!r}, expected 'robot_action'")
        if expects_only_soridormi and route_actions and route_actions != expected_capabilities:
            errors.append(
                "goal interpretation actions mismatch: "
                f"expected {expected_capabilities!r}, got {route_actions!r}"
            )
        if capability_ids != expected_capabilities:
            errors.append(
                "interaction capabilities mismatch: "
                f"expected {expected_capabilities!r}, got {capability_ids!r}"
            )

    if expect_no_capabilities:
        if route_actions:
            errors.append(f"goal interpretation emitted Soridormi actions, expected none: {route_actions!r}")
        if capability_ids:
            errors.append(f"interaction emitted executable capabilities, expected none: {capability_ids!r}")

    for index, key, expected in expected_args:
        if index >= len(capabilities):
            errors.append(
                f"expected arg {index}:{key}={expected!r}, "
                f"but only {len(capabilities)} Soridormi skill(s) were emitted"
            )
            continue
        actual = capabilities[index].args.get(key)
        if not _numbers_close(actual, expected, tolerance=arg_tolerance):
            errors.append(
                f"arg mismatch for skill[{index}] {capabilities[index].capability_id} "
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
    if status.get("safe_idle") is not True:
        errors.append(f"safe_idle is not true: {status.get('safe_idle')!r}")
    if "active_task" not in status or status.get("active_task") is not None:
        errors.append(f"active_task is not idle: {status.get('active_task')!r}")
    if status.get("emergency_stop") is not False:
        errors.append(f"emergency_stop is not false: {status.get('emergency_stop')!r}")
    if status.get("fallen") is not False:
        errors.append(f"fallen is not false: {status.get('fallen')!r}")
    return errors


def should_require_tts_speech(route: Any, *, require_speech: bool) -> bool:
    if not require_speech:
        return False
    if getattr(route, "route", "") == "interrupt":
        return False
    if getattr(route, "should_speak", True) is False:
        return False
    return True


def _workflow_field(message: str, key: str) -> str:
    match = re.search(rf"(?:^|\s){re.escape(key)}=([^\s]+)", message)
    if not match:
        return ""
    return match.group(1).strip().strip("'\"")


def required_speech_delivery_errors(
    session_state: Any,
    *,
    allow_interrupted: bool = False,
) -> list[str]:
    """Validate completed, correlated delivery for one required-speech turn."""

    if not isinstance(session_state, dict):
        return ["required speech delivery has no retained session state"]

    def count(name: str) -> int:
        try:
            return int(session_state.get(name, 0))
        except (TypeError, ValueError):
            return 0

    scheduled = count("scheduled_tts")
    played = count("played_tts")
    failed = count("failed_tts")
    skipped = count("skipped_tts")
    interrupted = session_state.get("interrupted") is True
    errors: list[str] = []
    if scheduled < 1:
        errors.append("required speech delivery scheduled no TTS items")
    if failed > 0:
        errors.append(f"required speech delivery failed {failed} TTS item(s)")
    if skipped > 0 and not (allow_interrupted and interrupted):
        errors.append(f"required speech delivery skipped {skipped} TTS item(s)")
    if scheduled < 1 or (
        played != scheduled and not (allow_interrupted and interrupted)
    ):
        errors.append(
            "required speech delivery incomplete: "
            f"scheduled={scheduled} played={played}"
        )

    workflow_events = session_state.get("workflow_events") or []
    if isinstance(workflow_events, list):
        for item in workflow_events:
            if not isinstance(item, dict) or item.get("event") != "capability_result":
                continue
            message = str(item.get("message") or "")
            capability_id = (
                _workflow_field(message, "capability_id")
            )
            status = _workflow_field(message, "status").casefold()
            if capability_id == "chromie.speak" and status not in {
                "completed",
                "ok",
                "success",
            }:
                errors.append(
                    "required chromie.speak execution failed with status "
                    f"{status or 'unknown'!r}"
                )
    return errors


def should_apply_cognitive_runtime(
    route: Any,
    *,
    enabled: bool,
    apply_lanes: str,
) -> bool:
    lanes = {item.strip() for item in apply_lanes.split(",") if item.strip()}
    route_name = str(getattr(route, "route", "") or "")
    lane = (
        "chat"
        if route_name in {"chat", "clarify", "deep_thought"}
        else route_name
    )
    return bool(
        enabled
        and not getattr(route, "interrupt_current", False)
        and route_name not in {"interrupt", "ignore"}
        and lane in lanes
    )


def _short_capability_id(item: dict[str, Any]) -> str:
    capability_id = str(item.get("capability_id") or "").strip()
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
    capabilities = [
        str(item.capability_id)
        for item in getattr(response, "capabilities", [])
        if str(item.capability_id).startswith("soridormi.")
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
        "capabilities": capabilities,
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
    if debug_summary.get("capabilities"):
        print(
            "[interaction-text-mujoco][debug] emitted_skills: "
            + ", ".join(debug_summary["capabilities"]),
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


def _git_text(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _manifest_upstream_revision(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        return None
    revision = str(metadata.get("upstream_commit") or "").strip()
    return revision or None


def _endpoint_source_revision(status: dict[str, Any] | None) -> str | None:
    if not isinstance(status, dict):
        return None
    candidates: list[Any] = [
        status.get("source_revision"),
        status.get("provider_revision"),
        status.get("build_revision"),
        status.get("revision"),
    ]
    for key in ("metadata", "provider", "build"):
        nested = status.get(key)
        if isinstance(nested, dict):
            candidates.extend(
                [
                    nested.get("source_revision"),
                    nested.get("provider_revision"),
                    nested.get("build_revision"),
                    nested.get("revision"),
                    nested.get("git_revision"),
                ]
            )
    for value in candidates:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def collect_run_provenance(
    *,
    manifest: Path,
    cognitive_runtime: bool,
    cognitive_apply_lanes: str,
    cognitive_runtime_selected: bool | None = None,
    soridormi_repo: Path | None = None,
    endpoint_revision: str | None = None,
    runtime_identity_path: Path | None = None,
    semantic_runtime_path: str | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Capture the source and semantic-runtime identity for retained evidence."""

    version_path = root / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip() or None
    except OSError:
        version = None
    revision = _git_text(root, "rev-parse", "HEAD")
    status = _git_text(root, "status", "--short")
    manifest_path = manifest.expanduser().resolve()
    soridormi_repo_path = soridormi_repo.expanduser().resolve() if soridormi_repo else None
    soridormi_revision = (
        _git_text(soridormi_repo_path, "rev-parse", "HEAD")
        if soridormi_repo_path is not None
        else None
    )
    soridormi_status = (
        _git_text(soridormi_repo_path, "status", "--short")
        if soridormi_repo_path is not None
        else None
    )
    lanes = [item.strip() for item in cognitive_apply_lanes.split(",") if item.strip()]
    selected = cognitive_runtime if cognitive_runtime_selected is None else bool(
        cognitive_runtime_selected
    )
    runtime_identity = load_runtime_evidence_identity(runtime_identity_path)
    runtime_identity_ref = {
        "path": str(runtime_identity_path) if runtime_identity_path else None,
        "identity_sha256": (
            runtime_identity.get("identity_sha256")
            if isinstance(runtime_identity, dict)
            else None
        ),
        "complete": runtime_identity is not None,
    }
    source_binding = (
        "endpoint_reported_revision"
        if endpoint_revision
        else "declared_paired_checkout"
    )
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "chromie": {
            "revision": revision,
            "version": version,
            "dirty": None if status is None else bool(status),
        },
        "soridormi": {
            "manifest": str(manifest_path),
            "upstream_revision": _manifest_upstream_revision(manifest_path),
            "checkout": str(soridormi_repo_path) if soridormi_repo_path else None,
            "checkout_revision": soridormi_revision,
            "checkout_dirty": (
                None if soridormi_status is None else bool(soridormi_status)
            ),
            "source_binding": source_binding,
            "endpoint_revision": endpoint_revision,
        },
        "runtime_identity": runtime_identity_ref,
        "semantic_runtime": {
            "path": (
                semantic_runtime_path
                or (
                    "goal_driven_cognitive_runtime"
                    if selected
                    else (
                        "agent_interaction_outside_apply_lanes"
                        if cognitive_runtime
                        else "legacy_agent_interaction"
                    )
                )
            ),
            "configured_cognitive_runtime_mode": (
                "apply" if cognitive_runtime else "off"
            ),
            "cognitive_runtime_selected_for_route": selected,
            "cognitive_apply_lanes": lanes if cognitive_runtime else [],
        },
    }


def _apply_soridormi_skill_timeout(response: Any, timeout_s: float | None) -> Any:
    if timeout_s is None or timeout_s <= 0:
        return response
    timeout_ms = int(timeout_s * 1000)
    capabilities = [
        skill.model_copy(
            update={"timeout_ms": max(int(skill.timeout_ms or 0), timeout_ms)}
        )
        if str(skill.capability_id).startswith("soridormi.")
        else skill
        for skill in response.capabilities
    ]
    return response.model_copy(deep=True, update={"capabilities": capabilities})


def _configure_environment(args: argparse.Namespace, evidence_dir: Path) -> None:
    # Imported Orchestrator use intentionally does not load generated runtime
    # configuration by itself. This live qualification runner is an explicit
    # bootstrap, so load the owned profile before applying its diagnostic-only
    # I/O, conversation, and evidence overrides. Without this call the runner
    # silently falls back to short production defaults (for example the 3.5s
    # Goal Association wait) even when .env.runtime contains the reviewed
    # architecture-validation budgets.
    from orchestrator.orchestrator import load_runtime_environment  # noqa: PLC0415

    load_runtime_environment()
    os.environ["AGENT_URL"] = args.agent_url
    os.environ["ORCH_ENABLE_AGENT"] = "1"
    os.environ["ORCH_ENABLE_INTERACTION_RESPONSE"] = "1"
    os.environ["ORCH_ENABLE_SORIDORMI_CAPABILITIES"] = "1"
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
    os.environ["ORCH_COGNITIVE_RUNTIME_MODE"] = (
        "apply" if args.cognitive_runtime else "off"
    )
    runtime_identity = getattr(args, "runtime_identity", None)
    if runtime_identity:
        os.environ["ORCH_COGNITIVE_RUN_IDENTITY_PATH"] = str(runtime_identity)
    if args.cognitive_runtime:
        os.environ["ORCH_COGNITIVE_APPLY_LANES"] = args.cognitive_apply_lanes
        os.environ["ORCH_COGNITIVE_FALLBACK_POLICY"] = "fail_closed"
        os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"] = "1"
        os.environ["ORCH_COGNITIVE_EVIDENCE_PATH"] = str(
            evidence_dir / "cognitive_runtime_events.jsonl"
        )
    else:
        os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"] = "0"
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


async def wait_for_session_done(
    assistant: Any,
    sid: str,
    *,
    timeout_s: float,
    allow_interrupted: bool = False,
) -> str:
    """Wait for the normal or explicitly allowed interrupted terminal state."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = assistant.sessions.state.get(sid) or {}
        if state.get("done_logged"):
            return "done"
        if (
            allow_interrupted
            and state.get("interrupted")
            and state.get("llm_done")
        ):
            return "interrupted"
        await asyncio.sleep(0.05)
    raise TimeoutError(f"session {sid} did not finish within {timeout_s:.1f}s")


async def wait_for_provider_started(
    runtime: Any,
    *,
    interaction_id: str,
    skill_prefix: str,
    timeout_s: float,
) -> dict[str, Any]:
    """Wait until a matching provider request has actually started.

    Cancellation qualification must not issue the interrupt while work is only
    planned or queued. The Trusted Capability Runtime observation excludes request
    arguments and provider payloads; it is used only to establish the timing
    boundary for the retained stop command.
    """

    # VoiceAssistant exposes the trusted runtime through its coordinator. Keep
    # the qualification boundary read-only while accepting either the
    # coordinator or the underlying CapabilityRuntime in focused tests/tools.
    observer = getattr(runtime, "runtime", runtime)
    observe = getattr(observer, "execution_observation", None)
    if not callable(observe):
        raise RuntimeError("Trusted Capability Runtime execution observation is unavailable")
    deadline = time.monotonic() + timeout_s
    last_observation: dict[str, Any] = {}
    while time.monotonic() < deadline:
        observation = await observe()
        last_observation = observation.model_dump(mode="json")
        for request in observation.requests:
            if (
                request.interaction_id == interaction_id
                and request.capability_id.startswith(skill_prefix)
                and request.provider_started
                and not request.task_done
            ):
                return last_observation
        await asyncio.sleep(0.05)
    raise TimeoutError(
        "no matching provider request started within "
        f"{timeout_s:.1f}s for interaction={interaction_id!r} "
        f"skill_prefix={skill_prefix!r}; last_observation={last_observation!r}"
    )


def record_execution_bindings(
    assistant: Any,
    response: Any,
    *,
    sid: str,
    confirmed_request_ids: set[str] | None,
) -> None:
    """Mirror the Host commit boundary before an acceptance-only execution."""

    conversation_state = getattr(assistant, "conversation_state", None)
    record = getattr(conversation_state, "record_agent_result", None)
    if not callable(record):
        raise RuntimeError("conversation state execution binding is unavailable")
    record(
        sid,
        response,
        confirmed_request_ids=confirmed_request_ids,
    )


async def dispatch_initial_reflex(
    *,
    assistant: Any,
    text: str,
    sid: str,
    turn_capture: Any,
    route_model: Any,
    timeout_s: float,
) -> tuple[Any, Any, dict[str, Any], list[str]]:
    """Exercise an admitted deterministic control through the production path.

    The text/MuJoCo runner captures the Gateway turn itself so it can retain
    evidence.  A matched reflex must still be dispatched by
    ``VoiceAssistant.handle_routed_text``: that is the owner of output
    invalidation, trusted cancellation, Goal reconciliation, and the guarantee
    that cognition is bypassed.
    """

    from shared.chromie_contracts.interaction import (  # noqa: PLC0415
        InteractionResponse,
    )

    outcome = turn_capture.reflex_candidate
    if outcome.action == "continue":
        raise ValueError("dispatch_initial_reflex requires a matched reflex")

    await assistant.handle_routed_text(text, sid, channel="text")
    await wait_for_session_done(
        assistant,
        sid,
        timeout_s=timeout_s,
        allow_interrupted=True,
    )

    recorded_turn: dict[str, Any] = {}
    for item in reversed(assistant.conversation_state.get_history()):
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if (
            isinstance(metadata, dict)
            and metadata.get("source") == "cognitive_gateway_reflex"
        ):
            recorded_turn = item
            break

    recorded_metadata = (
        recorded_turn.get("metadata")
        if isinstance(recorded_turn.get("metadata"), dict)
        else {}
    )
    recorded_outcome = (
        recorded_metadata.get("reflex_outcome")
        if isinstance(recorded_metadata.get("reflex_outcome"), dict)
        else {}
    )
    errors: list[str] = []
    if not recorded_turn:
        errors.append("production reflex dispatch retained no reflex user turn")
    if recorded_turn.get("route") != outcome.action:
        errors.append(
            "production reflex route mismatch: "
            f"expected {outcome.action!r}, got {recorded_turn.get('route')!r}"
        )
    if recorded_turn.get("intent") != outcome.intent:
        errors.append(
            "production reflex intent mismatch: "
            f"expected {outcome.intent!r}, got {recorded_turn.get('intent')!r}"
        )
    if recorded_outcome.get("cancellation_scope") != outcome.cancellation_scope:
        errors.append(
            "production reflex cancellation scope mismatch: "
            f"expected {outcome.cancellation_scope!r}, got "
            f"{recorded_outcome.get('cancellation_scope')!r}"
        )
    if outcome.action == "interrupt" and not isinstance(
        recorded_metadata.get("cancellation_dispatch_receipt"), dict
    ):
        errors.append("production interrupt retained no cancellation dispatch receipt")

    reflex_evidence = {
        "captured_outcome": outcome.model_dump(mode="json"),
        "recorded_turn": recorded_turn,
        "goal_interpretation_bypassed": True,
    }
    route = route_model.model_validate(
        {
            "route": outcome.action,
            "intent": outcome.intent,
            "confidence": outcome.confidence,
            "language": outcome.language,
            "priority": outcome.priority,
            "interrupt_current": outcome.interrupt_current,
            "needs_agent": False,
            "should_speak": outcome.should_speak,
            "reason": outcome.reason,
            "source": "rules",
            "metadata": {
                "cancellation_scope": outcome.cancellation_scope,
                "reflex_outcome": recorded_outcome,
                "goal_interpretation_bypassed": True,
            },
        }
    )
    response = InteractionResponse(
        metadata={
            "source": "cognitive_gateway_reflex",
            "reflex_action": outcome.action,
            "no_interaction_response": True,
        }
    )
    return route, response, reflex_evidence, errors


async def run_check(
    args: argparse.Namespace,
    *,
    assistant: Any | None = None,
    configure_environment: bool = True,
) -> dict[str, Any]:
    evidence_dir = Path(args.evidence_dir or DEFAULT_EVIDENCE_ROOT / acceptance_id())
    evidence_dir = evidence_dir.expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if configure_environment:
        _configure_environment(args, evidence_dir)
    raw_soridormi_repo = str(getattr(args, "soridormi_repo", "") or "").strip()

    # Import after the explicit environment bootstrap and harness overrides.
    from orchestrator.orchestrator import VoiceAssistant  # noqa: PLC0415
    from orchestrator.schemas.route import RouteDecision  # noqa: PLC0415

    owns_assistant = assistant is None
    if assistant is None:
        assistant = VoiceAssistant()
    errors: list[str] = []
    timings_ms: dict[str, float] = {}
    total_start = time.perf_counter()
    execution_payload: dict[str, Any] | None = None
    status_before: dict[str, Any] | None = None
    status_after: dict[str, Any] | None = None
    cognitive_runtime_selected = False
    interrupt_payload: dict[str, Any] | None = None

    try:
        health_start = time.perf_counter()
        session = await assistant.get_http_session()
        agent_health = await assistant.agent_client.health(session)
        timings_ms["health_ms"] = (time.perf_counter() - health_start) * 1000.0
        _write_json(evidence_dir / "agent_health.json", agent_health)

        if "soridormi" not in set(agent_health.get("capability_sources") or []):
            errors.append(
                "Agent service did not load the Soridormi manifest. "
                "Start Chromie with AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json."
            )

        invoker = assistant.interaction_runtime.soridormi_invoker
        if invoker is None:
            raise RuntimeError("Soridormi Trusted Capability Runtime invoker is not configured")

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

        gateway = assistant._cognitive_gateway_adapter()
        turn_capture = gateway.capture(
            args.text,
            session_id=sid,
            conversation_id=context.get("conversation_id"),
            channel="text",
        )
        if turn_capture.reflex_candidate.action != "continue":
            if args.preview_only:
                raise RuntimeError(
                    "preview-only cannot dispatch a deterministic reflex; use a "
                    "non-preview retained run so cancellation evidence is real"
                )
            reflex_start = time.perf_counter()
            route, response, reflex_evidence, reflex_errors = (
                await dispatch_initial_reflex(
                    assistant=assistant,
                    text=args.text,
                    sid=sid,
                    turn_capture=turn_capture,
                    route_model=RouteDecision,
                    timeout_s=args.timeout_s,
                )
            )
            timings_ms["reflex_ms"] = (
                time.perf_counter() - reflex_start
            ) * 1000.0
            errors.extend(reflex_errors)
            errors.extend(
                validate_contract(
                    route=route,
                    response=response,
                    expected_route=args.expect_route,
                    expected_capabilities=args.expect_capability,
                    expect_no_capabilities=args.expect_no_capabilities,
                    expected_args=args.expect_arg,
                    arg_tolerance=args.arg_tolerance,
                )
            )
            reject_speech_patterns = list(
                getattr(args, "reject_speech_pattern", []) or []
            )
            if bool(getattr(args, "reject_internal_speech", False)):
                reject_speech_patterns = (
                    INTERNAL_SPEECH_PATTERNS + reject_speech_patterns
                )
            errors.extend(
                validate_speech_contract(response, reject_speech_patterns)
            )

            _write_json(evidence_dir / "reflex.json", reflex_evidence)
            _write_json(evidence_dir / "route.json", route.model_dump(mode="json"))
            _write_json(
                evidence_dir / "interaction_response.json",
                response.model_dump(mode="json"),
            )
            try:
                status_after_start = time.perf_counter()
                status_after = await _invoke_soridormi_status(invoker)
            except Exception as exc:
                errors.append(
                    "post-reflex Soridormi status probe failed: "
                    f"{_exception_text(exc)}"
                )
                _write_json(
                    evidence_dir / "status_after_error.json",
                    {"error": _exception_text(exc)},
                )
            else:
                timings_ms["status_after_ms"] = (
                    time.perf_counter() - status_after_start
                ) * 1000.0
                _write_json(evidence_dir / "status_after.json", status_after)
                if not args.allow_non_sim and status_after.get("mode") != "sim":
                    errors.append(
                        "Post-reflex Soridormi mode is not sim: "
                        f"{status_after.get('mode')!r}"
                    )
                errors.extend(safe_idle_errors(status_after))

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
                "preview_only": False,
                "capability_timeout_s": args.capability_timeout_s,
                "evidence_dir": str(evidence_dir),
                "timings_ms": {
                    **{
                        name: round(value, 1)
                        for name, value in timings_ms.items()
                    },
                    "total_ms": round(
                        (time.perf_counter() - total_start) * 1000.0,
                        1,
                    ),
                },
                "debug_summary": debug_summary,
                "errors": errors,
                "route": route.model_dump(mode="json"),
                "interaction_response": response.model_dump(mode="json"),
                "reflex": reflex_evidence,
                "cognitive_runtime": None,
                "execution": None,
                "interrupt": None,
                "cognitive_events": str(
                    evidence_dir / "cognitive_runtime_events.jsonl"
                ),
                "status_before": status_before,
                "status_after": status_after,
                "session_state": assistant.sessions.state.get(sid),
                "provenance": collect_run_provenance(
                    manifest=Path(args.manifest),
                    cognitive_runtime=bool(args.cognitive_runtime),
                    cognitive_apply_lanes=str(args.cognitive_apply_lanes),
                    cognitive_runtime_selected=False,
                    soridormi_repo=(
                        Path(raw_soridormi_repo)
                        if raw_soridormi_repo
                        else None
                    ),
                    endpoint_revision=_endpoint_source_revision(status_before),
                    runtime_identity_path=(
                        Path(args.runtime_identity)
                        if getattr(args, "runtime_identity", None)
                        else None
                    ),
                    semantic_runtime_path="cognitive_gateway_reflex",
                ),
            }
            _write_json(evidence_dir / "summary.json", summary)
            return summary
        context_snapshot = gateway.assemble_context(turn_capture, context)
        attention_request = gateway.attention_request(
            turn_capture,
            context_snapshot,
        )
        attention_review = await assistant.agent_client.review_attention(
            session,
            request=attention_request,
        )
        _write_json(
            evidence_dir / "attention_review.json",
            {
                "request": attention_request.model_dump(mode="json"),
                "result": attention_review.model_dump(mode="json"),
            },
        )
        turn_envelope = gateway.admit_attention(
            turn_capture,
            context_snapshot,
            attention_review,
        )
        if turn_envelope.admission != "admit":
            raise RuntimeError(
                "text-to-MuJoCo acceptance input was suppressed before Core entry"
            )

        route_start = time.perf_counter()
        core_interpretation = await assistant.agent_client.interpret_turn(
            session,
            turn_envelope=turn_envelope,
            context_snapshot=context_snapshot,
        )
        route = RouteDecision.model_validate(
            core_interpretation.route_decision_projection().model_dump(
                mode="json"
            )
        )
        route_ms = (time.perf_counter() - route_start) * 1000.0
        timings_ms["route_ms"] = route_ms
        _write_json(
            evidence_dir / "core_interpretation.json",
            core_interpretation.model_dump(mode="json"),
        )
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
        cognitive_runtime_selected = should_apply_cognitive_runtime(
            route,
            enabled=bool(args.cognitive_runtime),
            apply_lanes=str(args.cognitive_apply_lanes),
        )
        if cognitive_runtime_selected:
            cognitive_resolution = await assistant._run_cognitive_runtime_pipeline(
                session,
                user_text=args.text,
                session_id=sid,
                context=context,
                decision=route,
                core_interpretation=core_interpretation,
                record_evidence=False,
                turn_envelope=turn_envelope,
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
                    **assistant._metadata_with_turn_envelope(
                        response.metadata,
                        turn_envelope,
                    ),
                    "goal_state_results": goal_state_results,
                    "cognitive_runtime_resolution": (
                        assistant._cognitive_resolution_summary(
                            cognitive_resolution
                        )
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
        response = _apply_soridormi_skill_timeout(response, args.capability_timeout_s)
        _write_json(
            evidence_dir / "interaction_response.json",
            response.model_dump(mode="json"),
        )
        assistant.session_log(
            sid,
            "text_check_interaction_done: status=%s speech=%s capabilities=%s confirmation=%s agent_ms=%.1f",
            response.status,
            len(response.speech),
            len(response.capabilities),
            response.requires_confirmation,
            agent_ms,
        )

        errors.extend(
            validate_contract(
                route=route,
                response=response,
                expected_route=args.expect_route,
                expected_capabilities=args.expect_capability,
                expect_no_capabilities=args.expect_no_capabilities,
                expected_args=args.expect_arg,
                arg_tolerance=args.arg_tolerance,
            )
        )
        reject_speech_patterns = list(getattr(args, "reject_speech_pattern", []) or [])
        if bool(getattr(args, "reject_internal_speech", False)):
            reject_speech_patterns = INTERNAL_SPEECH_PATTERNS + reject_speech_patterns
        errors.extend(validate_speech_contract(response, reject_speech_patterns))

        confirmation_request_ids = (
            await assistant.interaction_runtime.confirmation_request_ids(response)
        )
        assistant.conversation_state.record_user_turn(
            sid,
            args.text,
            route=route.route,
            intent=route.intent,
            metadata={
                "source": "interaction_text_mujoco_check",
                "semantic_task_resolution_authoritative": bool(
                    cognitive_runtime_selected
                ),
                "turn_envelope": turn_envelope.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
            },
        )
        if args.preview_only or errors:
            assistant.conversation_state.record_agent_result(sid, response)
        if confirmation_request_ids and not args.grant_confirmation:
            errors.append(
                "The provider/Host contract requires confirmation, but this text "
                "check was not given an explicit confirmation grant."
            )

        if not errors and not args.preview_only:
            execution_start = time.perf_counter()
            confirmed = confirmation_request_ids if args.grant_confirmation else None
            record_execution_bindings(
                assistant,
                response,
                sid=sid,
                confirmed_request_ids=confirmed,
            )
            before_result_tasks = set(
                getattr(assistant, "active_capability_result_tasks", {})
            )
            await assistant._dispatch_detached_interaction(
                response,
                sid,
                confirmed_request_ids=confirmed,
                reset_playback=True,
                mark_session_done=True,
            )
            current_result_tasks = getattr(
                assistant, "active_capability_result_tasks", {}
            )
            created_result_tasks = [
                task
                for task in current_result_tasks
                if task not in before_result_tasks
            ]
            if len(created_result_tasks) != 1:
                raise RuntimeError(
                    "detached interaction did not register exactly one result task"
                )
            execution_task = created_result_tasks[0]

            if args.interrupt_text:
                provider_observation = await wait_for_provider_started(
                    assistant.interaction_runtime,
                    interaction_id=response.interaction_id,
                    skill_prefix=args.interrupt_capability_prefix,
                    timeout_s=args.interrupt_start_timeout_s,
                )
                interrupt_sid = assistant.create_session()
                interrupt_started = time.perf_counter()
                await assistant.handle_routed_text(
                    args.interrupt_text,
                    interrupt_sid,
                    channel="text",
                )
                await wait_for_session_done(
                    assistant,
                    interrupt_sid,
                    timeout_s=args.timeout_s,
                )
                interrupt_payload = {
                    "text": args.interrupt_text,
                    "text_sha256": hashlib.sha256(
                        args.interrupt_text.encode("utf-8")
                    ).hexdigest(),
                    "sid": interrupt_sid,
                    "duration_ms": round(
                        (time.perf_counter() - interrupt_started) * 1000.0, 1
                    ),
                    "provider_observation_before_interrupt": provider_observation,
                    "session_state": assistant.sessions.state.get(interrupt_sid),
                }
                _write_json(evidence_dir / "interrupt.json", interrupt_payload)
            execution = await asyncio.wait_for(
                asyncio.shield(execution_task),
                timeout=args.timeout_s,
            )
            timings_ms["execution_ms"] = (
                time.perf_counter() - execution_start
            ) * 1000.0
            if execution is None:
                raise RuntimeError("Interaction execution returned no result")
            execution_payload = execution.model_dump(mode="json")
            _write_json(evidence_dir / "execution.json", execution_payload)
            body_results = [
                result
                for result in execution.results
                if result.capability_id.startswith("soridormi.")
            ]
            if args.expect_cancelled:
                if not args.interrupt_text:
                    errors.append("--expect-cancelled requires --interrupt-text")
                if execution.status != "cancelled":
                    errors.append(
                        f"Trusted Capability Runtime status was {execution.status!r}; expected 'cancelled'"
                    )
                cancelled_body = [
                    result
                    for result in body_results
                    if result.status == "cancelled"
                    and str(result.reason_code or "").startswith("cancelled")
                ]
                if not cancelled_body:
                    errors.append(
                        "no Soridormi result retained trusted cancellation evidence"
                    )
            else:
                if execution.status != "completed":
                    errors.append(f"Trusted Capability Runtime status was {execution.status!r}")
                for result in body_results:
                    if result.status != "completed":
                        errors.append(
                            f"{result.capability_id} ended with status {result.status!r}: "
                            f"{result.reason_code or result.message}"
                        )
            try:
                await wait_for_session_done(
                    assistant,
                    sid,
                    timeout_s=args.timeout_s,
                    allow_interrupted=bool(args.interrupt_text),
                )
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
                if not args.allow_non_sim and status_after.get("mode") != "sim":
                    errors.append(
                        "Post-run Soridormi mode is not sim: "
                        f"{status_after.get('mode')!r}"
                    )
                errors.extend(safe_idle_errors(status_after))

            session_state = assistant.sessions.state.get(sid) or {}
            require_tts = should_require_tts_speech(
                route,
                require_speech=args.require_speech,
            )
            if require_tts:
                errors.extend(
                    required_speech_delivery_errors(
                        session_state,
                        allow_interrupted=bool(args.interrupt_text),
                    )
                )

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
            "capability_timeout_s": args.capability_timeout_s,
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
            "interrupt": interrupt_payload,
            "cognitive_events": str(
                evidence_dir / "cognitive_runtime_events.jsonl"
            ),
            "status_before": status_before,
            "status_after": status_after,
            "session_state": assistant.sessions.state.get(sid),
            "provenance": collect_run_provenance(
                manifest=Path(args.manifest),
                cognitive_runtime=bool(args.cognitive_runtime),
                cognitive_apply_lanes=str(args.cognitive_apply_lanes),
                cognitive_runtime_selected=cognitive_runtime_selected,
                soridormi_repo=(
                    Path(raw_soridormi_repo) if raw_soridormi_repo else None
                ),
                endpoint_revision=_endpoint_source_revision(status_before),
                runtime_identity_path=(
                    Path(args.runtime_identity)
                    if getattr(args, "runtime_identity", None)
                    else None
                ),
            ),
        }
        _write_json(evidence_dir / "summary.json", summary)
        return summary
    finally:
        if owns_assistant:
            await assistant.cleanup()


async def run_check_sequence(
    turn_args: list[argparse.Namespace],
    *,
    evidence_dir: Path,
) -> list[dict[str, Any]]:
    """Run multiple retained turns through one live conversation state.

    The first turn configures and owns the shared Host runtime. Each later turn
    gets a fresh SID and artifact directory while reusing the same bounded
    conversation, Goal snapshots, tool evidence, and deployed service clients.
    A basic runner failure stops the episode so later turns cannot disguise the
    earliest failed boundary.
    """

    if not turn_args:
        raise ValueError("live text sequence requires at least one turn")
    root = evidence_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _configure_environment(turn_args[0], root)

    from orchestrator.orchestrator import VoiceAssistant  # noqa: PLC0415

    assistant = VoiceAssistant()
    summaries: list[dict[str, Any]] = []
    try:
        for args in turn_args:
            summary = await run_check(
                args,
                assistant=assistant,
                configure_environment=False,
            )
            summaries.append(summary)
            if not summary.get("ok"):
                break
    finally:
        await assistant.cleanup()
    return summaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run text through the maintained goal-driven runtime and trusted "
            "Trusted Capability Runtime to Soridormi/MuJoCo without microphone or ASR."
        )
    )
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "capabilities" / "soridormi.json")
    parser.add_argument(
        "--soridormi-repo",
        default=os.getenv("SORIDORMI_REPO", ""),
        help=(
            "Declared paired Soridormi Git checkout recorded for diagnostic "
            "provenance; this does not identify the source executing behind the "
            "MCP endpoint."
        ),
    )
    parser.add_argument("--language", default=None)
    parser.add_argument("--evidence-dir")
    parser.add_argument(
        "--runtime-identity",
        type=Path,
        default=ROOT / ".chromie" / "evidence" / "runtime-identity.json",
        help="Source/model/image identity captured for the evaluated deployment.",
    )
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Use goal association, Fast/Deep Planner, response composition, and "
            "the trusted runtime adapter (default). Use --no-cognitive-runtime "
            "only for an explicit legacy Agent /interaction compatibility check."
        ),
    )
    parser.add_argument(
        "--cognitive-apply-lanes",
        default="chat,memory,robot_action,tool",
        help="Comma-separated PR7 apply lanes used with --cognitive-runtime.",
    )
    parser.add_argument("--preview-only", action="store_true", help="Route and validate /interaction without executing Soridormi capabilities.")
    parser.add_argument("--allow-non-sim", action="store_true", help="Permit non-sim Soridormi modes. Use only under separate supervision.")
    parser.add_argument(
        "--grant-confirmation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Grant any provider/Host-declared confirmation requirements inside "
            "this supervised diagnostic harness, independent of backend type."
        ),
    )
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
        help="Optional post-run assertion; this is not sent to the Cognitive Core or Agent runtime.",
    )
    parser.add_argument(
        "--expect-no-capabilities",
        action="store_true",
        help="Optional post-run assertion that no Soridormi capabilities were emitted.",
    )
    parser.add_argument(
        "--expect-capability",
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
        "--interrupt-text",
        default="",
        help=(
            "Optional deterministic interrupt utterance sent only after a matching "
            "provider request has started. Intended for supervised cancellation "
            "qualification, not normal interaction."
        ),
    )
    parser.add_argument(
        "--interrupt-capability-prefix",
        default="soridormi.",
        help="Skill prefix whose provider-start boundary triggers the interrupt.",
    )
    parser.add_argument(
        "--interrupt-start-timeout-s",
        type=float,
        default=30.0,
        help="Maximum wait for the selected provider-start boundary.",
    )
    parser.add_argument(
        "--expect-cancelled",
        action="store_true",
        help=(
            "Require a cancelled Trusted Capability Runtime result with trusted Soridormi "
            "cancellation evidence."
        ),
    )
    parser.add_argument(
        "--capability-timeout-s",
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
    if args.expect_no_capabilities and args.expect_capability:
        parser.error("--expect-no-capabilities cannot be combined with --expect-capability")
    if args.expect_cancelled and not args.interrupt_text:
        parser.error("--expect-cancelled requires --interrupt-text")
    if args.interrupt_text and args.preview_only:
        parser.error("--interrupt-text cannot be used with --preview-only")
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
