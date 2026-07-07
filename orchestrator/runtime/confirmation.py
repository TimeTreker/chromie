from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest

ConfirmationDecision = Literal[
    "approved",
    "denied",
    "ambiguous",
    "expired",
    "operational_interrupt",
    "no_pending",
    "not_confirmation",
]

_AFFIRMATIVE_PHRASES = frozenset(
    {
        "yes",
        "yes please",
        "confirm",
        "confirmed",
        "proceed",
        "go ahead",
        "do it",
        "ok",
        "okay",
        "是",
        "是的",
        "好",
        "好的",
        "确认",
        "可以",
        "执行",
        "请执行",
    }
)
_NEGATIVE_PHRASES = frozenset(
    {
        "no",
        "no thanks",
        "do not",
        "don't",
        "cancel",
        "stop",
        "never mind",
        "nevermind",
        "不",
        "不要",
        "取消",
        "停止",
        "算了",
    }
)
_OPERATIONAL_INTERRUPT_PHRASES = frozenset(
    {
        "stop",
        "cancel",
        "emergency",
        "emergency stop",
        "停止",
        "取消",
        "急停",
        "紧急停止",
    }
)
_SENSITIVE_ARGUMENT_PARTS = ("password", "secret", "token", "credential", "key")


@dataclass(frozen=True)
class PendingConfirmation:
    confirmation_id: str
    response: InteractionResponse
    confirmed_request_ids: frozenset[str]
    fingerprint: str
    prompt: str
    created_at: float
    expires_at: float
    origin_session_id: str | None
    conversation_id: str | None


@dataclass(frozen=True)
class ConfirmationResolution:
    decision: ConfirmationDecision
    confirmation_id: str | None = None
    response: InteractionResponse | None = None
    confirmed_request_ids: frozenset[str] = frozenset()
    fingerprint: str | None = None
    message: str = ""


