from __future__ import annotations

import copy
import json
import logging
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ..clients.ollama_client import llm_failure_metadata
from .loader import AgentSkillRegistry

try:
    from chromie_contracts.agent_skill import (
        AgentSkillProjectionName,
        AgentSkillSelectionModelOutput,
        AgentSkillSelectionRequest,
        AgentSkillSelectionResolution,
        AgentSkillSummary,
        SelectedAgentSkill,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.agent_skill import (
        AgentSkillProjectionName,
        AgentSkillSelectionModelOutput,
        AgentSkillSelectionRequest,
        AgentSkillSelectionResolution,
        AgentSkillSummary,
        SelectedAgentSkill,
    )


logger = logging.getLogger("chromie.agent.agent_skills.selection")

_ROLE_LABELS: dict[AgentSkillProjectionName, str] = {
    "goal_association": "Goal Association Agent",
    "fast_planner": "Fast Planner Agent",
    "deep_planner": "Deep Planner Agent",
    "response_composer": "Response Composer Agent",
    "tool_result_interpreter": "Tool Result Interpreter Agent",
}


class AgentSkillSelectionService:
    """Model-authored optional method selection from bounded approved summaries.

    This service neither loads Skill projections nor mutates Plans, registries,
    permissions, or execution state. The caller declares the responsible Agent
    role; the model makes the semantic selection for that role.
    """

    def __init__(
        self,
        client: Any,
        registry: AgentSkillRegistry,
        *,
        max_candidates: int = 12,
        max_selected: int = 4,
        min_confidence: float = 0.55,
        num_ctx: int = 8192,
        num_predict: int = 512,
    ) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if max_selected < 1 or max_selected > max_candidates:
            raise ValueError("max_selected must be between 1 and max_candidates")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        self.client = client
        self.registry = registry
        self.max_candidates = int(max_candidates)
        self.max_selected = int(max_selected)
        self.min_confidence = float(min_confidence)
        self.num_ctx = int(num_ctx)
        self.num_predict = int(num_predict)

    async def select(
        self,
        request: AgentSkillSelectionRequest,
    ) -> AgentSkillSelectionResolution:
        candidates, candidate_total, candidate_truncated = self._discover_candidates(
            request
        )
        selection_id = f"agent-skill-selection-{uuid4().hex}"
        model_name = str(getattr(self.client, "model", "") or "") or None

        logger.info(
            "agent_skill_selection_start sid=%s turn_id=%s role=%s "
            "candidate_ids=%s candidate_total=%s truncated=%s",
            request.sid,
            request.turn_id,
            request.agent_role,
            [item.agent_skill_id for item in candidates],
            candidate_total,
            candidate_truncated,
        )

        if request.agent_role == "goal_association" and not request.goals:
            resolution = AgentSkillSelectionResolution(
                selection_id=selection_id,
                sid=request.sid,
                turn_id=request.turn_id,
                agent_role=request.agent_role,
                decision="no_skill",
                status="no_skill",
                selected_agent_skills=(),
                candidate_summaries=candidates,
                confidence=1.0,
                reason_summary=(
                    "Goal Association must establish the current Goal before "
                    "passive domain methods may be selected."
                ),
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model=model_name,
            )
            self._log_resolution(resolution)
            return resolution

        if not candidates:
            return AgentSkillSelectionResolution(
                selection_id=selection_id,
                sid=request.sid,
                turn_id=request.turn_id,
                agent_role=request.agent_role,
                decision="no_skill",
                status="no_candidates",
                selected_agent_skills=(),
                candidate_summaries=(),
                confidence=1.0,
                reason_summary=(
                    "No approved Agent Skill exposes the requested Agent projection."
                ),
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model=model_name,
            )

        prompt = self._selection_prompt(request, candidates)
        schema = self._response_schema(request, candidates)
        initial_raw: Any = None
        initial_error: str | None = None

        try:
            initial_raw = await self.client.generate(
                prompt,
                system=self._system_prompt(request.agent_role),
                options={
                    "temperature": 0.0,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                },
                response_format=schema,
                prompt_family="agent_skill_selection.primary",
                turn_id=request.turn_id,
                attempt=1,
            )
            return self._validate_output(
                initial_raw,
                request=request,
                candidates=candidates,
                selection_id=selection_id,
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model_name=model_name,
                repair_attempted=False,
                repair_succeeded=False,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            initial_error = self._validation_error_json(exc)
            logger.warning(
                "agent_skill_selection_contract_repair sid=%s turn_id=%s role=%s "
                "error=%s",
                request.sid,
                request.turn_id,
                request.agent_role,
                initial_error,
            )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.warning(
                "agent_skill_selection_model_unavailable sid=%s turn_id=%s role=%s "
                "failure_class=%s failure_domain=%s error_type=%s error=%s",
                request.sid,
                request.turn_id,
                request.agent_role,
                failure.get("failure_class"),
                failure.get("failure_domain"),
                type(exc).__name__,
                exc,
            )
            return self._failure_resolution(
                request=request,
                selection_id=selection_id,
                candidates=candidates,
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model_name=model_name,
                status="model_unavailable",
                reason_summary=(
                    "Agent Skill selection was unavailable; no optional Skill was accepted."
                ),
                exc=exc,
                repair_attempted=False,
            )

        repair_prompt = self._repair_prompt(
            request,
            candidates,
            initial_raw=initial_raw,
            validation_error=initial_error or "unknown validation error",
        )
        try:
            repaired_raw = await self.client.generate(
                repair_prompt,
                system=self._system_prompt(request.agent_role),
                options={
                    "temperature": 0.0,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                },
                response_format=schema,
                prompt_family="agent_skill_selection.repair",
                turn_id=request.turn_id,
                attempt=2,
            )
            resolution = self._validate_output(
                repaired_raw,
                request=request,
                candidates=candidates,
                selection_id=selection_id,
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model_name=model_name,
                repair_attempted=True,
                repair_succeeded=True,
            )
            logger.info(
                "agent_skill_selection_contract_repair_done sid=%s turn_id=%s "
                "role=%s status=success",
                request.sid,
                request.turn_id,
                request.agent_role,
            )
            return resolution
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.warning(
                "agent_skill_selection_contract_failed sid=%s turn_id=%s role=%s "
                "failure_class=%s failure_domain=%s error_type=%s error=%s",
                request.sid,
                request.turn_id,
                request.agent_role,
                failure.get("failure_class"),
                failure.get("failure_domain"),
                type(exc).__name__,
                exc,
            )
            return self._failure_resolution(
                request=request,
                selection_id=selection_id,
                candidates=candidates,
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model_name=model_name,
                status="model_contract_failed",
                reason_summary=(
                    "Agent Skill selection did not satisfy the closed contract after "
                    "one repair attempt; no optional Skill was accepted."
                ),
                exc=exc,
                repair_attempted=True,
            )

    def _discover_candidates(
        self,
        request: AgentSkillSelectionRequest,
    ) -> tuple[tuple[AgentSkillSummary, ...], int, bool]:
        summaries = {
            item.agent_skill_id: item
            for item in self.registry.list_summaries()
        }
        requested_ids = request.candidate_agent_skill_ids
        current_route = self._current_route(request)

        def route_applies(summary: AgentSkillSummary) -> bool:
            return bool(
                not current_route
                or not summary.applicable_routes
                or current_route in summary.applicable_routes
            )

        if requested_ids:
            ordered: list[AgentSkillSummary] = []
            for agent_skill_id in requested_ids:
                try:
                    summary = summaries[agent_skill_id]
                except KeyError as exc:
                    raise ValueError(
                        f"unknown Agent Skill candidate {agent_skill_id!r}"
                    ) from exc
                if request.agent_role not in summary.available_projections:
                    raise ValueError(
                        f"Agent Skill {agent_skill_id!r} does not expose projection "
                        f"{request.agent_role!r}"
                    )
                if not route_applies(summary):
                    raise ValueError(
                        f"Agent Skill {agent_skill_id!r} is not applicable to "
                        f"route {current_route!r}"
                    )
                ordered.append(summary)
        else:
            ordered = [
                summary
                for summary in summaries.values()
                if request.agent_role in summary.available_projections
                and route_applies(summary)
            ]
            ordered.sort(key=lambda item: item.agent_skill_id)

        candidate_total = len(ordered)
        bounded = tuple(ordered[: self.max_candidates])
        return bounded, candidate_total, candidate_total > len(bounded)

    @staticmethod
    def _current_route(request: AgentSkillSelectionRequest) -> str:
        for item in request.context_summary:
            key, separator, value = item.partition("=")
            if separator and key.strip().casefold() == "route":
                return "_".join(
                    value.strip().casefold().replace("-", "_").split()
                )
        return ""

    def _validate_output(
        self,
        raw: Any,
        *,
        request: AgentSkillSelectionRequest,
        candidates: tuple[AgentSkillSummary, ...],
        selection_id: str,
        candidate_total: int,
        candidate_truncated: bool,
        model_name: str | None,
        repair_attempted: bool,
        repair_succeeded: bool,
    ) -> AgentSkillSelectionResolution:
        if not isinstance(raw, dict):
            raise TypeError("Agent Skill selection output must be a JSON object")
        output = AgentSkillSelectionModelOutput.model_validate(raw)
        candidate_by_id = {item.agent_skill_id: item for item in candidates}
        allowed_goal_ids = {item.goal_id for item in request.goals}

        if output.decision == "no_skill":
            resolution = AgentSkillSelectionResolution(
                selection_id=selection_id,
                sid=request.sid,
                turn_id=request.turn_id,
                agent_role=request.agent_role,
                decision="no_skill",
                status="no_skill",
                selected_agent_skills=(),
                candidate_summaries=candidates,
                confidence=output.confidence,
                reason_summary=output.reason_summary,
                candidate_total=candidate_total,
                candidate_truncated=candidate_truncated,
                model=model_name,
                contract_repair_attempted=repair_attempted,
                contract_repair_succeeded=repair_succeeded,
            )
            self._log_resolution(resolution)
            return resolution

        if len(output.selected_agent_skills) > self.max_selected:
            raise ValueError(
                f"selected_agent_skills exceeds max_selected={self.max_selected}"
            )
        if output.confidence < self.min_confidence:
            raise ValueError(
                f"selection confidence {output.confidence} is below "
                f"minimum {self.min_confidence}"
            )

        selected: list[SelectedAgentSkill] = []
        for item in output.selected_agent_skills:
            try:
                summary = candidate_by_id[item.agent_skill_id]
            except KeyError as exc:
                raise ValueError(
                    f"model selected unknown or undisclosed Agent Skill "
                    f"{item.agent_skill_id!r}"
                ) from exc
            if item.version != summary.version:
                raise ValueError(
                    f"Agent Skill {item.agent_skill_id!r} version mismatch: "
                    f"model={item.version!r} registry={summary.version!r}"
                )
            if item.projection != request.agent_role:
                raise ValueError(
                    f"selection projection {item.projection!r} does not match "
                    f"responsible Agent role {request.agent_role!r}"
                )
            if item.projection not in summary.available_projections:
                raise ValueError(
                    f"Agent Skill {item.agent_skill_id!r} does not expose "
                    f"projection {item.projection!r}"
                )
            relevant_goal_ids = item.relevant_goal_ids
            if request.goals and not relevant_goal_ids:
                if len(request.goals) == 1:
                    # The model already authored the Skill choice. Binding that
                    # choice to the sole authoritative Goal is identity
                    # normalization, not a semantic selection or Host routing
                    # decision. Multi-Goal turns still require explicit model
                    # ownership.
                    relevant_goal_ids = (request.goals[0].goal_id,)
                else:
                    raise ValueError(
                        "multi-Goal Agent Skill selections require explicit "
                        "relevant_goal_ids"
                    )
            unknown_goal_ids = set(relevant_goal_ids) - allowed_goal_ids
            if unknown_goal_ids:
                raise ValueError(
                    "selection references unknown Goal IDs: "
                    + ", ".join(sorted(unknown_goal_ids))
                )
            if item.confidence < self.min_confidence:
                raise ValueError(
                    f"Agent Skill {item.agent_skill_id!r} confidence "
                    f"{item.confidence} is below minimum {self.min_confidence}"
                )
            selected.append(
                SelectedAgentSkill(
                    agent_skill_id=item.agent_skill_id,
                    version=item.version,
                    projection=item.projection,
                    content_digest=summary.content_digest,
                    relevant_goal_ids=relevant_goal_ids,
                    rationale=item.rationale,
                    confidence=item.confidence,
                )
            )

        resolution = AgentSkillSelectionResolution(
            selection_id=selection_id,
            sid=request.sid,
            turn_id=request.turn_id,
            agent_role=request.agent_role,
            decision="select_skills",
            status="selected",
            selected_agent_skills=tuple(selected),
            candidate_summaries=candidates,
            confidence=output.confidence,
            reason_summary=output.reason_summary,
            candidate_total=candidate_total,
            candidate_truncated=candidate_truncated,
            model=model_name,
            contract_repair_attempted=repair_attempted,
            contract_repair_succeeded=repair_succeeded,
        )
        self._log_resolution(resolution)
        return resolution

    @staticmethod
    def _system_prompt(agent_role: AgentSkillProjectionName) -> str:
        role = _ROLE_LABELS[agent_role]
        return (
            f"You are the {role}. Decide whether zero, one, or several of the "
            "approved passive Agent Skills are useful for your own current "
            "responsibility. Agent Skills teach methods only: they do not execute, "
            "authorize Capabilities, resolve safety, or replace the current Goal and "
            "Plan contracts. Select only from the supplied summaries. Do not infer "
            "availability of unlisted Skills. A no_skill decision is valid and often "
            "correct. The extends field is dependency metadata, not automatic "
            "selection or inherited content: selecting a specialization never loads "
            "its parent projection. Evaluate each candidate independently; when both "
            "a reusable base method and its domain specialization are useful, select "
            "both explicitly and order the base method before the specialization. "
            "For the Goal Association role, if no current Goals are supplied, return no_skill; establish the user Goal before selecting a domain method. "
            "Judge applicability from the current "
            "Goal meanings, not from an older Goal, generic context, or a shared "
            "field such as a number, duration, date, or location. External-information "
            "methods apply only when the current Goal asks to obtain or interpret "
            "facts from an outside information source. They do not validate physical "
            "execution, action duration, gestures, singing, conversation, or plan "
            "correctness. A physical-action parameter is not external information "
            "merely because it contains a time or quantity. Never select a Skill in "
            "order to explain that it is "
            "irrelevant or not applicable; use no_skill when no supplied method is "
            "actually useful. Whenever supplied Goals exist, "
            "every selected item must include relevant_goal_ids copied exactly from "
            "those Goal IDs; planner roles must never omit them. Return only the "
            "required JSON object."
        )

    def _selection_prompt(
        self,
        request: AgentSkillSelectionRequest,
        candidates: tuple[AgentSkillSummary, ...],
    ) -> str:
        payload = {
            "agent_role": request.agent_role,
            "user_text": request.text,
            "language": request.language,
            "goals": [item.model_dump(mode="json") for item in request.goals],
            "context_summary": list(request.context_summary),
            "candidate_agent_skills": [
                item.model_dump(mode="json") for item in candidates
            ],
            "selection_contract": {
                "decision": "select_skills or no_skill",
                "selected_items": (
                    "Use exact candidate agent_skill_id and version, projection equal "
                    "to agent_role, relevant Goal IDs from the supplied goals, a "
                    "concise rationale, and confidence."
                ),
                "execution_authority": "none",
                "host_behavior": (
                    "The Host validates identity/provenance only and will not execute "
                    "or load a projection in this selection step."
                ),
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _repair_prompt(
        self,
        request: AgentSkillSelectionRequest,
        candidates: tuple[AgentSkillSummary, ...],
        *,
        initial_raw: Any,
        validation_error: str,
    ) -> str:
        payload = {
            "instruction": (
                "Repair the previous Agent Skill selection so it exactly satisfies "
                "the same closed schema and supplied candidate/Goal identities. Do "
                "not introduce a new Skill, version, projection, Goal, Capability, or "
                "execution proposal. Return only the repaired JSON object."
            ),
            "agent_role": request.agent_role,
            "allowed_candidates": [
                {
                    "agent_skill_id": item.agent_skill_id,
                    "version": item.version,
                    "available_projections": list(item.available_projections),
                    "extends": list(item.extends),
                }
                for item in candidates
            ],
            "allowed_goal_ids": [item.goal_id for item in request.goals],
            "previous_output": initial_raw,
            "validation_error": validation_error,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    def _response_schema(
        self,
        request: AgentSkillSelectionRequest,
        candidates: tuple[AgentSkillSummary, ...],
    ) -> dict[str, Any]:
        schema = copy.deepcopy(AgentSkillSelectionModelOutput.model_json_schema())
        candidate_ids = [item.agent_skill_id for item in candidates]
        versions = sorted({item.version for item in candidates})
        goal_ids = [item.goal_id for item in request.goals]

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    agent_skill_id = properties.get("agent_skill_id")
                    if isinstance(agent_skill_id, dict):
                        agent_skill_id["enum"] = candidate_ids
                    version = properties.get("version")
                    if isinstance(version, dict):
                        version["enum"] = versions
                    projection = properties.get("projection")
                    if isinstance(projection, dict):
                        projection["enum"] = [request.agent_role]
                    relevant_goal_ids = properties.get("relevant_goal_ids")
                    if isinstance(relevant_goal_ids, dict):
                        relevant_goal_ids["items"] = {
                            "type": "string",
                            "enum": goal_ids,
                        }
                        relevant_goal_ids["uniqueItems"] = True
                        if goal_ids:
                            relevant_goal_ids["minItems"] = 1
                            required_fields = node.setdefault("required", [])
                            if "relevant_goal_ids" not in required_fields:
                                required_fields.append("relevant_goal_ids")
                    selected = properties.get("selected_agent_skills")
                    if isinstance(selected, dict):
                        selected["maxItems"] = self.max_selected
                if node.get("type") == "object":
                    node["additionalProperties"] = False
                for value in node.values():
                    constrain(value)
            elif isinstance(node, list):
                for value in node:
                    constrain(value)

        constrain(schema)
        return schema

    @staticmethod
    def _validation_error_json(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            value: Any = exc.errors(include_url=False)
        else:
            value = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )[:6000]

    @staticmethod
    def _failure_resolution(
        *,
        request: AgentSkillSelectionRequest,
        selection_id: str,
        candidates: tuple[AgentSkillSummary, ...],
        candidate_total: int,
        candidate_truncated: bool,
        model_name: str | None,
        status: str,
        reason_summary: str,
        exc: Exception,
        repair_attempted: bool,
    ) -> AgentSkillSelectionResolution:
        return AgentSkillSelectionResolution(
            selection_id=selection_id,
            sid=request.sid,
            turn_id=request.turn_id,
            agent_role=request.agent_role,
            decision="no_skill",
            status=status,
            selected_agent_skills=(),
            candidate_summaries=candidates,
            confidence=0.0,
            reason_summary=reason_summary,
            candidate_total=candidate_total,
            candidate_truncated=candidate_truncated,
            model=model_name,
            contract_repair_attempted=repair_attempted,
            contract_repair_succeeded=False,
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )

    @staticmethod
    def _log_resolution(resolution: AgentSkillSelectionResolution) -> None:
        logger.info(
            "agent_skill_selection_done sid=%s turn_id=%s role=%s decision=%s "
            "status=%s selected_ids=%s confidence=%.3f repair_attempted=%s "
            "repair_succeeded=%s",
            resolution.sid,
            resolution.turn_id,
            resolution.agent_role,
            resolution.decision,
            resolution.status,
            [item.agent_skill_id for item in resolution.selected_agent_skills],
            resolution.confidence,
            resolution.contract_repair_attempted,
            resolution.contract_repair_succeeded,
        )
