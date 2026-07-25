from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .profiles import EvidenceProfile, EvidenceProfileError


COMPLETE_EVIDENCE_STATUSES = frozenset({"observed", "succeeded", "complete"})
VALID_EVIDENCE_STATUSES = COMPLETE_EVIDENCE_STATUSES | frozenset(
    {"partial", "failed", "unavailable"}
)


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    source: str
    correlation_id: str
    status: str
    detail: str | None = None
    artifact: str | None = None
    timestamp_ms: float | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceItem":
        kind = value.get("kind")
        source = value.get("source")
        correlation_id = value.get("correlation_id")
        status = value.get("status")
        if not all(isinstance(item, str) and item.strip() for item in (kind, source, correlation_id)):
            raise EvidenceProfileError(
                "E2E evidence requires non-empty kind, source, and correlation_id"
            )
        if status not in VALID_EVIDENCE_STATUSES:
            raise EvidenceProfileError(f"invalid E2E evidence status: {status!r}")
        detail = value.get("detail")
        artifact = value.get("artifact")
        timestamp = value.get("timestamp_ms")
        if detail is not None and not isinstance(detail, str):
            raise EvidenceProfileError("E2E evidence detail must be a string or null")
        if artifact is not None and not isinstance(artifact, str):
            raise EvidenceProfileError("E2E evidence artifact must be a string or null")
        if timestamp is not None and (
            not isinstance(timestamp, (int, float)) or timestamp < 0
        ):
            raise EvidenceProfileError("E2E evidence timestamp_ms must be non-negative")
        return cls(
            kind=kind,
            source=source,
            correlation_id=correlation_id,
            status=status,
            detail=detail,
            artifact=artifact,
            timestamp_ms=float(timestamp) if timestamp is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "detail": self.detail,
            "artifact": self.artifact,
            "timestamp_ms": self.timestamp_ms,
        }


def parse_evidence(values: Iterable[Any]) -> tuple[EvidenceItem, ...]:
    result: list[EvidenceItem] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise EvidenceProfileError("E2E evidence entries must be objects")
        result.append(EvidenceItem.from_mapping(value))
    return tuple(result)


def load_partial_evidence(path: Path) -> tuple[EvidenceItem, ...]:
    if not path.exists():
        return ()
    result: list[EvidenceItem] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvidenceProfileError(f"cannot read partial E2E evidence {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceProfileError(
                f"invalid partial E2E evidence at {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            raise EvidenceProfileError(
                f"partial E2E evidence at {path}:{line_number} must be an object"
            )
        result.append(EvidenceItem.from_mapping(value))
    return tuple(result)


def merge_evidence(*groups: Iterable[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    merged: list[EvidenceItem] = []
    seen: set[tuple[Any, ...]] = set()
    for group in groups:
        for item in group:
            key = (
                item.kind,
                item.source,
                item.correlation_id,
                item.status,
                item.detail,
                item.artifact,
                item.timestamp_ms,
            )
            if key not in seen:
                seen.add(key)
                merged.append(item)
    return tuple(merged)


def validate_evidence(
    profile: EvidenceProfile,
    evidence: Iterable[EvidenceItem],
    *,
    correlation_id: str,
) -> dict[str, Any]:
    items = tuple(evidence)
    correlation_mismatches = sorted(
        {
            item.correlation_id
            for item in items
            if item.correlation_id != correlation_id
        }
    )
    completed_kinds = {
        item.kind for item in items if item.status in COMPLETE_EVIDENCE_STATUSES
    }
    failed_kinds = sorted(
        {item.kind for item in items if item.status in {"failed", "unavailable"}}
    )
    missing = sorted(set(profile.required_evidence) - completed_kinds)
    return {
        "complete": not missing and not failed_kinds and not correlation_mismatches,
        "required": list(profile.required_evidence),
        "observed_complete": sorted(completed_kinds),
        "missing": missing,
        "failed_or_unavailable": failed_kinds,
        "correlation_mismatches": correlation_mismatches,
    }


def validate_claims(profile: EvidenceProfile, claims: Iterable[str]) -> dict[str, Any]:
    claim_list = tuple(claims)
    if not all(isinstance(item, str) and item for item in claim_list):
        raise EvidenceProfileError("execution_claims must contain non-empty strings")
    forbidden = sorted(set(claim_list) - set(profile.allowed_execution_claims))
    return {
        "valid": not forbidden,
        "observed": list(claim_list),
        "allowed": list(profile.allowed_execution_claims),
        "forbidden": forbidden,
    }


def _numeric_timing(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or value < 0:
        raise EvidenceProfileError(f"timing marker {name!r} must be non-negative")
    return float(value)


def has_auxiliary_behavior(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "none", "no_auxiliary"}
    if isinstance(value, Mapping):
        decision = value.get("decision") or value.get("behavior") or value.get("name")
        if isinstance(decision, str):
            return decision.strip().casefold() not in {"", "none", "no_auxiliary"}
        return bool(value)
    return bool(value)


def validate_timing(
    profile: EvidenceProfile,
    timing: Mapping[str, Any],
    *,
    auxiliary_behavior: Any,
) -> dict[str, Any]:
    normalized = {name: _numeric_timing(value, name) for name, value in timing.items()}
    required = set(profile.required_timing_markers)
    if has_auxiliary_behavior(auxiliary_behavior):
        required.add("auxiliary_started_ms")
    missing = sorted(required - set(normalized))
    ordering_errors: list[str] = []
    input_marker = normalized.get("input_received_ms", normalized.get("audio_submitted_ms"))
    terminal = normalized.get("terminal_ms")
    if input_marker is not None and terminal is not None and terminal < input_marker:
        ordering_errors.append("terminal_ms precedes input")

    derived: dict[str, float] = {}
    if input_marker is not None:
        for marker, output_name in (
            ("primary_response_started_ms", "input_to_primary_response_ms"),
            ("primary_execution_started_ms", "input_to_primary_execution_ms"),
            ("auxiliary_started_ms", "input_to_auxiliary_ms"),
        ):
            if marker in normalized:
                derived[output_name] = normalized[marker] - input_marker
    if "auxiliary_started_ms" in normalized and "primary_response_started_ms" in normalized:
        derived["auxiliary_offset_from_primary_response_ms"] = (
            normalized["auxiliary_started_ms"] - normalized["primary_response_started_ms"]
        )
    if "auxiliary_started_ms" in normalized and "primary_execution_started_ms" in normalized:
        derived["auxiliary_offset_from_primary_execution_ms"] = (
            normalized["auxiliary_started_ms"] - normalized["primary_execution_started_ms"]
        )
    return {
        "complete": not missing and not ordering_errors,
        "required": sorted(required),
        "observed": normalized,
        "missing": missing,
        "ordering_errors": ordering_errors,
        "derived": derived,
    }
