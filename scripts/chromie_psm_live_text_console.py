#!/usr/bin/env python3
"""Interactive no-microphone console for Chromie's live Cognitive Core / PSM workflow.

This is a development runner, not a second semantic path.

- Plain terminal text is injected at the maintained post-ASR text boundary through
  ``VoiceAssistant.handle_routed_text(..., channel='text')``.
- ``/presence`` injects an already-trusted person/presence/audience observation through
  the PSM-5 typed social-world ingress.
- ``/feedback`` injects an already-trusted observable social signal through the PSM-6
  feedback ingress.  It reports observations only; it never labels them as anger,
  approval, rejection, or a recommended response.

The runner intentionally does not implement family/friend/stranger behavior rules.
All ordinary social relevance, silence, wording, repair, deliberation, relationship
experience, and self-context decisions remain owned by the Cognitive Core.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Iterable


def _discover_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        root = explicit.expanduser().resolve()
        if not (root / "orchestrator" / "orchestrator.py").is_file():
            raise RuntimeError(f"not a Chromie checkout: {root}")
        return root
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError("git is required, or pass --repo-root") from exc
    if completed.returncode != 0:
        raise RuntimeError("run this from a Chromie checkout, or pass --repo-root")
    root = Path(completed.stdout.strip()).resolve()
    if not (root / "orchestrator" / "orchestrator.py").is_file():
        raise RuntimeError(f"git root is not a Chromie checkout: {root}")
    return root


def _utc_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _kv_options(parts: Iterable[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError(f"expected KEY=VALUE option, got {part!r}")
        key, value = part.split("=", 1)
        key = key.strip().casefold()
        if not key:
            raise ValueError("option key must not be empty")
        options[key] = value.strip()
    return options


def _history_len(assistant: Any) -> int:
    try:
        return len(assistant.conversation_state.get_history())
    except Exception:
        return 0


def _print_history_delta(assistant: Any, before: int) -> None:
    try:
        history = assistant.conversation_state.get_history()
    except Exception:
        return
    for item in history[before:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "?")
        text = str(item.get("text") or "").strip()
        if text:
            label = "you" if role == "user" else "Chromie" if role == "assistant" else role
            print(f"{label}> {text}")


def _interaction_context(assistant: Any, sid: str | None) -> dict[str, Any]:
    ledger = getattr(getattr(assistant, "cognitive_runtime", None), "interaction_ledger", None)
    if ledger is None:
        return {}
    scope = str(sid or getattr(assistant, "session_id", "") or "psm-console")
    try:
        value = ledger.context(scope, goal_ids=[], turn_id="psm-console")
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)
    except Exception:
        return {}


def _latest_delivered_activity_id(assistant: Any, sid: str | None) -> str:
    context = _interaction_context(assistant, sid)
    for event in reversed(context.get("already_spoken") or []):
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        activity_ids = metadata.get("communicative_activity_ids") or []
        for value in reversed(activity_ids if isinstance(activity_ids, list) else []):
            text = str(value or "").strip()
            if text:
                return text
    return ""


def _print_ledger(assistant: Any, sid: str | None) -> None:
    context = _interaction_context(assistant, sid)
    spoken = context.get("already_spoken") or []
    if not spoken:
        print("[ledger] no delivered speech in this scope")
        return
    print("[ledger] recently delivered:")
    for event in spoken[-8:]:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        ids = metadata.get("communicative_activity_ids") or []
        print(
            "  - "
            + json.dumps(
                {
                    "text": event.get("text"),
                    "speech_act": event.get("speech_act"),
                    "activity_ids": ids,
                    "situation_signature": metadata.get("situation_signature"),
                },
                ensure_ascii=False,
            )
        )


async def _wait_for_session_done(assistant: Any, sid: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = assistant.sessions.state.get(sid) or {}
        if state.get("done_logged"):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"session {sid} did not finish within {timeout_s:.1f}s")


def _configure_environment(root: Path, args: argparse.Namespace, output_dir: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from orchestrator.orchestrator import load_runtime_environment  # noqa: PLC0415

    # Load the same generated model/budget profile as normal deployment first.
    load_runtime_environment()

    os.environ["AGENT_URL"] = args.agent_url
    os.environ["ORCH_ENABLE_AGENT"] = "1"
    os.environ["ORCH_ENABLE_INTERACTION_RESPONSE"] = "1"
    os.environ["ORCH_AUDIO_INPUT_MODE"] = "stdin"  # bypass microphone/VAD/ASR
    os.environ["ORCH_AUDIO_OUTPUT_MODE"] = "device" if args.speaker else "discard"
    if not args.speaker:
        os.environ.setdefault("ORCH_DISCARD_PLAYBACK_REALTIME", "0")
    os.environ["ORCH_COGNITIVE_RUNTIME_MODE"] = "apply"
    os.environ["ORCH_CONVERSATION_ID"] = args.conversation_id
    os.environ["ORCH_EVENT_LOG_PATH"] = str(output_dir / "events.jsonl")
    os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"] = "1"
    os.environ["ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT"] = "1"
    os.environ["ORCH_COGNITIVE_EVIDENCE_PATH"] = str(output_dir / "cognitive_events.jsonl")
    os.environ["RECORDINGS_DIR"] = str(output_dir / "recordings")

    if args.capabilities:
        os.environ["ORCH_ENABLE_SORIDORMI_CAPABILITIES"] = "1"
        os.environ["ORCH_SORIDORMI_MANIFEST"] = str(args.manifest)
        if args.soridormi_mcp_url:
            os.environ["SORIDORMI_MCP_URL"] = args.soridormi_mcp_url
    else:
        os.environ["ORCH_ENABLE_SORIDORMI_CAPABILITIES"] = "0"


def _print_help() -> None:
    print(
        r"""
