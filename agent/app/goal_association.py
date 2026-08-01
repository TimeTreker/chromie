from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .clients.ollama_client import (
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
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
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

    relationship: GoalAssociationModelRelationship
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


class GoalAssociationModelGoal(BaseModel):
    """Minimal model-facing semantic goal. IDs and persistence fields are host-owned."""

    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)
    responsibility_kind: GoalResponsibilityKind = Field(
        default="other",
        description=(
            "How this user-visible responsibility can be completed: an "
            "effectful action, a direct spoken response, work whose completion "
            "depends on capability planning, or another semantic mode."
        ),
    )
    bindings: list[GoalAssociationModelBinding] = Field(
        default_factory=list,
        max_length=12,
    )

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


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
            clarification_only=self._clarification_only(request),
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
        semantic_review_attempted = False

        try:
            raw = await self.ollama.generate(
                self._build_prompt(request, candidate_goals, output_type=output_type),
                system=self._system_prompt(output_type),
                options=generation_options,
                response_format=response_schema,
            )
            if not isinstance(raw, dict):
                raise ValueError("goal-association response is not a JSON object")
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
                logger.warning(
                    "goal_association_contract_repair_start sid=%s validation_errors=%s "
                    "raw_output=%s",
                    request.sid,
                    initial_validation_error,
                    self._bounded_json(raw, 4000),
                )
                repaired = await self.ollama.generate(
                    self._build_repair_prompt(
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
                )
                if not isinstance(repaired, dict):
                    raise ValueError("goal-association repair response is not a JSON object")
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
                    "strategy": "schema_constrained_model_revision",
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
            model_output = output_type.model_validate(review_candidate)
            review_triggers = self._semantic_review_triggers(model_output)
            if review_triggers:
                semantic_review_attempted = True
                logger.info(
                    "goal_association_semantic_review_start sid=%s triggers=%s",
                    request.sid,
                    ",".join(review_triggers),
                )
                reviewed = await self.ollama.generate(
                    self._build_semantic_review_prompt(
                        request=request,
                        candidate_goals=candidate_goals,
                        output_type=output_type,
                        raw=review_candidate,
                        triggers=review_triggers,
                    ),
                    system=self._semantic_review_system_prompt(output_type),
                    options=generation_options,
                    response_format=response_schema,
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
                semantic_review_raw = reviewed
                resolution = await self._validate_contract_output(
                    reviewed,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                review_metadata = dict(resolution.metadata)
                if repair_attempted:
                    review_metadata["contract_repair"] = {
                        "attempted": True,
                        "succeeded": True,
                        "strategy": "schema_constrained_model_revision",
                        "attempt_count": 1,
                    }
                review_metadata["semantic_review"] = {
                    "attempted": True,
                    "succeeded": True,
                    "strategy": "model_owned_goal_association_review",
                    "triggers": review_triggers,
                    "attempt_count": 1,
                }
                resolution = resolution.model_copy(
                    update={"metadata": review_metadata}
                )
                logger.info(
                    "goal_association_semantic_review_done sid=%s status=success",
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
                "initial_validation_errors=%s initial_raw=%s repair_raw=%s "
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
            if initial_raw is not None:
                metadata["initial_raw_output"] = self._bounded_json(initial_raw, 4000)
            if repair_raw is not None:
                metadata["repair_raw_output"] = self._bounded_json(repair_raw, 4000)
            if semantic_review_raw is not None:
                metadata["semantic_review_raw_output"] = self._bounded_json(
                    semantic_review_raw,
                    4000,
                )
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
        return self._validate(
            resolution,
            candidate_goals=candidate_goals,
            request=request,
        )

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
        if self._clarification_only(request) and model_output.decision != "clarify":
            raise ValueError(
                "an admitted clarify route requires a clarification-only Goal "
                "Association result"
            )
        collection_bindings = self._action_collection_bindings(model_output)
        if collection_bindings:
            raise ValueError(
                "new Goal bindings cannot contain action collections; emit one "
                "new_goals item for every independently observable responsibility: "
                + ", ".join(collection_bindings)
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
    def _semantic_review_triggers(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
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
        if isinstance(model_output, GoalAssociationModelOutput) and any(
            association.relationship in {"modify", "replace"}
            for association in model_output.associations
        ):
            triggers.append("existing_goal_semantic_update")
        return triggers

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
                    if "responsibility_kind" in node_properties:
                        node_required = node.setdefault("required", [])
                        if "responsibility_kind" not in node_required:
                            node_required.append("responsibility_kind")
                    target_ids = node_properties.get("target_goal_ids")
                    if isinstance(target_ids, dict):
                        target_ids["items"] = {
                            "type": "string",
                            "enum": active_ids,
                        }
                        target_ids["uniqueItems"] = True
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
    def _clarification_only(request: AgentRunRequest) -> bool:
        return str(request.route_decision.route or "").strip() == "clarify"

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
        clarification_authority = (
            "The admitted Cognitive Core disposition is clarify. Preserve that "
            "semantic authority: return decision=clarify with one concise "
            "user-facing question, associations=[], and new_goals=[]. Do not "
            "reinterpret the low-information turn as a social goal.\n\n"
            if self._clarification_only(request)
            else ""
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
                "For continuity with an existing goal, emit an associations item with relationship, target_goal_ids, confidence, reason_summary, and optionally updated_description, resolved_gap_ids, and requires_replan. "
                "relationship must be copied exactly from [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"replace\",\"merge\",\"split\",\"reference\"]. "
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
            + clarification_authority
            + "The model-facing contract is deliberately small. "
            "The host owns all IDs, versions, source text, constraints, metadata, persistence fields, and canonical object construction. "
            "Never emit id, goal_id, association_id, turn_id, schema_version, source_text, constraints, object, metadata, success_criteria, skills, or plans. Referent IDs may only be copied from the supplied discourse context; new referent IDs are Host-generated.\n\n"
            "Create one new goal for each independently satisfiable user responsibility. Emit exactly one new_goals item containing description and typed bindings for each responsibility. "
            "Every new Goal must also declare responsibility_kind. Use executable_action for a user-visible physical or other effectful action; spoken_response only when the responsibility is completed directly from Chromie's authored speech or text without external evidence, including singing, telling a joke, or a social reply; capability_dependent when lookup, retrieval, computation, or another capability must determine completion; and other only when none of those meanings is accurate. This is the Goal's completion modality, not a capability choice. The eventual spoken delivery of a capability result is part of that same capability_dependent Goal, never an additional spoken_response Goal. Persona, tone, wording, and answer delivery are not independent Goals. "
            "A standalone social interaction such as a greeting, thanks, reassurance request, or casual check-in is itself one satisfiable conversational Goal: respond naturally to that social act. Do not treat it as an empty turn. "
            "A greeting or politeness preamble attached to a substantive request is conversational framing, not a separate Goal unless the user independently asks for a social response. Owner-approved identity and personality shape expression only; never create a Goal merely to mention age, identity, warmth, curiosity, or another style trait. "
            "A factual lookup and the user's requested interpretation of that same evidence are one Goal when one capability result can satisfy both, such as checking weather and judging whether it is hot. Do not split evidence acquisition from the answer derived from that evidence. "
            "A physical action and a conversational answer or spoken performance are independent goals. Physical actions are independent goals whenever either can succeed or fail separately, including actions requested simultaneously, with shared duration, or in one coordinated sentence. Do not collapse walking, gestures, speech, or other independently observable responsibilities into one Goal merely because they share timing. Before returning, verify that every independently observable responsibility appears in exactly one new_goals item: no merged action-collection Goal and no duplicated responsibility across Goals. "
            "Put all user-visible parameters such as count, duration, direction, target, or requested content into the natural-language description. "
            "Also preserve semantic qualifiers such as temporal scope, comparison period, and requested answer shape. Never silently rewrite annual, seasonal, historical, comparative, or otherwise broad scope into current, today, tomorrow, or another narrower scope. If the intended scope is materially ambiguous, return clarification instead of choosing a narrower interpretation. "
            "Resolve references, pronouns, demonstratives, ellipsis, and task mentions before planning. Authority order is: explicit current user meaning; foreground scoped discourse referents; candidate Goal bindings; recent dialogue. Phrases such as ‘the last task I told you’ may semantically associate with an active, recoverable, or retained recent terminal Goal, but the model must decide that relationship from the supplied Goal state and dialogue—not from a Host phrase table. Tool-result memory is not reference-resolution authority and must never decide what an unresolved expression refers to. "
            "When the user introduces or explicitly corrects a salient entity, emit referent_updates. Use operation=correct with target_referent_ids when a new value supersedes an earlier referent in the current discourse; the old referent remains available in its own task scope but becomes background. Use operation=introduce for a new salient entity, and focus/background/retire only for supplied referent IDs. "
            "Use resolved_references only for indirect references whose denotation must be selected from a supplied discourse referent or active Goal binding, such as pronouns, demonstratives, ellipsis, aliases, corrections, or task mentions. Do not emit resolved_references for an ordinary explicit entity mention such as a directly named place; represent that meaning in the new Goal bindings and, when it is salient for future dialogue, in referent_updates. Every resolved_references item must copy a supplied referent_id and include explicit confidence. If resolution is materially ambiguous, return decision=clarify rather than selecting a value from stale evidence or recency alone. "
            "Each new Goal must include typed bindings for material entities and parameters already resolved here. For weather, a resolved place belongs in a binding named location. Downstream planners must receive the explicit binding rather than an unresolved expression. "
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
            "The clarification field is only a concise user-facing question. Never put analysis, rationale, translation, route labels, validator errors, model failures, or system diagnostics in clarification. Put optional compact rationale in reason_summary. If the user meaning is materially ambiguous, use decision=clarify; otherwise keep clarification empty.\n\n"
            "Abstract decomposition example: a request to perform action A, then action B, and answer question C produces three new_goals descriptions: perform action A; perform action B; answer question C. "
            "This example is structural, not a phrase-matching rule.\n\n"
            + output_instructions
            + "Each new_goals object contains description, responsibility_kind, and bindings only. bindings is an array of typed semantic parameters with name, entity_type, value, optional copied referent_id, and confidence. Use [] when no material binding exists. Every referent_updates item and every resolved_references item must include explicit confidence; never rely on an omitted-field default.\n\n"
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{personality_json}\n\n"
            + skill_section
            + "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 6500)}\n\n"
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
        clarification_authority = (
            "The admitted Cognitive Core disposition is clarify. Return only "
            "decision=clarify with a concise user-facing question; do not create "
            "or associate goals.\n\n"
            if self._clarification_only(request)
            else ""
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
                "Existing Goal bindings are provenance-stable and cannot be changed by an association. If current user meaning changes a material binding, use decision=create_goals with one fully bound replacement Goal rather than a description-only association. "
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
            + clarification_authority
            + "\n\n"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            + "\n\nResolved references are only for indirect references bound to a supplied discourse referent or active Goal binding. Direct explicit entity mentions belong in Goal bindings and salient referent updates, not resolved_references. Every resolved reference and referent update must include explicit confidence.\n\nOwner-approved Chromie identity JSON:\n"
            + identity_json
            + "\n\nOwner-approved Personality Expression JSON:\n"
            + personality_json
            + "\n\n"
            + skill_section
            + f"Latest user turn:\n{request.text}\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 7000)}\n\n"
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
            + "Select exactly one decision branch. clarification is only a concise user-facing question and must be empty for non-clarify decisions. Each new_goals item contains description, responsibility_kind, and bindings only. executable_action is effectful work; spoken_response is direct authored speech or text, including spoken performance; capability_dependent requires capability planning; other is only for a genuinely different modality. Preserve or repair explicit discourse resolution and referent updates; never use tool-result contents to infer a reference. "
            "The host owns every ID and persistence field. Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
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
        return (
            f"Independently review this model-authored {contract_name} DTO and "
            "return the complete final JSON object. The Host supplied only typed "
            f"review triggers {self._bounded_json(triggers, 800)}. A trigger is "
            "not proof that any semantic choice is wrong. "
            "Use semantic reasoning over the authoritative user turn and bounded "
            "dialogue context. Do not use phrase matching, binding equality, "
            "numeric suffixes, lexical overlap, or another deterministic shortcut.\n\n"
            "Keep separate Goals when the user truly requested an independently "
            "satisfiable direct spoken or text response in addition to capability "
            "work, such as a song, joke, or unrelated social answer. When a "
            "spoken_response item merely phrases, reports, explains, or interprets "
            "the evidence acquired by a capability_dependent item, the capability "
            "Goal owns that delivery: remove the redundant spoken Goal and preserve "
            "the complete requested outcome and correct semantic bindings in the "
            "capability Goal. Never invent, copy, or repair an entity by character "
            "pattern; resolve it from the user meaning and supplied discourse. "
            "Persona and wording are expression concerns, not extra Goals.\n\n"
            "Existing Goal bindings are provenance-stable at this contract. An "
            "association may update only its description and lifecycle relation; "
            "it cannot rewrite typed material bindings. If the current user meaning "
            "changes a material entity or parameter, preserve the earlier Goal and "
            "its evidence, then return decision=create_goals with one fully bound "
            "replacement Goal for the corrected responsibility. The model decides "
            "whether meaning actually changed. Do not infer a correction from words, "
            "syntax, or binding inequality alone. If the newly salient entity has a "
            "supplied referent ID, emit a valid correct update targeting it; otherwise "
            "use introduce rather than fabricating a referent ID or emitting an "
            "invalid correction.\n\n"
            "The Host is asking for a semantic judgment, not prescribing merge or "
            "separation. Preserve every genuinely independent responsibility, all "
            "valid associations, and all valid discourse updates. Return only JSON "
            f"with {output_fields}. The exact schema is enforced out-of-band.\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 6500)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON:\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "DTO to review JSON:\n"
            f"{self._bounded_json(raw, 6000)}\n\n"
            "Tool-result contents are intentionally absent. Do not use remembered "
            "capability results to decide Goal structure or claim completion.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    @staticmethod
    def _semantic_review_system_prompt(
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
            f"You are Chromie's independent semantic reviewer for the "
            f"{contract_name} boundary. Decide with model reasoning whether "
            "responsibilities are genuinely independent and whether an existing "
            "Goal relation preserves authoritative material bindings. "
            "Return only the complete final DTO as JSON. The Host owns validation, "
            "IDs, lifecycle, and persistence and does not make this semantic choice."
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
            "Conversational framing attached to substantive work is not a separate Goal; a standalone social interaction remains one conversational Goal. One lookup and an interpretation derived from the same evidence are one Goal. "
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
            new_goals.append(
                SemanticGoal(
                    goal_id=goal_id,
                    description=item.description,
                    source_text=request.text,
                    object={"bindings": binding_map} if binding_map else {},
                    constraints={},
                    success_criteria=[item.description],
                    metadata={
                        "model_boundary": type(model_output).__name__,
                        "host_generated_fields": True,
                        "responsibility_kind": item.responsibility_kind,
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
