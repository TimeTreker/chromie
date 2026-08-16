from __future__ import annotations

from .goal_progress_communication import goal_progress_communication_prompt
import copy
import hashlib
import json
import logging
import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .clients.ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from .agent_skills import agent_skill_prompt_section
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
)
try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from chromie_runtime.llm_diagnostics import cognition_text_reference
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from shared.chromie_runtime.llm_diagnostics import cognition_text_reference
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

try:
    from chromie_contracts.discourse import (
        DiscourseReferent,
        DiscourseReferentUpdate,
        GoalEntityBinding,
        ResolvedDiscourseReference,
        stable_referent_id,
    )
    from chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from chromie_contracts.resource import (
        AcquireAndDeliverResource,
        ResourceDescriptor,
        ResourceRecipient,
        ResourceSource,
    )
    from chromie_contracts.semantic_task import SemanticGoal
    from chromie_contracts.situation import SituationProjection
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.discourse import (
        DiscourseReferent,
        DiscourseReferentUpdate,
        GoalEntityBinding,
        ResolvedDiscourseReference,
        stable_referent_id,
    )
    from shared.chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from shared.chromie_contracts.resource import (
        AcquireAndDeliverResource,
        ResourceDescriptor,
        ResourceRecipient,
        ResourceSource,
    )
    from shared.chromie_contracts.semantic_task import SemanticGoal
    from shared.chromie_contracts.situation import SituationProjection

logger = logging.getLogger("chromie.agent.goal_association")


