from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InteractionStatus = Literal["ok", "clarify", "refused", "ignored", "error"]
CapabilityTiming = Literal["parallel", "sequential"]
SpeechTiming = Literal["immediate", "parallel", "sequential", "after_capabilities"]
CapabilityResultStatus = Literal[
    "accepted",
    "running",
    "completed",
    "refused",
    "failed",
    "cancelled",
    "timed_out",
]

VOCAL_PERFORMANCE_CAPABILITY_ID = "chromie.vocal.perform"
VOCAL_MODES = (
    "speech",
    "expressive_speech",
    "recitation",
    "singing",
    "humming",
    "nonverbal_vocalization",
)
VocalMode = Literal[
    "speech",
    "expressive_speech",
    "recitation",
    "singing",
    "humming",
    "nonverbal_vocalization",
]
VocalEvidenceLevel = Literal[
    "source_test",
    "automated_target",
    "supervised_target",
]

MEDIA_CAPABILITY_IDS = {
    "play": "chromie.media.play",
    "pause": "chromie.media.pause",
    "resume": "chromie.media.resume",
    "seek": "chromie.media.seek",
    "stop": "chromie.media.stop",
    "volume": "chromie.media.volume",
    "status": "chromie.media.status",
}
MEDIA_OPERATIONS = tuple(MEDIA_CAPABILITY_IDS)
MediaOperation = Literal[
    "play",
    "pause",
    "resume",
    "seek",
    "stop",
    "volume",
    "status",
]
MediaPlaybackState = Literal[
    "starting",
    "playing",
    "paused",
    "completed",
    "stopped",
    "failed",
]
MediaMixerPolicy = Literal["duck_media_during_vocal"]


