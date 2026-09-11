from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .text import normalize_whitespace
from .interaction import reject_forbidden_low_level_fields
from .resource import AcquireAndDeliverResource


TaskOperationName = Literal[
    "create",
    "modify",
    "clarification_answer",
    "confirm",
    "reject",
    "cancel",
    "pause",
    "resume",
    "query_status",
    "correct",
]

ResponsibilityStatus = Literal[
    "open",
    "satisfied",
    "cancelled",
    "refused",
    "superseded",
]

TaskLifecycleStatus = Literal[
    "open",
    "planning",
    "needs_context",
    "waiting_for_user",
    "awaiting_confirmation",
    "committed",
    "scheduled",
    "running",
    "paused",
    "recoverable",
    "done",
    "failed",
    "refused",
    "timed_out",
    "cancelled",
    "superseded",
]

CommitmentState = Literal[
    "none",
    "heard",
    "evaluating",
    "accepted",
    "waiting_for_user",
    "executing",
    "completed",
    "failed",
    "cancelled",
]

InformationResolution = Literal[
    "ask_user",
    "observe_environment",
    "query_trusted_service",
    "use_owner_approved_preference",
    "use_safe_default",
    "unresolvable",
]
InformationGapOwner = Literal["fast_planner"]
InformationGapSourceKind = Literal["unresolved_meaning", "execution_input"]
InformationGapResolutionSource = Literal[
    "authoritative_context",
    "trusted_observation",
    "trusted_query",
    "owner_preference",
    "capability_schema",
    "safe_default",
]

PlanningResultKind = Literal[
    "direct_capability",
    "composed_plan",
    "needs_context",
    "needs_clarification",
    "needs_confirmation",
    "unavailable",
    "refused",
]