Plain text is treated exactly as user text after ASR.

Commands:
  /help
  /quit
  /context
  /memory
  /ledger

  /presence SUBJECT entered|present|left [identity=resolved|candidate|unknown]
            [confidence=0.95] [audience=person:dad,self:chromie]

    Example:
      /presence person:dad entered identity=resolved confidence=0.95 audience=person:dad,self:chromie
      /presence candidate:track-4 entered identity=candidate confidence=0.42
      /presence person:dad left identity=resolved confidence=0.99

  /feedback SUBJECT RELATION VALUE [activity=ACTIVITY_ID]
            [audience=person:anna,self:chromie]

    Example after Chromie has actually spoken:
      /feedback person:anna social.observed_signal turned_away audience=person:anna,self:chromie

    If activity= is omitted, the console mechanically targets the latest delivered
    situational Communicative Activity in the current social-event session.  The
    console does not interpret the signal or decide what Chromie should do.

Notes:
  - audience is NEVER inferred by this script. Supply it only when your manual test
    intends to stand in for a trusted audience/principal source.
  - /presence and /feedback inject source facts, not social behavior expectations.
  - PSM-7 experience memory, PSM-8 deliberation and PSM-9 self-context are produced
    by the Cognitive Core automatically; use /memory to inspect the retained result.