class ConfirmationDialogue:
    """Single-use, request-bound spoken confirmation state."""

    def __init__(
        self,
        *,
        ttl_s: float = 20.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ttl_s = min(300.0, max(1.0, float(ttl_s)))
        self._clock = clock
        self._pending: PendingConfirmation | None = None

    @property
    def pending(self) -> PendingConfirmation | None:
        return self._pending

    def begin(
        self,
        response: InteractionResponse,
        *,
        confirmed_request_ids: set[str],
        origin_session_id: str | None,
        conversation_id: str | None,
        language: str | None = None,
        prompt_override: str | None = None,
        ttl_s: float | None = None,
    ) -> PendingConfirmation:
        request_ids = frozenset(confirmed_request_ids)
        known_ids = {request.request_id for request in response.skills}
        if not request_ids:
            raise ValueError("confirmation must bind at least one skill request")
        if not request_ids.issubset(known_ids):
            unknown = sorted(request_ids - known_ids)
            raise ValueError(f"confirmation references unknown request IDs: {unknown}")

        stored = response.model_copy(deep=True)
        now = self._clock()
        effective_ttl_s = self.ttl_s if ttl_s is None else min(300.0, max(1.0, float(ttl_s)))
        prompt = (prompt_override or "").strip() or _confirmation_prompt(
            stored,
            request_ids,
            language=language,
        )
        pending = PendingConfirmation(
            confirmation_id=f"confirm_{uuid4().hex[:12]}",
            response=stored,
            confirmed_request_ids=request_ids,
            fingerprint=_request_fingerprint(stored, request_ids),
            prompt=prompt,
            created_at=now,
            expires_at=now + effective_ttl_s,
            origin_session_id=origin_session_id,
            conversation_id=conversation_id,
        )
        self._pending = pending
        return pending

    def cancel(self) -> PendingConfirmation | None:
        pending = self._pending
        self._pending = None
        return pending

    def resolve(self, text: str | None) -> ConfirmationResolution:
        normalized = _normalize_reply(text)
        pending = self._pending
        if pending is None:
            if normalized in _OPERATIONAL_INTERRUPT_PHRASES:
                return ConfirmationResolution(decision="not_confirmation")
            if normalized in _AFFIRMATIVE_PHRASES or normalized in _NEGATIVE_PHRASES:
                return ConfirmationResolution(
                    decision="no_pending",
                    message="There is no action waiting for confirmation.",
                )
            return ConfirmationResolution(decision="not_confirmation")

        self._pending = None
        if normalized in _OPERATIONAL_INTERRUPT_PHRASES:
            return self._resolution(
                pending,
                "operational_interrupt",
                "The pending action was cancelled.",
            )
        if pending.expires_at <= self._clock():
            return self._resolution(
                pending,
                "expired",
                "That confirmation expired, so I will not perform the action.",
            )
        if _request_fingerprint(
            pending.response,
            pending.confirmed_request_ids,
        ) != pending.fingerprint:
            return self._resolution(
                pending,
                "ambiguous",
                "The requested action changed, so I will not perform it.",
            )
        if normalized in _AFFIRMATIVE_PHRASES:
            return self._resolution(
                pending,
                "approved",
                "Confirmed.",
                include_request=True,
            )
        if normalized in _NEGATIVE_PHRASES:
            return self._resolution(
                pending,
                "denied",
                "Okay, I will not perform that action.",
            )
        return self._resolution(
            pending,
            "ambiguous",
            "I did not get a clear yes or no, so I will not perform the action.",
        )

    @staticmethod
    def _resolution(
        pending: PendingConfirmation,
        decision: ConfirmationDecision,
        message: str,
        *,
        include_request: bool = False,
    ) -> ConfirmationResolution:
        return ConfirmationResolution(
            decision=decision,
            confirmation_id=pending.confirmation_id,
            response=(
                pending.response.model_copy(deep=True)
                if include_request
                else None
            ),
            confirmed_request_ids=(
                pending.confirmed_request_ids if include_request else frozenset()
            ),
            fingerprint=pending.fingerprint,
            message=message,
        )


def _normalize_reply(text: str | None) -> str:
    normalized = " ".join((text or "").strip().casefold().split())
    normalized = re.sub(r"[,;:，、；：]+", " ", normalized)
    normalized = " ".join(normalized.split())
    return re.sub(r"[.!?。！？]+$", "", normalized).strip()


def _request_fingerprint(
    response: InteractionResponse,
    request_ids: frozenset[str],
) -> str:
    payload = {
        "interaction_id": response.interaction_id,
        "requests": [
            request.model_dump(mode="json")
            for request in response.skills
            if request.request_id in request_ids
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _confirmation_prompt(
    response: InteractionResponse,
    request_ids: frozenset[str],
    *,
    language: str | None,
) -> str:
    requests = [
        request
        for request in response.skills
        if request.request_id in request_ids
    ]
    descriptions = [_describe_request(request) for request in requests]
    joined = "; ".join(descriptions)
    if (language or "").lower().startswith("zh"):
        return f"请确认：要执行{joined}吗？请只回答是或否。"
    return f"Please confirm: should I {joined}? Please answer yes or no."


def _describe_request(request: SkillRequest) -> str:
    skill_name = request.skill_id.removeprefix("soridormi.")
    skill_name = re.sub(r"[._-]+", " ", skill_name).strip() or "requested action"
    safe_args = _redact_prompt_value(request.args)
    if not safe_args:
        return f"run {skill_name}"
    rendered = json.dumps(
        safe_args,
        ensure_ascii=False,
        sort_keys=True,
        separators=(", ", ": "),
    )
    if len(rendered) > 120:
        rendered = "the requested parameters"
    return f"run {skill_name} with {rendered}"


def _redact_prompt_value(value: object, *, key: str | None = None) -> object:
    if key and any(part in key.casefold() for part in _SENSITIVE_ARGUMENT_PARTS):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(item_key): _redact_prompt_value(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_prompt_value(item) for item in value]
    return value
