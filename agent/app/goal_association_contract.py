from __future__ import annotations

"""Model-facing Goal Association DTOs and typed representation only.

Schema construction and deterministic normalization/conservation mechanics live in sibling
modules; GoalAssociationResolver remains the sole semantic continuity transaction.
"""

import re
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue

try:
    from chromie_contracts.text import normalize_whitespace
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.text import normalize_whitespace


GoalSegmentationDecision = Literal["create_goals"]
InformationResourceDomain = Literal[
    "local_clock",
    "weather_forecast",
    "external_grounded_information",
    "direct_environment_perception",
    "private_runtime_information",
]
GoalOutputMode = Literal[
    "speech",
    "styled_speech",
    "recitation",
    "singing",
    "humming",
    "nonverbal_vocalization",
    "body_action",
    "media_playback",
    "information",
    "stateful_effect",
    "other",
]
GoalMediaOperation = Literal[
    "none",
    "play",
    "pause",
    "resume",
    "seek",
    "stop",
    "volume",
    "status",
]
_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])"
)
_EXECUTION_CONTRACT_PROMPT = (
    "Preserve the human-facing WHAT category from Goal Interpretation exactly. "
    "Goal Association may refine semantic bindings, resource structure, references, "
    "and canonical continuity, but it does not decide whether a Capability, provider, "
    "execution lane, fresh Evidence, or Work is required. Use information when the "
    "person wants Chromie to determine or provide information, whether that information "
    "is already available to reasoning/context or must later be acquired. Use "
    "stateful_effect only for a durable or future state change outside embodiment, such as "
    "recording, scheduling, changing a setting, or sending later. Locomotion, posture, "
    "gaze, gesture, physical manipulation, carrying, and handover use body_action even "
    "when they change location or another lasting physical state; lifecycle "
    "control of media uses media_playback; authored vocal performances use their exact "
    "vocal mode. Ordinary directly authored conversation uses speech. Capability and "
    "provider applicability are Planner concerns and must not be encoded into Goal "
    "output_mode or metadata. A negative instruction that limits another outcome is a "
    "constraint, not a separate Goal. A manner, mood, persona, or social-presentation "
    "directive attached to another effect is expression framing, not an extra spoken "
    "Goal. Coordination grammar still requires one Goal per independently satisfiable "
    "observable outcome. Never invent an audible modality from style wording alone."
)

_GOAL_SEGMENTATION_IDENTITY_CONTRACT = (
    "Owner-approved identity evidence names the first-person Chromie entity. Preserve "
    "its exact name, age description, family role, social identity, and acting/perceiving/body "
    "ownership when those facts are material. Do not turn that social identity into a "
    "biological-human claim. Never replace that identity with model, "
    "provider, device, robot, or system metadata. Unknown family members and relationship "
    "labels remain unknown until introduced. Identity and personality expression never "
    "create an extra Goal and must not be volunteered in unrelated work. "
)


GoalAssociationModelRelationship = Literal[
    "continue",
    "modify",
    "clarify",
    "confirm",
    "reject",
    "cancel",
    "pause",
    "resume",
    "merge",
    "split",
    "reference",
]