""".strip()
    )


async def _run_console(root: Path, args: argparse.Namespace) -> None:
    output_dir = (args.output_dir or root / ".chromie" / "acceptance" / "psm-live-text" / _utc_id())
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _configure_environment(root, args, output_dir)

    try:
        from orchestrator.orchestrator import VoiceAssistant  # noqa: PLC0415
        from orchestrator.runtime.playback_transport import (  # noqa: PLC0415
            transport_for as playback_transport_for,
        )
        from orchestrator.runtime.shutdown_lifecycle import (  # noqa: PLC0415
            shutdown_voice_assistant,
        )
        from orchestrator.runtime.situation import (  # noqa: PLC0415
            apply_goal_free_situation_opportunity,
            build_social_feedback_situation_observation,
            build_social_perception_situation_observation,
        )
        from shared.chromie_contracts.situation import SituationSourceRef  # noqa: PLC0415
        from shared.chromie_contracts.social_world import (  # noqa: PLC0415
            TrustedPersonPresence,
            TrustedSocialFeedbackObservation,
            TrustedSocialFeedbackSignal,
            TrustedSocialPerceptionObservation,
        )
    except ImportError as exc:
        raise RuntimeError(
            "This console requires the PSM-5..PSM-9 source patches to be applied. "
            f"Missing import: {exc}"
        ) from exc

    assistant = VoiceAssistant()
    source_id = "manual_psm_console"
    source_revision = 0
    last_social_sid: str | None = None
    last_social_digest = ""

    print("[psm-console] microphone/ASR bypassed; terminal text uses channel='text'.")
    print(f"[psm-console] evidence: {output_dir}")
    print(
        "[psm-console] Soridormi capabilities: "
        + ("enabled" if args.capabilities else "disabled")
        + "; speaker: "
        + ("device" if args.speaker else "discard")
    )
    print("[psm-console] type /help for commands.\n")

    try:
        while True:
            try:
                raw = await asyncio.to_thread(input, "you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            raw = raw.strip()
            if not raw:
                continue
            if raw in {"/quit", "/exit"}:
                break
            if raw == "/help":
                _print_help()
                continue
            if raw == "/context":
                context = assistant.build_context(last_social_sid)
                compact = {
                    "conversation_id": context.get("conversation_id"),
                    "active_goal_count": len(context.get("active_goal_snapshots") or []),
                    "pending_task_count": len(context.get("pending_tasks") or []),
                    "memory_summary": context.get("memory_summary"),
                    "history_tail": (context.get("history") or [])[-8:],
                }
                print(json.dumps(compact, ensure_ascii=False, indent=2, default=str))
                continue
            if raw == "/memory":
                memory = assistant.conversation_state.session_memory()
                compact = {
                    "summary": memory.get("summary"),
                    "extracted_memory": memory.get("extracted_memory"),
                }
                print(json.dumps(compact, ensure_ascii=False, indent=2, default=str))
                continue
            if raw == "/ledger":
                _print_ledger(assistant, last_social_sid)
                continue

            if raw.startswith("/presence "):
                parts = shlex.split(raw)
                if len(parts) < 3:
                    print("usage: /presence SUBJECT entered|present|left [KEY=VALUE ...]")
                    continue
                subject_ref = parts[1]
                presence = parts[2]
                options = _kv_options(parts[3:])
                identity_status = options.get("identity", "unknown")
                confidence = float(options.get("confidence", "0"))
                audience_refs = _csv(options.get("audience"))
                source_revision += 1
                ref_id = f"manual-social:{source_revision}"
                source = SituationSourceRef(
                    kind="perception",
                    reference_id=ref_id,
                    owner=source_id,
                )
                observation = TrustedSocialPerceptionObservation(
                    observation_id=f"manual-social-{source_revision}",
                    source_id=source_id,
                    source_revision=source_revision,
                    source_refs=[source],
                    people=[
                        TrustedPersonPresence(
                            subject_ref=subject_ref,
                            presence=presence,
                            identity_status=identity_status,
                            identity_confidence=confidence,
                            epistemic_status=(
                                "established" if identity_status == "resolved" else "provisional"
                            ),
                            source_refs=[ref_id],
                        )
                    ],
                    audience_refs=audience_refs,
                )
                situation = build_social_perception_situation_observation(
                    observation,
                    context=assistant.build_context(last_social_sid),
                )
                sid = assistant.create_session()
                before = _history_len(assistant)
                result = await apply_goal_free_situation_opportunity(
                    assistant,
                    situation,
                    previous_situation_digest=last_social_digest,
                    session_id=sid,
                    language=args.language,
                )
                last_social_sid = sid
                last_social_digest = situation.projection.digest
                print(f"[presence] runtime={result} digest={last_social_digest[:12]}")
                _print_history_delta(assistant, before)
                activity_id = _latest_delivered_activity_id(assistant, sid)
                if activity_id:
                    print(f"[presence] delivered_activity_id={activity_id}")
                continue

            if raw.startswith("/feedback "):
                parts = shlex.split(raw)
                if len(parts) < 4:
                    print("usage: /feedback SUBJECT RELATION VALUE [KEY=VALUE ...]")
                    continue
                subject_ref, relation, value = parts[1], parts[2], parts[3]
                options = _kv_options(parts[4:])
                audience_refs = _csv(options.get("audience"))
                target_activity = options.get("activity", "").strip()
                if not target_activity:
                    target_activity = _latest_delivered_activity_id(assistant, last_social_sid)
                if not target_activity:
                    print(
                        "[feedback] no delivered situational Activity is available; "
                        "pass activity=ACTIVITY_ID explicitly"
                    )
                    continue
                source_revision += 1
                ref_id = f"manual-feedback:{source_revision}"
                source = SituationSourceRef(
                    kind="perception",
                    reference_id=ref_id,
                    owner=source_id,
                )
                observation = TrustedSocialFeedbackObservation(
                    observation_id=f"manual-feedback-{source_revision}",
                    source_id=source_id,
                    source_revision=source_revision,
                    source_refs=[source],
                    reacts_to_activity_ids=[target_activity],
                    signals=[
                        TrustedSocialFeedbackSignal(
                            subject_ref=subject_ref,
                            relation=relation,
                            value=value,
                            epistemic_status="established",
                            source_refs=[ref_id],
                        )
                    ],
                    audience_refs=audience_refs,
                )
                situation = build_social_feedback_situation_observation(
                    observation,
                    context=assistant.build_context(last_social_sid),
                )
                sid = last_social_sid or assistant.create_session()
                before = _history_len(assistant)
                result = await apply_goal_free_situation_opportunity(
                    assistant,
                    situation,
                    previous_situation_digest=last_social_digest,
                    session_id=sid,
                    language=args.language,
                )
                last_social_sid = sid
                last_social_digest = situation.projection.digest
                print(
                    f"[feedback] target={target_activity} runtime={result} "
                    f"digest={last_social_digest[:12]}"
                )
                _print_history_delta(assistant, before)
                new_activity_id = _latest_delivered_activity_id(assistant, sid)
                if new_activity_id and new_activity_id != target_activity:
                    print(f"[feedback] delivered_activity_id={new_activity_id}")
                continue

            if raw.startswith("/"):
                print("unknown command; type /help")
                continue

            # Ordinary user text: maintained post-ASR text boundary.
            sid = assistant.create_session()
            before = _history_len(assistant)
            started = time.perf_counter()
            try:
                await assistant.handle_routed_text(raw, sid, channel="text")
                await _wait_for_session_done(assistant, sid, args.timeout_s)
            except Exception as exc:
                print(f"[text][error] {type(exc).__name__}: {exc}")
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            print(f"[text] completed in {elapsed_ms:.0f} ms sid={sid}")
            _print_history_delta(assistant, before)

    finally:
        await shutdown_voice_assistant(
            assistant,
            close_output_stream=playback_transport_for(assistant).close_output_stream,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--conversation-id", default=f"psm-live-text-{_utc_id()}")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="play TTS on the configured speaker; default keeps real TTS/delivery but discards audio",
    )
    parser.add_argument(
        "--capabilities",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="enable Soridormi/robot capabilities for ordinary text turns",
    )
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = _discover_repo_root(args.repo_root)
        if args.manifest is None:
            args.manifest = root / "capabilities" / "soridormi.json"
        asyncio.run(_run_console(root, args))
    except Exception as exc:
        print(f"[psm-console][error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