def _immutable_provider_revision(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(
        re.fullmatch(r"[0-9a-f]{7,64}", normalized)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", normalized)
        or re.fullmatch(
            r"v?\d+\.\d+\.\d+(?:[-+][a-z0-9.-]+)?",
            normalized,
        )
    )


class VocalProviderArtifact(BaseModel):
    """One immutable model or runtime artifact used by a vocal provider."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    license_id: str = Field(min_length=1)

    @field_validator("kind", "artifact_id", "revision", "license_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("vocal provider artifact fields must not be empty")
        return normalized

    @field_validator("revision")
    @classmethod
    def require_immutable_revision(cls, value: str) -> str:
        if not _immutable_provider_revision(value):
            raise ValueError(
                "vocal provider artifact revision must be an immutable commit, "
                "sha256 digest, or semantic version"
            )
        return value


class VocalProviderProvenance(BaseModel):
    """Auditable implementation and model identity behind one provider."""

    model_config = ConfigDict(extra="forbid")

    implementation: str = Field(min_length=1)
    software_source: str = Field(min_length=1)
    software_revision: str = Field(min_length=1)
    software_license_id: str = Field(min_length=1)
    license_review_status: str = Field(min_length=1)
    model_artifacts: list[VocalProviderArtifact] = Field(min_length=1)

    @field_validator(
        "implementation",
        "software_source",
        "software_revision",
        "software_license_id",
        "license_review_status",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("vocal provider provenance fields must not be empty")
        return normalized

    @field_validator("software_revision")
    @classmethod
    def require_immutable_revision(cls, value: str) -> str:
        if not _immutable_provider_revision(value):
            raise ValueError(
                "vocal provider software_revision must be an immutable commit, "
                "sha256 digest, or semantic version"
            )
        return value


class VocalModeEvidence(BaseModel):
    """Retained qualification evidence for one advertised vocal mode."""

    model_config = ConfigDict(extra="forbid")

    level: VocalEvidenceLevel
    artifact_refs: list[str] = Field(min_length=1)
    claim_summary: str = Field(min_length=1)

    @field_validator("artifact_refs", mode="before")
    @classmethod
    def normalize_artifact_refs(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            raise ValueError("artifact_refs must be a list")
        result: list[str] = []
        for item in values:
            normalized = " ".join(str(item or "").strip().split())
            if normalized and normalized not in result:
                result.append(normalized)
        if not result:
            raise ValueError("artifact_refs must contain retained evidence")
        return result

    @field_validator("claim_summary")
    @classmethod
    def normalize_claim_summary(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("claim_summary must not be empty")
        return normalized


class VocalProviderDeclaration(BaseModel):
    """Qualified behavior, resource, and evidence declaration for one backend.

    The backend identity is trusted runtime metadata. Planner-to-execution
    identity remains :data:`VOCAL_PERFORMANCE_CAPABILITY_ID`.
    """

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    supported_modes: list[VocalMode] = Field(min_length=1)
    native_text_streaming: bool
    native_audio_streaming: bool
    request_cancellation: bool
    timing_mark_types: list[str] = Field(default_factory=list)
    sample_formats: list[str] = Field(min_length=1)
    sample_rates: list[int] = Field(min_length=1)
    max_concurrency: int = Field(ge=1)
    provenance: VocalProviderProvenance
    mode_evidence: dict[VocalMode, VocalModeEvidence]
    contract_version: int = Field(default=1, ge=1)

    @field_validator("provider_id")
    @classmethod
    def normalize_provider_id(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("provider_id must not be empty")
        return normalized

    @field_validator("supported_modes", mode="before")
    @classmethod
    def normalize_supported_modes(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            raise ValueError("supported_modes must be a list")
        result: list[str] = []
        for item in values:
            normalized = str(item or "").strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @field_validator("timing_mark_types", "sample_formats", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            raise ValueError("provider declaration field must be a list")
        result: list[str] = []
        for item in values:
            normalized = " ".join(str(item or "").strip().split())
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @field_validator("sample_rates")
    @classmethod
    def validate_sample_rates(cls, value: list[int]) -> list[int]:
        if any(rate < 8000 for rate in value):
            raise ValueError("sample_rates must contain valid PCM rates")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def require_mode_evidence(self) -> "VocalProviderDeclaration":
        supported = set(self.supported_modes)
        declared = set(self.mode_evidence)
        if supported != declared:
            missing = sorted(supported - declared)
            extra = sorted(declared - supported)
            raise ValueError(
                "mode_evidence must match supported_modes exactly: "
                f"missing={missing}, extra={extra}"
            )
        if not self.sample_formats:
            raise ValueError("sample_formats must not be empty")
        if not self.sample_rates:
            raise ValueError("sample_rates must not be empty")
        return self


class VocalPerformanceDelivery(BaseModel):
    """Host-retained audible-delivery evidence returned by a vocal backend."""

    model_config = ConfigDict(extra="forbid")

    delivered_mode: VocalMode
    delivery_evidence_id: str = Field(min_length=1)
    playback_started: bool
    playback_completed: bool
    audio_duration_ms: float = Field(gt=0)
    sample_format: str = Field(min_length=1)
    sample_rate: int = Field(ge=8000)
    timing_marks_emitted: list[str] = Field(default_factory=list)

    @field_validator("delivery_evidence_id", "sample_format")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("vocal delivery evidence fields must not be empty")
        return normalized

    @field_validator("timing_marks_emitted", mode="before")
    @classmethod
    def normalize_timing_marks(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            raise ValueError("timing_marks_emitted must be a list")
        return list(
            dict.fromkeys(
                normalized
                for item in values
                if (normalized := " ".join(str(item or "").strip().split()))
            )
        )


class MediaOperationEvidence(BaseModel):
    """Retained source or target evidence for one advertised media operation."""

    model_config = ConfigDict(extra="forbid")

    level: VocalEvidenceLevel
    artifact_refs: list[str] = Field(min_length=1)
    claim_summary: str = Field(min_length=1)

    @field_validator("artifact_refs", mode="before")
    @classmethod
    def normalize_artifact_refs(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            raise ValueError("artifact_refs must be a list")
        result = list(
            dict.fromkeys(
                normalized
                for item in values
                if (normalized := " ".join(str(item or "").strip().split()))
            )
        )
        if not result:
            raise ValueError("artifact_refs must contain retained evidence")
        return result

    @field_validator("claim_summary")
    @classmethod
    def normalize_claim_summary(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("claim_summary must not be empty")
        return normalized


class MediaProviderDeclaration(BaseModel):
    """Qualified lifecycle and mixer contract for one peer media backend.

    The backend identity remains trusted runtime metadata. Model-facing
    planning uses only the stable ``chromie.media.*`` capability family.
    """

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    supported_operations: list[MediaOperation] = Field(min_length=1)
    supported_media_kinds: list[str] = Field(min_length=1)
    persistent_playback: bool
    request_cancellation: bool
    progress_reporting: bool
    max_concurrency: int = Field(ge=1)
    mixer_policy: MediaMixerPolicy
    ducking_gain_db: float = Field(le=0.0)
    duck_attack_ms: int = Field(ge=0, le=5000)
    duck_release_ms: int = Field(ge=0, le=10000)
    provenance: VocalProviderProvenance
    operation_evidence: dict[MediaOperation, MediaOperationEvidence]
    contract_version: int = Field(default=1, ge=1)

    @field_validator("provider_id")
    @classmethod
    def normalize_provider_id(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("provider_id must not be empty")
        return normalized

    @field_validator("supported_operations", "supported_media_kinds", mode="before")
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            raise ValueError("media provider declaration field must be a list")
        return list(
            dict.fromkeys(
                normalized
                for item in values
                if (normalized := " ".join(str(item or "").strip().split()))
            )
        )

    @model_validator(mode="after")
    def require_operation_evidence(self) -> "MediaProviderDeclaration":
        supported = set(self.supported_operations)
        declared = set(self.operation_evidence)
        if supported != declared:
            missing = sorted(supported - declared)
            extra = sorted(declared - supported)
            raise ValueError(
                "operation_evidence must match supported_operations exactly: "
                f"missing={missing}, extra={extra}"
            )
        if not self.persistent_playback:
            raise ValueError("qualified media providers must retain persistent playback state")
        if not self.progress_reporting:
            raise ValueError("qualified media providers must report bounded playback progress")
        if not self.supported_media_kinds:
            raise ValueError("supported_media_kinds must not be empty")
        return self


class MediaPlaybackEvidence(BaseModel):
    """Provider-owned state evidence for one exact media lifecycle operation."""

    model_config = ConfigDict(extra="forbid")

    operation: MediaOperation
    playback_id: str = Field(min_length=1)
    state: MediaPlaybackState
    media_kind: str = Field(min_length=1)
    media_ref: str = Field(min_length=1)
    position_ms: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    volume: float = Field(ge=0.0, le=1.0)
    delivery_evidence_id: str = Field(min_length=1)
    ducking_active: bool = False

    @field_validator(
        "playback_id",
        "media_kind",
        "media_ref",
        "delivery_evidence_id",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("media playback evidence fields must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_progress(self) -> "MediaPlaybackEvidence":
        if self.duration_ms is not None and self.position_ms > self.duration_ms:
            raise ValueError("media position_ms cannot exceed duration_ms")
        return self


def media_capability_input_schema(
    operation: str,
    supported_media_kinds: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return the closed model-facing input schema for one media operation."""

    if operation not in MEDIA_CAPABILITY_IDS:
        raise ValueError(f"unknown media operation: {operation!r}")
    properties: dict[str, Any] = {
        "playback_id": {"type": "string", "minLength": 1},
    }
    required = ["playback_id"]
    if operation == "play":
        media_kinds = list(dict.fromkeys(supported_media_kinds or ()))
        properties = {
            "media_ref": {"type": "string", "minLength": 1},
            "media_kind": (
                {"type": "string", "enum": media_kinds}
                if media_kinds
                else {"type": "string", "minLength": 1}
            ),
            "start_position_ms": {"type": "integer", "minimum": 0},
            "volume": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        }
        required = ["media_ref", "media_kind"]
    elif operation == "seek":
        properties["position_ms"] = {"type": "integer", "minimum": 0}
        required.append("position_ms")
    elif operation == "volume":
        properties["volume"] = {"type": "number", "minimum": 0.0, "maximum": 1.0}
        required.append("volume")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def media_capability_output_schema() -> dict[str, Any]:
    """Return the shared closed provider-result schema for media lifecycle work."""

    return {
        "type": "object",
        "properties": {
            "completed": {"type": "boolean"},
            "operation": {"type": "string", "enum": list(MEDIA_OPERATIONS)},
            "capability_id": {
                "type": "string",
                "enum": list(MEDIA_CAPABILITY_IDS.values()),
            },
            "provider_id": {"type": "string"},
            "provider_contract_version": {"type": "integer", "minimum": 1},
            "evidence_level": {
                "type": ["string", "null"],
                "enum": [None, "source_test", "automated_target", "supervised_target"],
            },
            "provider_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "playback_id": {"type": "string"},
            "state": {
                "type": ["string", "null"],
                "enum": [
                    None,
                    "starting",
                    "playing",
                    "paused",
                    "completed",
                    "stopped",
                    "failed",
                ],
            },
            "media_kind": {"type": "string"},
            "media_ref": {"type": "string"},
            "position_ms": {"type": "integer", "minimum": 0},
            "duration_ms": {"type": ["integer", "null"], "minimum": 0},
            "volume": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "delivery_evidence_id": {"type": "string"},
            "mixer_policy": {
                "type": "string",
                "enum": ["duck_media_during_vocal"],
            },
            "ducking_active": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": [
            "completed",
            "operation",
            "capability_id",
            "provider_id",
            "provider_contract_version",
            "evidence_level",
            "provider_evidence_refs",
            "playback_id",
            "state",
            "media_kind",
            "media_ref",
            "position_ms",
            "duration_ms",
            "volume",
            "delivery_evidence_id",
            "mixer_policy",
            "ducking_active",
            "reason",
        ],
        "additionalProperties": False,
    }


def vocal_performance_input_schema(
    supported_modes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return the model-safe request schema for the exact public Capability."""

    modes = list(dict.fromkeys(supported_modes or VOCAL_MODES))
    invalid = sorted(set(modes) - set(VOCAL_MODES))
    if invalid or not modes:
        raise ValueError(f"invalid supported vocal modes: {invalid or modes}")
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "mode": {"type": "string", "enum": modes},
            "language_hint": {"type": "string", "minLength": 1},
            "voice_profile": {"type": "string", "minLength": 1},
            "metadata": {"type": "object"},
        },
        "required": ["text", "mode"],
        "additionalProperties": False,
    }


def vocal_performance_output_schema() -> dict[str, Any]:
    """Return the closed provider-result schema committed by the Host."""

    return {
        "type": "object",
        "properties": {
            "completed": {"type": "boolean"},
            "requested_mode": {"type": "string", "enum": list(VOCAL_MODES)},
            "delivered_mode": {
                "type": ["string", "null"],
                "enum": [None, *VOCAL_MODES],
            },
            "provider_id": {"type": "string"},
            "provider_contract_version": {"type": "integer", "minimum": 1},
            "evidence_level": {
                "type": ["string", "null"],
                "enum": [None, "source_test", "automated_target", "supervised_target"],
            },
            "provider_evidence_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
            "delivery_evidence_id": {"type": "string"},
            "playback_started": {"type": "boolean"},
            "playback_completed": {"type": "boolean"},
            "audio_duration_ms": {"type": "number", "minimum": 0},
            "sample_format": {"type": "string"},
            "sample_rate": {"type": "integer", "minimum": 0},
            "timing_marks_emitted": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reason": {"type": "string"},
        },
        "required": [
            "completed",
            "requested_mode",
            "delivered_mode",
            "provider_id",
            "provider_contract_version",
            "evidence_level",
            "provider_evidence_refs",
            "delivery_evidence_id",
            "playback_started",
            "playback_completed",
            "audio_duration_ms",
            "sample_format",
            "sample_rate",
            "timing_marks_emitted",
            "reason",
        ],
        "additionalProperties": False,
    }


FORBIDDEN_LOW_LEVEL_FIELDS = frozenset(
    {
        "action_14d",
        "actuator_ctrl",
        "joint_command",
        "joint_commands",
        "joint_target",
        "joint_targets",
        "motor_command",
        "motor_commands",
        "positions_by_name",
        "raw_joint_targets",
        "raw_motor_commands",
        "torque_command",
        "torque_commands",
    }
)
_FORBIDDEN_LOW_LEVEL_FIELD_COMPACTS = frozenset(
    field.replace("_", "") for field in FORBIDDEN_LOW_LEVEL_FIELDS
)
_FIELD_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_FIELD_SEPARATOR = re.compile(r"[^a-z0-9]+")

RAW_PLANAR_CONTROLLER_FIELDS = frozenset({"vx", "vy", "yaw"})
_OUTPUT_SCHEMA_DIGEST_DOMAIN = b"chromie-output-schema-v1\x00"
_ValueT = TypeVar("_ValueT")


def output_schema_sha256(output_schema: dict[str, Any]) -> str:
    """Return the deterministic identity of an output-schema document.

    This function only canonicalizes and hashes. Call
    :func:`validate_output_schema_declaration` before treating the digest as an
    authority commitment. Keeping hashing separate lets retained malformed
    evidence still be recognized and rejected deterministically.
    """

    if not isinstance(output_schema, dict):
        raise TypeError("output_schema must be a dictionary")
    try:
        canonical = json.dumps(
            output_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("output_schema is not canonical JSON") from exc
    return hashlib.sha256(_OUTPUT_SCHEMA_DIGEST_DOMAIN + canonical).hexdigest()


def find_raw_controller_array_schema(value: Any, *, path: str = "$") -> str | None:
    """Return the first schema path exposing a raw planar command array.

    Bounded named capabilities may expose semantic speed or duration parameters.  A
    repeated ``commands[]`` surface containing the complete ``vx``/``vy``/``yaw``
    controller vector is different: it lets a model author a low-level motion
    recipe.  Keep that provider compatibility contract callable by trusted
    runtime code, but never publish it as an LLM-visible capability.
    """

    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).strip().lower() == "commands" and isinstance(item, dict):
                items = item.get("items")
                properties = items.get("properties") if isinstance(items, dict) else None
                if isinstance(properties, dict) and RAW_PLANAR_CONTROLLER_FIELDS.issubset(
                    {str(name).strip().lower() for name in properties}
                ):
                    return child_path
            found = find_raw_controller_array_schema(item, path=child_path)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = find_raw_controller_array_schema(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def reject_forbidden_low_level_fields(
    value: _ValueT,
    *,
    path: str = "$",
) -> _ValueT:
    if isinstance(value, dict):
        for key, item in value.items():
            expanded = _FIELD_CAMEL_BOUNDARY.sub(" ", str(key).strip())
            normalized = "_".join(
                part for part in _FIELD_SEPARATOR.split(expanded.casefold()) if part
            )
            if (
                normalized in FORBIDDEN_LOW_LEVEL_FIELDS
                or normalized.replace("_", "") in _FORBIDDEN_LOW_LEVEL_FIELD_COMPACTS
            ):
                raise ValueError(f"forbidden low-level field at {path}.{key}")
            reject_forbidden_low_level_fields(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_forbidden_low_level_fields(item, path=f"{path}[{index}]")
    return value


SUPPORTED_OUTPUT_SCHEMA_TYPES = frozenset(
    {
        "array",
        "boolean",
        "integer",
        "null",
        "number",
        "object",
        "string",
    }
)


def output_schema_declaration_error(
    schema: Any,
    *,
    path: str = "$",
) -> str | None:
    """Return why a provider output schema is unsafe for model observation.

    Model-visible provider data must be declared by a closed, explicit schema.
    Open objects, empty declarations, schema composition, and untyped children
    are rejected so a provider cannot widen what later model stages may see.
    """

    if not isinstance(schema, dict):
        return f"{path} is not an object schema"
    if "$ref" in schema or any(key in schema for key in ("allOf", "anyOf", "oneOf")):
        return f"{path} uses unsupported schema indirection or composition"
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        schema_types = {schema_type}
    elif (
        isinstance(schema_type, list)
        and schema_type
        and all(isinstance(item, str) for item in schema_type)
    ):
        schema_types = set(schema_type)
    elif schema_type is None:
        schema_types = set()
    else:
        return f"{path} has an invalid type declaration"
    unsupported = sorted(schema_types - SUPPORTED_OUTPUT_SCHEMA_TYPES)
    if unsupported:
        return f"{path} uses unsupported types: {unsupported}"
    enum = schema.get("enum")
    if "enum" in schema and (not isinstance(enum, list) or not enum):
        return f"{path} enum must be a non-empty list"
    properties = schema.get("properties")
    if path == "$" and schema_type != "object":
        return "output schema root must have type=object"
    if path != "$" and not schema_types and "enum" not in schema:
        return f"{path} must declare a type or enum"
    if properties is not None and "object" not in schema_types:
        return f"{path} declares properties without type=object"
    if "object" in schema_types:
        if not isinstance(properties, dict) or not properties:
            return f"{path} must declare non-empty properties"
        if schema.get("additionalProperties") is not False:
            return f"{path} must set additionalProperties=false"
        required = schema.get("required", [])
        if not isinstance(required, list) or any(
            not isinstance(item, str) or item not in properties for item in required
        ):
            return f"{path} has invalid required properties"
        for key, child in properties.items():
            error = output_schema_declaration_error(
                child,
                path=f"{path}.properties.{key}",
            )
            if error is not None:
                return error
    if "items" in schema and "array" not in schema_types:
        return f"{path} declares items without type=array"
    if "array" in schema_types:
        items = schema.get("items")
        if not isinstance(items, dict):
            return f"{path} array must declare an item schema"
        return output_schema_declaration_error(items, path=f"{path}.items")
    return None


def validate_output_schema_declaration(schema: Any) -> dict[str, Any]:
    """Validate and return one closed provider output-schema declaration."""

    error = output_schema_declaration_error(schema)
    if error is not None:
        raise ValueError(error)
    if not isinstance(schema, dict):
        raise ValueError("output schema validation completed without an object declaration")
    reject_forbidden_low_level_fields(schema)
    raw_controller_path = find_raw_controller_array_schema(schema)
    if raw_controller_path is not None:
        raise ValueError(
            f"output schema exposes a raw planar controller command array at {raw_controller_path}"
        )
    return schema


class OptionalCapabilityIdentityModel(BaseModel):
    """Optional canonical executable capability identity."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str | None = None

    @field_validator("capability_id", mode="before")
    @classmethod
    def normalize_capability_id(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None


class CapabilityIdentityModel(BaseModel):
    """Canonical executable capability identity."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1)

    @field_validator("capability_id", mode="before")
    @classmethod
    def normalize_capability_id(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value


class InteractionSpeech(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"speech_{uuid4().hex[:12]}")
    text: str = Field(min_length=1)
    timing: SpeechTiming = "immediate"
    style: str = "brief"
    priority: str = "normal"
    interruptible: bool = True
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("speech id must not be empty")
        return normalized

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join((value or "").strip().split())
        if not normalized:
            raise ValueError("speech text must not be empty")
        return normalized

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class CapabilityRequest(CapabilityIdentityModel):
    """One exact executable Capability request."""

    request_id: str = Field(default_factory=lambda: f"capreq_{uuid4().hex[:12]}")
    capability_version: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    timing: CapabilityTiming = "parallel"
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    cancellable: bool = True
    requires_confirmation: bool = False
    idempotency_key: str | None = None
    committed_output_schema_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    committed_completion_evidence_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("identifier must not be empty")
        return normalized

    @field_validator("args", "metadata")
    @classmethod
    def reject_low_level_payloads(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class CapabilityResult(CapabilityIdentityModel):
    """Terminal or intermediate result for one exact Capability request."""

    request_id: str
    capability_version: str | None = None
    status: CapabilityResultStatus
    provider_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason_code: str | None = None
    message: str = ""
    trace_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("output", "metadata")
    @classmethod
    def reject_low_level_result_payloads(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class CapabilityTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str = Field(min_length=1)
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def reject_low_level_trace_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class CapabilityTrace(CapabilityIdentityModel):
    """Correlated execution trace for one exact Capability request."""

    trace_id: str = Field(default_factory=lambda: f"captrace_{uuid4().hex[:12]}")
    interaction_id: str
    request_id: str
    provider_id: str
    status: CapabilityResultStatus = "accepted"
    events: list[CapabilityTraceEvent] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(default_factory=lambda: f"interaction_{uuid4().hex[:12]}")
    status: InteractionStatus = "ok"
    speech: list[InteractionSpeech] = Field(default_factory=list)
    capabilities: list[CapabilityRequest] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("interaction_id")
    @classmethod
    def normalize_interaction_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("interaction_id must not be empty")
        return normalized

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def propagate_confirmation_requirement(self) -> "InteractionResponse":
        if any(request.requires_confirmation for request in self.capabilities):
            self.requires_confirmation = True
        execution_ids = [
            *(item.id for item in self.speech),
            *(item.request_id for item in self.capabilities),
        ]
        if len(execution_ids) != len(set(execution_ids)):
            raise ValueError(
                "speech ids and capability request_ids must be unique within one interaction"
            )
        return self
