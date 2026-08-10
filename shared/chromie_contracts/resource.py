from __future__ import annotations

from typing import Any, Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields


ResourceKind = Literal["physical_object", "information"]
ResourceSourceStatus = Literal["known", "unknown", "provider_resolved"]

_RESOURCE_IMPLEMENTATION_FIELDS = frozenset(
    {
        "backend",
        "capability_id",
        "coordinates",
        "execution_mode",
        "grasp_pose",
        "latitude",
        "longitude",
        "plan",
        "provider",
        "provider_id",
        "search_engine",
        "skill_id",
        "steps",
        "transport",
        "website",
    }
)
_RESOURCE_FIELD_SEPARATOR = re.compile(r"[^a-z0-9]+")


def _reject_resource_implementation_fields(
    value: dict[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    reject_forbidden_low_level_fields(value, path=path)
    for key, item in value.items():
        normalized = "_".join(
            part
            for part in _RESOURCE_FIELD_SEPARATOR.split(str(key).strip().casefold())
            if part
        )
        if normalized in _RESOURCE_IMPLEMENTATION_FIELDS:
            raise ValueError(f"provider or implementation field is forbidden at {path}.{key}")
        if isinstance(item, dict):
            _reject_resource_implementation_fields(item, path=f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                if isinstance(child, dict):
                    _reject_resource_implementation_fields(
                        child,
                        path=f"{path}.{key}[{index}]",
                    )
    return value

ResourceDeliveryMode = Literal[
    "physical_handover",
    "spoken_explanation",
    "structured_result",
]


class ResourceDescriptor(BaseModel):
    """Provider-neutral description of what the user wants acquired."""

    model_config = ConfigDict(extra="forbid")

    kind: ResourceKind
    description: str = Field(min_length=1)
    quantity: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("description", "quantity", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("attributes")
    @classmethod
    def reject_low_level_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_resource_implementation_fields(value, path="resource.attributes")


class ResourceSource(BaseModel):
    """Semantic source binding without provider, coordinates, or implementation details."""

    model_config = ConfigDict(extra="forbid")

    status: ResourceSourceStatus
    description: str = ""
    bindings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("bindings")
    @classmethod
    def reject_low_level_bindings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_resource_implementation_fields(value, path="resource.source.bindings")

    @model_validator(mode="after")
    def validate_source_shape(self) -> "ResourceSource":
        if self.status == "known" and not (self.description or self.bindings):
            raise ValueError("known resource source requires description or bindings")
        if self.status == "unknown" and (self.description or self.bindings):
            raise ValueError("unknown resource source must not invent a source")
        return self


class ResourceRecipient(BaseModel):
    """Who should receive the resource after acquisition."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(default="requester", min_length=1)
    referent_id: str | None = None

    @field_validator("description", "referent_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


class AcquireAndDeliverResource(BaseModel):
    """One human-level responsibility that may be fulfilled by any exact provider.

    The contract intentionally contains no provider ID, capability ID, execution
    mode, coordinates, grasp pose, search engine, or website. Goal Association
    owns this semantic responsibility; the Planner later selects one exact
    registered capability, and the provider owns implementation and evidence.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    responsibility_type: Literal["acquire_and_deliver_resource"] = (
        "acquire_and_deliver_resource"
    )
    resource: ResourceDescriptor
    source: ResourceSource
    recipient: ResourceRecipient = Field(default_factory=ResourceRecipient)
    delivery_mode: ResourceDeliveryMode
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_resource_implementation_fields(value, path="resource.metadata")

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_responsibility_variant(cls, value: Any) -> Any:
        """Accept the retired variant only as an input-compatibility alias.

        Canonical semantics are responsibility_type + resource.kind.  Keeping a
        second serialized discriminator creates two names for one decision and
        invites planners/providers to route by labels instead of semantic scope.
        """

        if not isinstance(value, dict):
            return value
        payload = dict(value)
        legacy_variant = payload.pop("responsibility_variant", None)
        if legacy_variant is None:
            return payload
        resource = payload.get("resource")
        kind = resource.get("kind") if isinstance(resource, dict) else None
        if kind in {"physical_object", "information"}:
            expected_variant = (
                "fetch_and_deliver_object"
                if kind == "physical_object"
                else "fetch_and_deliver_information"
            )
            if legacy_variant != expected_variant:
                raise ValueError(
                    "resource kind and legacy responsibility_variant disagree: "
                    f"kind={kind} variant={legacy_variant}"
                )
        return payload

    @model_validator(mode="after")
    def validate_delivery_mode(self) -> "AcquireAndDeliverResource":
        if (
            self.resource.kind == "physical_object"
            and self.delivery_mode != "physical_handover"
        ):
            raise ValueError(
                "physical_object resource requires delivery_mode=physical_handover"
            )
        if (
            self.resource.kind == "information"
            and self.delivery_mode == "physical_handover"
        ):
            raise ValueError(
                "information resource cannot use delivery_mode=physical_handover"
            )
        return self
