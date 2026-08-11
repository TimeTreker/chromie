from __future__ import annotations

from typing import Any

from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)


_ENGLISH_STATUS_TEXT = {
    "completed": "Done.",
    "partial": "I only finished part of it.",
    "failed": "That did not work just now.",
    "refused": "I cannot do that.",
    "timed_out": "That took too long just now.",
    "cancelled": "I stopped.",
    "not_run": "I did not do that.",
}

_CHINESE_STATUS_TEXT = {
    "completed": "好啦。",
    "partial": "刚才只弄好了一部分。",
    "failed": "刚才没成功。",
    "refused": "这个我不能做。",
    "timed_out": "刚才等太久了。",
    "cancelled": "已经停下来啦。",
    "not_run": "刚才没有做。",
}


_ENGLISH_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
)

_EXPLICIT_OBSERVATION_FIELDS = ("user_summary",)

_INTERPRETATION_UNAVAILABLE_TEXT = {
    "zh": "结果已经拿到了，不过我刚才没整理好怎么说。",
    "en": "I got the result, but I could not phrase the details properly just now.",
}

_MAX_OBSERVATION_TEXT = 240



def compose_outcome_response(
    bundle: ExecutionOutcomeBundle,
    plan: CanonicalPlan,
    language: str,
) -> InteractionResponse:
    """Compose an exceptional natural-language fallback from trusted outcomes.

    Normal post-execution speech belongs to the evidence-bound LLM interpreter.
    This boundary exists only when that interpreter is unavailable. It validates
    immutable correlations and may expose one trusted provider-authored summary,
    but never narrates internal task status, evidence, or observation labels.
    """

    bundle, plan = _validated_inputs(bundle, plan)
    executable_goal_ids = _validate_correlations(bundle=bundle, plan=plan)
    bundle_fingerprint = execution_outcome_fingerprint(bundle)
    evidence_by_id = {item.evidence_id: item for item in bundle.evidence}
    outcomes_by_goal = {item.goal_id: item for item in bundle.goal_outcomes}
    internal_ids = _internal_identifiers(
        bundle=bundle,
        plan=plan,
        bundle_fingerprint=bundle_fingerprint,
    )
    chinese = _is_chinese(language)

    speech: list[InteractionSpeech] = []
    per_goal_evidence_refs: list[dict[str, Any]] = []
    goal_count = len(executable_goal_ids)
    for index, goal_id in enumerate(executable_goal_ids, start=1):
        outcome = outcomes_by_goal[goal_id]
        (
            observation_text,
            observed_evidence_ids,
            had_available_observation,
        ) = _goal_observation_text(
            outcome=outcome,
            evidence_by_id=evidence_by_id,
            internal_ids=internal_ids,
            chinese=chinese,
        )
        text = _status_text(
            status=outcome.status,
            index=index,
            count=goal_count,
            chinese=chinese,
            part_of_larger_request=bool(bundle.non_execution_goal_ids),
        )
        if observation_text:
            text = _append_observation(
                text,
                observation_text,
                status=outcome.status,
                chinese=chinese,
            )
        elif outcome.status == "completed" and had_available_observation:
            text = _INTERPRETATION_UNAVAILABLE_TEXT["zh" if chinese else "en"]

        speech_id = f"speech_outcome_{bundle_fingerprint[:12]}_{index}"
        speech.append(
            InteractionSpeech(
                id=speech_id,
                text=text,
                timing="immediate",
                style="brief" if outcome.status == "completed" else "warning",
                priority="normal",
                interruptible=True,
                metadata={
                    "source": "deterministic_outcome_fallback",
                    "phase": "post_execution",
                    "wait_for_playback_start": True,
                    "playback_start_required_for_delivery": True,
                    "covers_goal_ids": [goal_id],
                    "goal_status": outcome.status,
                    "evidence_ids": list(outcome.evidence_ids),
                    "observed_evidence_ids": observed_evidence_ids,
                    "execution_outcome_fingerprint": bundle_fingerprint,
                },
            )
        )
        per_goal_evidence_refs.append(
            {
                "goal_id": goal_id,
                "status": outcome.status,
                "step_ids": list(outcome.step_ids),
                "evidence_ids": list(outcome.evidence_ids),
                "observed_evidence_ids": observed_evidence_ids,
                "speech_id": speech_id,
            }
        )

    response_status = (
        "ok"
        if bundle.aggregate_status == "completed"
        else "refused"
        if bundle.aggregate_status == "refused"
        else "error"
    )
    return InteractionResponse(
        interaction_id=bundle.interaction_id,
        status=response_status,
        speech=speech,
        skills=[],
        requires_confirmation=False,
        reason=(
            None
            if bundle.aggregate_status == "completed"
            else f"post_execution_{bundle.aggregate_status}"
        ),
        metadata={
            "source": "deterministic_outcome_fallback",
            "phase": "post_execution",
            "language": language,
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": bundle.canonical_plan_fingerprint,
            "execution_outcome_fingerprint": bundle_fingerprint,
            "execution_outcome_bundle": bundle.model_dump(mode="json"),
            "aggregate_status": bundle.aggregate_status,
            "executable_goal_ids": executable_goal_ids,
            "per_goal_evidence_refs": per_goal_evidence_refs,
        },
    )


