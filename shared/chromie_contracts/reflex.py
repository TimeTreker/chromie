from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ReflexAction = Literal["continue", "interrupt", "ignore"]
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
    should_speak: bool = False
    reason: str = "No deterministic reflex matched"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action_invariants(self) -> "ReflexOutcome":
        if self.action == "continue":
            if self.matched or self.interrupt_current or self.trigger != "none":
                raise ValueError("continue outcomes cannot claim a matched reflex")
        elif not self.matched:
            raise ValueError("interrupt and ignore outcomes must be matched")
        if self.action == "interrupt" and not self.interrupt_current:
            raise ValueError("interrupt outcomes must set interrupt_current")
        if self.action != "interrupt" and self.interrupt_current:
            raise ValueError("only interrupt outcomes may set interrupt_current")
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
_STOP_PATTERNS = (
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:stop|cancel|quiet|shut\s+up|be\s+quiet|enough|"
        r"pause|hold\s+on)(?:\s+(?:now|right\s+now|please|immediately))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:stop|cancel|pause|halt)"
        r"(?:\s+(?:the\s+robot|moving|motion|walking|everything|all\s+motion|"
        r"all\s+movement|right\s+now|now|please|immediately))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^{_COMMAND_PREFIX}(?:stop\s+(?:talking|speaking)|"
        r"do\s+not\s+speak|don['’]t\s+speak)"
        r"(?:\s*,?\s*(?:now|right\s+now|please|immediately|anymore|"
        r"for\s+(?:a\s+)?(?:moment|second|minute|while)))*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:请|麻烦你)?(?:停|停下|停止|闭嘴|别说了|不要说了|安静|暂停|打住)"
        r"(?:机器人|动作|移动|运动|现在|马上|立即|立刻)*[。！!？?]*$"
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
                intent="stop_current_output",
                confidence=0.99,
                language=resolved_language,
                priority="urgent",
                interrupt_current=True,
                reason="Matched emergency stop command safety rule",
            )
        if not is_negated and _matches(normalized, _STOP_PATTERNS):
            return ReflexOutcome(
                matched=True,
                action="interrupt",
                trigger="stop_command",
                intent="stop_current_output",
                confidence=0.99,
                language=resolved_language,
                priority="urgent",
                interrupt_current=True,
                reason="Matched interrupt safety rule",
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
