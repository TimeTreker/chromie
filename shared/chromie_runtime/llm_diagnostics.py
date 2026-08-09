from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


LLM_CALL_EVIDENCE_SCHEMA_VERSION = 1
LLM_CALL_EVIDENCE_LOG_MARKER = "llm_call_evidence"


_TRUNCATION_DONE_REASONS = {
    "length",
    "max_tokens",
    "max_new_tokens",
    "num_predict",
    "context_length",
    "context_window",
    "limit",
}


def new_llm_call_id(namespace: str = "runtime") -> str:
    """Return a process-independent ID for one provider inference attempt."""

    safe_namespace = "".join(
        character if character.isalnum() else "_"
        for character in str(namespace or "runtime")
    ).strip("_") or "runtime"
    return f"llmcall_{safe_namespace}_{uuid.uuid4().hex[:16]}"


def _json_compatible(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


def _raw_model_output(response: Mapping[str, Any] | None) -> str | None:
    if not isinstance(response, Mapping):
        return None
    direct = response.get("response")
    if isinstance(direct, str):
        return direct
    message = response.get("message")
    if isinstance(message, Mapping) and isinstance(message.get("content"), str):
        return str(message["content"])
    return None


def llm_call_evidence_payload(
    *,
    call_id: str,
    purpose: str,
    stage: str,
    transport: str,
    request: Mapping[str, Any],
    response: Mapping[str, Any] | None,
    status: str,
    elapsed_ms: float | None = None,
    correlations: Mapping[str, Any] | None = None,
    parsed_output: Any = None,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one private, exact prompt/output record for root-cause review.

    Ollama's ``context`` token vector is deliberately omitted because it is not
    model-authored output and can dwarf the semantic evidence. The complete
    prompt-bearing request and exact raw model text remain intact.
    """

    provider_response = dict(response or {})
    omitted_provider_fields: list[str] = []
    if "context" in provider_response:
        provider_response.pop("context", None)
        omitted_provider_fields.append("context")
    raw_output = _raw_model_output(response)
    request_value = _json_compatible(dict(request))
    response_value = _json_compatible(provider_response)
    record: dict[str, Any] = {
        "schema_version": LLM_CALL_EVIDENCE_SCHEMA_VERSION,
        "event": "chromie.llm_call_evidence",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "call_id": str(call_id),
        "purpose": str(purpose),
        "stage": str(stage),
        "transport": str(transport),
        "status": str(status),
        "correlations": _json_compatible(dict(correlations or {})),
        "request": request_value,
        "request_reference": cognition_text_reference(request_value),
        "response": {
            "raw_model_output": raw_output,
            "raw_model_output_reference": cognition_text_reference(raw_output),
            "parsed_output": _json_compatible(parsed_output),
            "provider_response": response_value,
            "omitted_provider_fields": omitted_provider_fields,
        },
        "elapsed_ms": round(float(elapsed_ms), 3)
        if elapsed_ms is not None
        else None,
        "error": _json_compatible(dict(error or {})) if error else None,
        "privacy": {
            "classification": "private_runtime_evidence",
            "contains_complete_prompt": True,
            "contains_raw_model_output": raw_output is not None,
            "safe_to_publish_without_review": False,
        },
        "root_cause_attribution": "unreviewed",
    }
    return record


def log_llm_call_evidence(
    logger: logging.Logger,
    **values: Any,
) -> dict[str, Any] | None:
    """Emit one single-line JSON record without affecting model execution."""

    try:
        record = llm_call_evidence_payload(**values)
        logger.info(
            "%s %s",
            LLM_CALL_EVIDENCE_LOG_MARKER,
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return record
    except (TypeError, ValueError, OverflowError) as exc:
        logger.warning(
            "llm_call_evidence_failed call_id=%s error_type=%s error=%s",
            values.get("call_id"),
            type(exc).__name__,
            exc,
        )
        return None


@dataclass(frozen=True)
class LlmBudgetDiagnostic:
    """A structured LLM budget warning/error that can be rendered into logs."""

    event: str
    level: int
    fields: dict[str, Any]

    def render(self) -> str:
        return f"{self.event}: " + " ".join(
            f"{key}={_format_value(value)}" for key, value in self.fields.items()
        )


def ollama_prompt_preflight_diagnostics(
    *,
    prompt_chars: int,
    options: dict[str, Any] | None,
    system_chars: int = 0,
    chars_per_token: float = 2.0,
    safety_margin_tokens: int = 0,
    warning_ratio: float = 0.90,
) -> list[LlmBudgetDiagnostic]:
    """Return conservative context-budget diagnostics before an Ollama request.

    Ollama exposes exact token counts only after generation.  The preflight
    therefore uses a configurable character/token estimate, includes both the
    prompt and system text, reserves the complete requested output budget, and
    adds an explicit safety margin.  When that declared request cannot fit in
    ``num_ctx`` it fails closed before model execution instead of allowing
    silent prompt truncation or output/context competition.
    """

    opts = options or {}
    num_ctx = _int_or_zero(opts.get("num_ctx"))
    num_predict = _int_or_zero(opts.get("num_predict"))
    input_chars = max(0, int(prompt_chars)) + max(0, int(system_chars))
    margin = max(0, int(safety_margin_tokens))
    if num_ctx <= 0 or input_chars <= 0 or chars_per_token <= 0:
        return []

    estimated_prompt_tokens = int((input_chars / chars_per_token) + 0.999)
    required_context_tokens = estimated_prompt_tokens + num_predict + margin
    fields = {
        "prompt_chars": max(0, int(prompt_chars)),
        "system_chars": max(0, int(system_chars)),
        "input_chars": input_chars,
        "chars_per_token_estimate": _format_float(chars_per_token),
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "reserved_output_tokens": num_predict,
        "safety_margin_tokens": margin,
        "required_context_tokens": required_context_tokens,
        "num_ctx": num_ctx,
        "usage": _ratio(required_context_tokens, num_ctx),
    }
    if required_context_tokens > num_ctx:
        return [
            LlmBudgetDiagnostic(
                event="llm_prompt_budget_exceeded",
                level=logging.ERROR,
                fields={
                    "reason": "estimated_prompt_plus_output_exceeds_num_ctx",
                    "failure_domain": "llm_budget",
                    "architecture_attribution": "not_evaluated",
                    "retryable": False,
                    "suggestion": "increase_num_ctx_or_reduce_declared_request_budget",
                    **fields,
                },
            )
        ]
    if required_context_tokens >= int(num_ctx * warning_ratio):
        return [
            LlmBudgetDiagnostic(
                event="llm_prompt_context_pressure",
                level=logging.WARNING,
                fields={
                    "reason": "estimated_request_near_num_ctx",
                    "suggestion": "increase_num_ctx_or_compact_prompt",
                    **fields,
                },
            )
        ]
    return []


def ollama_completion_diagnostics(
    *,
    options: dict[str, Any] | None,
    data: dict[str, Any] | None,
    prompt_chars: int | None = None,
    warning_ratio: float = 0.90,
) -> list[LlmBudgetDiagnostic]:
    """Return warning/error diagnostics from an Ollama completion payload."""

    opts = options or {}
    payload = data or {}
    num_ctx = _int_or_zero(opts.get("num_ctx"))
    num_predict = _int_or_zero(opts.get("num_predict"))
    prompt_eval_count = _int_or_zero(payload.get("prompt_eval_count"))
    eval_count = _int_or_zero(payload.get("eval_count"))
    done_reason = str(payload.get("done_reason") or payload.get("finish_reason") or "").strip()
    done_reason_key = done_reason.casefold()

    diagnostics: list[LlmBudgetDiagnostic] = []

    if num_ctx > 0 and prompt_eval_count > 0:
        prompt_fields: dict[str, Any] = {
            "prompt_eval_count": prompt_eval_count,
            "num_ctx": num_ctx,
            "usage": _ratio(prompt_eval_count, num_ctx),
            "suggestion": "increase_num_ctx_or_compact_prompt",
        }
        if prompt_chars is not None:
            prompt_fields["prompt_chars"] = prompt_chars
        if prompt_eval_count >= num_ctx:
            diagnostics.append(
                LlmBudgetDiagnostic(
                    event="llm_prompt_truncated",
                    level=logging.ERROR,
                    fields={
                        "reason": "prompt_eval_count_reached_num_ctx",
                        "failure_domain": "llm_budget",
                        "architecture_attribution": "not_evaluated",
                        "retryable": True,
                        **prompt_fields,
                    },
                )
            )
        elif prompt_eval_count >= int(num_ctx * warning_ratio):
            diagnostics.append(
                LlmBudgetDiagnostic(
                    event="llm_prompt_context_pressure",
                    level=logging.WARNING,
                    fields={
                        "reason": "prompt_eval_count_near_num_ctx",
                        **prompt_fields,
                    },
                )
            )

    if num_predict > 0 and eval_count > 0:
        output_fields: dict[str, Any] = {
            "eval_count": eval_count,
            "num_predict": num_predict,
            "usage": _ratio(eval_count, num_predict),
            "done_reason": done_reason or "unknown",
            "suggestion": "increase_num_predict_or_shorten_response",
        }
        truncated_by_reason = done_reason_key in _TRUNCATION_DONE_REASONS
        exhausted_budget = eval_count >= num_predict and done_reason_key not in {"stop", "done", "completed"}
        if truncated_by_reason or exhausted_budget:
            diagnostics.append(
                LlmBudgetDiagnostic(
                    event="llm_output_truncated",
                    level=logging.ERROR,
                    fields={
                        "reason": "done_reason_length"
                        if truncated_by_reason
                        else "num_predict_exhausted",
                        "failure_domain": "llm_budget",
                        "architecture_attribution": "not_evaluated",
                        "retryable": True,
                        **output_fields,
                    },
                )
            )
        elif eval_count >= int(num_predict * warning_ratio):
            diagnostics.append(
                LlmBudgetDiagnostic(
                    event="llm_output_budget_pressure",
                    level=logging.WARNING,
                    fields={
                        "reason": "eval_count_near_num_predict",
                        **output_fields,
                    },
                )
            )
    elif done_reason_key in _TRUNCATION_DONE_REASONS:
        diagnostics.append(
            LlmBudgetDiagnostic(
                event="llm_output_truncated",
                level=logging.ERROR,
                fields={
                    "reason": "done_reason_length",
                    "failure_domain": "llm_budget",
                    "architecture_attribution": "not_evaluated",
                    "retryable": True,
                    "done_reason": done_reason,
                    "suggestion": "increase_num_predict_or_shorten_response",
                },
            )
        )

    return diagnostics


def _int_or_zero(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return f"{numerator / denominator:.2f}"


def _format_float(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value)
    if not text:
        return "''"
    if any(ch.isspace() for ch in text):
        return repr(text)
    return text


_PREFIX_WINDOWS = (256, 512, 1024, 2048, 4096)


def cognition_text_reference(value: Any) -> dict[str, Any]:
    """Return a stable non-content reference for diagnostic model text.

    Any retained model text remains confined to the diagnostic channel.
    Prompt-facing state may carry this compact reference so a failure can be
    correlated with the matching log record without replaying the output.
    """

    if value is None:
        return {"chars": 0, "digest": ""}
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    return {
        "chars": len(text),
        "digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _optional_ns_to_ms(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(int(value) / 1_000_000, 3)
    except (TypeError, ValueError):
        return None


def _prefix_proxy(system: str | None, prompt: str | None) -> str:
    # This is a raw request-character proxy, not Ollama's final templated token
    # sequence. The explicit separator prevents an ambiguous concatenation.
    return f"system\0{system or ''}\0prompt\0{prompt or ''}"


def _prefix_digests(value: str) -> dict[int, str]:
    return {
        window: hashlib.sha256(value[:window].encode("utf-8")).hexdigest()
        for window in _PREFIX_WINDOWS
        if len(value) >= window
    }


@dataclass(frozen=True)
class PrefixCacheProbe:
    event: str
    fields: dict[str, Any]

    def render(self) -> str:
        return f"{self.event}: " + " ".join(
            f"{key}={_format_value(value)}" for key, value in self.fields.items()
        )


@dataclass
class _PrefixHistory:
    call_id: str
    sequence: int
    model: str
    purpose: str
    prompt_family: str
    proxy_chars: int
    full_digest: str
    window_digests: dict[int, str]
    declared_stable_prefix_chars: int | None
    declared_stable_prefix_bytes: int | None
    declared_stable_prefix_digest: str | None
    request_contract_digest: str | None


@dataclass
class _PendingPrefixCall:
    history: _PrefixHistory
    started_monotonic: float
    response_data: dict[str, Any] | None = None


class PrefixCacheTracker:
    """Measure request-prefix stability without assuming cache semantics.

    Calls are registered before preflight or transport begins. Consequently a
    failed first attempt remains part of the observed sequence and a later
    repair cannot be misattributed to the previous turn. Prompt families are
    supplied by call sites when one OllamaClient purpose owns multiple prompt
    shapes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._last_call: _PrefixHistory | None = None
        self._last_by_family: dict[tuple[str, str], _PrefixHistory] = {}
        self._pending: dict[str, _PendingPrefixCall] = {}

    def begin(
        self,
        *,
        purpose: str,
        prompt_family: str,
        model: str,
        system: str | None,
        prompt: str | None,
        declared_stable_layers: Iterable[tuple[str, str]] | None = None,
        request_contract_digest: str | None = None,
        trace_id: str | None = None,
        turn_id: str | None = None,
        attempt: int | None = None,
    ) -> PrefixCacheProbe:
        proxy = _prefix_proxy(system, prompt)
        window_digests = _prefix_digests(proxy)
        full_digest = hashlib.sha256(proxy.encode("utf-8")).hexdigest()
        stable_layers = tuple(declared_stable_layers or ())
        stable_layer_chars = {
            name: len(content) for name, content in stable_layers
        }
        stable_layer_bytes = {
            name: len(content.encode("utf-8")) for name, content in stable_layers
        }
        stable_layer_digests = {
            name: "sha256:"
            + hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in stable_layers
        }
        stable_descriptor = "".join(
            f"{name}\0{content}\0" for name, content in stable_layers
        )
        declared_stable_prefix_chars = (
            sum(stable_layer_chars.values()) if stable_layers else None
        )
        declared_stable_prefix_bytes = (
            sum(stable_layer_bytes.values()) if stable_layers else None
        )
        declared_stable_prefix_digest = (
            hashlib.sha256(stable_descriptor.encode("utf-8")).hexdigest()
            if stable_layers
            else None
        )
        family_key = (model, prompt_family)
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
            call_id = new_llm_call_id("agent")
            previous_call = self._last_call
            previous_family = self._last_by_family.get(family_key)
            common_lower_bound = 0
            if previous_family is not None:
                for window in _PREFIX_WINDOWS:
                    if (
                        window_digests.get(window)
                        and window_digests.get(window)
                        == previous_family.window_digests.get(window)
                    ):
                        common_lower_bound = window
                    else:
                        break
            history = _PrefixHistory(
                call_id=call_id,
                sequence=sequence,
                model=model,
                purpose=purpose,
                prompt_family=prompt_family,
                proxy_chars=len(proxy),
                full_digest=full_digest,
                window_digests=window_digests,
                declared_stable_prefix_chars=declared_stable_prefix_chars,
                declared_stable_prefix_bytes=declared_stable_prefix_bytes,
                declared_stable_prefix_digest=declared_stable_prefix_digest,
                request_contract_digest=request_contract_digest,
            )
            self._last_call = history
            self._last_by_family[family_key] = history
            self._pending[call_id] = _PendingPrefixCall(
                history=history,
                started_monotonic=time.perf_counter(),
            )
        stable_prefix_repeat = bool(
            declared_stable_prefix_digest
            and previous_family is not None
            and previous_family.declared_stable_prefix_digest
            == declared_stable_prefix_digest
            and previous_family.declared_stable_prefix_bytes
            == declared_stable_prefix_bytes
        )
        request_contract_repeat = bool(
            request_contract_digest
            and previous_family is not None
            and previous_family.request_contract_digest == request_contract_digest
        )
        return PrefixCacheProbe(
            event="llm_prefix_probe_start",
            fields={
                "call_id": call_id,
                "sequence": sequence,
                "purpose": purpose,
                "prompt_family": prompt_family,
                "model": model,
                "trace_id": trace_id,
                "turn_id": turn_id,
                "attempt": attempt,
                "probe_kind": "raw_system_prompt_character_proxy",
                "proxy_chars": len(proxy),
                "proxy_digest": "sha256:" + full_digest,
                "family_seen_before": previous_family is not None,
                "exact_proxy_repeat": (
                    previous_family is not None
                    and previous_family.proxy_chars == len(proxy)
                    and previous_family.full_digest == full_digest
                ),
                "common_prefix_lower_bound_chars": (
                    common_lower_bound if previous_family is not None else None
                ),
                "calls_since_same_family": (
                    sequence - previous_family.sequence
                    if previous_family is not None
                    else None
                ),
                "declared_stable_prefix": bool(stable_layers),
                "declared_stable_prefix_chars": declared_stable_prefix_chars,
                "declared_stable_prefix_bytes": declared_stable_prefix_bytes,
                "declared_stable_prefix_digest": (
                    "sha256:" + declared_stable_prefix_digest
                    if declared_stable_prefix_digest
                    else None
                ),
                "declared_stable_layer_chars": (
                    stable_layer_chars if stable_layers else None
                ),
                "declared_stable_layer_bytes": (
                    stable_layer_bytes if stable_layers else None
                ),
                "declared_stable_layer_digests": (
                    stable_layer_digests if stable_layers else None
                ),
                "stable_prefix_repeat": stable_prefix_repeat,
                "request_contract_digest": request_contract_digest,
                "request_contract_repeat": request_contract_repeat,
                "reuse_candidate": (
                    stable_prefix_repeat and request_contract_repeat
                ),
                "previous_call_id": (previous_call.call_id if previous_call else None),
                "previous_purpose": (previous_call.purpose if previous_call else None),
                "previous_prompt_family": (
                    previous_call.prompt_family if previous_call else None
                ),
                "previous_model": (previous_call.model if previous_call else None),
            },
        )

    def record_response(self, call_id: str, data: dict[str, Any] | None) -> None:
        with self._lock:
            pending = self._pending.get(call_id)
            if pending is not None:
                pending.response_data = dict(data or {})

    def finish(
        self,
        call_id: str,
        *,
        status: str,
        error_type: str | None = None,
        failure_class: str | None = None,
    ) -> PrefixCacheProbe | None:
        with self._lock:
            pending = self._pending.pop(call_id, None)
        if pending is None:
            return None
        data = pending.response_data or {}
        elapsed_ms = round(
            (time.perf_counter() - pending.started_monotonic) * 1000.0, 3
        )
        history = pending.history
        return PrefixCacheProbe(
            event="llm_prefix_probe_finish",
            fields={
                "call_id": call_id,
                "sequence": history.sequence,
                "purpose": history.purpose,
                "prompt_family": history.prompt_family,
                "model": history.model,
                "status": status,
                "error_type": error_type,
                "failure_class": failure_class,
                "elapsed_ms": elapsed_ms,
                "prompt_eval_count": data.get("prompt_eval_count"),
                "prompt_eval_duration_ms": _optional_ns_to_ms(
                    data.get("prompt_eval_duration")
                ),
                "load_duration_ms": _optional_ns_to_ms(data.get("load_duration")),
                "eval_count": data.get("eval_count"),
                "eval_duration_ms": _optional_ns_to_ms(data.get("eval_duration")),
                "total_duration_ms": _optional_ns_to_ms(data.get("total_duration")),
            },
        )

    def reset(self) -> None:
        """Clear process-local state for deterministic unit tests."""

        with self._lock:
            self._sequence = 0
            self._last_call = None
            self._last_by_family.clear()
            self._pending.clear()
