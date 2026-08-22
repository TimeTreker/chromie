from __future__ import annotations

"""Model-facing Goal Association DTOs and typed representation only.

Schema construction and deterministic normalization/coverage mechanics live in sibling
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
