from __future__ import annotations

import copy
import json
import re
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    field_validator,
    model_validator,
    ValidationError,
)
from pydantic.json_schema import JsonSchemaValue

from .prompt_projection import bounded_json

try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
    from chromie_contracts.text import normalize_whitespace
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.text import normalize_whitespace


class _CoverageSourceExcerptViolation(ValueError):
    """Coverage audit cited text outside the authoritative user turn."""


GoalSegmentationDecision = Literal["create_goals"]
GoalAssociationDecision = Literal["associate", "create_goals"]
InformationResourceDomain = Literal[
    "local_clock",
    "weather_forecast",
    "external_grounded_information",
    "direct_environment_perception",
    "private_runtime_information",
]
GoalResponsibilityKind = Literal[
    "executable_action",
    "vocal_output",
    "capability_dependent",
    "other",
]
GoalExecutionLane = Literal["vocal", "activity", "none"]
GoalOutputMode = Literal[
    "speech",
    "styled_speech",
    "recitation",
    "singing",
    "humming",
    "nonverbal_vocalization",
    "body_action",
    "media_playback",
    "capability_work",
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
_OUTPUT_MODE_EXECUTION_CONTRACT: dict[
    GoalOutputMode,
    tuple[GoalResponsibilityKind, GoalExecutionLane, bool],
] = {
    "speech": ("vocal_output", "vocal", False),
    "styled_speech": ("vocal_output", "vocal", True),
    "recitation": ("vocal_output", "vocal", True),
    "singing": ("vocal_output", "vocal", True),
    "humming": ("vocal_output", "vocal", True),
    "nonverbal_vocalization": ("vocal_output", "vocal", True),
    "body_action": ("executable_action", "activity", True),
    "media_playback": ("executable_action", "activity", True),
    "capability_work": ("capability_dependent", "activity", True),
    "other": ("other", "none", False),
}
_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])"
)
_EXECUTION_CONTRACT_PROMPT = (
    "Classify each Goal by the semantic work that must actually complete the "
    "human outcome, not by the channel used later to report that outcome. In the "
    "model-facing Goal JSON, output_mode is the completion discriminant; the Host "
    "deterministically derives responsibility kind, execution lane, and "
    "provider requirement from that choice. Those Host-owned projections are not "
    "fields in the model schema. Use capability_work only when completion depends on "
    "fresh external, private, or runtime evidence from a registered non-vocal "
    "Capability. Stable general knowledge, reasoning, creative content, and an "
    "immediate user-facing reminder or piece of advice that Chromie can author "
    "and deliver in the current exchange use ordinary speech. A deferred reminder, "
    "scheduled notification, recorded obligation, or later message to another person "
    "is stateful capability work: saying the reminder now does not complete that "
    "future effect. Represent the reminder's recipient, trigger, time, and content "
    "as ordinary typed Goal bindings; it is not an information acquisition resource "
    "merely because its eventual notification is spoken. The same rule applies to "
    "persistent state mutations such as adding/removing list items, recording an "
    "obligation, changing a setting, or sending a later message: use capability_work "
    "with ordinary typed bindings and no resource_responsibility unless the human "
    "outcome is genuinely to acquire and deliver a resource. Embodied effects use "
    "body_action; lifecycle "
    "control of existing media uses media_playback; authored vocal performances "
    "use their exact vocal mode. The fact that a capability result will later be "
    "spoken does not turn its owned work into speech. If no matching provider is "
    "available, preserve the evidence-dependent completion mode so downstream "
    "planning can report the limitation instead of inventing an answer. Never "
    "replace a requested embodied effect with a speech Goal because the current "
    "input channel is text, because later acknowledgement is spoken, or because "
    "of an unsupported assumption that Chromie has no embodied Capability. "
    "media_operation is meaningful only for media_playback; otherwise omit it or "
    "leave it as none. A negative instruction that limits what Chromie may say "
    "while completing another requested outcome is a constraint on that outcome, "
    "not an independently satisfiable spoken Goal. A manner, mood, persona, or "
    "social-presentation directive attached to another requested effect is likewise "
    "an expression constraint on that effect, not an additional spoken Goal. Preserve "
    "that framing in the effect Goal. Create a separate vocal Goal only when the user "
    "requests independently observable positive words, information, or a vocal "
    "performance—not merely because wording or speech could help convey the style. "
    "Coordination grammar in any language requires one Goal for every independently "
    "observable requested modality. Preserve coordination in descriptions or bindings, "
    "but never merge independently satisfiable effects merely because they overlap in "
    "time or share one sentence. Preserve each effect's own semantic output mode. "
    "When a concrete requested effect is accompanied by a broad desired social "
    "impression but no words, information, vocal performance, or second effect "
    "modality is specified, apply that impression as embodiment-wide expression "
    "framing to the concrete effect. Do not invent an audible modality from an "
    "adjective, state directive, conjunction, or imperative grammar."
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

    kind: Literal["physical_object"]
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
    """Minimal model-facing semantic Goal; ``output_mode`` is the sole execution truth."""

    model_config = ConfigDict(extra="forbid")

    source_responsibility_refs: list[str] = Field(min_length=1, max_length=8)
    description: str = Field(min_length=1)
    output_mode: GoalOutputMode = Field(
        description=(
            "Semantic work that completes this Goal, not the later channel used "
            "to deliver its result. Choose capability_work when fresh external, "
            "private, or runtime evidence is required; choose speech for directly "
            "authored ordinary conversation; use exact embodied, media, or vocal "
            "modes when those effects are the requested outcome. This is the sole "
            "model-authored execution discriminant; the Host derives responsibility "
            "kind, execution lane, and provider requirement from it."
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
    resource_responsibility: GoalAssociationModelResourceResponsibility | None = None

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
    def responsibility_kind(self) -> GoalResponsibilityKind:
        return _OUTPUT_MODE_EXECUTION_CONTRACT[self.output_mode][0]

    @property
    def execution_lane(self) -> GoalExecutionLane:
        return _OUTPUT_MODE_EXECUTION_CONTRACT[self.output_mode][1]

    @property
    def provider_required(self) -> bool:
        return _OUTPUT_MODE_EXECUTION_CONTRACT[self.output_mode][2]

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
        if self.resource_responsibility is not None:
            required_mode: GoalOutputMode = (
                "body_action"
                if self.resource_responsibility.kind == "physical_object"
                else "capability_work"
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
    """Small discriminated semantic DTO returned by Goal Association."""

    model_config = ConfigDict(extra="forbid")

    decision: GoalAssociationDecision | None = None
    associations: list[GoalAssociationModelAssociation] = Field(default_factory=list)
    new_goals: list[GoalAssociationModelGoal] = Field(default_factory=list)
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
        if decision not in {"associate", "create_goals"}:
            if normalized.get("associations"):
                decision = "associate"
            else:
                decision = "create_goals"
        elif (
            decision == "create_goals"
            and not normalized.get("new_goals")
            and normalized.get("associations")
        ):
            decision = "associate"
        elif (
            decision == "associate"
            and not normalized.get("associations")
            and normalized.get("new_goals")
        ):
            decision = "create_goals"
        normalized["decision"] = decision
        if decision == "create_goals":
            normalized["associations"] = []
        else:
            # ``decision`` is the sole semantic branch authority. Decoder-small
            # models can populate an inactive branch even after selecting
            # association; discard it mechanically just as the create branch
            # already discards inactive associations. It must never double-map one
            # Responsibility and exhaust the one allowed DTO repair.
            normalized["new_goals"] = []
        return normalized

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelOutput":
        if self.decision == "associate" and not self.associations:
            raise ValueError("decision=associate requires associations")
        if self.decision == "create_goals" and not self.new_goals:
            raise ValueError("decision=create_goals requires new_goals")
        return self


class GoalResponsibilityCoverageItem(BaseModel):
    """One independently audited semantic fragment from the authoritative turn.

    The audit does not create Goals.  It explains how current user meaning is
    accounted for by already proposed Goal candidates so the Host can reject a
    structurally incomplete or over-merged segmentation without interpreting the
    user's words itself.
    """

    model_config = ConfigDict(extra="forbid")

    source_excerpt: str = Field(min_length=1, max_length=500)
    role: Literal["responsibility", "constraint", "context", "framing"]
    coverage: Literal["covered", "missing", "clarification_required", "representation_mismatch"]
    independently_satisfiable: bool = False
    candidate_goal_indices: list[int] = Field(default_factory=list, max_length=8)
    required_goal_shape: Literal[
        "ordinary",
        "information_resource",
        "physical_resource",
        "persistent_effect",
    ] = "ordinary"
    required_information_domain: Literal[
        "none",
        "local_clock",
        "weather_forecast",
        "external_grounded_information",
        "direct_environment_perception",
        "private_runtime_information",
    ] = "none"
    required_output_mode: Literal[
        "none",
        "speech",
        "styled_speech",
        "recitation",
        "singing",
        "humming",
        "nonverbal_vocalization",
        "body_action",
        "media_playback",
        "capability_work",
        "other",
    ] = "none"

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("candidate_goal_indices")
    @classmethod
    def unique_goal_indices(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("candidate_goal_indices must be unique")
        return value


    @model_validator(mode="after")
    def validate_shape(self) -> "GoalResponsibilityCoverageItem":
        if self.required_goal_shape != "ordinary" and self.role != "responsibility":
            raise ValueError(
                "required_goal_shape is valid only on responsibility coverage items"
            )
        if self.required_goal_shape == "information_resource":
            if self.required_information_domain == "none":
                raise ValueError(
                    "information_resource coverage requires an information domain"
                )
        elif self.required_information_domain != "none":
            raise ValueError(
                "required_information_domain is valid only for an information resource"
            )
        if self.role != "responsibility" and self.independently_satisfiable:
            raise ValueError(
                "only a responsibility may be independently_satisfiable"
            )
        if self.role != "responsibility" and self.required_output_mode != "none":
            raise ValueError(
                "required_output_mode is valid only on responsibility coverage items"
            )
        if self.role in {"context", "framing"}:
            if self.coverage != "covered" or self.candidate_goal_indices:
                raise ValueError(
                    "context and framing are acknowledged without Goal ownership"
                )
            return self
        if self.coverage in {"covered", "clarification_required"}:
            if not self.candidate_goal_indices:
                raise ValueError(
                    "covered or clarification-required responsibility/constraint "
                    "requires provisional Goal ownership"
                )
            if self.role == "responsibility" and len(self.candidate_goal_indices) != 1:
                raise ValueError(
                    "one responsibility must map to exactly one Goal candidate"
                )
        elif self.coverage == "representation_mismatch":
            if not self.candidate_goal_indices:
                raise ValueError(
                    "representation_mismatch requires the mismatched Goal candidate"
                )
            if self.role == "responsibility" and len(self.candidate_goal_indices) != 1:
                raise ValueError(
                    "one mismatched responsibility must identify exactly one Goal candidate"
                )
        elif self.candidate_goal_indices:
            raise ValueError(
                "missing meaning cannot claim Goal ownership"
            )
        return self



class GoalResponsibilityCoverageCertificate(BaseModel):
    """Authority-ephemeral proof over one candidate Goal set.

    The model authors only source-grounded item judgments.  The Host derives the
    verdict and every unjustified candidate index, so neither can drift or need a
    repair call.
    """

    model_config = ConfigDict(extra="forbid")

    responsibility_items: list[GoalResponsibilityCoverageItem] = Field(
        min_length=1,
        max_length=8,
    )
    supporting_items: list[GoalResponsibilityCoverageItem] = Field(
        max_length=16,
    )
    reason_summary: str = Field(min_length=1, max_length=1200)

    @property
    def items(self) -> list[GoalResponsibilityCoverageItem]:
        return [*self.responsibility_items, *self.supporting_items]

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_material_evidence(self) -> "GoalResponsibilityCoverageCertificate":
        if any(item.role != "responsibility" for item in self.responsibility_items):
            raise ValueError(
                "responsibility_items accepts only role=responsibility"
            )
        if any(item.role == "responsibility" for item in self.supporting_items):
            raise ValueError(
                "supporting_items accepts only constraint, context, or framing roles"
            )
        return self

# ---------------------------------------------------------------------------
# Goal Association model-contract mechanics
# ---------------------------------------------------------------------------
# These helpers shape, normalize, and mechanically validate the model-facing GA
# representation. They do not invoke a model, read or mutate canonical Goal state,
# authorize Work, or commit continuity decisions. GoalAssociationResolver remains
# the single semantic continuity authority.

def normalize_optional_referent_updates(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop only semantically unusable optional referent-index updates.

    Referent focus changes, retirements, and introductions with actual entity
    content remain contract-authoritative and still fail closed. A correction
    without any supplied target referent cannot update the discourse index; the
    canonical Goal association and coverage audit remain responsible for the
    actual correction meaning.
    A model-added ``introduce`` item with neither an entity type nor canonical
    value cannot ground any Goal binding and must not discard otherwise valid
    Goals.
    """

    normalized = copy.deepcopy(raw)
    updates = normalized.get("referent_updates")
    if not isinstance(updates, list):
        return normalized, []
    kept: list[Any] = []
    dropped: list[dict[str, Any]] = []
    for index, item in enumerate(updates):
        if not isinstance(item, dict):
            kept.append(item)
            continue
        operation = str(item.get("operation") or "").strip()
        entity_type = str(item.get("entity_type") or "").strip()
        canonical_value = str(item.get("canonical_value") or "").strip()
        target_referent_ids = item.get("target_referent_ids") or []
        target_goal_ids = item.get("target_goal_ids") or []
        if (
            operation == "introduce"
            and not entity_type
            and not canonical_value
            and not target_referent_ids
            and not target_goal_ids
        ):
            dropped.append(
                {
                    "path": f"referent_updates[{index}]",
                    "operation": "introduce",
                    "reason": "missing_entity_type_and_canonical_value",
                }
            )
            continue
        if operation == "correct" and not target_referent_ids:
            dropped.append(
                {
                    "path": f"referent_updates[{index}]",
                    "operation": "correct",
                    "reason": "missing_target_referent_ids",
                }
            )
            continue
        kept.append(item)
    normalized["referent_updates"] = kept
    return normalized, dropped


def normalize_resource_binding_branches(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize model content from a resource Goal's inactive binding branch.

    Resource Goals have one semantic owner: ``resource_responsibility``. Some
    structured-output models nevertheless populate the mutually exclusive top-
    level ``bindings`` branch. Move nonduplicate model-authored bindings into the
    discriminated resource owner before clearing the inactive branch. This is
    mechanical DTO normalization: no value is inferred or rewritten, and the
    independent source-grounded coverage certificate still decides whether each
    migrated fact belongs to the Responsibility.
    """

    normalized = copy.deepcopy(raw)
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, []

    dropped: list[dict[str, Any]] = []
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        top_level = goal.get("bindings")
        if not isinstance(top_level, list):
            top_level = []
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict):
            continue
        kind = str(resource.get("kind") or "").strip()
        if kind not in {"information", "physical_object"}:
            continue
        if kind == "information":
            target = resource.get("query_scope")
        else:
            source = resource.get("source")
            target = (
                source.get("acquisition_bindings")
                if isinstance(source, dict)
                else None
            )
        physical_source_unknown = bool(
            kind == "physical_object"
            and isinstance(resource.get("source"), dict)
            and resource["source"].get("status") != "known"
        )
        has_inactive_physical_grounding = bool(
            physical_source_unknown
            and isinstance(target, list)
            and target
        )
        if physical_source_unknown and (top_level or has_inactive_physical_grounding):
            # `status` is the discriminant: unknown/provider-resolved sources
            # cannot own acquisition grounding. Clear model content from that
            # inactive branch so the independent semantic coverage audit can
            # decide whether the entire resource wrapper was justified. Never
            # flip unknown to known or reinterpret body-motion parameters as an
            # object-acquisition location.
            source = resource["source"]
            existing = source.pop("acquisition_bindings", [])
            goal["bindings"] = []
            dropped.append(
                {
                    "path": f"new_goals[{index}].bindings",
                    "resource_kind": kind,
                    "binding_count": len(top_level),
                    "migrated_count": 0,
                    "inactive_acquisition_binding_count": (
                        len(existing) if isinstance(existing, list) else 0
                    ),
                    "reason": "unknown_physical_source_has_no_grounding_branch",
                }
            )
            continue
        if not top_level:
            continue
        if not isinstance(target, list):
            target = []
            if kind == "information":
                resource["query_scope"] = target
            elif isinstance(resource.get("source"), dict):
                resource["source"]["acquisition_bindings"] = target
        fingerprints = {
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in target
        }
        migrated_count = 0
        for binding in top_level:
            fingerprint = json.dumps(
                binding,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if fingerprint in fingerprints:
                continue
            target.append(copy.deepcopy(binding))
            fingerprints.add(fingerprint)
            migrated_count += 1
        goal["bindings"] = []
        dropped.append(
            {
                "path": f"new_goals[{index}].bindings",
                "resource_kind": kind,
                "binding_count": len(top_level),
                "migrated_count": migrated_count,
                "reason": "normalized_into_active_resource_binding_branch",
            }
        )
    return normalized, dropped


def normalize_optional_resource_quantity(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop only malformed optional quantity scalars before validation.

    No replacement quantity is inferred. Responsibility coverage still proves
    conservation of any source-grounded quantity, so removing decoder noise
    cannot silently erase a quantity the human actually supplied.
    """

    normalized = copy.deepcopy(raw)
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, []
    dropped: list[dict[str, Any]] = []
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict) or "quantity" not in resource:
            continue
        value = resource.get("quantity")
        if value is None or value == "":
            continue
        try:
            if not isinstance(value, str):
                raise ValueError("quantity is not a string")
            _validate_model_resource_quantity(value.strip())
        except (TypeError, ValueError):
            resource.pop("quantity", None)
            dropped.append(
                {
                    "path": (
                        f"new_goals[{index}].resource_responsibility.quantity"
                    ),
                    "reason": "invalid_optional_quantity_scalar",
                    "input_type": type(value).__name__,
                }
            )
    return normalized, dropped


def restore_missing_goal_descriptions(
    raw: dict[str, Any],
    *,
    request: CognitiveWorkRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore a mechanically omitted description from its exact source outcome.

    The source Responsibility remains the semantic authority.  Recovery is
    permitted only when the candidate names exactly one admitted local_ref and
    its description is absent or blank; no wording is generated or inferred.
    Responsibility/output-mode conservation and the independent coverage audit
    still validate the resulting Goal.
    """

    normalized = copy.deepcopy(raw)
    outcomes = {
        item.local_ref: item.outcome
        for item in request.responsibilities
        if item.local_ref and item.outcome
    }
    recovered: list[dict[str, Any]] = []
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, recovered
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        if str(goal.get("description") or "").strip():
            continue
        source_refs = goal.get("source_responsibility_refs")
        if not isinstance(source_refs, list) or len(source_refs) != 1:
            continue
        source_ref = str(source_refs[0] or "").strip()
        outcome = outcomes.get(source_ref)
        if not outcome:
            continue
        goal["description"] = outcome
        recovered.append(
            {
                "path": f"new_goals[{index}].description",
                "source_responsibility_ref": source_ref,
                "semantic_value_unchanged": True,
            }
        )
    return normalized, recovered


def drop_ungrounded_resource_query_locations(
    raw: dict[str, Any],
    *,
    request: CognitiveWorkRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop an invented optional query location without choosing a replacement.

    This restores Responsibility conservation before validation.  Coverage
    remains responsible for rejecting the Goal when location was actually
    material, so the normalization cannot silently satisfy missing meaning.
    """

    normalized = copy.deepcopy(raw)
    authoritative_turn = " ".join(request.text.strip().split()).casefold()
    grounded_values = {
        " ".join(str(value).strip().split()).casefold()
        for responsibility in request.responsibilities
        for value in responsibility.bindings.values()
        if str(value).strip()
    }
    resolved_values = {
        " ".join(str(item.get("resolved_value") or "").strip().split()).casefold()
        for item in normalized.get("resolved_references") or []
        if isinstance(item, dict)
        and str(item.get("resolved_value") or "").strip()
    }
    location_types = {
        "address",
        "city",
        "country",
        "county",
        "location",
        "place",
        "region",
    }
    dropped: list[dict[str, Any]] = []
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, dropped
    for goal_index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict) or resource.get("kind") != "information":
            continue
        query_scope = resource.get("query_scope")
        if not isinstance(query_scope, list):
            continue
        kept: list[Any] = []
        for binding_index, binding in enumerate(query_scope):
            if not isinstance(binding, dict):
                kept.append(binding)
                continue
            name = "_".join(
                str(binding.get("name") or "")
                .strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            entity_type = "_".join(
                str(binding.get("entity_type") or "")
                .strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            value = " ".join(
                str(binding.get("value") or "").strip().split()
            ).casefold()
            is_location = name == "location" or entity_type in location_types
            grounded = bool(
                value
                and (
                    value in authoritative_turn
                    or value in grounded_values
                    or value in resolved_values
                )
            )
            if (
                not is_location
                or str(binding.get("referent_id") or "").strip()
                or grounded
            ):
                kept.append(binding)
                continue
            dropped.append(
                {
                    "path": (
                        f"new_goals[{goal_index}].resource_responsibility."
                        f"query_scope[{binding_index}]"
                    ),
                    "name": str(binding.get("name") or ""),
                    "entity_type": str(binding.get("entity_type") or ""),
                    "value": str(binding.get("value") or ""),
                    "reason": "not_entailed_by_turn_responsibility_or_referent",
                }
            )
        resource["query_scope"] = kept
    return normalized, dropped


def normalize_grounded_generic_location_types(
    raw: dict[str, Any],
    *,
    request: CognitiveWorkRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Canonicalize only a source-grounded location with a generic DTO type.

    The model already owns the semantic field name and exact value. This adapter
    changes neither; it replaces only the mechanically non-semantic ``string``/
    ``text``/``entity`` type label after the value is proven by the authoritative
    turn, GI bindings, or an admitted resolved reference.
    """

    normalized = copy.deepcopy(raw)
    authoritative_turn = " ".join(request.text.strip().split()).casefold()
    grounded_values = {
        " ".join(str(value).strip().split()).casefold()
        for responsibility in request.responsibilities
        for value in responsibility.bindings.values()
        if str(value).strip()
    }
    grounded_values.update(
        " ".join(str(item.get("resolved_value") or "").strip().split()).casefold()
        for item in normalized.get("resolved_references") or []
        if isinstance(item, dict)
        and str(item.get("resolved_value") or "").strip()
    )
    generic_types = {"entity", "string", "text"}
    repaired: list[dict[str, Any]] = []
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, repaired
    for goal_index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        surfaces: list[tuple[str, Any]] = [("bindings", goal.get("bindings"))]
        resource = goal.get("resource_responsibility")
        if isinstance(resource, dict):
            if resource.get("kind") == "information":
                surfaces.append(("resource.query_scope", resource.get("query_scope")))
            source = resource.get("source")
            if isinstance(source, dict):
                surfaces.append(
                    (
                        "resource.source.acquisition_bindings",
                        source.get("acquisition_bindings"),
                    )
                )
        for surface_name, bindings in surfaces:
            if not isinstance(bindings, list):
                continue
            for binding_index, binding in enumerate(bindings):
                if not isinstance(binding, dict):
                    continue
                name = "_".join(
                    str(binding.get("name") or "")
                    .strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                entity_type = "_".join(
                    str(binding.get("entity_type") or "")
                    .strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                value = " ".join(
                    str(binding.get("value") or "").strip().split()
                ).casefold()
                if (
                    name != "location"
                    or entity_type not in generic_types
                    or not value
                    or (
                        value not in authoritative_turn
                        and value not in grounded_values
                    )
                ):
                    continue
                binding["entity_type"] = "place"
                repaired.append(
                    {
                        "path": (
                            f"new_goals[{goal_index}].{surface_name}"
                            f"[{binding_index}].entity_type"
                        ),
                        "from": entity_type,
                        "to": "place",
                        "value_unchanged": True,
                    }
                )
    return normalized, repaired


def action_collection_bindings(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
) -> list[str]:
    rejected: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        for binding in goal.semantic_bindings:
            entity_type = "_".join(
                binding.entity_type.strip().casefold().replace("-", "_").split()
            )
            if "action" in entity_type and (
                "list" in entity_type
                or "set" in entity_type
                or "group" in entity_type
                or "collection" in entity_type
            ):
                rejected.append(
                    f"new_goals[{goal_index}].bindings[{binding.name}]="
                    f"{binding.entity_type}"
                )
    return rejected


def responsibility_output_mode_conflicts(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    *,
    request: CognitiveWorkRequest,
) -> list[str]:
    expected = {
        item.local_ref: item.output_mode
        for item in request.responsibilities
        if item.output_mode != "unspecified"
    }
    conflicts: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        for source_ref in goal.source_responsibility_refs:
            required = expected.get(source_ref)
            if required is None or goal.output_mode == required:
                continue
            conflicts.append(
                f"new_goals[{goal_index}] source_ref={source_ref} "
                f"expected={required} actual={goal.output_mode}"
            )
    return conflicts


def binding_semantic_contract_conflicts(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
) -> list[str]:
    """Reject contradictions between model-authored canonical binding fields.

    This does not infer a parameter from user wording. It only prevents a DTO
    from calling the same binding a different or non-canonical parameter kind,
    such as ``name=distance`` with ``entity_type=quantity`` or the generic
    ``measurement`` label. The decoder already exposes this exact invariant;
    runtime validation keeps it fail-closed when a provider ignores the clause.
    """

    categories = {
        "distance": {"distance"},
        "direction": {"direction"},
        "quantity": {
            "amount",
            "count",
            "item_count",
            "quantity",
            "quantity_binding",
            "resource_count",
            "resource_quantity",
        },
    }
    category_by_token = {
        token: category
        for category, tokens in categories.items()
        for token in tokens
    }
    conflicts: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        for binding_index, binding in enumerate(goal.semantic_bindings):
            name = "_".join(
                binding.name.strip().casefold().replace("-", "_").split()
            )
            entity_type = "_".join(
                binding.entity_type.strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            name_category = category_by_token.get(name)
            type_category = category_by_token.get(entity_type)
            if name_category is not None and type_category != name_category:
                conflicts.append(
                    f"new_goals[{goal_index}].bindings[{binding_index}]="
                    f"{binding.name}/{binding.entity_type}"
                )
    return conflicts


def resource_source_binding_contract_conflicts(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
) -> list[str]:
    """Report invalid model-declared links from a resource to source evidence.

    This is a typed integrity check over fields the model already authored. It
    does not infer a source, binding, parameter, or value from user wording.
    It prevents the resource's identity, requested amount, recipient, or delivery
    mode from being relabelled as the place/source from which that resource should
    be acquired. A focused model revision remains responsible for semantic repair.
    """

    non_source_names = {
        "amount",
        "count",
        "delivery_mode",
        "delivery_recipient",
        "desired_item",
        "item",
        "item_count",
        "object",
        "quantity",
        "recipient",
        "resource",
        "resource_count",
        "resource_description",
        "resource_identity",
        "resource_kind",
        "resource_quantity",
        "target_item",
    }
    identity_or_quantity_types = {
        "amount",
        "count",
        "item",
        "object",
        "physical_object",
        "quantity",
        "resource",
        "resource_identity",
        "resource_kind",
    }
    explicit_source_names = {
        "direction",
        "distance",
        "location",
        "origin",
        "path",
        "place",
        "provider",
        "route",
        "source",
        "source_location",
        "source_provider",
        "spatial_offset",
    }
    spatial_source_types = {
        "direction",
        "distance",
        "location",
        "place",
        "relative_location",
        "route",
    }

    conflicts: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        resource = goal.resource_responsibility
        if resource is None:
            continue
        if resource.kind != "physical_object":
            continue
        for binding in resource.source.acquisition_bindings:
            source_name = binding.name
            normalized_name = "_".join(
                binding.name.strip().casefold().replace("-", "_").split()
            )
            normalized_type = "_".join(
                binding.entity_type.strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            if (
                normalized_name in non_source_names
                or normalized_name not in explicit_source_names
                or normalized_type not in spatial_source_types
                or (
                    normalized_type in identity_or_quantity_types
                    and normalized_name not in explicit_source_names
                )
            ):
                conflicts.append(
                    f"new_goals[{goal_index}].resource_responsibility."
                    f"source.acquisition_bindings[{source_name}]="
                    f"non_source_semantics({binding.name}/{binding.entity_type})"
                )
    return conflicts


def source_grounded_binding_coverage_conflicts(
    model_output: (
        GoalAssociationModelOutput
        | GoalSegmentationModelOutput
        | list[GoalAssociationModelGoal]
    ),
    *,
    request: CognitiveWorkRequest,
) -> list[str]:
    """Conserve direct GI material values on their one typed Goal surface.

    Goal Interpretation already owns whether a value is material WHAT. This
    check does not infer a parameter kind from the utterance; it follows the
    model-authored source_responsibility_refs and verifies that directly
    source-grounded values did not disappear. The Goal description is the
    authoritative owner of the action/effect itself, while bindings own its
    material parameters; an exact source action retained in that description
    therefore does not need a redundant ``action`` binding.
    Context-normalized values absent from the literal turn remain governed by
    their dedicated temporal/referent contracts.
    """

    authoritative_turn = " ".join(request.text.strip().casefold().split())
    expected_by_ref: dict[str, set[tuple[str, str]]] = {}

    def scalar_values(value: Any) -> set[str]:
        if isinstance(value, str):
            normalized = " ".join(value.strip().casefold().split())
            return {normalized} if normalized else set()
        if isinstance(value, dict):
            return {
                item
                for nested in value.values()
                for item in scalar_values(nested)
            }
        if isinstance(value, (list, tuple)):
            return {
                item
                for nested in value
                for item in scalar_values(nested)
            }
        return set()

    for responsibility in request.responsibilities:
        expected_by_ref[responsibility.local_ref] = {
            (
                "_".join(str(name).strip().casefold().replace("-", "_").split()),
                value,
            )
            for name, raw_value in responsibility.bindings.items()
            for value in scalar_values(raw_value)
            if value in authoritative_turn
        }

    conflicts: list[str] = []
    goals = model_output if isinstance(model_output, list) else model_output.new_goals
    for goal_index, goal in enumerate(goals):
        expected_pairs = {
            pair
            for source_ref in goal.source_responsibility_refs
            for pair in expected_by_ref.get(source_ref, set())
        }
        if not expected_pairs:
            continue
        resource = goal.resource_responsibility
        canonicalized_binding_names: set[str] = set()
        if resource is None:
            actual = {
                " ".join(binding.value.strip().casefold().split())
                for binding in goal.semantic_bindings
            }
            canonicalized_binding_names = {
                "_".join(
                    binding.name.strip().casefold().replace("-", "_").split()
                )
                for binding in goal.semantic_bindings
                if binding.entity_type.casefold() == "speed"
            }
            normalized_description = " ".join(
                goal.description.strip().casefold().split()
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"action", "activity", "effect", "outcome"}
                and value in normalized_description
            )
        elif resource.kind == "information":
            actual = {
                " ".join(binding.value.strip().casefold().split())
                for binding in resource.query_scope
            }
            actual.update(
                scalar_values(resource.quantity)
            )
            actual.update(scalar_values(resource.recipient.description))
            if resource.source.status == "known":
                actual.update(scalar_values(resource.source.source_name))
        else:
            actual = {
                " ".join(binding.value.strip().casefold().split())
                for binding in resource.source.acquisition_bindings
            }
            normalized_description = " ".join(
                goal.description.strip().casefold().split()
            )
            normalized_resource_description = " ".join(
                resource.description.strip().casefold().split()
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"action", "activity", "effect", "outcome"}
                and value in normalized_description
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name
                in {
                    "desired_item",
                    "item",
                    "object",
                    "resource",
                    "resource_identity",
                    "target_item",
                }
                and value in normalized_resource_description
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"amount", "count", "quantity", "resource_quantity"}
                and value in scalar_values(resource.quantity)
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"recipient", "delivery_recipient"}
                and value in scalar_values(resource.recipient.description)
            )
        for _, missing in sorted(
            pair
            for pair in expected_pairs
            if pair[1] not in actual
            and pair[0] not in canonicalized_binding_names
        ):
            conflicts.append(
                f"new_goals[{goal_index}] source_refs="
                f"{','.join(goal.source_responsibility_refs)} missing={missing!r}"
            )
    return conflicts


def non_verbatim_explicit_location_bindings(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    *,
    request: CognitiveWorkRequest,
) -> list[str]:
    """Reject ungrounded rewrites of directly named locations.

    Indirect references keep their resolved canonical value and provenance.
    A new location without referent provenance, however, came from the current
    explicit user turn and must remain source-grounded user language after
    whitespace normalization.  This prevents a model translation or
    transliteration from silently changing which real place a provider sees.
    """

    authoritative_turn = " ".join(request.text.strip().split()).casefold()
    resolved_values = {
        (item.entity_type.casefold(), item.resolved_value.casefold())
        for item in model_output.resolved_references
    }
    rejected: list[str] = []
    canonical_location_types = {
        "address",
        "city",
        "country",
        "county",
        "location",
        "place",
        "relative_location",
        "region",
    }
    for goal_index, goal in enumerate(model_output.new_goals):
        for binding in goal.semantic_bindings:
            name = "_".join(
                binding.name.strip().casefold().replace("-", "_").split()
            )
            entity_type = "_".join(
                binding.entity_type.strip().casefold().replace("-", "_").split()
            )
            if name != "location" and entity_type not in {
                "address",
                "city",
                "country",
                "county",
                "location",
                "place",
                "region",
            }:
                continue
            if name == "location" and entity_type not in canonical_location_types:
                rejected.append(
                    f"new_goals[{goal_index}].bindings[{binding.name}]="
                    f"non_location_semantics({binding.entity_type!r})"
                )
                continue
            if binding.referent_id or (
                binding.entity_type.casefold(),
                binding.value.casefold(),
            ) in resolved_values:
                continue
            value = " ".join(binding.value.strip().split()).casefold()
            if value not in authoritative_turn:
                rejected.append(
                    f"new_goals[{goal_index}].bindings[{binding.name}]="
                    f"{binding.value!r}"
                )
    return rejected


def validation_error_json(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        payload: Any = exc.errors(include_url=False)
    else:
        payload = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
    return bounded_json(payload, 6000)


def goal_association_response_schema(
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
    candidate_goals: list[dict[str, Any]],
    discourse_referents: list[dict[str, Any]],
    *,
    responsibility_count: int | None = None,
    responsibility_refs: list[str] | None = None,
    responsibility_output_modes: dict[str, str] | None = None,
    responsibility_fresh_evidence_refs: set[str] | None = None,
    responsibility_bindings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    schema = copy.deepcopy(output_type.model_json_schema())
    active_ids = [
        " ".join(str(item.get("goal_id") or "").strip().split())
        for item in candidate_goals
        if " ".join(str(item.get("goal_id") or "").strip().split())
    ]
    referent_ids = [
        " ".join(str(item.get("referent_id") or "").strip().split())
        for item in discourse_referents
        if " ".join(str(item.get("referent_id") or "").strip().split())
    ]
    gap_ids = [
        " ".join(str(gap.get("gap_id") or "").strip().split())
        for goal in candidate_goals
        for gap in (goal.get("open_information_gaps") or [])
        if isinstance(gap, dict)
        and " ".join(str(gap.get("gap_id") or "").strip().split())
    ]
    responsibility_refs = list(responsibility_refs or [])
    responsibility_output_modes = dict(responsibility_output_modes or {})
    responsibility_fresh_evidence_refs = set(
        responsibility_fresh_evidence_refs or set()
    )
    responsibility_bindings = {
        str(source_ref): dict(bindings)
        for source_ref, bindings in (responsibility_bindings or {}).items()
    }
    properties = schema.get("properties", {})
    new_goals = properties.get("new_goals")
    if isinstance(new_goals, dict):
        new_goals["maxItems"] = (
            8
            if responsibility_count is None
            else min(8, max(0, int(responsibility_count)))
        )
    if not referent_ids:
        resolved_references = properties.get("resolved_references")
        if isinstance(resolved_references, dict):
            resolved_references["maxItems"] = 0

    def constrain(node: Any) -> None:
        if isinstance(node, dict):
            node_properties = node.get("properties")
            if isinstance(node_properties, dict):
                source_refs = node_properties.get("source_responsibility_refs")
                if isinstance(source_refs, dict):
                    required_fields = list(node.get("required") or [])
                    if "source_responsibility_refs" not in required_fields:
                        required_fields.append("source_responsibility_refs")
                    node["required"] = required_fields
                    source_refs["items"] = {
                        "type": "string",
                        "enum": responsibility_refs,
                    }
                    source_refs["uniqueItems"] = True
                    if responsibility_refs:
                        source_refs["minItems"] = 1
                    if "relationship" in node_properties:
                        # Association confidence is model evidence used by the
                        # fail-closed commit threshold. A DTO default of 0.0 is
                        # not evidence and must never silently discard an
                        # otherwise correct continuity decision.
                        required_fields = list(node.get("required") or [])
                        for field in ("target_goal_ids", "confidence"):
                            if field not in required_fields:
                                required_fields.append(field)
                        node["required"] = required_fields
                related_field = node_properties.get("related_goal_ids")
                if isinstance(related_field, dict):
                    items = related_field.get("items")
                    if isinstance(items, dict):
                        if active_ids:
                            items["type"] = "string"
                            items["enum"] = active_ids
                        else:
                            related_field["maxItems"] = 0
                target_ids = node_properties.get("target_goal_ids")
                if isinstance(target_ids, dict):
                    target_ids["items"] = {
                        "type": "string",
                        "enum": active_ids,
                    }
                    target_ids["uniqueItems"] = True
                    if "relationship" in node_properties and active_ids:
                        # Every association addresses retained Goal state.
                        # An empty array can never satisfy the DTO, so expose
                        # that mechanical fact to the structured decoder.
                        target_ids["minItems"] = 1
                target_referents = node_properties.get("target_referent_ids")
                if isinstance(target_referents, dict):
                    target_referents["items"] = {
                        "type": "string",
                        "enum": referent_ids,
                    }
                    target_referents["uniqueItems"] = True
                resolved_gaps = node_properties.get("resolved_gap_ids")
                if isinstance(resolved_gaps, dict):
                    if gap_ids:
                        resolved_gaps["items"] = {
                            "type": "string",
                            "enum": gap_ids,
                        }
                        resolved_gaps["uniqueItems"] = True
                    else:
                        resolved_gaps["maxItems"] = 0
                referent_id = node_properties.get("referent_id")
                if isinstance(referent_id, dict):
                    referent_id["type"] = "string"
                    referent_id["enum"] = ["", *referent_ids]
            if node.get("type") == "object":
                node["additionalProperties"] = False
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)
    goal_schema = schema.get("$defs", {}).get("GoalAssociationModelGoal")
    if isinstance(goal_schema, dict) and responsibility_refs:
        # Every writable Goal-semantic surface must be explicit in the
        # constrained model output. Defaults on these fields are Python DTO
        # conveniences, not permission for the model to drop GI-grounded
        # bindings or silently avoid deciding the resource branch.
        goal_required = list(
            dict.fromkeys(
                [
                    *(goal_schema.get("required") or []),
                    "source_responsibility_refs",
                    "description",
                    "output_mode",
                    "bindings",
                    "resource_responsibility",
                ]
            )
        )
        goal_schema["required"] = goal_required
        source_refs_schema = goal_schema.get("properties", {}).get(
            "source_responsibility_refs"
        )
        if isinstance(source_refs_schema, dict):
            source_refs_schema["minItems"] = 1
            source_refs_schema["maxItems"] = 1
        goal_properties = goal_schema.get("properties")
        branch_goal_properties = (
            copy.deepcopy(goal_properties)
            if isinstance(goal_properties, dict)
            else {}
        )

        def branch_properties(
            source_ref: str,
            *,
            resource_variant: Literal[
                "ordinary", "physical_object", "information", "unbounded"
            ],
        ) -> dict[str, Any]:
            """Return the complete, output-mode-compatible Goal surface.

            ``resource_responsibility`` is required so the decoder must make
            the resource decision explicitly, but Pydantic's default schema
            lists the object union before ``null``.  Ollama's constrained
            decoder consequently biased ordinary effects toward fabricated
            resources.  Keep semantic selection model-owned while removing
            impossible resource kinds and putting the ordinary ``null`` branch
            first.  ``body_action`` remains free to select a real physical
            acquisition, and ``capability_work`` remains free to select a real
            information responsibility.
            """

            properties = copy.deepcopy(branch_goal_properties)
            output_mode = responsibility_output_modes.get(source_ref)
            if resource_variant == "ordinary":
                properties["resource_responsibility"] = {"type": "null"}
                expected_bindings = [
                    (" ".join(str(name).strip().split()), str(value))
                    for name, value in responsibility_bindings.get(
                        source_ref, {}
                    ).items()
                    if " ".join(str(name).strip().split())
                    and "_".join(
                        str(name)
                        .strip()
                        .casefold()
                        .replace("-", "_")
                        .split()
                    )
                    not in {"action", "activity", "effect", "outcome"}
                ]
                if expected_bindings:
                    bindings_schema = copy.deepcopy(
                        properties.get("bindings") or {}
                    )
                    bindings_schema["minItems"] = len(expected_bindings)
                    bindings_schema["maxItems"] = len(expected_bindings)
                    binding_item_template = copy.deepcopy(
                        schema.get("$defs", {}).get(
                            "GoalAssociationModelBinding"
                        )
                        or {}
                    )
                    binding_branches: list[dict[str, Any]] = []
                    for name, value in expected_bindings:
                        binding_branch = copy.deepcopy(binding_item_template)
                        binding_properties = binding_branch.setdefault(
                            "properties", {}
                        )
                        binding_properties["name"] = {"const": name}
                        binding_properties["value"] = {"const": value}
                        binding_branch["required"] = list(
                            dict.fromkeys(
                                [
                                    *(binding_branch.get("required") or []),
                                    "name",
                                    "value",
                                    "entity_type",
                                    "confidence",
                                ]
                            )
                        )
                        binding_branches.append(binding_branch)
                    bindings_schema["items"] = {"oneOf": binding_branches}
                    bindings_schema["allOf"] = [
                        {
                            "contains": {
                                "type": "object",
                                "properties": {
                                    "name": {"const": name},
                                    "value": {"const": value},
                                },
                                "required": ["name", "value"],
                            },
                            "minContains": 1,
                        }
                        for name, value in expected_bindings
                    ]
                    properties["bindings"] = bindings_schema
            elif resource_variant == "physical_object":
                properties["resource_responsibility"] = {
                    "$ref": (
                        "#/$defs/"
                        "GoalAssociationModelPhysicalResourceResponsibility"
                    )
                }
                properties["bindings"] = {
                    **copy.deepcopy(properties.get("bindings") or {}),
                    "maxItems": 0,
                }
            elif resource_variant == "information":
                properties["resource_responsibility"] = {
                    "$ref": (
                        "#/$defs/"
                        "GoalAssociationModelInformationResourceResponsibility"
                    )
                }
                properties["bindings"] = {
                    **copy.deepcopy(properties.get("bindings") or {}),
                    "maxItems": 0,
                }

            properties["source_responsibility_refs"] = {
                "const": [source_ref]
            }
            if output_mode is not None:
                properties["output_mode"] = {"const": output_mode}
            return properties

        def resource_variants(source_ref: str) -> list[str]:
            output_mode = responsibility_output_modes.get(source_ref)
            if source_ref in responsibility_fresh_evidence_refs:
                # GI already authored the fresh-evidence semantic fact. At the
                # trusted Goal boundary that fact has exactly one canonical
                # representation: information resource work. Keeping the
                # ordinary branch would silently downgrade evidence acquisition
                # to conversational speech.
                return ["information"]
            if output_mode == "body_action":
                return ["ordinary", "physical_object"]
            if output_mode == "capability_work":
                return ["ordinary", "information"]
            if output_mode is not None:
                return ["ordinary"]
            return ["unbounded"]

        goal_schema["oneOf"] = []
        for source_ref in responsibility_refs:
            for resource_variant in resource_variants(source_ref):
                goal_schema["oneOf"].append(
                    {
                        # Ollama's constrained decoder treats the selected
                        # oneOf object branch as the active production surface.
                        # Repeat the complete writable Goal surface here, not
                        # only the discriminants, so branch-local required
                        # fields can actually be generated. Resource-capable
                        # modes use complete cross-product branches so an
                        # ordinary Goal cannot also populate a resource object.
                        "properties": branch_properties(
                            source_ref,
                            resource_variant=resource_variant,
                        ),
                        # Some constrained decoders treat a nested oneOf branch
                        # as the active object production surface rather than
                        # combining its required list with the parent object.
                        "required": list(
                            dict.fromkeys(
                                [
                                    *goal_required,
                                    "source_responsibility_refs",
                                    *(
                                        ["output_mode"]
                                        if source_ref
                                        in responsibility_output_modes
                                        else []
                                    ),
                                ]
                            )
                        ),
                    }
                )
    properties = schema.setdefault("properties", {})
    required = list(schema.get("required") or [])
    if output_type is GoalSegmentationModelOutput:
        properties["decision"] = {
            "type": "string",
            "enum": ["create_goals"],
        }
        ordered_required = [
            "decision",
            "new_goals",
            "referent_updates",
            "resolved_references",
            "confidence",
            "reason_summary",
        ]
    else:
        properties["decision"] = {
            "type": "string",
            "enum": ["associate", "create_goals"],
        }
        ordered_required = [
            "decision",
            "associations",
            "new_goals",
            "referent_updates",
            "resolved_references",
            "confidence",
            "reason_summary",
        ]
    if responsibility_refs:
        def contains_source_ref(source_ref: str) -> dict[str, Any]:
            return {
                "contains": {
                    "type": "object",
                    "properties": {
                        "source_responsibility_refs": {
                            "type": "array",
                            "contains": {"const": source_ref},
                            "minContains": 1,
                            "maxContains": 1,
                        }
                    },
                    "required": ["source_responsibility_refs"],
                },
                "minContains": 1,
                "maxContains": 1,
            }

        new_goal_conservation = {
            "minItems": len(responsibility_refs),
            "maxItems": len(responsibility_refs),
            "allOf": [
                contains_source_ref(source_ref)
                for source_ref in responsibility_refs
            ],
        }
        if output_type is GoalSegmentationModelOutput:
            # With no retained Goal candidate, every GI Responsibility must
            # become exactly one new Goal. Encode the already-enforced Host
            # invariant in the decoder so contract repair cannot emit r1,r1
            # for an r1,r2 turn. This is identity conservation, not semantic
            # reassociation.
            properties["new_goals"].update(new_goal_conservation)
        else:
            # Goal Association owns the branch choice. Once it chooses
            # create_goals, associations are inactive and every Responsibility
            # necessarily belongs to the new-goal branch. Conversely, an
            # association branch must conserve each supplied ref exactly once.
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {"decision": {"const": "create_goals"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {
                            "associations": {"maxItems": 0},
                            "new_goals": new_goal_conservation,
                        }
                    },
                    "else": {
                        "properties": {
                            "new_goals": {"maxItems": 0},
                            "associations": {
                                "minItems": 1,
                                "allOf": [
                                    contains_source_ref(source_ref)
                                    for source_ref in responsibility_refs
                                ],
                            },
                        }
                    },
                }
            )

    schema["required"] = list(dict.fromkeys([*ordered_required, *required]))
    schema.pop("oneOf", None)
    schema.pop("anyOf", None)
    return resource_semantic_contract_response_schema(
        binding_semantic_contract_response_schema(
            schema
        )
    )


def binding_semantic_contract_response_schema(
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    """Expose the existing canonical binding invariant to constrained decoding."""

    schema = copy.deepcopy(response_schema)
    binding_schema = schema.get("$defs", {}).get(
        "GoalAssociationModelBinding"
    )
    if not isinstance(binding_schema, dict):
        return schema
    categories = {
        "distance": ["distance"],
        "direction": ["direction"],
        "quantity": [
            "amount",
            "count",
            "item_count",
            "quantity",
            "quantity_binding",
            "resource_count",
            "resource_quantity",
        ],
    }
    clauses = binding_schema.setdefault("allOf", [])
    for names in categories.values():
        clauses.append(
            {
                "if": {
                    "properties": {"name": {"enum": names}},
                    "required": ["name"],
                },
                "then": {
                    "properties": {"entity_type": {"enum": names}},
                    "required": ["entity_type"],
                },
            }
        )
    clauses.append(
        {
            "if": {
                "properties": {"entity_type": {"const": "speed"}},
                "required": ["entity_type"],
            },
            "then": {
                "properties": {
                    "value": {
                        "anyOf": [
                            {"enum": ["slow", "normal", "quick"]},
                            {"pattern": r".*[0-9].*"},
                        ]
                    }
                },
                "required": ["value"],
            },
        }
    )
    return schema


def resource_semantic_contract_response_schema(
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    """Expose single-owner resource kinds and completion modes to decoding."""

    schema = copy.deepcopy(response_schema)
    definitions = schema.get("$defs", {})
    goal_schema = definitions.get("GoalAssociationModelGoal")
    if isinstance(goal_schema, dict):
        clauses = goal_schema.setdefault("allOf", [])
        for resource_kind, output_mode in (
            ("physical_object", "body_action"),
            ("information", "capability_work"),
        ):
            clauses.append(
                {
                    "if": {
                        "properties": {
                            "resource_responsibility": {
                                "type": "object",
                                "properties": {"kind": {"enum": [resource_kind]}},
                                "required": ["kind"],
                            }
                        },
                        "required": ["resource_responsibility"],
                    },
                    "then": {
                        "properties": {"output_mode": {"enum": [output_mode]}},
                        "required": ["output_mode"],
                    },
                }
            )

    physical_source = definitions.get("GoalAssociationModelPhysicalSource")
    if isinstance(physical_source, dict):
        physical_source.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"status": {"enum": ["known"]}},
                    "required": ["status"],
                },
                "then": {
                    "properties": {"acquisition_bindings": {"minItems": 1}}
                },
            }
        )

    information_source = definitions.get("GoalAssociationModelInformationSource")
    if isinstance(information_source, dict):
        information_source.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"status": {"enum": ["known"]}},
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {"source_name": {"minLength": 1}}
                    },
                },
                {
                    "if": {
                        "properties": {
                            "status": {"enum": ["unknown", "provider_resolved"]}
                        },
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {"source_name": {"maxLength": 0}}
                    },
                },
            ]
        )
    return schema


def responsibility_coverage_required(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    *,
    request: CognitiveWorkRequest,
) -> bool:
    """Audit every newly proposed Goal set and no association-only branch.

    This is a structural transition, not a Host semantic risk heuristic.
    Association-only results have no candidate new-Goal set for this certificate
    to prove.
    """

    del request
    return bool(model_output.new_goals)


def coverage_certificate_response_schema(
    candidate_goals: list[GoalAssociationModelGoal],
    *,
    authoritative_turn: str = "",
) -> dict[str, Any]:
    goal_count = len(candidate_goals)
    schema = copy.deepcopy(
        GoalResponsibilityCoverageCertificate.model_json_schema()
    )
    item_schema = schema.get("$defs", {}).get(
        "GoalResponsibilityCoverageItem"
    )
    if isinstance(item_schema, dict):
        item_schema["required"] = [
            "source_excerpt",
            "role",
            "coverage",
            "independently_satisfiable",
            "candidate_goal_indices",
            "required_goal_shape",
            "required_information_domain",
            "required_output_mode",
        ]
        indices = item_schema.get("properties", {}).get(
            "candidate_goal_indices"
        )
        surface = " ".join(str(authoritative_turn or "").strip().split())
        if surface and len(surface) <= 40:
            exact_surfaces = sorted(
                {
                    surface[start:end]
                    for start in range(len(surface))
                    for end in range(start + 1, len(surface) + 1)
                },
                key=lambda value: (len(value), value),
            )
            source_excerpt = item_schema.get("properties", {}).get(
                "source_excerpt"
            )
            if isinstance(source_excerpt, dict):
                source_excerpt["enum"] = exact_surfaces
                source_excerpt["description"] = (
                    "Copy one exact non-empty contiguous source slice; the decoder "
                    "cannot translate, inflect, combine, or rewrite particles."
                )
        if isinstance(indices, dict):
            indices["uniqueItems"] = True
            index_items = indices.get("items")
            if isinstance(index_items, dict):
                index_items["type"] = "integer"
                index_items["enum"] = list(range(max(0, goal_count)))
        item_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["context", "framing"]}
                        },
                        "required": ["role"],
                    },
                    "then": {
                        "properties": {
                            "coverage": {
                                "enum": ["covered", "clarification_required"]
                            },
                            "independently_satisfiable": {"enum": [False]},
                            "candidate_goal_indices": {"maxItems": 0},
                            "required_goal_shape": {"const": "ordinary"},
                            "required_information_domain": {"const": "none"},
                            "required_output_mode": {"const": "none"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["constraint"]}
                        },
                        "required": ["role"],
                    },
                    "then": {
                        "properties": {
                            "independently_satisfiable": {"enum": [False]},
                            "required_goal_shape": {"const": "ordinary"},
                            "required_information_domain": {"const": "none"},
                            "required_output_mode": {"const": "none"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["responsibility"]},
                            "required_goal_shape": {
                                "enum": ["information_resource"]
                            },
                        },
                        "required": ["role", "required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_information_domain": {
                                "enum": [
                                    "local_clock",
                                    "weather_forecast",
                                    "external_grounded_information",
                                    "direct_environment_perception",
                                    "private_runtime_information",
                                ]
                            },
                            "required_output_mode": {"const": "capability_work"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "required_goal_shape": {
                                "enum": [
                                    "ordinary",
                                    "physical_resource",
                                    "persistent_effect",
                                ]
                            }
                        },
                        "required": ["required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_information_domain": {"const": "none"}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "required_goal_shape": {
                                "enum": ["physical_resource"]
                            }
                        },
                        "required": ["required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_output_mode": {"const": "body_action"}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "required_goal_shape": {
                                "enum": ["persistent_effect"]
                            }
                        },
                        "required": ["required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_output_mode": {"const": "capability_work"}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {
                                "enum": ["responsibility", "constraint"]
                            },
                            "coverage": {
                                "enum": ["covered", "clarification_required"]
                            },
                        },
                        "required": ["role", "coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {"minItems": 1}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["responsibility"]},
                            "coverage": {"enum": ["covered"]},
                        },
                        "required": ["role", "coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {
                                "minItems": 1,
                                "maxItems": 1,
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "coverage": {"enum": ["representation_mismatch"]}
                        },
                        "required": ["coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {"minItems": 1}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["responsibility"]},
                            "coverage": {"enum": ["representation_mismatch"]},
                        },
                        "required": ["role", "coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {
                                "minItems": 1,
                                "maxItems": 1,
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "coverage": {
                                "enum": ["missing"]
                            }
                        },
                        "required": ["coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {"maxItems": 0}
                        }
                    },
                },
            ]
        )
        properties = schema.get("properties", {})
        responsibility_items = properties.get("responsibility_items")
        supporting_items = properties.get("supporting_items")
        if isinstance(responsibility_items, dict):
            responsibility_item = copy.deepcopy(item_schema)
            responsibility_item_properties = responsibility_item["properties"]
            responsibility_required = list(responsibility_item["required"])

            def candidate_shape(
                candidate: GoalAssociationModelGoal,
            ) -> tuple[str, str, str]:
                resource = candidate.resource_responsibility
                if resource is not None and resource.kind == "information":
                    return (
                        "information_resource",
                        resource.information_domain,
                        candidate.output_mode,
                    )
                if resource is not None and resource.kind == "physical_object":
                    return ("physical_resource", "none", candidate.output_mode)
                if candidate.output_mode == "capability_work":
                    return ("persistent_effect", "none", candidate.output_mode)
                return ("ordinary", "none", candidate.output_mode)

            def responsibility_branch(
                *,
                coverage: str,
                candidate_index: int | None,
                constrain_to_candidate: bool,
            ) -> dict[str, Any]:
                branch_properties = copy.deepcopy(
                    responsibility_item_properties
                )
                branch_properties["role"] = {"const": "responsibility"}
                branch_properties["coverage"] = {"const": coverage}
                branch_properties["candidate_goal_indices"] = {
                    "const": (
                        []
                        if candidate_index is None
                        else [candidate_index]
                    )
                }
                if constrain_to_candidate and candidate_index is not None:
                    shape, information_domain, output_mode = candidate_shape(
                        candidate_goals[candidate_index]
                    )
                    branch_properties["required_goal_shape"] = {
                        "const": shape
                    }
                    branch_properties["required_information_domain"] = {
                        "const": information_domain
                    }
                    branch_properties["required_output_mode"] = {
                        "const": output_mode
                    }
                return {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": branch_properties,
                    "required": responsibility_required,
                }

            responsibility_branches: list[dict[str, Any]] = []
            for candidate_index in range(goal_count):
                responsibility_branches.extend(
                    [
                        responsibility_branch(
                            coverage="covered",
                            candidate_index=candidate_index,
                            constrain_to_candidate=True,
                        ),
                        responsibility_branch(
                            coverage="clarification_required",
                            candidate_index=candidate_index,
                            constrain_to_candidate=True,
                        ),
                        responsibility_branch(
                            coverage="representation_mismatch",
                            candidate_index=candidate_index,
                            constrain_to_candidate=False,
                        ),
                    ]
                )
            responsibility_branches.append(
                responsibility_branch(
                    coverage="missing",
                    candidate_index=None,
                    constrain_to_candidate=False,
                )
            )
            responsibility_items["items"] = {
                "oneOf": responsibility_branches
            }
        if isinstance(supporting_items, dict):
            supporting_item = copy.deepcopy(item_schema)
            supporting_item["properties"]["role"] = {
                "type": "string",
                "enum": ["constraint", "context", "framing"],
            }
            supporting_items["items"] = supporting_item
    schema["required"] = [
        "responsibility_items",
        "supporting_items",
        "reason_summary",
    ]
    schema["additionalProperties"] = False
    return schema


