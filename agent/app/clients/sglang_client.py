from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from typing import Any, AsyncGenerator

import httpx

try:
    from chromie_runtime.llm_diagnostics import (
        log_llm_call_evidence,
        ollama_prompt_preflight_diagnostics,
    )
    from chromie_runtime.runtime_trace import TraceModule
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime.llm_diagnostics import (
        log_llm_call_evidence,
        ollama_prompt_preflight_diagnostics,
    )
    from shared.chromie_runtime.runtime_trace import TraceModule

from ..inference_compute import CognitionComputeClass
from ..settings import AgentServiceSettings
from .ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
    ResponseFormat,
    _PREFIX_CACHE_TRACKER,
    llm_failure_metadata,
)
from .sglang_protocol import (
    assert_no_sglang_reasoning,
    build_sglang_chat_payload,
    sglang_completion_content,
    sglang_stream_delta,
)

logger = logging.getLogger("chromie.agent.sglang")


class SGLangGenerationError(OllamaGenerationError):
    """SGLang transport failure using Chromie's existing typed inference facts."""


class SGLangClient(OllamaClient):
    """Chromie model-client contract over SGLang's OpenAI-compatible transport."""

    TRACE_MODULE = TraceModule(
        name="agent.sglang",
        component_type="model_client",
        implementation="SGLangClient",
        schema_version=1,
    )

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_ms: int,
        purpose: str | None = None,
        compute_class: CognitionComputeClass | None = None,
        service_settings: AgentServiceSettings | None = None,
        priority_step: int = 100,
    ) -> None:
        super().__init__(
            base_url,
            model,
            timeout_ms=timeout_ms,
            purpose=purpose,
            compute_class=compute_class,
            service_settings=service_settings,
        )
        self.priority_step = max(1, int(priority_step))
        logger.info(
            "sglang_client_init purpose=%s compute_class=%s base_url=%s model=%s priority_step=%s",
            self.purpose,
            self.compute_class.value,
            self.base_url,
            self.model,
            self.priority_step,
        )

    def _payload(
        self,
        prompt: str,
        *,
        system: str | None,
        options: dict[str, Any] | None,
        response_format: ResponseFormat,
        stream: bool,
    ) -> dict[str, Any]:
        return build_sglang_chat_payload(
            model=self.model,
            messages=self._chat_messages(prompt, system=system),
            compute_class=self.compute_class,
            options=options,
            response_format=response_format,
            stream=stream,
            priority_step=self.priority_step,
        )

    def _preflight(
        self,
        *,
        prompt: str,
        system: str | None,
        options: dict[str, Any],
    ) -> None:
        diagnostics = ollama_prompt_preflight_diagnostics(
            prompt_chars=len(prompt),
            system_chars=len(system or ""),
            options=options,
            chars_per_token=self.prompt_chars_per_token_estimate,
            safety_margin_tokens=self.context_safety_margin_tokens,
        )
        for diagnostic in diagnostics:
            self._log_budget_diagnostic(diagnostic.level, diagnostic.render())
        blocking = next(
            (
                item
                for item in diagnostics
                if item.event == "llm_prompt_budget_exceeded"
                and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking is not None:
            raise SGLangGenerationError(
                f"SGLang request rejected before inference: {blocking.render()}",
                failure_class="prompt_budget_exceeded",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": self.purpose,
                    "model": self.model,
                    **blocking.fields,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                },
            )

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
        request_options = dict(options or {})
        self._preflight(prompt=prompt, system=system, options=request_options)
        payload = self._payload(
            prompt,
            system=system,
            options=request_options,
            response_format=response_format,
            stream=False,
        )
        url = f"{self.base_url}/chat/completions"
        started = time.perf_counter()
        data: Any = None
        parsed: dict[str, Any] | None = None
        completed = False
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_ms / 1000.0),
                trust_env=False,
            ) as client:
                response = await client.post(url, json=payload)
            data = {"http_status": response.status_code, "body": response.text}
            if response.status_code >= 400:
                body = response.text[:1000]
                raise SGLangGenerationError(
                    f"SGLang returned HTTP {response.status_code}: {body[:300]}",
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
            decoded = response.json()
            if not isinstance(decoded, dict):
                raise ValueError("SGLang completion response is not an object")
            data = decoded
            text, finish_reason = sglang_completion_content(data)
            if finish_reason == "length":
                raise SGLangGenerationError(
                    "SGLang output reached max_tokens before completion",
                    failure_class="output_truncated",
                    failure_domain="llm_budget",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                    details={"purpose": self.purpose, "model": self.model},
                )
            if prefix_probe_call_id:
                _PREFIX_CACHE_TRACKER.record_response(prefix_probe_call_id, data)
            if response_format != "text":
                parsed = self._parse_json(text)
            completed = True
            return text.strip() if response_format == "text" else parsed or {}
        except asyncio.CancelledError:
            raise
        except SGLangGenerationError:
            raise
        except httpx.TimeoutException as exc:
            raise SGLangGenerationError(
                "SGLang request timed out",
                failure_class="timeout",
                failure_domain="inference_transport",
                architecture_attribution="not_evaluated",
                retryable=True,
                details={"purpose": self.purpose, "model": self.model},
            ) from exc

        finally:
            active_error = None if completed else sys.exc_info()[1]
            log_llm_call_evidence(
                logger,
                call_id=prefix_probe_call_id or "llmcall_untracked",
                purpose=self.purpose,
                stage=str((evidence_context or {}).get("prompt_family") or self.purpose),
                transport="sglang.chat",
                request=payload,
                response=data,
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
        declared_stable_layers = (
            layered_prompt.stable_layer_items(system=system)
            if layered_prompt is not None
            else None
        )
        self._preflight(
            prompt=rendered_prompt,
            system=system,
            options=request_options,
        )
        payload = self._payload(
            rendered_prompt,
            system=system,
            options=request_options,
            response_format=response_format,
            stream=True,
        )
        family = str(prompt_family or self.purpose).strip() or self.purpose
        request_contract_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "options": request_options,
                    "response_format": response_format,
                    "stream": True,
                    "provider": "sglang",
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        probe = _PREFIX_CACHE_TRACKER.begin(
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
        call_id = str(probe.fields["call_id"])
        logger.info("%s", probe.render())
        started = time.perf_counter()
        full_text = ""
        finish_reason: str | None = None
        status = "failed"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_ms / 1000.0),
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise SGLangGenerationError(
                            f"SGLang returned HTTP {response.status_code}: {body[:300]}",
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
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_text = line[5:].strip()
                        if data_text == "[DONE]":
                            break
                        chunk = json.loads(data_text)
                        if not isinstance(chunk, dict):
                            raise ValueError("SGLang streaming chunk is not an object")
                        assert_no_sglang_reasoning(chunk)
                        delta, observed_finish_reason = sglang_stream_delta(chunk)
                        if observed_finish_reason is not None:
                            finish_reason = observed_finish_reason
                        if delta:
                            full_text += delta
                            yield delta
            if finish_reason == "length":
                raise SGLangGenerationError(
                    "SGLang streaming output reached max_tokens before completion",
                    failure_class="output_truncated",
                    failure_domain="llm_budget",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                    details={"purpose": self.purpose, "model": self.model},
                )
            if finish_reason is None:
                raise SGLangGenerationError(
                    "SGLang stream ended without a finish_reason",
                    failure_class="stream_transport_invalid",
                    failure_domain="provider_contract",
                    architecture_attribution="sglang",
                    retryable=True,
                    details={"purpose": self.purpose, "model": self.model},
                )
            _PREFIX_CACHE_TRACKER.record_response(
                call_id,
                {
                    "model": self.model,
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": full_text},
                            "finish_reason": finish_reason,
                        }
                    ],
                },
            )
            status = "completed"

        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException as exc:
            raise SGLangGenerationError(
                "SGLang streaming request timed out",
                failure_class="timeout",
                failure_domain="inference_transport",
                architecture_attribution="not_evaluated",
                retryable=True,
                details={"purpose": self.purpose, "model": self.model},
            ) from exc
        finally:
            active_error = None if status == "completed" else sys.exc_info()[1]
            log_llm_call_evidence(
                logger,
                call_id=call_id,
                purpose=self.purpose,
                stage=family,
                transport="sglang.chat_stream",
                request=payload,
                response={
                    "model": self.model,
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": full_text},
                            "finish_reason": finish_reason,
                        }
                    ],
                },
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
