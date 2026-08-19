from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .execution_lanes import LaneCoordinationGroup
from .interaction import reject_forbidden_low_level_fields
from .goal import GoalAssociationResolution
from .plan import CanonicalPlan
from .semantic_task import ResponsePlan, ResponseStage

ResponseCompositionStatus = Literal["resolved", "model_unavailable", "invalid_input"]
ResponseCompositionPhase = Literal["pre_execution"]
def goal_association_fingerprint(resolution: GoalAssociationResolution) -> str:
    payload = json.dumps(
        resolution.prompt_projection(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_plan_fingerprint(plan: CanonicalPlan) -> str:
    payload = json.dumps(
        plan.prompt_projection(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CoordinatedResponsePlan(BaseModel):
    """Immutable task plan plus truthful user-facing response expression."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    composition_id: str = Field(min_length=1)
    phase: ResponseCompositionPhase = "pre_execution"
    canonical_plan_id: str = Field(min_length=1)
    canonical_plan_fingerprint: str = Field(min_length=16)
    canonical_plan: CanonicalPlan
    response_plan: ResponsePlan
    lane_coordination: list[LaneCoordinationGroup] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "composition_id",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
        "rationale",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @staticmethod
    def _stages(plan: ResponsePlan) -> list[tuple[str, ResponseStage]]:
        return [
            (phase, stage)
            for phase, stage in (
                ("immediate", plan.immediate),
                ("pre_action", plan.pre_action),
                *[("progress", item) for item in plan.progress],
                ("final", plan.final),
            )
            if stage is not None
        ]

    @model_validator(mode="after")
    def validate_coordination(self) -> "CoordinatedResponsePlan":
        plan = self.canonical_plan
        if plan.disposition == "escalate":
            raise ValueError("response composition requires a terminal canonical plan")
        if self.canonical_plan_id != plan.plan_id:
            raise ValueError("canonical_plan_id must match the embedded immutable plan")
        expected_fingerprint = canonical_plan_fingerprint(plan)
        if self.canonical_plan_fingerprint != expected_fingerprint:
            raise ValueError("canonical plan fingerprint mismatch")

        phased_stages = self._stages(self.response_plan)
        stages = [stage for _, stage in phased_stages]
        execution_only_speech_optional = (
            not stages
            and plan.disposition == "execute"
            and bool(plan.steps)
            and set(plan.executable_goal_ids()) == set(plan.goal_ids)
        )
        if not stages and not execution_only_speech_optional:
            raise ValueError("terminal canonical plans require at least one spoken response stage")

        known_goals = set(plan.goal_ids)
        covered_goals: set[str] = set()
        for stage in stages:
            unknown = set(stage.covers_goal_ids) - known_goals
            if unknown:
                raise ValueError(
                    "response stage references unknown goal IDs: " + ",".join(sorted(unknown))
                )
            covered_goals.update(stage.covers_goal_ids)

        if (
            known_goals
            and covered_goals != known_goals
            and not execution_only_speech_optional
        ):
            missing = sorted(known_goals - covered_goals)
            raise ValueError(
                "response composition does not cover all plan goals: " + ",".join(missing)
            )

        coordination_by_id = {item.coordination_id: item for item in self.lane_coordination}
        if len(coordination_by_id) != len(self.lane_coordination):
            raise ValueError("lane coordination IDs must be unique")
        plan_steps = {step.step_id: step for step in plan.steps}
        coordinated_vocal_steps: set[str] = set()
        coordinated_activity_steps: set[str] = set()
        for group in self.lane_coordination:
            for step_id in group.vocal_step_ids:
                step = plan_steps.get(step_id)
                if step is None:
                    raise ValueError(
                        "lane coordination references unknown speaking step: " + step_id
                    )
                if step_id in coordinated_vocal_steps:
                    raise ValueError(
                        "speaking step belongs to more than one lane coordination group: " + step_id
                    )
                coordinated_vocal_steps.add(step_id)
                if step.timing != "parallel":
                    raise ValueError(
                        "cross-lane speaking steps must use timing=parallel: " + step_id
                    )
            for step_id in group.activity_step_ids:
                step = plan_steps.get(step_id)
                if step is None:
                    raise ValueError(
                        "lane coordination references unknown activity step: " + step_id
                    )
                if step_id in coordinated_activity_steps:
                    raise ValueError(
                        "activity step belongs to more than one lane coordination group: " + step_id
                    )
                coordinated_activity_steps.add(step_id)
                if step.timing != "parallel":
                    raise ValueError(
                        "cross-lane activity steps must use timing=parallel: " + step_id
                    )

        coordinated_speech_ids: set[str] = set()
        for stage in stages:
            coordination_id = str(stage.coordination_id or "").strip()
            if not coordination_id:
                continue
            coordination_group = coordination_by_id.get(coordination_id)
            if coordination_group is None:
                raise ValueError(
                    "response stage references unknown lane coordination: " + coordination_id
                )
            if "vocal" not in coordination_group.lanes:
                raise ValueError(
                    "response stage coordination requires the vocal lane: " + coordination_id
                )
            if (
                stage.speech_act.casefold() == "ask_confirmation"
                or stage.commitment_state == "waiting_for_user"
            ):
                raise ValueError("confirmation and waiting speech cannot overlap effect execution")
            coordinated_speech_ids.add(coordination_id)

        for group in self.lane_coordination:
            lane_set = set(group.lanes)
            if (
                "vocal" in lane_set
                and not group.vocal_step_ids
                and group.coordination_id not in coordinated_speech_ids
            ):
                raise ValueError(
                    "vocal lane coordination requires a provider step or one "
                    "coordinated response stage: " + group.coordination_id
                )
            if (
                group.vocal_step_ids
                and group.coordination_id in coordinated_speech_ids
            ):
                raise ValueError(
                    "one personal voice cannot run ordinary speech and provider Vocal work "
                    "in the same parallel coordination group: " + group.coordination_id
                )

        if plan.disposition == "execute":
            if self.response_plan.final is not None:
                raise ValueError(
                    "pre-execution response composition must not include a final stage"
                )
            allowed = {"none", "heard", "evaluating", "waiting_for_user"}
            for stage in stages:
                if stage.commitment_state not in allowed:
                    raise ValueError(
                        "pre-execution response stage overstates commitment: "
                        + stage.commitment_state
                    )
                if not stage.must_not_claim_completion:
                    raise ValueError("pre-execution response stages must forbid completion claims")
        elif plan.disposition == "mixed":
            execute_goals = set(plan.executable_goal_ids())
            clarify_goals = set(plan.waiting_goal_ids())
            if execute_goals and self.response_plan.final is not None:
                raise ValueError("mixed pre-execution composition must not include a final stage")
            allowed = {"none", "heard", "evaluating", "waiting_for_user"}
            for _, stage in phased_stages:
                if set(stage.covers_goal_ids).intersection(execute_goals):
                    if stage.commitment_state not in allowed:
                        raise ValueError(
                            "mixed pre-execution response overstates commitment: "
                            + stage.commitment_state
                        )
                    if not stage.must_not_claim_completion:
                        raise ValueError("mixed pre-execution stages must forbid completion claims")
            covered_clarifications: set[str] = set()
            for _, stage in phased_stages:
                if (
                    stage.speech_act.casefold() in {"clarify", "ask_clarification"}
                    and stage.commitment_state == "waiting_for_user"
                ):
                    covered_clarifications.update(
                        set(stage.covers_goal_ids).intersection(clarify_goals)
                    )
            if covered_clarifications != clarify_goals:
                missing = sorted(clarify_goals - covered_clarifications)
                raise ValueError(
                    "mixed plans require waiting-for-user clarification for goals: "
                    + ",".join(missing)
                )
        elif plan.disposition == "clarify":
            clarification_stages = [
                stage
                for stage in stages
                if stage.speech_act.casefold() in {"clarify", "ask_clarification"}
                and stage.commitment_state == "waiting_for_user"
            ]
            if not clarification_stages:
                raise ValueError(
                    "clarification plans require a waiting-for-user clarification speech stage"
                )
        elif plan.disposition in {"unavailable", "refused"}:
            if any(stage.commitment_state in {"completed", "executing"} for stage in stages):
                raise ValueError(
                    "unavailable or refused plans cannot claim execution or completion"
                )

        return self


class DirectResponseComposition(BaseModel):
    """Planless composition for model-authored non-effectful speech Goals."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    composition_id: str = Field(min_length=1)
    phase: Literal["direct"] = "direct"
    goal_association_fingerprint: str = Field(min_length=16)
    goal_association: GoalAssociationResolution
    response_plan: ResponsePlan
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "composition_id",
        "goal_association_fingerprint",
        "rationale",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_direct_composition(self) -> "DirectResponseComposition":
        association = self.goal_association
        if self.goal_association_fingerprint != goal_association_fingerprint(association):
            raise ValueError("goal association fingerprint mismatch")
        if association.associations:
            raise ValueError("planless direct composition accepts only newly authored speech Goals")
        goal_ids = [
            str(goal.goal_id or "").strip()
            for goal in association.new_goals
            if str(goal.goal_id or "").strip()
        ]
        if not goal_ids:
            raise ValueError("direct response composition requires canonical Goal IDs")
        if any(
            str((goal.metadata or {}).get("responsibility_kind") or "") != "vocal_output"
            or str((goal.metadata or {}).get("output_mode") or "") != "speech"
            or bool((goal.metadata or {}).get("provider_required"))
            for goal in association.new_goals
        ):
            raise ValueError(
                "planless direct composition is limited to ordinary speech Vocal Goals"
            )
        response = self.response_plan
        if (
            response.immediate is not None
            or response.pre_action is not None
            or response.progress
            or response.final is None
        ):
            raise ValueError("direct response composition requires exactly one final speech stage")
        final = response.final
        if set(final.covers_goal_ids) != set(goal_ids):
            raise ValueError("direct response must cover every spoken Goal exactly")
        if final.commitment_state != "completed":
            raise ValueError("direct response final stage must complete the spoken Goals")
        if final.must_not_claim_completion:
            raise ValueError(
                "direct response final stage must permit completion of authored speech"
            )
        return self


ResponseComposition = Annotated[
    CoordinatedResponsePlan | DirectResponseComposition,
    Field(discriminator="phase"),
]


class ResponseCompositionResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResponseCompositionStatus
    composition: ResponseComposition | None = None
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_status(self) -> "ResponseCompositionResolution":
        if self.status == "resolved" and self.composition is None:
            raise ValueError("resolved response composition requires composition")
        if self.status != "resolved" and self.composition is not None:
            raise ValueError("non-resolved response composition must not carry composition")
        return self