def _validated_inputs(
    bundle: ExecutionOutcomeBundle,
    plan: CanonicalPlan,
) -> tuple[ExecutionOutcomeBundle, CanonicalPlan]:
    if not isinstance(bundle, ExecutionOutcomeBundle):
        raise ValueError("post-execution response requires ExecutionOutcomeBundle")
    if not isinstance(plan, CanonicalPlan):
        raise ValueError("post-execution response requires CanonicalPlan")
    try:
        validated_bundle = ExecutionOutcomeBundle.model_validate(
            bundle.model_dump(mode="python")
        )
        validated_plan = CanonicalPlan.model_validate(
            plan.model_dump(mode="python")
        )
    except Exception as exc:
        raise ValueError(
            f"post-execution response contract validation failed: {type(exc).__name__}"
        ) from exc
    return validated_bundle, validated_plan


def _validate_correlations(
    *,
    bundle: ExecutionOutcomeBundle,
    plan: CanonicalPlan,
) -> list[str]:
    if bundle.canonical_plan_id != plan.plan_id:
        raise ValueError("post-execution canonical plan ID mismatch")

    expected_plan_fingerprint = canonical_plan_fingerprint(plan)
    if bundle.canonical_plan_fingerprint != expected_plan_fingerprint:
        raise ValueError("post-execution canonical plan fingerprint mismatch")

    if bundle.canonical_goal_ids != plan.goal_ids:
        raise ValueError(
            "post-execution canonical goal correlation or order mismatch"
        )

    executable_goal_set = set(plan.executable_goal_ids())
    executable_goal_ids = [
        goal_id for goal_id in plan.goal_ids if goal_id in executable_goal_set
    ]
    if not executable_goal_ids:
        raise ValueError(
            "post-execution response requires an executable canonical goal"
        )

    expected_non_execution = [
        goal_id for goal_id in plan.goal_ids if goal_id not in executable_goal_set
    ]
    if bundle.non_execution_goal_ids != expected_non_execution:
        raise ValueError("post-execution non-execution goal correlation mismatch")

    outcomes_by_goal = {item.goal_id: item for item in bundle.goal_outcomes}
    if set(outcomes_by_goal) != set(executable_goal_ids):
        raise ValueError("post-execution executable goal outcome mismatch")

    plan_steps_by_id = {item.step_id: item for item in plan.steps}
    evidence_by_id = {item.evidence_id: item for item in bundle.evidence}
    referenced_evidence_ids: set[str] = set()

    for evidence in bundle.evidence:
        step = plan_steps_by_id.get(evidence.step_id)
        if step is None:
            raise ValueError(
                "post-execution evidence references an unknown canonical step"
            )
        if evidence.skill_id != step.skill_id:
            raise ValueError(
                "post-execution evidence capability does not match canonical step"
            )
        if set(evidence.source_goal_ids) != set(step.source_goal_ids):
            raise ValueError(
                "post-execution evidence goal ownership mismatch"
            )

    for goal_id in executable_goal_ids:
        outcome = outcomes_by_goal[goal_id]
        expected_step_ids = [
            step.step_id
            for step in plan.steps
            if goal_id in step.source_goal_ids
        ]
        if set(outcome.step_ids) != set(expected_step_ids):
            raise ValueError(
                "post-execution goal-to-step correlation mismatch"
            )
        referenced_evidence_ids.update(outcome.evidence_ids)

    if referenced_evidence_ids != set(evidence_by_id):
        raise ValueError(
            "post-execution bundle contains uncorrelated execution evidence"
        )
    return executable_goal_ids


def _goal_observation_text(
    *,
    outcome: GoalExecutionOutcome,
    evidence_by_id: dict[str, ExecutionEvidence],
    internal_ids: set[str],
    chinese: bool,
) -> tuple[str, list[str], bool]:
    """Return only an explicitly provider-authored user summary.

    Structured observations remain complete in the outcome bundle and logs. The
    exceptional deterministic fallback must not convert arbitrary fields into a
    spoken report; relevance and phrasing belong to the LLM interpreter.
    """

    had_available_observation = False
    for evidence_id in outcome.evidence_ids:
        evidence = evidence_by_id[evidence_id]
        observation = evidence.observation
        if (
            observation is None
            or observation.status != "available"
            or not observation.schema_validated
            or not observation.data
        ):
            continue
        had_available_observation = True
        text = _explicit_user_summary(
            observation.data,
            internal_ids=internal_ids,
            chinese=chinese,
        )
        if text:
            return text, [evidence_id], True
    return "", [], had_available_observation


