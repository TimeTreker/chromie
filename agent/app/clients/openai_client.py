from __future__ import annotations

import json
import logging
from typing import Any

from shared.chromie_runtime.llm_diagnostics import ollama_prompt_preflight_diagnostics
from shared.chromie_runtime.runtime_trace import TraceModule

from ..inference_compute import CognitionComputeClass
from ..settings import AgentServiceSettings
from .ollama_client import ResponseFormat
from .openai_protocol import bearer_headers, build_openai_chat_payload
from .sglang_client import SGLangClient, SGLangGenerationError

logger = logging.getLogger("chromie.agent.openai")


class OpenAICompatibleGenerationError(SGLangGenerationError):
    """Remote OpenAI-compatible transport failure with Chromie's typed inference facts."""


def check_canonical_schema(
    text: str, schema: dict[str, Any], *, purpose: str, model: str,
) -> None:
    """Re-apply the full request schema a remote decoder may not have enforced.

    Unparseable text is left to the role's own parser, which already owns that
    failure. Any schema violation is a typed, retryable model-contract failure.
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
        raise OpenAICompatibleGenerationError(
            f"Remote model output violates the request schema: {errors[0].message[:300]}",
            failure_class="structured_output_validation",
            failure_domain="model_contract",
            architecture_attribution="not_evaluated",
            retryable=True,
            details={
                "purpose": purpose, "model": model,
                "schema_errors": [
                    {"path": "/".join(str(part) for part in error.absolute_path), "message": error.message[:300]}
                    for error in errors[:8]
                ],
                "result_trusted": False,
                "new_execution_allowed": False,
            },
        )


class OpenAICompatibleClient(SGLangClient):
    """Chromie model-client contract over any remote OpenAI-compatible chat service."""

    TRACE_MODULE = TraceModule(
        name="agent.openai",
        component_type="model_client",
        implementation="OpenAICompatibleClient",
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
    ) -> None:
        configured = service_settings or AgentServiceSettings()
        self.openai_settings = configured.openai
        resolved_model = configured.openai.model_for_role(model, purpose=purpose)
        if not resolved_model:
            # OllamaClient would otherwise fall back to the local default tag.
            raise ValueError("AGENT_OPENAI_MODEL is required when AGENT_LLM_PROVIDER=openai")
        super().__init__(
            configured.openai.base_url,
            resolved_model,
            timeout_ms=max(int(timeout_ms), configured.openai.timeout_floor_ms),
            purpose=purpose,
            compute_class=compute_class,
            service_settings=configured,
        )

    def _log_init(self) -> None:
        logger.info(
            "openai_client_init purpose=%s compute_class=%s base_url=%s model=%s structured_output=%s "
            "timeout_ms=%s credential_env=%s credential_present=%s",
            self.purpose, self.compute_class.value, self.base_url, self.model,
            self.openai_settings.structured_output, self.timeout_ms,
            self.openai_settings.api_key_env, bool(self.openai_settings.api_key()),
        )

    def _request_headers(self) -> dict[str, str]:
        return bearer_headers(self.openai_settings.api_key())

    def _payload(
        self,
        prompt: str,
        *,
        system: str | None,
        options: dict[str, Any] | None,
        response_format: ResponseFormat,
        stream: bool,
    ) -> dict[str, Any]:
        return build_openai_chat_payload(
            model=self.model,
            messages=self._chat_messages(prompt, system=system),
            compute_class=self.compute_class,
            options=options,
            response_format=response_format,
            stream=stream,
            structured_output=self.openai_settings.structured_output,
        )

    async def _preflight(
        self,
        *,
        prompt: str,
        system: str | None,
        options: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        # The character estimate screens against a local num_ctx; a remote service
        # has no tokenizer endpoint, so the estimate is logged and the service's
        # own context-length error is the authority.
        for diagnostic in ollama_prompt_preflight_diagnostics(
            prompt_chars=len(prompt),
            system_chars=len(system or ""),
            options=options,
            chars_per_token=self.prompt_chars_per_token_estimate,
            safety_margin_tokens=self.context_safety_margin_tokens,
        ):
            self._log_budget_diagnostic(min(diagnostic.level, logging.WARNING), diagnostic.render())

    def _parse_json(self, text: str, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        # The schema travels with the request: this client is shared by concurrent
        # calls, so instance state could validate one answer against another's schema.
        parsed = super()._parse_json(text, schema=schema)
        if isinstance(schema, dict):
            check_canonical_schema(text, schema, purpose=self.purpose, model=self.model)
        return parsed
