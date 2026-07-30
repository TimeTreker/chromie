from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InteractionStatus = Literal["ok", "clarify", "refused", "ignored", "error"]
CapabilityTiming = Literal["parallel", "sequential"]
SkillTiming = CapabilityTiming
SpeechTiming = Literal["immediate", "parallel", "sequential", "after_skills"]
CapabilityResultStatus = Literal[
    "accepted",
    "running",
    "completed",
    "refused",
    "failed",
    "cancelled",
    "timed_out",
]
SkillResultStatus = CapabilityResultStatus

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
_FIELD_CAMEL_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)
_FIELD_SEPARATOR = re.compile(r"[^a-z0-9]+")

RAW_PLANAR_CONTROLLER_FIELDS = frozenset({"vx", "vy", "yaw"})
_OUTPUT_SCHEMA_DIGEST_DOMAIN = b"chromie-output-schema-v1\x00"


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
    return hashlib.sha256(
        _OUTPUT_SCHEMA_DIGEST_DOMAIN + canonical
    ).hexdigest()


def find_raw_controller_array_schema(value: Any, *, path: str = "$") -> str | None:
    """Return the first schema path exposing a raw planar command array.

    Bounded named skills may expose semantic speed or duration parameters.  A
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


def reject_forbidden_low_level_fields(value: Any, *, path: str = "$") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            expanded = _FIELD_CAMEL_BOUNDARY.sub(" ", str(key).strip())
            normalized = "_".join(
                part
                for part in _FIELD_SEPARATOR.split(expanded.casefold())
                if part
            )
            if (
                normalized in FORBIDDEN_LOW_LEVEL_FIELDS
                or normalized.replace("_", "")
                in _FORBIDDEN_LOW_LEVEL_FIELD_COMPACTS
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
    if "$ref" in schema or any(
        key in schema for key in ("allOf", "anyOf", "oneOf")
    ):
        return f"{path} uses unsupported schema indirection or composition"
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        schema_types = {schema_type}
    elif isinstance(schema_type, list) and schema_type and all(
        isinstance(item, str) for item in schema_type
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
            not isinstance(item, str) or item not in properties
            for item in required
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
        raise ValueError(
            "output schema validation completed without an object declaration"
        )
    reject_forbidden_low_level_fields(schema)
    raw_controller_path = find_raw_controller_array_schema(schema)
    if raw_controller_path is not None:
        raise ValueError(
            "output schema exposes a raw planar controller command array at "
            f"{raw_controller_path}"
        )
    return schema


def normalize_capability_identity_payload(value: Any) -> Any:
    """Normalize one bounded legacy ``skill_id`` input to ``capability_id``.

    New contracts serialize only ``capability_id``.  Historical payloads may
    still provide ``skill_id`` at declared decode/persistence boundaries.  A
    payload containing both names is accepted only when the normalized values
    are identical; contradictory executable identity fails closed.
    """

    if not isinstance(value, dict):
        return value
    payload = dict(value)
    has_capability = "capability_id" in payload
    has_legacy = "skill_id" in payload
    if not has_capability and not has_legacy:
        return payload

    capability_id = " ".join(str(payload.get("capability_id") or "").strip().split())
    legacy_skill_id = " ".join(str(payload.get("skill_id") or "").strip().split())
    if has_capability and has_legacy and capability_id != legacy_skill_id:
        raise ValueError(
            "conflicting capability_id and legacy skill_id executable identities"
        )
    normalized = capability_id or legacy_skill_id
    if not normalized:
        raise ValueError("capability_id must not be empty")
    payload["capability_id"] = normalized
    payload.pop("skill_id", None)
    return payload


class CapabilityIdentityModel(BaseModel):
    """Canonical executable identity with a bounded legacy read alias."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_identity(cls, value: Any) -> Any:
        return normalize_capability_identity_payload(value)

    @field_validator("capability_id", mode="before")
    @classmethod
    def normalize_capability_id(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @property
    def skill_id(self) -> str:
        """Read-only compatibility projection for already-migrating callers."""

        return self.capability_id

    def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False):
        normalized = normalize_capability_identity_payload(update) if update else update
        return super().model_copy(update=normalized, deep=deep)


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

    request_id: str = Field(default_factory=lambda: f"skillreq_{uuid4().hex[:12]}")
    skill_version: str | None = None
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
    skill_version: str | None = None
    status: CapabilityResultStatus
    provider_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    reason_code: str | None = None
    message: str = ""
    trace_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("output")
    @classmethod
    def reject_low_level_output(cls, value: dict[str, Any]) -> dict[str, Any]:
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

    trace_id: str = Field(default_factory=lambda: f"skilltrace_{uuid4().hex[:12]}")
    interaction_id: str
    request_id: str
    provider_id: str
    status: CapabilityResultStatus = "accepted"
    events: list[CapabilityTraceEvent] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


# Bounded source compatibility.  These aliases accept legacy ``skill_id`` input
# through the canonical models, while all new serialization emits
# ``capability_id``.
SkillRequest = CapabilityRequest
SkillResult = CapabilityResult
SkillTraceEvent = CapabilityTraceEvent
SkillTrace = CapabilityTrace


class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(default_factory=lambda: f"interaction_{uuid4().hex[:12]}")
    status: InteractionStatus = "ok"
    speech: list[InteractionSpeech] = Field(default_factory=list)
    skills: list[CapabilityRequest] = Field(default_factory=list)
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
        if any(request.requires_confirmation for request in self.skills):
            self.requires_confirmation = True
        execution_ids = [
            *(item.id for item in self.speech),
            *(item.request_id for item in self.skills),
        ]
        if len(execution_ids) != len(set(execution_ids)):
            raise ValueError(
                "speech ids and skill request_ids must be unique within "
                "one interaction"
            )
        return self
