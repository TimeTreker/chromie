from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillRequest,
    SkillResult,
)

_TASK_GRAPH_SKILL_ID = "chromie.task_graph.execute"
_RECOVERABLE_FAILURE_CLASSES = frozenset(
    {
        "recoverable",
        "recoverable_failure",
        "user_preference_required",
        "needs_user_preference",
        "b_level",
        "b_level_recovery",
    }
)


@dataclass(frozen=True)
class BodyRecoveryConfirmation:
    """Single bounded retry proposal after a recoverable body failure.

    The confirmation is intentionally request-bound. Approval is not physical
    authorization by itself; it only lets the retry response re-enter the normal
    InteractionRuntime -> SkillRuntime -> Soridormi preflight/validation path.
    """

    response: InteractionResponse
    confirmed_request_ids: frozenset[str]
    prompt: str
    failed_request_ids: tuple[str, ...]
    retry_request_ids: tuple[str, ...]
    attempt: int
    max_attempts: int


def is_recoverable_body_result(result: SkillResult) -> bool:
    """Return True for B-level body failures that may ask user preference.

    A-level safety refusals, cancellations, and timeouts are terminal at this
    layer. They may be explained to the user, but they must not trigger a retry
    prompt because the physical world may no longer match the original plan.
    """

    if not result.skill_id.startswith("soridormi."):
        return False
    if result.status in {"refused", "timed_out", "cancelled"}:
        return False
    if result.status != "failed":
        return False
    output = result.output or {}
    recovery = _dict_value(output.get("recovery"))
    if output.get("recoverable") is True or recovery.get("recoverable") is True:
        return True
    if output.get("retryable") is True or recovery.get("retryable") is True:
        return True
    failure_class = str(
        output.get("failure_class")
        or output.get("failure_type")
        or recovery.get("failure_class")
        or recovery.get("failure_type")
        or ""
    ).strip().casefold()
    if failure_class in _RECOVERABLE_FAILURE_CLASSES:
        return True
    return False


def recoverable_body_results(results: list[SkillResult]) -> list[SkillResult]:
    return [result for result in results if is_recoverable_body_result(result)]


def build_body_recovery_confirmation(
    response: InteractionResponse,
    failed_results: list[SkillResult],
    *,
    max_attempts: int,
    timeout_s: float,
    language: str,
) -> BodyRecoveryConfirmation | None:
    """Create a bounded retry confirmation for recoverable body failures.

    The retry response contains only failed Soridormi requests plus any original
    after-skills speech. It does not replay earlier immediate filler speech.
    """

    if max_attempts <= 0:
        return None
    recoverable = recoverable_body_results(failed_results)
    if not recoverable:
        return None

    requests_by_id = {request.request_id: request for request in response.skills}
    retry_requests: list[SkillRequest] = []
    retry_request_ids: list[str] = []
    failed_request_ids: list[str] = []
    next_attempt = 0

    for result in recoverable:
        request = requests_by_id.get(result.request_id)
        if request is None:
            continue
        attempt = _recovery_attempt(request)
        if attempt >= max_attempts:
            continue
        next_attempt = max(next_attempt, attempt + 1)
        retry_request_id = _retry_request_id(request.request_id, attempt + 1)
        retry_metadata = {
            **request.metadata,
            "body_recovery_retry": True,
            "body_recovery_attempt": attempt + 1,
            "body_recovery_max_attempts": max_attempts,
            "body_recovery_parent_request_id": request.request_id,
            "body_recovery_parent_interaction_id": response.interaction_id,
            "body_recovery_failed_reason_code": result.reason_code,
            "source_component": "host.body_recovery",
            "execution_mode": "proposed",
            "execution_semantics": "proposal_from_body_recovery",
            "requires_runtime_validation": True,
        }
        retry_request = request.model_copy(
            deep=True,
            update={
                "request_id": retry_request_id,
                "requires_confirmation": True,
                "metadata": retry_metadata,
                "idempotency_key": _retry_idempotency_key(
                    request.idempotency_key,
                    request.request_id,
                    attempt + 1,
                ),
            },
        )
        retry_requests.append(retry_request)
        retry_request_ids.append(retry_request_id)
        failed_request_ids.append(result.request_id)

    if not retry_requests:
        return None

    after_skills_speech = [
        speech
        for speech in response.speech
        if speech.timing == "after_skills"
    ]
    metadata = {
        **response.metadata,
        "source": "host_body_recovery_retry",
        "body_recovery_retry": True,
        "body_recovery_attempt": next_attempt,
        "body_recovery_max_attempts": max_attempts,
        "body_recovery_parent_interaction_id": response.interaction_id,
        "body_recovery_failed_request_ids": failed_request_ids,
        "body_recovery_retry_request_ids": retry_request_ids,
    }
    retry_response = InteractionResponse(
        interaction_id=f"{response.interaction_id}_recovery{next_attempt}",
        speech=after_skills_speech,
        skills=retry_requests,
        requires_confirmation=True,
        metadata=metadata,
    )
    prompt = body_recovery_prompt(
        recoverable,
        language=language,
        timeout_s=timeout_s,
        attempt=next_attempt,
        max_attempts=max_attempts,
    )
    return BodyRecoveryConfirmation(
        response=retry_response,
        confirmed_request_ids=frozenset(retry_request_ids),
        prompt=prompt,
        failed_request_ids=tuple(failed_request_ids),
        retry_request_ids=tuple(retry_request_ids),
        attempt=next_attempt,
        max_attempts=max_attempts,
    )


