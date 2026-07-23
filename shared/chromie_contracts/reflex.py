from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ReflexAction = Literal["continue", "interrupt", "ignore"]
CancellationScope = Literal[
    "none",
    "output_only",
    "embodied_motion",
    "current_interaction",
    "specific_goal",
    "global_emergency",
]
ReflexTrigger = Literal[
    "none",
    "stop_command",
    "emergency_stop_command",
    "noise_or_filler",
    "repeated_filler_or_asr_hallucination",
]
ReflexPriority = Literal["low", "normal", "high", "urgent"]


class ReflexOutcome(BaseModel):
    """Deterministic pre-cognitive decision shared by every input gateway.

    A trigger records what input was recognized; it is not provider execution
    evidence or proof that an embodied safe state was reached.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    matched: bool = False
    action: ReflexAction = "continue"
    trigger: ReflexTrigger = "none"
    intent: str = "none"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = "auto"
    priority: ReflexPriority = "normal"
    interrupt_current: bool = False
    cancellation_scope: CancellationScope = "none"
    target_goal_ids: tuple[str, ...] = ()
    should_speak: bool = False
    reason: str = "No deterministic reflex matched"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action_invariants(self) -> "ReflexOutcome":
        if self.action == "continue":
            if (
                self.matched
                or self.interrupt_current
                or self.trigger != "none"
                or self.cancellation_scope != "none"
                or self.target_goal_ids
            ):
                raise ValueError("continue outcomes cannot claim a matched reflex")
        elif not self.matched:
            raise ValueError("interrupt and ignore outcomes must be matched")
        if self.action == "interrupt" and not self.interrupt_current:
            raise ValueError("interrupt outcomes must set interrupt_current")
        if self.action == "interrupt" and self.cancellation_scope == "none":
            raise ValueError("interrupt outcomes require a cancellation scope")
        if self.action != "interrupt" and self.interrupt_current:
            raise ValueError("only interrupt outcomes may set interrupt_current")
        if self.action != "interrupt" and self.cancellation_scope != "none":
            raise ValueError("only interrupt outcomes may set a cancellation scope")
        if self.cancellation_scope == "specific_goal" and not self.target_goal_ids:
            raise ValueError("specific_goal cancellation requires target_goal_ids")
        if self.cancellation_scope != "specific_goal" and self.target_goal_ids:
            raise ValueError(
                "target_goal_ids are valid only for specific_goal cancellation"
            )
        if (
            self.trigger == "emergency_stop_command"
            and self.cancellation_scope != "global_emergency"
        ):
            raise ValueError(
                "emergency stop commands require global_emergency scope"
            )
        return self


class CancellationDirective(BaseModel):
    """Trusted request to apply one already-resolved cancellation scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    source_turn_id: str = Field(min_length=1)
    requested_scope: CancellationScope
    foreground_interaction_id: str | None = None
    target_goal_ids: tuple[str, ...] = ()
    expected_plan_id: str | None = None
    expected_plan_fingerprint: str | None = None
    reason: str = ""

    @model_validator(mode="after")
    def validate_directive(self) -> "CancellationDirective":
        if self.requested_scope == "none":
            raise ValueError("cancellation directive scope cannot be none")
        if (
            self.requested_scope
            in {"output_only", "current_interaction", "specific_goal"}
            and not self.foreground_interaction_id
        ):
            raise ValueError(
                f"{self.requested_scope} requires foreground_interaction_id"
            )
        if self.requested_scope == "specific_goal":
            if not self.target_goal_ids:
                raise ValueError("specific_goal requires target_goal_ids")
            if not self.expected_plan_id or not self.expected_plan_fingerprint:
                raise ValueError(
                    "specific_goal requires exact plan identity"
                )
        elif (
            self.target_goal_ids
            or self.expected_plan_id
            or self.expected_plan_fingerprint
        ):
            raise ValueError(
                "goal and plan bindings are valid only for "
                "specific_goal cancellation"
            )
        return self


