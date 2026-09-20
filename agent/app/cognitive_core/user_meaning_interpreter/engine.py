from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...settings import (
    UserMeaningInterpreterSettings as Settings,
    user_meaning_interpreter_settings as settings,
)
from .errors import InterpretationUnavailableError
from .model_interpreter import OllamaUserMeaningInterpreter
from .schema import UserMeaningInterpretationDecision, UserMeaningInterpretationRequest


logger = logging.getLogger("chromie.agent.user_meaning_interpreter")


user_meaning_interpreter = OllamaUserMeaningInterpreter(
    ollama_url=settings.ollama_url,
    model=settings.model,
    deep_model=settings.deep_model,
    inference_provider=settings.inference_provider,
    sglang_url=settings.sglang_url,
    sglang_priority_step=settings.sglang_priority_step,
    timeout_ms=settings.timeout_ms,
    num_ctx=settings.llm_num_ctx,
    num_predict=settings.llm_num_predict,
    keep_alive=settings.llm_keep_alive,
    prompt_path=Path(__file__).parent / "prompts" / "user_meaning_interpreter_system.txt",
)


async def initialize_user_meaning_interpreter() -> None:
    """Warm the meaning-and-orchestration model when configured.

    User Meaning Interpretation intentionally does not initialize or query Capability
    Catalog state. Capability availability belongs to Planner/Capability Runtime.
    """

    if not settings.warm_llm_on_startup:
        return
    try:
        await user_meaning_interpreter.warm_model(
            timeout_s=max(0.1, settings.warm_llm_timeout_ms / 1000.0)
        )
    except Exception as exc:
        logger.warning(
            "User Meaning Interpreter LLM startup warm failed: model=%s error_type=%s error=%s",
            settings.model,
            type(exc).__name__,
            exc,
        )
    else:
        logger.info(
            "User Meaning Interpreter LLM startup warm succeeded: model=%s keep_alive=%s",
            settings.model,
            settings.llm_keep_alive or "default",
        )


def interpretation_profile() -> dict[str, Any]:
    """Describe the maintained User Meaning Interpretation authority."""

    return {
        "authority": "meaning_and_cognitive_orchestration",
        "model": settings.model,
        "deep_model": settings.deep_model,
        "output": [
            "responsibilities", "confidence", "meaning_uncertainties",
            "cognitive_requests",
        ],
        "forbidden_authority": [
            "route",
            "intent",
            "activity",
            "work",
            "plan",
            "capability",
            "provider",
            "execution",
            "response_wording",
        ],
    }


async def interpret_user_meaning(
    request: UserMeaningInterpretationRequest,
) -> UserMeaningInterpretationDecision:
    """Interpret one admitted turn into WHAT plus bounded next-cognition requests."""

    request.text = " ".join(request.text.strip().split())
    if not request.text:
        raise InterpretationUnavailableError("empty admitted input cannot be interpreted")
    return await user_meaning_interpreter.interpret_user_meaning(request)
