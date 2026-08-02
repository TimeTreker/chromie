#!/usr/bin/env python3
"""Fail-fast preflight for source-bound Cognitive Gateway/Core qualification.

The preflight validates deployment identity and readiness only. It does not send
qualification utterances, infer user intent, execute motion, approve human
review, or grant release qualification.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.clients.tts_client import TTSClient  # noqa: E402

DEFAULT_CAPABILITY_MANIFEST = ROOT / "capabilities" / "soridormi.json"
DEFAULT_OUTPUT = (
    ROOT
    / ".chromie"
    / "acceptance"
    / "cognitive-gateway-core"
    / "preflight.json"
)


class PreflightError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"failed to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{path}: expected a JSON object")
    return value


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise PreflightError(
            f"git {' '.join(args)} failed in {root}: {detail}"
        )
    return completed.stdout.strip()


def _git_identity(root: Path) -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise PreflightError(f"repository does not exist: {resolved}")
    revision = _run_git(resolved, "rev-parse", "HEAD")
    branch = _run_git(resolved, "branch", "--show-current")
    status = _run_git(resolved, "status", "--porcelain")
    return {
        "root": str(resolved),
        "revision": revision,
        "branch": branch,
        "dirty": bool(status),
        "status_porcelain": status.splitlines(),
    }


def _manifest_upstream_revision(path: Path) -> str | None:
    payload = _read_json(path)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = str(metadata.get("upstream_commit") or "").strip()
    return value or None


def _endpoint_source_revision(status: dict[str, Any]) -> str | None:
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


def _safe_idle_errors(status: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if status.get("safe_idle") is not True:
        errors.append("Soridormi endpoint does not report safe_idle=true")
    if "active_task" not in status or status.get("active_task") is not None:
        errors.append("Soridormi endpoint has an active task")
    if status.get("emergency_stop") is not False:
        errors.append("Soridormi endpoint has emergency_stop active or unknown")
    if status.get("fallen") is not False:
        errors.append("Soridormi endpoint reports fallen or unknown state")
    return errors


def _evaluate_preflight(
    *,
    chromie: dict[str, Any],
    soridormi: dict[str, Any],
    manifest_revision: str | None,
    agent_health: dict[str, Any],
    provider_status: dict[str, Any],
    tts_readiness: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            errors.append(detail)

    check(
        "chromie_clean",
        chromie.get("dirty") is False,
        "Chromie worktree must be clean before qualification",
    )
    check(
        "soridormi_clean",
        soridormi.get("dirty") is False,
        "Soridormi worktree must be clean before qualification",
    )

    soridormi_revision = str(soridormi.get("revision") or "").strip()
    check(
        "manifest_matches_soridormi",
        bool(manifest_revision) and manifest_revision == soridormi_revision,
        (
            "Chromie capability manifest upstream revision must match the paired "
            f"Soridormi checkout: manifest={manifest_revision!r} "
            f"checkout={soridormi_revision!r}"
        ),
    )

    check(
        "agent_healthy",
        agent_health.get("ok") is True,
        "Chromie Agent /health did not report ok=true",
    )
    capability_sources = set(agent_health.get("capability_sources") or [])
    check(
        "agent_loaded_soridormi",
        "soridormi" in capability_sources,
        "Chromie Agent did not load the Soridormi capability manifest",
    )

    check(
        "tts_synthesis_ready",
        tts_readiness.get("ready") is True
        and int(tts_readiness.get("pcm_bytes") or 0) > 0,
        "TTS synthesis readiness failed: "
        + str(tts_readiness.get("error") or "no completed PCM synthesis"),
    )

    check(
        "provider_sim_mode",
        provider_status.get("mode") == "sim",
        f"Soridormi endpoint must run in sim mode, got {provider_status.get('mode')!r}",
    )
    safe_idle_errors = _safe_idle_errors(provider_status)
    if safe_idle_errors:
        for index, safe_idle_error in enumerate(safe_idle_errors, start=1):
            check(
                f"provider_safe_idle_{index}",
                False,
                safe_idle_error,
            )
    else:
        check(
            "provider_safe_idle",
            True,
            "Soridormi endpoint is safe idle",
        )

    endpoint_revision = _endpoint_source_revision(provider_status)
    check(
        "provider_reports_revision",
        bool(endpoint_revision),
        "Soridormi robot.get_status must report source_revision or provider_revision",
    )
    if endpoint_revision:
        check(
            "provider_revision_matches_checkout",
            endpoint_revision == soridormi_revision,
            (
                "running Soridormi endpoint revision must match the paired checkout: "
                f"endpoint={endpoint_revision!r} checkout={soridormi_revision!r}"
            ),
        )
        check(
            "provider_revision_matches_manifest",
            bool(manifest_revision) and endpoint_revision == manifest_revision,
            (
                "running Soridormi endpoint revision must match the Chromie "
                f"capability manifest: endpoint={endpoint_revision!r} "
                f"manifest={manifest_revision!r}"
            ),
        )
    return checks, errors


async def _agent_health(agent_url: str, timeout_s: float) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{agent_url.rstrip('/')}/health") as response:
            body = await response.text()
            if response.status != 200:
                raise PreflightError(
                    f"Chromie Agent health returned HTTP {response.status}: {body[:500]}"
                )
            try:
                value = json.loads(body)
            except json.JSONDecodeError as exc:
                raise PreflightError("Chromie Agent health was not valid JSON") from exc
            if not isinstance(value, dict):
                raise PreflightError("Chromie Agent health was not an object")
            return value


async def _synthesize_tts_readiness(
    *,
    tts_url: str,
    speaker_id: str,
    timeout_s: float,
    text: str = "Hello.",
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        pcm, sample_rate = await asyncio.wait_for(
            TTSClient(tts_url).synthesize(
                text=text,
                speaker_id=speaker_id,
                request_id=f"gateway-core-preflight-{uuid.uuid4().hex}",
            ),
            timeout=max(1.0, timeout_s),
        )
    except Exception as exc:
        raise PreflightError(
            f"TTS synthesis probe failed within {timeout_s:.1f}s: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not pcm:
        raise PreflightError("TTS synthesis probe completed without PCM audio")
    if int(sample_rate) <= 0:
        raise PreflightError(
            f"TTS synthesis probe returned invalid sample rate {sample_rate!r}"
        )
    return {
        "ready": True,
        "url": tts_url,
        "speaker_id": speaker_id,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "pcm_bytes": len(pcm),
        "sample_rate": int(sample_rate),
        "timeout_s": float(timeout_s),
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 1),
    }


async def _provider_status(
    *,
    manifest: Path,
    mcp_url: str,
) -> dict[str, Any]:
    os.environ["SORIDORMI_MCP_URL"] = mcp_url
    from orchestrator.runtime.interaction_coordinator import (  # noqa: PLC0415
        build_soridormi_invoker,
    )

    invoker = build_soridormi_invoker(manifest_path=manifest)
    outcome = await invoker.invoke("soridormi.robot.get_status", {})
    if outcome.status != "success":
        raise PreflightError(
            outcome.error or f"Soridormi status returned {outcome.status}"
        )
    if not isinstance(outcome.output, dict):
        raise PreflightError("Soridormi robot.get_status did not return an object")
    return outcome.output


async def run_preflight(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    capability_manifest = args.capability_manifest.expanduser().resolve()
    chromie = _git_identity(args.root.expanduser().resolve())
    soridormi = _git_identity(args.soridormi_repo.expanduser().resolve())
    manifest_revision = _manifest_upstream_revision(capability_manifest)
    agent_health = await _agent_health(args.agent_url, args.timeout_s)
    try:
        tts_readiness = await _synthesize_tts_readiness(
            tts_url=args.tts_url,
            speaker_id=args.tts_speaker_id,
            timeout_s=args.tts_readiness_timeout_s,
            text=args.tts_probe_text,
        )
    except Exception as exc:
        tts_readiness = {
            "ready": False,
            "url": args.tts_url,
            "speaker_id": args.tts_speaker_id,
            "timeout_s": args.tts_readiness_timeout_s,
            "error": f"{type(exc).__name__}: {exc}",
        }
    provider_status = await _provider_status(
        manifest=capability_manifest,
        mcp_url=args.soridormi_mcp_url,
    )
    checks, errors = _evaluate_preflight(
        chromie=chromie,
        soridormi=soridormi,
        manifest_revision=manifest_revision,
        agent_health=agent_health,
        provider_status=provider_status,
        tts_readiness=tts_readiness,
    )
    payload = {
        "schema_version": 1,
        "captured_at": _utc_now(),
        "ready": not errors,
        "checks": checks,
        "errors": errors,
        "chromie": chromie,
        "soridormi": soridormi,
        "capability_manifest": {
            "path": str(capability_manifest),
            "upstream_revision": manifest_revision,
        },
        "agent": {
            "url": args.agent_url,
            "health": agent_health,
        },
        "tts": tts_readiness,
        "provider": {
            "url": args.soridormi_mcp_url,
            "status": provider_status,
            "source_revision": _endpoint_source_revision(provider_status),
        },
        "qualification": {
            "issue_closure_eligible": False,
            "release_qualified": False,
            "human_review_required": True,
        },
    }
    return payload, 0 if payload["ready"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--soridormi-repo", type=Path, default=ROOT.parent / "soridormi")
    parser.add_argument(
        "--capability-manifest",
        type=Path,
        default=DEFAULT_CAPABILITY_MANIFEST,
    )
    parser.add_argument(
        "--agent-url",
        default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"),
    )
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument(
        "--tts-url",
        default=os.getenv("TTS_URL", "ws://127.0.0.1:5000"),
    )
    parser.add_argument(
        "--tts-speaker-id",
        default=os.getenv("TTS_SPEAKER_ID", "default"),
    )
    parser.add_argument(
        "--tts-readiness-timeout-s",
        type=float,
        default=float(os.getenv("TTS_COSYVOICE_WARMUP_TIMEOUT_SEC", "300")),
    )
    parser.add_argument(
        "--tts-probe-text",
        default=os.getenv("TTS_COSYVOICE_EN_WARMUP_TEXT", "Hello."),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    output = args.output.expanduser().resolve()
    try:
        payload, exit_code = asyncio.run(run_preflight(args))
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "captured_at": _utc_now(),
            "ready": False,
            "checks": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
            "qualification": {
                "issue_closure_eligible": False,
                "release_qualified": False,
                "human_review_required": True,
            },
        }
        exit_code = 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if payload.get("ready") is True:
        print(f"[gateway-core-preflight] ready: {output}")
    else:
        print(f"[gateway-core-preflight][error] not ready: {output}", file=sys.stderr)
        for error in payload.get("errors") or []:
            print(f"  - {error}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
