from __future__ import annotations

import re

from .schema import RouteDecision, RouteRequest, detect_language, finalize_decision


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


INTERRUPT_PATTERNS = [
    r"^(?:please\s+|(?:can|could|would)\s+you\s+(?:please\s+)?)?(stop|cancel|quiet|shut up|be quiet|enough|pause|hold on)(?:\s+(?:now|please))?[.!?]*$",
    r"^(?:please\s+|(?:can|could|would)\s+you\s+(?:please\s+)?)?(stop|cancel|pause|halt)(?:\s+(?:moving|motion|walking|everything|all\s+motion|all\s+movement|right\s+now|now|please|immediately))*[.!?]*$",
    r"(stop talking|stop speaking|don't speak|do not speak)",
    r"^(?:请|麻烦你)?(停|停下|停止|闭嘴|别说了|不要说了|安静|暂停|打住)(?:动作|移动|运动|现在|马上|立刻)*[。！!？?]*$",
]

IGNORE_PATTERNS = [
    r"^$",
    r"^[\W_]+$",
    r"^(um+|uh+|er+|hmm+|mm+|嗯+|呃+|啊+|额+)[。.!?？]*$",
]

ACK_FILLER_PHRASES = frozenset(
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
REPEATED_FILLER_SPLIT_RE = re.compile(r"[.!?。！？,，;；]+")


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _looks_like_repeated_filler_hallucination(text: str) -> bool:
    chunks = [
        _norm(chunk)
        for chunk in REPEATED_FILLER_SPLIT_RE.split(text)
        if _norm(chunk)
    ]
    if len(chunks) >= 4 and all(chunk in ACK_FILLER_PHRASES for chunk in chunks):
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk] = counts.get(chunk, 0) + 1
        return max(counts.values()) >= 4 or len(chunks) >= 6

    words = text.split()
    if len(words) >= 5 and len(set(words)) == 1 and words[0] in ACK_FILLER_PHRASES:
        return True

    for phrase in ACK_FILLER_PHRASES:
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


def _looks_like_interrupt_negation(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:don'?t|do\s+not|never)\s+stop\b",
            text,
            re.IGNORECASE,
        )
    )


def route_by_priority_rules(request: RouteRequest) -> RouteDecision | None:
    """Handle only safety-critical interruption and obvious non-speech noise."""

    text = _norm(request.text)
    lang = request.language or detect_language(request.text)
    if _matches(text, INTERRUPT_PATTERNS) and not _looks_like_interrupt_negation(text):
        return finalize_decision(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="stop_current_output",
                confidence=0.99,
                language=lang,
                priority="urgent",
                interrupt_current=True,
                needs_agent=False,
                should_speak=False,
                reason="Matched interrupt safety rule",
                source="rules",
            ),
            request,
            source="rules",
        )
    if _matches(text, IGNORE_PATTERNS):
        reason = "Matched ignore/noise rule"
        intent = "noise_or_filler"
        confidence = 0.90
    elif _looks_like_repeated_filler_hallucination(text):
        reason = "Repeated filler/acknowledgment ASR hallucination"
        intent = "repeated_filler_or_asr_hallucination"
        confidence = 0.94
    else:
        return None

    return finalize_decision(
        RouteDecision(
            route="ignore",
            agents=[],
            intent=intent,
            confidence=confidence,
            language=lang,
            priority="low",
            needs_agent=False,
            should_speak=False,
            reason=reason,
            source="rules",
        ),
        request,
        source="rules",
    )