def body_recovery_prompt(
    results: list[SkillResult],
    *,
    language: str,
    timeout_s: float,
    attempt: int,
    max_attempts: int,
) -> str:
    zh = language.lower().startswith("zh")
    reason = _short_reason(results[0], zh=zh) if results else ""
    if zh:
        pieces = ["动作遇到了可恢复的问题，我已经停下。"]
        if reason:
            pieces.append(reason)
        pieces.append(
            "请确认是否要我重新预检后再试一次；如果不确认，我不会重试，会保持当前更保守的安全状态。"
        )
        if max_attempts > 1:
            pieces.append(f"这是第 {attempt} 次恢复尝试，最多 {max_attempts} 次。")
        pieces.append("请只回答是或否。")
        return "".join(pieces)

    pieces = ["I hit a recoverable movement issue and stopped."]
    if reason:
        pieces.append(reason)
    pieces.append(
        "Please confirm if you want me to re-check safety and try once more; without confirmation, I will not retry and will stay in the safer fallback state."
    )
    if max_attempts > 1:
        pieces.append(f"This is recovery attempt {attempt} of {max_attempts}.")
    pieces.append("Please answer yes or no.")
    return " ".join(pieces)


def conservative_body_failure_message(
    results: list[SkillResult],
    *,
    language: str,
) -> str | None:
    recoverable = recoverable_body_results(results)
    if not recoverable:
        return None
    zh = language.lower().startswith("zh")
    if zh:
        return "动作再次遇到可恢复问题，我不会继续重试。我已保持更保守的安全状态。"
    return "The movement hit a recoverable issue again, so I will not keep retrying. I have stayed in the safer fallback state."


def _recovery_attempt(request: SkillRequest) -> int:
    value = request.metadata.get("body_recovery_attempt")
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _retry_request_id(request_id: str, attempt: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_.:-]+", "_", request_id.strip()) or "skillreq"
    return f"{base}_recovery{attempt}"


def _retry_idempotency_key(
    existing: str | None,
    request_id: str,
    attempt: int,
) -> str:
    base = existing or request_id
    return f"{base}:body_recovery:{attempt}"


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _short_reason(result: SkillResult, *, zh: bool) -> str:
    output = result.output or {}
    recovery = _dict_value(output.get("recovery"))
    message = (
        recovery.get("user_message")
        or recovery.get("message")
        or output.get("user_message")
        or output.get("message")
        or result.message
        or result.reason_code
        or ""
    )
    if not isinstance(message, str):
        try:
            message = json.dumps(message, ensure_ascii=False, sort_keys=True)
        except TypeError:
            message = str(message)
    message = " ".join(message.strip().split())
    if len(message) > 160:
        message = message[:157].rstrip() + "..."
    if not message:
        return ""
    if zh:
        return f"原因：{message}。"
    return f"Reason: {message}."
