from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable


_TRUNCATION_DONE_REASONS = {
    "length",
    "max_tokens",
    "max_new_tokens",
    "num_predict",
    "context_length",
    "context_window",
    "limit",
}


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
    chars_per_token: float = 4.0,
    warning_ratio: float = 0.90,
) -> list[LlmBudgetDiagnostic]:
    """Return approximate prompt-context warnings before an Ollama request.

    Ollama reports exact token counts only after generation.  This preflight is
    deliberately conservative and emits only context-pressure warnings based on
    a rough character/token estimate; exact truncation is detected by
    ``ollama_completion_diagnostics`` when ``prompt_eval_count`` is available.
    """

    opts = options or {}
    num_ctx = _int_or_zero(opts.get("num_ctx"))
    if num_ctx <= 0 or prompt_chars <= 0 or chars_per_token <= 0:
        return []
    estimated_prompt_tokens = int((prompt_chars / chars_per_token) + 0.999)
    if estimated_prompt_tokens < int(num_ctx * warning_ratio):
        return []
    return [
        LlmBudgetDiagnostic(
            event="llm_prompt_context_pressure",
            level=logging.WARNING,
            fields={
                "reason": "estimated_prompt_near_num_ctx",
                "prompt_chars": prompt_chars,
                "estimated_prompt_tokens": estimated_prompt_tokens,
                "num_ctx": num_ctx,
                "usage": _ratio(estimated_prompt_tokens, num_ctx),
                "suggestion": "increase_num_ctx_or_compact_prompt",
            },
        )
    ]


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
                        "architecture_attribution": "excluded",
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
                        "architecture_attribution": "excluded",
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
                    "architecture_attribution": "excluded",
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


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value)
    if not text:
        return "''"
    if any(ch.isspace() for ch in text):
        return repr(text)
    return text
