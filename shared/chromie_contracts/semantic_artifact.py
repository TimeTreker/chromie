"""Immutable transport/archival envelopes for already-owned semantic artifacts.

The envelope is mechanical integrity and lineage metadata around an artifact whose
semantic authority already belongs to Gateway, GI, GA, Planner, SC, or Runtime.
It never creates, repairs, summarizes, or reinterprets the payload.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SemanticArtifactKind = Literal[
    "user_turn",
    "goal_interpretation",
    "responsibility",
    "goal_association",
    "goal",
    "planner_plan",
    "social_cognition",
    "communicative_act",
    "execution_outcome",
]


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def semantic_artifact_payload_sha256(payload: dict[str, Any]) -> str:
    """Hash one exact canonical JSON payload without semantic normalization."""

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class SemanticArtifactRef(BaseModel):
    """Content-bound reference to one immutable accepted artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    artifact_kind: SemanticArtifactKind
    artifact_id: str = Field(min_length=1, max_length=240)
    payload_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("artifact_id", mode="before")
    @classmethod
    def normalize_artifact_id(cls, value: Any) -> str:
        return _normalized_text(value)

    @field_validator("payload_sha256")
    @classmethod
    def validate_payload_sha256(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("payload_sha256 must be a lowercase SHA-256 hex digest")
        return normalized


class SemanticArtifactLineage(BaseModel):
    """Typed transport set of immutable upstream semantic artifact references.

    The lineage carries content-bound identity only. It does not duplicate payloads,
    grant semantic authority, or become model-facing context. Existing owners still
    transport the payloads they need through their normal typed contracts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    refs: tuple[SemanticArtifactRef, ...] = Field(default_factory=tuple, max_length=128)

    @model_validator(mode="after")
    def validate_unique_refs(self) -> "SemanticArtifactLineage":
        identities = [
            (item.artifact_kind, item.artifact_id, item.payload_sha256)
            for item in self.refs
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("semantic artifact lineage refs must be unique")
        by_identity: dict[tuple[str, str], str] = {}
        for item in self.refs:
            key = (item.artifact_kind, item.artifact_id)
            previous = by_identity.setdefault(key, item.payload_sha256)
            if previous != item.payload_sha256:
                raise ValueError("semantic artifact lineage contains conflicting digests")
        return self

    def by_kind(self, artifact_kind: SemanticArtifactKind) -> tuple[SemanticArtifactRef, ...]:
        return tuple(item for item in self.refs if item.artifact_kind == artifact_kind)

    def require(self, expected: SemanticArtifactRef) -> None:
        for item in self.refs:
            if item.artifact_kind == expected.artifact_kind and item.artifact_id == expected.artifact_id:
                if item.payload_sha256 != expected.payload_sha256:
                    raise ValueError(
                        f"semantic artifact lineage digest mismatch for {expected.artifact_kind}:{expected.artifact_id}"
                    )
                return
        raise ValueError(
            f"semantic artifact lineage missing {expected.artifact_kind}:{expected.artifact_id}"
        )


def semantic_artifact_ref(
    payload: BaseModel | dict[str, Any],
    *,
    artifact_kind: SemanticArtifactKind,
    artifact_id: str,
) -> SemanticArtifactRef:
    """Create one content-bound ref without creating another semantic payload."""

    if isinstance(payload, BaseModel):
        canonical = payload.model_dump(mode="json", exclude_none=True)
    elif isinstance(payload, dict):
        canonical = deepcopy(payload)
    else:  # pragma: no cover - defensive public-contract guard
        raise TypeError("semantic artifact payload must be a BaseModel or object")
    return SemanticArtifactRef(
        artifact_kind=artifact_kind,
        artifact_id=artifact_id,
        payload_sha256=semantic_artifact_payload_sha256(canonical),
    )


def merge_semantic_artifact_lineage(
    *parts: SemanticArtifactLineage | SemanticArtifactRef | Iterable[SemanticArtifactRef] | None,
) -> SemanticArtifactLineage:
    """Merge exact refs while rejecting same-identity/different-content transport."""

    refs: list[SemanticArtifactRef] = []
    identities: dict[tuple[str, str], str] = {}
    for part in parts:
        if part is None:
            continue
        if isinstance(part, SemanticArtifactLineage):
            items = part.refs
        elif isinstance(part, SemanticArtifactRef):
            items = (part,)
        else:
            items = tuple(part)
        for raw in items:
            item = SemanticArtifactRef.model_validate(raw)
            key = (item.artifact_kind, item.artifact_id)
            previous = identities.get(key)
            if previous is not None:
                if previous != item.payload_sha256:
                    raise ValueError(
                        f"semantic artifact lineage conflict for {item.artifact_kind}:{item.artifact_id}"
                    )
                continue
            identities[key] = item.payload_sha256
            refs.append(item)
    return SemanticArtifactLineage(refs=tuple(refs))


class SemanticArtifactEnvelope(BaseModel):
    """Mechanical identity/lineage wrapper around one semantic artifact payload.

    ``authority`` names an already-existing semantic owner. ``parent_refs`` names
    immutable upstream artifacts; it does not grant their authority to this one.
    The payload itself is carried exactly once by :class:`SemanticArtifactPacket`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    ref: SemanticArtifactRef
    authority: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(default="", max_length=200)
    conversation_id: str = Field(default="", max_length=200)
    parent_refs: tuple[SemanticArtifactRef, ...] = Field(default_factory=tuple, max_length=64)

    @field_validator("authority", "session_id", "turn_id", "conversation_id", mode="before")
    @classmethod
    def normalize_identity_text(cls, value: Any) -> str:
        return _normalized_text(value)

    @model_validator(mode="after")
    def validate_lineage(self) -> "SemanticArtifactEnvelope":
        identities = [
            (item.artifact_kind, item.artifact_id, item.payload_sha256)
            for item in self.parent_refs
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("semantic artifact parent_refs must be unique")
        own = (self.ref.artifact_kind, self.ref.artifact_id, self.ref.payload_sha256)
        if own in identities:
            raise ValueError("semantic artifact cannot cite itself as a parent")
        return self


class SemanticArtifactPacket(BaseModel):
    """One immutable envelope plus the exact canonical payload it protects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    envelope: SemanticArtifactEnvelope
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload_integrity(self) -> "SemanticArtifactPacket":
        digest = semantic_artifact_payload_sha256(self.payload)
        if digest != self.envelope.ref.payload_sha256:
            raise ValueError("semantic artifact payload does not match envelope digest")
        return self

    @property
    def ref(self) -> SemanticArtifactRef:
        return self.envelope.ref


def semantic_artifact_packet(
    payload: BaseModel | dict[str, Any],
    *,
    artifact_kind: SemanticArtifactKind,
    artifact_id: str,
    authority: str,
    session_id: str,
    turn_id: str = "",
    conversation_id: str = "",
    parent_refs: Iterable[SemanticArtifactRef] = (),
) -> SemanticArtifactPacket:
    """Build an immutable packet without letting the transport author semantics."""

    if isinstance(payload, BaseModel):
        canonical = payload.model_dump(mode="json", exclude_none=True)
    elif isinstance(payload, dict):
        canonical = deepcopy(payload)
    else:  # pragma: no cover - defensive public-contract guard
        raise TypeError("semantic artifact payload must be a BaseModel or object")
    digest = semantic_artifact_payload_sha256(canonical)
    ref = SemanticArtifactRef(
        artifact_kind=artifact_kind,
        artifact_id=artifact_id,
        payload_sha256=digest,
    )
    unique_parents: list[SemanticArtifactRef] = []
    seen: set[tuple[str, str, str]] = set()
    for item in parent_refs:
        validated = SemanticArtifactRef.model_validate(item)
        key = (
            validated.artifact_kind,
            validated.artifact_id,
            validated.payload_sha256,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_parents.append(validated)
    return SemanticArtifactPacket(
        envelope=SemanticArtifactEnvelope(
            ref=ref,
            authority=authority,
            session_id=session_id,
            turn_id=turn_id,
            conversation_id=conversation_id,
            parent_refs=tuple(unique_parents),
        ),
        payload=canonical,
    )


__all__ = [
    "SemanticArtifactEnvelope",
    "SemanticArtifactLineage",
    "SemanticArtifactKind",
    "SemanticArtifactPacket",
    "SemanticArtifactRef",
    "semantic_artifact_packet",
    "semantic_artifact_ref",
    "merge_semantic_artifact_lineage",
    "semantic_artifact_payload_sha256",
]
