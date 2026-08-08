"""Policy-snapshotted Data Loop evidence for one voice interaction Session.

Chromie owns the Session trigger semantics.  This module resolves one typed
collection policy at Session start, reuses evidence supplied by the existing
input/trace/episode owners, and seals one immutable runtime-event package at the
Session lifecycle boundary.  It does not evaluate the interaction or infer why
the evidence is useful.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.chromie_runtime.runtime_events import (
    RuntimeEventArtifact,
    persist_runtime_event,
)
from shared.chromie_runtime.runtime_trace import TraceSnapshot


logger = logging.getLogger("chromie.orchestrator.interaction_session_evidence")

POLICY_ID = "chromie.interaction_session_capture"
POLICY_SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InteractionSessionEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_input_audio: bool = True
    runtime_trace: bool = True
    episode: bool = True


class InteractionSessionGovernance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retention_profile_id: str
    usage_purpose: str

    @field_validator("retention_profile_id", "usage_purpose")
    @classmethod
    def require_token(cls, value: str) -> str:
        normalized = " ".join(str(value or "").strip().split())
        if not normalized:
            raise ValueError("governance values must not be empty")
        return normalized


class InteractionSessionCapturePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = POLICY_SCHEMA_VERSION
    policy_id: Literal["chromie.interaction_session_capture"] = POLICY_ID
    policy_version: str
    enabled: bool = False
    evidence: InteractionSessionEvidenceRequest = Field(
        default_factory=InteractionSessionEvidenceRequest
    )
    governance: InteractionSessionGovernance

    @field_validator("policy_version")
    @classmethod
    def require_version(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("policy_version must not be empty")
        return normalized

    @model_validator(mode="after")
    def require_evidence_when_enabled(self) -> "InteractionSessionCapturePolicy":
        if self.enabled and not any(
            (
                self.evidence.user_input_audio,
                self.evidence.runtime_trace,
                self.evidence.episode,
            )
        ):
            raise ValueError("enabled interaction-session policy requests no evidence")
        return self


class InteractionSessionCapturePolicySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = POLICY_SCHEMA_VERSION
    policy_id: Literal["chromie.interaction_session_capture"] = POLICY_ID
    policy_version: str
    enabled: bool
    evidence: InteractionSessionEvidenceRequest
    governance: InteractionSessionGovernance
    provider: str
    resolved_at: str
    policy_sha256: str
    source_reference: str | None = None
    resolution_error: str | None = None


class InteractionSessionCapturePolicyProvider(Protocol):
    """Replaceable local/cloud boundary consumed by Session lifecycle code."""

    def resolve(self) -> InteractionSessionCapturePolicySnapshot: ...


class LocalInteractionSessionCapturePolicyProvider:
    """Resolve a versioned policy file selected by the Host environment."""

    def __init__(self, policy_path: Path | None) -> None:
        self.policy_path = policy_path.resolve() if policy_path is not None else None
        self._last_valid: InteractionSessionCapturePolicySnapshot | None = None

    def resolve(self) -> InteractionSessionCapturePolicySnapshot:
        if self.policy_path is None:
            return self._disabled_snapshot()
        try:
            payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("policy document must be a JSON object")
            policy = InteractionSessionCapturePolicy.model_validate(payload)
            snapshot = InteractionSessionCapturePolicySnapshot(
                **policy.model_dump(mode="json"),
                provider="local_file",
                resolved_at=_now_iso(),
                policy_sha256=_canonical_digest(policy.model_dump(mode="json")),
                source_reference=str(self.policy_path),
            )
            self._last_valid = snapshot
            return snapshot
        except (OSError, UnicodeError, TypeError, ValueError):
            if self._last_valid is not None:
                logger.warning(
                    "Interaction-session policy refresh failed; retaining cached "
                    "policy id=%s version=%s",
                    self._last_valid.policy_id,
                    self._last_valid.policy_version,
                    exc_info=True,
                )
                return self._last_valid
            raise

    @staticmethod
    def _disabled_snapshot(
        *,
        error: str | None = None,
    ) -> InteractionSessionCapturePolicySnapshot:
        policy = InteractionSessionCapturePolicy(
            policy_version="local-disabled-v1",
            enabled=False,
            evidence=InteractionSessionEvidenceRequest(
                user_input_audio=False,
                runtime_trace=False,
                episode=False,
            ),
            governance=InteractionSessionGovernance(
                retention_profile_id="none",
                usage_purpose="disabled",
            ),
        )
        return InteractionSessionCapturePolicySnapshot(
            **policy.model_dump(mode="json"),
            provider="local_default",
            resolved_at=_now_iso(),
            policy_sha256=_canonical_digest(policy.model_dump(mode="json")),
            resolution_error=error,
        )


@dataclass
class _ActiveCapture:
    sid: str
    activation_id: str
    policy: InteractionSessionCapturePolicySnapshot
    started_at: str
    active_dir: Path | None
    runtime_identity: dict[str, Any] | None
    capture_errors: list[str] = field(default_factory=list)


class InteractionSessionEvidenceCollector:
    """Best-effort physical capture and immutable Session evidence sealing."""

    def __init__(
        self,
        *,
        policy_provider: InteractionSessionCapturePolicyProvider,
        event_root: Path | None,
        trigger_root: Path | None = None,
        runtime_identity: dict[str, Any] | None = None,
        event_persister: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.policy_provider = policy_provider
        self.event_root = event_root.resolve() if event_root is not None else None
        self.trigger_root = (
            trigger_root.resolve() if trigger_root is not None else None
        )
        self.runtime_identity = (
            json.loads(json.dumps(runtime_identity))
            if isinstance(runtime_identity, dict)
            else None
        )
        self.event_persister = event_persister or persist_runtime_event
        self.active_root = (
            self.event_root / ".interaction-session-capture" / "active"
            if self.event_root is not None
            else None
        )
        self._active: dict[str, _ActiveCapture] = {}
        self._sealed: dict[str, dict[str, Any]] = {}
        self._references: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.recovered_sessions = self._recover_abandoned_sessions()

    def begin_session(self, sid: str) -> InteractionSessionCapturePolicySnapshot:
        normalized_sid = self._token(sid, "sid")
        with self._lock:
            existing = self._active.get(normalized_sid)
            if existing is not None:
                return existing.policy
            try:
                policy = self.policy_provider.resolve()
            except Exception as exc:
                logger.error(
                    "Interaction-session policy resolution failed; capture is "
                    "disabled for sid=%s error_type=%s error=%s",
                    normalized_sid,
                    type(exc).__name__,
                    exc,
                )
                policy = LocalInteractionSessionCapturePolicyProvider._disabled_snapshot(
                    error=f"{type(exc).__name__}: {str(exc)[:500]}"
                )
            activation_id = self._activation_id(normalized_sid, policy)
            active_dir = None
            errors: list[str] = []
            if policy.enabled:
                if self.active_root is None:
                    errors.append("runtime_event_root_not_configured")
                else:
                    candidate_dir = self.active_root / activation_id
                    try:
                        candidate_dir.mkdir(parents=True, exist_ok=True)
                        active_dir = candidate_dir
                    except OSError as exc:
                        errors.append(
                            f"active_staging:{type(exc).__name__}:{str(exc)[:300]}"
                        )
                        logger.warning(
                            "Interaction-session evidence staging failed sid=%s "
                            "error_type=%s error=%s",
                            normalized_sid,
                            type(exc).__name__,
                            exc,
                        )
            capture = _ActiveCapture(
                sid=normalized_sid,
                activation_id=activation_id,
                policy=policy,
                started_at=_now_iso(),
                active_dir=active_dir,
                runtime_identity=self.runtime_identity,
                capture_errors=errors,
            )
            self._active[normalized_sid] = capture
            if policy.enabled:
                self._references[normalized_sid] = self._reference(capture)
            self._persist_active_state_safely(capture)
            return policy

    def session_reference(self, sid: str) -> dict[str, Any] | None:
        with self._lock:
            reference = self._references.get(str(sid or ""))
            return dict(reference) if reference is not None else None

    def capture_input_audio(
        self,
        sid: str,
        audio: bytes,
        *,
        sample_rate_hz: int,
        channels: int,
    ) -> dict[str, Any] | None:
        with self._lock:
            capture = self._active.get(str(sid or ""))
            if (
                capture is None
                or not capture.policy.enabled
                or not capture.policy.evidence.user_input_audio
                or capture.active_dir is None
                or not audio
            ):
                return None
            path = capture.active_dir / "input-audio.pcm16"
            metadata = {
                "sample_rate_hz": max(1, int(sample_rate_hz)),
                "channels": max(1, int(channels)),
                "sample_format": "pcm_s16le",
                "source": "validated_vad_input_buffer",
            }
            try:
                self._write_once(path, bytes(audio))
                self._write_json_once(
                    capture.active_dir / "input-audio-metadata.json",
                    metadata,
                )
            except (OSError, TypeError, ValueError) as exc:
                self._remember_error(capture, "audio", exc)
                return None
            self._persist_active_state_safely(capture)
            return {
                "path": str(path),
                "sha256": self._file_digest(path),
                **metadata,
            }

    def attach_episode_evidence(
        self,
        sid: str,
        episode: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock:
            capture = self._active.get(str(sid or ""))
            if (
                capture is None
                or not capture.policy.enabled
                or not capture.policy.evidence.episode
                or capture.active_dir is None
            ):
                return None
            path = capture.active_dir / "episode.json"
            try:
                self._write_or_replace_json(path, dict(episode))
            except (OSError, TypeError, ValueError) as exc:
                self._remember_error(capture, "episode", exc)
                return None
            self._persist_active_state_safely(capture)
            return {"path": str(path), "sha256": self._file_digest(path)}

    def seal_session(
        self,
        sid: str,
        *,
        termination_state: Literal["complete", "abandoned"],
        trace_snapshot: TraceSnapshot | None = None,
        recovered: bool = False,
    ) -> dict[str, Any]:
        normalized_sid = str(sid or "").strip()
        with self._lock:
            if normalized_sid in self._sealed:
                return dict(self._sealed[normalized_sid])
            capture = self._active.get(normalized_sid)
            if capture is None:
                return {
                    "event_id": "",
                    "capture_status": "not_requested",
                    "trigger_status": "not_attempted",
                }
            if not capture.policy.enabled:
                self._active.pop(normalized_sid, None)
                return {
                    "event_id": "",
                    "capture_status": "not_requested",
                    "trigger_status": "not_attempted",
                }
            if capture.active_dir is None or self.event_root is None:
                result = {
                    "event_id": self._event_id(capture),
                    "capture_status": "failed",
                    "trigger_status": "not_attempted",
                    "error": "runtime_event_root_not_configured",
                }
                self._sealed[normalized_sid] = result
                return dict(result)
            if trace_snapshot is not None and capture.policy.evidence.runtime_trace:
                try:
                    self._write_or_replace_json(
                        capture.active_dir / "runtime-trace.json",
                        trace_snapshot.trace,
                    )
                    self._write_or_replace_json(
                        capture.active_dir / "trace-summary.json",
                        trace_snapshot.summary,
                    )
                except (OSError, TypeError, ValueError) as exc:
                    self._remember_error(capture, "runtime_trace", exc)

            event_id = self._event_id(capture)
            try:
                evidence, artifacts = self._evidence_manifest(
                    capture,
                    active_dir=capture.active_dir,
                    termination_state=termination_state,
                    recovered=recovered,
                )
            except (OSError, TypeError, ValueError) as exc:
                result = {
                    "event_id": event_id,
                    "capture_status": "failed",
                    "trigger_status": "not_attempted",
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                }
                self._sealed[normalized_sid] = result
                return dict(result)
            try:
                result = self.event_persister(
                    event_type="chromie.interaction_session_evidence",
                    event_subtype=f"session_{termination_state}",
                    severity="warning" if termination_state == "abandoned" else "info",
                    producer="chromie.orchestrator.session",
                    payloads={"interaction-session-evidence.json": evidence},
                    artifacts=artifacts,
                    attributes={
                        "policy_id": capture.policy.policy_id,
                        "policy_version": capture.policy.policy_version,
                        "policy_activation_id": capture.activation_id,
                        "termination_state": termination_state,
                        "evidence_status": evidence["evidence_status"],
                        "retention_profile_id": (
                            capture.policy.governance.retention_profile_id
                        ),
                        "usage_purpose": capture.policy.governance.usage_purpose,
                    },
                    correlations=evidence["correlations"],
                    derivation={
                        "fact_layer": True,
                        "offline_evaluation_supported": True,
                        "scenario_candidate_eligible": True,
                        "scenario_auto_promotion_allowed": False,
                        "realtime_evaluation_performed": False,
                    },
                    event_root=self.event_root,
                    trigger_root=self.trigger_root,
                    event_id=event_id,
                )
            except Exception as exc:
                result = {
                    "event_id": event_id,
                    "capture_status": "failed",
                    "trigger_status": "not_attempted",
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                }
            if result.get("capture_status") == "complete":
                shutil.rmtree(capture.active_dir, ignore_errors=True)
                self._active.pop(normalized_sid, None)
            self._sealed[normalized_sid] = dict(result)
            return dict(result)

    def _evidence_manifest(
        self,
        capture: _ActiveCapture,
        *,
        active_dir: Path,
        termination_state: str,
        recovered: bool,
    ) -> tuple[dict[str, Any], dict[str, RuntimeEventArtifact]]:
        requested = capture.policy.evidence
        specifications = [
            (
                "user_input_audio",
                "input-audio.pcm16",
                "audio/L16",
                requested.user_input_audio,
            ),
            (
                "runtime_trace",
                "runtime-trace.json",
                "application/json",
                requested.runtime_trace,
            ),
            (
                "trace_summary",
                "trace-summary.json",
                "application/json",
                requested.runtime_trace,
            ),
            ("episode", "episode.json", "application/json", requested.episode),
        ]
        artifacts: dict[str, RuntimeEventArtifact] = {}
        artifact_records: list[dict[str, Any]] = []
        missing: list[str] = []
        for kind, name, content_type, required in specifications:
            if not required:
                continue
            path = active_dir / name
            if not path.is_file():
                missing.append(kind)
                continue
            digest = self._file_digest(path)
            record: dict[str, Any] = {
                "artifact_id": f"artifact_sha256_{digest}",
                "kind": kind,
                "path": name,
                "content_type": content_type,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "status": "complete",
                "physical_source": "existing_session_evidence_provider",
            }
            if kind == "user_input_audio":
                metadata_path = active_dir / "input-audio-metadata.json"
                if metadata_path.is_file():
                    record["audio"] = self._read_json(metadata_path)
            artifact_records.append(record)
            artifacts[name] = RuntimeEventArtifact(
                source=path,
                content_type=content_type,
            )

        trace_payload = self._read_json(active_dir / "runtime-trace.json")
        episode_payload = self._read_json(active_dir / "episode.json")
        trace_correlations = (
            dict(trace_payload.get("correlations") or {})
            if isinstance(trace_payload, dict)
            else {}
        )
        correlations = {
            "session_id": capture.sid,
            "conversation_id": str(
                trace_correlations.get("conversation_id")
                or (
                    episode_payload.get("conversation_id")
                    if isinstance(episode_payload, dict)
                    else ""
                )
                or ""
            ),
            "episode_id": str(
                trace_correlations.get("episode_id")
                or (
                    episode_payload.get("episode_id")
                    if isinstance(episode_payload, dict)
                    else ""
                )
                or ""
            ),
            "trace_id": str(
                trace_payload.get("trace_id")
                if isinstance(trace_payload, dict)
                else ""
            ),
            "policy_activation_id": capture.activation_id,
        }
        policy_payload = capture.policy.model_dump(mode="json", exclude_none=True)
        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "evidence_id": f"interaction_session_evidence_{capture.activation_id}",
            "event_id": self._event_id(capture),
            "session": {
                "sid": capture.sid,
                "started_at": capture.started_at,
                "ended_at": _now_iso(),
                "termination_state": termination_state,
                "recovered_after_restart": bool(recovered),
            },
            "policy_snapshot": policy_payload,
            "correlations": correlations,
            "provenance": {
                "source_sid": capture.sid,
                "runtime_identity": capture.runtime_identity,
                "policy_id": capture.policy.policy_id,
                "policy_version": capture.policy.policy_version,
                "policy_sha256": capture.policy.policy_sha256,
            },
            "artifacts": artifact_records,
            "evidence_status": (
                "partial" if missing or capture.capture_errors else "complete"
            ),
            "missing_evidence": sorted(set(missing)),
            "capture_errors": list(capture.capture_errors),
            "derived_artifacts": {
                "episode_is_semantic_projection": True,
                "evaluation_created_in_realtime": False,
                "scenario_candidate_created_in_realtime": False,
            },
        }
        return evidence, artifacts

    def _recover_abandoned_sessions(self) -> list[dict[str, Any]]:
        if self.active_root is None or not self.active_root.exists():
            return []
        recovered: list[dict[str, Any]] = []
        for state_path in sorted(self.active_root.glob("*/capture-state.json")):
            try:
                payload = self._read_json(state_path)
                if not isinstance(payload, dict):
                    raise ValueError("active capture state must be an object")
                policy = InteractionSessionCapturePolicySnapshot.model_validate(
                    payload["policy_snapshot"]
                )
                sid = self._token(payload.get("sid"), "sid")
                capture = _ActiveCapture(
                    sid=sid,
                    activation_id=self._token(
                        payload.get("policy_activation_id"),
                        "policy_activation_id",
                    ),
                    policy=policy,
                    started_at=str(payload.get("started_at") or _now_iso()),
                    active_dir=state_path.parent,
                    runtime_identity=(
                        dict(payload.get("runtime_identity"))
                        if isinstance(payload.get("runtime_identity"), dict)
                        else None
                    ),
                    capture_errors=[
                        str(item)
                        for item in payload.get("capture_errors") or []
                        if str(item).strip()
                    ],
                )
                self._active[sid] = capture
                self._references[sid] = self._reference(capture)
                event = self.seal_session(
                    sid,
                    termination_state="abandoned",
                    recovered=True,
                )
                recovered.append({"sid": sid, "event": event})
            except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Interaction-session evidence recovery failed path=%s "
                    "error_type=%s error=%s",
                    state_path,
                    type(exc).__name__,
                    exc,
                )
        return recovered

    def _persist_active_state(self, capture: _ActiveCapture) -> None:
        if capture.active_dir is None:
            return
        self._write_or_replace_json(
            capture.active_dir / "capture-state.json",
            {
                "schema_version": 1,
                "sid": capture.sid,
                "policy_activation_id": capture.activation_id,
                "policy_snapshot": capture.policy.model_dump(
                    mode="json", exclude_none=True
                ),
                "started_at": capture.started_at,
                "runtime_identity": capture.runtime_identity,
                "capture_errors": list(capture.capture_errors),
            },
        )

    def _persist_active_state_safely(self, capture: _ActiveCapture) -> None:
        try:
            self._persist_active_state(capture)
        except (OSError, TypeError, ValueError) as exc:
            self._remember_error(capture, "capture_state", exc)

    @staticmethod
    def _activation_id(
        sid: str,
        policy: InteractionSessionCapturePolicySnapshot,
    ) -> str:
        seed = f"{sid}|{policy.policy_id}|{policy.policy_version}|{policy.policy_sha256}"
        return "policyact_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _event_id(capture: _ActiveCapture) -> str:
        return "evt_interaction_session_" + hashlib.sha256(
            capture.activation_id.encode("utf-8")
        ).hexdigest()[:24]

    @classmethod
    def _reference(cls, capture: _ActiveCapture) -> dict[str, Any]:
        return {
            "source_sid": capture.sid,
            "policy_activation_id": capture.activation_id,
            "evidence_event_id": cls._event_id(capture),
            "policy_id": capture.policy.policy_id,
            "policy_version": capture.policy.policy_version,
            "policy_sha256": capture.policy.policy_sha256,
        }

    @staticmethod
    def _token(value: Any, name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{name} must not be empty")
        return normalized

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return dict(payload) if isinstance(payload, dict) else None

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f"immutable artifact already exists with other bytes: {path}")
            return
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @classmethod
    def _write_json_once(cls, path: Path, payload: Mapping[str, Any]) -> None:
        content = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        cls._write_once(path, content)

    @classmethod
    def _write_or_replace_json(cls, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _remember_error(
        capture: _ActiveCapture,
        kind: str,
        exc: Exception,
    ) -> None:
        error = f"{kind}:{type(exc).__name__}:{str(exc)[:300]}"
        if error not in capture.capture_errors:
            capture.capture_errors.append(error)
        logger.warning(
            "Interaction-session evidence capture failed sid=%s kind=%s "
            "error_type=%s error=%s",
            capture.sid,
            kind,
            type(exc).__name__,
            exc,
        )


__all__ = [
    "InteractionSessionCapturePolicy",
    "InteractionSessionCapturePolicyProvider",
    "InteractionSessionCapturePolicySnapshot",
    "InteractionSessionEvidenceCollector",
    "LocalInteractionSessionCapturePolicyProvider",
]
