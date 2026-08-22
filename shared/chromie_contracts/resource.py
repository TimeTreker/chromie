from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .text import normalize_whitespace
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
        "capability_id",
        "steps",
        "transport",
        "website",
    }
)
_RESOURCE_FIELD_SEPARATOR = re.compile(r"[^a-z0-9]+")
_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])"
)
_MEASUREMENT_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<number>[-+]?(?:\d+(?:\.\d+)?|\.\d+))"
    r"\s*(?P<unit>[A-Za-z\u4e00-\u9fff]+)"
)
_MEASUREMENT_UNIT_ALIASES = {
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "米": "m",
    "kilometer": "km",
    "kilometers": "km",
    "kilometre": "km",
    "kilometres": "km",
    "千米": "km",
}


def typed_measurement_facts(value: Any) -> set[tuple[Decimal, str]]:
    """Return mechanically comparable number/unit facts from a typed value."""

    facts: set[tuple[Decimal, str]] = set()
    for match in _MEASUREMENT_LITERAL_RE.finditer(str(value or "")):
        try:
            number = Decimal(match.group("number"))
        except InvalidOperation:
            continue
        unit = match.group("unit").strip().casefold()
        unit = _MEASUREMENT_UNIT_ALIASES.get(unit, unit)
        if unit:
            facts.add((number, unit))
    return facts


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


def _typed_binding_facts(bindings: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Return comparable typed facts without deciding their semantic owner."""

    facts: dict[tuple[str, str], str] = {}
    for name, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        entity_type = " ".join(
            str(binding.get("entity_type") or "").strip().casefold().split()
        )
        value = " ".join(
            str(binding.get("value") or "").strip().casefold().split()
        )
        if entity_type and value:
            facts[(entity_type, value)] = str(name)
    return facts

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
        return normalize_whitespace(value)

    @field_validator("attributes")
    @classmethod
    def reject_low_level_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        checked = _reject_resource_implementation_fields(
            value,
            path="resource.attributes",
        )
        reserved = {
            "delivery_mode",
            "item",
            "quantity",
            "recipient",
            "resource",
            "resource_description",
            "resource_kind",
            "resource_quantity",
            "source",
        }
        duplicated = sorted(
            str(name)
            for name in checked
            if str(name).strip().casefold().replace("-", "_") in reserved
        )
        if duplicated:
            raise ValueError(
                "resource attributes cannot duplicate canonical resource fields: "
                + ", ".join(duplicated)
            )
        return checked

class ResourceSource(BaseModel):
    """Semantic source binding without provider, coordinates, or implementation details."""

    model_config = ConfigDict(extra="forbid")

    status: ResourceSourceStatus
    description: str = ""
    bindings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("bindings")
    @classmethod
    def reject_low_level_bindings(cls, value: dict[str, Any]) -> dict[str, Any]:
        checked = _reject_resource_implementation_fields(
            value,
            path="resource.source.bindings",
        )
        non_source = {
            "amount",
            "count",
            "delivery_mode",
            "item",
            "quantity",
            "recipient",
            "resource",
            "resource_description",
            "resource_kind",
            "resource_quantity",
        }
        duplicated = sorted(
            str(name)
            for name in checked
            if str(name).strip().casefold().replace("-", "_") in non_source
        )
        if duplicated:
            raise ValueError(
                "resource source bindings cannot duplicate non-source authority: "
                + ", ".join(duplicated)
            )
        return checked

    @model_validator(mode="after")
    def validate_source_shape(self) -> "ResourceSource":
        if self.status == "known" and not self.bindings:
            raise ValueError(
                "known resource source requires typed source bindings; "
                "source.description is summary only"
            )
        if self.status == "unknown" and (self.description or self.bindings):
            raise ValueError("unknown resource source must not invent a source")
        described_numbers = set(_NUMERIC_LITERAL_RE.findall(self.description))
        bound_numbers = {
            number
            for binding in self.bindings.values()
            if isinstance(binding, dict)
            for number in _NUMERIC_LITERAL_RE.findall(
                str(binding.get("value") or "")
            )
        }
        unbound_numbers = sorted(described_numbers - bound_numbers)
        if unbound_numbers:
            raise ValueError(
                "numeric facts in source.description require typed source.bindings "
                "with the same value: " + ", ".join(unbound_numbers)
            )
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
        return normalize_whitespace(value)


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
        attribute_facts = _typed_binding_facts(self.resource.attributes)
        source_facts = _typed_binding_facts(self.source.bindings)
        duplicate_facts = sorted(set(attribute_facts) & set(source_facts))
        if duplicate_facts:
            rendered = ", ".join(
                f"resource.attributes.{attribute_facts[fact]}="
                f"source.bindings.{source_facts[fact]}"
                for fact in duplicate_facts
            )
            raise ValueError(
                "one typed resource fact cannot be authored by both resource "
                "attributes and source bindings: " + rendered
            )
        attribute_measurements = {
            fact: str(name)
            for name, binding in self.resource.attributes.items()
            if isinstance(binding, dict)
            for fact in typed_measurement_facts(binding.get("value"))
        }
        source_measurements = {
            fact: str(name)
            for name, binding in self.source.bindings.items()
            if isinstance(binding, dict)
            for fact in typed_measurement_facts(binding.get("value"))
        }
        duplicate_measurements = sorted(
            set(attribute_measurements) & set(source_measurements)
        )
        if duplicate_measurements:
            rendered = ", ".join(
                f"resource.attributes.{attribute_measurements[fact]}="
                f"source.bindings.{source_measurements[fact]}"
                for fact in duplicate_measurements
            )
            raise ValueError(
                "one equivalent typed measurement cannot be authored by both "
                "resource attributes and source bindings: " + rendered
            )
        return self


def resource_semantic_bindings(
    responsibility: AcquireAndDeliverResource,
) -> dict[str, dict[str, Any]]:
    """Return a transient flat view of canonical resource facts for validation.

    The returned mapping is computed on demand and is never stored back into a
    Goal.  ``resource_responsibility`` remains the sole semantic authority; this
    helper only lets generic Planner validators compare typed argument names
    without creating a second persisted representation.
    """

    bindings: dict[str, dict[str, Any]] = {}

    def add_binding(name: str, value: Any) -> None:
        if not isinstance(value, dict):
            return
        normalized_name = " ".join(str(name or "").strip().split())
        if not normalized_name or normalized_name in bindings:
            raise ValueError(
                "canonical resource contains duplicate semantic binding name="
                f"{normalized_name!r}"
            )
        payload = dict(value)
        payload["name"] = normalized_name
        bindings[normalized_name] = payload

    for name, value in responsibility.resource.attributes.items():
        add_binding(name, value)
    for name, value in responsibility.source.bindings.items():
        add_binding(name, value)
    if responsibility.resource.quantity:
        add_binding(
            "quantity",
            {
                "name": "quantity",
                "entity_type": "quantity",
                "value": responsibility.resource.quantity,
                "confidence": 1.0,
            },
        )
    return bindings