GoalSegmentationDecision = Literal["create_goals", "clarify"]
GoalAssociationDecision = Literal["associate", "create_goals", "clarify"]
GoalResponsibilityKind = Literal[
    "executable_action",
    "vocal_output",
    "capability_dependent",
    "other",
]
GoalExecutionLane = Literal["vocal", "activity", "none"]
GoalOutputMode = Literal[
    "speech",
    "expressive_speech",
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
    "expressive_speech": ("vocal_output", "vocal", True),
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
    "When a concrete requested effect is accompanied by a broad desired social "
    "impression but no words, information, vocal performance, or second effect "
    "modality is specified, apply that impression as embodiment-wide expression "
    "framing to the concrete effect. Do not invent an audible modality from an "
    "adjective, state directive, conjunction, or imperative grammar."
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
    target_goal_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    updated_description: str = ""
    resolved_gap_ids: list[str] = Field(default_factory=list)
    requires_replan: bool = False

    @field_validator("reason_summary", "updated_description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("target_goal_ids", "resolved_gap_ids", mode="before")
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
    value: str = Field(min_length=1)
    referent_id: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("name", "entity_type", "value", "referent_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


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
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

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
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

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
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


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
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

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
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

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

    kind: Literal["information"] = "information"
    description: str = Field(min_length=1)
    quantity: str = ""
    query_scope: list[GoalAssociationModelBinding] = Field(min_length=1, max_length=12)
    source: GoalAssociationModelInformationSource
    recipient: GoalAssociationModelResourceRecipient = Field(
        default_factory=GoalAssociationModelResourceRecipient
    )
    delivery_mode: Literal["spoken_explanation", "structured_result"]

    @field_validator("description", "quantity", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: str) -> str:
        return _validate_model_resource_quantity(value)

    @model_validator(mode="after")
    def validate_scope(self) -> "GoalAssociationModelInformationResourceResponsibility":
        reserved = {
            "source", "provider", "provider_id", "website", "search_engine",
            "delivery_mode", "recipient", "resource", "quantity",
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

    kind: Literal["physical_object"] = "physical_object"
    description: str = Field(min_length=1)
    quantity: str = ""
    source: GoalAssociationModelPhysicalSource
    recipient: GoalAssociationModelResourceRecipient = Field(
        default_factory=GoalAssociationModelResourceRecipient
    )
    delivery_mode: Literal["physical_handover"] = "physical_handover"

    @field_validator("description", "quantity", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

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
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator(
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
    clarification: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def select_branch(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        decision = str(normalized.get("decision") or "").strip()
        if decision not in {"create_goals", "clarify"}:
            decision = "create_goals" if normalized.get("new_goals") else "clarify"
        normalized["decision"] = decision
        if decision == "create_goals":
            normalized["clarification"] = ""
        else:
            normalized["new_goals"] = []
            normalized["referent_updates"] = []
            normalized["resolved_references"] = []
        return normalized

    @field_validator("clarification", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalSegmentationModelOutput":
        if self.decision == "create_goals" and not self.new_goals:
            raise ValueError("decision=create_goals requires new_goals")
        if self.decision == "clarify" and not self.clarification:
            raise ValueError("decision=clarify requires clarification")
        return self


class GoalAssociationModelOutput(BaseModel):
    """Small discriminated semantic DTO returned by Goal Association."""

    model_config = ConfigDict(extra="ignore")

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
    clarification: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def select_branch(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        decision = str(normalized.get("decision") or "").strip()
        if decision not in {"associate", "create_goals", "clarify"}:
            if normalized.get("associations"):
                decision = "associate"
            elif normalized.get("new_goals"):
                decision = "create_goals"
            else:
                decision = "clarify"
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
        if decision == "clarify":
            normalized["associations"] = []
            normalized["new_goals"] = []
            normalized["referent_updates"] = []
            normalized["resolved_references"] = []
        else:
            normalized["clarification"] = ""
            if decision == "create_goals":
                normalized["associations"] = []
        return normalized

    @field_validator("clarification", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelOutput":
        if self.decision == "clarify" and not self.clarification:
            raise ValueError("decision=clarify requires clarification")
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

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("candidate_goal_indices")
    @classmethod
    def unique_goal_indices(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("candidate_goal_indices must be unique")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalResponsibilityCoverageItem":
        if self.role != "responsibility" and self.independently_satisfiable:
            raise ValueError(
                "only a responsibility may be independently_satisfiable"
            )
        if self.role in {"context", "framing"}:
            if self.coverage != "covered" or self.candidate_goal_indices:
                raise ValueError(
                    "context and framing are acknowledged without Goal ownership"
                )
            return self
        if self.coverage == "covered":
            if not self.candidate_goal_indices:
                raise ValueError(
                    "covered responsibility or constraint requires Goal ownership"
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
                "missing or clarification-required meaning cannot claim Goal ownership"
            )
        return self



class GoalResponsibilityCoverageCertificate(BaseModel):
    """Authority-ephemeral proof over one candidate Goal set.

    The model authors only source-grounded item judgments.  The Host derives the
    verdict and every unjustified candidate index, so neither can drift or need a
    repair call.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[GoalResponsibilityCoverageItem] = Field(
        min_length=1,
        max_length=16,
    )
    reason_summary: str = Field(min_length=1, max_length=1200)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @model_validator(mode="after")
    def validate_material_evidence(self) -> "GoalResponsibilityCoverageCertificate":
        # This certificate is immutable proof evidence, not a second canonical
        # segmentation. Redundant/overlapping excerpts are diagnostically noisy but
        # must not crash a valid semantic transaction by themselves.
        if not any(
            item.role in {"responsibility", "constraint"}
            for item in self.items
        ):
            raise ValueError(
                "coverage certificate for created Goals requires material user meaning"
            )
        return self




class GoalAssociationResolver:
    """Resolve continuity before creation without mutating runtime state."""

    TRACE_MODULE = TraceModule(
        name="agent.goal_association",
        component_type="goal_association",
        implementation="GoalAssociationResolver",
        schema_version=1,
    )

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        min_confidence: float = 0.65,
        max_active_goals: int = 8,
        num_ctx: int = 4096,
        num_predict: int = 512,
    ) -> None:
        self.ollama = ollama
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.max_active_goals = max(1, min(32, int(max_active_goals)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(self, request: CognitiveWorkRequest) -> GoalAssociationResolution:
        trace_scope = runtime_tracer.continue_from_context(request.context)
        if not trace_scope.enabled:
            return await self._resolve(request)
        try:
            async with trace_scope:
                async with runtime_tracer.span(
                    module=self.TRACE_MODULE,
                    operation="resolve",
                    attributes={
                        "candidate_goal_count": len(self._candidate_goals(request)),
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                    },
                ) as span:
                    result = await self._resolve(request)
                    status = result.resolution_status
                    span.set_attribute("result_status", status)
                    span.set_attribute("association_count", len(result.associations))
                    span.set_attribute("new_goal_count", len(result.new_goals))
                    if status not in {"resolved", "needs_clarification"}:
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise
        trace_scope.finish(state="complete")
        runtime_tracer.attach_fragment(result.metadata, trace_scope)
        return result

    async def _resolve(self, request: CognitiveWorkRequest) -> GoalAssociationResolution:
        """Resolve one turn through the bounded Goal semantic transaction."""

        candidate_goals = self._candidate_goals(request)
        turn_id = self._turn_id(request)
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ) = (
            GoalAssociationModelOutput
            if candidate_goals
            else GoalSegmentationModelOutput
        )
        response_schema = self._response_schema(
            output_type,
            candidate_goals,
            self._discourse_referents(request),
            clarification_only=False,
        )
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        logical_invocations = 0
        invocation_families: list[str] = []
        initial_raw: dict[str, Any] | None = None
        accepted_raw: dict[str, Any] | None = None
        certificate_raw: dict[str, Any] | None = None
        contract_repair_attempted = False
        semantic_reconsideration_attempted = False
        optional_referent_recovery: list[dict[str, Any]] = []

        async def invoke(
            prompt: Any,
            *,
            system: str,
            response_format: dict[str, Any],
            prompt_family: str,
        ) -> Any:
            nonlocal logical_invocations
            if logical_invocations >= 5:
                raise RuntimeError(
                    "goal-association logical invocation budget exhausted"
                )
            logical_invocations += 1
            invocation_families.append(prompt_family)
            return await self.ollama.generate(
                prompt,
                system=system,
                options=generation_options,
                response_format=response_format,
                prompt_family=prompt_family,
                turn_id=request.sid,
                attempt=logical_invocations,
            )

        def normalize_raw(value: Any, *, stage: str) -> dict[str, Any]:
            if not isinstance(value, dict):
                raise OllamaGenerationError(
                    f"goal-association {stage} response is not a JSON object",
                    failure_class="structured_output_invalid",
                    failure_domain="model_contract",
                    architecture_attribution="not_evaluated",
                    retryable=True,
                )
            normalized, recovered = self._drop_invalid_optional_referent_introductions(
                value
            )
            optional_referent_recovery.extend(recovered)
            return normalized

        try:
            initial_raw = normalize_raw(
                await invoke(
                    self._layered_prompt(
                        request,
                        candidate_goals,
                        output_type=output_type,
                    ),
                    system=self._system_prompt(output_type),
                    response_format=response_schema,
                    prompt_family="goal_association.primary",
                ),
                stage="primary",
            )
            try:
                resolution = await self._validate_contract_output(
                    initial_raw,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                accepted_raw = initial_raw
            except (ValidationError, ValueError) as initial_exc:
                contract_repair_attempted = True
                repaired = normalize_raw(
                    await invoke(
                        self._layered_repair_prompt(
                            request=request,
                            candidate_goals=candidate_goals,
                            turn_id=turn_id,
                            output_type=output_type,
                            raw=initial_raw,
                            validation_error=self._validation_error_json(
                                initial_exc
                            ),
                        ),
                        system=self._repair_system_prompt(output_type),
                        response_format=response_schema,
                        prompt_family="goal_association.contract_repair",
                    ),
                    stage="contract repair",
                )
                resolution = await self._validate_contract_output(
                    repaired,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                accepted_raw = repaired

            model_output = output_type.model_validate(accepted_raw)
            coverage_metadata: dict[str, Any] = {
                "attempted": False,
                "succeeded": False,
                "initial_verdict": "not_required",
                "final_verdict": "not_required",
                "reconsidered": False,
            }
            if self._responsibility_coverage_required(
                model_output,
                request=request,
            ):
                coverage_metadata["attempted"] = True
                certificate_raw = await invoke(
                    self._build_responsibility_coverage_prompt(
                        request=request,
                        raw=accepted_raw,
                    ),
                    system=self._responsibility_coverage_system_prompt(),
                    response_format=self._coverage_certificate_response_schema(
                        len(model_output.new_goals)
                    ),
                    prompt_family="goal_association.responsibility_coverage",
                )
                certificate = self._validate_coverage_certificate(
                    certificate_raw,
                    request=request,
                    goal_count=len(model_output.new_goals),
                )
                verdict, problems = self._coverage_verdict(
                    certificate,
                    goal_count=len(model_output.new_goals),
                )
                coverage_metadata["initial_verdict"] = verdict
                coverage_metadata["certificate"] = certificate.model_dump(
                    mode="json"
                )
                if verdict == "reject":
                    semantic_reconsideration_attempted = True
                    coverage_metadata["reconsidered"] = True
                    clarification_required = any(
                        item.coverage == "clarification_required"
                        for item in certificate.items
                    )
                    reconsidered_raw = normalize_raw(
                        await invoke(
                            self._build_fresh_interpretation_prompt(
                                request=request,
                                candidate_goals=candidate_goals,
                                output_type=output_type,
                                problems=problems,
                                force_clarification=clarification_required,
                            ),
                            system=self._semantic_review_system_prompt(
                                output_type,
                                fresh_resegmentation=True,
                            ),
                            response_format=(
                                self._response_schema(
                                    output_type,
                                    candidate_goals,
                                    self._discourse_referents(request),
                                    clarification_only=True,
                                )
                                if clarification_required
                                else response_schema
                            ),
                            prompt_family="goal_association.fresh_interpretation",
                        ),
                        stage="fresh interpretation",
                    )
                    # A semantic reconsideration is the final interpretation.  It
                    # receives no DTO repair.
                    resolution = await self._validate_contract_output(
                        reconsidered_raw,
                        request=request,
                        turn_id=turn_id,
                        output_type=output_type,
                    )
                    accepted_raw = reconsidered_raw
                    reconsidered_output = output_type.model_validate(accepted_raw)
                    if self._responsibility_coverage_required(
                        reconsidered_output,
                        request=request,
                    ):
                        certificate_raw = await invoke(
                            self._build_responsibility_coverage_prompt(
                                request=request,
                                raw=accepted_raw,
                            ),
                            system=self._responsibility_coverage_system_prompt(),
                            response_format=self._coverage_certificate_response_schema(
                                len(reconsidered_output.new_goals)
                            ),
                            prompt_family=(
                                "goal_association.responsibility_coverage_final"
                            ),
                        )
                        final_certificate = self._validate_coverage_certificate(
                            certificate_raw,
                            request=request,
                            goal_count=len(reconsidered_output.new_goals),
                        )
                        final_verdict, final_problems = self._coverage_verdict(
                            final_certificate,
                            goal_count=len(reconsidered_output.new_goals),
                        )
                        coverage_metadata["final_verdict"] = final_verdict
                        coverage_metadata["certificate"] = (
                            final_certificate.model_dump(mode="json")
                        )
                        if final_verdict != "accept":
                            raise ValueError(
                                "fresh Goal interpretation failed final responsibility "
                                "coverage: " + "; ".join(final_problems)
                            )
                    else:
                        coverage_metadata["final_verdict"] = "clarification"
                else:
                    coverage_metadata["final_verdict"] = "accept"
                coverage_metadata["succeeded"] = True

            metadata = dict(resolution.metadata)
            metadata.update(
                {
                    "goal_semantic_transaction": {
                        "logical_invocation_count": logical_invocations,
                        "logical_invocation_budget": 5,
                        "prompt_families": invocation_families,
                        "contract_repair_attempted": contract_repair_attempted,
                        "semantic_reconsideration_attempted": (
                            semantic_reconsideration_attempted
                        ),
                        "terminal_state": "commit",
                    },
                    "responsibility_coverage": coverage_metadata,
                }
            )
            if optional_referent_recovery:
                metadata["optional_contract_recovery"] = {
                    "field": "referent_updates",
                    "strategy": "drop_invalid_unreferenced_introduce",
                    "dropped_count": len(optional_referent_recovery),
                    "entries": optional_referent_recovery,
                }
            resolution = resolution.model_copy(update={"metadata": metadata})
            return self._validate(
                resolution,
                candidate_goals=candidate_goals,
                request=request,
            )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.exception(
                "goal_association_transaction_failed sid=%s error_type=%s "
                "error=%s logical_invocations=%d prompt_families=%s",
                request.sid,
                type(exc).__name__,
                exc,
                logical_invocations,
                ",".join(invocation_families),
            )
            metadata: dict[str, Any] = {
                "resolver": "goal_association_agent",
                "status": "model_contract_failed",
                "sid": request.sid,
                "authority": "advisory",
                **failure,
                **cognitive_integrity_metadata(
                    stage="goal_association",
                    exc=exc,
                    request=request,
                ),
                "goal_semantic_transaction": {
                    "logical_invocation_count": logical_invocations,
                    "logical_invocation_budget": 5,
                    "prompt_families": invocation_families,
                    "contract_repair_attempted": contract_repair_attempted,
                    "semantic_reconsideration_attempted": (
                        semantic_reconsideration_attempted
                    ),
                    "terminal_state": "fail_closed",
                },
                "initial_raw_output_ref": cognition_text_reference(initial_raw),
                "accepted_raw_output_ref": cognition_text_reference(accepted_raw),
                "coverage_certificate_ref": cognition_text_reference(certificate_raw),
            }
            if isinstance(exc, (ValidationError, ValueError)):
                metadata.update(
                    {
                        "failure_class": "structured_output_validation",
                        "failure_domain": "model_contract",
                        "architecture_attribution": "not_evaluated",
                        "retryable": False,
                    }
                )
            if optional_referent_recovery:
                metadata["optional_contract_recovery"] = {
                    "field": "referent_updates",
                    "strategy": "drop_invalid_unreferenced_introduce",
                    "dropped_count": len(optional_referent_recovery),
                    "entries": optional_referent_recovery,
                }
            return GoalAssociationResolution(
                turn_id=turn_id,
                resolution_status="fail_closed",
                confidence=0.0,
                reason_summary=(
                    "Goal semantics did not reach the trusted commit boundary; "
                    "no goal operation was accepted."
                ),
                metadata=metadata,
            )


    @staticmethod
    def _drop_invalid_optional_referent_introductions(
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

    async def _validate_contract_output(
        self,
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> GoalAssociationResolution:
        model_output = output_type.model_validate(raw)
        collection_bindings = self._action_collection_bindings(model_output)
        if collection_bindings:
            raise ValueError(
                "new Goal bindings cannot contain action collections; emit one "
                "new_goals item for every independently observable responsibility: "
                + ", ".join(collection_bindings)
            )
        binding_conflicts = self._binding_semantic_contract_conflicts(model_output)
        if binding_conflicts:
            raise ValueError(
                "binding name and entity_type cannot declare conflicting canonical "
                "parameter categories; preserve the intended parameter and correct "
                "the contradictory field: "
                + ", ".join(binding_conflicts)
            )
        resource_source_conflicts = (
            self._resource_source_binding_contract_conflicts(model_output)
        )
        if resource_source_conflicts:
            raise ValueError(
                "physical resource source.acquisition_bindings may describe only an "
                "actual spatial/acquisition constraint. Resource identity, "
                "requested quantity, recipient, and delivery fields are not source "
                "evidence: "
                + ", ".join(resource_source_conflicts)
            )
        location_bindings = self._non_verbatim_explicit_location_bindings(
            model_output,
            request=request,
        )
        if location_bindings:
            raise ValueError(
                "a location binding must preserve explicit or referent-backed "
                "provenance. For a directly named location, preserve a verbatim "
                "contiguous span from the authoritative user turn and do not "
                "translate, transliterate, or expand it. For an indirect "
                "location, copy the supplied referent_id into both the location "
                "binding and resolved_references, and copy the indirect user "
                "surface into resolved_references.surface_form: "
                + ", ".join(location_bindings)
            )
        return self._expand_model_output(
            model_output,
            request=request,
            turn_id=turn_id,
        )

    @staticmethod
    def _action_collection_bindings(
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

    @staticmethod
    def _binding_semantic_contract_conflicts(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    ) -> list[str]:
        """Reject contradictions between model-authored canonical binding fields.

        This does not infer a parameter from user wording. It only prevents a DTO
        from calling the same binding two different canonical parameter kinds, such
        as ``name=distance`` with ``entity_type=quantity``.
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
                if (
                    name_category is not None
                    and type_category is not None
                    and name_category != type_category
                ):
                    conflicts.append(
                        f"new_goals[{goal_index}].bindings[{binding_index}]="
                        f"{binding.name}/{binding.entity_type}"
                    )
        return conflicts

    @staticmethod
    def _resource_source_binding_contract_conflicts(
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
            "place",
            "provider",
            "source",
            "source_location",
            "source_provider",
            "spatial_offset",
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
                if normalized_name in non_source_names or (
                    normalized_type in identity_or_quantity_types
                    and normalized_name not in explicit_source_names
                ):
                    conflicts.append(
                        f"new_goals[{goal_index}].resource_responsibility."
                        f"source.acquisition_bindings[{source_name}]="
                        f"non_source_semantics({binding.name}/{binding.entity_type})"
                    )
        return conflicts

    @staticmethod
    def _non_verbatim_explicit_location_bindings(
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


    @staticmethod
    def _validation_error_json(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            payload: Any = exc.errors(include_url=False)
        else:
            payload = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )[:6000]


    @staticmethod
    def _response_schema(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        candidate_goals: list[dict[str, Any]],
        discourse_referents: list[dict[str, Any]],
        *,
        clarification_only: bool = False,
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
        properties = schema.get("properties", {})
        new_goals = properties.get("new_goals")
        if isinstance(new_goals, dict):
            new_goals["maxItems"] = 8
        if not referent_ids:
            resolved_references = properties.get("resolved_references")
            if isinstance(resolved_references, dict):
                resolved_references["maxItems"] = 0

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                node_properties = node.get("properties")
                if isinstance(node_properties, dict):
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
        properties = schema.setdefault("properties", {})
        required = list(schema.get("required") or [])
        if output_type is GoalSegmentationModelOutput:
            properties["decision"] = {
                "type": "string",
                "enum": ["create_goals", "clarify"],
            }
            ordered_required = [
                "decision",
                "new_goals",
                "referent_updates",
                "resolved_references",
                "clarification",
                "confidence",
                "reason_summary",
            ]
        else:
            properties["decision"] = {
                "type": "string",
                "enum": ["associate", "create_goals", "clarify"],
            }
            ordered_required = [
                "decision",
                "associations",
                "new_goals",
                "referent_updates",
                "resolved_references",
                "clarification",
                "confidence",
                "reason_summary",
            ]
        schema["required"] = list(dict.fromkeys([*ordered_required, *required]))
        if clarification_only:
            properties["decision"] = {"type": "string", "enum": ["clarify"]}
            clarification = properties.get("clarification")
            if isinstance(clarification, dict):
                clarification["minLength"] = 1
            new_goals = properties.get("new_goals")
            if isinstance(new_goals, dict):
                new_goals["maxItems"] = 0
            associations = properties.get("associations")
            if isinstance(associations, dict):
                associations["maxItems"] = 0
            referent_updates = properties.get("referent_updates")
            if isinstance(referent_updates, dict):
                referent_updates["maxItems"] = 0
            resolved_references = properties.get("resolved_references")
            if isinstance(resolved_references, dict):
                resolved_references["maxItems"] = 0
        schema.pop("oneOf", None)
        schema.pop("anyOf", None)
        return GoalAssociationResolver._resource_semantic_contract_response_schema(
            GoalAssociationResolver._binding_semantic_contract_response_schema(
                schema
            )
        )

    @staticmethod
    def _binding_semantic_contract_response_schema(
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
        return schema

    @staticmethod
    def _resource_semantic_contract_response_schema(
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

    def _candidate_goals(self, request: CognitiveWorkRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        active = context.get("active_goal_snapshots")
        recent = context.get("recent_goal_snapshots")
        if not isinstance(active, list):
            active = []
        if not isinstance(recent, list):
            recent = []
        raw = [*active, *recent]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(raw):
            if len(out) >= self.max_active_goals:
                break
            if not isinstance(item, dict):
                continue
            try:
                snapshot = ActiveGoalSnapshot.model_validate(item).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                goal_id = str(snapshot.get("goal_id") or "").strip()
                if not goal_id or goal_id in seen:
                    continue
                seen.add(goal_id)
                out.append(snapshot)
            except ValidationError as exc:
                logger.debug(
                    "Ignoring malformed Goal association candidate index=%s error=%s",
                    index,
                    exc,
                )
                continue
        return out

    def _discourse_referents(self, request: CognitiveWorkRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("discourse_referents")
        if not isinstance(raw, list):
            raw = []
        out: list[dict[str, Any]] = []
        for index, item in enumerate(raw[:24]):
            if not isinstance(item, dict):
                continue
            try:
                out.append(
                    DiscourseReferent.model_validate(item).model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                )
            except ValidationError as exc:
                logger.debug(
                    "Ignoring malformed discourse referent index=%s error=%s",
                    index,
                    exc,
                )
                continue
        return out

    @staticmethod
    def _situation_projection(request: CognitiveWorkRequest) -> dict[str, Any]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("situation")
        if not isinstance(raw, dict):
            return {}
        try:
            return SituationProjection.model_validate(raw).prompt_projection()
        except ValidationError as exc:
            logger.debug("Ignoring malformed Situation projection error=%s", exc)
            return {}

    @staticmethod
    def _turn_id(request: CognitiveWorkRequest) -> str:
        seed = f"{request.sid or 'turn'}|{request.text}"
        return f"turn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _bounded_json(value: Any, max_chars: int) -> str:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."

    @staticmethod
    def _fast_planner_advance_goal_projection(context: dict[str, Any]) -> dict[str, Any]:
        """Project only continuity markers from pre-Goal Planner HOW.

        Goal Association never needs Planner-authored response wording. Keeping that
        text out of the segmentation prompt prevents a model from mistaking an
        already-authored progress Activity for a second human Responsibility/Goal.
        """

        raw = context.get("fast_planner_advance")
        if not isinstance(raw, dict):
            return {}
        activity = raw.get("immediate_vocal_activity")
        activity_projection: dict[str, Any] | None = None
        if isinstance(activity, dict):
            refs = activity.get("source_responsibility_refs")
            activity_projection = {
                "activity_id": str(activity.get("activity_id") or ""),
                "role": str(activity.get("role") or ""),
                "source_responsibility_refs": (
                    list(refs) if isinstance(refs, list) else []
                ),
            }
        metadata = raw.get("metadata")
        return {
            "covered_responsibility_refs": list(
                raw.get("covered_responsibility_refs")
                if isinstance(raw.get("covered_responsibility_refs"), list)
                else []
            ),
            "continuations": list(
                raw.get("continuations")
                if isinstance(raw.get("continuations"), list)
                else []
            ),
            "immediate_vocal_activity": activity_projection,
            "advance_status": (
                str(metadata.get("advance_status") or "")
                if isinstance(metadata, dict)
                else ""
            ),
        }

    def _build_prompt(
        self,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        *,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        skill_section = agent_skill_prompt_section(
            context,
            agent_role="goal_association",
        )
        if output_type is GoalSegmentationModelOutput:
            state_instructions = (
                "There are no active or retained recent Goals, so no existing-goal relationship is possible and the contract intentionally has no associations field. "
                "Segment the authoritative user turn into independent new Goals, or return a clarification if the human-level outcome is materially ambiguous or still lacks semantic information required to define what Chromie owes. "
            )
            output_instructions = (
                "Return only JSON with decision, new_goals, referent_updates, resolved_references, clarification, confidence, and reason_summary. "
                "Use decision=create_goals when every material part of the owed outcome is semantically defined. Use decision=clarify for genuinely ambiguous meaning or unresolved material semantic information required to define that outcome; do not clarify for provider or execution details of an already-defined outcome. "
                "The decoder enforces the exact GoalSegmentationModelOutput JSON Schema. "
            )
        else:
            state_instructions = (
                "Resolve continuity before creation using semantic reasoning. "
                "For continuity with an existing goal, emit an associations item with relationship, target_goal_ids, confidence, reason_summary, the applicable updated_description, resolved_gap_ids, and requires_replan fields. "
                "relationship must be copied exactly from [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"merge\",\"split\",\"reference\"]. "
                "Use continue only when the current turn advances unchanged unfinished active or recoverable work. Use reference when the current turn asks to retrieve, restate, explain, compare, verify, or otherwise answer from a retained Goal without changing its meaning or lifecycle. Do not use continue or reference merely because the topic overlaps with a previous Goal. When the latest turn is a social reaction, acknowledgement, personal feeling, practical decision, conversational evaluation, empathy-seeking comment, or another independently satisfiable communicative act, create a fresh vocal_output Goal that captures that latest intent; prior delivered information remains context for that answer. Use modify only when the same Responsibility is being refined and include updated_description or resolved_gap_ids. When the user abandons that Responsibility for a genuinely different outcome, return decision=create_goals with a new Goal whose supersedes_goal_ids names the old Goal; never mutate the old Goal through an association. The association relationship clarify means the current user turn supplies missing information for a Goal and must include updated_description or resolved_gap_ids; it never means that the user is asking Chromie for more explanation. When Chromie still lacks material semantic information required to define the current owed outcome, or the user's meaning itself is ambiguous, use top-level decision=clarify instead of guessing or deferring that meaning to planning. "
                "Use confirm only when the current turn approves a pending proposal for the targeted Goal, and use reject only when it declines that proposal. "
                "Associations may target only IDs from the bounded candidate-goal list. A recent terminal Goal may be referenced without reopening or changing its terminal lifecycle state. "
                "An association cannot rewrite an existing Goal's typed material bindings. When your semantic judgment is that the current user meaning changes a material entity or parameter, preserve the old Goal and return decision=create_goals with a complete replacement Goal and authoritative bindings. "
            )
            output_instructions = (
                "Return only JSON with decision, associations, new_goals, referent_updates, resolved_references, clarification, confidence, and reason_summary. "
                "Use decision=associate for continuity, decision=create_goals for semantically defined independent work, or decision=clarify when meaning is genuinely ambiguous or material semantic information required to define the owed outcome is unresolved. New Goals may copy related_goal_ids from the bounded active Goal list when that relationship helps later reasoning; this contextual relationship does not itself reopen or add the retained Goal to the current responsibility. "
                "The decoder enforces the exact GoalAssociationModelOutput JSON Schema. "
            )
        return (
            state_instructions
            + "Goal Association receives provider-neutral Responsibility evidence, not a route or intent classification. "
            "No compatibility label may force a clarification branch or attach the turn to an existing Goal. "
            "Create or associate a Goal only when the human-level owed outcome is semantically defined. A material entity or parameter that determines what Chromie owes the user belongs to Goal meaning, not to Planner execution detail; if that material meaning remains unresolved after the authoritative user turn, discourse, retained-Goal bindings, and Situation context, return clarification instead of inventing a value or deferring it to planning. The Planner owns only execution information needed to realize an already-defined outcome. "
            + "The model-facing contract is deliberately small. "
            "The host owns all IDs, versions, source text, constraints, metadata, persistence fields, and canonical object construction. "
            "Never emit id, goal_id, association_id, turn_id, schema_version, source_text, constraints, object, metadata, success_criteria, capabilities, or plans. Referent IDs may only be copied from the supplied discourse context; new referent IDs are Host-generated.\n\n"
            "Create one new goal for each independently satisfiable user responsibility. The authoritative user turn plus Responsibility evidence are the only sources of human Responsibility here; a pre-Goal Fast Planner Activity is HOW already authored downstream and must never become, justify, or be copied into a sibling Goal. Emit exactly one new_goals item containing description, typed bindings, and an optional provider-neutral resource_responsibility for each responsibility. "
            "Every new Goal must declare one exact output_mode that describes the semantic work completing the human outcome. output_mode is the only model-authored execution discriminator. Responsibility kind, execution lane, and provider requirement are Host-derived projections and are not fields in the model schema. Media playback may also declare its exact media_operation; non-media Goals may omit media_operation and the Host supplies none. "
            f"{_EXECUTION_CONTRACT_PROMPT} "
            "The eventual spoken delivery of a capability result is part of that same capability_dependent Goal, never an additional vocal_output Goal. Persona, tone, wording, and answer delivery are not independent Goals. "
            "A requested manner, mood, persona, or social presentation attached to a substantive action or other effect is a constraint on how that effect should be expressed, not a second Goal. Keep it in the substantive Goal description. It becomes a separate vocal Goal only when the user independently asks to hear positive authored content or a vocal performance that remains satisfiable without the substantive effect. "
            "A standalone social interaction such as a greeting, thanks, reassurance request, casual check-in, reaction, personal feeling, evaluation, or practical decision is itself one satisfiable conversational Goal: respond naturally to that current social act. This remains true when the act is grounded in information delivered by a previous Goal. Prior evidence may support the answer, but it does not replace the latest communicative responsibility. Do not treat it as an empty turn or fold it into an already completed task merely because the topic is related. "
            "A greeting or politeness preamble attached to a substantive request is conversational framing, not a separate Goal unless the user independently asks for a social response. Owner-approved identity and personality shape expression only; never create a Goal merely to mention age, identity, warmth, curiosity, or another style trait. "
            "A factual lookup and the user's requested interpretation of that same evidence are one Goal when one capability result can satisfy both, such as checking weather and judging whether it is hot. Multiple requested aspects of one information result, such as precipitation and whether the resulting temperature is cold, remain one information responsibility when the same result satisfies them. Do not split evidence acquisition, requested result aspects, or interpretation of that result into separate Goals. "
            "A physical action and a conversational answer or spoken performance are independent goals when the answer or performance is genuinely requested. Separate independently requested outcomes that can be accepted or rejected on their own. However, acquisition and delivery stages that together constitute one human responsibility are one Goal: navigating/searching, locating, grasping or retrieving, carrying, returning, and handing over are provider-owned stages of one physical resource delivery; external search, evidence retrieval, evaluation, and spoken explanation are stages of one information resource delivery. Do not split those implementation stages into separate Goals unless the user independently requests one stage as its own outcome. A simple acknowledgement, confirmation, willingness statement, or progress prelude for capability work is not a separate vocal_output Goal; it is prospective conversational output attached to the existing responsibility and every cognitive stage must use Interaction Context to avoid repeating an already fulfilled act. Before returning, verify that every independently satisfiable user responsibility appears in exactly one new_goals item: no merged unrelated outcomes and no duplicated responsibility across Goals. "
            "For a responsibility whose human-level outcome is to obtain something and make it available to a recipient, include exactly one nested resource_responsibility. It is the sole writable resource authority and is discriminated by top-level kind. For kind=information, use output_mode=capability_work and write every requested query fact—location, time, requested aspect, comparison, threshold, or other answer-shaping scope—exactly once in query_scope. Its source object is intentionally narrow: source.status=provider_resolved delegates public/external source selection; source.status=unknown preserves an unavailable local/private/runtime source; source.status=known is only for a user- or discourse-named information source and then source_name is required. Never copy query_scope facts into source. For kind=physical_object, use output_mode=body_action and delivery_mode=physical_handover; identity and quantity live at resource_responsibility.description/quantity, while source.acquisition_bindings is the only writable location/distance/direction/route surface. Preserve explicit distance and direction separately; source.description is summary only and any numeric fact in it must also exist in acquisition_bindings. Resource Goals keep top-level bindings empty. No flat compatibility copy is created. resource_responsibility must never name or imply a Capability, provider implementation, website, search engine, coordinates, grasp pose, execution mode, or plan. Human-readable descriptions never override typed fields. "
            "Also preserve semantic qualifiers such as temporal scope, comparison period, and requested answer shape. When a local day part is semantically resolved, represent it provider-neutrally as entity_type=day_part with canonical value morning, afternoon, evening, or tonight; keep the user's natural wording in the Goal description rather than using a provider-specific token. This is semantic normalization, not Capability selection. Never silently rewrite annual, seasonal, historical, comparative, or otherwise broad scope into current, today, tomorrow, or another narrower scope. If the intended scope is materially ambiguous, return clarification instead of choosing a narrower interpretation. "
            "Resolve references, pronouns, demonstratives, ellipsis, and task mentions before planning. Authority order is: explicit current user meaning; foreground scoped discourse referents; candidate Goal bindings; recent dialogue. First identify every material indirect referring expression, then require a unique value from that authority order and preserve it in a typed binding or supplied referent. Imperative grammar and a plausible generic noun such as device, object, person, task, or setting are never reference evidence. If two or more contextual candidates remain plausible, or none is supplied, ask a narrow clarification. Phrases such as ‘the last task I told you’ may semantically associate with an active, recoverable, or retained recent terminal Goal, but the model must decide that relationship from the supplied Goal state and dialogue—not from a Host phrase table. Tool-result memory is not reference-resolution authority and must never decide what an unresolved expression refers to. "
            "When the user introduces or explicitly corrects a salient entity, emit referent_updates only when the required discourse-index provenance is available. Use operation=correct with non-empty target_referent_ids copied from supplied discourse context when a new value supersedes an earlier referent; never emit an unscoped correction when no target referent ID was supplied. The canonical Goal association and typed bindings still preserve a correction even when no discourse-index update can be authored. The old referent remains available in its own task scope but becomes background. Use operation=introduce for a new salient entity, and focus/background/retire only for supplied referent IDs. "
            "Use resolved_references only for indirect references whose denotation must be selected from a supplied discourse referent or active Goal binding, such as pronouns, demonstratives, ellipsis, aliases, corrections, or task mentions. Do not emit resolved_references for an ordinary explicit entity mention such as a directly named place; represent that meaning in the new Goal bindings and, when it is salient for future dialogue, in referent_updates. Every resolved_references item must copy a supplied referent_id and include explicit confidence. If resolution is materially ambiguous, return decision=clarify rather than selecting a value from stale evidence or recency alone. "
            "Each non-resource Goal must include top-level typed bindings for material entities and parameters already resolved here, including explicit counts, durations, speeds, directions, and targets. A resource Goal keeps top-level bindings empty and owns every material resource fact only in resource_responsibility. For information, query_scope is the one query-fact surface; for weather, a resolved place is a query_scope binding named location, with time and requested result aspects as separate bindings. Preserve every explicit severity, intensity, magnitude, threshold, subtype, negation, or comparison qualifier that changes satisfactory completion. Never generalize a narrower request. Downstream planners read the canonical resource directly; no persisted flat projection exists. "
            "For a location named directly in the final authoritative user turn, copy the complete location value verbatim as one contiguous span in the user's language. Never translate, transliterate, shorten, or expand a directly named location. A directly supplied location is a resolved semantic binding, not a claim that provider canonicalization has already succeeded. Do not ask the user for administrative granularity merely because multiple real-world places might share that value; create the fully bound Goal and let the downstream Capability resolve the exact value or report provider ambiguity. Clarify only when the user's intended location is genuinely underdetermined in the dialogue. Only an indirect reference resolved from a supplied referent may use the referent's canonical value instead. For an indirect location, copy the supplied referent_id into both the location binding and resolved_references, and copy the indirect user surface into resolved_references.surface_form. "
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
            "The clarification field is only a concise user-facing question. Never put analysis, rationale, translation, route labels, validator errors, model failures, or system diagnostics in clarification. Put optional compact rationale in reason_summary. If the user meaning is materially ambiguous or a material semantic part of the owed outcome remains unresolved, use decision=clarify; otherwise keep clarification empty.\n\n"
            "Abstract decomposition example: a request to perform action A, then action B, and answer question C produces three new_goals descriptions: perform action A; perform action B; answer question C. "
            "This example is structural, not a phrase-matching rule.\n\n"
            + output_instructions
            + "Each new_goals object contains description, output_mode, optional media_operation, bindings, optional resource_responsibility, related_goal_ids only when retained Goals remain relevant context, and supersedes_goal_ids only when the old Responsibility is genuinely abandoned and replaced by this new independently owed outcome. bindings is an array of typed semantic parameters with name, entity_type, value, optional copied referent_id, and confidence. Use [] when no material binding exists. resource_responsibility is provider-neutral and must follow the contract above. A vocal Goal must never carry resource_responsibility merely because rendering needs a provider. Every referent_updates item and every resolved_references item must include explicit confidence; never rely on an omitted-field default.\n\n"
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{personality_json}\n\n"
            + skill_section
            + "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 6500)}\n\n"
            "Responsibility evidence JSON (Core-authored provider-neutral semantic handoff from Goal Interpretation. These are not canonical Goals. Preserve the WHAT and material bindings; use the authoritative user turn, discourse, retained Goal state, and Situation only to associate continuity or identify a real representation mismatch, never to silently rewrite the Responsibility. Goal Association alone decides create/continue/modify/supersede canonical Goal state. Never infer a Capability, provider, execution method, executable argument, or response wording here):\n"
            f"{self._bounded_json([item.model_dump(mode='json', exclude_none=True) for item in request.responsibilities], 4200)}\n\n"
            "Pre-Goal Fast Planner continuity markers JSON (same Fast Planner, earlier lifecycle phase. Response wording is intentionally absent because Planner HOW is not Goal Association input. An immediate Activity is not a Goal, not human Responsibility evidence, and must never become or justify a sibling Goal. Associate only the underlying Responsibility evidence to canonical Goal state):\n"
            f"{self._bounded_json(self._fast_planner_advance_goal_projection(context), 1800)}\n\n"
            "Bounded active task/progress snapshots JSON:\n"
            f"{self._bounded_json(context.get('active_task_snapshots') or [], 5200)}\n\n"
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON (append-only facts about what Chromie already associated, planned, said, committed, completed, or failed; owner and event_type preserve evidence strength). Use it to identify the still-needed Goal/continuity delta. Generated or scheduled speech is not heard speech, and planned or committed work is not completed work. Do not reopen, repeat, or recreate an already fulfilled responsibility unless the current turn explicitly repeats it or new failure, correction, changed state, evidence, or clarification requires a new delta:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON (most recent/foreground last):\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "Recent conversation is accepted dialogue evidence for ellipsis, pronouns, corrections, and other follow-up meaning. Bounded Goal and Task state is stronger evidence of already-validated semantic continuity when it exists. A newer accepted turn whose metadata says semantic_status=failed or terminal_without_canonical_goal remains valid recent conversational evidence even though it has no canonical Goal; do not skip it solely because an older Goal is canonical. If an earlier admitted turn has not yet produced canonical Goal state, dialogue may still resolve the current reference, but never invent a Goal ID or pretend uncommitted work is canonical.\n\n"
            "Tool-result contents are intentionally absent at this boundary. Resolve references and Goal bindings from user semantics, scoped referents, candidate Goals, and dialogue only. A later Planner may explicitly retrieve an exact verified memory record after bindings are fixed. "
            "For an open safe-read Goal whose bound Work is scheduled, running, or recoverable, associate a semantic follow-up with that exact Goal when appropriate; do not answer from another task's result. "
            "Do not reason from prior routing labels, planner states, validation failures, fallback states, or other runtime diagnostics; they are not user-semantic evidence.\n\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANDIDATE GOAL IDS JSON:\n{self._bounded_json([item.get('goal_id') for item in candidate_goals], 1600)}"
        )

    def _build_repair_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        raw: dict[str, Any],
        validation_error: str,
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        skill_section = agent_skill_prompt_section(
            context,
            agent_role="goal_association",
        )
        if output_type is GoalSegmentationModelOutput:
            contract_name = "Goal Segmentation"
            revision_action = "Re-evaluate the independent goal segmentation"
            state_instructions = (
                "There are no active or retained recent Goals. Existing-goal associations are structurally invalid and must not appear. "
                "Re-segment every independently satisfiable responsibility into new_goals, or return only a clarification when the human-level outcome is materially ambiguous or still lacks material semantic information required to define what Chromie owes. "
                "A standalone social interaction is one conversational Goal and must not be returned as an empty goal list. A greeting attached to substantive work is framing, not a second Goal. Identity and personality shape wording only and never create a Goal. A lookup plus an interpretation derived from the same result is one Goal. "
            )
            output_instructions = (
                "The exact GoalSegmentationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
                "Return only decision, new_goals, referent_updates, resolved_references, clarification, confidence, and reason_summary. "
            )
        else:
            contract_name = "Goal Association"
            revision_action = "Re-evaluate the semantic associations"
            state_instructions = (
                "Re-evaluate continuity against only the supplied bounded candidate Goal IDs. "
                "The final authoritative user turn owns the current communicative responsibility. A completed task may supply context, but a reaction, feeling, evaluation, acknowledgement, or practical decision about that context is normally a fresh vocal_output Goal rather than continuation or reference. Existing Goal bindings are provenance-stable and cannot be changed by an association. If current user meaning changes a material binding, use decision=create_goals with one fully bound replacement Goal rather than a description-only association. "
            )
            output_instructions = (
                "The exact GoalAssociationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
                "Return only decision, associations, new_goals, referent_updates, resolved_references, clarification, confidence, and reason_summary. "
            )
        return (
            f"The previous minimal {contract_name} semantic DTO failed its exact contract. {revision_action} and "
            "return one corrected JSON object. Preserve valid semantic judgments, but revise every field needed to satisfy "
            "the schema and validation errors. Do not explain the correction and do not use synonym substitution rules.\n\n"
            + state_instructions
            + "The supplied pre-association route and intent are advisory only. Reconstruct semantic Goals from the authoritative user turn and bounded Goal state; do not preserve a clarification branch merely because an earlier stage selected route=clarify.\n\n"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            + "\n\nResolved references are only for indirect references bound to a supplied discourse referent or active Goal binding. Direct explicit entity mentions belong in Goal bindings and salient referent updates, not resolved_references. For an indirect location binding, copy the supplied referent_id into both the location binding and resolved_references, copy the indirect user surface into resolved_references.surface_form, and retain the referent canonical value. Every resolved reference and referent update must include explicit confidence.\n\nOwner-approved Chromie identity JSON:\n"
            + identity_json
            + "\n\nOwner-approved Personality Expression JSON:\n"
            + personality_json
            + "\n\n"
            + skill_section
            + f"Latest user turn:\n{request.text}\n\n"
            "For a location named directly in that user turn, copy the complete location binding value verbatim as one contiguous span. Never translate, transliterate, shorten, or expand it. Do not ask the user for provider canonicalization or extra administrative granularity merely because multiple real-world places might share the supplied value; bind it exactly and let the downstream Capability resolve it or report provider ambiguity. Only an indirect reference resolved from a supplied referent may use the referent's canonical value.\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 7000)}\n\n"
            "Bounded live Situation projection JSON (soft/revisable relevance only):\n"
            f"{self._bounded_json(self._situation_projection(request), 3600)}\n\n"
            "Bounded active task/progress snapshots JSON:\n"
            f"{self._bounded_json(context.get('active_task_snapshots') or [], 5200)}\n\n"
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON:\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "Use recent conversation as accepted dialogue evidence for follow-up meaning, while bounded Goal and Task state remains the authority for already-validated semantic work. A newer failed or terminal-without-canonical-Goal dialogue turn remains relevant context and must not be skipped solely because an older Goal has canonical state. Never invent a Goal ID merely because dialogue implies an earlier turn is still being processed.\n\n"
            "Previous model output JSON:\n"
            f"{self._bounded_json(raw, 5000)}\n\n"
            "Exact validation errors JSON:\n"
            f"{validation_error}\n\n"
            + output_instructions
            + "Select exactly one decision branch. clarification is only a concise user-facing question and must be empty for non-clarify decisions. Each new_goals item contains description, output_mode, optional media_operation, bindings, optional supersedes_goal_ids, and optional provider-neutral resource_responsibility only. Choose output_mode from the work that actually completes the Goal; the Host derives the internal responsibility class, lane, and provider-evidence requirement. media_playback requires one exact media_operation; non-media Goals may omit it. "
            + _EXECUTION_CONTRACT_PROMPT
            + " Preserve one nested resource_responsibility when the responsibility is genuinely to acquire and deliver a physical object or grounded information; never add it to a vocal performance or insert provider details. It is the sole writable resource authority. Use kind=information with output_mode=capability_work, query_scope for all requested information facts, and a narrow source object that can only delegate, remain unknown, or name one explicit information source. Use kind=physical_object with output_mode=body_action, delivery_mode=physical_handover, and source.acquisition_bindings as the sole spatial/acquisition fact surface. Never duplicate one fact across fields and never create top-level Goal bindings for a resource Goal. For a semantically resolved local day part, use entity_type=day_part with canonical value morning, afternoon, evening, or tonight. Never repair missing human-level scope by inventing a default: if authoritative user, discourse, retained-Goal, and Situation context cannot resolve what Chromie owes, return top-level clarification. Preserve or repair explicit discourse resolution and referent updates; never use tool-result contents to infer a reference. "
            "The host owns every ID and persistence field. Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    def _layered_prompt(
        self,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        *,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        identity_world = self._stable_identity_world_layer(context)
        skill_contract = agent_skill_prompt_section(
            context,
            agent_role="goal_association",
        )
        rendered = self._build_prompt(
            request,
            candidate_goals,
            output_type=output_type,
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
                _EXECUTION_CONTRACT_PROMPT,
            ),
            capability_contract=(skill_contract,),
        )

    def _layered_repair_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        raw: dict[str, Any],
        validation_error: str,
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        identity_world = self._stable_identity_world_layer(context)
        skill_contract = agent_skill_prompt_section(
            context,
            agent_role="goal_association",
        )
        rendered = self._build_repair_prompt(
            request=request,
            candidate_goals=candidate_goals,
            turn_id=turn_id,
            output_type=output_type,
            raw=raw,
            validation_error=validation_error,
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
                _EXECUTION_CONTRACT_PROMPT,
            ),
            capability_contract=(skill_contract,),
        )

    @staticmethod
    def _stable_identity_world_layer(context: dict[str, Any]) -> str:
        return (
            "Owner-approved Chromie identity JSON:\n"
            f"{bounded_identity_json(context)}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{bounded_personality_json(context)}\n\n"
        )


    @staticmethod
    def _responsibility_coverage_required(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
    ) -> bool:
        """Audit every newly proposed Goal set and no non-creation branch.

        This is a structural transition, not a Host semantic risk heuristic.
        Association-only and clarification results have no candidate new-Goal set
        for this certificate to prove.
        """

        del request
        return bool(model_output.new_goals)


    @staticmethod
    def _coverage_certificate_response_schema(
        goal_count: int,
    ) -> dict[str, Any]:
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
            ]
            indices = item_schema.get("properties", {}).get(
                "candidate_goal_indices"
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
                                "coverage": {"enum": ["covered"]},
                                "independently_satisfiable": {"enum": [False]},
                                "candidate_goal_indices": {"maxItems": 0},
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
                                "independently_satisfiable": {"enum": [False]}
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "role": {
                                    "enum": ["responsibility", "constraint"]
                                },
                                "coverage": {"enum": ["covered"]},
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
                                    "enum": [
                                        "missing",
                                        "clarification_required",
                                    ]
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
        schema["required"] = ["items", "reason_summary"]
        schema["additionalProperties"] = False
        return schema

    @classmethod
    def _validate_coverage_certificate(
        cls,
        raw: Any,
        *,
        request: CognitiveWorkRequest,
        goal_count: int,
    ) -> GoalResponsibilityCoverageCertificate:
        if not isinstance(raw, dict):
            raise OllamaGenerationError(
                "goal-association responsibility coverage is not a JSON object",
                failure_class="structured_output_invalid",
                failure_domain="model_contract",
                architecture_attribution="not_evaluated",
                retryable=True,
            )
        normalized_raw = copy.deepcopy(raw)
        normalized_items = normalized_raw.get("items")
        recoveries: list[dict[str, Any]] = []
        if isinstance(normalized_items, list):
            for item_index, item in enumerate(normalized_items):
                if not isinstance(item, dict):
                    continue
                coverage = str(item.get("coverage") or "")
                indices = item.get("candidate_goal_indices")
                if not isinstance(indices, list) or not indices:
                    continue
                if coverage == "missing":
                    # "missing" plus a named attempted owner is structurally
                    # contradictory. Preserve the attempted owner but keep the
                    # certificate rejecting by normalizing to representation mismatch.
                    item["coverage"] = "representation_mismatch"
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "from": "missing",
                            "to": "representation_mismatch",
                            "candidate_goal_indices": list(indices),
                        }
                    )
                elif coverage == "clarification_required":
                    # Unresolved human meaning cannot have a Goal owner yet. Dropping
                    # the indices preserves the rejecting/clarification verdict.
                    item["candidate_goal_indices"] = []
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "from": "clarification_required_with_owner",
                            "to": "clarification_required",
                            "candidate_goal_indices": [],
                        }
                    )
        if recoveries:
            logger.warning(
                "goal_association_coverage_shape_normalized sid=%s recoveries=%s",
                request.sid,
                cls._bounded_json(recoveries, 1800),
            )
        certificate = GoalResponsibilityCoverageCertificate.model_validate(normalized_raw)
        authoritative_turn = " ".join(request.text.strip().split()).casefold()
        for index, item in enumerate(certificate.items):
            excerpt = " ".join(item.source_excerpt.strip().split()).casefold()
            if excerpt not in authoritative_turn:
                raise ValueError(
                    "coverage source_excerpt must be a verbatim current-turn span: "
                    f"items[{index}]={item.source_excerpt!r}"
                )
            invalid_indices = [
                goal_index
                for goal_index in item.candidate_goal_indices
                if goal_index < 0 or goal_index >= goal_count
            ]
            if invalid_indices:
                raise ValueError(
                    "coverage references unknown Goal candidate indices: "
                    + ",".join(str(value) for value in invalid_indices)
                )
        return certificate

    @staticmethod
    def _coverage_verdict(
        certificate: GoalResponsibilityCoverageCertificate,
        *,
        goal_count: int,
    ) -> tuple[Literal["accept", "reject"], list[str]]:
        problems: list[str] = []
        responsibility_owner_counts: dict[int, int] = {}
        positively_owned: set[int] = set()
        for item in certificate.items:
            if item.role in {"responsibility", "constraint"} and item.coverage != "covered":
                problems.append(
                    f"{item.coverage}:{item.role}:{item.source_excerpt}"
                )
            if item.role != "responsibility" or item.coverage != "covered":
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

    def _build_fresh_interpretation_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        problems: list[str],
        force_clarification: bool = False,
    ) -> str:
        terminal_instruction = (
            "The independent proof established that material meaning is unresolved. "
            "Return decision=clarify with exactly one concise question that asks for "
            "that missing meaning; do not create or associate Goals. "
            if force_clarification
            else ""
        )
        return (
            self._build_prompt(
                request,
                candidate_goals,
                output_type=output_type,
            )
            + "\n\nAn independent source-grounded coverage proof rejected the "
            "first candidate set. Discard that candidate DTO as authority and perform "
            "one final fresh interpretation from the FINAL AUTHORITATIVE USER TURN. "
            "Do not discard independently supported current-turn Responsibility evidence: "
            "the Fast responsibility proposals rendered above remain provider-neutral "
            "semantic evidence and must be re-checked against the authoritative turn. "
            "The FINAL AUTHORITATIVE USER TURN remains the source for explicit material "
            "qualifiers: if a proposal or rejected candidate generalized away severity, "
            "intensity, magnitude, threshold, subtype, negation, comparison, quantity, or "
            "scope, restore that source-grounded WHAT in the final Goal representation. "
            "Planner Activity metadata is never a Responsibility source and must not be "
            "preserved as a Goal. "
            "Removing an unjustified sibling Goal never permits dropping a still-supported "
            "human Responsibility. The following compact defects are proof feedback, not "
            "Goal labels and not permission to copy a previous DTO:\n"
            + self._bounded_json(problems, 3000)
            + "\n"
            + terminal_instruction
            + "Return one complete final DTO. This interpretation receives no "
            "contract repair; invalid or incomplete output fails closed."
        )

    @staticmethod
    def _responsibility_coverage_system_prompt() -> str:
        return (
            "You are Chromie's independent Goal responsibility-coverage auditor. "
            "Read the authoritative user turn from scratch and compare its semantic "
            "requirements with the supplied zero-based Goal candidates. Enumerate "
            "material responsibilities, constraints, context, and conversational "
            "framing without planning or selecting capabilities. Audit not only Goal "
            "ownership but whether the candidate represents the same kind of human "
            "outcome. A future reminder, list mutation, state change, message delivery, "
            "or other persistent effect is not an information resource merely because "
            "words or data are involved. Conversely, an immediate judgment, choice, "
            "prioritization, or advice that needs no fresh external/private/runtime "
            "evidence is conversational reasoning rather than information acquisition. "
            "Use coverage=representation_mismatch when a candidate clearly attempts to "
            "own the fragment but represents it incorrectly, including wrong completion "
            "semantics or a dropped/generalized material qualifier, binding, result aspect, "
            "severity, threshold, or scope. In that case identify the mismatched candidate "
            "index. Use coverage=missing only when no candidate attempts to own the fragment, "
            "with no candidate indices. A positive observable "
            "outcome the user can independently judge is a responsibility, not a "
            "constraint or decoration. Do not invent a vocal outcome from a broad "
            "social impression when no words, information, or vocal performance were "
            "requested. Audit reference grounding too: an unresolved pronoun, "
            "demonstrative, ellipsis, correction, or other indirect reference cannot "
            "be treated as resolved merely because a candidate description invented "
            "a plausible referent. Use clarification_required when no supplied turn or "
            "dialogue evidence uniquely grounds material meaning. Trusted code derives "
            "whether any Goal candidate lacks a "
            "positive responsibility owner. Return JSON only."
        )


    def _build_responsibility_coverage_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        raw: dict[str, Any],
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        return (
            "Audit whether this candidate Goal segmentation completely accounts for "
            "the authoritative user's current semantic responsibilities. This is an "
            "independent audit: candidate Goal wording is not evidence that the "
            "segmentation is complete by itself. Inspect the complete candidate DTO: "
            "description, output_mode, typed bindings, resource responsibility, and "
            "source/recipient fields are the evidence for what each candidate "
            "actually represents. Do not call a constraint missing when those fields "
            "materially preserve it on the Goal that it modifies.\n\n"
            "For each semantically material fragment of the current turn, emit one "
            "items entry and copy source_excerpt as a verbatim contiguous span from "
            "the FINAL AUTHORITATIVE USER TURN. Use role=responsibility for a positive "
            "outcome Chromie owes, role=constraint for a modifier/prohibition/timing "
            "condition on such an outcome, role=context for reference/background that "
            "does not itself need completion, and role=framing for politeness or social "
            "preamble attached to substantive work. Stated preferences, reasons, "
            "candidate options, and background facts that merely constrain one requested "
            "decision are context or constraints, not independent responsibilities, "
            "unless the user separately asks for an observable outcome for each. A "
            "manner, mood, persona, or social-"
            "presentation modifier attached to a requested effect is role=constraint "
            "on that effect; it is not a second responsibility merely because speech "
            "could also convey the style. When a concrete effect is requested together "
            "with a broad desired social impression but no words, information, vocal "
            "performance, or second effect modality is specified, that impression is "
            "embodiment-wide framing on the concrete effect. Do not infer speech from "
            "an adjective, state directive, conjunction, or imperative grammar. Emit "
            "each semantic fragment once: never duplicate the same source_excerpt "
            "under both responsibility and constraint (or any other conflicting "
            "roles); decide its one actual role.\n\n"
            "Set independently_satisfiable=true only when the user could reasonably "
            "judge that positive outcome completed even if sibling outcomes did not "
            "happen. A factual lookup and an interpretation requested from that same "
            "evidence form one responsibility when one result satisfies both. Multiple "
            "aspects requested from one information result likewise remain one "
            "responsibility; for example, precipitation plus whether the returned "
            "temperature is cold are not independent merely because either aspect can "
            "be described separately. Represent their contiguous request as one "
            "responsibility and set independently_satisfiable=false. Every genuinely "
            "independently satisfiable responsibility must own its own "
            "Goal candidate. Do not collapse separately observable requested effects "
            "merely because they can overlap in time, share one sentence, or use a "
            "common provider. For acquire-and-deliver meaning, apply the inverse "
            "counterfactual too: navigation, distance, direction, locating, pickup, "
            "carrying, return, and handoff are not independent positive outcomes when "
            "the person would consider them satisfied by successful resource delivery "
            "and would not still require that stage for its own sake. In that case map "
            "the material fragment as a constraint on the one resource responsibility, "
            "not as ownership evidence for another Goal. Conversely, do "
            "not promote greeting/politeness framing, implementation steps, result "
            "delivery, or a negative speech boundary into a separate Goal.\n\n"
            "For coverage=covered, map a responsibility to exactly one candidate Goal "
            "index; a constraint may map to one or more affected Goal indices. Use "
            "coverage=missing only when a responsibility or constraint has no Goal "
            "candidate attempting to own it, and then candidate_goal_indices must be empty. "
            "If a candidate attempts to own the fragment but drops or generalizes a material "
            "qualifier, binding, result aspect, severity/intensity, threshold, subtype, "
            "comparison, or scope, use coverage=representation_mismatch and include that "
            "candidate index instead. clarification_required only when the human-level responsibility itself "
            "cannot be determined without asking the user. Context and framing "
            "acknowledge non-owed meaning rather than requiring ownership: they must "
            "always use coverage=covered, independently_satisfiable=false, and an "
            "empty candidate_goal_indices list. Never mark context or framing as "
            "missing or clarification_required. For a represented constraint, the expected shape is "
            "role=constraint, independently_satisfiable=false, coverage=covered, and "
            "the affected Goal index or indices. Never mark a constraint missing "
            "merely because it is not a responsibility, has no separate Goal, or is "
            "an instrumental provider stage; mark it missing only when no candidate "
            "DTO field preserves it on the outcome that it modifies. Coverage also "
            "requires the candidate's output_mode, resource shape, and observable "
            "completion meaning to match the requested responsibility. Use "
            "coverage=representation_mismatch when a state mutation or deferred effect "
            "(recording/updating something, scheduling a future notification, or sending "
            "something later) is represented as an information resource, when provider-"
            "backed evidence work is represented as ordinary speech, or when immediate "
            "reasoning/advice with no fresh evidence need is represented as external "
            "information acquisition. Speech cannot cover requested body motion, media "
            "control, external evidence work, or a vocal performance. Every Goal "
            "candidate must be "
            "justified by at least one covered role=responsibility item; a constraint "
            "alone never justifies another Goal. Do not author a top-level verdict or "
            "unjustified-candidate inventory; trusted code derives both from the item "
            "judgments. A resource Goal's nested typed resource fields are authoritative; "
            "its human-readable description cannot supply or override a missing resource "
            "fact, and a material contradiction between summary and typed truth is not "
            "covered. For an information resource, requested location, time, and result "
            "aspects are covered only by resource_responsibility.query_scope; its narrow "
            "source object cannot own those query facts. For a physical resource, an "
            "acquisition location, distance, direction, or route constraint is covered "
            "only by resource_responsibility.source.acquisition_bindings. Descriptions "
            "are summary only. The schema deliberately exposes one writable owner per "
            "resource fact, so coverage must never infer a missing typed fact from prose. "
            "Classify the meaning in context; "
            "do not decide its role from a field name alone.\n\n"
            "Reference grounding is part of responsibility coverage. Before assigning "
            "coverage, explicitly identify each material indirect referring expression "
            "in the authoritative turn and audit its grounding independently. A material "
            "pronoun, demonstrative, ellipsis, correction, or other indirect "
            "reference is covered only when the candidate copies an explicit current-"
            "turn value or a supplied discourse referent with its referent_id. A "
            "candidate description that silently invents a generic object, device, "
            "person, task, or setting does not resolve the reference. Mark the "
            "containing responsibility or constraint clarification_required when the "
            "supplied evidence does not select exactly one meaning, including when "
            "multiple scene candidates remain plausible. Candidate prose alone cannot "
            "ground an indirect target; require the explicit current-turn value or the "
            "typed referent-backed binding before marking it covered.\n\n"
            "Do not add, remove, rename, plan, execute, or complete Goals. Do not use "
            "provider availability to decide whether a responsibility exists. An "
            "unavailable requested effect remains a responsibility.\n\n"
            "Candidate Goal DTO JSON:\n"
            f"{self._bounded_json(raw, 9000)}\n\n"
            "Recent conversation JSON (reference context only; current-turn Goal "
            "coverage must still be anchored by source_excerpt from the final turn):\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-6:], 3000)}\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )


    @staticmethod
    def _semantic_review_system_prompt(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        *,
        fresh_resegmentation: bool = False,
    ) -> str:
        contract_name = (
            "Goal Segmentation"
            if output_type is GoalSegmentationModelOutput
            else "Goal Association"
        )
        return (
            f"You are Chromie's independent semantic reviewer for the "
            f"{contract_name} boundary. "
            + (
                "Perform a fresh segmentation from the authoritative user turn; "
                "no earlier Goal labels are evidence and none are available to copy. "
                if fresh_resegmentation
                else "Review the supplied DTO without assuming it is correct. "
            )
            + "Decide with model reasoning whether responsibilities are genuinely "
            "independent and classify each by its completion channel. An authored "
            "vocal performance belongs to vocal_output even when coordinated "
            "with embodied work. Return only the complete final DTO as JSON. The "
            "Host owns validation, IDs, lifecycle, and persistence and does not make "
            "this semantic choice."
        )

    @staticmethod
    def _repair_system_prompt(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        contract_name = (
            "Goal Segmentation"
            if output_type is GoalSegmentationModelOutput
            else "Goal Association"
        )
        return (
            f"You repair one minimal {contract_name} semantic DTO using semantic reasoning and the supplied exact JSON Schema. "
            "Return only the corrected JSON object. Do not add commentary, markdown, lexical mappings, or hidden reasoning."
        )

    @staticmethod
    def _system_prompt(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        if output_type is GoalSegmentationModelOutput:
            return (
                "You are Chromie's Goal Segmentation model. No active or retained recent Goal IDs exist, so association with existing work is impossible. "
                "Use semantic reasoning to resolve current-turn references from scoped discourse context and preserve independently satisfiable user responsibilities as separate new Goals, but never turn plan steps into goals. "
                "Conversational framing attached to a substantive responsibility is not independently satisfiable work: do not create a separate Goal for its greeting or politeness preamble. A standalone social interaction remains one conversational Goal. "
                "When one evidence acquisition satisfies both a factual lookup and the requested interpretation of its result, preserve them as one Goal. "
                "Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
                "You are advisory only and never execute or commit. Return JSON only."
            )
        return (
            "You are Chromie's Goal Association and Segmentation model. Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
            "Apply continuity before creation. Resolve references from current user meaning, scoped discourse referents/focus, bounded candidate Goals and their bindings, and dialogue context. Candidate Goals may be active, recoverable, or recently terminal; referencing a terminal Goal does not reopen it. Tool-result memory is not reference-resolution authority. Status follow-ups about an unfinished lookup should associate with the bound task; if its safe read is recoverable, preserve the exact skill arguments for retry. Do not treat another task's evidence as completion. "
            "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
            "Preserve independent user responsibilities as separate goals, but never turn plan steps into goals. "
            "Conversational framing attached to substantive work is not a separate Goal; a standalone social interaction remains one conversational Goal. A new reaction, feeling, evaluation, acknowledgement, or practical decision after a prior result is a current conversational responsibility, not continuation of the completed lookup. One lookup and an interpretation requested as part of that same lookup are one Goal. "
            "You are advisory only and never execute or commit. Return JSON only."
        )

    def _expand_model_output(
        self,
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
        turn_id: str,
    ) -> GoalAssociationResolution:
        candidate_goals = self._candidate_goals(request)
        active_goal_ids = {
            str(item.get("goal_id") or "").strip()
            for item in candidate_goals
            if str(item.get("goal_id") or "").strip()
        }
        existing_referents = {
            str(item.get("referent_id") or "").strip(): item
            for item in self._discourse_referents(request)
            if str(item.get("referent_id") or "").strip()
        }

        associations: list[GoalAssociation] = []
        model_associations = (
            model_output.associations
            if isinstance(model_output, GoalAssociationModelOutput)
            else []
        )
        for index, item in enumerate(model_associations):
            goal_update: dict[str, Any] = {}
            if item.updated_description:
                goal_update["description"] = item.updated_description
            associations.append(
                GoalAssociation(
                    association_id=stable_goal_operation_id(
                        turn_id=turn_id,
                        ordinal=index,
                        relationship=item.relationship,
                        target_goal_ids=item.target_goal_ids,
                    ),
                    relationship=item.relationship,
                    target_goal_ids=item.target_goal_ids,
                    confidence=item.confidence,
                    reason_summary=item.reason_summary,
                    goal_update=goal_update,
                    resolved_gap_ids=item.resolved_gap_ids,
                    requires_replan=(
                        item.requires_replan
                        or item.relationship
                        in {"modify", "clarify", "merge", "split"}
                    ),
                )
            )

        # Host generates canonical Goal IDs first so newly introduced referents
        # can be scoped to the Goals whose bindings use them.
        generated_goal_ids: list[str] = []
        for index, item in enumerate(model_output.new_goals):
            digest = hashlib.sha256(
                f"{turn_id}|goal|{index}|{item.description}".encode("utf-8")
            ).hexdigest()[:20]
            generated_goal_ids.append(f"goal_{digest}")

        referent_updates: list[DiscourseReferentUpdate] = []
        introduced_by_value: dict[tuple[str, str], str] = {}
        for index, item in enumerate(model_output.referent_updates):
            if item.confidence < self.min_confidence:
                raise ValueError(
                    "discourse referent update is below confidence threshold"
                )
            unknown_targets = [
                referent_id
                for referent_id in item.target_referent_ids
                if referent_id not in existing_referents
            ]
            if unknown_targets:
                raise ValueError(
                    "referent update targets unknown referent IDs: "
                    + ",".join(unknown_targets)
                )
            unknown_goals = [
                goal_id
                for goal_id in item.target_goal_ids
                if goal_id not in active_goal_ids
            ]
            if unknown_goals:
                raise ValueError(
                    "referent update targets unknown active Goal IDs: "
                    + ",".join(unknown_goals)
                )

            referent: DiscourseReferent | None = None
            if item.operation in {"introduce", "correct"}:
                referent_id = stable_referent_id(
                    turn_id=turn_id,
                    ordinal=index,
                    entity_type=item.entity_type,
                    canonical_value=item.canonical_value,
                )
                matching_new_goal_ids = [
                    goal_id
                    for goal_id, goal_item in zip(
                        generated_goal_ids,
                        model_output.new_goals,
                        strict=True,
                    )
                    if any(
                        binding.entity_type.casefold()
                        == item.entity_type.casefold()
                        and binding.value.casefold()
                        == item.canonical_value.casefold()
                        for binding in goal_item.semantic_bindings
                    )
                ]
                source_goal_ids = list(
                    dict.fromkeys([*item.target_goal_ids, *matching_new_goal_ids])
                )
                scope_ids = (
                    source_goal_ids
                    if item.scope_kind == "goal"
                    else item.target_goal_ids
                    if item.scope_kind == "task"
                    else []
                )
                referent = DiscourseReferent(
                    referent_id=referent_id,
                    entity_type=item.entity_type,
                    canonical_value=item.canonical_value,
                    aliases=item.aliases,
                    scope_kind=item.scope_kind,
                    scope_ids=scope_ids,
                    status="foreground",
                    confidence=item.confidence,
                    source_turn_id=turn_id,
                    source_goal_ids=source_goal_ids,
                    supersedes_referent_ids=(
                        item.target_referent_ids
                        if item.operation == "correct"
                        else []
                    ),
                    reason_summary=item.reason_summary,
                    metadata={
                        "model_boundary": type(model_output).__name__,
                        "host_generated_fields": True,
                    },
                )
                introduced_by_value[
                    (item.entity_type.casefold(), item.canonical_value.casefold())
                ] = referent_id
            referent_updates.append(
                DiscourseReferentUpdate(
                    operation=item.operation,
                    referent=referent,
                    target_referent_ids=item.target_referent_ids,
                    confidence=item.confidence,
                    reason_summary=item.reason_summary,
                )
            )

        resolved_references: list[ResolvedDiscourseReference] = []
        for item in model_output.resolved_references:
            referent_id = item.referent_id or introduced_by_value.get(
                (item.entity_type.casefold(), item.resolved_value.casefold()),
                "",
            )
            if item.source in {"discourse_referent", "active_goal_binding"}:
                if referent_id not in existing_referents:
                    raise ValueError(
                        f"resolved reference uses unknown referent_id={referent_id!r}"
                    )
                expected = existing_referents[referent_id]
                if (
                    str(expected.get("entity_type") or "").casefold()
                    != item.entity_type.casefold()
                    or str(expected.get("canonical_value") or "").casefold()
                    != item.resolved_value.casefold()
                ):
                    raise ValueError(
                        "resolved reference value does not match supplied referent"
                    )
            if item.confidence < self.min_confidence:
                raise ValueError(
                    "material reference resolution is below confidence threshold"
                )
            resolved_references.append(
                ResolvedDiscourseReference(
                    surface_form=item.surface_form,
                    entity_type=item.entity_type,
                    resolved_value=item.resolved_value,
                    source=item.source,
                    referent_id=referent_id or None,
                    confidence=item.confidence,
                    reason_summary=item.reason_summary,
                )
            )

        resolved_reference_by_value = {
            (item.entity_type.casefold(), item.resolved_value.casefold()): item
            for item in resolved_references
        }
        new_goals: list[SemanticGoal] = []
        for goal_id, item in zip(
            generated_goal_ids,
            model_output.new_goals,
            strict=True,
        ):
            def normalize_binding(
                binding: GoalAssociationModelBinding,
            ) -> dict[str, Any]:
                referent_id = binding.referent_id
                if not referent_id:
                    introduced = introduced_by_value.get(
                        (binding.entity_type.casefold(), binding.value.casefold())
                    )
                    if introduced:
                        referent_id = introduced
                    else:
                        resolved = resolved_reference_by_value.get(
                            (binding.entity_type.casefold(), binding.value.casefold())
                        )
                        referent_id = (resolved.referent_id if resolved else None) or ""
                if referent_id and (
                    referent_id not in existing_referents
                    and referent_id not in introduced_by_value.values()
                ):
                    raise ValueError(
                        f"goal binding uses unknown referent_id={referent_id!r}"
                    )
                normalized = GoalEntityBinding(
                    name=binding.name,
                    entity_type=binding.entity_type,
                    value=binding.value,
                    referent_id=referent_id or None,
                    confidence=binding.confidence,
                )
                return normalized.model_dump(
                    mode="json",
                    exclude_none=True,
                )

            binding_map: dict[str, Any] = {}
            resource_responsibility = None
            if item.resource_responsibility is not None:
                resource_item = item.resource_responsibility
                recipient_referent_id = resource_item.recipient.referent_id
                if (
                    recipient_referent_id
                    and recipient_referent_id not in existing_referents
                    and recipient_referent_id not in introduced_by_value.values()
                ):
                    raise ValueError(
                        "resource recipient uses unknown referent_id="
                        f"{recipient_referent_id!r}"
                    )

                if resource_item.kind == "information":
                    attribute_bindings = {
                        binding.name: normalize_binding(binding)
                        for binding in resource_item.query_scope
                    }
                    source_bindings: dict[str, Any] = {}
                    source_description = ""
                    if resource_item.source.status == "known":
                        source_binding = GoalAssociationModelBinding(
                            name="source",
                            entity_type="information_source",
                            value=resource_item.source.source_name,
                            referent_id=resource_item.source.referent_id or "",
                            confidence=resource_item.source.confidence,
                        )
                        source_bindings["source"] = normalize_binding(source_binding)
                        source_description = resource_item.source.source_name
                    resource_responsibility = AcquireAndDeliverResource(
                        resource=ResourceDescriptor(
                            kind="information",
                            description=resource_item.description,
                            quantity=resource_item.quantity,
                            attributes=attribute_bindings,
                        ),
                        source=ResourceSource(
                            status=resource_item.source.status,
                            description=source_description,
                            bindings=source_bindings,
                        ),
                        recipient=ResourceRecipient(
                            description=resource_item.recipient.description,
                            referent_id=recipient_referent_id,
                        ),
                        delivery_mode=resource_item.delivery_mode,
                    )
                else:
                    source_bindings = {
                        binding.name: normalize_binding(binding)
                        for binding in resource_item.source.acquisition_bindings
                    }
                    resource_responsibility = AcquireAndDeliverResource(
                        resource=ResourceDescriptor(
                            kind="physical_object",
                            description=resource_item.description,
                            quantity=resource_item.quantity,
                            attributes={},
                        ),
                        source=ResourceSource(
                            status=resource_item.source.status,
                            description=resource_item.source.description,
                            bindings=source_bindings,
                        ),
                        recipient=ResourceRecipient(
                            description=resource_item.recipient.description,
                            referent_id=recipient_referent_id,
                        ),
                        delivery_mode="physical_handover",
                    )
            else:
                for binding in item.bindings:
                    normalized = normalize_binding(binding)
                    if binding.name in binding_map:
                        raise ValueError(
                            f"duplicate Goal binding name={binding.name!r}"
                        )
                    binding_map[binding.name] = normalized

            unknown_related_goal_ids = sorted(
                set(item.related_goal_ids) - active_goal_ids
            )
            if unknown_related_goal_ids:
                raise ValueError(
                    "new Goal references unknown related Goal IDs: "
                    + ", ".join(unknown_related_goal_ids)
                )
            unknown_superseded_goal_ids = sorted(
                set(item.supersedes_goal_ids) - active_goal_ids
            )
            if unknown_superseded_goal_ids:
                raise ValueError(
                    "replacement Goal references unknown superseded Goal IDs: "
                    + ", ".join(unknown_superseded_goal_ids)
                )
            if set(item.related_goal_ids).intersection(item.supersedes_goal_ids):
                raise ValueError(
                    "replacement Goal cannot also retain a superseded Goal as related context"
                )
            new_goals.append(
                SemanticGoal(
                    goal_id=goal_id,
                    description=item.description,
                    source_text=request.text,
                    object={"bindings": binding_map} if binding_map else {},
                    constraints={},
                    success_criteria=[item.description],
                    resource_responsibility=resource_responsibility,
                    related_goal_ids=item.related_goal_ids,
                    supersedes_goal_ids=item.supersedes_goal_ids,
                    metadata={
                        "model_boundary": type(model_output).__name__,
                        "host_generated_fields": True,
                        "responsibility_kind": item.responsibility_kind,
                        "execution_lane": item.execution_lane,
                        "output_mode": item.output_mode,
                        "provider_required": item.provider_required,
                        "media_operation": item.media_operation,
                        "resolved_references": [
                            reference.model_dump(mode="json", exclude_none=True)
                            for reference in resolved_references
                        ],
                    },
                )
            )


        return GoalAssociationResolution(
            turn_id=turn_id,
            resolution_status=(
                "needs_clarification"
                if model_output.clarification
                else "resolved"
            ),
            associations=associations,
            new_goals=new_goals,
            referent_updates=referent_updates,
            resolved_references=resolved_references,
            clarification=model_output.clarification,
            confidence=model_output.confidence,
            reason_summary=model_output.reason_summary,
            metadata={
                "model_contract": type(model_output).__name__,
                "host_generated_identifiers": True,
                "discourse_resolution_authority": "goal_association_llm",
            },
        )

    def _validate(
        self,
        resolution: GoalAssociationResolution,
        *,
        candidate_goals: list[dict[str, Any]],
        request: CognitiveWorkRequest,
    ) -> GoalAssociationResolution:
        candidate_ids = {
            str(item.get("goal_id") or "") for item in candidate_goals
        }
        accepted: list[GoalAssociation] = []
        rejected: list[dict[str, Any]] = []
        for association in resolution.associations:
            reason = None
            if association.confidence < self.min_confidence:
                reason = "below_confidence_threshold"
            elif any(
                goal_id not in candidate_ids
                for goal_id in association.target_goal_ids
            ):
                reason = "unknown_target_goal"
            if reason:
                rejected.append({"association_id": association.association_id, "reason": reason})
            else:
                accepted.append(association)

        if resolution.clarification:
            accepted = []
            new_goals: list[SemanticGoal] = []
        else:
            new_goals = resolution.new_goals

        metadata = dict(resolution.metadata)
        metadata.update(
            {
                "resolver": "goal_association_agent",
                "status": "resolved",
                "candidate_goal_count": len(candidate_goals),
                "accepted_association_count": len(accepted),
                "new_goal_count": len(new_goals),
                "referent_update_count": len(resolution.referent_updates),
                "resolved_reference_count": len(resolution.resolved_references),
                "rejected_associations": rejected,
                "min_confidence": self.min_confidence,
                "sid": request.sid,
                "authority": "advisory",
            }
        )
        if (
            not accepted
            and not new_goals
            and not resolution.referent_updates
            and not resolution.clarification
        ):
            return GoalAssociationResolution(
                turn_id=resolution.turn_id,
                resolution_status="needs_clarification",
                clarification=self._safe_clarification(
                    request,
                    has_candidate_goals=bool(candidate_goals),
                ),
                confidence=0.0,
                reason_summary="No sufficiently grounded goal association or new goal was accepted.",
                metadata={**metadata, "status": "needs_clarification"},
            )
        return resolution.model_copy(update={"associations": accepted, "new_goals": new_goals, "metadata": metadata})

    @staticmethod
    def _safe_clarification(
        request: CognitiveWorkRequest,
        *,
        has_candidate_goals: bool,
    ) -> str:
        if has_candidate_goals:
            return (
                "你是在继续刚才的事情，还是想开始一件新的事情？"
                if (request.language or "").startswith("zh")
                else "Is this about what we were already doing, or is it a new request?"
            )
        return (
            "我还没能可靠地分清你想完成的事情，可以换一种说法吗？"
            if (request.language or "").startswith("zh")
            else "I couldn't reliably separate the things you want done. Could you rephrase the request?"
        )