class GoalAssociationModelAssociation(BaseModel):
    """Minimal model-facing continuity decision for an existing goal."""

    # The decoder schema forbids extras. Validation intentionally ignores harmless
    # transport noise such as model-authored IDs; the host never trusts or copies it.
    model_config = ConfigDict(extra="ignore")

    relationship: GoalAssociationModelRelationship = Field(
        description=(
            "Model-owned semantic relationship to the targeted Goal. continue "
            "advances unfinished unchanged work; reference requests retrieval, "
            "restatement, explanation, comparison, or another answer from a retained "
            "Goal without changing it. A social reaction, personal feeling, practical "
            "decision, acknowledgement, or new conversational judgment is a fresh "
            "vocal_output Goal even when prior Goal evidence supplies context. "
            "clarify means the current user "
            "turn supplies missing information for that Goal, not that the user "
            "is asking for more explanation."
        )
    )
    source_responsibility_refs: list[str] = Field(min_length=1, max_length=8)
    target_goal_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    updated_description: str = ""
    resolved_gap_ids: list[str] = Field(default_factory=list)

    @field_validator("reason_summary", "updated_description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator(
        "source_responsibility_refs",
        "target_goal_ids",
        "resolved_gap_ids",
        mode="before",
    )
    @classmethod
    def normalize_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("goal ID fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = " ".join(str(item or "").strip().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
        return out

    @model_validator(mode="after")
    def validate_relationship_shape(self) -> "GoalAssociationModelAssociation":
        if not self.target_goal_ids:
            raise ValueError(f"relationship={self.relationship} requires target_goal_ids")
        if self.relationship == "merge" and len(self.target_goal_ids) < 2:
            raise ValueError("relationship=merge requires at least two target goals")
        if self.relationship in {"modify", "clarify"} and not (
            self.updated_description or self.resolved_gap_ids
        ):
            raise ValueError(
                f"relationship={self.relationship} requires updated_description "
                "or resolved_gap_ids"
            )
        return self
class GoalAssociationModelBinding(BaseModel):
    """Model-facing semantic binding resolved before planning."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    value: str = Field(
        min_length=1,
        description=(
            "Resolved semantic value. A directly supplied value preserves the exact "
            "contiguous user-language surface from the authoritative current turn; "
            "only an indirect reference backed by supplied discourse provenance may "
            "use a contextual resolved value. Goal Association never rewrites human "
            "temporal wording into Capability argument vocabulary."
        ),
    )
    referent_id: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("name", "entity_type", "value", "referent_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_semantic_value(self) -> "GoalAssociationModelBinding":
        if (
            self.entity_type.casefold() == "speed"
            and not any(character.isdigit() for character in self.value)
            and self.value not in {"slow", "normal", "quick"}
        ):
            raise ValueError(
                "qualitative speed bindings require a canonical value: "
                "slow, normal, or quick"
            )
        return self


class GoalAssociationModelResolvedReference(BaseModel):
    """Model-facing explicit resolution of a reference in the current turn."""

    model_config = ConfigDict(extra="ignore")

    surface_form: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    resolved_value: str = Field(min_length=1)
    source: Literal[
        "discourse_referent",
        "active_goal_binding",
    ]
    referent_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator(
        "surface_form",
        "entity_type",
        "resolved_value",
        "referent_id",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

class GoalAssociationModelReferentUpdate(BaseModel):
    """Model-facing scoped discourse mutation; identifiers remain Host-owned."""

    model_config = ConfigDict(extra="ignore")

    operation: Literal["introduce", "correct", "focus", "background", "retire"]
    entity_type: str = ""
    canonical_value: str = ""
    aliases: list[str] = Field(default_factory=list)
    target_referent_ids: list[str] = Field(default_factory=list)
    target_goal_ids: list[str] = Field(default_factory=list)
    scope_kind: Literal["conversation", "task", "goal"] = "conversation"
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator(
        "entity_type",
        "canonical_value",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator(
        "aliases",
        "target_referent_ids",
        "target_goal_ids",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected an array")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelReferentUpdate":
        if self.operation in {"introduce", "correct"}:
            if not self.entity_type or not self.canonical_value:
                raise ValueError(
                    f"operation={self.operation} requires entity_type and canonical_value"
                )
        if self.operation in {"focus", "background", "retire"} and not self.target_referent_ids:
            raise ValueError(
                f"operation={self.operation} requires target_referent_ids"
            )
        if self.operation == "correct" and not self.target_referent_ids:
            raise ValueError("operation=correct requires target_referent_ids")
        return self


class GoalAssociationModelResourceRecipient(BaseModel):
    """Canonical recipient meaning for one resource responsibility."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(default="requester", min_length=1)
    referent_id: str | None = None

    @field_validator("description", "referent_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_whitespace(value)


class GoalAssociationModelInformationSource(BaseModel):
    """Information acquisition source without a second arbitrary binding surface.

    Query scope belongs only in ``query_scope``.  If the user explicitly names an
    information source, ``source_name`` owns that one semantic fact.  This shape
    makes it impossible for a model to duplicate location/time query scope under
    both resource attributes and source bindings.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["known", "unknown", "provider_resolved"]
    source_name: str = ""
    referent_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("source_name", "referent_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelInformationSource":
        if self.status == "known" and not self.source_name:
            raise ValueError("known information source requires source_name")
        if self.status != "known" and (self.source_name or self.referent_id):
            raise ValueError(
                "only status=known may name an information source; provider_resolved "
                "delegates source selection and unknown must remain unknown"
            )
        return self


class GoalAssociationModelPhysicalSource(BaseModel):
    """Physical acquisition grounding; this is the sole writable spatial surface."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["known", "unknown", "provider_resolved"]
    description: str = ""
    acquisition_bindings: list[GoalAssociationModelBinding] = Field(
        default_factory=list,
        max_length=12,
    )

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelPhysicalSource":
        if self.status == "known" and not self.acquisition_bindings:
            raise ValueError(
                "known physical source requires typed acquisition_bindings; "
                "description is summary only"
            )
        if self.status == "unknown" and (self.description or self.acquisition_bindings):
            raise ValueError("unknown physical source must not invent acquisition grounding")
        described_numbers = set(_NUMERIC_LITERAL_RE.findall(self.description))
        bound_numbers = {
            number
            for binding in self.acquisition_bindings
            for number in _NUMERIC_LITERAL_RE.findall(binding.value)
        }
        unbound_numbers = sorted(described_numbers - bound_numbers)
        if unbound_numbers:
            raise ValueError(
                "numeric facts in physical source description require matching typed "
                "acquisition_bindings: " + ", ".join(unbound_numbers)
            )
        return self


def _validate_model_resource_quantity(value: str) -> str:
    if not value:
        return value
    try:
        quantity = float(value)
    except ValueError as exc:
        raise ValueError("resource quantity must be a normalized numeric string") from exc
    if quantity <= 0 or not value.replace(".", "", 1).isdigit():
        raise ValueError("resource quantity must be a positive normalized numeric string")
    return value


class GoalAssociationModelInformationResourceResponsibility(BaseModel):
    """Single-owner model-facing contract for grounded information acquisition."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["information"]
    information_domain: InformationResourceDomain = Field(
        description=(
            "Provider-neutral semantic evidence domain. Classify the needed fact, "
            "not the nearest available Capability: local_clock for Chromie's trusted "
            "local date/time, weather_forecast for weather, "
            "external_grounded_information for public facts/research, "
            "direct_environment_perception for present nearby people/objects/events, "
            "and private_runtime_information for other private live state."
        ),
    )
    description: str = Field(min_length=1)
    quantity: str = ""
    query_scope: list[GoalAssociationModelBinding] = Field(
        min_length=1,
        max_length=12,
        description=(
            "Every material human information-query constraint exactly once. Preserve "
            "source-grounded temporal wording as semantic scope; do not translate it "
            "into Capability argument names or values. A natural compound time scope "
            "may remain one binding with entity_type=temporal_scope."
        ),
    )
    source: GoalAssociationModelInformationSource
    recipient: GoalAssociationModelResourceRecipient = Field(
        default_factory=GoalAssociationModelResourceRecipient
    )
    delivery_mode: Literal["spoken_explanation", "structured_result"]

    @field_validator("description", "quantity", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: str) -> str:
        return _validate_model_resource_quantity(value)

    @model_validator(mode="after")
    def validate_scope(self) -> "GoalAssociationModelInformationResourceResponsibility":
        reserved = {
            "source", "provider", "provider_id", "website", "search_engine",
            "delivery_mode", "recipient", "resource", "quantity", "information_domain",
        }
        duplicated = sorted(
            binding.name
            for binding in self.query_scope
            if binding.name.strip().casefold().replace("-", "_") in reserved
        )
        if duplicated:
            raise ValueError(
                "information query_scope cannot duplicate source/delivery/resource authority: "
                + ", ".join(duplicated)
            )
        return self


class GoalAssociationModelPhysicalResourceResponsibility(BaseModel):
    """Single-owner model-facing contract for physical acquisition and handover."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["physical_object"] = Field(
        description=(
            "Select only when the responsibility is to acquire a distinct concrete "
            "object independent of Chromie's body and physically hand it to a "
            "recipient. Never select for Chromie's own locomotion, posture, gaze, "
            "gesture, turning, or other body motion."
        ),
    )
    description: str = Field(
        min_length=1,
        description=(
            "A distinct concrete object/resource that must be acquired and handed "
            "to a recipient. Body motion, locomotion, gaze, blinking, waving, "
            "turning, posture, and gestures are not physical resources."
        ),
    )
    quantity: str = ""
    source: GoalAssociationModelPhysicalSource
    recipient: GoalAssociationModelResourceRecipient = Field(
        default_factory=GoalAssociationModelResourceRecipient
    )
    delivery_mode: Literal["physical_handover"]

    @field_validator("description", "quantity", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: str) -> str:
        return _validate_model_resource_quantity(value)


GoalAssociationModelResourceResponsibility = Annotated[
    Union[
        GoalAssociationModelInformationResourceResponsibility,
        GoalAssociationModelPhysicalResourceResponsibility,
    ],
    Field(discriminator="kind"),
]


class GoalAssociationModelGoal(BaseModel):
    """Minimal model-facing semantic Goal preserving provider-neutral WHAT."""

    model_config = ConfigDict(extra="forbid")

    source_responsibility_refs: list[str] = Field(min_length=1, max_length=8)
    description: str = Field(min_length=1)
    output_mode: GoalOutputMode = Field(
        description=(
            "Provider-neutral human outcome modality copied from Goal Interpretation. "
            "information says the person wants information; stateful_effect says the "
            "person wants a durable or future state change outside embodiment. Physical "
            "motion, posture, gaze, gesture, manipulation, carrying, and handover are "
            "body_action even when their physical result lasts. Neither category asserts "
            "that a Capability, provider, execution lane, fresh Evidence, or Work is "
            "required. Use exact embodied, media, or vocal modes only when those are "
            "the requested observable outcome."
        ),
    )
    media_operation: GoalMediaOperation = Field(
        default="none",
        description=(
            "Exact persistent media lifecycle operation for media_playback; "
            "none for every other output mode."
        ),
    )
    bindings: list[GoalAssociationModelBinding] = Field(
        default_factory=list,
        max_length=12,
    )
    related_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    supersedes_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    resource_kind: Literal["none", "physical_object", "information"] = Field(
        default="none",
        description=(
            "Explicit discriminator for the requested resource outcome. Use none for "
            "ordinary conversation and Chromie's own locomotion, posture, gaze, "
            "gesture, turning, or body motion; physical_object only when acquiring a "
            "distinct concrete object and handing it to a recipient is the outcome; "
            "information only when determining or providing information is the outcome."
        ),
    )
    resource_responsibility: GoalAssociationModelResourceResponsibility | None = Field(
        default=None,
        description=(
            "Use null for ordinary conversation, vocal/media effects, and Chromie's "
            "own locomotion, posture, gaze, gesture, turning, or other body motion. "
            "Use a physical_object only when acquiring a distinct concrete object "
            "independent of Chromie's body and handing it to a recipient is itself "
            "the requested outcome. Use information only for an information outcome."
        ),
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: Any,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {
                        "resource_responsibility": {"not": {"type": "null"}}
                    },
                    "required": ["resource_responsibility"],
                },
                "then": {"properties": {"bindings": {"maxItems": 0}}},
            }
        )
        return schema

    @property
    def semantic_bindings(self) -> list[GoalAssociationModelBinding]:
        resource = self.resource_responsibility
        if resource is None:
            return list(self.bindings)
        if resource.kind == "information":
            return list(resource.query_scope)
        return list(resource.source.acquisition_bindings)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator(
        "source_responsibility_refs",
        "related_goal_ids",
        "supersedes_goal_ids",
        mode="before",
    )
    @classmethod
    def normalize_related_goal_ids(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(
            normalized
            for item in value
            if (normalized := " ".join(str(item or "").strip().split()))
        ))

    @model_validator(mode="after")
    def validate_mode_specific_fields(self) -> "GoalAssociationModelGoal":
        if self.output_mode == "media_playback" and self.media_operation == "none":
            raise ValueError("media_playback requires one exact media_operation")
        if self.output_mode != "media_playback" and self.media_operation != "none":
            raise ValueError("media_operation is valid only for output_mode=media_playback")
        actual_resource_kind = (
            self.resource_responsibility.kind
            if self.resource_responsibility is not None
            else "none"
        )
        if self.resource_kind != actual_resource_kind:
            raise ValueError(
                "resource_kind must exactly discriminate resource_responsibility: "
                f"declared={self.resource_kind!r} actual={actual_resource_kind!r}"
            )
        if self.resource_responsibility is not None:
            required_mode: GoalOutputMode = (
                "body_action"
                if self.resource_responsibility.kind == "physical_object"
                else "information"
            )
            if self.output_mode != required_mode:
                raise ValueError(
                    f"resource kind={self.resource_responsibility.kind} "
                    f"requires output_mode={required_mode}; spoken delivery is "
                    "represented by resource_responsibility.delivery_mode"
                )
        if self.resource_responsibility is not None and self.bindings:
            raise ValueError(
                "resource Goal bindings are authored only inside the typed "
                "resource_responsibility contract"
            )
        return self


