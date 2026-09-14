from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .text import normalize_whitespace
from .execution_lanes import LaneCoordinationGroup
from .interaction import reject_forbidden_low_level_fields
from .plan import CanonicalPlan, canonical_plan_fingerprint
from .semantic_task import ResponsePlan, ResponseStage
from .social_cognition import SocialCognitionRequest, SocialCognitionResolution


class PlannerResponseProjection(BaseModel):
    """Mechanical join of SC interaction, immutable Work and lane coordination."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    projection_id: str = Field(min_length=1)
    canonical_plan_id: str = Field(min_length=1)
    canonical_plan_fingerprint: str = Field(min_length=16)
    canonical_plan: CanonicalPlan
    response_plan: ResponsePlan
    lane_coordination: list[LaneCoordinationGroup] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    social_cognition_request: SocialCognitionRequest | None = None
    social_cognition: SocialCognitionResolution | None = None

    @field_validator(
        "projection_id",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
        "rationale",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @staticmethod
    def _stages(plan: ResponsePlan) -> list[tuple[str, ResponseStage]]:
        if plan.activities:
            return [(stage.delivery_phase, stage) for stage in plan.activities]
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
    def validate_coordination(self) -> "PlannerResponseProjection":
        plan = self.canonical_plan
        social = self.social_cognition
        if (social is None) != (self.social_cognition_request is None):
            raise ValueError("SC response projection requires its exact request and result")
        if social is not None:
            request = self.social_cognition_request
            if request is None:
                raise ValueError("SC source snapshot is unavailable")
            social.validate_request(request)
            if request.goal_ids != plan.goal_ids or request.communication_needs != plan.communication_needs:
                raise ValueError("SC response must preserve the canonical communication obligations")
            if plan.plan_id not in request.source_refs or request.context.get("canonical_plan_resolution") != plan.prompt_projection():
                raise ValueError("SC response must read the exact immutable Work decision")
        if plan.disposition == "escalate":
            raise ValueError("planner response projection requires a terminal canonical plan")
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
        fail_closed_speech_optional = (
            not stages
            and not plan.steps
            and plan.disposition in {"clarify", "unavailable", "refused"}
            and plan.metadata.get("execution_allowed") is False
        )
        speech_optional = execution_only_speech_optional or fail_closed_speech_optional or social is not None
        if not stages and not speech_optional:
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
        if social is not None:
            acts = {act.activity_id: act for act in social.activities if act.text.strip()}
            needs = {need.need_id: need for need in plan.communication_needs}
            responding_goals = {
                item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"
            }
            projected_ids: list[str] = []
            for stage in stages:
                ids = stage.metadata.get("communicative_activity_ids", [])
                if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or ids[0] not in acts:
                    raise ValueError("SC projection must retain one exact communicative act per stage")
                act = acts[ids[0]]
                projected_ids.extend(ids)
                if stage.text != act.text or stage.covers_goal_ids != act.source_goal_ids or stage.delivery_phase != act.delivery_phase:
                    raise ValueError("SC projection changed exact words, scope or delivery order")
                addressed = [needs[key] for key in act.addressed_need_ids]
                completion_goals = sorted({
                    goal_id for need in addressed
                    if need.kind == "answer" and social.need_outcomes[need.need_id] == "covered"
                    for goal_id in need.source_goal_ids if goal_id in responding_goals
                })
                confirmation = any(need.kind == "confirmation" for need in addressed)
                waiting = confirmation or any(need.kind == "input" for need in addressed)
                completion = bool(completion_goals) and not set(act.source_goal_ids).intersection(plan.executable_goal_ids())
                expected_metadata = {
                    "wording_owner": "social_cognition",
                    "truth_stages": [act.truth_stage],
                    "evidence_refs": list(act.evidence_refs),
                    "addressed_need_ids": list(act.addressed_need_ids),
                    "source_responsibility_refs": list(act.source_responsibility_refs),
                    "communication_completion_goal_ids": completion_goals,
                    "required_before_work": confirmation or any(need.delivery_phase == "pre_action" or need.before_step_ids for need in addressed),
                    "communication_before_step_ids": sorted({key for need in addressed for key in need.before_step_ids}),
                    "communication_after_step_ids": sorted({key for need in addressed for key in need.after_step_ids}),
                }
                if any(stage.metadata.get(key) != value for key, value in expected_metadata.items()):
                    raise ValueError("SC projection changed communication evidence or completion authority")
                if (
                    stage.speech_act != ("ask_confirmation" if confirmation else "ask_clarification" if waiting else act.function)
                    or stage.commitment_state != ("waiting_for_user" if waiting else "completed" if completion else "none")
                    or stage.must_not_claim_completion != (not (completion and not waiting))
                ):
                    raise ValueError("SC projection changed communication commitment or input obligation")
            if set(projected_ids) != set(acts) or len(projected_ids) != len(set(projected_ids)):
                raise ValueError("SC projection omitted or duplicated a verbal act")

        # A ResponsePlan transports Planner-owned communication; it does not
        # become completion evidence for an executable-only Goal. When exact
        # Communicative Activities exist, their source Goal IDs are the complete
        # response-coverage authority. Plan steps and per-Goal outcomes retain
        # ownership of the other Goals in a mixed Plan.
        communicative_goals = {
            goal_id
            for act in plan.communicative_acts
            for goal_id in act.source_goal_ids
        }
        required_response_goals = (
            communicative_goals if plan.communicative_acts else known_goals
        )
        if (
            required_response_goals
            and covered_goals != required_response_goals
            and not speech_optional
        ):
            missing = sorted(required_response_goals - covered_goals)
            overclaimed = sorted(covered_goals - required_response_goals)
            details = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if overclaimed:
                details.append("overclaimed=" + ",".join(overclaimed))
            raise ValueError(
                "planner response projection must exactly cover Planner-owned "
                "communicative goals: " + ";".join(details)
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
            if any(phase == "final" for phase, _ in phased_stages):
                raise ValueError(
                    "pre-execution planner response projection must not include a final stage"
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
            if covered_clarifications != clarify_goals and social is None:
                missing = sorted(clarify_goals - covered_clarifications)
                raise ValueError(
                    "mixed plans require waiting-for-user clarification for goals: "
                    + ",".join(missing)
                )
        elif plan.disposition == "clarify" and not fail_closed_speech_optional and social is None:
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
