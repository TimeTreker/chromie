from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal


from ..settings import AgentServiceSettings

import httpx

try:
    from chromie_runtime.llm_diagnostics import (
        PrefixCacheTracker,
        log_llm_call_evidence,
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from chromie_runtime.log_colors import colorize_for_cli
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
    from chromie_runtime.ollama_non_thinking import (
        OllamaNonThinkingViolation,
        enforce_non_thinking_ollama_response,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime.llm_diagnostics import (
        PrefixCacheTracker,
        log_llm_call_evidence,
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from shared.chromie_runtime.log_colors import colorize_for_cli
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer
    from shared.chromie_runtime.ollama_non_thinking import (
        OllamaNonThinkingViolation,
        enforce_non_thinking_ollama_response,
    )


logger = logging.getLogger("chromie.agent.ollama")

ResponseFormat = Literal["text", "json"] | dict[str, Any]


@dataclass(frozen=True)
class LayeredPrompt:
    """Stable prompt layers plus the volatile session/turn suffix.

    Ollama still owns tokenization and KV-cache lifetime.  This value only makes
    the request prefix explicit so role-local builders cannot accidentally put
    turn state ahead of otherwise reusable material.
    """

    identity_world: tuple[str, ...] = ()
    operating_contract: tuple[str, ...] = ()
    capability_contract: tuple[str, ...] = ()
    volatile_suffix: str = ""

    @classmethod
    def promote(
        cls,
        rendered_prompt: str,
        *,
        identity_world: tuple[str, ...] = (),
        operating_contract: tuple[str, ...] = (),
        capability_contract: tuple[str, ...] = (),
    ) -> "LayeredPrompt":
        """Move exact rendered fragments ahead of the volatile suffix once."""

        suffix = str(rendered_prompt)
        layers = (identity_world, operating_contract, capability_contract)
        for fragments in layers:
            for fragment in fragments:
                if not fragment:
                    continue
                if fragment not in suffix:
                    raise ValueError(
                        "stable prompt fragment is absent from rendered prompt"
                    )
                suffix = suffix.replace(fragment, "", 1)
        return cls(
            identity_world=tuple(item for item in identity_world if item),
            operating_contract=tuple(
                item for item in operating_contract if item
            ),
            capability_contract=tuple(
                item for item in capability_contract if item
            ),
            volatile_suffix=suffix,
        )

    @staticmethod
    def _join(fragments: tuple[str, ...]) -> str:
        content = "".join(fragments).rstrip()
        return f"{content}\n\n" if content else ""

    def stable_layer_items(
        self,
        *,
        system: str | None,
    ) -> tuple[tuple[str, str], ...]:
        return (
            ("layer0_constitutional_foundation", system or ""),
            ("layer1_identity_world", self._join(self.identity_world)),
            ("layer2_operating_contract", self._join(self.operating_contract)),
            ("layer3_capability_contract", self._join(self.capability_contract)),
        )

    def render(self) -> str:
        return "".join(
            (
                self._join(self.identity_world),
                self._join(self.operating_contract),
                self._join(self.capability_contract),
                self.volatile_suffix,
            )
        )

    def __str__(self) -> str:
        return self.render()

    def __contains__(self, value: object) -> bool:
        return isinstance(value, str) and value in self.render()

    def casefold(self) -> str:
        return self.render().casefold()

    def index(self, value: str, *bounds: int) -> int:
        return self.render().index(value, *bounds)


class OllamaGenerationError(RuntimeError):
    """Typed inference failure with immediate domain facts, not causal judgment."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: str,
        failure_domain: str,
        architecture_attribution: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.failure_domain = failure_domain
        self.architecture_attribution = architecture_attribution
        self.retryable = bool(retryable)
        self.details = dict(details or {})

    def metadata(self) -> dict[str, Any]:
        public_details = {
            key: value
            for key, value in self.details.items()
            if not str(key).startswith("_")
        }
        return {
            "failure_class": self.failure_class,
            "failure_domain": self.failure_domain,
            "architecture_attribution": self.architecture_attribution,
            "retryable": self.retryable,
            **public_details,
        }

    def incident_evidence(self) -> dict[str, Any]:
        value = self.details.get("_incident_evidence")
        return dict(value) if isinstance(value, dict) else {}


def llm_failure_metadata(exc: Exception) -> dict[str, Any]:
    """Return stable failure-domain facts without assigning root cause."""

    if isinstance(exc, OllamaGenerationError):
        return exc.metadata()
    if isinstance(exc, httpx.TimeoutException):
        return {
            "failure_class": "timeout",
            "failure_domain": "inference_transport",
            "architecture_attribution": "not_evaluated",
            "retryable": True,
        }
    if isinstance(exc, httpx.HTTPError):
        return {
            "failure_class": "http_error",
            "failure_domain": "inference_transport",
            "architecture_attribution": "not_evaluated",
            "retryable": True,
        }
    if isinstance(exc, json.JSONDecodeError):
        return {
            "failure_class": "structured_output_invalid",
            "failure_domain": "model_contract",
            "architecture_attribution": "not_evaluated",
            "retryable": True,
        }
    if type(exc).__name__ == "ValidationError":
        return {
            "failure_class": "structured_output_validation",
            "failure_domain": "model_contract",
            "architecture_attribution": "not_evaluated",
            "retryable": True,
        }
    return {
        "failure_class": "unclassified_model_failure",
        "failure_domain": "model_or_runtime",
        "architecture_attribution": "not_evaluated",
        "retryable": False,
    }



_PREFIX_CACHE_TRACKER = PrefixCacheTracker()


class OllamaClient:
    TRACE_MODULE = TraceModule(
        name="agent.ollama",
        component_type="model_client",
        implementation="OllamaClient",
        schema_version=1,
    )

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout_ms: int | None = None,
        purpose: str | None = None,
        service_settings: AgentServiceSettings | None = None,
    ):
        configured = service_settings or AgentServiceSettings()
        self.base_url = (base_url or configured.ollama_url).rstrip("/")
        self.model = model or configured.model
        self.timeout_ms = int(timeout_ms or configured.timeout_ms)
        self.purpose = str(purpose or "unspecified").strip() or "unspecified"
        self.default_num_ctx = configured.ollama_num_ctx
        self.default_num_predict = configured.ollama_num_predict
        self.prompt_chars_per_token_estimate = (
            configured.llm_prompt_chars_per_token_estimate
        )
        self.context_safety_margin_tokens = (
            configured.llm_context_safety_margin_tokens
        )

        logger.info(
            "ollama_client_init purpose=%s base_url=%s model=%s timeout_ms=%s "
            "default_num_ctx=%s default_num_predict=%s context_safety_margin_tokens=%s",
            self.purpose,
            self.base_url,
            self.model,
            self.timeout_ms,
            self.default_num_ctx or None,
            self.default_num_predict or None,
            self.context_safety_margin_tokens,
        )

    def _effective_options(self, options: dict[str, Any] | None) -> dict[str, Any]:
        resolved = dict(options or {})
        if "num_ctx" not in resolved and self.default_num_ctx > 0:
            resolved["num_ctx"] = self.default_num_ctx
        if "num_predict" not in resolved and self.default_num_predict > 0:
            resolved["num_predict"] = self.default_num_predict
        return resolved

    @staticmethod
    def _chat_messages(prompt: str, *, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _assistant_content(payload: dict[str, Any]) -> str:
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
        else:
            # Retain compatibility with already-recorded generate-shaped test
            # fixtures and provider evidence while production uses /api/chat.
            content = payload.get("response")
        return content if isinstance(content, str) else ""

    async def generate(
        self,
        prompt: str | LayeredPrompt,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        response_format: ResponseFormat = "text",
        prompt_family: str | None = None,
        turn_id: str | None = None,
        attempt: int | None = None,
    ) -> str | dict[str, Any]:
        request_options = self._effective_options(options)
        layered_prompt = prompt if isinstance(prompt, LayeredPrompt) else None
        rendered_prompt = layered_prompt.render() if layered_prompt else prompt
        declared_stable_layers = (
            layered_prompt.stable_layer_items(system=system)
            if layered_prompt is not None
            else None
        )
        request_contract_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "options": request_options,
                    "response_format": response_format,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        response_format_label = (
            "json_schema" if isinstance(response_format, dict) else response_format
        )
        family = str(prompt_family or self.purpose).strip() or self.purpose
        snapshot = runtime_tracer.current_snapshot()
        trace_id = (
            str(snapshot.trace.get("trace_id") or "")
            if snapshot is not None
            else ""
        )
        trace_correlations = (
            dict(snapshot.trace.get("correlations") or {})
            if snapshot is not None
            else {}
        )
        start_probe = _PREFIX_CACHE_TRACKER.begin(
            purpose=self.purpose,
            prompt_family=family,
            model=self.model,
            system=system,
            prompt=rendered_prompt,
            declared_stable_layers=declared_stable_layers,
            request_contract_digest=request_contract_digest,
            trace_id=trace_id or None,
            turn_id=turn_id,
            attempt=attempt,
        )
        call_id = str(start_probe.fields["call_id"])
        logger.info("%s", start_probe.render())
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="generate",
            kind="model_call",
            attributes={
                "purpose": self.purpose,
                "prompt_family": family,
                "model": self.model,
                "response_format": response_format_label,
                "timeout_ms": self.timeout_ms,
                "prompt_chars": len(rendered_prompt),
                "system_chars": len(system or ""),
                "declared_stable_prefix_chars": start_probe.fields.get(
                    "declared_stable_prefix_chars"
                ),
                "declared_stable_prefix_digest": start_probe.fields.get(
                    "declared_stable_prefix_digest"
                ),
                "stable_prefix_repeat": start_probe.fields.get(
                    "stable_prefix_repeat"
                ),
                "reuse_candidate": start_probe.fields.get("reuse_candidate"),
                "num_ctx": request_options.get("num_ctx"),
                "num_predict": request_options.get("num_predict"),
                "llm_call_id": call_id,
                "attempt": attempt,
            },
        ) as span:
            finish_probe = None
            try:
                result = await self._generate(
                    rendered_prompt,
                    system=system,
                    options=request_options,
                    response_format=response_format,
                    prefix_probe_call_id=call_id,
                    evidence_context={
                        **trace_correlations,
                        "trace_id": trace_id or None,
                        "turn_id": turn_id,
                        "prompt_family": family,
                        "attempt": attempt,
                    },
                )
            finally:
                active_error = sys.exc_info()[1]
                if active_error is None:
                    finish_probe = _PREFIX_CACHE_TRACKER.finish(
                        call_id,
                        status="completed",
                    )
                else:
                    cancelled = isinstance(active_error, asyncio.CancelledError)
                    failure = (
                        llm_failure_metadata(active_error)
                        if isinstance(active_error, Exception)
                        else {"failure_class": "cancelled"}
                    )
                    finish_probe = _PREFIX_CACHE_TRACKER.finish(
                        call_id,
                        status="cancelled" if cancelled else "failed",
                        error_type=type(active_error).__name__,
                        failure_class=str(failure.get("failure_class") or ""),
                    )
                if finish_probe is not None:
                    logger.info("%s", finish_probe.render())
            if finish_probe is not None:
                span.set_attribute(
                    "prompt_eval_duration_ms",
                    finish_probe.fields.get("prompt_eval_duration_ms"),
                )
            if isinstance(result, str):
                span.set_attribute("response_chars", len(result))
            elif isinstance(result, dict):
                span.set_attribute("response_key_count", len(result))
            return result

    async def generate_stream(
        self,
        prompt: str | LayeredPrompt,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        response_format: ResponseFormat = "text",
        prompt_family: str | None = None,
        turn_id: str | None = None,
        attempt: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield trusted Ollama response deltas from one inference invocation.

        This transport does not decide application-level commit boundaries. The
        caller must buffer and validate a complete typed value before realizing
        it. Provider errors, truncation, and non-thinking violations terminate the
        iterator with ``OllamaGenerationError``; no automatic retry is performed.
        """

        request_options = self._effective_options(options)
        layered_prompt = prompt if isinstance(prompt, LayeredPrompt) else None
        rendered_prompt = layered_prompt.render() if layered_prompt else prompt
        declared_stable_layers = (
            layered_prompt.stable_layer_items(system=system)
            if layered_prompt is not None
            else None
        )
        structured_output = response_format == "json" or isinstance(
            response_format, dict
        )
        if not isinstance(response_format, dict) and response_format not in {
            "text",
            "json",
        }:
            raise ValueError(f"Unsupported response_format: {response_format!r}")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._chat_messages(rendered_prompt, system=system),
            "stream": True,
            "think": False,
            "options": request_options,
        }
        if response_format == "json":
            payload["format"] = "json"
        elif isinstance(response_format, dict):
            payload["format"] = response_format

        preflight = ollama_prompt_preflight_diagnostics(
            prompt_chars=len(rendered_prompt),
            system_chars=len(system or ""),
            options=request_options,
            chars_per_token=self.prompt_chars_per_token_estimate,
            safety_margin_tokens=self.context_safety_margin_tokens,
        )
        for diagnostic in preflight:
            self._log_budget_diagnostic(diagnostic.level, diagnostic.render())
        blocking_preflight = next(
            (
                item
                for item in preflight
                if item.event == "llm_prompt_budget_exceeded"
                and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking_preflight is not None:
            raise OllamaGenerationError(
                "Ollama streaming request rejected before inference: "
                + blocking_preflight.render(),
                failure_class="prompt_budget_exceeded",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": self.purpose,
                    "model": self.model,
                    **blocking_preflight.fields,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                },
            )

        request_contract_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "options": request_options,
                    "response_format": response_format,
                    "stream": True,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        family = str(prompt_family or self.purpose).strip() or self.purpose
        start_probe = _PREFIX_CACHE_TRACKER.begin(
            purpose=self.purpose,
            prompt_family=family,
            model=self.model,
            system=system,
            prompt=rendered_prompt,
            declared_stable_layers=declared_stable_layers,
            request_contract_digest=request_contract_digest,
            turn_id=turn_id,
            attempt=attempt,
        )
        call_id = str(start_probe.fields["call_id"])
        logger.info("%s", start_probe.render())
        started = time.perf_counter()
        full_text = ""
        final_payload: dict[str, Any] | None = None
        status = "failed"
        active_error: BaseException | None = None
        try:
            timeout = httpx.Timeout(self.timeout_ms / 1000.0)
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(
                            "utf-8", errors="replace"
                        )[:1000]
                        raise OllamaGenerationError(
                            f"Ollama returned HTTP {response.status_code}: {body[:300]}",
                            failure_class="http_error",
                            failure_domain="inference_transport",
                            architecture_attribution="not_evaluated",
                            retryable=True,
                            details={
                                "purpose": self.purpose,
                                "model": self.model,
                                "status_code": response.status_code,
                            },
                        )
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise OllamaGenerationError(
                                "Ollama streaming response contained invalid NDJSON",
                                failure_class="stream_transport_invalid",
                                failure_domain="provider_contract",
                                architecture_attribution="ollama",
                                retryable=True,
                            ) from exc
                        if not isinstance(chunk, dict):
                            raise OllamaGenerationError(
                                "Ollama streaming response chunk is not an object",
                                failure_class="stream_transport_invalid",
                                failure_domain="provider_contract",
                                architecture_attribution="ollama",
                                retryable=True,
                            )
                        if chunk.get("error"):
                            raise OllamaGenerationError(
                                "Ollama streaming inference error: "
                                + str(chunk.get("error"))[:300],
                                failure_class="stream_provider_error",
                                failure_domain="inference_transport",
                                architecture_attribution="not_evaluated",
                                retryable=True,
                            )
                        for field in ("thinking", "reasoning", "reasoning_content"):
                            if chunk.get(field) not in (None, "", [], {}):
                                raise OllamaGenerationError(
                                    "Ollama streaming response exposed reasoning output",
                                    failure_class="thinking_output_violation",
                                    failure_domain="provider_contract",
                                    architecture_attribution="ollama_or_model_template",
                                    retryable=True,
                                )
                        message = chunk.get("message")
                        if isinstance(message, dict):
                            for field in (
                                "thinking",
                                "reasoning",
                                "reasoning_content",
                            ):
                                if message.get(field) not in (None, "", [], {}):
                                    raise OllamaGenerationError(
                                        "Ollama streaming response exposed reasoning output",
                                        failure_class="thinking_output_violation",
                                        failure_domain="provider_contract",
                                        architecture_attribution="ollama_or_model_template",
                                        retryable=True,
                                    )
                            delta = message.get("content")
                        else:
                            delta = chunk.get("response")
                        if delta is not None and not isinstance(delta, str):
                            raise OllamaGenerationError(
                                "Ollama streaming response delta is not text",
                                failure_class="stream_transport_invalid",
                                failure_domain="provider_contract",
                                architecture_attribution="ollama",
                                retryable=True,
                            )
                        if delta:
                            full_text += delta
                            yield delta
                        if chunk.get("done") is True:
                            final_payload = dict(chunk)
            if final_payload is None:
                raise OllamaGenerationError(
                    "Ollama streaming response ended without a terminal chunk",
                    failure_class="stream_terminal_missing",
                    failure_domain="inference_transport",
                    architecture_attribution="not_evaluated",
                    retryable=True,
                )
            provider_message = dict(final_payload.get("message") or {})
            provider_message.update({"role": "assistant", "content": full_text})
            provider_payload = {**final_payload, "message": provider_message}
            try:
                boundary = enforce_non_thinking_ollama_response(
                    provider_payload,
                    structured_output=structured_output,
                )
            except OllamaNonThinkingViolation as exc:
                raise OllamaGenerationError(
                    str(exc),
                    failure_class="thinking_output_violation",
                    failure_domain="provider_contract",
                    architecture_attribution="ollama_or_model_template",
                    retryable=True,
                ) from exc
            if boundary.recovered:
                raise OllamaGenerationError(
                    "Streaming output required non-thinking content recovery",
                    failure_class="thinking_output_violation",
                    failure_domain="provider_contract",
                    architecture_attribution="ollama_or_model_template",
                    retryable=True,
                )
            completion_diagnostics = ollama_completion_diagnostics(
                options=request_options,
                data=provider_payload,
                prompt_chars=len(rendered_prompt) + len(system or ""),
            )
            for diagnostic in completion_diagnostics:
                self._log_budget_diagnostic(diagnostic.level, diagnostic.render())
            blocking_completion = next(
                (
                    item
                    for item in completion_diagnostics
                    if item.event in {"llm_output_truncated", "llm_prompt_truncated"}
                    and item.level >= logging.ERROR
                ),
                None,
            )
            if blocking_completion is not None:
                raise OllamaGenerationError(
                    "Ollama streaming generation rejected: "
                    + blocking_completion.render(),
                    failure_class=(
                        "output_truncated"
                        if blocking_completion.event == "llm_output_truncated"
                        else "prompt_truncated"
                    ),
                    failure_domain="llm_budget",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                    details={
                        **blocking_completion.fields,
                        "result_trusted": False,
                        "new_execution_allowed": False,
                    },
                )
            _PREFIX_CACHE_TRACKER.record_response(call_id, provider_payload)
            status = "completed"
            log_llm_call_evidence(
                logger,
                call_id=call_id,
                purpose=self.purpose,
                stage=family,
                transport="ollama.chat_stream",
                request=payload,
                response=provider_payload,
                status="accepted",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations={"turn_id": turn_id, "attempt": attempt},
                parsed_output=None,
                error=None,
            )
        except BaseException as exc:
            active_error = exc
            if isinstance(exc, asyncio.CancelledError):
                raise
            normalized_error: BaseException = exc
            if isinstance(exc, httpx.TimeoutException):
                normalized_error = OllamaGenerationError(
                    "Ollama streaming request timed out",
                    failure_class="timeout",
                    failure_domain="inference_transport",
                    architecture_attribution="not_evaluated",
                    retryable=True,
                    details={"purpose": self.purpose, "model": self.model},
                )
                active_error = normalized_error
            log_llm_call_evidence(
                logger,
                call_id=call_id,
                purpose=self.purpose,
                stage=family,
                transport="ollama.chat_stream",
                request=payload,
                response={
                    "message": {"role": "assistant", "content": full_text}
                },
                status="rejected",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations={"turn_id": turn_id, "attempt": attempt},
                parsed_output=None,
                error={
                    "error_type": type(normalized_error).__name__,
                    "message": str(normalized_error),
                    **(
                        normalized_error.metadata()
                        if isinstance(normalized_error, OllamaGenerationError)
                        else {}
                    ),
                },
            )
            if normalized_error is exc:
                raise
            raise normalized_error from exc
        finally:
            finish_probe = _PREFIX_CACHE_TRACKER.finish(
                call_id,
                status=(
                    "cancelled"
                    if isinstance(active_error, asyncio.CancelledError)
                    else status
                ),
                error_type=(type(active_error).__name__ if active_error else None),
                failure_class=(
                    str(llm_failure_metadata(active_error).get("failure_class") or "")
                    if isinstance(active_error, Exception)
                    else ""
                ),
            )
            if finish_probe is not None:
                logger.info("%s", finish_probe.render())

    async def _generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        response_format: ResponseFormat = "text",
        prefix_probe_call_id: str | None = None,
        evidence_context: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._chat_messages(prompt, system=system),
            "stream": False,
            "think": False,
        }

        if options:
            payload["options"] = options

        structured_output = response_format == "json" or isinstance(response_format, dict)
        if response_format == "json":
            payload["format"] = "json"
        elif isinstance(response_format, dict):
            payload["format"] = response_format
        elif response_format != "text":
            raise ValueError(f"Unsupported response_format: {response_format!r}")

        response_format_label = "json_schema" if isinstance(response_format, dict) else response_format
        url = f"{self.base_url}/api/chat"
        timeout = httpx.Timeout(self.timeout_ms / 1000.0)
        evidence_started = time.perf_counter()
        evidence_recorded = False

        def record_evidence(
            *,
            status: str,
            response_payload: dict[str, Any] | None = None,
            parsed_output: Any = None,
            error: dict[str, Any] | None = None,
        ) -> None:
            nonlocal evidence_recorded
            if evidence_recorded:
                return
            log_llm_call_evidence(
                logger,
                call_id=prefix_probe_call_id or "llmcall_untracked",
                purpose=self.purpose,
                stage=str(
                    (evidence_context or {}).get("prompt_family") or self.purpose
                ),
                transport="ollama.chat",
                request=payload,
                response=response_payload,
                status=status,
                elapsed_ms=(time.perf_counter() - evidence_started) * 1000.0,
                correlations=evidence_context,
                parsed_output=parsed_output,
                error=error,
            )
            evidence_recorded = True

        prompt_preview = " ".join(prompt.split())[:160]
        request_options = dict(options or {})
        num_ctx = request_options.get("num_ctx")
        num_predict = request_options.get("num_predict")

        system_chars = len(system or "")
        logger.info(
            "ollama_generate_start purpose=%s url=%s model=%s response_format=%s "
            "timeout_ms=%s num_ctx=%s num_predict=%s prompt_chars=%s system_chars=%s "
            "input_chars=%s prompt_preview=%r",
            self.purpose,
            url,
            self.model,
            response_format_label,
            self.timeout_ms,
            num_ctx,
            num_predict,
            len(prompt),
            system_chars,
            len(prompt) + system_chars,
            prompt_preview,
        )
        preflight_diagnostics = ollama_prompt_preflight_diagnostics(
            prompt_chars=len(prompt),
            system_chars=system_chars,
            options=request_options,
            chars_per_token=self.prompt_chars_per_token_estimate,
            safety_margin_tokens=self.context_safety_margin_tokens,
        )
        for diagnostic in preflight_diagnostics:
            self._log_budget_diagnostic(diagnostic.level, diagnostic.render())
        blocking_preflight = next(
            (
                item
                for item in preflight_diagnostics
                if item.event == "llm_prompt_budget_exceeded"
                and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking_preflight is not None:
            failure = OllamaGenerationError(
                f"Ollama request rejected before inference: {blocking_preflight.render()}",
                failure_class="prompt_budget_exceeded",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": self.purpose,
                    "model": self.model,
                    "response_format": response_format_label,
                    "timeout_ms": self.timeout_ms,
                    **blocking_preflight.fields,
                    "automatic_retry_allowed": False,
                    "context_reduction_allowed": False,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                    "_incident_evidence": {
                        "request": {
                            "model": self.model,
                            "purpose": self.purpose,
                            "prompt": prompt,
                            "system": system,
                            "options": request_options,
                            "response_format": response_format,
                        }
                    },
                },
            )
            logger.error(
                "ollama_request_rejected purpose=%s failure_class=prompt_budget_exceeded "
                "failure_domain=llm_budget architecture_attribution=not_evaluated "
                "retryable=false num_ctx=%s num_predict=%s required_context_tokens=%s",
                self.purpose,
                num_ctx,
                num_predict,
                blocking_preflight.fields.get("required_context_tokens"),
            )
            record_evidence(
                status="rejected_preflight",
                error={
                    "error_type": type(failure).__name__,
                    "message": str(failure),
                    **failure.metadata(),
                },
            )
            raise failure

        started = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                trust_env=False,
            ) as client:
                response = await client.post(url, json=payload)

            elapsed_ms = (time.perf_counter() - started) * 1000.0

            logger.info(
                "ollama_generate_http_done purpose=%s status_code=%s elapsed_ms=%.1f",
                self.purpose,
                response.status_code,
                elapsed_ms,
            )

            if response.status_code >= 400:
                response_error = response.text[:1000]
                lowered = response_error.casefold()
                context_limit = any(
                    marker in lowered
                    for marker in (
                        "context length",
                        "context window",
                        "input length",
                        "too many tokens",
                        "token limit",
                        "num_ctx",
                    )
                )
                failure = OllamaGenerationError(
                    f"Ollama returned HTTP {response.status_code}: {response_error[:300]}",
                    failure_class=(
                        "context_limit_exceeded" if context_limit else "http_error"
                    ),
                    failure_domain=(
                        "llm_budget" if context_limit else "inference_transport"
                    ),
                    architecture_attribution="not_evaluated",
                    retryable=True,
                    details={
                        "purpose": self.purpose,
                        "model": self.model,
                        "status_code": response.status_code,
                        "response_error": response_error,
                        "timeout_ms": self.timeout_ms,
                        "num_ctx": num_ctx,
                        "num_predict": num_predict,
                    },
                )
                logger.error(
                    "ollama_infrastructure_failure purpose=%s failure_class=%s "
                    "failure_domain=%s architecture_attribution=not_evaluated retryable=true "
                    "status_code=%s num_ctx=%s num_predict=%s response_error=%r",
                    self.purpose,
                    failure.failure_class,
                    failure.failure_domain,
                    response.status_code,
                    num_ctx,
                    num_predict,
                    response_error[:300],
                )
                record_evidence(
                    status="provider_error",
                    response_payload={
                        "status_code": response.status_code,
                        "error_body": response.text,
                    },
                    error={
                        "error_type": type(failure).__name__,
                        "message": str(failure),
                        **failure.metadata(),
                    },
                )
                raise failure

            response.raise_for_status()
            provider_data = response.json()
            try:
                boundary = enforce_non_thinking_ollama_response(
                    provider_data,
                    structured_output=structured_output,
                )
            except OllamaNonThinkingViolation as exc:
                failure = OllamaGenerationError(
                    str(exc),
                    failure_class="thinking_output_violation",
                    failure_domain="provider_contract",
                    architecture_attribution="ollama_or_model_template",
                    retryable=True,
                    details={
                        "purpose": self.purpose,
                        "model": self.model,
                        "response_format": response_format_label,
                        "violation": exc.reason,
                        "result_trusted": False,
                        "new_execution_allowed": False,
                    },
                )
                logger.error(
                    "ollama_non_thinking_boundary_rejected purpose=%s model=%s "
                    "violation=%s",
                    self.purpose,
                    self.model,
                    exc.reason,
                )
                record_evidence(
                    status="rejected_provider_contract",
                    error={
                        "error_type": type(failure).__name__,
                        "message": str(failure),
                        **failure.metadata(),
                    },
                )
                raise failure from exc
            data = boundary.response
            if boundary.recovered:
                logger.warning(
                    "ollama_non_thinking_boundary_recovered purpose=%s model=%s "
                    "recovery=%s",
                    self.purpose,
                    self.model,
                    boundary.recovery,
                )
            if prefix_probe_call_id:
                _PREFIX_CACHE_TRACKER.record_response(prefix_probe_call_id, data)

            text = self._assistant_content(data).strip()

            logger.info(
                "ollama_generate_done purpose=%s response_chars=%s done_reason=%s "
                "prompt_eval_count=%s eval_count=%s response_preview=%r",
                self.purpose,
                len(text),
                data.get("done_reason") or data.get("finish_reason") or "unknown",
                data.get("prompt_eval_count"),
                data.get("eval_count"),
                " ".join(text.split())[:160],
            )
            completion_diagnostics = ollama_completion_diagnostics(
                options=request_options,
                data=data,
                prompt_chars=len(prompt) + system_chars,
            )
            for diagnostic in completion_diagnostics:
                self._log_budget_diagnostic(diagnostic.level, diagnostic.render())

            blocking = next(
                (
                    item
                    for item in completion_diagnostics
                    if item.event in {"llm_output_truncated", "llm_prompt_truncated"}
                    and item.level >= logging.ERROR
                ),
                None,
            )
            if blocking is not None:
                failure_class = (
                    "output_truncated"
                    if blocking.event == "llm_output_truncated"
                    else "prompt_truncated"
                )
                generation_kind = "structured JSON" if structured_output else "text"
                failure = OllamaGenerationError(
                    f"{generation_kind} generation rejected: {blocking.render()}",
                    failure_class=failure_class,
                    failure_domain="llm_budget",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                    details={
                        "purpose": self.purpose,
                        "model": self.model,
                        "response_format": response_format_label,
                        "timeout_ms": self.timeout_ms,
                        **blocking.fields,
                        "retryable": False,
                        "automatic_retry_allowed": False,
                        "context_reduction_allowed": False,
                        "result_trusted": False,
                        "new_execution_allowed": False,
                        "_incident_evidence": {
                            "request": {
                                "model": self.model,
                                "purpose": self.purpose,
                                "prompt": prompt,
                                "system": system,
                                "options": request_options,
                                "response_format": response_format,
                            },
                            "response": data,
                        },
                    },
                )
                rejection_event = (
                    "ollama_structured_output_rejected"
                    if structured_output
                    else "ollama_text_output_rejected"
                )
                logger.error(
                    "%s purpose=%s failure_class=%s "
                    "failure_domain=%s architecture_attribution=%s retryable=%s "
                    "done_reason=%s num_ctx=%s num_predict=%s",
                    rejection_event,
                    self.purpose,
                    failure.failure_class,
                    failure.failure_domain,
                    failure.architecture_attribution,
                    failure.retryable,
                    data.get("done_reason") or data.get("finish_reason") or "unknown",
                    num_ctx,
                    num_predict,
                )
                record_evidence(
                    status="rejected_completion",
                    response_payload=data,
                    error={
                        "error_type": type(failure).__name__,
                        "message": str(failure),
                        **failure.metadata(),
                    },
                )
                raise failure

        except OllamaGenerationError as exc:
            if not evidence_recorded:
                record_evidence(
                    status="failed",
                    error={
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        **exc.metadata(),
                    },
                )
            raise
        except httpx.TimeoutException as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            failure = OllamaGenerationError(
                f"Ollama request timed out after {elapsed_ms:.1f} ms",
                failure_class="timeout",
                failure_domain="inference_transport",
                architecture_attribution="not_evaluated",
                retryable=True,
                details={
                    "purpose": self.purpose,
                    "model": self.model,
                    "timeout_ms": self.timeout_ms,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "num_ctx": num_ctx,
                    "num_predict": num_predict,
                },
            )
            logger.error(
                "ollama_infrastructure_failure purpose=%s failure_class=timeout "
                "failure_domain=inference_transport architecture_attribution=not_evaluated "
                "retryable=true timeout_ms=%s elapsed_ms=%.1f num_ctx=%s num_predict=%s",
                self.purpose,
                self.timeout_ms,
                elapsed_ms,
                num_ctx,
                num_predict,
            )
            record_evidence(
                status="failed",
                error={
                    "error_type": type(failure).__name__,
                    "message": str(failure),
                    **failure.metadata(),
                },
            )
            raise failure from exc
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            failure = llm_failure_metadata(exc)
            logger.exception(
                "ollama_generate_failed purpose=%s elapsed_ms=%.1f error_type=%s error=%s "
                "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s",
                self.purpose,
                elapsed_ms,
                type(exc).__name__,
                exc,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                failure["retryable"],
            )
            record_evidence(
                status="failed",
                error={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    **failure,
                },
            )
            raise

        if response_format == "text":
            record_evidence(status="accepted", response_payload=data)
            return text

        if structured_output:
            try:
                parsed = self._parse_json(text)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    "ollama_structured_output_invalid purpose=%s failure_class=structured_output_invalid "
                    "failure_domain=model_contract architecture_attribution=not_evaluated "
                    "retryable=true done_reason=%s response_chars=%s error=%s",
                    self.purpose,
                    data.get("done_reason") or data.get("finish_reason") or "unknown",
                    len(text),
                    exc,
                )
                record_evidence(
                    status="rejected_contract",
                    response_payload=data,
                    error={
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        **llm_failure_metadata(exc),
                    },
                )
                raise
            logger.info(
                "ollama_generate_json_parsed purpose=%s keys=%s",
                self.purpose,
                list(parsed.keys()),
            )
            record_evidence(
                status="accepted",
                response_payload=data,
                parsed_output=parsed,
            )
            return parsed

        raise ValueError(f"Unsupported response_format: {response_format}")

    def _log_budget_diagnostic(self, level: int, rendered: str) -> None:
        logger.log(
            level,
            "%s",
            colorize_for_cli(rendered, level, env_var="CHROMIE_CLI_COLOR"),
        )

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = self._strip_code_fence(text)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as original_error:
            object_start = cleaned.find("{")
            if object_start < 0:
                raise
            try:
                parsed, consumed = json.JSONDecoder().raw_decode(
                    cleaned[object_start:]
                )
            except json.JSONDecodeError:
                raise original_error from None
            trailing = cleaned[object_start + consumed :]
            if "{" in trailing:
                # Preserve the existing rejection of multiple competing JSON
                # objects. Raw decoding is used only to isolate one complete
                # object from harmless surrounding prose or unmatched closing
                # delimiters emitted after a schema-complete response.
                raise original_error from None

        if not isinstance(parsed, dict):
            raise ValueError("Ollama JSON response is not an object")

        return parsed

    def _strip_code_fence(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)

        return text.strip()
