from __future__ import annotations

from .goal_progress_communication import goal_progress_communication_prompt
import copy
import hashlib
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

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
from .schema import AgentRunRequest

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

logger = logging.getLogger("chromie.agent.goal_association")


GoalSegmentationDecision = Literal["create_goals", "clarify"]
GoalAssociationDecision = Literal["associate", "create_goals", "clarify"]
GoalResponsibilityKind = Literal[
    "executable_action",
    "spoken_response",
    "capability_dependent",
    "other",
]
GoalExecutionLane = Literal["speaking", "activity", "none"]
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
_VOCAL_OUTPUT_MODES = frozenset(
    {
        "speech",
        "expressive_speech",
        "recitation",
        "singing",
        "humming",
        "nonverbal_vocalization",
    }
)
_MODE_SPECIFIC_VOCAL_OUTPUTS = _VOCAL_OUTPUT_MODES - {"speech"}
_OUTPUT_MODE_EXECUTION_CONTRACT: dict[
    GoalOutputMode,
    tuple[GoalResponsibilityKind, GoalExecutionLane, bool],
] = {
    "speech": ("spoken_response", "speaking", False),
    "expressive_speech": ("spoken_response", "speaking", True),
    "recitation": ("spoken_response", "speaking", True),
    "singing": ("spoken_response", "speaking", True),
    "humming": ("spoken_response", "speaking", True),
    "nonverbal_vocalization": ("spoken_response", "speaking", True),
    "body_action": ("executable_action", "activity", True),
    "media_playback": ("executable_action", "activity", True),
    "capability_work": ("capability_dependent", "activity", True),
    "other": ("other", "none", False),
}
_FRESH_RESEGMENTATION_TRIGGERS = frozenset(
    {
        "invalid_action_collection_binding",
        "invalid_location_binding_provenance",
        "embodied_responsibility_decomposition",
        "mixed_capability_and_spoken_responsibilities",
        "multi_embodied_responsibility_review",
        "recommendation_route_spoken_responsibility_review",
        "tool_route_spoken_responsibility_review",
        "invalid_typed_execution_contract",
    }
)


class GoalAssociationFreshResegmentationError(ValueError):
    """A mechanical contract defect that must not anchor model repair."""

    def __init__(self, message: str, *, trigger: str) -> None:
        super().__init__(message)
        self.trigger = trigger
_EXECUTION_CONTRACT_PROMPT = (
    "Classify each Goal by the semantic work that must actually complete the "
    "human outcome, not by the channel used later to report that outcome. In the "
    "model-facing Goal JSON, output_mode is the completion discriminant; the Host "
    "deterministically derives responsibility_kind, execution_lane, and "
    "provider_required from that choice, so do not emit or duplicate those "
    "Host-owned invariants. Use capability_work only when completion depends on "
    "fresh external, private, or runtime evidence from a registered non-vocal "
    "Capability. Stable general knowledge, reasoning, creative content, and an "
    "immediate conversational reminder that Chromie can author without fresh "
    "evidence use ordinary speech. Embodied effects use body_action; lifecycle "
    "control of existing media uses media_playback; authored vocal performances "
    "use their exact vocal mode. The fact that a capability result will later be "
    "spoken does not turn its owned work into speech. If no matching provider is "
    "available, preserve the evidence-dependent completion mode so downstream "
    "planning can report the limitation instead of inventing an answer. "
    "media_operation is meaningful only for media_playback; otherwise omit it or "
    "leave it as none. A negative instruction that limits what Chromie may say "
    "while completing another requested outcome is a constraint on that outcome, "
    "not an independently satisfiable spoken Goal."
)


def _execution_contract_error(message: str) -> PydanticCustomError:
    return PydanticCustomError("goal_execution_contract", message)


