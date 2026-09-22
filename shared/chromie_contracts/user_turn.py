from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .reflex import ReflexOutcome


UserTurnChannel = Literal["voice", "text", "trusted_event"]
InputQualitySource = Literal["asr_final", "text", "trusted_event", "unknown"]
AttentionDisposition = Literal["admit", "suppress"]
AttentionSpeechAct = Literal[
    "question",
    "request",
    "imperative",
    "greeting",
    "reply",
    "ambient_report",
    "dictation",
    "narration",
    "unclear",
]
ContextFreshness = Literal["current", "stale", "unknown"]
TurnAdmissionDisposition = Literal[
    "admit",
    "suppress",
    "unusable",
    "reflex_only",
    "reflex_and_admit",
]


def normalize_turn_text(value: str) -> str:
    """Apply only transport-safe whitespace normalization."""

    return " ".join((value or "").strip().split())




class UserTurnSourceSpan(BaseModel):
    """Closed token span into one immutable normalized UserTurnEnvelope source.

    Semantic models may select these references, but they never retype the source
    surface. Trusted code resolves the refs against the authoritative envelope.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_start_token_ref: str = Field(min_length=1, max_length=24)
    source_end_token_ref: str = Field(min_length=1, max_length=24)

    @field_validator("source_start_token_ref", "source_end_token_ref", mode="before")
    @classmethod
    def normalize_source_token_ref(cls, value: Any) -> str:
        return normalize_turn_text(str(value or ""))


def user_turn_source_span_schema(
    source_token_refs: list[str] | None,
) -> dict[str, Any]:
    """Expose all and only ordered spans; semantic models still choose their scope."""
    token_ref = (
        {"type": "string", "enum": list(source_token_refs)}
        if source_token_refs
        else {"type": "string", "minLength": 1, "maxLength": 24}
    )
    def span(starts: dict[str, Any], ends: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_start_token_ref": starts,
                "source_end_token_ref": ends,
            },
            "required": ["source_start_token_ref", "source_end_token_ref"],
            "additionalProperties": False,
        }

    if not source_token_refs:
        return span(dict(token_ref), dict(token_ref))

    def ordered(refs: list[str]) -> list[dict[str, Any]]:
        if len(refs) == 1:
            return [span({"enum": refs, "type": "string"}, {"enum": refs, "type": "string"})]
        middle = len(refs) // 2
        left, right = refs[:middle], refs[middle:]
        # Every forward span is within one half or crosses left to right.
        # Disjoint branches preserve all spans without a quadratic pair table.
        return [span({"enum": left, "type": "string"}, {"enum": right, "type": "string"}),
                *ordered(left), *ordered(right)]

    return {"oneOf": ordered(list(source_token_refs))}



def user_turn_prohibits_speech(envelope: Any) -> bool:
    """Read the trusted protective control without interpreting the utterance."""

    if not isinstance(envelope, dict):
        return False
    reflex = envelope.get("reflex")
    return bool(
        envelope.get("admission") == "reflex_and_admit"
        and isinstance(reflex, dict)
        and reflex.get("action") == "interrupt"
        and reflex.get("should_speak") is not True
    )


class OriginalTurnInput(BaseModel):
    """Immutable input evidence exactly as received by the Gateway."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(max_length=65536)


