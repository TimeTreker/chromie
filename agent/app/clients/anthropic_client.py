from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from typing import Any, AsyncGenerator

import anthropic

from shared.chromie_runtime.llm_diagnostics import log_llm_call_evidence
from shared.chromie_runtime.runtime_trace import TraceModule

from ..inference_compute import CognitionComputeClass
from ..settings import AgentServiceSettings, AnthropicProviderSettings
from .anthropic_protocol import (
    anthropic_completion_evidence,
    anthropic_message_text,
    claude_output_schema,
    ollama_options_to_anthropic,
    schema_prompt_instruction,
)
from .ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
    ResponseFormat,
    _PREFIX_CACHE_TRACKER,
    llm_failure_metadata,
)

logger = logging.getLogger("chromie.agent.anthropic")

_SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_JSON_ONLY_INSTRUCTION = "Respond with exactly one JSON object and no other text."
# Schema digests the service rejected as native grammars; later calls use the
# prompt-stated schema directly instead of repeating a request known to fail.
_PROMPT_ONLY_SCHEMAS: set[str] = set()


class AnthropicGenerationError(OllamaGenerationError):
    """Anthropic transport failure using Chromie's existing typed inference facts."""


def _schema_digest(schema: dict[str, Any]) -> str:
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_anthropic_request(
    *,
    model: str,
    messages: list[dict[str, Any]],
    response_format: ResponseFormat,
    options: dict[str, Any] | None,
    settings: AnthropicProviderSettings,
    force_prompt_schema: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return Messages API keyword arguments and the structured-output decision."""

    system_parts = [
        str(item.get("content") or "")
        for item in messages
        if item.get("role") == "system" and item.get("content")
    ]
    conversation = [
        {"role": item["role"], "content": str(item.get("content") or "")}
        for item in messages
        if item.get("role") in {"user", "assistant"}
    ]
    if not conversation or conversation[-1]["role"] != "user":
        # Current Claude models reject assistant prefill; Chromie never relies on it.
        raise AnthropicGenerationError(
            "Anthropic request must end with a user message",
            failure_class="provider_contract_unsupported",
            failure_domain="provider_contract",
            architecture_attribution="anthropic",
            retryable=False,
            details={"model": model},
        )
    max_tokens, ignored_options = ollama_options_to_anthropic(
        options, max_tokens_floor=settings.max_tokens_floor
    )
    output_config: dict[str, Any] = {"effort": settings.effort}
    decision: dict[str, Any] = {"mode": "text", "ignored_options": ignored_options}
    if response_format == "json":
        system_parts.append(_JSON_ONLY_INSTRUCTION)
        decision["mode"] = "prompt_json"
    elif isinstance(response_format, dict):
        translation = claude_output_schema(response_format)
        digest = _schema_digest(response_format)
        native = not force_prompt_schema and digest not in _PROMPT_ONLY_SCHEMAS and (
            settings.structured_output == "native"
            or (settings.structured_output == "auto" and translation.native_eligible)
        )
        if native:
            output_config["format"] = {"type": "json_schema", "schema": translation.schema}
        else:
            system_parts.append(schema_prompt_instruction(response_format))
        decision.update(
            mode="native_schema" if native else "prompt_schema",
            schema_digest=digest,
            **translation.summary(),
        )
    elif response_format != "text":
        raise ValueError(f"Unsupported response_format: {response_format!r}")
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": conversation,
        "thinking": {"type": "adaptive"},
        "output_config": output_config,
    }
    if system_parts:
        # The system prompt and any stated schema are the stable prefix; a breakpoint
        # there lets repeated role calls read them from cache.
        request["system"] = [
            {"type": "text", "text": "\n\n".join(system_parts), "cache_control": {"type": "ephemeral"}}
        ]
    if settings.server_side_fallback:
        request["betas"] = [_SERVER_SIDE_FALLBACK_BETA]
        request["fallbacks"] = "default"
    return request, decision


def _typed_error(exc: anthropic.AnthropicError, *, purpose: str, model: str) -> AnthropicGenerationError:
    details = {"purpose": purpose, "model": model}
    if isinstance(exc, anthropic.APITimeoutError):
        return AnthropicGenerationError(
            "Anthropic request timed out", failure_class="timeout",
            failure_domain="inference_transport", architecture_attribution="not_evaluated",
            retryable=True, details=details,
        )
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return AnthropicGenerationError(
            f"Anthropic credentials were rejected: {exc}", failure_class="provider_configuration",
            failure_domain="inference_transport", architecture_attribution="not_evaluated",
            retryable=False, details=details,
        )
    if isinstance(exc, anthropic.APIStatusError):
        return AnthropicGenerationError(
            f"Anthropic returned HTTP {exc.status_code}: {str(exc)[:300]}", failure_class="http_error",
            failure_domain="inference_transport", architecture_attribution="not_evaluated",
            retryable=exc.status_code == 429 or exc.status_code >= 500,
            details={**details, "status_code": exc.status_code},
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return AnthropicGenerationError(
            f"Anthropic transport failed: {exc}", failure_class="http_error",
            failure_domain="inference_transport", architecture_attribution="not_evaluated",
            retryable=True, details=details,
        )
    # Remaining SDK errors include a missing credential, raised before any request.
    return AnthropicGenerationError(
        f"Anthropic client is not configured: {exc}", failure_class="provider_configuration",
        failure_domain="inference_transport", architecture_attribution="not_evaluated",
        retryable=False, details=details,
    )


def _check_stop(message: Any, *, purpose: str, model: str) -> None:
    stop_reason = getattr(message, "stop_reason", None)
    if stop_reason == "max_tokens":
        raise AnthropicGenerationError(
            "Anthropic output reached max_tokens before completion",
            failure_class="output_truncated", failure_domain="llm_budget",
            architecture_attribution="not_evaluated", retryable=False,
            details={"purpose": purpose, "model": model},
        )
    if stop_reason == "refusal":
        stop_details = getattr(message, "stop_details", None)
        raise AnthropicGenerationError(
            "Anthropic model declined the request",
            failure_class="model_refusal", failure_domain="model_contract",
            architecture_attribution="not_evaluated", retryable=False,
            details={
                "purpose": purpose, "model": model,
                "refusal_category": getattr(stop_details, "category", None),
                "result_trusted": False, "new_execution_allowed": False,
            },
        )


async def _final_message(client: Any, request: dict[str, Any]) -> Any:
    async with client.beta.messages.stream(**request) as stream:
        return await stream.get_final_message()


async def claude_complete(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    response_format: ResponseFormat,
    options: dict[str, Any] | None,
    settings: AnthropicProviderSettings,
    purpose: str,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run one complete Claude call; return text, evidence, request and decision.

    A schema the service rejects as a native grammar is stated in the prompt
    instead. That changes only the provider encoding of the same contract, never
    the content, and no generation has happened when the rejection arrives.
    """

    request, decision = build_anthropic_request(
        model=model, messages=messages, response_format=response_format,
        options=options, settings=settings,
    )
    try:
        message = await _final_message(client, request)
    except anthropic.BadRequestError as exc:
        if not (
            settings.structured_output == "auto"
            and decision["mode"] == "native_schema"
            and "schema" in str(exc).casefold()
        ):
            raise _typed_error(exc, purpose=purpose, model=model) from exc
        _PROMPT_ONLY_SCHEMAS.add(decision["schema_digest"])
        logger.warning(
            "anthropic_native_schema_rejected purpose=%s title=%s error=%s",
            purpose, decision.get("title"), str(exc)[:300],
        )
        request, decision = build_anthropic_request(
            model=model, messages=messages, response_format=response_format,
            options=options, settings=settings, force_prompt_schema=True,
        )
        decision["native_rejected"] = True
        try:
            message = await _final_message(client, request)
        except anthropic.AnthropicError as retry_exc:
            raise _typed_error(retry_exc, purpose=purpose, model=model) from retry_exc
    except anthropic.AnthropicError as exc:
        raise _typed_error(exc, purpose=purpose, model=model) from exc
    text = anthropic_message_text(message)
    evidence = anthropic_completion_evidence(message, text)
    _check_stop(message, purpose=purpose, model=model)
    if isinstance(response_format, dict):
        _check_canonical_schema(text, response_format, decision, purpose=purpose, model=model)
    return text, evidence, request, decision


def _check_canonical_schema(
    text: str, schema: dict[str, Any], decision: dict[str, Any], *, purpose: str, model: str,
) -> None:
    """Re-apply the full request schema that local decoders enforced while generating.

    Claude decodes a reduced schema, or none when the schema is stated in the
    prompt, so the provider boundary restores the guarantee every role parser
    was written against. Unparseable text is left to the role's own parser.
    """

    from jsonschema import Draft202012Validator

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        raw = json.loads(candidate)
    except json.JSONDecodeError:
        return
    errors = sorted(
        Draft202012Validator(schema).iter_errors(raw), key=lambda error: list(error.absolute_path)
    )
    if errors:
        raise AnthropicGenerationError(
            f"Claude output violates the request schema: {errors[0].message[:300]}",
            failure_class="structured_output_validation",
            failure_domain="model_contract",
            architecture_attribution="not_evaluated",
            retryable=True,
            details={
                "purpose": purpose, "model": model,
                "structured_output_mode": decision.get("mode"),
                "schema_errors": [
                    {"path": "/".join(str(part) for part in error.absolute_path), "message": error.message[:300]}
                    for error in errors[:8]
                ],
                "result_trusted": False,
                "new_execution_allowed": False,
            },
        )


class ClaudeClient(OllamaClient):
    """Chromie model-client contract over the Anthropic Messages API."""

    TRACE_MODULE = TraceModule(
        name="agent.anthropic",
        component_type="model_client",
        implementation="ClaudeClient",
        schema_version=1,
    )

    def __init__(
        self,
        model: str,
        *,
        timeout_ms: int,
        purpose: str | None = None,
        compute_class: CognitionComputeClass | None = None,
        service_settings: AgentServiceSettings | None = None,
        client: Any | None = None,
    ) -> None:
        configured = service_settings or AgentServiceSettings()
        self.anthropic_settings = configured.anthropic
        super().__init__(
            configured.anthropic.base_url or "https://api.anthropic.com",
            configured.anthropic.model_for_role(model),
            timeout_ms=max(int(timeout_ms), configured.anthropic.timeout_floor_ms),
            purpose=purpose,
            compute_class=compute_class,
            service_settings=configured,
        )
        self._client = client
        logger.info(
            "anthropic_client_init purpose=%s compute_class=%s model=%s role_model=%s effort=%s "
            "structured_output=%s timeout_ms=%s",
            self.purpose, self.compute_class.value, self.model, model,
            self.anthropic_settings.effort, self.anthropic_settings.structured_output, self.timeout_ms,
        )

    def _anthropic(self) -> Any:
        if self._client is None:
            kwargs: dict[str, Any] = {"timeout": self.timeout_ms / 1000.0, "max_retries": 0}
            if self.anthropic_settings.base_url:
                kwargs["base_url"] = self.anthropic_settings.base_url
            try:
                self._client = anthropic.AsyncAnthropic(**kwargs)
            except anthropic.AnthropicError as exc:
                raise _typed_error(exc, purpose=self.purpose, model=self.model) from exc
        return self._client

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
        started = time.perf_counter()
        request: dict[str, Any] | None = None
        evidence: dict[str, Any] | None = None
        parsed: dict[str, Any] | None = None
        completed = False
        try:
            text, evidence, request, decision = await claude_complete(
                self._anthropic(),
                model=self.model,
                messages=self._chat_messages(prompt, system=system),
                response_format=response_format,
                options=options,
                settings=self.anthropic_settings,
                purpose=self.purpose,
            )
            logger.info(
                "anthropic_call purpose=%s mode=%s input_tokens=%s output_tokens=%s cache_read=%s",
                self.purpose, decision["mode"], evidence.get("prompt_eval_count"),
                evidence.get("eval_count"), evidence.get("cache_read_input_tokens"),
            )
            if prefix_probe_call_id:
                _PREFIX_CACHE_TRACKER.record_response(prefix_probe_call_id, evidence)
            if response_format != "text":
                parsed = self._parse_json(text)
            completed = True
            return text.strip() if response_format == "text" else parsed or {}
        finally:
            active_error = None if completed else sys.exc_info()[1]
            log_llm_call_evidence(
                logger,
                call_id=prefix_probe_call_id or "llmcall_untracked",
                purpose=self.purpose,
                stage=str((evidence_context or {}).get("prompt_family") or self.purpose),
                transport="anthropic.messages",
                request=request,
                response=evidence,
                status=("accepted" if active_error is None else
                        "cancelled" if isinstance(active_error, asyncio.CancelledError) else "failed"),
                error=({
                    "error_type": type(active_error).__name__,
                    "message": str(active_error),
                    **(llm_failure_metadata(active_error) if isinstance(active_error, Exception) else {}),
                } if active_error is not None else None),
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations=evidence_context,
                parsed_output=parsed,
            )

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
    ) -> AsyncGenerator[str, None]:
        request_options = self._effective_options(options)
        layered_prompt = prompt if isinstance(prompt, LayeredPrompt) else None
        rendered_prompt = layered_prompt.render() if layered_prompt else str(prompt)
        family = str(prompt_family or self.purpose).strip() or self.purpose
        request, _decision = build_anthropic_request(
            model=self.model,
            messages=self._chat_messages(rendered_prompt, system=system),
            response_format=response_format,
            options=request_options,
            settings=self.anthropic_settings,
        )
        probe = _PREFIX_CACHE_TRACKER.begin(
            purpose=self.purpose,
            prompt_family=family,
            model=self.model,
            system=system,
            prompt=rendered_prompt,
            declared_stable_layers=(
                layered_prompt.stable_layer_items(system=system) if layered_prompt else None
            ),
            request_contract_digest=_schema_digest(
                {"options": request_options, "response_format": response_format,
                 "stream": True, "provider": "anthropic"}
            ),
            turn_id=turn_id,
            attempt=attempt,
        )
        call_id = str(probe.fields["call_id"])
        logger.info("%s", probe.render())
        started = time.perf_counter()
        full_text = ""
        evidence: dict[str, Any] | None = None
        status = "failed"
        try:
            try:
                async with self._anthropic().beta.messages.stream(**request) as stream:
                    async for delta in stream.text_stream:
                        if delta:
                            full_text += delta
                            yield delta
                    message = await stream.get_final_message()
            except anthropic.AnthropicError as exc:
                raise _typed_error(exc, purpose=self.purpose, model=self.model) from exc
            evidence = anthropic_completion_evidence(message, full_text)
            _check_stop(message, purpose=self.purpose, model=self.model)
            _PREFIX_CACHE_TRACKER.record_response(call_id, evidence)
            status = "completed"
        finally:
            active_error = None if status == "completed" else sys.exc_info()[1]
            log_llm_call_evidence(
                logger,
                call_id=call_id,
                purpose=self.purpose,
                stage=family,
                transport="anthropic.messages_stream",
                request=request,
                response=evidence or {"message": {"role": "assistant", "content": full_text}},
                status=("accepted" if status == "completed" else
                        "cancelled" if isinstance(active_error, asyncio.CancelledError) else "failed"),
                error=({
                    "error_type": type(active_error).__name__,
                    "message": str(active_error),
                    **(llm_failure_metadata(active_error) if isinstance(active_error, Exception) else {}),
                } if active_error is not None else None),
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations={"turn_id": turn_id, "attempt": attempt},
                parsed_output=None,
            )
            finish_probe = _PREFIX_CACHE_TRACKER.finish(
                call_id,
                status="cancelled" if isinstance(active_error, asyncio.CancelledError) else status,
                error_type=(type(active_error).__name__ if active_error else None),
                failure_class=(
                    str(llm_failure_metadata(active_error).get("failure_class") or "")
                    if isinstance(active_error, Exception)
                    else ""
                ),
            )
            if finish_probe is not None:
                logger.info("%s", finish_probe.render())