class CancellationRequestBinding(BaseModel):
    """Interaction-qualified request identity for auditable cancellation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interaction_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)


class CancellationProviderFailure(BaseModel):
    """Provider cancellation failure bound to one exact runtime request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interaction_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    error: str = Field(min_length=1)


class CancellationDispatchReceipt(BaseModel):
    """Deterministic selection/dispatch evidence, not a safe-state claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    source_turn_id: str = Field(min_length=1)
    requested_scope: CancellationScope
    effective_scope: CancellationScope
    interaction_ids: tuple[str, ...] = ()
    host_interaction_ids: tuple[str, ...] = ()
    target_goal_ids: tuple[str, ...] = ()
    expected_plan_id: str | None = None
    expected_plan_fingerprint: str | None = None
    affected_goal_ids: tuple[str, ...] = ()
    selected_request_ids: tuple[str, ...] = ()
    selected_request_bindings: tuple[CancellationRequestBinding, ...] = ()
    active_request_ids: tuple[str, ...] = ()
    active_request_bindings: tuple[CancellationRequestBinding, ...] = ()
    queued_request_ids: tuple[str, ...] = ()
    queued_request_bindings: tuple[CancellationRequestBinding, ...] = ()
    cancel_requested_request_ids: tuple[str, ...] = ()
    cancel_requested_request_bindings: tuple[
        CancellationRequestBinding, ...
    ] = ()
    non_interruptible_request_ids: tuple[str, ...] = ()
    non_interruptible_request_bindings: tuple[
        CancellationRequestBinding, ...
    ] = ()
    shared_owner_conflict_request_ids: tuple[str, ...] = ()
    stale_binding_request_ids: tuple[str, ...] = ()
    provider_cancel_failures: tuple[str, ...] = ()
    provider_cancel_failure_evidence: tuple[
        CancellationProviderFailure, ...
    ] = ()
    dispatch_failures: tuple[str, ...] = ()
    output_invalidation_requested: bool = False
    host_task_cancel_requested_interaction_ids: tuple[str, ...] = ()
    widened: bool = False
    widening_reason: str = ""
    emergency_stop_evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_receipt(self) -> "CancellationDispatchReceipt":
        if self.requested_scope == "none" or self.effective_scope == "none":
            raise ValueError("cancellation receipt scopes cannot be none")
        if self.requested_scope == "specific_goal":
            if not self.target_goal_ids:
                raise ValueError(
                    "specific_goal receipt requires target_goal_ids"
                )
            if (
                not self.expected_plan_id
                or not self.expected_plan_fingerprint
            ):
                raise ValueError(
                    "specific_goal receipt requires exact plan identity"
                )
        elif (
            self.target_goal_ids
            or self.expected_plan_id
            or self.expected_plan_fingerprint
        ):
            raise ValueError(
                "goal and plan bindings are valid only for "
                "specific_goal receipts"
            )
        if self.effective_scope != self.requested_scope and not self.widened:
            raise ValueError(
                "a changed effective scope must be marked widened"
            )
        if self.widened and not self.widening_reason:
            raise ValueError("widened cancellation requires a reason")
        if not self.widened and self.widening_reason:
            raise ValueError(
                "non-widened cancellation cannot carry a widening reason"
            )
        if (
            self.emergency_stop_evidence
            and self.requested_scope != "global_emergency"
            and self.effective_scope != "global_emergency"
        ):
            raise ValueError(
                "emergency stop evidence requires global emergency scope"
            )
        return self


_COMMAND_PREFIX = (
    r"(?:(?:please|kindly)\s+|"
    r"(?:(?:can|could|would|will)\s+you\s+)(?:please\s+)?)?"
)
_ENGLISH_EMERGENCY_PATTERNS = (
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:emergency\s+stop|e[\s-]?stop)"
        r"(?:\s+(?:the\s+robot|everything|now|right\s+now|please|immediately|"
        r"right\s+away))*"
        r"[.!?]*$",
        re.IGNORECASE,
    ),
)
_CHINESE_EMERGENCY_PATTERNS = (
    re.compile(
        r"^(?:请|麻烦你)?(?:让)?(?:机器人)?(?:现在|马上|立即|立刻)?"
        r"(?:急停|紧急停止)(?:机器人|动作|移动|运动|一切|所有动作|所有运动|"
        r"现在|马上|立即|立刻|一下|一下子)*[。！!？?]*$"
    ),
)
_OUTPUT_STOP_PATTERNS = (
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:quiet|shut\s+up|be\s+quiet|"
        r"stop\s+(?:talking|speaking)|do\s+not\s+speak|don['’]t\s+speak)"
        r"(?:\s*,?\s*(?:now|right\s+now|please|immediately|anymore|"
        r"for\s+(?:a\s+)?(?:moment|second|minute|while)))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:请|麻烦你)?(?:闭嘴|别说了|不要说了|安静|停止说话|"
        r"别讲话|不要讲话)(?:现在|马上|立即|立刻|一下)*[。！!？?]*$"
    ),
)
_MOTION_STOP_PATTERNS = (
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:stop|cancel|pause|halt)"
        r"(?:\s+(?:the\s+robot|moving|motion|walking|all\s+motion|"
        r"all\s+movement))"
        r"(?:\s+(?:right\s+now|now|please|immediately))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:请|麻烦你)?(?:让)?(?:机器人)?(?:现在|马上|立即|立刻)?"
        r"(?:停|停下|停止|暂停)"
        r"(?:(?:机器人)(?:的)?(?:动作|移动|运动)?|(?:所有)?(?:动作|移动|运动))"
        r"(?:现在|马上|立即|立刻|一下)*[。！!？?]*$"
    ),
    re.compile(
        r"^(?:请|麻烦你)?(?:让)?机器人(?:现在|马上|立即|立刻)?"
        r"(?:停|停下|停止|暂停)"
        r"(?:现在|马上|立即|立刻|一下)*[。！!？?]*$"
    ),
)
_CURRENT_INTERACTION_STOP_PATTERNS = (
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:stop|cancel|pause|halt)"
        r"\s+(?:everything|all(?:\s+(?:tasks|work))?)"
        r"(?:\s+(?:now|right\s+now|please|immediately))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:stop|cancel|enough|pause|hold\s+on)"
        r"(?:\s+(?:now|right\s+now|please|immediately))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:请|麻烦你)?(?:现在|马上|立即|立刻)?"
        r"(?:停|停下|停止|取消|暂停|打住)"
        r"(?:现在|马上|立即|立刻|一下)*[。！!？?]*$"
    ),
    re.compile(
        r"^(?:请|麻烦你)?(?:现在|马上|立即|立刻)?"
        r"(?:(?:停止|取消|暂停)(?:一切|全部|所有任务|所有工作)|"
        r"(?:一切|全部|所有任务|所有工作)(?:停止|取消|暂停))"
        r"(?:现在|马上|立即|立刻|一下)*[。！!？?]*$"
    ),
)
_INTERRUPT_NEGATION_PATTERNS = (
    re.compile(
        r"\b(?:don['’]?t|do\s+not|never)\s+(?:emergency\s+)?"
        r"(?:stop|halt|pause|cancel)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:不要|别|不能|无需|不必|不用)(?:让(?:机器人|它))?"
        r"(?:急停|紧急停止|停止|停下|暂停|取消)"
    ),
)
_IGNORE_PATTERNS = (
    re.compile(r"^$"),
    re.compile(r"^[\W_]+$"),
    re.compile(
        r"^(?:um+|uh+|er+|hmm+|mm+|嗯+|呃+|啊+|额+)[。.!?？]*$",
        re.IGNORECASE,
    ),
)
_ACK_FILLER_PHRASES = frozenset(
    {
        "all right",
        "alright",
        "ok",
        "okay",
        "right",
        "sure",
        "yeah",
        "yes",
        "yep",
        "好的",
        "好",
        "嗯",
        "啊",
        "对",
        "是的",
        "行",
    }
)
_REPEATED_FILLER_SPLIT_RE = re.compile(r"[.!?。！？,，;；]+")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def _detect_language(text: str) -> str:
    if any("一" <= char <= "鿿" for char in text):
        return "zh-CN"
    if any("Ѐ" <= char <= "ӿ" for char in text):
        return "ru-RU"
    return "en-US"


def _matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _looks_like_repeated_filler_hallucination(text: str) -> bool:
    chunks = [
        _normalize(chunk)
        for chunk in _REPEATED_FILLER_SPLIT_RE.split(text)
        if _normalize(chunk)
    ]
    if len(chunks) >= 4 and all(chunk in _ACK_FILLER_PHRASES for chunk in chunks):
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk] = counts.get(chunk, 0) + 1
        return max(counts.values()) >= 4 or len(chunks) >= 6

    words = text.split()
    if len(words) >= 5 and len(set(words)) == 1 and words[0] in _ACK_FILLER_PHRASES:
        return True

    for phrase in _ACK_FILLER_PHRASES:
        phrase_words = phrase.split()
        if len(phrase_words) < 2:
            continue
        if len(words) < len(phrase_words) * 4 or len(words) % len(phrase_words) != 0:
            continue
        if all(
            words[index : index + len(phrase_words)] == phrase_words
            for index in range(0, len(words), len(phrase_words))
        ):
            return True

    return False


class ReflexFilter:
    """Rules-only guard for commands that must not wait for model inference."""

    def evaluate(self, text: str, *, language: str | None = None) -> ReflexOutcome:
        normalized = _normalize(text)
        resolved_language = language or _detect_language(text or "")
        is_negated = _matches(normalized, _INTERRUPT_NEGATION_PATTERNS)

        if not is_negated and _matches(normalized, _ENGLISH_EMERGENCY_PATTERNS + _CHINESE_EMERGENCY_PATTERNS):
            return ReflexOutcome(
                matched=True,
                action="interrupt",
                trigger="emergency_stop_command",
                intent="global_emergency_stop",
                confidence=0.99,
                language=resolved_language,
                priority="urgent",
                interrupt_current=True,
                cancellation_scope="global_emergency",
                reason="Matched emergency stop command safety rule",
            )
        if not is_negated and _matches(normalized, _OUTPUT_STOP_PATTERNS):
            return ReflexOutcome(
                matched=True,
                action="interrupt",
                trigger="stop_command",
                intent="stop_current_output",
                confidence=0.99,
                language=resolved_language,
                priority="high",
                interrupt_current=True,
                cancellation_scope="output_only",
                reason="Matched deterministic speech-output stop rule",
            )
        if not is_negated and _matches(normalized, _MOTION_STOP_PATTERNS):
            return ReflexOutcome(
                matched=True,
                action="interrupt",
                trigger="stop_command",
                intent="stop_embodied_motion",
                confidence=0.99,
                language=resolved_language,
                priority="urgent",
                interrupt_current=True,
                cancellation_scope="embodied_motion",
                reason="Matched deterministic embodied-motion stop rule",
            )
        if not is_negated and _matches(
            normalized,
            _CURRENT_INTERACTION_STOP_PATTERNS,
        ):
            return ReflexOutcome(
                matched=True,
                action="interrupt",
                trigger="stop_command",
                intent="cancel_current_interaction",
                confidence=0.99,
                language=resolved_language,
                priority="urgent",
                interrupt_current=True,
                cancellation_scope="current_interaction",
                reason="Matched deterministic foreground-interaction stop rule",
            )
        if _matches(normalized, _IGNORE_PATTERNS):
            return ReflexOutcome(
                matched=True,
                action="ignore",
                trigger="noise_or_filler",
                intent="noise_or_filler",
                confidence=0.90,
                language=resolved_language,
                priority="low",
                reason="Matched ignore/noise rule",
            )
        if _looks_like_repeated_filler_hallucination(normalized):
            return ReflexOutcome(
                matched=True,
                action="ignore",
                trigger="repeated_filler_or_asr_hallucination",
                intent="repeated_filler_or_asr_hallucination",
                confidence=0.94,
                language=resolved_language,
                priority="low",
                reason="Repeated filler/acknowledgment ASR hallucination",
            )
        return ReflexOutcome(language=resolved_language)


DEFAULT_REFLEX_FILTER = ReflexFilter()