def coverage_verdict(
    certificate: GoalResponsibilityCoverageCertificate,
    *,
    goal_count: int,
) -> tuple[Literal["accept", "reject"], list[str]]:
    problems: list[str] = []
    responsibility_owner_counts: dict[int, int] = {}
    positively_owned: set[int] = set()
    for item in certificate.items:
        if item.role in {"responsibility", "constraint"} and item.coverage not in {
            "covered",
            "clarification_required",
        }:
            problems.append(
                f"{item.coverage}:{item.role}:{item.source_excerpt}"
            )
            # Preserve the auditor's typed semantic proof as feedback for the
            # one already-authorized fresh interpretation.  The Host does not
            # infer these facts from user wording; it only forwards fields the
            # GA-owned coverage model explicitly declared.
            if item.required_goal_shape != "ordinary":
                problems.append(
                    "required_goal_shape:"
                    + item.required_goal_shape
                    + f":{item.role}:{item.source_excerpt}"
                )
            if item.required_information_domain != "none":
                problems.append(
                    "required_information_domain:"
                    + item.required_information_domain
                    + f":{item.role}:{item.source_excerpt}"
                )
            if item.required_output_mode != "none":
                problems.append(
                    "required_output_mode:"
                    + item.required_output_mode
                    + f":{item.role}:{item.source_excerpt}"
                )
        if item.role != "responsibility" or item.coverage not in {
            "covered",
            "clarification_required",
        }:
            continue
        for goal_index in item.candidate_goal_indices:
            positively_owned.add(goal_index)
            if item.independently_satisfiable:
                responsibility_owner_counts[goal_index] = (
                    responsibility_owner_counts.get(goal_index, 0) + 1
                )
    for goal_index, count in sorted(responsibility_owner_counts.items()):
        if count > 1:
            problems.append(
                f"overmerged_independent_responsibilities:goal[{goal_index}]"
            )
    unjustified = sorted(set(range(max(0, goal_count))) - positively_owned)
    if unjustified:
        problems.append(
            "unjustified_goal_indices:"
            + ",".join(str(index) for index in unjustified)
        )
    return ("reject", problems) if problems else ("accept", [])
