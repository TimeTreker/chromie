#!/usr/bin/env python3
"""Deep-thought response scenario check.

This runner feeds text directly into the host Orchestrator's routed text path
so it exercises the same pre-agent behavior used by live voice turns:

- Router selects ``deep_thought``.
- Chromie schedules the immediate thinking acknowledgement.
- Chromie optionally launches the simulator-safe thinking pose.
- The deepthinking Agent returns a final spoken response.

It skips microphone and ASR. Use ``--speaker`` when you also want to hear the
TTS output through the configured speaker.
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

DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "deep-thought"
DEFAULT_TEXT = (
    "Please think carefully and split the implementation plan for adding "
    "social.look_at_user: router trigger, ability registry mapping, "
    "Soridormi skill binding, and tests."
)


def acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def _event_contains(events: list[dict[str, Any]], *patterns: str) -> bool:
    for event in events:
        message = str(event.get("message") or "")
        if all(pattern in message for pattern in patterns):
            return True
    return False


def validate_deep_thought_events(
    events: list[dict[str, Any]],
    *,
    require_body_cue: bool,
    require_body_cue_completed: bool,
    require_agent_success: bool,
    min_scheduled_tts: int,
) -> list[str]:
    errors: list[str] = []
    if not _event_contains(events, "router_done:", "route=deep_thought"):
        errors.append("router did not report route=deep_thought")
    if not _event_contains(events, "deep_thought_ack_schedule:"):
        errors.append("deep-thought thinking acknowledgement was not scheduled")
    if not _event_contains(events, "deep_thought_ack_scheduled:"):
        errors.append("deep-thought thinking acknowledgement did not enter TTS")
    if require_body_cue and not _event_contains(
        events,
        "deep_thought_body_cue_launch:",
        "soridormi.express_attention",
    ):
        errors.append("thinking body cue was not launched")
    if require_body_cue_completed and not _event_contains(
        events,
        "skill_result:",
        "skill_id=soridormi.express_attention",
        "status=completed",
    ):
        errors.append("thinking body cue did not complete")
    if require_agent_success:
        if _event_contains(events, "agent_exception:"):
            errors.append(
                "deepthinking Agent failed; rebuild/restart Chromie services if "
                "the running agent image is stale"
            )
        if not (
            _event_contains(events, "interaction_done:")
            or _event_contains(events, "agent_done:")
        ):
            errors.append("deepthinking Agent did not produce a final response")
    done_events = [
        event
        for event in events
        if str(event.get("message") or "").startswith("session_done:")
    ]
    if not done_events:
        errors.append("session_done was not logged")
    elif min_scheduled_tts > 0:
        message = str(done_events[-1].get("message") or "")
        scheduled_token = f"scheduled_tts={min_scheduled_tts}"
        if scheduled_token not in message:
            try:
                scheduled = int(message.split("scheduled_tts=", 1)[1].split()[0])
            except (IndexError, ValueError):
                scheduled = -1
            if scheduled < min_scheduled_tts:
                errors.append(
                    "not enough TTS responses were scheduled: "
                    f"expected at least {min_scheduled_tts}, got {scheduled}"
                )
    return errors


def _configure_environment(args: argparse.Namespace, evidence_dir: Path) -> None:
    os.environ["ROUTER_URL"] = args.router_url
    os.environ["AGENT_URL"] = args.agent_url
    os.environ.setdefault("ORCH_ROUTER_TIMEOUT_MS", "10000")
    os.environ.setdefault("ORCH_AGENT_TIMEOUT_MS", "120000")
    os.environ["ORCH_ENABLE_ROUTER"] = "1"
    os.environ["ORCH_ENABLE_AGENT"] = "1"
    os.environ["ORCH_ENABLE_INTERACTION_RESPONSE"] = "1"
    os.environ["ORCH_ENABLE_SORIDORMI_SKILLS"] = "1"
    os.environ["ORCH_AUTO_CONFIRM_SIM_SKILLS"] = "1"
    os.environ["ORCH_ACTION_DRY_RUN"] = "1"
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


async def _wait_for_session_done(assistant: Any, sid: str, *, timeout_s: float) -> None:
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

    from orchestrator.orchestrator import VoiceAssistant  # noqa: PLC0415

    assistant = VoiceAssistant()
    errors: list[str] = []
    sid = assistant.create_session()
    try:
        await assistant.handle_routed_text(args.text, sid)
        try:
            await _wait_for_session_done(assistant, sid, timeout_s=args.timeout_s)
        except Exception as exc:
            errors.append(str(exc))

        event_path = evidence_dir / "events.jsonl"
        events = _read_jsonl(event_path)
        errors.extend(
            validate_deep_thought_events(
                events,
                require_body_cue=args.require_body_cue,
                require_body_cue_completed=args.require_body_cue_completed,
                require_agent_success=args.require_agent_success,
                min_scheduled_tts=args.min_scheduled_tts,
            )
        )
        session_state = assistant.sessions.state.get(sid) or {}
        if int(session_state.get("failed_tts", 0)) > 0:
            errors.append(f"TTS failed {session_state.get('failed_tts')} time(s)")
        summary = {
            "ok": not errors,
            "text": args.text,
            "sid": sid,
            "speaker": args.speaker,
            "evidence_dir": str(evidence_dir),
            "event_log": str(event_path),
            "errors": errors,
            "session_state": session_state,
            "checks": {
                "require_body_cue": args.require_body_cue,
                "require_body_cue_completed": args.require_body_cue_completed,
                "require_agent_success": args.require_agent_success,
                "min_scheduled_tts": args.min_scheduled_tts,
            },
        }
        _write_json(evidence_dir / "summary.json", summary)
        return summary
    finally:
        await assistant.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a no-microphone deep_thought acknowledgement/final-response check."
    )
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    parser.add_argument("--router-url", default=os.getenv("ROUTER_URL", "http://127.0.0.1:8091"))
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "capabilities" / "soridormi.json")
    parser.add_argument("--evidence-dir")
    parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Play Chromie TTS through the configured speaker.",
    )
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument(
        "--require-body-cue",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require the simulator-safe thinking pose to be launched.",
    )
    parser.add_argument(
        "--require-body-cue-completed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require soridormi.express_attention to complete.",
    )
    parser.add_argument(
        "--require-agent-success",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require the deepthinking Agent to return a final response without fallback.",
    )
    parser.add_argument(
        "--min-scheduled-tts",
        type=int,
        default=2,
        help="Minimum scheduled TTS items; 2 means acknowledgement plus final answer.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = asyncio.run(run_check(args))
    except Exception as exc:
        print(f"[deep-thought-response][error] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