GoalAssociationModelRelationship = Literal[
    "continue",
    "modify",
    "clarify",
    "confirm",
    "reject",
    "cancel",
    "pause",
    "resume",
    "replace",
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
            "spoken_response Goal even when prior Goal evidence supplies context. "
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
        if self.relationship in {"modify", "clarify", "replace"} and not (
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


class GoalAssociationModelResourceResponsibility(BaseModel):
    """Provider-neutral acquire-and-deliver responsibility emitted by the model."""

    model_config = ConfigDict(extra="forbid")

    resource_kind: Literal["physical_object", "information"]
    resource_description: str = Field(min_length=1)
    source_status: Literal["known", "unknown", "provider_resolved"]
    source_description: str = ""
    source_binding_names: list[str] = Field(default_factory=list, max_length=8)
    recipient_description: str = Field(default="requester", min_length=1)
    delivery_mode: Literal[
        "physical_handover",
        "spoken_explanation",
        "structured_result",
    ]

    @field_validator(
        "resource_description",
        "source_description",
        "recipient_description",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("source_binding_names", mode="before")
    @classmethod
    def normalize_binding_names(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("source_binding_names must be a list or string")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelResourceResponsibility":
        if self.source_status == "known" and not (
            self.source_description or self.source_binding_names
        ):
            raise ValueError(
                "known resource source requires source_description or source_binding_names"
            )
        if self.source_status == "unknown" and (
            self.source_description or self.source_binding_names
        ):
            raise ValueError("unknown resource source must not invent a source")
        if (
            self.resource_kind == "physical_object"
            and self.delivery_mode != "physical_handover"
        ):
            raise ValueError(
                "physical_object resource requires physical_handover delivery"
            )
        if (
            self.resource_kind == "information"
            and self.delivery_mode == "physical_handover"
        ):
            raise ValueError("information resource cannot use physical_handover")
        return self


class GoalAssociationModelGoal(BaseModel):
    """Minimal model-facing semantic goal. IDs and persistence fields are host-owned."""

    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)
    responsibility_kind: GoalResponsibilityKind = Field(
        default="other",
        description=(
            "Host-materialized responsibility class derived from output_mode. "
            "Retained on the validated DTO for downstream compatibility; it is "
            "not a model-facing decision."
        ),
    )
    execution_lane: GoalExecutionLane | None = Field(
        default=None,
        description=(
            "Host-materialized execution lane derived from output_mode; not a "
            "model-facing decision."
        ),
    )
    output_mode: GoalOutputMode | None = Field(
        default=None,
        description=(
            "Semantic work that completes this Goal, not the later channel used "
            "to deliver its result. Choose capability_work when fresh external, "
            "private, or runtime evidence is required; choose speech for directly "
            "authored ordinary conversation; use exact embodied, media, or vocal "
            "modes when those effects are the requested outcome."
        ),
    )
    provider_required: bool | None = Field(
        default=None,
        description=(
            "Host-materialized provider-evidence requirement derived from "
            "output_mode; not a model-facing decision."
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
    resource_responsibility: GoalAssociationModelResourceResponsibility | None = None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @model_validator(mode="before")
    @classmethod
    def materialize_execution_contract(cls, value: Any) -> Any:
        """Derive Host-owned execution invariants from one semantic output mode.

        Live model-facing schemas expose ``output_mode`` but not the redundant
        responsibility/lane/provider fields. Historical fixtures may still supply
        the older fields, so missing ``output_mode`` is inferred from the retained
        responsibility kind before the same deterministic materialization runs.
        Explicit legacy fields are never silently overwritten; the after-validator
        still rejects an inconsistent retained DTO.
        """

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        mode = normalized.get("output_mode")
        if mode is None:
            responsibility = str(normalized.get("responsibility_kind") or "other")
            mode = {
                "spoken_response": "speech",
                "executable_action": "body_action",
                "capability_dependent": "capability_work",
                "other": "other",
            }.get(responsibility, "other")
            normalized["output_mode"] = mode
        contract = _OUTPUT_MODE_EXECUTION_CONTRACT.get(str(mode))
        if contract is not None:
            responsibility, lane, provider_required = contract
            normalized.setdefault("responsibility_kind", responsibility)
            if normalized.get("execution_lane") is None:
                normalized["execution_lane"] = lane
            if normalized.get("provider_required") is None:
                normalized["provider_required"] = provider_required
        if normalized.get("media_operation") is None:
            normalized["media_operation"] = "none"
        return normalized

    @model_validator(mode="after")
    def validate_execution_contract(self) -> "GoalAssociationModelGoal":
        lane = self.execution_lane
        mode = self.output_mode
        provider_required = bool(self.provider_required)

        if self.responsibility_kind == "spoken_response":
            if lane != "speaking" or mode not in _VOCAL_OUTPUT_MODES:
                raise _execution_contract_error(
                    "spoken_response requires execution_lane=speaking and a vocal output_mode"
                )
        elif self.responsibility_kind == "executable_action":
            if lane != "activity" or mode not in {"body_action", "media_playback"}:
                raise _execution_contract_error(
                    "executable_action requires activity lane and body_action or media_playback"
                )
            if not provider_required:
                raise _execution_contract_error(
                    "executable_action requires provider_required=true"
                )
        elif self.responsibility_kind == "capability_dependent":
            if lane != "activity" or mode != "capability_work":
                raise _execution_contract_error(
                    "capability_dependent requires activity lane and capability_work"
                )
            if not provider_required:
                raise _execution_contract_error(
                    "capability_dependent requires provider_required=true"
                )
        else:
            if lane != "none" or mode != "other" or provider_required:
                raise _execution_contract_error(
                    "other responsibility requires execution_lane=none, output_mode=other, "
                    "and provider_required=false"
                )

        if mode in _VOCAL_OUTPUT_MODES and lane != "speaking":
            raise _execution_contract_error(
                "vocal output_mode requires execution_lane=speaking"
            )
        if mode in {"body_action", "media_playback", "capability_work"} and lane != "activity":
            raise _execution_contract_error(
                "activity output_mode requires execution_lane=activity"
            )
        if mode == "other" and lane != "none":
            raise _execution_contract_error(
                "output_mode=other requires execution_lane=none"
            )
        if mode in _MODE_SPECIFIC_VOCAL_OUTPUTS and not provider_required:
            raise _execution_contract_error(
                "mode-specific vocal output requires provider_required=true; ordinary "
                "speech delivery is not evidence for that mode"
            )
        if mode == "speech" and provider_required:
            raise _execution_contract_error(
                "ordinary speech uses Chromie's maintained Speaking delivery path and "
                "must set provider_required=false"
            )
        if mode == "media_playback" and self.media_operation == "none":
            raise _execution_contract_error(
                "media_playback requires one exact media_operation"
            )
        if mode != "media_playback" and self.media_operation != "none":
            raise _execution_contract_error(
                "media_operation is valid only for output_mode=media_playback"
            )
        if self.resource_responsibility is not None and lane == "speaking":
            raise _execution_contract_error(
                "a normal vocal performance is not resource acquisition or delivery"
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


class GoalIndependenceCandidateDecision(BaseModel):
    """Model-owned completion-mode judgment for one validated Goal candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_goal_index: int = Field(ge=0)
    completion_mode: Literal[
        "positive_effect",
        "independently_requested_authored_content",
        "capability_result_delivery_only",
        "silence_or_omission_only",
    ]
    audible_content_summary: str = Field(default="", max_length=500)
    final_goal_description: str = Field(default="", max_length=1000)
    reason_summary: str = Field(min_length=1, max_length=1000)

    @field_validator(
        "audible_content_summary",
        "final_goal_description",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

class GoalIndependenceModelOutput(BaseModel):
    """Focused model-owned judgment over already validated Goal candidates."""

    model_config = ConfigDict(extra="forbid")

    candidate_decisions: list[GoalIndependenceCandidateDecision] = Field(
        min_length=1,
        max_length=8,
    )
    reason_summary: str = Field(min_length=1, max_length=1000)

    @field_validator("candidate_decisions")
    @classmethod
    def unique_candidate_indices(
        cls,
        value: list[GoalIndependenceCandidateDecision],
    ) -> list[GoalIndependenceCandidateDecision]:
        indices = [item.candidate_goal_index for item in value]
        if len(indices) != len(set(indices)):
            raise ValueError("candidate_decisions must use unique Goal indices")
        return value


class GoalBindingAuditItem(BaseModel):
    """Model-owned material bindings for one already segmented Goal candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_goal_index: int = Field(ge=0)
    bindings: list[GoalAssociationModelBinding] = Field(
        default_factory=list,
        max_length=16,
    )
    reason_summary: str = Field(min_length=1, max_length=1000)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


class GoalBindingAuditOutput(BaseModel):
    """Focused model-owned audit of explicit Goal material parameters."""

    model_config = ConfigDict(extra="forbid")

    goal_bindings: list[GoalBindingAuditItem] = Field(min_length=1, max_length=8)
    reason_summary: str = Field(min_length=1, max_length=1000)

    @field_validator("goal_bindings")
    @classmethod
    def unique_goal_indices(
        cls,
        value: list[GoalBindingAuditItem],
    ) -> list[GoalBindingAuditItem]:
        indices = [item.candidate_goal_index for item in value]
        if len(indices) != len(set(indices)):
            raise ValueError("goal_bindings must use unique Goal indices")
        return value

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


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

    async def resolve(self, request: AgentRunRequest) -> GoalAssociationResolution:
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
                    status = str((result.metadata or {}).get("status") or "resolved")
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

    async def _resolve(self, request: AgentRunRequest) -> GoalAssociationResolution:
        candidate_goals = self._candidate_goals(request)
        turn_id = self._turn_id(request)
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ) = (
            GoalAssociationModelOutput
            if candidate_goals
            else GoalSegmentationModelOutput
        )
        discourse_referents = self._discourse_referents(request)
        response_schema = self._response_schema(
            output_type,
            candidate_goals,
            discourse_referents,
            clarification_only=False,
        )
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        initial_raw: dict[str, Any] | None = None
        repair_raw: dict[str, Any] | None = None
        semantic_review_raw: dict[str, Any] | None = None
        initial_validation_error = ""
        repair_attempted = False
        contract_repair_succeeded = False
        contract_repair_strategy = ""
        semantic_review_attempted = False
        semantic_review_attempt_count = 0
        optional_referent_recovery: list[dict[str, Any]] = []

        try:
            raw = await self.ollama.generate(
                self._layered_prompt(request, candidate_goals, output_type=output_type),
                system=self._system_prompt(output_type),
                options=generation_options,
                response_format=response_schema,
                prompt_family="goal_association.primary",
                turn_id=request.sid,
                attempt=1,
            )
            if not isinstance(raw, dict):
                raise ValueError("goal-association response is not a JSON object")
            raw, recovered = self._drop_invalid_optional_referent_introductions(raw)
            optional_referent_recovery.extend(recovered)
            initial_raw = raw
            try:
                resolution = await self._validate_contract_output(
                    raw,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
            except (ValidationError, ValueError) as exc:
                repair_attempted = True
                initial_validation_error = self._validation_error_json(exc)
                fresh_typed_resegmentation = self._is_execution_contract_validation_error(
                    exc
                )
                fresh_semantic_trigger = (
                    exc.trigger
                    if isinstance(exc, GoalAssociationFreshResegmentationError)
                    else ""
                )
                fresh_resegmentation = bool(
                    fresh_typed_resegmentation or fresh_semantic_trigger
                )
                contract_repair_strategy = (
                    "model_owned_fresh_typed_resegmentation"
                    if fresh_typed_resegmentation
                    else "model_owned_fresh_goal_resegmentation"
                    if fresh_semantic_trigger
                    else "schema_constrained_model_revision"
                )
                logger.warning(
                    "goal_association_contract_repair_start sid=%s validation_errors=%s "
                    "strategy=%s raw_output=%s",
                    request.sid,
                    initial_validation_error,
                    contract_repair_strategy,
                    self._bounded_json(raw, 4000),
                )
                if fresh_resegmentation:
                    resegmentation_trigger = (
                        "invalid_typed_execution_contract"
                        if fresh_typed_resegmentation
                        else fresh_semantic_trigger
                    )
                    repaired = await self.ollama.generate(
                        self._build_semantic_review_prompt(
                            request=request,
                            candidate_goals=candidate_goals,
                            output_type=output_type,
                            raw={},
                            triggers=[resegmentation_trigger],
                        ),
                        system=self._semantic_review_system_prompt(
                            output_type,
                            fresh_resegmentation=True,
                        ),
                        options=generation_options,
                        response_format=response_schema,
                        prompt_family=(
                            "goal_association.typed_execution_resegmentation"
                            if fresh_typed_resegmentation
                            else "goal_association.semantic_contract_resegmentation"
                        ),
                        turn_id=request.sid,
                        attempt=2,
                    )
                else:
                    repaired = await self.ollama.generate(
                        self._layered_repair_prompt(
                            request=request,
                            candidate_goals=candidate_goals,
                            turn_id=turn_id,
                            output_type=output_type,
                            raw=raw,
                            validation_error=initial_validation_error,
                        ),
                        system=self._repair_system_prompt(output_type),
                        options=generation_options,
                        response_format=response_schema,
                        prompt_family="goal_association.repair",
                        turn_id=request.sid,
                        attempt=2,
                    )
                if not isinstance(repaired, dict):
                    raise ValueError(
                        "goal-association repair response is not a JSON object"
                    ) from exc
                repaired, recovered = (
                    self._drop_invalid_optional_referent_introductions(repaired)
                )
                optional_referent_recovery.extend(recovered)
                repair_raw = repaired
                resolution = await self._validate_contract_output(
                    repaired,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                contract_repair_succeeded = True
                repair_metadata = dict(resolution.metadata)
                repair_metadata["contract_repair"] = {
                    "attempted": True,
                    "succeeded": True,
                    "strategy": contract_repair_strategy,
                    "attempt_count": 1,
                }
                resolution = resolution.model_copy(update={"metadata": repair_metadata})
                logger.info(
                    "goal_association_contract_repair_done sid=%s status=success",
                    request.sid,
                )
            review_candidate = repair_raw or initial_raw
            if review_candidate is None:
                raise ValueError("goal-association review candidate is missing")
            accepted_raw = review_candidate
            model_output = output_type.model_validate(review_candidate)
            review_triggers = self._semantic_review_triggers(
                model_output,
                request=request,
                candidate_goals=candidate_goals,
            )
            if review_triggers:
                semantic_review_attempted = True
                semantic_review_attempt_count = 1
                logger.info(
                    "goal_association_semantic_review_start sid=%s triggers=%s",
                    request.sid,
                    ",".join(review_triggers),
                )
                fresh_resegmentation = bool(
                    _FRESH_RESEGMENTATION_TRIGGERS.intersection(review_triggers)
                )
                reviewed = await self.ollama.generate(
                    self._build_semantic_review_prompt(
                        request=request,
                        candidate_goals=candidate_goals,
                        output_type=output_type,
                        raw=review_candidate,
                        triggers=review_triggers,
                    ),
                    system=self._semantic_review_system_prompt(
                        output_type,
                        fresh_resegmentation=fresh_resegmentation,
                    ),
                    options=generation_options,
                    response_format=response_schema,
                    prompt_family=(
                        "goal_association.semantic_resegmentation"
                        if fresh_resegmentation
                        else "goal_association.semantic_review"
                    ),
                    turn_id=request.sid,
                    attempt=3,
                )
                if not isinstance(reviewed, dict):
                    raise OllamaGenerationError(
                        "goal-association semantic review response is not a JSON "
                        "object",
                        failure_class="structured_output_invalid",
                        failure_domain="model_contract",
                        architecture_attribution="not_evaluated",
                        retryable=True,
                    )
                reviewed, recovered = (
                    self._drop_invalid_optional_referent_introductions(reviewed)
                )
                optional_referent_recovery.extend(recovered)
                semantic_review_raw = reviewed
                accepted_raw = reviewed
                resolution = await self._validate_contract_output(
                    reviewed,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                residual_review_triggers = (
                    self._residual_semantic_review_triggers(
                        output_type.model_validate(reviewed)
                    )
                )
                if residual_review_triggers:
                    semantic_review_attempt_count += 1
                    logger.info(
                        "goal_association_independence_review_start sid=%s "
                        "triggers=%s",
                        request.sid,
                        ",".join(residual_review_triggers),
                    )
                    adjudication_raw = await self.ollama.generate(
                        self._build_independence_review_prompt(
                            request=request,
                            raw=reviewed,
                            triggers=residual_review_triggers,
                        ),
                        system=self._independence_review_system_prompt(output_type),
                        options=generation_options,
                        response_format=self._independence_response_schema(
                            len(reviewed.get("new_goals") or [])
                        ),
                        prompt_family="goal_association.independence_adjudication",
                        turn_id=request.sid,
                        attempt=4,
                    )
                    if not isinstance(adjudication_raw, dict):
                        raise OllamaGenerationError(
                            "goal-association independence review response is not "
                            "a JSON object",
                            failure_class="structured_output_invalid",
                            failure_domain="model_contract",
                            architecture_attribution="not_evaluated",
                            retryable=True,
                        )
                    adjudication = GoalIndependenceModelOutput.model_validate(
                        adjudication_raw
                    )
                    candidate_goal_count = len(reviewed.get("new_goals") or [])
                    decision_by_index = {
                        item.candidate_goal_index: item
                        for item in adjudication.candidate_decisions
                    }
                    expected_indices = set(range(candidate_goal_count))
                    if set(decision_by_index) != expected_indices:
                        raise ValueError(
                            "independence review must adjudicate every candidate Goal "
                            "index exactly once"
                        )
                    adjudicated = copy.deepcopy(reviewed)
                    adjudicated["new_goals"] = [
                        {
                            **reviewed["new_goals"][index],
                            "description": (
                                decision.final_goal_description
                                or reviewed["new_goals"][index]["description"]
                            ),
                        }
                        for index in range(candidate_goal_count)
                        if (
                            decision := decision_by_index[index]
                        ).completion_mode
                        not in {
                            "capability_result_delivery_only",
                            "silence_or_omission_only",
                        }
                    ]
                    if not adjudicated["new_goals"]:
                        raise ValueError(
                            "independence review removed every candidate Goal"
                        )
                    adjudicated["reason_summary"] = adjudication.reason_summary
                    accepted_raw = adjudicated
                    semantic_review_raw = adjudicated
                    resolution = await self._validate_contract_output(
                        adjudicated,
                        request=request,
                        turn_id=turn_id,
                        output_type=output_type,
                    )
                    logger.info(
                        "goal_association_independence_review_done sid=%s "
                        "status=success",
                        request.sid,
                    )
                review_metadata = dict(resolution.metadata)
                if repair_attempted:
                    review_metadata["contract_repair"] = {
                        "attempted": True,
                        "succeeded": True,
                        "strategy": contract_repair_strategy,
                        "attempt_count": 1,
                    }
                review_metadata["semantic_review"] = {
                    "attempted": True,
                    "succeeded": True,
                    "strategy": (
                        "model_owned_goal_independence_adjudication"
                        if semantic_review_attempt_count > 1
                        else "model_owned_fresh_goal_resegmentation"
                        if fresh_resegmentation
                        else "model_owned_goal_association_review"
                    ),
                    "triggers": review_triggers,
                    "residual_triggers": residual_review_triggers,
                    "attempt_count": semantic_review_attempt_count,
                }
                resolution = resolution.model_copy(
                    update={"metadata": review_metadata}
                )
                logger.info(
                    "goal_association_semantic_review_done sid=%s status=success",
                    request.sid,
                )
            if self._binding_audit_required(accepted_raw):
                semantic_review_attempted = True
                semantic_review_attempt_count += 1
                logger.info(
                    "goal_association_binding_audit_start sid=%s",
                    request.sid,
                )
                binding_audit_raw = await self.ollama.generate(
                    self._build_binding_audit_prompt(
                        request=request,
                        raw=accepted_raw,
                    ),
                    system=self._binding_audit_system_prompt(),
                    options=generation_options,
                    response_format=self._binding_audit_response_schema(
                        len(accepted_raw.get("new_goals") or [])
                    ),
                    prompt_family="goal_association.binding_audit",
                    turn_id=request.sid,
                    attempt=5,
                )
                if not isinstance(binding_audit_raw, dict):
                    raise OllamaGenerationError(
                        "goal-association binding audit response is not a JSON object",
                        failure_class="structured_output_invalid",
                        failure_domain="model_contract",
                        architecture_attribution="not_evaluated",
                        retryable=True,
                    )
                binding_audit = GoalBindingAuditOutput.model_validate(
                    binding_audit_raw
                )
                goal_count = len(accepted_raw.get("new_goals") or [])
                audit_by_index = {
                    item.candidate_goal_index: item
                    for item in binding_audit.goal_bindings
                }
                if set(audit_by_index) != set(range(goal_count)):
                    raise ValueError(
                        "binding audit must cover every candidate Goal index exactly once"
                    )
                audited = copy.deepcopy(accepted_raw)
                for index, goal in enumerate(audited["new_goals"]):
                    existing = {
                        str(item.get("name") or "").strip(): item
                        for item in list(goal.get("bindings") or [])
                        if isinstance(item, dict)
                        and str(item.get("name") or "").strip()
                    }
                    for binding in audit_by_index[index].bindings:
                        existing.setdefault(
                            binding.name,
                            binding.model_dump(
                                mode="json",
                                exclude_none=True,
                            ),
                        )
                    goal["bindings"] = list(existing.values())
                accepted_raw = audited
                semantic_review_raw = audited
                pre_audit_metadata = dict(resolution.metadata)
                resolution = await self._validate_contract_output(
                    audited,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                audit_metadata = {
                    **pre_audit_metadata,
                    **dict(resolution.metadata),
                }
                audit_metadata["binding_audit"] = {
                    "attempted": True,
                    "succeeded": True,
                    "strategy": "model_owned_material_parameter_audit",
                    "trigger": "compound_executable_goal_without_bindings",
                    "attempt_count": 1,
                }
                resolution = resolution.model_copy(
                    update={"metadata": audit_metadata}
                )
                logger.info(
                    "goal_association_binding_audit_done sid=%s status=success",
                    request.sid,
                )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            status = (
                "model_contract_failed"
                if failure["failure_domain"] == "model_contract" or repair_attempted
                else "model_unavailable"
            )
            logger.exception(
                "goal_association_inference_failed sid=%s error_type=%s error=%s "
                "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s "
                "repair_attempted=%s semantic_review_attempted=%s "
                "initial_validation_errors=%s initial_raw_ref=%s repair_raw_ref=%s "
                "semantic_review_raw_ref=%s initial_raw=%s repair_raw=%s "
                "semantic_review_raw=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                failure["retryable"],
                repair_attempted,
                semantic_review_attempted,
                initial_validation_error,
                cognition_text_reference(initial_raw),
                cognition_text_reference(repair_raw),
                cognition_text_reference(semantic_review_raw),
                self._bounded_json(initial_raw, 4000) if initial_raw is not None else "",
                self._bounded_json(repair_raw, 4000) if repair_raw is not None else "",
                (
                    self._bounded_json(semantic_review_raw, 4000)
                    if semantic_review_raw is not None
                    else ""
                ),
            )
            integrity_metadata = cognitive_integrity_metadata(stage="goal_association", exc=exc, request=request)
            metadata: dict[str, Any] = {
                "resolver": "goal_association_agent",
                "status": status,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                **failure,
                "candidate_goal_count": len(candidate_goals),
                "sid": request.sid,
                "contract_schema": output_type.__name__,
                "contract_repair_attempted": repair_attempted,
                "contract_repair_succeeded": contract_repair_succeeded,
                "semantic_review_attempted": semantic_review_attempted,
                "semantic_review_succeeded": False,
                **integrity_metadata,
            }
            if initial_validation_error:
                metadata["initial_validation_errors"] = initial_validation_error
            metadata["initial_raw_output_ref"] = cognition_text_reference(initial_raw)
            metadata["repair_raw_output_ref"] = cognition_text_reference(repair_raw)
            metadata["semantic_review_raw_output_ref"] = cognition_text_reference(
                semantic_review_raw
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
                clarification=self._safe_clarification(
                    request,
                    has_candidate_goals=bool(candidate_goals),
                ),
                confidence=0.0,
                reason_summary=(
                    "Goal semantic review did not complete successfully; no goal operation was accepted."
                    if semantic_review_attempted
                    else "Goal association output did not satisfy the schema after one model repair attempt; no goal operation was accepted."
                    if repair_attempted
                    else "Goal association model was unavailable; no goal operation was accepted."
                ),
                metadata=metadata,
            )
        if optional_referent_recovery:
            metadata = dict(resolution.metadata)
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

    @staticmethod
    def _drop_invalid_optional_referent_introductions(
        raw: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Drop only semantically empty, unscoped optional introductions.

        Referent corrections, focus changes, retirements, and introductions with
        actual entity content remain contract-authoritative and still fail closed.
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
            kept.append(item)
        normalized["referent_updates"] = kept
        return normalized, dropped

    async def _validate_contract_output(
        self,
        raw: dict[str, Any],
        *,
        request: AgentRunRequest,
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> GoalAssociationResolution:
        model_output = output_type.model_validate(raw)
        collection_bindings = self._action_collection_bindings(model_output)
        if collection_bindings:
            raise GoalAssociationFreshResegmentationError(
                "new Goal bindings cannot contain action collections; emit one "
                "new_goals item for every independently observable responsibility: "
                + ", ".join(collection_bindings),
                trigger="invalid_action_collection_binding",
            )
        location_bindings = self._non_verbatim_explicit_location_bindings(
            model_output,
            request=request,
        )
        if location_bindings:
            raise GoalAssociationFreshResegmentationError(
                "a location binding must preserve explicit or referent-backed "
                "provenance. For a directly named location, preserve a verbatim "
                "contiguous span from the authoritative user turn and do not "
                "translate, transliterate, or expand it. For an indirect "
                "location, copy the supplied referent_id into both the location "
                "binding and resolved_references, and copy the indirect user "
                "surface into resolved_references.surface_form: "
                + ", ".join(location_bindings),
                trigger="invalid_location_binding_provenance",
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
            for binding in goal.bindings:
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
    def _non_verbatim_explicit_location_bindings(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: AgentRunRequest,
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
            for binding in goal.bindings:
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
    def _semantic_review_triggers(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: AgentRunRequest,
        candidate_goals: list[dict[str, Any]],
    ) -> list[str]:
        """Return typed review triggers without making a semantic judgment."""

        triggers: list[str] = []
        responsibility_kinds = {
            goal.responsibility_kind for goal in model_output.new_goals
        }
        if {
            "capability_dependent",
            "spoken_response",
        }.issubset(responsibility_kinds):
            triggers.append("mixed_capability_and_spoken_responsibilities")
        if (
            getattr(getattr(request, "route_decision", None), "route", "") == "tool"
            and model_output.new_goals
            and responsibility_kinds == {"spoken_response"}
        ):
            # The route is advisory, but a tool-routed turn that was reduced to
            # ordinary authored speech has crossed an evidence-responsibility
            # boundary. The model, not the Host, re-segments the authoritative
            # turn and decides whether current evidence is actually required.
            triggers.append("tool_route_spoken_responsibility_review")
        if (
            getattr(getattr(request, "route_decision", None), "intent", "")
            == "recommendation"
            and model_output.new_goals
            and responsibility_kinds == {"spoken_response"}
        ):
            # A recommendation route is still advisory, but it is a useful typed
            # signal that the first Goal DTO needs an independent evidence-needs
            # review. This does not classify the Goal or select a provider: the
            # second model call re-segments the authoritative turn from scratch.
            triggers.append("recommendation_route_spoken_responsibility_review")
        executable_goal_count = sum(
            goal.responsibility_kind == "executable_action"
            and goal.resource_responsibility is None
            for goal in model_output.new_goals
        )
        if executable_goal_count == 1:
            triggers.append("embodied_responsibility_decomposition")
        elif executable_goal_count >= 3:
            # A compound request with three or more model-authored effectful
            # responsibilities is high-risk for grammar-driven misclassification.
            # Ask the model to re-segment from authoritative context without
            # treating the first DTO as evidence.
            triggers.append("multi_embodied_responsibility_review")
        has_resource_work = any(
            goal.resource_responsibility is not None
            for goal in model_output.new_goals
        )
        has_ordinary_spoken = any(
            goal.responsibility_kind == "spoken_response"
            and goal.output_mode == "speech"
            and not goal.provider_required
            for goal in model_output.new_goals
        )
        if has_resource_work and has_ordinary_spoken:
            triggers.append(
                "mixed_resource_work_and_ordinary_spoken_responsibilities"
            )
        if (
            isinstance(model_output, GoalAssociationModelOutput)
            and model_output.decision == "create_goals"
            and len(model_output.new_goals) == 1
            and candidate_goals
        ):
            triggers.append("single_new_goal_with_retained_context")
        if isinstance(model_output, GoalAssociationModelOutput) and any(
            association.relationship in {"modify", "clarify", "replace"}
            for association in model_output.associations
        ):
            triggers.append("existing_goal_semantic_update")
        if (
            isinstance(model_output, GoalAssociationModelOutput)
            and model_output.decision == "clarify"
            and candidate_goals
        ):
            triggers.append("candidate_goal_clarification_continuity")
        return triggers

    @staticmethod
    def _residual_semantic_review_triggers(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    ) -> list[str]:
        """Request one bounded model adjudication for a residual risky split.

        The typed combination is only a review trigger. The Host does not decide
        whether the ordinary spoken responsibility is genuine; the focused model
        review may preserve a real independent answer or remove a constraint that
        was incorrectly promoted into another Goal.
        """

        has_capability_work = any(
            goal.responsibility_kind in {
                "executable_action",
                "capability_dependent",
            }
            for goal in model_output.new_goals
        )
        has_ordinary_spoken = any(
            goal.responsibility_kind == "spoken_response"
            and goal.output_mode == "speech"
            and not goal.provider_required
            for goal in model_output.new_goals
        )
        return (
            ["mixed_capability_work_and_ordinary_spoken_responsibilities"]
            if has_capability_work and has_ordinary_spoken
            else []
        )

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
    def _is_execution_contract_validation_error(exc: Exception) -> bool:
        """Return true only when every defect is a typed Goal tuple mismatch.

        The Host does not repair or reclassify the semantic fields. It uses this
        distinction only to choose a fresh model-owned resegmentation that omits
        the invalid DTO, avoiding repair anchoring on mutually inconsistent typed
        labels. Missing fields and unrelated schema defects still use the normal
        exact-error repair path.
        """

        if not isinstance(exc, ValidationError):
            return False
        errors = exc.errors(include_url=False)
        if not errors:
            return False
        for error in errors:
            location = tuple(error.get("loc") or ())
            if not location or location[0] != "new_goals":
                return False
            if error.get("type") != "goal_execution_contract":
                return False
        return True

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
                    if (
                        "responsibility_kind" in node_properties
                        and "output_mode" in node_properties
                    ):
                        # The model chooses one semantic completion mode.  The Host
                        # materializes the redundant responsibility/lane/provider
                        # invariants after decoding, so illegal cross-field tuples
                        # are not representable at the model boundary.
                        for field_name in (
                            "responsibility_kind",
                            "execution_lane",
                            "provider_required",
                        ):
                            node_properties.pop(field_name, None)
                        node_required = [
                            field_name
                            for field_name in list(node.get("required") or [])
                            if field_name
                            not in {
                                "responsibility_kind",
                                "execution_lane",
                                "provider_required",
                            }
                        ]
                        if "output_mode" not in node_required:
                            node_required.append("output_mode")
                        node["required"] = node_required
                        output_mode = node_properties.get("output_mode")
                        if isinstance(output_mode, dict):
                            output_mode.pop("anyOf", None)
                            output_mode.pop("default", None)
                            output_mode["type"] = "string"
                            output_mode["enum"] = list(
                                _OUTPUT_MODE_EXECUTION_CONTRACT
                            )
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
        return schema

    def _candidate_goals(self, request: AgentRunRequest) -> list[dict[str, Any]]:
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

    def _discourse_referents(self, request: AgentRunRequest) -> list[dict[str, Any]]:
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
    def _turn_id(request: AgentRunRequest) -> str:
        seed = f"{request.sid or 'turn'}|{request.text}"
        return f"turn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _bounded_json(value: Any, max_chars: int) -> str:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."

    def _build_prompt(
        self,
        request: AgentRunRequest,
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
                "Segment the authoritative user turn into independent new Goals, or return a clarification if the meaning is materially ambiguous. "
            )
            output_instructions = (
                "Return only JSON with decision, new_goals, referent_updates, resolved_references, clarification, confidence, and reason_summary. "
                "Use decision=create_goals for a clear turn and decision=clarify only for a genuinely ambiguous user meaning. "
                "The decoder enforces the exact GoalSegmentationModelOutput JSON Schema. "
            )
        else:
            state_instructions = (
                "Resolve continuity before creation using semantic reasoning. "
                "For continuity with an existing goal, emit an associations item with relationship, target_goal_ids, confidence, reason_summary, and the applicable updated_description, resolved_gap_ids, and requires_replan fields. "
                "relationship must be copied exactly from [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"replace\",\"merge\",\"split\",\"reference\"]. "
                "Use continue only when the current turn advances unchanged unfinished active or recoverable work. Use reference when the current turn asks to retrieve, restate, explain, compare, verify, or otherwise answer from a retained Goal without changing its meaning or lifecycle. Do not use continue or reference merely because the topic overlaps with a previous Goal. When the latest turn is a social reaction, acknowledgement, personal feeling, practical decision, conversational evaluation, empathy-seeking comment, or another independently satisfiable communicative act, create a fresh spoken_response Goal that captures that latest intent; prior delivered information remains context for that answer. Use modify or replace only when the user meaning actually changes and include updated_description or resolved_gap_ids. The association relationship clarify means the current user turn supplies missing information for a Goal and must include updated_description or resolved_gap_ids; it never means that the user is asking Chromie for more explanation. When the user's meaning itself is ambiguous and Chromie must ask a question, use top-level decision=clarify instead. "
                "Use confirm only when the current turn approves a pending proposal for the targeted Goal, and use reject only when it declines that proposal. "
                "Associations may target only IDs from the bounded candidate-goal list. A recent terminal Goal may be referenced without reopening or changing its terminal lifecycle state. "
                "An association cannot rewrite an existing Goal's typed material bindings. When your semantic judgment is that the current user meaning changes a material entity or parameter, preserve the old Goal and return decision=create_goals with a complete replacement Goal and authoritative bindings. "
            )
            output_instructions = (
                "Return only JSON with decision, associations, new_goals, referent_updates, resolved_references, clarification, confidence, and reason_summary. "
                "Use decision=associate for continuity, decision=create_goals for independent work, or decision=clarify only for genuine ambiguity. "
                "The decoder enforces the exact GoalAssociationModelOutput JSON Schema. "
            )
        return (
            state_instructions
            + "The supplied pre-association route and intent are advisory only. "
            "They must not force a clarification branch or attach the turn to an existing Goal. "
            "If the user's intended outcome is clear, create or associate the semantic Goal even when downstream capability planning may still need a binding; the Planner owns execution-information gaps. "
            + "The model-facing contract is deliberately small. "
            "The host owns all IDs, versions, source text, constraints, metadata, persistence fields, and canonical object construction. "
            "Never emit id, goal_id, association_id, turn_id, schema_version, source_text, constraints, object, metadata, success_criteria, skills, or plans. Referent IDs may only be copied from the supplied discourse context; new referent IDs are Host-generated.\n\n"
            "Create one new goal for each independently satisfiable user responsibility. Emit exactly one new_goals item containing description, typed bindings, and an optional provider-neutral resource_responsibility for each responsibility. "
            "Every new Goal must declare one exact output_mode that describes the semantic work completing the human outcome. The Host derives responsibility_kind, execution_lane, and provider_required deterministically from that mode; never emit those Host-owned fields. Media playback may also declare its exact media_operation; non-media Goals may omit media_operation and the Host supplies none. "
            f"{_EXECUTION_CONTRACT_PROMPT} "
            "The eventual spoken delivery of a capability result is part of that same capability_dependent Goal, never an additional spoken_response Goal. Persona, tone, wording, and answer delivery are not independent Goals. "
            "A standalone social interaction such as a greeting, thanks, reassurance request, casual check-in, reaction, personal feeling, evaluation, or practical decision is itself one satisfiable conversational Goal: respond naturally to that current social act. This remains true when the act is grounded in information delivered by a previous Goal. Prior evidence may support the answer, but it does not replace the latest communicative responsibility. Do not treat it as an empty turn or fold it into an already completed task merely because the topic is related. "
            "A greeting or politeness preamble attached to a substantive request is conversational framing, not a separate Goal unless the user independently asks for a social response. Owner-approved identity and personality shape expression only; never create a Goal merely to mention age, identity, warmth, curiosity, or another style trait. "
            "A factual lookup and the user's requested interpretation of that same evidence are one Goal when one capability result can satisfy both, such as checking weather and judging whether it is hot. Do not split evidence acquisition from the answer derived from that evidence. "
            "A physical action and a conversational answer or spoken performance are independent goals when the answer or performance is genuinely requested. Separate independently requested outcomes that can be accepted or rejected on their own. However, acquisition and delivery stages that together constitute one human responsibility are one Goal: navigating/searching, locating, grasping or retrieving, carrying, returning, and handing over are provider-owned stages of one physical resource delivery; external search, evidence retrieval, evaluation, and spoken explanation are stages of one information resource delivery. Do not split those implementation stages into separate Goals unless the user independently requests one stage as its own outcome. A simple acknowledgement, confirmation, willingness statement, or progress prelude for capability work is not a separate spoken_response Goal; it is prospective conversational output attached to the existing responsibility and every cognitive stage must use Interaction Context to avoid repeating an already fulfilled act. Before returning, verify that every independently satisfiable user responsibility appears in exactly one new_goals item: no merged unrelated outcomes and no duplicated responsibility across Goals. "
            "For a responsibility whose human-level outcome is to obtain something and make it available to a recipient, include resource_responsibility. Use resource_kind=physical_object for embodied objects and delivery_mode=physical_handover. Use resource_kind=information for weather, restaurant or place recommendations, web research, current facts, and other grounded information; use delivery_mode=spoken_explanation unless the user explicitly requests structured output. Resource identity is not source evidence: naming or pointing at the desired object or information does not by itself say where it is or which source supplies it. Set source_status=known only when the user or discourse supplies an actual source, and then source_description or source_binding_names is mandatory. Set unknown when a required source is absent, including an unresolved demonstrative whose referent or location is not established. Use provider_resolved only when source selection is intentionally delegated to the eventual provider. source_binding_names may reference only bindings in the same Goal. This semantic object must never name or imply a provider, capability ID, website, search engine, execution mode, coordinates, grasp pose, or implementation plan. Provider selection belongs only to the Planner. Put every user-visible parameter such as count, duration, speed, direction, target, or requested content into both the natural-language description and a typed binding. When the user states an unambiguous quantity in words, normalize its binding value to the equivalent numeric string without units; the model owns that semantic normalization. Description text alone is not parameter provenance for planning. "
            "Also preserve semantic qualifiers such as temporal scope, comparison period, and requested answer shape. Never silently rewrite annual, seasonal, historical, comparative, or otherwise broad scope into current, today, tomorrow, or another narrower scope. If the intended scope is materially ambiguous, return clarification instead of choosing a narrower interpretation. "
            "Resolve references, pronouns, demonstratives, ellipsis, and task mentions before planning. Authority order is: explicit current user meaning; foreground scoped discourse referents; candidate Goal bindings; recent dialogue. Phrases such as ‘the last task I told you’ may semantically associate with an active, recoverable, or retained recent terminal Goal, but the model must decide that relationship from the supplied Goal state and dialogue—not from a Host phrase table. Tool-result memory is not reference-resolution authority and must never decide what an unresolved expression refers to. "
            "When the user introduces or explicitly corrects a salient entity, emit referent_updates. Use operation=correct with target_referent_ids when a new value supersedes an earlier referent in the current discourse; the old referent remains available in its own task scope but becomes background. Use operation=introduce for a new salient entity, and focus/background/retire only for supplied referent IDs. "
            "Use resolved_references only for indirect references whose denotation must be selected from a supplied discourse referent or active Goal binding, such as pronouns, demonstratives, ellipsis, aliases, corrections, or task mentions. Do not emit resolved_references for an ordinary explicit entity mention such as a directly named place; represent that meaning in the new Goal bindings and, when it is salient for future dialogue, in referent_updates. Every resolved_references item must copy a supplied referent_id and include explicit confidence. If resolution is materially ambiguous, return decision=clarify rather than selecting a value from stale evidence or recency alone. "
            "Each new Goal must include typed bindings for material entities and parameters already resolved here, including explicit counts, durations, speeds, directions, and targets. For weather, a resolved place belongs in a binding named location. Downstream planners must receive the explicit binding rather than an unresolved expression. "
            "For a location named directly in the final authoritative user turn, copy the complete location value verbatim as one contiguous span in the user's language. Never translate, transliterate, shorten, or expand a directly named location. A directly supplied location is a resolved semantic binding, not a claim that provider canonicalization has already succeeded. Do not ask the user for administrative granularity merely because multiple real-world places might share that value; create the fully bound Goal and let the downstream Capability resolve the exact value or report provider ambiguity. Clarify only when the user's intended location is genuinely underdetermined in the dialogue. Only an indirect reference resolved from a supplied referent may use the referent's canonical value instead. For an indirect location, copy the supplied referent_id into both the location binding and resolved_references, and copy the indirect user surface into resolved_references.surface_form. "
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
            "The clarification field is only a concise user-facing question. Never put analysis, rationale, translation, route labels, validator errors, model failures, or system diagnostics in clarification. Put optional compact rationale in reason_summary. If the user meaning is materially ambiguous, use decision=clarify; otherwise keep clarification empty.\n\n"
            "Abstract decomposition example: a request to perform action A, then action B, and answer question C produces three new_goals descriptions: perform action A; perform action B; answer question C. "
            "This example is structural, not a phrase-matching rule.\n\n"
            + output_instructions
            + "Each new_goals object contains description, output_mode, optional media_operation, bindings, and optional resource_responsibility only. bindings is an array of typed semantic parameters with name, entity_type, value, optional copied referent_id, and confidence. Use [] when no material binding exists. resource_responsibility is provider-neutral and must follow the contract above. A vocal Goal must never carry resource_responsibility merely because rendering needs a provider. Every referent_updates item and every resolved_references item must include explicit confidence; never rely on an omitted-field default.\n\n"
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{personality_json}\n\n"
            + skill_section
            + "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 6500)}\n\n"
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON (append-only facts about what Chromie already associated, planned, said, committed, completed, or failed; owner and event_type preserve evidence strength). Use it to identify the still-needed Goal/continuity delta. Generated or scheduled speech is not heard speech, and planned or committed work is not completed work. Do not reopen, repeat, or recreate an already fulfilled responsibility unless the current turn explicitly repeats it or new failure, correction, changed state, evidence, or clarification requires a new delta:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Fast interaction decision JSON (reviewed reason for choosing one early acknowledgement or silence; this never proves playback, which remains owned by Interaction Context):\n"
            f"{self._bounded_json(context.get('fast_interaction_decision') or {}, 1400)}\n\n"
            "Treat intentional Fast silence as a valid conversational choice rather than a missing Goal. Do not create a filler spoken_response Goal merely to compensate for silence. If later speech is needed, judge that from the current user's meaning and remaining conversational delta, not from a rule that Fast speech must exist. "
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON (most recent/foreground last):\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "Tool-result contents are intentionally absent at this boundary. Resolve references and Goal bindings from user semantics, scoped referents, candidate Goals, and dialogue only. A later Planner may explicitly retrieve an exact verified memory record after bindings are fixed. "
            "For a scheduled, running, or recoverable safe-read Goal, associate a semantic follow-up with that exact Goal when appropriate; do not answer from another task's result. "
            "Do not reason from prior routing labels, planner states, validation failures, fallback states, or other runtime diagnostics; they are not user-semantic evidence.\n\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANDIDATE GOAL IDS JSON:\n{self._bounded_json([item.get('goal_id') for item in candidate_goals], 1600)}"
        )

    def _build_repair_prompt(
        self,
        *,
        request: AgentRunRequest,
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
                "Re-segment every independently satisfiable responsibility into new_goals, or return only a clarification when the meaning is materially ambiguous. "
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
                "The final authoritative user turn owns the current communicative responsibility. A completed task may supply context, but a reaction, feeling, evaluation, acknowledgement, or practical decision about that context is normally a fresh spoken_response Goal rather than continuation or reference. Existing Goal bindings are provenance-stable and cannot be changed by an association. If current user meaning changes a material binding, use decision=create_goals with one fully bound replacement Goal rather than a description-only association. "
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
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON:\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "Previous model output JSON:\n"
            f"{self._bounded_json(raw, 5000)}\n\n"
            "Exact validation errors JSON:\n"
            f"{validation_error}\n\n"
            + output_instructions
            + "Select exactly one decision branch. clarification is only a concise user-facing question and must be empty for non-clarify decisions. Each new_goals item contains description, output_mode, optional media_operation, bindings, and optional provider-neutral resource_responsibility only. Choose output_mode from the work that actually completes the Goal; the Host derives the internal responsibility class, lane, and provider-evidence requirement. media_playback requires one exact media_operation; non-media Goals may omit it. "
            + _EXECUTION_CONTRACT_PROMPT
            + " Preserve resource_responsibility when the responsibility is genuinely to acquire and deliver a physical object or grounded information; never add it to a vocal performance and never insert provider or capability details into it. Resource identity is not source evidence. source_status=known requires an actual user- or discourse-supplied source and a nonempty source_description or source_binding_names; use unknown when a required source is absent, and provider_resolved only when source selection is deliberately delegated. Preserve every explicit count, duration, speed, direction, target, and other material parameter in a typed binding as well as the description; normalize an unambiguous worded quantity to a numeric-string binding value without units. Preserve or repair explicit discourse resolution and referent updates; never use tool-result contents to infer a reference. "
            "The host owns every ID and persistence field. Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    def _layered_prompt(
        self,
        request: AgentRunRequest,
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
        request: AgentRunRequest,
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

    def _build_semantic_review_prompt(
        self,
        *,
        request: AgentRunRequest,
        candidate_goals: list[dict[str, Any]],
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        raw: dict[str, Any],
        triggers: list[str],
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        contract_name = (
            "Goal Segmentation"
            if output_type is GoalSegmentationModelOutput
            else "Goal Association"
        )
        output_fields = (
            "decision, new_goals, referent_updates, resolved_references, "
            "clarification, confidence, and reason_summary"
            if output_type is GoalSegmentationModelOutput
            else "decision, associations, new_goals, referent_updates, "
            "resolved_references, clarification, confidence, and reason_summary"
        )
        fresh_resegmentation = bool(
            _FRESH_RESEGMENTATION_TRIGGERS.intersection(triggers)
        )
        mixed_responsibility_guidance = (
            "For the mixed capability_dependent plus spoken_response trigger, "
            "apply this independence test before returning JSON: if the capability "
            "did not run, could the proposed spoken Goal still be truthfully and "
            "fully completed? The generic act of answering a question, reporting, "
            "summarizing, explaining, or recommending from that capability result "
            "fails this test and must not be a separate Goal; return only the "
            "capability_dependent Goal, whose delivery_mode owns the later speech. "
            "Keep a spoken_response sibling only for independently satisfiable "
            "content such as an unrelated joke, greeting, authored reminder, or "
            "other answer that does not depend on the capability result. Do not "
            "justify a second Goal merely as 'the subsequent verbal response'.\n\n"
            if "mixed_capability_and_spoken_responsibilities" in triggers
            else ""
        )
        review_input = (
            "No previous Goal DTO is supplied for this review. Reconstruct the "
            "segmentation independently from the authoritative user turn so an "
            "earlier completion-modality label cannot anchor the result. Do not "
            "try to preserve an earlier description, ordering, or responsibility_kind.\n\n"
            if fresh_resegmentation
            else (
                "DTO to review JSON:\n"
                f"{self._bounded_json(raw, 6000)}\n\n"
            )
        )
        return (
            f"Independently review this model-authored {contract_name} boundary and "
            "return the complete final JSON object. The Host supplied only typed "
            f"review triggers {self._bounded_json(triggers, 800)}. A trigger is "
            "not proof that any semantic choice is wrong. "
            "Use semantic reasoning over the authoritative user turn and bounded "
            "dialogue context. Do not use phrase matching, binding equality, "
            "numeric suffixes, lexical overlap, or another deterministic shortcut.\n\n"
            + mixed_responsibility_guidance
            + "Classify each candidate's output_mode by the semantic work and evidence "
            "that complete the human outcome, not by grammar, verb choice, command "
            "framing, or the surrounding route. Embodied effects use body_action; "
            "existing-media lifecycle work uses media_playback plus the exact "
            "media_operation; directly authored ordinary conversation uses speech; "
            "authored vocal performances use their exact vocal mode; and work whose "
            "truth or completion depends on fresh external, private, or runtime "
            "evidence uses capability_work. The Host derives the internal "
            "responsibility class, execution lane, and provider-evidence requirement "
            "from output_mode. Never map a vocal performance to a body or media effect, "
            "and never treat eventual spoken delivery of capability evidence as the "
            "completion mode of the evidence-acquisition Goal. "
            f"{_EXECUTION_CONTRACT_PROMPT}\n\n"
            "Keep or create a fresh spoken_response Goal when the latest turn is an "
            "independently satisfiable reaction, feeling, acknowledgement, evaluation, "
            "decision, or other direct conversational act, even when a retained Goal "
            "supplies the topic or evidence. Do not replay the retained task as the "
            "current responsibility. Keep separate Goals when the user truly requested "
            "an independently satisfiable direct spoken or text response in addition "
            "to capability work, such as a song, joke, or unrelated social answer. "
            "When a spoken_response item merely phrases, reports, "
            "explains, or interprets evidence acquired by a capability_dependent item, "
            "the capability Goal owns that delivery. Persona and wording are expression "
            "concerns, not extra Goals. A mere acknowledgement, confirmation, promise "
            "of willingness, or progress prelude for executable work is prospective "
            "conversation attached to the existing responsibility, not a new Goal; "
            "use Interaction Context so later stages do not repeat an already fulfilled "
            "act. Identity shapes expression only and "
            "never proves that a physical responsibility is available. A prohibition "
            "on saying or repeating content while another action is performed is not "
            "a request for a verbal acknowledgement. Keep it in the action Goal's "
            "description as an expression constraint and do not create a sibling "
            "spoken_response Goal for it. Simultaneous or ordered framing does "
            "not merge independently observable outcomes. Preserve each responsibility "
            "exactly once and preserve its temporal relationship in the descriptions "
            "without making one Goal claim completion of its siblings. For embodied "
            "work, keep a genuinely independent requested movement or manipulation "
            "outcome separate. However, navigating, locating, grasping, carrying, "
            "returning, and handing over are provider-owned stages of one physical "
            "resource-delivery Goal when the human outcome is to obtain an object and "
            "make it available to a recipient. Do not split pickup and handoff merely "
            "because those provider stages can fail separately. A report that is "
            "requested only after that effect finishes is delivery owned by the same "
            "effect Goal, not an independently satisfiable spoken_response.\n\n"
            "A location named directly in the final authoritative user turn must remain "
            "a complete verbatim contiguous binding value in the user's language. Never "
            "translate, transliterate, shorten, or expand it. Do not ask for provider "
            "canonicalization or extra administrative detail merely because the name "
            "could match more than one real place; downstream capability resolution owns "
            "that ambiguity. Clarify only when the intended location is genuinely "
            "underdetermined. For an indirect location, "
            "copy the supplied referent_id into both the location binding and "
            "resolved_references and retain the supplied canonical value.\n\n"
            "Existing Goal bindings are provenance-stable at this contract. An "
            "association may update only its description and lifecycle relation; it "
            "cannot rewrite typed material bindings. If current meaning changes a "
            "material entity or parameter, preserve the earlier Goal and create one "
            "fully bound replacement Goal. Do not infer a correction from words, "
            "syntax, or binding inequality alone; decide from user meaning and supplied "
            "discourse evidence.\n\n"
            "Resource identity is not source evidence. For every resource_responsibility, "
            "source_status=known is valid only when the user or discourse supplied an "
            "actual source and source_description or source_binding_names is nonempty. "
            "Use unknown when a required source is absent, including an unresolved "
            "demonstrative, and provider_resolved only when source selection is deliberately "
            "delegated. When the human outcome is physical acquisition and handoff, "
            "return one Goal with resource_kind=physical_object and "
            "delivery_mode=physical_handover; retain a contingent completion report in "
            "that Goal's description. Preserve every explicit count, duration, speed, direction, target, "
            "and other material parameter in a typed binding as well as the description; "
            "normalize an unambiguous worded quantity to a numeric-string binding value "
            "without units.\n\n"
            "The Host is asking for a semantic judgment, not prescribing merge or "
            "separation. Preserve every genuinely independent responsibility, all "
            "valid associations, and all valid discourse updates. Before returning, "
            "audit every Goal description against its bindings: if the description "
            "preserves an explicit count, duration, speed, direction, target, or "
            "other material parameter from the authoritative turn, omitting its typed "
            "binding is invalid. Worded quantities must be normalized to numeric-string "
            "binding values; description text alone is never enough. Return only JSON "
            f"with {output_fields}. The exact schema is enforced out-of-band.\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 6500)}\n\n"
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON:\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            + review_input
            + "Tool-result contents are intentionally absent. Do not use remembered "
            "capability results to decide Goal structure or claim completion.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    def _build_independence_review_prompt(
        self,
        *,
        request: AgentRunRequest,
        raw: dict[str, Any],
        triggers: list[str],
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        return (
            "Adjudicate one residual Goal-independence question. The typed Host "
            "trigger is review evidence only; "
            "it does not prove that the current split is wrong.\n\n"
            f"Review triggers JSON:\n{self._bounded_json(triggers, 800)}\n\n"
            "Candidate DTO JSON:\n"
            f"{self._bounded_json(raw, 7000)}\n\n"
            "Apply this independence test to every ordinary spoken_response beside "
            "embodied or capability-dependent work: if the body action occurred, or "
            "if the capability work occurred, and Chromie otherwise stayed silent, "
            "did the user independently ask to "
            "hear authored content that can be truthfully completed without the pending "
            "capability result? Preserve "
            "the spoken Goal when the answer is yes, such as a requested joke, answer, "
            "greeting, reassurance, or other independently acceptable content. An "
            "instruction not to say, repeat, mention, explain, or provide some content "
            "sets a boundary on delivery; it does not request a verbal acknowledgement "
            "of that boundary. Keep such a restriction in the affected surviving Goal "
            "description and remove any Goal whose only outcome is silence, omission, "
            "or acknowledgement of the prohibition. A boundary is not an independent "
            "spoken outcome merely because the user can notice or accept compliance. "
            "Speaking-lane authored content requires positive words, information, or a "
            "vocal performance that the user actually asked to hear; silence and not "
            "mentioning a topic produce no speaking-lane output. A report, explanation, "
            "evaluation, or recommendation whose truth or content depends on the pending "
            "capability result is delivery owned by that capability Goal, not an "
            "independent spoken Goal. This includes a contingent completion report: "
            "an instruction to notify, report, or tell the user when pending work is "
            "finished can be authored truthfully only from that work's execution "
            "result, so classify it as capability_result_delivery_only even though "
            "the eventual report is audible. Do not treat the requested timing of a "
            "result-dependent report as independently authored content. Do not remove "
            "genuinely requested "
            "independent speech. Preserve every explicit material action binding, "
            "including normalized worded quantities, and all valid associations and "
            "discourse updates. Do not add a capability, provider, execution step, or "
            "completion claim.\n\n"
            "Return one candidate_decisions item for every zero-based candidate Goal "
            "index. Use completion_mode=positive_effect for embodied or capability "
            "outcomes. Use independently_requested_authored_content only when the user "
            "positively requested content that must be audibly produced, and summarize "
            "that requested content in audible_content_summary. Use "
            "capability_result_delivery_only when the apparent spoken outcome can be "
            "authored only after and from a pending capability result; exclude that "
            "candidate because the capability Goal owns result delivery. Use "
            "silence_or_omission_only when compliance consists only of withholding, "
            "omitting, or not repeating content. Descriptive fields on an excluded "
            "candidate are ignored. For every kept candidate, use final_goal_description "
            "to preserve any delivery constraint on its surviving Goal; if it is empty, "
            "the Host retains the candidate's already validated description. The "
            "completion-mode decisions are semantic; the Host will apply them "
            "mechanically without interpreting any Goal. Return only the "
            "exact JSON object enforced out-of-band.\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    @staticmethod
    def _independence_response_schema(goal_count: int) -> dict[str, Any]:
        schema = copy.deepcopy(GoalIndependenceModelOutput.model_json_schema())
        properties = schema.setdefault("properties", {})
        decisions = properties.get("candidate_decisions")
        if isinstance(decisions, dict):
            decisions["minItems"] = max(1, goal_count)
            decisions["maxItems"] = max(1, goal_count)
        decision_schema = schema.get("$defs", {}).get(
            "GoalIndependenceCandidateDecision"
        )
        if isinstance(decision_schema, dict):
            decision_schema["required"] = [
                "candidate_goal_index",
                "completion_mode",
                "audible_content_summary",
                "final_goal_description",
                "reason_summary",
            ]
            index_schema = decision_schema.get("properties", {}).get(
                "candidate_goal_index"
            )
            if isinstance(index_schema, dict):
                index_schema["enum"] = list(range(max(0, goal_count)))
        schema["required"] = [
            "candidate_decisions",
            "reason_summary",
        ]
        schema["additionalProperties"] = False
        return schema

    @staticmethod
    def _independence_review_system_prompt(
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
            f"You are Chromie's focused {contract_name} independence adjudicator. "
            "Use semantic reasoning to distinguish independently requested spoken "
            "content from capability-result delivery and from a constraint on what "
            "should not be spoken. Preserve all "
            "genuine embodied and conversational responsibilities and their typed "
            "bindings. A speaking responsibility must require positive audible content "
            "that can be completed independently of pending capability evidence; "
            "a contingent report that pending work has finished depends on execution "
            "evidence and is capability_result_delivery_only, not independently "
            "authored content. "
            "silence, omission, and not repeating a topic are delivery constraints even "
            "when the user explicitly requests them. Return one completion-mode decision "
            "for every zero-based candidate Goal index, final descriptions for kept "
            "Goals, and a concise reason as JSON. The Host "
            "validates structure and mechanically applies your semantic selection; "
            "it owns no semantic choice."
        )

    @staticmethod
    def _binding_audit_required(raw: dict[str, Any]) -> bool:
        """Trigger model review for an unbound executable Goal in a compound turn.

        Compound segmentation plus an empty executable binding list is a
        mechanical provenance-risk signal only. The Host does not inspect words
        or decide whether a parameter exists, its name, value, meaning, or owning
        Goal; the focused model audit does. This keeps worded quantities from
        passing accidentally through a matching Capability schema default.
        """

        goals = raw.get("new_goals")
        if not isinstance(goals, list):
            return False
        executable = [
            item
            for item in goals
            if isinstance(item, dict)
            and (
                item.get("output_mode") in {"body_action", "media_playback"}
                or (
                    item.get("output_mode") is None
                    and item.get("responsibility_kind") == "executable_action"
                )
            )
        ]
        if len(goals) < 2 or not executable:
            return False
        return any(not item.get("bindings") for item in executable)

    def _build_binding_audit_prompt(
        self,
        *,
        request: AgentRunRequest,
        raw: dict[str, Any],
    ) -> str:
        return (
            "Audit explicit material parameter bindings for an already segmented "
            "Goal DTO. The Host detected only a mechanical risk: this compound set "
            "contains at least one executable Goal with no typed bindings. That "
            "trigger does not decide whether a material parameter exists or what "
            "any word or number means.\n\n"
            "Return one goal_bindings item for every candidate Goal index exactly "
            "once. For each item, return the complete list of explicit material "
            "parameters belonging to that Goal: counts, durations, speeds, directions, "
            "targets, distances, quantities, and other user-supplied arguments. "
            "Normalize an unambiguous worded quantity to a numeric-string value. A "
            "duration binding should use the semantic parameter name duration_s and a "
            "count should use count when those meanings are explicit. Use an empty "
            "bindings list only when that Goal truly has no explicit material "
            "parameter. Do not invent defaults, infer provider-specific values, merge "
            "or split Goals, change descriptions, select capabilities, or claim "
            "completion. The Host will merge your model-authored bindings by Goal index "
            "and preserve every already validated binding. Return only the exact JSON "
            "object enforced out-of-band.\n\n"
            f"Candidate Goal DTO JSON:\n{self._bounded_json(raw.get('new_goals') or [], 7000)}\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    @staticmethod
    def _binding_audit_response_schema(goal_count: int) -> dict[str, Any]:
        schema = copy.deepcopy(GoalBindingAuditOutput.model_json_schema())
        properties = schema.setdefault("properties", {})
        items = properties.get("goal_bindings")
        if isinstance(items, dict):
            items["minItems"] = max(1, goal_count)
            items["maxItems"] = max(1, goal_count)
        item_schema = schema.get("$defs", {}).get("GoalBindingAuditItem")
        if isinstance(item_schema, dict):
            item_schema["required"] = [
                "candidate_goal_index",
                "bindings",
                "reason_summary",
            ]
            index_schema = item_schema.get("properties", {}).get(
                "candidate_goal_index"
            )
            if isinstance(index_schema, dict):
                index_schema["enum"] = list(range(max(0, goal_count)))
        schema["required"] = ["goal_bindings", "reason_summary"]
        schema["additionalProperties"] = False
        return schema

    @staticmethod
    def _binding_audit_system_prompt() -> str:
        return (
            "You are Chromie's focused Goal binding-provenance auditor. Use semantic "
            "reasoning over the authoritative turn and already segmented Goals. Return "
            "all and only explicit material bindings for every Goal index. Do not plan, "
            "select capabilities, alter Goal structure, or invent defaults. Return JSON only."
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
            "vocal performance belongs to spoken_response even when coordinated "
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
        request: AgentRunRequest,
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
                        in {"modify", "clarify", "replace", "merge", "split"}
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
                        for binding in goal_item.bindings
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
            binding_map: dict[str, Any] = {}
            for binding in item.bindings:
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
                if normalized.name in binding_map:
                    raise ValueError(
                        f"duplicate Goal binding name={normalized.name!r}"
                    )
                binding_map[normalized.name] = normalized.model_dump(
                    mode="json",
                    exclude_none=True,
                )
            resource_responsibility = None
            if item.resource_responsibility is not None:
                resource_item = item.resource_responsibility
                unknown_source_bindings = sorted(
                    set(resource_item.source_binding_names) - set(binding_map)
                )
                if unknown_source_bindings:
                    raise ValueError(
                        "resource source references unknown Goal bindings: "
                        f"{unknown_source_bindings}"
                    )
                source_bindings = {
                    name: binding_map[name]
                    for name in resource_item.source_binding_names
                }
                responsibility_variant = (
                    "fetch_and_deliver_object"
                    if resource_item.resource_kind == "physical_object"
                    else "fetch_and_deliver_information"
                )
                resource_responsibility = AcquireAndDeliverResource(
                    responsibility_variant=responsibility_variant,
                    resource=ResourceDescriptor(
                        kind=resource_item.resource_kind,
                        description=resource_item.resource_description,
                    ),
                    source=ResourceSource(
                        status=resource_item.source_status,
                        description=resource_item.source_description,
                        bindings=source_bindings,
                    ),
                    recipient=ResourceRecipient(
                        description=resource_item.recipient_description
                    ),
                    delivery_mode=resource_item.delivery_mode,
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
        request: AgentRunRequest,
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
        request: AgentRunRequest,
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
