#!/usr/bin/env python3
"""Run maintained live-text Gateway/Core qualification scenarios.

This runner uses the deployed Agent and TTS services but bypasses microphone and
ASR. It does not inject expected routes, goals, tool calls, or responses into
Chromie. Expectations remain in the separate qualification manifest and are
checked only after evidence is retained.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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

from orchestrator.runtime.evidence_identity import (  # noqa: E402
    load_runtime_evidence_identity,
)
from scripts.interaction_text_mujoco_check import (  # noqa: E402
    required_speech_delivery_errors,
)

DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "cognitive_gateway_core_qualification_v1.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / ".chromie" / "acceptance" / "cognitive-gateway-core"


def _acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _wait_for_session_done(assistant: Any, sid: str, *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = assistant.sessions.state.get(sid) or {}
        if state.get("done_logged"):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"session {sid} did not finish within {timeout_s:.1f}s")


def _configure_environment(args: argparse.Namespace, output_dir: Path) -> None:
    # Directly importing VoiceAssistant does not load the generated runtime
    # profile. Live source-bound collection must use the same reviewed models
    # and cognitive budgets as the deployed composition before applying its
    # text-injection and evidence-path overrides.
    from orchestrator.orchestrator import load_runtime_environment  # noqa: PLC0415

    load_runtime_environment()
    os.environ["AGENT_URL"] = args.agent_url
    os.environ["ORCH_ENABLE_AGENT"] = "1"
    os.environ["ORCH_ENABLE_INTERACTION_RESPONSE"] = "1"
    os.environ["ORCH_ENABLE_SORIDORMI_CAPABILITIES"] = "0"
    os.environ["ORCH_AUDIO_INPUT_MODE"] = "stdin"
    os.environ["ORCH_AUDIO_OUTPUT_MODE"] = "device" if args.speaker else "discard"
    if not args.speaker:
        os.environ.setdefault("ORCH_DISCARD_PLAYBACK_REALTIME", "0")
    os.environ["ORCH_EVENT_LOG_PATH"] = str(output_dir / "session_events.jsonl")
    os.environ["ORCH_COGNITIVE_RUNTIME_MODE"] = "apply"
    os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"] = "1"
    os.environ["ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT"] = "0"
    os.environ["ORCH_COGNITIVE_EVIDENCE_PATH"] = str(
        output_dir / "cognitive_events.jsonl"
    )
    os.environ["ORCH_COGNITIVE_RUN_IDENTITY_PATH"] = str(args.runtime_identity)
    os.environ["ORCH_ENABLE_TASK_CONTEXT_STORE"] = "0"
    os.environ["RECORDINGS_DIR"] = str(output_dir / "recordings")


async def _run_scenario(
    scenario: dict[str, Any],
    *,
    timeout_s: float,
    output_dir: Path,
) -> dict[str, Any]:
    from orchestrator.orchestrator import VoiceAssistant  # noqa: PLC0415

    scenario_id = str(scenario.get("scenario_id") or "").strip()
    if not scenario_id:
        raise ValueError("qualification scenario is missing scenario_id")
    turns = scenario.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError(f"scenario {scenario_id}: turns must be a non-empty list")

    os.environ["ORCH_CONVERSATION_ID"] = f"gateway-core-{scenario_id}"
    assistant = VoiceAssistant()
    turn_results: list[dict[str, Any]] = []
    scenario_errors: list[str] = []
    try:
        for item in turns:
            if not isinstance(item, dict):
                raise ValueError(f"scenario {scenario_id}: turn must be an object")
            turn_key = str(item.get("turn_key") or "").strip()
            text = str(item.get("text") or "")
            if not turn_key or not text.strip():
                raise ValueError(
                    f"scenario {scenario_id}: every turn requires turn_key and text"
                )
            sid = assistant.create_session()
            started = time.perf_counter()
            error = ""
            try:
                await assistant.handle_routed_text(text, sid, channel="text")
                await _wait_for_session_done(assistant, sid, timeout_s=timeout_s)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                scenario_errors.append(f"{turn_key}: {error}")
            context = assistant.build_context(sid)
            history = context.get("history")
            session_state = assistant.sessions.state.get(sid)
            expectations = item.get("expect")
            if (
                isinstance(expectations, dict)
                and expectations.get("require_delivered_speech") is True
            ):
                scenario_errors.extend(
                    f"{turn_key}: {delivery_error}"
                    for delivery_error in required_speech_delivery_errors(
                        session_state
                    )
                )
            turn_results.append(
                {
                    "turn_key": turn_key,
                    "sid": sid,
                    "conversation_id": context.get("conversation_id"),
                    "text": text,
                    "text_sha256": _text_sha256(text),
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 1),
                    "error": error or None,
                    "session_state": session_state,
                    "history_tail": (
                        list(history[-6:]) if isinstance(history, list) else []
                    ),
                }
            )
    finally:
        await assistant.cleanup()

    scenario_dir = output_dir / "scenarios" / scenario_id
    result = {
        "scenario_id": scenario_id,
        "conversation_scope": scenario.get("conversation_scope"),
        "ok": not scenario_errors,
        "errors": scenario_errors,
        "turns": turn_results,
    }
    _write_json(scenario_dir / "summary.json", result)
    return result


async def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest).expanduser().resolve()
    runtime_identity_path = Path(args.runtime_identity).expanduser().resolve()
    output_dir = Path(args.output_dir or DEFAULT_OUTPUT_ROOT / _acceptance_id())
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported Gateway/Core qualification manifest")
    identity = load_runtime_evidence_identity(runtime_identity_path)
    if identity is None:
        raise ValueError(
            "source-bound runtime identity is missing; run "
            "scripts/capture_runtime_identity.py first"
        )
    _configure_environment(args, output_dir)

    selected = set(args.scenario or [])
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("qualification manifest scenarios must be a list")
    if selected:
        scenarios = [
            item
            for item in scenarios
            if isinstance(item, dict) and item.get("scenario_id") in selected
        ]
        missing = selected - {
            str(item.get("scenario_id")) for item in scenarios if isinstance(item, dict)
        }
        if missing:
            raise ValueError("unknown scenario IDs: " + ", ".join(sorted(missing)))

    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("qualification scenario must be an object")
        results.append(
            await _run_scenario(
                scenario,
                timeout_s=args.timeout_s,
                output_dir=output_dir,
            )
        )

    summary = {
        "schema_version": 1,
        "qualification_id": manifest.get("qualification_id"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "live_service_text",
        "manifest": str(manifest_path),
        "runtime_identity": {
            "path": str(runtime_identity_path),
            "identity_sha256": identity["identity_sha256"],
        },
        "cognitive_events": str(output_dir / "cognitive_events.jsonl"),
        "session_events": str(output_dir / "session_events.jsonl"),
        "scenarios": results,
        "ok": all(item["ok"] for item in results),
        "release_qualified": False,
        "human_review_required": True,
        "evidence_dir": str(output_dir),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--runtime-identity",
        type=Path,
        default=ROOT / ".chromie" / "evidence" / "runtime-identity.json",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = asyncio.run(run(args))
    except Exception as exc:
        print(f"[gateway-core-live-text][error] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
