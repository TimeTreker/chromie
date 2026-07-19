from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .clients.ollama_client import OllamaClient, llm_failure_metadata
from .schema import AgentRunRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata

try:
    from chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from chromie_contracts.semantic_task import SemanticGoal
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from shared.chromie_contracts.semantic_task import SemanticGoal

logger = logging.getLogger("chromie.agent.goal_association")


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


class GoalAssociationModelGoal(BaseModel):
    """Minimal model-facing semantic goal. IDs and persistence fields are host-owned."""

    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


class GoalSegmentationModelOutput(BaseModel):
    """Semantic goal segmentation used when no association target exists."""

    model_config = ConfigDict(extra="forbid")

    new_goals: list[GoalAssociationModelGoal] = Field(
        default_factory=list,
        max_length=8,
    )
    clarification: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator("clarification", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalSegmentationModelOutput":
        if self.clarification and self.new_goals:
            raise ValueError("clarification must not be mixed with new goals")
        if not self.clarification and not self.new_goals:
            raise ValueError("output must contain new_goals or clarification")
        return self


class GoalAssociationModelOutput(BaseModel):
    """Small semantic DTO returned by the Goal Association model."""

    model_config = ConfigDict(extra="ignore")

    associations: list[GoalAssociationModelAssociation] = Field(default_factory=list)
    new_goals: list[GoalAssociationModelGoal] = Field(default_factory=list)
    clarification: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator("clarification", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "GoalAssociationModelOutput":
        if self.clarification and (self.associations or self.new_goals):
            raise ValueError("clarification must not be mixed with goal changes")
        if not self.clarification and not self.associations and not self.new_goals:
            raise ValueError("output must contain associations, new_goals, or clarification")
        return self


class GoalAssociationResolver:
    """Resolve continuity before creation without mutating runtime state."""

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
        active_goals = self._active_goals(request)
        turn_id = self._turn_id(request)
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ) = (
            GoalAssociationModelOutput
            if active_goals
            else GoalSegmentationModelOutput
        )
        response_schema = self._response_schema(output_type, active_goals)
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        initial_raw: dict[str, Any] | None = None
        repair_raw: dict[str, Any] | None = None
        initial_validation_error = ""
        repair_attempted = False

        try:
            raw = await self.ollama.generate(
                self._build_prompt(request, active_goals, output_type=output_type),
                system=self._system_prompt(output_type),
                options=generation_options,
                response_format=response_schema,
            )
            if not isinstance(raw, dict):
                raise ValueError("goal-association response is not a JSON object")
            initial_raw = raw
            try:
                resolution = self._validate_contract_output(
                    raw,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
            except ValidationError as exc:
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
                        active_goals=active_goals,
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
                resolution = self._validate_contract_output(
                    repaired,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
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
                "repair_attempted=%s initial_validation_errors=%s initial_raw=%s repair_raw=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                failure["retryable"],
                repair_attempted,
                initial_validation_error,
                self._bounded_json(initial_raw, 4000) if initial_raw is not None else "",
                self._bounded_json(repair_raw, 4000) if repair_raw is not None else "",
            )
            integrity_metadata = cognitive_integrity_metadata(stage="goal_association", exc=exc, request=request)
            metadata: dict[str, Any] = {
                "resolver": "goal_association_agent",
                "status": status,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                **failure,
                "active_goal_count": len(active_goals),
                "sid": request.sid,
                "contract_schema": output_type.__name__,
                "contract_repair_attempted": repair_attempted,
                "contract_repair_succeeded": False,
                **integrity_metadata,
            }
            if initial_validation_error:
                metadata["initial_validation_errors"] = initial_validation_error
            if initial_raw is not None:
                metadata["initial_raw_output"] = self._bounded_json(initial_raw, 4000)
            if repair_raw is not None:
                metadata["repair_raw_output"] = self._bounded_json(repair_raw, 4000)
            return GoalAssociationResolution(
                turn_id=turn_id,
                clarification=self._safe_clarification(
                    request,
                    has_active_goals=bool(active_goals),
                ),
                confidence=0.0,
                reason_summary=(
                    "Goal association output did not satisfy the schema after one model repair attempt; no goal operation was accepted."
                    if repair_attempted
                    else "Goal association model was unavailable; no goal operation was accepted."
                ),
                metadata=metadata,
            )
        return self._validate(resolution, active_goals=active_goals, request=request)

    def _validate_contract_output(
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
        return self._expand_model_output(
            model_output,
            request=request,
            turn_id=turn_id,
        )

    @staticmethod
    def _validation_error_json(exc: ValidationError) -> str:
        return json.dumps(
            exc.errors(include_url=False),
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
        active_goals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        schema = copy.deepcopy(output_type.model_json_schema())
        active_ids = [
            " ".join(str(item.get("goal_id") or "").strip().split())
            for item in active_goals
            if " ".join(str(item.get("goal_id") or "").strip().split())
        ]
        properties = schema.get("properties", {})
        new_goals = properties.get("new_goals")
        if isinstance(new_goals, dict):
            new_goals["maxItems"] = 8

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                node_properties = node.get("properties")
                if isinstance(node_properties, dict):
                    target_ids = node_properties.get("target_goal_ids")
                    if isinstance(target_ids, dict) and active_ids:
                        target_ids["items"] = {"type": "string", "enum": active_ids}
                        target_ids["uniqueItems"] = True
                if node.get("type") == "object":
                    node["additionalProperties"] = False
                for value in node.values():
                    constrain(value)
            elif isinstance(node, list):
                for value in node:
                    constrain(value)

        constrain(schema)
        if output_type is GoalSegmentationModelOutput:
            return schema

        schema["oneOf"] = [
            {
                "properties": {
                    "clarification": {"type": "string", "minLength": 1},
                    "associations": {"type": "array", "maxItems": 0},
                    "new_goals": {"type": "array", "maxItems": 0},
                },
                "required": ["clarification", "associations", "new_goals"],
            },
            {
                "properties": {"clarification": {"type": "string", "maxLength": 0}},
                "anyOf": [
                    {"properties": {"associations": {"type": "array", "minItems": 1}}},
                    {"properties": {"new_goals": {"type": "array", "minItems": 1}}},
                ],
                "required": ["clarification", "associations", "new_goals"],
            },
        ]
        return schema

    def _active_goals(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("active_goal_snapshots")
        if not isinstance(raw, list):
            raw = []
        out: list[dict[str, Any]] = []
        for item in raw[: self.max_active_goals]:
            if not isinstance(item, dict):
                continue
            try:
                out.append(ActiveGoalSnapshot.model_validate(item).model_dump(mode="json", exclude_none=True))
            except Exception:
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
        active_goals: list[dict[str, Any]],
        *,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        route = request.route_decision
        route_advisory = {
            "route": route.route,
            "intent": route.intent,
            "confidence": route.confidence,
            "routes": [
                {"route": item.route, "intent": item.intent, "confidence": item.confidence}
                for item in route.routes[:8]
            ],
        }
        if output_type is GoalSegmentationModelOutput:
            state_instructions = (
                "There are no active Goals, so no existing-goal relationship is possible and the contract intentionally has no associations field. "
                "Segment the authoritative user turn into independent new Goals, or return a clarification if the meaning is materially ambiguous. "
            )
            output_instructions = (
                "Return only JSON with new_goals, clarification, confidence, and reason_summary. "
                "The decoder enforces the exact GoalSegmentationModelOutput JSON Schema. "
            )
        else:
            state_instructions = (
                "Resolve continuity before creation using semantic reasoning. "
                "For continuity with an existing goal, emit an associations item with relationship, target_goal_ids, confidence, reason_summary, and optionally updated_description, resolved_gap_ids, and requires_replan. "
                "relationship must be copied exactly from [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"replace\",\"merge\",\"split\",\"reference\"]. "
                "Associations may target only IDs from the active-goal list. "
            )
            output_instructions = (
                "Return only JSON with associations, new_goals, clarification, confidence, and reason_summary. "
                "The decoder enforces the exact GoalAssociationModelOutput JSON Schema. "
            )
        return (
            state_instructions
            + "The model-facing contract is deliberately small. "
            "The host owns all IDs, versions, source text, constraints, metadata, persistence fields, and canonical object construction. "
            "Never emit id, goal_id, association_id, turn_id, schema_version, source_text, constraints, object, metadata, success_criteria, skills, or plans.\n\n"
            "Create one new goal for each independently satisfiable user responsibility. Emit exactly one new_goals item containing only description for each responsibility. "
            "A physical action and a conversational answer are independent goals. Ordered physical actions are independent goals when either can succeed or fail separately. "
            "Put all user-visible parameters such as count, duration, direction, target, or requested content into the natural-language description. "
            "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
            "If the user meaning is materially ambiguous, return only one concise clarification.\n\n"
            "Abstract decomposition example: a request to perform action A, then action B, and answer question C produces three new_goals descriptions: perform action A; perform action B; answer question C. "
            "This example is structural, not a phrase-matching rule.\n\n"
            + output_instructions
            + "Each new_goals object contains exactly one field: description.\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(active_goals, 6500)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-6:], 2200)}\n\n"
            "Router output is advisory JSON:\n"
            f"{self._bounded_json(route_advisory, 1400)}\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL ACTIVE GOAL IDS JSON:\n{self._bounded_json([item.get('goal_id') for item in active_goals], 1600)}"
        )

    def _build_repair_prompt(
        self,
        *,
        request: AgentRunRequest,
        active_goals: list[dict[str, Any]],
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        raw: dict[str, Any],
        validation_error: str,
    ) -> str:
        if output_type is GoalSegmentationModelOutput:
            contract_name = "Goal Segmentation"
            revision_action = "Re-evaluate the independent goal segmentation"
            state_instructions = (
                "There are no active Goals. Existing-goal associations are structurally invalid and must not appear. "
                "Re-segment every independently satisfiable responsibility into new_goals, or return only a clarification when the meaning is materially ambiguous. "
            )
            output_instructions = (
                "The exact GoalSegmentationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
                "Return only new_goals, clarification, confidence, and reason_summary. "
            )
        else:
            contract_name = "Goal Association"
            revision_action = "Re-evaluate the semantic associations"
            state_instructions = (
                "Re-evaluate continuity against only the supplied active Goal IDs. "
            )
            output_instructions = (
                "The exact GoalAssociationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
                "Return only associations, new_goals, clarification, confidence, and reason_summary. "
            )
        return (
            f"The previous minimal {contract_name} semantic DTO failed its exact contract. {revision_action} and "
            "return one corrected JSON object. Preserve valid semantic judgments, but revise every field needed to satisfy "
            "the schema and validation errors. Do not explain the correction and do not use synonym substitution rules.\n\n"
            + state_instructions
            + "\n\n"
            f"Latest user turn:\n{request.text}\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(active_goals, 7000)}\n\n"
            "Previous model output JSON:\n"
            f"{self._bounded_json(raw, 5000)}\n\n"
            "Exact validation errors JSON:\n"
            f"{validation_error}\n\n"
            + output_instructions
            + "Each new_goals item contains only description. "
            "The host owns every ID and persistence field. Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
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
                "You are Chromie's Goal Segmentation model. No active Goal IDs exist, so association with existing work is impossible. "
                "Use semantic reasoning to preserve independently satisfiable user responsibilities as separate new Goals, but never turn plan steps into goals. "
                "Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
                "You are advisory only and never execute or commit. Return JSON only."
            )
        return (
            "You are Chromie's Goal Association and Segmentation model. Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
            "Apply continuity before creation. Understand references from meaning, bounded active goals, unresolved gaps, and dialogue context. "
            "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
            "Preserve independent user responsibilities as separate goals, but never turn plan steps into goals. "
            "You are advisory only and never execute or commit. Return JSON only."
        )

    def _expand_model_output(
        self,
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: AgentRunRequest,
        turn_id: str,
    ) -> GoalAssociationResolution:
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
                        or item.relationship in {"modify", "clarify", "replace", "merge", "split"}
                    ),
                )
            )

        new_goals: list[SemanticGoal] = []
        for index, item in enumerate(model_output.new_goals):
            digest = hashlib.sha256(
                f"{turn_id}|goal|{index}|{item.description}".encode("utf-8")
            ).hexdigest()[:20]
            new_goals.append(
                SemanticGoal(
                    goal_id=f"goal_{digest}",
                    description=item.description,
                    source_text=request.text,
                    object={},
                    constraints={},
                    success_criteria=[item.description],
                    metadata={
                        "model_boundary": type(model_output).__name__,
                        "host_generated_fields": True,
                    },
                )
            )

        return GoalAssociationResolution(
            turn_id=turn_id,
            associations=associations,
            new_goals=new_goals,
            clarification=model_output.clarification,
            confidence=model_output.confidence,
            reason_summary=model_output.reason_summary,
            metadata={
                "model_contract": type(model_output).__name__,
                "host_generated_identifiers": True,
            },
        )

    def _validate(
        self,
        resolution: GoalAssociationResolution,
        *,
        active_goals: list[dict[str, Any]],
        request: AgentRunRequest,
    ) -> GoalAssociationResolution:
        active_ids = {str(item.get("goal_id") or "") for item in active_goals}
        accepted: list[GoalAssociation] = []
        rejected: list[dict[str, Any]] = []
        for association in resolution.associations:
            reason = None
            if association.confidence < self.min_confidence:
                reason = "below_confidence_threshold"
            elif any(goal_id not in active_ids for goal_id in association.target_goal_ids):
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
                "active_goal_count": len(active_goals),
                "accepted_association_count": len(accepted),
                "new_goal_count": len(new_goals),
                "rejected_associations": rejected,
                "min_confidence": self.min_confidence,
                "sid": request.sid,
                "authority": "advisory",
            }
        )
        if not accepted and not new_goals and not resolution.clarification:
            return GoalAssociationResolution(
                turn_id=resolution.turn_id,
                clarification=self._safe_clarification(
                    request,
                    has_active_goals=bool(active_goals),
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
        has_active_goals: bool,
    ) -> str:
        if has_active_goals:
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