class NormalizedTurnInput(BaseModel):
    """Transport-normalized input without semantic reinterpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(max_length=65536)
    language: str = Field(default="auto", min_length=1, max_length=64)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return str(value or "auto").strip() or "auto"


class InputQualityEvidence(BaseModel):
    """Bounded evidence about whether the received input is usable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: InputQualitySource = "unknown"
    usable: bool = True
    asr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class AttentionFinding(BaseModel):
    """A bounded admission finding, never a normal intent decision.

    ``speech_act`` is preserved as immutable Gateway evidence so later latency
    phases can distinguish an already-qualified greeting from semantic work
    without reclassifying the user's words or calling a second reviewer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: AttentionDisposition
    speech_act: AttentionSpeechAct = "unclear"
    source: str = Field(min_length=1, max_length=120)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)

    @field_validator("source", "reason", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class AttentionReviewRequest(BaseModel):
    """Focused pre-Core addressedness review input.

    The contract contains no route, intent, capability, action, or plan fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    context_digest: str = Field(min_length=64, max_length=64)
    channel: UserTurnChannel
    text: str = Field(max_length=65536)
    language: str = Field(default="auto", min_length=1, max_length=64)
    engagement: dict[str, Any] = Field(default_factory=dict)
    recent_dialogue: list[dict[str, Any]] = Field(default_factory=list, max_length=8)

    @field_validator("turn_id", "session_id", "language", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("context_digest")
    @classmethod
    def validate_context_digest(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("context_digest must be a lowercase SHA-256 hex digest")
        return normalized

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class AttentionReviewResult(BaseModel):
    """Bounded Gateway attention result; never a semantic route decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    context_digest: str = Field(min_length=64, max_length=64)
    disposition: AttentionDisposition
    speech_act: AttentionSpeechAct = "unclear"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=500)

    @field_validator("turn_id", "session_id", "source", "reason", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("context_digest")
    @classmethod
    def validate_context_digest(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("context_digest must be a lowercase SHA-256 hex digest")
        return normalized

    def as_finding(self) -> AttentionFinding:
        return AttentionFinding(
            disposition=self.disposition,
            speech_act=self.speech_act,
            source=self.source,
            confidence=self.confidence,
            reason=self.reason,
        )


class ContextReference(BaseModel):
    """Source-attributed reference to a bounded immutable context snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_type: str = Field(min_length=1, max_length=120)
    reference_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=160)
    captured_at: datetime
    freshness: ContextFreshness = "unknown"
    age_ms: int | None = Field(default=None, ge=0)

    @field_validator("context_type", "reference_id", "source", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_freshness(self) -> "ContextReference":
        if self.freshness == "current" and self.age_ms is None:
            raise ValueError("current context references require age_ms")
        return self


class GatewayContextSnapshot(BaseModel):
    """Bounded, source-attributed context assembled before Core admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    captured_at: datetime
    context: dict[str, Any] = Field(default_factory=dict)
    references: tuple[ContextReference, ...] = Field(default_factory=tuple, max_length=32)
    digest: str = Field(min_length=64, max_length=64)

    @field_validator("turn_id", "session_id", "conversation_id", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> "GatewayContextSnapshot":
        encoded = json.dumps(
            self.context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        if len(encoded) > 262144:
            raise ValueError("Gateway context snapshot exceeds 262144 bytes")
        expected = hashlib.sha256(encoded).hexdigest()
        if self.digest != expected:
            raise ValueError("Gateway context snapshot digest mismatch")
        reference_ids = [item.reference_id for item in self.references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("Gateway context reference IDs must be unique")
        return self


class UserTurnEnvelope(BaseModel):
    """Canonical, evidence-preserving input to one Cognitive Core turn.

    The contract intentionally has no ordinary intent, route, goal, capability,
    plan, authorization, execution, or response fields. Compatibility adapters
    may carry those objects alongside this envelope, but never inside it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    channel: UserTurnChannel
    received_at: datetime
    original_input: OriginalTurnInput
    normalized_input: NormalizedTurnInput
    quality: InputQualityEvidence
    reflex: ReflexOutcome
    attention: AttentionFinding
    context_refs: tuple[ContextReference, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    admission: TurnAdmissionDisposition

    @field_validator("turn_id", "session_id", "conversation_id", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_gateway_invariants(self) -> "UserTurnEnvelope":
        expected_normalized = normalize_turn_text(self.original_input.text)
        if self.normalized_input.text != expected_normalized:
            raise ValueError(
                "normalized input may change whitespace only; semantic "
                "substitution is forbidden"
            )

        reference_ids = [item.reference_id for item in self.context_refs]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("context reference IDs must be unique")

        if not self.quality.usable:
            if self.admission != "unusable":
                raise ValueError("unusable input requires admission=unusable")
            if self.attention.disposition != "suppress":
                raise ValueError("unusable input must be suppressed")
        elif self.admission == "unusable":
            raise ValueError("usable input cannot use admission=unusable")

        if self.admission == "suppress":
            if self.attention.disposition != "suppress":
                raise ValueError("suppressed input requires a suppress finding")
        elif self.attention.disposition == "suppress":
            raise ValueError("a suppress finding requires admission=suppress")

        if self.reflex.action == "interrupt":
            if self.admission not in {"reflex_only", "reflex_and_admit"}:
                raise ValueError(
                    "interrupt reflexes require reflex_only or reflex_and_admit"
                )
        elif self.reflex.action == "ignore":
            if self.admission != "suppress":
                raise ValueError("ignore reflexes require admission=suppress")
        elif self.admission in {"reflex_only", "reflex_and_admit"}:
            raise ValueError(
                "reflex_only and reflex_and_admit require an interrupt reflex"
            )

        if self.admission in {"admit", "reflex_and_admit"}:
            if self.attention.disposition != "admit":
                raise ValueError("admitted input requires an admit finding")
            if not self.quality.usable:
                raise ValueError("unusable input cannot be admitted")

        return self


class CoreTurnRequest(BaseModel):
    """Normal Cognitive Core API input after Gateway admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_envelope: UserTurnEnvelope
    context_snapshot: GatewayContextSnapshot

    @model_validator(mode="after")
    def validate_core_entry(self) -> "CoreTurnRequest":
        envelope = self.turn_envelope
        snapshot = self.context_snapshot
        if envelope.admission not in {"admit", "reflex_and_admit"}:
            raise ValueError("Cognitive Core accepts only admitted UserTurnEnvelope")
        if envelope.turn_id != snapshot.turn_id:
            raise ValueError("Core turn and context snapshot turn IDs differ")
        if envelope.session_id != snapshot.session_id:
            raise ValueError("Core turn and context snapshot session IDs differ")
        if envelope.conversation_id != snapshot.conversation_id:
            raise ValueError("Core turn and context snapshot conversation IDs differ")
        envelope_refs = tuple(item.reference_id for item in envelope.context_refs)
        snapshot_refs = tuple(item.reference_id for item in snapshot.references)
        if envelope_refs != snapshot_refs:
            raise ValueError("Core turn context references do not match snapshot")
        return self


__all__ = [
    "AttentionDisposition",
    "AttentionReviewRequest",
    "AttentionReviewResult",
    "AttentionSpeechAct",
    "AttentionFinding",
    "ContextFreshness",
    "ContextReference",
    "CoreTurnRequest",
    "GatewayContextSnapshot",
    "InputQualityEvidence",
    "InputQualitySource",
    "NormalizedTurnInput",
    "OriginalTurnInput",
    "TurnAdmissionDisposition",
    "UserTurnChannel",
    "UserTurnEnvelope",
    "UserTurnSourceSpan",
    "canonical_literal_user_turn_source_span",
    "normalize_turn_text",
    "resolve_user_turn_source_span",
    "user_turn_prohibits_speech",
    "user_turn_source_span_contains",
    "user_turn_source_tokens",
]

def user_turn_source_tokens(source: str | UserTurnEnvelope) -> list[dict[str, Any]]:
    """Return deterministic closed token refs over the normalized admitted source.

    This is transport tokenization only: Latin/digit runs stay readable, CJK
    characters remain independently citable, punctuation is retained, and no
    semantic segmentation is attempted.
    """

    text = source.normalized_input.text if isinstance(source, UserTurnEnvelope) else normalize_turn_text(str(source or ""))
    tokens: list[dict[str, Any]] = []
    index = 0

    def is_cjk(char: str) -> bool:
        codepoint = ord(char)
        return (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
        )

    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        start = index
        char = text[index]
        if is_cjk(char):
            index += 1
        elif char.isalnum() or char == "_":
            index += 1
            while index < len(text):
                candidate = text[index]
                if is_cjk(candidate) or not (
                    candidate.isalnum() or candidate in {"_", "'", "’"}
                ):
                    break
                index += 1
        else:
            index += 1
        tokens.append({
            "ref": f"t{len(tokens)}",
            "surface": text[start:index],
            "start": start,
            "end": index,
        })
    return tokens


def resolve_user_turn_source_span(
    source: str | UserTurnEnvelope, span: UserTurnSourceSpan,
) -> str:
    """Materialize one model-selected source span without copying model prose."""

    text = source.normalized_input.text if isinstance(source, UserTurnEnvelope) else normalize_turn_text(str(source or ""))
    tokens = user_turn_source_tokens(text)
    by_ref = {str(item["ref"]): (index, item) for index, item in enumerate(tokens)}
    start = by_ref.get(span.source_start_token_ref)
    end = by_ref.get(span.source_end_token_ref)
    if start is None or end is None:
        raise ValueError("UserTurn source span cites an unknown token ref")
    if start[0] > end[0]:
        raise ValueError("UserTurn source span token endpoints are reversed")
    return text[int(start[1]["start"]):int(end[1]["end"])]




def canonical_literal_user_turn_source_span(
    source: str | UserTurnEnvelope,
    span: UserTurnSourceSpan,
    value: Any,
) -> UserTurnSourceSpan:
    """Narrow an already-valid span to one unique exact literal occurrence.

    This is provenance canonicalization only.  Trusted code never searches outside
    the model-selected span, never converts units/number words, and preserves the
    original span when the literal is absent or ambiguous.
    """

    if not isinstance(value, str):
        return span
    literal = normalize_turn_text(value)
    if not literal:
        return span
    tokens = user_turn_source_tokens(source)
    indexes = {str(item["ref"]): index for index, item in enumerate(tokens)}
    start = indexes.get(span.source_start_token_ref)
    end = indexes.get(span.source_end_token_ref)
    if start is None or end is None or start > end:
        return span
    matches: list[UserTurnSourceSpan] = []
    for left in range(start, end + 1):
        for right in range(left, end + 1):
            candidate = UserTurnSourceSpan(
                source_start_token_ref=str(tokens[left]["ref"]),
                source_end_token_ref=str(tokens[right]["ref"]),
            )
            if normalize_turn_text(resolve_user_turn_source_span(source, candidate)) == literal:
                matches.append(candidate)
                if len(matches) > 1:
                    return span
    return matches[0] if len(matches) == 1 else span


def user_turn_source_span_contains(
    outer: UserTurnSourceSpan, inner: UserTurnSourceSpan, *, source: str | UserTurnEnvelope,
) -> bool:
    """Return whether ``inner`` is a closed subspan of ``outer`` on this turn."""

    tokens = user_turn_source_tokens(source)
    indexes = {str(item["ref"]): index for index, item in enumerate(tokens)}
    refs = (outer.source_start_token_ref, outer.source_end_token_ref, inner.source_start_token_ref, inner.source_end_token_ref)
    if any(ref not in indexes for ref in refs):
        return False
    return indexes[outer.source_start_token_ref] <= indexes[inner.source_start_token_ref] <= indexes[inner.source_end_token_ref] <= indexes[outer.source_end_token_ref]
