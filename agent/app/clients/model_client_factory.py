from __future__ import annotations

from ..inference_compute import CognitionComputeClass
from ..settings import AgentServiceSettings
from .ollama_client import OllamaClient
from .sglang_client import SGLangClient


def build_model_client(
    *,
    model: str,
    timeout_ms: int,
    purpose: str,
    service_settings: AgentServiceSettings,
    compute_class: CognitionComputeClass | None = None,
) -> OllamaClient:
    """Select one operator-configured transport without changing role semantics."""

    if service_settings.llm_provider == "sglang":
        return SGLangClient(
            service_settings.sglang_url,
            model,
            timeout_ms=timeout_ms,
            purpose=purpose,
            compute_class=compute_class,
            service_settings=service_settings,
            priority_step=service_settings.sglang_priority_step,
        )
    return OllamaClient(
        service_settings.ollama_url,
        model,
        timeout_ms=timeout_ms,
        purpose=purpose,
        compute_class=compute_class,
        service_settings=service_settings,
    )
