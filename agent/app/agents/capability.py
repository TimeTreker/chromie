from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

try:
    from chromie_contracts.interaction import SkillRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import SkillRequest

from ..capabilities.validator import normalize_args_for_schema
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.capability")


class _PlannedSkill(BaseModel):
    skill_id: str
    args: dict[str, Any] = Field(default_factory=dict)


class _CapabilityPlan(BaseModel):
    decision: Literal["execute", "clarify", "unsupported"]
    speech: str = ""
    skills: list[_PlannedSkill] = Field(default_factory=list)


class CapabilityAgent(BaseAgent):
    """Select exact executable capabilities from the shared catalog."""

    name = "capability_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        catalog = self.services.capability_catalog
        add_skill = getattr(result, "add_skill", None)
        if catalog is None or not callable(add_skill):
            return result

        search = await catalog.search(
            request.text,
            language=self.language(request),
            limit=self.services.capability_match_limit,
            min_score=0.0,
            prefer_interaction_executable=True,
        )
        request.route_decision.candidate_capabilities = [
            match.model_dump(mode="json") for match in search.matches
        ]
        executable = [
            match for match in search.matches if match.interaction_executable
        ]
        direct_actions = list(request.route_decision.actions or [])
        if direct_actions:
            allowed = {match.capability_id: match for match in executable}
            selected_ids: list[str] = []
            for action in sorted(
                direct_actions,
                key=lambda item: int(item.get("sequence", 0)),
            ):
                capability_id = str(action.get("capability_id") or "").strip()
                match = allowed.get(capability_id)
                if match is None:
                    result.metadata["capability_handled"] = True
                    result.metadata["capability_decision"] = "blocked"
                    result.metadata["invalid_selected_capability_id"] = capability_id
                    self.trace(
                        result,
                        f"router action capability is unavailable or non-executable: {capability_id}",
                    )
                    return result
                args = action.get("args")
                if not isinstance(args, dict):
                    args = {}
                args, normalized = normalize_args_for_schema(args, match.input_schema)
                metadata = {
                    "source": "router_actions",
                    "catalog_version": search.catalog_version,
                    "catalog_score": match.score,
                    "sequence": int(action.get("sequence", len(selected_ids))),
                }
                if normalized:
                    metadata["schema_normalized_args"] = True
                add_skill(
                    SkillRequest(
                        skill_id=capability_id,
                        args=args,
                        timing="sequential",
                        requires_confirmation=match.requires_confirmation,
                        metadata=metadata,
                    )
                )
                selected_ids.append(capability_id)
            if selected_ids:
                speech = (
                    ""
                    if request.route_decision.speak_first
                    else self._direct_plan_speech(selected_ids, direct_actions)
                )
                if speech:
                    result.add_speak_immediate(speech, style="brief")
                result.metadata["capability_handled"] = True
                result.metadata["capability_decision"] = "execute"
                result.metadata["capability_catalog_version"] = search.catalog_version
                result.metadata["capability_selected"] = selected_ids
                self.trace(result, f"accepted {len(selected_ids)} router capability action(s)")
                return result

        selected_id = ""
        intent = (request.route_decision.intent or "").strip()
        if intent.startswith("capability:"):
            selected_id = intent[len("capability:") :].strip()
        if selected_id:
            selected = [
                match for match in executable if match.capability_id == selected_id
            ]
            if not selected:
                result.metadata["capability_handled"] = True
                result.metadata["capability_decision"] = "blocked"
                result.metadata["invalid_selected_capability_id"] = selected_id
                self.trace(
                    result,
                    f"router-selected capability is unavailable or non-executable: {selected_id}",
                )
                return result
            executable = selected
            self.trace(result, f"honoring router-selected capability: {selected_id}")
        if not executable:
            result.metadata["capability_search"] = search.model_dump(mode="json")
            self.trace(result, "no interaction-executable capability matched")
            return result

        if not self.services.use_llm or self.services.ollama is None:
            self.trace(result, "capability match found but LLM selection is unavailable")
            return result

        plan = await self._plan(request, executable)
        allowed = {match.capability_id: match for match in executable}
        if plan.decision != "execute":
            if plan.speech:
                result.add_speak_immediate(plan.speech, style="brief")
            result.metadata["capability_handled"] = True
            result.metadata["capability_decision"] = plan.decision
            self.trace(result, f"capability decision={plan.decision}")
            return result

        selected = 0
        selected_requests: list[SkillRequest] = []
        selected_matches: list[Any] = []
        for item in plan.skills:
            match = allowed.get(item.skill_id)
            if match is None:
                logger.warning("LLM selected capability outside candidate set: %s", item.skill_id)
                continue
            args, normalized = normalize_args_for_schema(item.args, match.input_schema)
            metadata = {
                "source": "capability_catalog",
                "catalog_version": search.catalog_version,
                "catalog_score": match.score,
            }
            if normalized:
                metadata["schema_normalized_args"] = True
            request_item = SkillRequest(
                skill_id=item.skill_id,
                args=args,
                timing="sequential",
                requires_confirmation=match.requires_confirmation,
                metadata=metadata,
            )
            add_skill(request_item)
            selected_requests.append(request_item)
            selected_matches.append(match)
            selected += 1

        if selected == 0:
            self.trace(result, "LLM produced no valid capability selection")
            return result

        speech = plan.speech
        if self._uses_body_capability(selected_matches):
            speech = self._skill_plan_speech(selected_requests)
        if speech:
            result.add_speak_immediate(speech, style="brief")
        result.metadata["capability_handled"] = True
        result.metadata["capability_catalog_version"] = search.catalog_version
        result.metadata["capability_selected"] = [
            item.skill_id for item in plan.skills if item.skill_id in allowed
        ]
        self.trace(result, f"selected {selected} catalog capability request(s)")
        return result

    def _direct_plan_speech(
        self,
        selected_ids: list[str],
        actions: list[dict[str, Any]],
    ) -> str:
        if len(selected_ids) > 1:
            return "I will do those actions in order."
        skill_id = selected_ids[0]
        args = actions[0].get("args") if actions else {}
        args = args if isinstance(args, dict) else {}
        return self._skill_plan_speech(
            [
                SkillRequest(
                    skill_id=skill_id,
                    args=args,
                )
            ]
        )

    def _skill_plan_speech(self, requests: list[SkillRequest]) -> str:
        if len(requests) > 1:
            return "I will do those actions in order."
        if not requests:
            return "Okay."
        request = requests[0]
        skill_id = request.skill_id
        args = request.args
        if skill_id == "soridormi.walk_velocity":
            direction = "backward" if float(args.get("vx_mps", 0.0)) < 0 else "forward"
            return self._movement_speech(f"Walking {direction}", args)
        if skill_id == "soridormi.walk_forward":
            return self._movement_speech("Walking forward", args)
        if skill_id == "soridormi.turn_in_place":
            direction = "left" if float(args.get("yaw_radps", 0.0)) < 0 else "right"
            return self._movement_speech(f"Turning {direction}", args)
        if skill_id == "soridormi.nod_yes":
            return "Nodding."
        if skill_id == "soridormi.shake_no":
            return "Shaking my head."
        if skill_id == "soridormi.blink_eyes":
            return "Blinking."
        return "Okay."

    def _movement_speech(self, prefix: str, args: dict[str, Any]) -> str:
        duration = args.get("duration_s")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
            return f"{prefix} for {self._format_seconds(float(duration))}."
        return f"{prefix}."

    @staticmethod
    def _format_seconds(value: float) -> str:
        rounded = round(value, 1)
        if rounded.is_integer():
            amount = int(rounded)
            unit = "second" if amount == 1 else "seconds"
            return f"{amount} {unit}"
        return f"{rounded:g} seconds"

    @staticmethod
    def _uses_body_capability(matches: list[Any]) -> bool:
        for match in matches:
            capability_id = str(getattr(match, "capability_id", "") or "")
            effects = list(getattr(match, "effects", []) or [])
            if capability_id.startswith("soridormi.") or "physical_motion" in effects:
                return True
        return False

    async def _plan(self, request: AgentRunRequest, candidates: list[Any]) -> _CapabilityPlan:
        assert self.services.ollama is not None
        zh = self.is_zh(request)
        candidate_payload = [
            {
                "skill_id": match.capability_id,
                "description": match.description,
                "input_schema": match.input_schema,
                "effects": match.effects,
                "requires_confirmation": match.requires_confirmation,
                "score": match.score,
            }
            for match in candidates
        ]
        system = (
            "You are Chromie's capability selection agent. Select only exact skill_id values from the provided candidates. "
            "Never invent a skill. Never output raw joint, motor, actuator, position-array, or torque controls. "
            "Return JSON only with keys decision, speech, and skills. decision is execute, clarify, or unsupported. "
            "For execute, every skills item must contain skill_id and args satisfying that candidate's input_schema. "
            "Schema obedience is more important than copying the user's words. "
            "Every enum argument must be copied exactly from that field's enum list in input_schema. "
            "Map natural wording to enum tokens: if enum contains quick and the user says quickly, output quick; "
            "if enum contains slow and the user says slowly, output slow. Never output words outside the enum. "
            "Use clarify when a required safe parameter is missing. Use unsupported when none of the candidates can satisfy the request. "
            "Keep speech short and suitable for voice."
        )
        prompt = (
            f"Language: {'zh-CN' if zh else 'en-US'}\n"
            f"User request: {request.text}\n"
            f"Candidate capabilities: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True)}\n"
            "Choose the smallest safe set of executable skills."
        )
        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            response_format="json",
            options={"temperature": 0, "top_p": 0.8, "num_predict": 320},
        )
        try:
            return _CapabilityPlan.model_validate(raw)
        except ValidationError as exc:
            logger.warning("invalid capability plan: %s", exc)
            return _CapabilityPlan(
                decision="clarify",
                speech=(
                    "请再说明一下你希望我做什么。"
                    if zh
                    else "Please clarify what action you want me to perform."
                ),
            )