def semantic_goal_fingerprint(goal: "SemanticGoal") -> str:
    payload = json.dumps(goal.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_goal_meaning_update(goal: "SemanticGoal", update: dict[str, Any]) -> "SemanticGoal":
    """Apply source-selected requirements atomically, without interpreting text.

    Requirement indices and field paths are GA continuity decisions. All new
    values are exact copies of accepted GI; the supplied retained Goal snapshot
    must still match. This function neither plans nor changes Work/Evidence.
    """
    from .core_interpretation import CognitiveResponsibilityProposal

    allowed = {"base_goal_fingerprint", "replace_requirement_indices", "source_turn_id",
               "source_responsibilities", "binding_changes"}
    if set(update) != allowed or update["base_goal_fingerprint"] != semantic_goal_fingerprint(goal):
        raise ValueError("Goal meaning update requires the exact unchanged source snapshot")
    turn_id = str(update["source_turn_id"] or "").strip()
    if not turn_id:
        raise ValueError("Goal meaning update requires source turn identity")
    sources = [CognitiveResponsibilityProposal.model_validate(item)
               for item in update["source_responsibilities"]]
    by_ref = {item.local_ref: item for item in sources}
    if not sources or len(by_ref) != len(sources):
        raise ValueError("Goal meaning update requires unique accepted GI sources")
    retained_mode = goal.metadata.get("output_mode", "unspecified")
    if any(item.output_mode not in {"unspecified", retained_mode}
           for item in sources) and retained_mode != "unspecified":
        raise ValueError("a changed outcome modality requires an explicitly sourced replacement Goal")
    criteria = list(goal.success_criteria or [goal.description])
    replaced = update["replace_requirement_indices"]
    if (not isinstance(replaced, list) or any(type(index) is not int or index < 0 or index >= len(criteria)
                                            for index in replaced)
            or len(replaced) != len(set(replaced))):
        raise ValueError("Goal meaning update references an unavailable requirement")
    prior_sources = goal.metadata.get("requirement_sources")
    if not isinstance(prior_sources, list) or len(prior_sources) != len(criteria):
        prior_sources = [{"origin": "retained_goal", "goal_id": goal.goal_id,
                          "goal_version": goal.version, "requirement_index": index,
                          "outcome": outcome} for index, outcome in enumerate(criteria)]
    kept = [index for index in range(len(criteria)) if index not in replaced]
    criteria = [criteria[index] for index in kept] + [item.outcome for item in sources]
    provenance = [copy.deepcopy(prior_sources[index]) for index in kept] + [
        {"origin": "gi", "turn_id": turn_id, "responsibility": item.model_dump(mode="json")}
        for item in sources
    ]
    values = goal.model_dump(mode="json")
    seen_paths: set[tuple[str, ...]] = set()
    for change in update["binding_changes"]:
        path = change["path"]
        if (not isinstance(path, list) or len(path) < 2
                or path[0] not in {"object", "constraints", "resource_responsibility"}
                or any(not isinstance(part, str) or not part or part.startswith("_") for part in path)):
            raise ValueError("Goal binding change has an invalid semantic path")
        key = tuple(path)
        if any(key[:len(other)] == other or other[:len(key)] == key for other in seen_paths):
            raise ValueError("Goal binding changes must not overlap")
        seen_paths.add(key)
        source = by_ref.get(change["source_responsibility_ref"])
        if source is None or change["source_binding"] not in source.bindings:
            raise ValueError("Goal binding change has no exact GI source")
        parent: Any = values
        for part in path[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                raise ValueError("Goal binding change parent is absent from retained state")
            parent = parent[part]
        if not isinstance(parent, dict):
            raise ValueError("Goal binding change parent must be a semantic object")
        parent[path[-1]] = copy.deepcopy(source.bindings[change["source_binding"]])
    values.update(description="; ".join(criteria), success_criteria=criteria,
                  version=goal.version + 1,
                  source_responsibility_refs=list(dict.fromkeys([*goal.source_responsibility_refs, *by_ref])))
    values["metadata"]["requirement_sources"] = provenance
    resource = values.get("resource_responsibility") or {}
    named_surfaces = [values["object"].get("bindings", {}), values["constraints"],
                      resource.get("resource", {}).get("attributes", {}),
                      resource.get("source", {}).get("bindings", {})]
    for source in sources:
        for name, expected in source.bindings.items():
            for surface in named_surfaces:
                if name in surface:
                    actual = surface[name]
                    if isinstance(actual, dict) and "value" in actual:
                        actual = actual["value"]
                    if actual != expected:
                        raise ValueError(f"Goal field {name!r} conflicts with its accepted GI binding")
    return SemanticGoal.model_validate(values)


class SemanticGoal(BaseModel):
    """Open semantic outcome retained independently from a concrete skill plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    goal_id: str | None = None
    version: int = Field(default=1, ge=1)
    responsibility_status: ResponsibilityStatus = "open"
    description: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    beneficiary: str | None = None
    object: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    success_criteria: list[str] = Field(default_factory=list)
    resource_responsibility: AcquireAndDeliverResource | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    source_responsibility_refs: list[str] = Field(default_factory=list)
    related_goal_ids: list[str] = Field(default_factory=list)
    supersedes_goal_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "goal_id",
        "description",
        "source_text",
        "beneficiary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_whitespace(value)

    @field_validator(
        "source_responsibility_refs",
        "related_goal_ids",
        "supersedes_goal_ids",
        mode="before",
    )
    @classmethod
    def normalize_related_goal_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("related_goal_ids must be a list or string")
        return list(dict.fromkeys(
            normalized
            for item in value
            if (normalized := " ".join(str(item or "").strip().split()))
        ))

    @model_validator(mode="after")
    def validate_related_goals(self) -> "SemanticGoal":
        if self.goal_id and self.goal_id in self.related_goal_ids:
            raise ValueError("related_goal_ids must not contain the Goal itself")
        if self.goal_id and self.goal_id in self.supersedes_goal_ids:
            raise ValueError("supersedes_goal_ids must not contain the Goal itself")
        if set(self.related_goal_ids).intersection(self.supersedes_goal_ids):
            raise ValueError(
                "a Goal cannot treat the same prior Goal as both related and superseded"
            )
        return self

    @field_validator("success_criteria", mode="before")
    @classmethod
    def normalize_criteria(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("success_criteria must be a list or string")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text:
                out.append(text)
        return out

    @field_validator("object", "constraints", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class InformationGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    blocking: bool = True
    required_for: list[str] = Field(default_factory=list)
    preferred_resolution: InformationResolution
    candidate_values: list[Any] = Field(default_factory=list)
    resolved: bool = False
    resolution_value: Any = None
    owner: InformationGapOwner | None = None
    source_kind: InformationGapSourceKind | None = None
    source_reference: str = ""
    resolution_sources_considered: list[InformationGapResolutionSource] = Field(
        default_factory=list,
        max_length=6,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("gap_id", "description", "source_reference", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("required_for", mode="before")
    @classmethod
    def normalize_required_for(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("required_for must be a list or string")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class ResponseStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    speech_act: str = Field(default="inform", min_length=1)
    commitment_state: CommitmentState = "none"
    must_not_claim_completion: bool = True
    reuse_current_turn_speech: bool = False
    reused_speech_event_id: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    covers_task_ids: list[str] = Field(default_factory=list)
    covers_goal_ids: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    coordination_id: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    delivery_role: Literal[
        "response",
        "activity_companion",
        "performance",
    ] = Field(
        default="response",
        exclude_if=lambda value: value == "response",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "text",
        "speech_act",
        "coordination_id",
        "reused_speech_event_id",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("covers_task_ids", "covers_goal_ids", "claims", mode="before")
    @classmethod
    def normalize_text_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected a list or string")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_completion_contract(self) -> "ResponseStage":
        terminal = {"completed", "failed", "cancelled"}
        if self.must_not_claim_completion and self.commitment_state in terminal:
            raise ValueError(
                "terminal commitment_state requires must_not_claim_completion=false"
            )
        if self.must_not_claim_completion and any(
            claim.strip().casefold() in terminal for claim in self.claims
        ):
            raise ValueError(
                "terminal claims require must_not_claim_completion=false"
            )
        if self.reuse_current_turn_speech:
            if not self.reused_speech_event_id:
                raise ValueError(
                    "reused current-turn speech requires reused_speech_event_id"
                )
            if not self.must_not_claim_completion or self.commitment_state in terminal:
                raise ValueError(
                    "reused current-turn speech may acknowledge pending work only"
                )
            if self.coordination_id or self.delivery_role != "response":
                raise ValueError(
                    "reused current-turn speech must remain an uncoordinated response"
                )
        elif self.reused_speech_event_id:
            raise ValueError(
                "reused_speech_event_id requires reuse_current_turn_speech=true"
            )
        if self.coordination_id and self.delivery_role == "response":
            raise ValueError(
                "coordinated speech requires activity_companion or performance role"
            )
        if not self.coordination_id and self.delivery_role != "response":
            raise ValueError(
                "non-response delivery roles require coordination_id"
            )
        return self


class ResponsePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    immediate: ResponseStage | None = None
    pre_action: ResponseStage | None = None
    progress: list[ResponseStage] = Field(default_factory=list)
    final: ResponseStage | None = None


class SemanticTaskOperation(BaseModel):
    """Advisory semantic change proposed by a model for deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    operation_id: str = Field(min_length=1)
    operation: TaskOperationName
    target_task_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    relationship: str = ""
    goal: SemanticGoal | None = None
    goal_update: dict[str, Any] = Field(default_factory=dict)
    information_gaps: list[InformationGap] = Field(default_factory=list)
    resolved_gap_ids: list[str] = Field(default_factory=list)
    status_update: TaskLifecycleStatus | None = None
    commitment_state: CommitmentState | None = None
    response_plan: ResponsePlan | None = None
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "operation_id",
        "relationship",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("target_task_ids", "resolved_gap_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("task and gap IDs must be a list or string")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @field_validator("goal_update", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "SemanticTaskOperation":
        if self.operation == "create" and self.goal is None:
            raise ValueError("operation=create requires goal")
        if self.operation != "create" and not self.target_task_ids:
            raise ValueError(f"operation={self.operation} requires target_task_ids")
        if self.operation in {"modify", "clarification_answer", "correct"}:
            if (
                not self.goal_update
                and self.goal is None
                and not self.information_gaps
                and not self.resolved_gap_ids
                and self.status_update is None
            ):
                raise ValueError(
                    f"operation={self.operation} requires a goal update, gap update, or status update"
                )
        return self


class SemanticTaskOperationSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    operations: list[SemanticTaskOperation] = Field(default_factory=list)
    response_plan: ResponsePlan | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class TaskContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    task_id: str = Field(min_length=1)
    status: TaskLifecycleStatus = "open"
    semantic_goal: SemanticGoal
    goal_version: int = Field(default=1, ge=1)
    plan_version: int = Field(default=0, ge=0)
    open_information_gaps: list[InformationGap] = Field(default_factory=list)
    confirmation: dict[str, Any] | None = None
    commitment_state: CommitmentState = "none"
    last_user_update: str = ""
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "last_user_update", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("confirmation", "evidence_summary", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return reject_forbidden_low_level_fields(value)


class PlanningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    task_id: str = Field(min_length=1)
    goal_version: int = Field(ge=1)
    result: PlanningResultKind
    plan: dict[str, Any] = Field(default_factory=dict)
    information_gaps: list[InformationGap] = Field(default_factory=list)
    unavailable_reason: str | None = None
    response_plan: ResponsePlan | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "unavailable_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_whitespace(value)

    @field_validator("plan", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)
