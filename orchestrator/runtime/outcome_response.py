from __future__ import annotations

import math
import re
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


_ENGLISH_STATUS_SUFFIX = {
    "completed": "completed.",
    "partial": "was partially completed.",
    "failed": "failed.",
    "refused": "was refused.",
    "timed_out": "timed out.",
    "cancelled": "was cancelled.",
    "not_run": "did not run.",
}

_CHINESE_STATUS_SUFFIX = {
    "completed": "已完成。",
    "partial": "仅部分完成。",
    "failed": "执行失败。",
    "refused": "被拒绝执行。",
    "timed_out": "执行超时。",
    "cancelled": "已取消。",
    "not_run": "未执行。",
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

_EXPLICIT_OBSERVATION_FIELDS = (
    "user_summary",
    "summary",
    "answer",
    "text",
    "result_text",
    "result",
)

_INTERNAL_KEY_PARTS = frozenset(
    {
        "credential",
        "evidence",
        "goal",
        "interaction",
        "password",
        "plan",
        "provider",
        "request",
        "secret",
        "skill",
        "step",
        "token",
        "trace",
        "turn",
    }
)

_MAX_OBSERVATION_TEXT = 240
_MAX_OBSERVATION_FIELDS = 3


def compose_outcome_response(
    bundle: ExecutionOutcomeBundle,
    plan: CanonicalPlan,
    language: str,
) -> InteractionResponse:
    """Compose one deterministic, speech-only response from trusted outcomes.

    This is a conservative fallback boundary, not a semantic planner. It
    validates the bundle against the immutable canonical plan, emits exactly
    one speech item for each executable goal in canonical order, and never
    treats provider messages or missing observations as user-facing output.
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
        observation_text, observed_evidence_ids = _goal_observation_text(
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
        )
        if observation_text:
            text = _append_observation(
                text,
                observation_text,
                chinese=chinese,
            )

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
                    "source": "deterministic_outcome_response",
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
            "source": "deterministic_outcome_response",
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
                "post-execution evidence skill does not match canonical step"
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
) -> tuple[str, list[str]]:
    snippets: list[str] = []
    observed_evidence_ids: list[str] = []
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
        snippet = _render_observation_data(
            observation.data,
            internal_ids=internal_ids,
            chinese=chinese,
        )
        if not snippet or snippet in snippets:
            continue
        snippets.append(snippet)
        observed_evidence_ids.append(evidence_id)
        if len(snippets) >= _MAX_OBSERVATION_FIELDS:
            break
    return "; ".join(snippets), observed_evidence_ids


def _render_observation_data(
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

    rendered: list[str] = []
    for raw_key in sorted(data, key=lambda item: str(item).casefold()):
        key = _normalize_text(str(raw_key))
        key_parts = set(re.split(r"[^a-z0-9]+", key.casefold()))
        if not key or key_parts.intersection(_INTERNAL_KEY_PARTS):
            continue
        value = _safe_scalar_text(
            data[raw_key],
            internal_ids=internal_ids,
            chinese=chinese,
        )
        if not value:
            continue
        label = _normalize_text(re.sub(r"[_-]+", " ", key))
        if key.casefold() in {"output", "result", "value"}:
            rendered.append(value)
        else:
            rendered.append(f"{label}: {value}")
        if len(rendered) >= _MAX_OBSERVATION_FIELDS:
            break
    return "; ".join(rendered)


def _safe_scalar_text(
    value: Any,
    *,
    internal_ids: set[str],
    chinese: bool,
) -> str:
    if isinstance(value, bool):
        text = "是" if chinese and value else "否" if chinese else "yes" if value else "no"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            return ""
        text = str(value)
    elif isinstance(value, str):
        text = _normalize_text(value)
    else:
        return ""

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
    return {value for value in values if value}


def _status_text(
    *,
    status: str,
    index: int,
    count: int,
    chinese: bool,
) -> str:
    if chinese:
        subject = "请求的任务" if count == 1 else f"第{index}个请求的任务"
        return subject + _CHINESE_STATUS_SUFFIX[status]

    if count == 1:
        subject = "The requested task"
    elif index <= len(_ENGLISH_ORDINALS):
        subject = f"The {_ENGLISH_ORDINALS[index - 1]} requested task"
    else:
        subject = f"Requested task {index}"
    return f"{subject} {_ENGLISH_STATUS_SUFFIX[status]}"


def _append_observation(
    status_text: str,
    observation_text: str,
    *,
    chinese: bool,
) -> str:
    if chinese:
        suffix = observation_text
        if suffix[-1:] not in {"。", "！", "？"}:
            suffix += "。"
        return f"{status_text}观测结果：{suffix}"

    suffix = observation_text
    if suffix[-1:] not in {".", "!", "?"}:
        suffix += "."
    return f"{status_text} Observed output: {suffix}"


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