class GoalSegmentationModelOutput(BaseModel):
    """Semantic goal segmentation used when no association target exists.

    The discriminant is authoritative.  The Host may receive harmless content in
    the inactive branch from a small structured-output model, but it never asks a
    second model call to decide which mutually exclusive branch was intended.
    """

    model_config = ConfigDict(extra="forbid")

    decision: GoalSegmentationDecision | None = None
    new_goals: list[GoalAssociationModelGoal] = Field(
        default_factory=list,
        max_length=8,
    )
    referent_updates: list[GoalAssociationModelReferentUpdate] = Field(
        default_factory=list,
        max_length=12,
    )
    resolved_references: list[GoalAssociationModelResolvedReference] = Field(
        default_factory=list,
        max_length=12,
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def select_branch(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        decision = str(normalized.get("decision") or "").strip()
        normalized["decision"] = "create_goals"
        return normalized

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalSegmentationModelOutput":
        if self.decision == "create_goals" and not self.new_goals:
            raise ValueError("decision=create_goals requires new_goals")
        return self

class GoalAssociationModelOutput(BaseModel):
    """One complete candidate-aware semantic result from Goal Association.

    Associations and new Goals are independent per-Responsibility outcomes, not
    mutually exclusive branches.  The dynamic decoder and trusted Host conserve
    every accepted GI Responsibility across the union of both collections.
    """

    model_config = ConfigDict(extra="forbid")

    associations: list[GoalAssociationModelAssociation] = Field(
        default_factory=list,
        max_length=8,
    )
    new_goals: list[GoalAssociationModelGoal] = Field(
        default_factory=list,
        max_length=8,
    )
    referent_updates: list[GoalAssociationModelReferentUpdate] = Field(
        default_factory=list,
        max_length=12,
    )
    resolved_references: list[GoalAssociationModelResolvedReference] = Field(
        default_factory=list,
        max_length=12,
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)
