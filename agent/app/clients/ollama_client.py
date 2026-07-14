from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Literal

import httpx

try:
    from chromie_runtime.llm_diagnostics import (
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from chromie_runtime.log_colors import colorize_for_cli
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime.llm_diagnostics import (
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from shared.chromie_runtime.log_colors import colorize_for_cli


logger = logging.getLogger("chromie.agent.ollama")

ResponseFormat = Literal["text", "json"]


class OllamaGenerationError(RuntimeError):
    """Typed inference failure that must not be attributed to cognition design."""

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
        return {
            "failure_class": self.failure_class,
            "failure_domain": self.failure_domain,
            "architecture_attribution": self.architecture_attribution,
            "retryable": self.retryable,
            **self.details,
        }


def llm_failure_metadata(exc: Exception) -> dict[str, Any]:
    """Return stable failure attribution for resolver and runtime evidence."""

    if isinstance(exc, OllamaGenerationError):
        return exc.metadata()
    if isinstance(exc, httpx.TimeoutException):
        return {
            "failure_class": "timeout",
            "failure_domain": "inference_transport",
            "architecture_attribution": "excluded",
            "retryable": True,
        }
    if isinstance(exc, httpx.HTTPError):
        return {
            "failure_class": "http_error",
            "failure_domain": "inference_transport",
            "architecture_attribution": "excluded",
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


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout_ms: int | None = None,
        purpose: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("AGENT_OLLAMA_URL")
            or os.getenv("OLLAMA_URL")
            or "http://chromie-llm:11434"
        ).rstrip("/")

        self.model = (
            model
            or os.getenv("AGENT_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "qwen3:4b"
        )

        self.timeout_ms = int(
            timeout_ms
            or os.getenv("AGENT_TIMEOUT_MS")
            or os.getenv("OLLAMA_TIMEOUT_MS")
            or "3000"
        )
        self.purpose = str(purpose or "unspecified").strip() or "unspecified"

        logger.info(
            "ollama_client_init purpose=%s base_url=%s model=%s timeout_ms=%s",
            self.purpose,
            self.base_url,
            self.model,
            self.timeout_ms,
        )

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        response_format: ResponseFormat = "text",
    ) -> str | dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
        }

        if system:
            payload["system"] = system

        if options:
            payload["options"] = options

        if response_format == "json":
            payload["format"] = "json"

        url = f"{self.base_url}/api/generate"
        timeout = httpx.Timeout(self.timeout_ms / 1000.0)

        prompt_preview = " ".join(prompt.split())[:160]
        request_options = dict(options or {})
        num_ctx = request_options.get("num_ctx")
        num_predict = request_options.get("num_predict")

        logger.info(
            "ollama_generate_start purpose=%s url=%s model=%s response_format=%s "
            "timeout_ms=%s num_ctx=%s num_predict=%s prompt_chars=%s prompt_preview=%r",
            self.purpose,
            url,
            self.model,
            response_format,
            self.timeout_ms,
            num_ctx,
            num_predict,
            len(prompt),
            prompt_preview,
        )
        for diagnostic in ollama_prompt_preflight_diagnostics(
            prompt_chars=len(prompt),
            options=options,
        ):
            self._log_budget_diagnostic(diagnostic.level, diagnostic.render())

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
                    architecture_attribution="excluded",
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
                    "failure_domain=%s architecture_attribution=excluded retryable=true "
                    "status_code=%s num_ctx=%s num_predict=%s response_error=%r",
                    self.purpose,
                    failure.failure_class,
                    failure.failure_domain,
                    response.status_code,
                    num_ctx,
                    num_predict,
                    response_error[:300],
                )
                raise failure

            response.raise_for_status()
            logger.info(
                "ollama_generate_raw_body purpose=%s body=%s",
                self.purpose,
                response.text[:2000],
            )
            data = response.json()

            text = str(data.get("response") or "").strip()

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
                options=options,
                data=data,
                prompt_chars=len(prompt),
            )
            for diagnostic in completion_diagnostics:
                self._log_budget_diagnostic(diagnostic.level, diagnostic.render())

            if response_format == "json":
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
                    failure = OllamaGenerationError(
                        f"structured JSON generation rejected: {blocking.render()}",
                        failure_class=failure_class,
                        failure_domain="llm_budget",
                        architecture_attribution="excluded",
                        retryable=True,
                        details={
                            "purpose": self.purpose,
                            "model": self.model,
                            "timeout_ms": self.timeout_ms,
                            **blocking.fields,
                        },
                    )
                    logger.error(
                        "ollama_structured_output_rejected purpose=%s failure_class=%s "
                        "failure_domain=%s architecture_attribution=%s retryable=%s "
                        "done_reason=%s num_ctx=%s num_predict=%s",
                        self.purpose,
                        failure.failure_class,
                        failure.failure_domain,
                        failure.architecture_attribution,
                        failure.retryable,
                        data.get("done_reason") or data.get("finish_reason") or "unknown",
                        num_ctx,
                        num_predict,
                    )
                    raise failure

        except OllamaGenerationError:
            raise
        except httpx.TimeoutException as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            failure = OllamaGenerationError(
                f"Ollama request timed out after {elapsed_ms:.1f} ms",
                failure_class="timeout",
                failure_domain="inference_transport",
                architecture_attribution="excluded",
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
                "failure_domain=inference_transport architecture_attribution=excluded "
                "retryable=true timeout_ms=%s elapsed_ms=%.1f num_ctx=%s num_predict=%s",
                self.purpose,
                self.timeout_ms,
                elapsed_ms,
                num_ctx,
                num_predict,
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
            raise

        if response_format == "text":
            return text

        if response_format == "json":
            try:
                parsed = self._parse_json(text)
            except json.JSONDecodeError as exc:
                logger.error(
                    "ollama_structured_output_invalid purpose=%s failure_class=structured_output_invalid "
                    "failure_domain=model_contract architecture_attribution=not_evaluated "
                    "retryable=true done_reason=%s response_chars=%s error=%s",
                    self.purpose,
                    data.get("done_reason") or data.get("finish_reason") or "unknown",
                    len(text),
                    exc,
                )
                raise
            logger.info(
                "ollama_generate_json_parsed purpose=%s keys=%s",
                self.purpose,
                list(parsed.keys()),
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
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))

        if not isinstance(parsed, dict):
            raise ValueError("Ollama JSON response is not an object")

        return parsed

    def _strip_code_fence(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)

        return text.strip()