def _explicit_user_summary(
    data: dict[str, Any],
    *,
    internal_ids: set[str],
    chinese: bool,
) -> str:
    for field in _EXPLICIT_OBSERVATION_FIELDS:
        if field not in data:
            continue
        text = _safe_scalar_text(
            data[field],
            internal_ids=internal_ids,
            chinese=chinese,
        )
        if text:
            return text
    return ""


def _safe_scalar_text(
    value: Any,
    *,
    internal_ids: set[str],
    chinese: bool,
) -> str:
    del chinese
    if not isinstance(value, str):
        return ""
    text = _normalize_text(value)
    if not text:
        return ""
    folded = text.casefold()
    if any(identifier.casefold() in folded for identifier in internal_ids):
        return ""
    if len(text) > _MAX_OBSERVATION_TEXT:
        text = text[: _MAX_OBSERVATION_TEXT - 1].rstrip() + "…"
    return text


def _internal_identifiers(
    *,
    bundle: ExecutionOutcomeBundle,
    plan: CanonicalPlan,
    bundle_fingerprint: str,
) -> set[str]:
    values: set[str] = {
        bundle.outcome_id,
        bundle.turn_id,
        bundle.interaction_id,
        bundle.canonical_plan_id,
        bundle.canonical_plan_fingerprint,
        bundle_fingerprint,
        plan.plan_id,
        *plan.goal_ids,
    }
    for step in plan.steps:
        values.update({step.step_id, step.skill_id})
    for evidence in bundle.evidence:
        values.update(
            {
                evidence.evidence_id,
                evidence.request_id,
                evidence.step_id,
                evidence.skill_id,
            }
        )
        for optional in (
            evidence.provider_id,
            evidence.trace_id,
        ):
            if optional:
                values.add(optional)
        observation = evidence.observation
        if observation is not None and isinstance(observation.data, dict):
            for key, raw_value in observation.data.items():
                normalized_key = str(key or "").strip().casefold()
                if (
                    normalized_key == "id"
                    or normalized_key.endswith("_id")
                    or normalized_key in {"plan_id", "request_id", "trace_id"}
                ) and isinstance(raw_value, str):
                    identifier = _normalize_text(raw_value)
                    if identifier:
                        values.add(identifier)
    return {value for value in values if value}


def _status_text(
    *,
    status: str,
    index: int,
    count: int,
    chinese: bool,
    part_of_larger_request: bool,
) -> str:
    base = (
        _CHINESE_STATUS_TEXT[status]
        if chinese
        else _ENGLISH_STATUS_TEXT[status]
    )
    if count == 1:
        if status == "completed" and part_of_larger_request:
            return "这一小步弄好啦。" if chinese else "That part is done."
        return base

    if chinese:
        templates = {
            "completed": f"第{index}件弄好啦。",
            "partial": f"第{index}件只弄好了一部分。",
            "failed": f"第{index}件没弄成。",
            "refused": f"第{index}件我不能做。",
            "timed_out": f"第{index}件等太久了。",
            "cancelled": f"第{index}件停下来啦。",
            "not_run": f"第{index}件没有做。",
        }
        return templates[status]

    label = (
        _ENGLISH_ORDINALS[index - 1]
        if index <= len(_ENGLISH_ORDINALS)
        else f"number {index}"
    )
    templates = {
        "completed": f"The {label} one is done.",
        "partial": f"I only finished part of the {label} one.",
        "failed": f"The {label} one did not work.",
        "refused": f"I cannot do the {label} one.",
        "timed_out": f"The {label} one took too long.",
        "cancelled": f"I stopped the {label} one.",
        "not_run": f"I did not do the {label} one.",
    }
    return templates[status]


def _append_observation(
    status_text: str,
    observation_text: str,
    *,
    status: str,
    chinese: bool,
) -> str:
    suffix = observation_text
    endings = {"。", "！", "？"} if chinese else {".", "!", "?"}
    if suffix[-1:] not in endings:
        suffix += "。" if chinese else "."
    if status == "completed":
        return suffix
    return f"{status_text}{suffix}"


def _is_chinese(language: str) -> bool:
    normalized = _normalize_text(language).casefold().replace("_", "-")
    return normalized.startswith("zh") or normalized in {
        "chinese",
        "mandarin",
        "中文",
        "汉语",
        "普通话",
    }


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split())


__all__ = ["compose_outcome_response"]
