from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Protocol

from agent.app.capabilities.validator import validate_args_for_schema
from pydantic import BaseModel, ConfigDict, Field

from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
    output_schema_sha256,
    validate_output_schema_declaration,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    ResponseCompositionResolution,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.user_turn import UserTurnEnvelope
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

CognitiveRuntimeMode = Literal["off", "report_only", "apply"]
CognitiveRuntimeStatus = Literal[
    "applied",
    "report_only",
    "skipped",
    "error",
]
CognitiveLane = Literal["chat", "robot_action", "tool", "memory", "unsupported"]


class CognitiveStageFailure(RuntimeError):
    """A stage failure with explicit architecture attribution metadata."""

    def __init__(self, stage: str, metadata: dict[str, Any]) -> None:
        self.stage = stage
        self.failure_metadata = dict(metadata)
        failure_class = str(metadata.get("failure_class") or "stage_failure")
        reason = str(
            metadata.get("error")
            or metadata.get("reason")
            or metadata.get("reason_summary")
            or failure_class
        )
        super().__init__(f"{stage}:{failure_class}:{reason}")


class CognitiveRuntimeResolution(BaseModel):
    """One bounded goal-driven turn resolution before host execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    mode: CognitiveRuntimeMode
    status: CognitiveRuntimeStatus
    lane: CognitiveLane
    turn_envelope: UserTurnEnvelope | None = None
    goal_association: GoalAssociationResolution | None = None
    fast_plan: CanonicalPlan | None = None
    terminal_plan: CanonicalPlan | None = None
    response_composition: ResponseCompositionResolution | None = None
    interaction_response: InteractionResponse | None = None
    goal_state_results: list[dict[str, Any]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    fallback_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class CognitiveRuntimePolicy:
    mode: CognitiveRuntimeMode = "off"
    apply_lanes: frozenset[str] = frozenset({"chat", "robot_action"})
    fallback_policy: str = "fail_closed"
    max_total_ms: int = 25000
    host_replan_budget: int = 1
    goal_association_timeout_ms: int = 3500
    fast_planner_timeout_ms: int = 3000
    deep_planner_timeout_ms: int = 10000
    response_composer_timeout_ms: int = 5000

    def lane_enabled(self, lane: str) -> bool:
        return lane in self.apply_lanes


class CognitiveAgentClient(Protocol):
    async def resolve_goal_association(self, session: Any, **kwargs: Any) -> GoalAssociationResolution: ...

    async def resolve_fast_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_deep_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def compose_response_plan(self, session: Any, **kwargs: Any) -> ResponseCompositionResolution: ...


class CognitiveEvidenceRecorder:
    """Append-only operational evidence and in-process rollout counters."""

    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = True,
        include_text: bool = False,
    ) -> None:
        self.path = path
        self.enabled = enabled
        self.include_text = include_text
        self.counters: Counter[str] = Counter()
        self.total_latency_ms = 0.0

    @staticmethod
    def _text_digest(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]

    def record(self, resolution: CognitiveRuntimeResolution, *, sid: str, text: str) -> None:
        self.counters[f"status:{resolution.status}"] += 1
        self.counters[f"lane:{resolution.lane}"] += 1
        self.counters[f"mode:{resolution.mode}"] += 1
        failure_class = str(resolution.metadata.get("failure_class") or "").strip()
        attribution = str(
            resolution.metadata.get("architecture_attribution") or ""
        ).strip()
        if failure_class:
            self.counters[f"failure_class:{failure_class}"] += 1
        if attribution:
            self.counters[f"architecture_attribution:{attribution}"] += 1
        fast_path = str(resolution.metadata.get("fast_planner_path") or "").strip()
        if fast_path:
            self.counters[f"fast_planner_path:{fast_path}"] += 1
        if (
            fast_path == "terminal"
            and resolution.fast_plan is not None
            and len(resolution.fast_plan.goal_ids) > 1
        ):
            self.counters["fast_terminal_multi_goal"] += 1
        if fast_path == "semantic_escalation":
            self.counters["fast_semantic_escalation"] += 1
        if fast_path == "contract_failure":
            self.counters["fast_contract_failure"] += 1
        if resolution.fast_plan is not None and bool(
            resolution.fast_plan.metadata.get("contract_repair_attempted")
        ):
            self.counters["fast_contract_repair"] += 1
        if bool(resolution.metadata.get("deep_planner_invoked")):
            reason = str(
                resolution.metadata.get("deep_planner_invocation_reason") or "unknown"
            )
            self.counters[f"deep_planner_invoked:{reason}"] += 1
        elif fast_path == "terminal":
            self.counters["deep_planner_avoided"] += 1
        self.counters["turns"] += 1
        total_ms = float(resolution.timings_ms.get("total", 0.0))
        self.total_latency_ms += total_ms
        if not self.enabled:
            return
        payload = {
            "schema_version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "mode": resolution.mode,
            "status": resolution.status,
            "lane": resolution.lane,
            "user_turn_envelope": (
                resolution.turn_envelope.model_dump(mode="json")
                if resolution.turn_envelope is not None
                else None
            ),
            "text_chars": len(text or ""),
            "text_sha256_16": self._text_digest(text),
            "goal_association": (
                resolution.goal_association.model_dump(mode="json", exclude_none=True)
                if resolution.goal_association is not None
                else None
            ),
            "fast_plan": self._plan_summary(resolution.fast_plan),
            "terminal_plan": self._plan_summary(resolution.terminal_plan),
            "composition": self._composition_summary(resolution.response_composition),
            "interaction": self._interaction_summary(resolution.interaction_response),
            "goal_state_results": resolution.goal_state_results,
            "timings_ms": resolution.timings_ms,
            "fallback_reason": resolution.fallback_reason,
            "metadata": resolution.metadata,
        }
        if self.include_text:
            payload["text"] = text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def record_outcome(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str,
        final_response: InteractionResponse | None,
        delivery_status: str,
        suppression_reason: str = "",
        goal_state_results: list[dict[str, Any]] | None = None,
    ) -> None:
        """Append the trusted post-execution half of a cognitive turn."""

        self.counters["outcome_bundles"] += 1
        self.counters[f"outcome_status:{bundle.aggregate_status}"] += 1
        self.counters[f"outcome_delivery:{delivery_status}"] += 1
        if not self.enabled:
            return
        payload = {
            "schema_version": 1,
            "event": "cognitive_execution_outcome",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "outcome_fingerprint": execution_outcome_fingerprint(bundle),
            "outcome_bundle": bundle.model_dump(mode="json", exclude_none=True),
            "goal_state_results": list(goal_state_results or []),
            "final_response": self._interaction_summary(final_response),
            "delivery_status": delivery_status,
            "suppression_reason": suppression_reason,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            )

    @staticmethod
    def _plan_summary(plan: CanonicalPlan | None) -> dict[str, Any] | None:
        if plan is None:
            return None
        return {
            "plan_id": plan.plan_id,
            "planner_tier": plan.planner_tier,
            "disposition": plan.disposition,
            "coverage": plan.coverage,
            "confidence": plan.confidence,
            "goal_ids": plan.goal_ids,
            "step_ids": [item.step_id for item in plan.steps],
            "skill_ids": [item.skill_id for item in plan.steps],
            "goal_satisfaction": (
                plan.goal_satisfaction.model_dump(mode="json")
                if plan.goal_satisfaction is not None
                else None
            ),
        }

    @staticmethod
    def _composition_summary(
        resolution: ResponseCompositionResolution | None,
    ) -> dict[str, Any] | None:
        if resolution is None:
            return None
        composition = resolution.composition
        return {
            "status": resolution.status,
            "composition_id": composition.composition_id if composition else None,
            "canonical_plan_fingerprint": (
                composition.canonical_plan_fingerprint if composition else None
            ),
            "social_attention": (
                composition.social_attention_plan.decision
                if composition and composition.social_attention_plan
                else None
            ),
        }

    @staticmethod
    def _interaction_summary(response: InteractionResponse | None) -> dict[str, Any] | None:
        if response is None:
            return None
        return {
            "interaction_id": response.interaction_id,
            "status": response.status,
            "speech_count": len(response.speech),
            "skill_ids": [item.skill_id for item in response.skills],
            "requires_confirmation": response.requires_confirmation,
        }

    def snapshot(self) -> dict[str, Any]:
        turns = int(self.counters.get("turns", 0))
        return {
            "turns": turns,
            "mean_total_latency_ms": (
                round(self.total_latency_ms / turns, 1) if turns else 0.0
            ),
            "counters": dict(sorted(self.counters.items())),
            "path": str(self.path),
            "enabled": self.enabled,
            "include_text": self.include_text,
        }


class CanonicalPlanRuntimeAdapter:
    """Translate validated canonical planning into the existing trusted runtime."""

    TRACE_MODULE = TraceModule(
        name="orchestrator.canonical_plan_adapter",
        component_type="runtime_adapter",
        implementation="CanonicalPlanRuntimeAdapter",
        schema_version=1,
    )

    def __init__(self, interaction_runtime: Any) -> None:
        self.interaction_runtime = interaction_runtime

    @staticmethod
    def lane_for_plan(plan: CanonicalPlan) -> CognitiveLane:
        if not plan.steps:
            return "chat"
        if all(step.skill_id.startswith("soridormi.") for step in plan.steps):
            return "robot_action"
        if all(step.skill_id.startswith("chromie.memory.") for step in plan.steps):
            return "memory"
        if all(step.skill_id.startswith("chromie.") for step in plan.steps):
            return "tool"
        return "unsupported"

    async def validation_errors(self, plan: CanonicalPlan) -> list[dict[str, Any]]:
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="validate_plan",
            attributes={
                "plan_disposition": plan.disposition,
                "step_count": len(plan.steps),
                "planner_tier": plan.planner_tier,
            },
        ) as span:
            errors = await self._validation_errors(plan)
            span.set_attribute("error_count", len(errors))
            if errors:
                span.set_status("error")
            return errors

    async def _validation_errors(self, plan: CanonicalPlan) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if plan.disposition not in {"execute", "mixed"}:
            if plan.steps:
                errors.append({"type": "non_execute_plan_has_steps"})
            return errors
        skill_ids = [step.skill_id for step in plan.steps]
        try:
            await self.interaction_runtime.ensure_skill_definitions(skill_ids)
        except Exception as exc:
            return [
                {
                    "type": "runtime_catalog_error",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:400],
                }
            ]

        definitions: dict[str, Any] = {}
        for step in plan.steps:
            try:
                definition = self.interaction_runtime.skill_definition(step.skill_id)
            except Exception as exc:
                errors.append(
                    {
                        "type": "unknown_runtime_skill",
                        "step_id": step.step_id,
                        "skill_id": step.skill_id,
                        "message": str(exc)[:300],
                    }
                )
                continue
            definitions[step.step_id] = definition
            if not definition.available:
                errors.append(
                    {
                        "type": "runtime_skill_unavailable",
                        "step_id": step.step_id,
                        "skill_id": step.skill_id,
                        "reason": definition.unavailable_reason,
                    }
                )
                continue
            try:
                validate_output_schema_declaration(definition.output_schema)
                output_schema_sha256(definition.output_schema)
            except (TypeError, ValueError) as exc:
                errors.append(
                    {
                        "type": "runtime_invalid_output_schema",
                        "step_id": step.step_id,
                        "skill_id": step.skill_id,
                        "message": str(exc)[:160],
                    }
                )
            schema_errors = validate_args_for_schema(step.args, definition.input_schema)
            if schema_errors:
                errors.append(
                    {
                        "type": "runtime_invalid_args",
                        "step_id": step.step_id,
                        "skill_id": step.skill_id,
                        "errors": schema_errors[:8],
                    }
                )

        parallel_batch: list[Any] = []
        for step in plan.steps:
            if step.timing == "parallel":
                parallel_batch.append(step)
                continue
            errors.extend(
                self._parallel_errors(
                    parallel_batch,
                    definitions,
                    plan_step_count=len(plan.steps),
                )
            )
            parallel_batch = []
        errors.extend(
            self._parallel_errors(
                parallel_batch,
                definitions,
                plan_step_count=len(plan.steps),
            )
        )
        return errors

    @staticmethod
    def _parallel_errors(
        steps: list[Any],
        definitions: dict[str, Any],
        *,
        plan_step_count: int,
    ) -> list[dict[str, Any]]:
        if not steps:
            return []
        if len(steps) == 1 and plan_step_count > 1:
            step = steps[0]
            return [
                {
                    "type": "runtime_parallel_singleton_group",
                    "step_id": step.step_id,
                    "skill_id": step.skill_id,
                }
            ]
        errors: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            definition = definitions.get(step.step_id)
            if definition is None:
                continue
            if not definition.can_run_parallel:
                errors.append(
                    {
                        "type": "runtime_parallel_not_supported",
                        "step_id": step.step_id,
                        "skill_id": step.skill_id,
                    }
                )
            left_group = str(definition.exclusive_group or "")
            left_resources = {
                str(item)
                for item in definition.metadata.get("resource_claims", [])
                if str(item)
            }
            for other in steps[index + 1 :]:
                other_definition = definitions.get(other.step_id)
                if other_definition is None:
                    continue
                right_group = str(other_definition.exclusive_group or "")
                right_resources = {
                    str(item)
                    for item in other_definition.metadata.get("resource_claims", [])
                    if str(item)
                }
                if left_group and right_group and left_group == right_group:
                    errors.append(
                        {
                            "type": "runtime_parallel_exclusive_group_conflict",
                            "step_ids": [step.step_id, other.step_id],
                            "exclusive_group": left_group,
                        }
                    )
                overlap = sorted(left_resources.intersection(right_resources))
                if overlap:
                    errors.append(
                        {
                            "type": "runtime_parallel_resource_conflict",
                            "step_ids": [step.step_id, other.step_id],
                            "resources": overlap,
                        }
                    )
        return errors


    @staticmethod
    def _attention_target_error(attention: Any, context: dict[str, Any]) -> str | None:
        target = attention.target
        if target.source == "none":
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "attention_target_not_available"
        if str(evidence.get("source") or "") != target.source:
            return "attention_target_source_mismatch"
        evidence_target = evidence.get("target")
        if not isinstance(evidence_target, dict):
            return "attention_target_not_available"
        expected_ref = str(evidence_target.get("target_ref") or "").strip()
        if expected_ref and expected_ref != target.target_ref:
            return "attention_target_ref_mismatch"
        expected_direction = str(
            evidence_target.get("relative_direction") or ""
        ).strip()
        claimed_direction = str(target.relative_direction or "").strip()
        if expected_direction and claimed_direction and expected_direction != claimed_direction:
            return "attention_target_direction_mismatch"
        return None

    @staticmethod
    def _attention_target_args_error(
        args: dict[str, Any],
        schema: dict[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            properties = {}
        target_fields = {
            str(key)
            for key in properties
            if str(key).startswith("target_")
            or str(key)
            in {"head_yaw_rad", "head_pitch_rad", "yaw_rad", "pitch_rad"}
        }
        if not target_fields:
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "targeted_behavior_requires_evidence"
        evidence_target = evidence.get("target")
        if not isinstance(evidence_target, dict):
            return "targeted_behavior_requires_evidence"
        suggested = evidence_target.get("suggested_args")
        if not isinstance(suggested, dict):
            suggested = {}
        for key, expected in suggested.items():
            if key not in args:
                continue
            actual = args.get(key)
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                if abs(float(expected) - float(actual)) > 1e-6:
                    return f"{key}_mismatch"
            elif actual != expected:
                return f"{key}_mismatch"
        return None

    @staticmethod
    def _attention_conflicts_with_primary(
        social_definition: Any,
        timing: str,
        primary_definitions: dict[str, Any],
    ) -> bool:
        if not primary_definitions:
            return False
        if timing != "parallel" or not social_definition.can_run_parallel:
            return True
        social_group = str(social_definition.exclusive_group or "")
        social_resources = {
            str(item)
            for item in social_definition.metadata.get("resource_claims", [])
            if str(item)
        }
        for definition in primary_definitions.values():
            if not definition.can_run_parallel:
                return True
            primary_group = str(definition.exclusive_group or "")
            if social_group and primary_group and social_group == primary_group:
                return True
            primary_resources = {
                str(item)
                for item in definition.metadata.get("resource_claims", [])
                if str(item)
            }
            if social_resources.intersection(primary_resources):
                return True
        return False

    @staticmethod
    def _authoritative_nonexecuting_text(
        plan: CanonicalPlan,
        goal_ids: list[str],
        *,
        language: str,
    ) -> str:
        """Render only canonical non-execution outcomes as user-facing text.

        A Response Composer stage can cover both an executable goal and a
        conversational or clarification goal.  Its prose cannot be safely
        reused after those authorities are split because the prose may claim
        an execution state.  Canonical per-goal outcome text is the trusted
        source for respond/clarify content; disposition-only fallbacks keep
        other non-execution outcomes truthful without borrowing action prose.
        """

        zh = language.lower().startswith("zh")
        texts: list[str] = []
        for goal_id in plan.goal_ids:
            if goal_id not in goal_ids:
                continue
            outcome = plan.outcome_for_goal(goal_id)
            if outcome is None or outcome.disposition == "execute":
                continue
            text = str(outcome.response_text or "").strip()
            if text:
                texts.append(text)
            elif outcome.disposition == "clarify":
                texts.append(
                    "我还需要你补充这个请求的信息。"
                    if zh
                    else "I still need more information for this request."
                )
            elif outcome.disposition == "unavailable":
                texts.append(
                    "这个请求当前不可用。"
                    if zh
                    else "This request is currently unavailable."
                )
            elif outcome.disposition == "refused":
                texts.append(
                    "我不能执行这个请求。"
                    if zh
                    else "I cannot carry out this request."
                )
        return " ".join(texts).strip()

    @staticmethod
    def _spoken_number(value: Any, *, language: str, repetitions: bool = False) -> str:
        """Render bounded structured numeric arguments without model prose."""

        zh = language.lower().startswith("zh")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return str(value)
        numeric = float(value)
        if numeric.is_integer():
            integer = int(numeric)
            if zh and 0 <= integer <= 10:
                if repetitions and integer == 2:
                    return "两"
                return "零一二三四五六七八九十"[integer]
            if not zh and 0 <= integer <= 10:
                words = (
                    "zero",
                    "one",
                    "two",
                    "three",
                    "four",
                    "five",
                    "six",
                    "seven",
                    "eight",
                    "nine",
                    "ten",
                )
                return words[integer]
            return str(integer)
        return f"{numeric:g}"

    @classmethod
    def _authoritative_step_text(cls, step: Any, *, language: str) -> str:
        """Describe one validated high-level step from its skill id and args.

        The text is deliberately rendered by the host from the same structured
        values later sent to Skill Runtime.  It therefore cannot inherit an
        execution or confirmation claim hidden in planner/composer prose.
        Unknown skills retain a truthful generic description instead of
        exposing an internal identifier or guessing at their effect.
        """

        zh = language.lower().startswith("zh")
        skill_id = str(step.skill_id)
        args = dict(step.args)
        count = args.get("count", 1)
        duration = args.get("duration_s")

        if skill_id == "soridormi.blink_eyes":
            if zh:
                number = cls._spoken_number(
                    count, language=language, repetitions=True
                )
                return f"眨{number}下眼睛"
            if count == 1:
                return "blink once"
            if count == 2:
                return "blink twice"
            number = cls._spoken_number(count, language=language)
            return f"blink {number} times"

        if skill_id == "soridormi.nod_yes":
            if zh:
                number = cls._spoken_number(
                    count, language=language, repetitions=True
                )
                return f"点{number}下头"
            if count == 1:
                return "nod once"
            if count == 2:
                return "nod twice"
            number = cls._spoken_number(count, language=language)
            return f"nod {number} times"

        if skill_id == "soridormi.look_at_person":
            if duration is None:
                return "看着你" if zh else "look at you"
            number = cls._spoken_number(duration, language=language)
            unit = "second" if float(duration) == 1 else "seconds"
            return (
                f"看着你{number}秒"
                if zh
                else f"look at you for {number} {unit}"
            )

        if skill_id == "soridormi.walk_forward":
            if duration is None:
                return "往前走" if zh else "walk forward"
            number = cls._spoken_number(duration, language=language)
            unit = "second" if float(duration) == 1 else "seconds"
            return (
                f"往前走{number}秒"
                if zh
                else f"walk forward for {number} {unit}"
            )

        if skill_id == "soridormi.shake_no":
            if zh:
                number = cls._spoken_number(
                    count, language=language, repetitions=True
                )
                return f"摇{number}下头"
            if count == 1:
                return "shake my head once"
            if count == 2:
                return "shake my head twice"
            number = cls._spoken_number(count, language=language)
            return f"shake my head {number} times"

        if skill_id == "soridormi.bow":
            return "鞠躬" if zh else "bow"
        if skill_id == "soridormi.neutral_head":
            return "把头恢复到自然位置" if zh else "return my head to neutral"
        if skill_id == "soridormi.stand_idle":
            return "保持站立待机" if zh else "stand idle"
        if skill_id == "soridormi.stop":
            return "停止动作" if zh else "stop moving"

        return "执行请求的动作" if zh else "perform the requested action"

    @classmethod
    def _authoritative_operational_text(
        cls,
        plan: CanonicalPlan,
        *,
        language: str,
        confirmation_required: bool,
    ) -> str:
        """Render prospective action speech from validated runtime authority."""

        zh = language.lower().startswith("zh")
        actions = [
            cls._authoritative_step_text(step, language=language)
            for step in plan.steps
        ]
        if zh:
            if len(actions) == 1:
                action_text = actions[0]
            else:
                action_text = "先" + actions[0] + "，再" + "，再".join(actions[1:])
            if confirmation_required:
                return f"请确认是否要我{action_text}。"
            return f"我会{action_text}。"

        if len(actions) == 1:
            action_text = actions[0]
        else:
            action_text = ", then ".join(actions)
        if confirmation_required:
            return f"Please confirm whether you'd like me to {action_text}."
        return f"I'll {action_text}."

    async def build_response(
        self,
        *,
        plan: CanonicalPlan,
        composition: CoordinatedResponsePlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="build_response",
            attributes={
                "plan_disposition": plan.disposition,
                "step_count": len(plan.steps),
                "speech_stage_count": sum(
                    1
                    for item in (
                        composition.response_plan.immediate,
                        composition.response_plan.pre_action,
                        composition.response_plan.final,
                    )
                    if item is not None
                )
                + len(composition.response_plan.progress),
            },
        ) as span:
            response = await self._build_response(
                plan=plan,
                composition=composition,
                session_id=session_id,
                language=language,
                context=context,
            )
            span.set_attribute("response_status", response.status)
            span.set_attribute("speech_count", len(response.speech))
            span.set_attribute("skill_count", len(response.skills))
            if response.status == "error":
                span.set_status("error")
            return response

    async def _build_response(
        self,
        *,
        plan: CanonicalPlan,
        composition: CoordinatedResponsePlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        if composition.canonical_plan_id != plan.plan_id:
            raise ValueError("response composition references a different canonical plan")
        if composition.canonical_plan_fingerprint != canonical_plan_fingerprint(plan):
            raise ValueError("response composition canonical-plan fingerprint mismatch")
        errors = await self.validation_errors(plan)
        if errors:
            raise ValueError("runtime canonical-plan validation failed: " + json.dumps(errors, ensure_ascii=False))

        fingerprint = canonical_plan_fingerprint(plan)
        alternative = str(plan.metadata.get("plan_relation") or "") in {
            "alternative",
            "safe_adjustment",
        } or bool(plan.metadata.get("user_confirmation_required"))
        executable_goal_ids = set(plan.executable_goal_ids())
        confirmation_goal_ids = set(executable_goal_ids) if alternative else set()
        if not alternative:
            for step in plan.steps:
                definition = self.interaction_runtime.skill_definition(step.skill_id)
                if definition.requires_confirmation:
                    confirmation_goal_ids.update(step.source_goal_ids)

        response_plan = composition.response_plan
        stage_items = [
            ("immediate", response_plan.immediate),
            ("pre_action", response_plan.pre_action),
            *[("progress", item) for item in response_plan.progress],
            ("final", response_plan.final),
        ]
        effectful_pre_execution = (
            plan.disposition in {"execute", "mixed"} and bool(plan.steps)
        )
        omitted_pre_execution_speech_phases: list[str] = []
        projected_speech_stages: list[dict[str, Any]] = []
        if effectful_pre_execution:
            required_goal_ids = set(plan.goal_ids)
            immediate_item = (
                ("immediate", response_plan.immediate)
                if response_plan.immediate is not None
                else None
            )
            pre_action_item = (
                ("pre_action", response_plan.pre_action)
                if response_plan.pre_action is not None
                else None
            )
            available_pre_execution = [
                item
                for item in (immediate_item, pre_action_item)
                if item is not None
            ]
            covered_pre_execution = {
                goal_id
                for _, stage in available_pre_execution
                for goal_id in stage.covers_goal_ids
            }
            if not available_pre_execution or not required_goal_ids.issubset(
                covered_pre_execution
            ):
                raise ValueError(
                    "effectful pre-execution response requires immediate and/or "
                    "pre_action stages covering all canonical goals"
                )

            if (
                pre_action_item is not None
                and required_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                )
            ):
                stage_items = [pre_action_item]
            elif (
                immediate_item is not None
                and required_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                )
            ):
                stage_items = [immediate_item]
            else:
                stage_items = list(available_pre_execution)

            selected_keys = {(phase, id(stage)) for phase, stage in stage_items}
            omitted_pre_execution_speech_phases = [
                phase
                for phase, stage in (
                    ("immediate", response_plan.immediate),
                    ("pre_action", response_plan.pre_action),
                    *[("progress", item) for item in response_plan.progress],
                    ("final", response_plan.final),
                )
                if stage is not None and (phase, id(stage)) not in selected_keys
            ]

            nonexecuting_goal_ids = required_goal_ids - executable_goal_ids
            projected_nonexecuting_goal_ids: set[str] = set()
            immediate_nonexecuting: list[dict[str, Any]] = []
            pre_action_nonexecuting: list[dict[str, Any]] = []
            for phase, stage in stage_items:
                covered_nonexecuting = [
                    goal_id
                    for goal_id in plan.goal_ids
                    if goal_id in stage.covers_goal_ids
                    and goal_id in nonexecuting_goal_ids
                ]
                if not covered_nonexecuting:
                    continue
                text = self._authoritative_nonexecuting_text(
                    plan,
                    covered_nonexecuting,
                    language=language,
                )
                if not text:
                    raise ValueError(
                        "effectful response cannot safely render non-executable "
                        "goal outcomes from canonical state"
                    )
                projected_nonexecuting_goal_ids.update(covered_nonexecuting)
                projected = {
                    "phase": phase,
                    "text": text,
                    "speech_act": stage.speech_act,
                    "commitment_state": stage.commitment_state,
                    "must_not_claim_completion": True,
                    "covers_goal_ids": covered_nonexecuting,
                    "claims": [],
                    "source": "goal_driven_canonical_outcome",
                }
                (
                    immediate_nonexecuting
                    if phase == "immediate"
                    else pre_action_nonexecuting
                ).append(projected)

            missing_nonexecuting = (
                nonexecuting_goal_ids - projected_nonexecuting_goal_ids
            )
            if missing_nonexecuting:
                raise ValueError(
                    "effectful response projection lost non-executable goals: "
                    + ",".join(sorted(missing_nonexecuting))
                )

            ordered_executable_goal_ids = [
                goal_id
                for goal_id in plan.goal_ids
                if goal_id in executable_goal_ids
            ]
            projected_operational = {
                "phase": "pre_action",
                "text": self._authoritative_operational_text(
                    plan,
                    language=language,
                    confirmation_required=bool(confirmation_goal_ids),
                ),
                "speech_act": (
                    "request_confirmation"
                    if confirmation_goal_ids
                    else "acknowledge"
                ),
                "commitment_state": (
                    "waiting_for_user" if confirmation_goal_ids else "accepted"
                ),
                "must_not_claim_completion": True,
                "covers_goal_ids": ordered_executable_goal_ids,
                "claims": [],
                "source": "goal_driven_runtime_authority",
                "operational_text_source": "runtime_authoritative_state",
                "runtime_confirmation_required": bool(confirmation_goal_ids),
            }
            projected_speech_stages = [
                *immediate_nonexecuting,
                projected_operational,
                *pre_action_nonexecuting,
            ]
        else:
            projected_speech_stages = [
                {
                    "phase": phase,
                    "text": stage.text,
                    "speech_act": stage.speech_act,
                    "commitment_state": stage.commitment_state,
                    "must_not_claim_completion": stage.must_not_claim_completion,
                    "covers_goal_ids": stage.covers_goal_ids,
                    "claims": stage.claims,
                    "source": "goal_driven_response_composer",
                }
                for phase, stage in stage_items
                if stage is not None
            ]

        speech: list[InteractionSpeech] = []
        for projected in projected_speech_stages:
            phase = str(projected["phase"])
            speech_metadata = {
                "source": projected["source"],
                "phase": phase,
                "speech_act": projected["speech_act"],
                "commitment_state": projected["commitment_state"],
                "must_not_claim_completion": projected[
                    "must_not_claim_completion"
                ],
                "covers_goal_ids": projected["covers_goal_ids"],
                "source_goal_ids": projected["covers_goal_ids"],
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "claims": projected["claims"],
                "wait_for_playback_start": True,
                "playback_start_required_for_delivery": True,
            }
            if effectful_pre_execution:
                speech_metadata["playback_start_required_for_effects"] = True
            for key in (
                "operational_text_source",
                "runtime_confirmation_required",
            ):
                if key in projected:
                    speech_metadata[key] = projected[key]
            speech.append(
                InteractionSpeech(
                    text=str(projected["text"]),
                    timing="immediate" if phase == "immediate" else "sequential",
                    style="brief",
                    metadata=speech_metadata,
                )
            )

        skills: list[SkillRequest] = []
        for step in plan.steps:
            definition = self.interaction_runtime.skill_definition(step.skill_id)
            digest = hashlib.sha256(
                f"{fingerprint}|{step.step_id}".encode("utf-8")
            ).hexdigest()[:20]
            skills.append(
                SkillRequest(
                    request_id=f"cogreq_{digest}",
                    skill_id=step.skill_id,
                    skill_version=definition.version,
                    args=step.args,
                    timing=step.timing,
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=(
                        bool(definition.requires_confirmation) or alternative
                    ),
                    idempotency_key=f"{plan.plan_id}:{step.step_id}:{fingerprint[:16]}",
                    committed_output_schema_sha256=output_schema_sha256(
                        definition.output_schema
                    ),
                    metadata={
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                        "planner_tier": plan.planner_tier,
                        "step_id": step.step_id,
                        "source_goal_ids": step.source_goal_ids,
                        "reason_summary": step.reason_summary,
                        **step.metadata,
                    },
                )
            )

        omitted_attention: list[str] = []
        attention = composition.social_attention_plan
        runtime_context = context if isinstance(context, dict) else {}
        if attention is not None and attention.decision == "express":
            target_error = self._attention_target_error(attention, runtime_context)
            if target_error:
                omitted_attention.append(target_error)
            else:
                primary_definitions = {
                    step.skill_id: self.interaction_runtime.skill_definition(step.skill_id)
                    for step in plan.steps
                }
                seen_social: set[str] = set()
                for index, behavior in enumerate(attention.behaviors):
                    try:
                        await self.interaction_runtime.ensure_skill_definitions(
                            [behavior.skill_id]
                        )
                        definition = self.interaction_runtime.skill_definition(
                            behavior.skill_id
                        )
                        if behavior.skill_id in primary_definitions or behavior.skill_id in seen_social:
                            omitted_attention.append(
                                f"duplicate_or_primary_skill:{behavior.skill_id}"
                            )
                            continue
                        if not definition.available:
                            omitted_attention.append(
                                f"unavailable:{behavior.skill_id}"
                            )
                            continue
                        if definition.requires_confirmation:
                            omitted_attention.append(
                                f"confirmation_required:{behavior.skill_id}"
                            )
                            continue
                        schema_errors = validate_args_for_schema(
                            behavior.args, definition.input_schema
                        )
                        if schema_errors:
                            omitted_attention.append(
                                f"invalid_args:{behavior.skill_id}"
                            )
                            continue
                        target_args_error = self._attention_target_args_error(
                            behavior.args,
                            definition.input_schema,
                            runtime_context,
                        )
                        if target_args_error:
                            omitted_attention.append(
                                f"target_error:{behavior.skill_id}:{target_args_error}"
                            )
                            continue
                        if self._attention_conflicts_with_primary(
                            definition,
                            behavior.timing,
                            primary_definitions,
                        ):
                            omitted_attention.append(
                                f"resource_conflict:{behavior.skill_id}"
                            )
                            continue
                        digest = hashlib.sha256(
                            f"{fingerprint}|social|{index}|{behavior.skill_id}".encode(
                                "utf-8"
                            )
                        ).hexdigest()[:20]
                        skills.append(
                            SkillRequest(
                                request_id=f"social_{digest}",
                                skill_id=behavior.skill_id,
                                skill_version=definition.version,
                                args=behavior.args,
                                timing=behavior.timing,
                                timeout_ms=definition.timeout_ms,
                                cancellable=definition.interruptible,
                                requires_confirmation=False,
                                idempotency_key=(
                                    f"{plan.plan_id}:social:{index}:{fingerprint[:16]}"
                                ),
                                metadata={
                                    "source": "social_attention_plan",
                                    "auxiliary_social_attention": True,
                                    "behavior_domain": attention.behavior_domain,
                                    "interaction_role": attention.interaction_role,
                                    "social_attention_purpose": attention.purpose,
                                    "speech_expression": attention.speech_expression.model_dump(
                                        mode="json", exclude_none=True
                                    ),
                                    "social_function": behavior.social_function,
                                    "canonical_plan_id": plan.plan_id,
                                    "target": attention.target.model_dump(
                                        mode="json", exclude_none=True
                                    ),
                                    "reason": behavior.reason,
                                },
                            )
                        )
                        seen_social.add(behavior.skill_id)
                    except Exception as exc:
                        omitted_attention.append(
                            f"invalid:{behavior.skill_id}:{type(exc).__name__}"
                        )

        status_map = {
            "respond": "ok",
            "execute": "ok",
            "mixed": "ok",
            "clarify": "clarify",
            "unavailable": "refused",
            "refused": "refused",
        }
        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": fingerprint,
            "response_composition": composition.model_dump(
                mode="json", exclude_none=True
            ),
            "planning_result": (
                "composed_plan"
                if plan.disposition in {"execute", "mixed"}
                else plan.disposition
            ),
            "capability_decision": plan.disposition,
            "goal_ids": plan.goal_ids,
            "planner_tier": plan.planner_tier,
            "goal_satisfaction": (
                plan.goal_satisfaction.model_dump(mode="json")
                if plan.goal_satisfaction is not None
                else None
            ),
            "omitted_social_attention": omitted_attention,
            "omitted_pre_execution_speech_phases": (
                omitted_pre_execution_speech_phases
            ),
            "operational_speech_authority": (
                "runtime_authoritative_state"
                if effectful_pre_execution
                else "not_applicable"
            ),
        }
        if alternative:
            metadata["disable_body_auto_confirm"] = True
            metadata["material_plan_change_requires_confirmation"] = True
        return InteractionResponse(
            status=status_map.get(plan.disposition, "error"),
            speech=speech,
            skills=skills,
            requires_confirmation=any(item.requires_confirmation for item in skills),
            reason=(
                plan.escalation_reason
                if plan.disposition in {"unavailable", "refused"}
                else None
            ),
            metadata=metadata,
        )


class GoalDrivenRuntimeCoordinator:
    """Single-direction goal association → fast/deep plan → composition pipeline."""

    TRACE_MODULE = TraceModule(
        name="orchestrator.cognitive_runtime",
        component_type="interaction_coordinator",
        implementation="GoalDrivenRuntimeCoordinator",
        schema_version=1,
    )

    def __init__(
        self,
        *,
        agent_client: CognitiveAgentClient,
        adapter: CanonicalPlanRuntimeAdapter,
        policy: CognitiveRuntimePolicy,
        goal_state_apply: Callable[..., list[dict[str, Any]]] | None = None,
        context_refresh: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.agent_client = agent_client
        self.adapter = adapter
        self.policy = policy
        self.goal_state_apply = goal_state_apply
        self.context_refresh = context_refresh

    @staticmethod
    def _association_goal_ids(association: GoalAssociationResolution) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            text = " ".join(str(value or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)

        for item in association.associations:
            for goal_id in item.target_goal_ids:
                add(goal_id)
        for goal in association.new_goals:
            add(goal.goal_id)
        return ordered

    @staticmethod
    def _fast_plan_path(plan: CanonicalPlan | None) -> str:
        if plan is None:
            return ""
        value = str(plan.metadata.get("path_classification") or "").strip()
        if value in {"terminal", "semantic_escalation", "contract_failure"}:
            return value
        if plan.metadata.get("failure_class"):
            return "contract_failure"
        if plan.disposition == "escalate":
            return "semantic_escalation"
        return "terminal"

    @staticmethod
    def _fast_plan_context_for_deep(
        plan: CanonicalPlan,
        *,
        path_classification: str,
    ) -> dict[str, Any]:
        payload = plan.model_dump(mode="json", exclude_none=True)
        if path_classification != "contract_failure":
            return payload
        metadata = dict(payload.get("metadata") or {})
        payload["metadata"] = {
            key: metadata[key]
            for key in (
                "resolver",
                "status",
                "authority",
                "path_classification",
                "failure_class",
                "failure_domain",
                "architecture_attribution",
                "retryable",
                "error_type",
            )
            if key in metadata
        }
        return payload

    async def resolve(
        self,
        session: Any,
        *,
        text: str,
        sid: str,
        route_decision: Any,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        language: str,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> CognitiveRuntimeResolution:
        if turn_envelope is not None:
            if turn_envelope.admission not in {"admit", "reflex_and_admit"}:
                raise ValueError(
                    "Goal-driven Runtime accepts only admitted UserTurnEnvelope "
                    f"records, got {turn_envelope.admission}"
                )
            if str(sid or "").strip() != turn_envelope.session_id:
                raise ValueError(
                    "Goal-driven Runtime session does not match UserTurnEnvelope"
                )
            if " ".join((text or "").strip().split()) != (
                turn_envelope.normalized_input.text
            ):
                raise ValueError(
                    "Goal-driven Runtime text does not match UserTurnEnvelope"
                )
            text = turn_envelope.normalized_input.text
            sid = turn_envelope.session_id
            language = turn_envelope.normalized_input.language
            context = {
                **context,
                "user_turn_envelope": turn_envelope.model_dump(mode="json"),
                "turn_id": turn_envelope.turn_id,
                "user_turn_schema_version": turn_envelope.schema_version,
            }
            envelope_history = context.get("history")
            if isinstance(envelope_history, list):
                history = list(envelope_history)

        experience = context.get("experience_context")
        if not isinstance(experience, dict):
            experience = {}
        conversation_id = str(
            context.get("conversation_id")
            or experience.get("conversation_id")
            or ""
        )
        interaction_id = str(
            context.get("interaction_id")
            or experience.get("interaction_id")
            or sid
        )
        turn_index = context.get("turn_index") or experience.get("turn_index")
        route = str(getattr(route_decision, "route", "") or "")
        intent = str(getattr(route_decision, "intent", "") or "")
        trace_scope = runtime_tracer.start_trace(
            correlations={
                "session_id": sid,
                "conversation_id": conversation_id,
                "interaction_id": interaction_id,
                "turn_index": turn_index,
            },
            attributes={
                "runtime_mode": self.policy.mode,
                "route": route,
                "intent": intent,
                "language": language,
                "text_chars": len(text or ""),
            },
            sampling_reason="goal_driven_interaction",
        )
        if not trace_scope.enabled:
            resolution = await self._resolve(
                session,
                text=text,
                sid=sid,
                route_decision=route_decision,
                context=context,
                history=history,
                language=language,
            )
            if turn_envelope is not None:
                resolution = resolution.model_copy(
                    update={"turn_envelope": turn_envelope}
                )
            return resolution
        try:
            async with trace_scope:
                async with runtime_tracer.span(
                    module=self.TRACE_MODULE,
                    operation="resolve",
                    kind="interaction",
                    attributes={"policy_mode": self.policy.mode},
                ) as span:
                    resolution = await self._resolve(
                        session,
                        text=text,
                        sid=sid,
                        route_decision=route_decision,
                        context=context,
                        history=history,
                        language=language,
                    )
                    if turn_envelope is not None:
                        resolution = resolution.model_copy(
                            update={"turn_envelope": turn_envelope}
                        )
                    span.set_attribute("result_status", resolution.status)
                    span.set_attribute("lane", resolution.lane)
                    span.set_attribute(
                        "runtime_replan_count",
                        resolution.metadata.get("runtime_replan_count", 0),
                    )
                    if resolution.status == "error":
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise

        snapshot = trace_scope.finish(state="complete")
        if snapshot is None:
            return resolution
        metadata = dict(resolution.metadata)
        metadata["runtime_trace"] = snapshot.reference()
        metadata["runtime_trace_summary"] = snapshot.summary
        retention = trace_scope.policy.retention_decision(snapshot)
        metadata["runtime_trace_retention"] = retention.as_dict()
        if retention.emit:
            metadata["runtime_trace_event"] = runtime_tracer.persist_snapshot(
                snapshot,
                event_subtype="goal_driven_interaction",
                producer="chromie.orchestrator.cognitive_runtime",
                severity=(
                    "warning"
                    if resolution.status == "error"
                    else retention.severity
                ),
                retention_reason=retention.reason,
            )
        return resolution.model_copy(update={"metadata": metadata})

    async def _resolve(
        self,
        session: Any,
        *,
        text: str,
        sid: str,
        route_decision: Any,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        language: str,
    ) -> CognitiveRuntimeResolution:
        started = time.perf_counter()
        timings: dict[str, float] = {}
        association: GoalAssociationResolution | None = None
        fast_plan: CanonicalPlan | None = None
        terminal_plan: CanonicalPlan | None = None
        composition_resolution: ResponseCompositionResolution | None = None
        interaction: InteractionResponse | None = None
        goal_state_results: list[dict[str, Any]] = []
        stage_diagnostics: list[dict[str, Any]] = []
        fast_planner_path = ""
        deep_planner_invocation_reasons: list[str] = []
        lane: CognitiveLane = "unsupported"

        def path_metadata() -> dict[str, Any]:
            first_deep_reason = (
                deep_planner_invocation_reasons[0]
                if deep_planner_invocation_reasons
                else ""
            )
            return {
                "fast_planner_path": fast_planner_path,
                "deep_planner_invoked": bool(deep_planner_invocation_reasons),
                "deep_planner_invocation_reason": first_deep_reason,
                "deep_planner_invocation_reasons": list(
                    deep_planner_invocation_reasons
                ),
                "deep_planner_avoided": bool(
                    fast_planner_path == "terminal"
                    and not deep_planner_invocation_reasons
                ),
                "terminal_planner_tier": (
                    terminal_plan.planner_tier if terminal_plan is not None else ""
                ),
                "authoritative_goal_count": (
                    len(self._association_goal_ids(association))
                    if association is not None
                    else 0
                ),
                "fast_goal_outcome_count": (
                    len(fast_plan.goal_outcomes) if fast_plan is not None else 0
                ),
                "fast_executable_step_count": (
                    len(fast_plan.steps) if fast_plan is not None else 0
                ),
            }

        try:
            stage = time.perf_counter()
            association = await self.agent_client.resolve_goal_association(
                session,
                text=text,
                route_decision=route_decision,
                sid=sid,
                context=context,
                history=history,
                timeout_ms=self.policy.goal_association_timeout_ms,
            )
            timings["goal_association"] = (time.perf_counter() - stage) * 1000.0
            association_status = str(
                (association.metadata or {}).get("status") or "resolved"
            )
            planning_context = dict(context)
            planning_context["goal_association_resolution"] = association.model_dump(
                mode="json", exclude_none=True
            )

            if association_status not in {"resolved", "needs_clarification"}:
                raise CognitiveStageFailure(
                    "goal_association",
                    self._stage_failure_metadata(
                        "goal_association",
                        association.metadata,
                        default_failure_class=association_status or "stage_failure",
                    ),
                )

            association_goal_ids = self._association_goal_ids(association)
            if association_status == "needs_clarification" or association.clarification:
                terminal_plan = CanonicalPlan(
                    plan_id=f"plan_goal_association_{sid}",
                    planner_tier="deep",
                    disposition="clarify",
                    coverage="uncertain",
                    confidence=association.confidence,
                    goal_ids=association_goal_ids,
                    goal_summary=text,
                    response_text=(
                        association.clarification
                        or (
                            "请补充你想继续或开始的具体事情。"
                            if language.startswith("zh")
                            else "Please clarify which goal you want to continue or start."
                        )
                    ),
                    steps=[],
                    unresolved=["goal_association_clarification"],
                    metadata={
                        "resolver": "goal_association",
                        "status": "clarify",
                        "authority": "advisory",
                        "association_status": association_status,
                    },
                )
            else:
                if not association_goal_ids:
                    raise CognitiveStageFailure(
                        "goal_association",
                        {
                            "failure_class": "empty_canonical_goal_set",
                            "failure_domain": "model_contract",
                            "architecture_attribution": "not_evaluated",
                            "retryable": True,
                            "reason": "resolved Goal Association produced no canonical goals",
                            "status": association_status,
                        },
                    )

                stage = time.perf_counter()
                fast_plan = await self.agent_client.resolve_fast_plan(
                    session,
                    text=text,
                    route_decision=route_decision,
                    sid=sid,
                    context=planning_context,
                    history=history,
                    timeout_ms=self.policy.fast_planner_timeout_ms,
                )
                timings["fast_planner"] = (time.perf_counter() - stage) * 1000.0
                fast_failure = self._optional_stage_failure_metadata(
                    "fast_planner", fast_plan.metadata
                )
                if fast_failure is not None:
                    stage_diagnostics.append(fast_failure)
                terminal_plan = fast_plan
                fast_planner_path = self._fast_plan_path(fast_plan)
                if fast_plan.disposition == "escalate":
                    deep_reason = (
                        "fast_contract_failure"
                        if fast_planner_path == "contract_failure"
                        else "semantic_escalation"
                    )
                    deep_planner_invocation_reasons.append(deep_reason)
                    deep_context = dict(planning_context)
                    deep_context["fast_plan_resolution"] = (
                        self._fast_plan_context_for_deep(
                            fast_plan,
                            path_classification=fast_planner_path,
                        )
                    )
                    deep_context["deep_planner_invocation_reason"] = deep_reason
                    stage = time.perf_counter()
                    terminal_plan = await self.agent_client.resolve_deep_plan(
                        session,
                        text=text,
                        route_decision=route_decision,
                        sid=sid,
                        context=deep_context,
                        history=history,
                        timeout_ms=self.policy.deep_planner_timeout_ms,
                    )
                    timings["deep_planner"] = (time.perf_counter() - stage) * 1000.0
                    deep_failure = self._optional_stage_failure_metadata(
                        "deep_planner", terminal_plan.metadata
                    )
                    if deep_failure is not None:
                        raise CognitiveStageFailure("deep_planner", deep_failure)

            lane = self.adapter.lane_for_plan(terminal_plan)
            source_route = str(getattr(route_decision, "route", "") or "")
            if lane == "robot_action" and source_route != "robot_action":
                return self._finish(
                    mode=self.policy.mode,
                    status="error",
                    lane=lane,
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    composition=None,
                    timings=timings,
                    started=started,
                    fallback_reason=(
                        "terminal_plan_exceeds_source_route_effect_envelope"
                    ),
                    metadata={
                        "failure_stage": "authority_boundary",
                        "failure_class": "route_effect_escalation",
                        "failure_domain": "cognitive_runtime",
                        "architecture_attribution": "not_evaluated",
                        "retryable": False,
                        "source_route": source_route,
                        "terminal_lane": lane,
                        "stage_diagnostics": stage_diagnostics,
                        **path_metadata(),
                    },
                )
            runtime_errors = await self.adapter.validation_errors(terminal_plan)
            replan_count = 0
            while runtime_errors and replan_count < self.policy.host_replan_budget:
                replan_count += 1
                if fast_plan is None:
                    raise ValueError("runtime replan requires an existing fast plan")
                deep_context = dict(planning_context)
                deep_context["fast_plan_resolution"] = self._fast_plan_context_for_deep(
                    fast_plan,
                    path_classification=fast_planner_path,
                )
                deep_context["runtime_validator_feedback"] = runtime_errors
                deep_context["deep_planner_invocation_reason"] = "host_replan"
                deep_planner_invocation_reasons.append("host_replan")
                stage = time.perf_counter()
                terminal_plan = await self.agent_client.resolve_deep_plan(
                    session,
                    text=text,
                    route_decision=route_decision,
                    sid=sid,
                    context=deep_context,
                    history=history,
                    timeout_ms=self.policy.deep_planner_timeout_ms,
                )
                timings[f"runtime_replan_{replan_count}"] = (
                    time.perf_counter() - stage
                ) * 1000.0
                deep_failure = self._optional_stage_failure_metadata(
                    "deep_planner", terminal_plan.metadata
                )
                if deep_failure is not None:
                    raise CognitiveStageFailure("deep_planner", deep_failure)
                lane = self.adapter.lane_for_plan(terminal_plan)
                if lane == "robot_action" and source_route != "robot_action":
                    return self._finish(
                        mode=self.policy.mode,
                        status="error",
                        lane=lane,
                        association=association,
                        fast_plan=fast_plan,
                        terminal_plan=terminal_plan,
                        composition=None,
                        timings=timings,
                        started=started,
                        fallback_reason=(
                            "terminal_plan_exceeds_source_route_effect_envelope"
                        ),
                        metadata={
                            "failure_stage": "authority_boundary",
                            "failure_class": "route_effect_escalation",
                            "failure_domain": "cognitive_runtime",
                            "architecture_attribution": "not_evaluated",
                            "retryable": False,
                            "source_route": source_route,
                            "terminal_lane": lane,
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )
                runtime_errors = await self.adapter.validation_errors(terminal_plan)
            if runtime_errors:
                raise ValueError(
                    "runtime validation rejected canonical plan: "
                    + json.dumps(runtime_errors, ensure_ascii=False)
                )

            composition_context = dict(planning_context)
            composition_context["canonical_plan_resolution"] = terminal_plan.model_dump(
                mode="json", exclude_none=True
            )
            stage = time.perf_counter()
            composition_resolution = await self.agent_client.compose_response_plan(
                session,
                text=text,
                route_decision=route_decision,
                sid=sid,
                context=composition_context,
                history=history,
                timeout_ms=self.policy.response_composer_timeout_ms,
            )
            timings["response_composer"] = (time.perf_counter() - stage) * 1000.0
            if (
                composition_resolution.status != "resolved"
                or composition_resolution.composition is None
            ):
                raise CognitiveStageFailure(
                    "response_composer",
                    self._stage_failure_metadata(
                        "response_composer",
                        composition_resolution.metadata,
                        default_failure_class=composition_resolution.status,
                    ),
                )

            if self.policy.mode == "apply":
                if not self.policy.lane_enabled(lane):
                    return self._finish(
                        mode="apply",
                        status="error",
                        lane=lane,
                        association=association,
                        fast_plan=fast_plan,
                        terminal_plan=terminal_plan,
                        composition=composition_resolution,
                        timings=timings,
                        started=started,
                        fallback_reason="terminal_plan_lane_not_enabled_for_apply",
                        metadata={
                            "failure_stage": "authority_boundary",
                            "failure_class": "terminal_plan_lane_mismatch",
                            "failure_domain": "cognitive_runtime",
                            "architecture_attribution": "not_evaluated",
                            "retryable": False,
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )
                stage = time.perf_counter()
                interaction = await self.adapter.build_response(
                    plan=terminal_plan,
                    composition=composition_resolution.composition,
                    session_id=sid,
                    language=language,
                    context=composition_context,
                )
                timings["runtime_adapter"] = (time.perf_counter() - stage) * 1000.0
                if self.goal_state_apply is not None:
                    goal_state_results = self.goal_state_apply(
                        association,
                        sid=sid,
                        user_text=text,
                        route=route_decision.route,
                        intent=route_decision.intent,
                        source="goal_driven_cognitive_runtime",
                    )
                    rejected = [
                        item
                        for item in goal_state_results
                        if item.get("applied") is False
                        and item.get("reason") not in {
                            "operation_already_applied",
                        }
                    ]
                    if rejected:
                        raise ValueError(
                            "goal state application rejected: "
                            + json.dumps(rejected, ensure_ascii=False)
                        )
                    interaction.metadata["goal_association"] = association.model_dump(
                        mode="json", exclude_none=True
                    )
                    interaction.metadata["goal_state_results"] = goal_state_results
                return self._finish(
                    mode="apply",
                    status="applied",
                    lane=lane,
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    composition=composition_resolution,
                    interaction=interaction,
                    goal_state_results=goal_state_results,
                    timings=timings,
                    started=started,
                    metadata={
                        "runtime_replan_count": replan_count,
                        "stage_diagnostics": stage_diagnostics,
                        "architecture_attribution": (
                            "not_evaluated"
                            if stage_diagnostics
                            else "not_evaluated"
                        ),
                        **path_metadata(),
                    },
                )

            return self._finish(
                mode="report_only",
                status="report_only",
                lane=lane,
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                composition=composition_resolution,
                timings=timings,
                started=started,
                metadata={
                    "runtime_replan_count": replan_count,
                    "stage_diagnostics": stage_diagnostics,
                    "architecture_attribution": (
                        "not_evaluated"
                        if stage_diagnostics
                        else "not_evaluated"
                    ),
                    **path_metadata(),
                },
            )
        except CognitiveStageFailure as exc:
            failure_metadata = {
                **exc.failure_metadata,
                "failure_stage": exc.stage,
                "stage_diagnostics": stage_diagnostics,
                **path_metadata(),
            }
            return self._finish(
                mode=self.policy.mode,
                status="error",
                lane=lane,
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                composition=composition_resolution,
                interaction=interaction,
                goal_state_results=goal_state_results,
                timings=timings,
                started=started,
                fallback_reason=str(exc)[:500],
                metadata=failure_metadata,
            )
        except Exception as exc:
            return self._finish(
                mode=self.policy.mode,
                status="error",
                lane=lane,
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                composition=composition_resolution,
                interaction=interaction,
                goal_state_results=goal_state_results,
                timings=timings,
                started=started,
                fallback_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
                metadata={
                    "failure_stage": "runtime",
                    "failure_class": type(exc).__name__,
                    "failure_domain": "cognitive_runtime",
                    "architecture_attribution": "not_evaluated",
                    "retryable": False,
                    "stage_diagnostics": stage_diagnostics,
                    **path_metadata(),
                },
            )

    @staticmethod
    def _optional_stage_failure_metadata(
        stage: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        values = dict(metadata or {})
        if not values.get("failure_class"):
            return None
        return GoalDrivenRuntimeCoordinator._stage_failure_metadata(
            stage,
            values,
            default_failure_class=str(values.get("failure_class")),
        )

    @staticmethod
    def _stage_failure_metadata(
        stage: str,
        metadata: dict[str, Any] | None,
        *,
        default_failure_class: str,
    ) -> dict[str, Any]:
        values = dict(metadata or {})
        result = {
            "stage": stage,
            "failure_class": str(
                values.get("failure_class") or default_failure_class or "stage_failure"
            ),
            "failure_domain": str(
                values.get("failure_domain") or "model_or_runtime"
            ),
            "architecture_attribution": str(
                values.get("architecture_attribution") or "not_evaluated"
            ),
            "retryable": bool(values.get("retryable", False)),
            "error_type": str(values.get("error_type") or ""),
            "error": str(values.get("error") or values.get("reason_summary") or "")[:300],
        }
        for key in (
            "purpose",
            "model",
            "timeout_ms",
            "elapsed_ms",
            "num_ctx",
            "num_predict",
            "done_reason",
            "prompt_eval_count",
            "eval_count",
            "suggestion",
            "reason",
        ):
            if key in values and values[key] not in {None, ""}:
                result[key] = values[key]
        return result

    @staticmethod
    def _finish(
        *,
        mode: CognitiveRuntimeMode,
        status: CognitiveRuntimeStatus,
        lane: CognitiveLane,
        association: GoalAssociationResolution | None,
        fast_plan: CanonicalPlan | None,
        terminal_plan: CanonicalPlan | None,
        composition: ResponseCompositionResolution | None,
        timings: dict[str, float],
        started: float,
        interaction: InteractionResponse | None = None,
        goal_state_results: list[dict[str, Any]] | None = None,
        fallback_reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CognitiveRuntimeResolution:
        final_timings = dict(timings)
        final_timings["total"] = (time.perf_counter() - started) * 1000.0
        return CognitiveRuntimeResolution(
            mode=mode,
            status=status,
            lane=lane,
            goal_association=association,
            fast_plan=fast_plan,
            terminal_plan=terminal_plan,
            response_composition=composition,
            interaction_response=interaction,
            goal_state_results=list(goal_state_results or []),
            timings_ms={key: round(value, 1) for key, value in final_timings.items()},
            fallback_reason=fallback_reason,
            metadata=dict(metadata or {}),
        )
