from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...settings import (
    GoalInterpreterSettings as Settings,
    goal_interpreter_settings as settings,
)
from .errors import InterpretationUnavailableError
from .model_interpreter import OllamaGoalInterpreter
from .schema import GoalInterpretationDecision, GoalInterpretationRequest


logger = logging.getLogger("chromie.agent.goal_interpreter")


goal_interpreter = OllamaGoalInterpreter(
    ollama_url=settings.ollama_url,
    model=settings.model,
    timeout_ms=settings.timeout_ms,
    num_ctx=settings.llm_num_ctx,
    num_predict=settings.llm_num_predict,
    keep_alive=settings.llm_keep_alive,
    prompt_path=Path(__file__).parent / "prompts" / "goal_interpreter_system.txt",
)


async def initialize_goal_interpreter() -> None:
    """Warm the WHAT-only model when configured.

    Goal Interpretation intentionally does not initialize or query Capability
    Catalog state. Capability availability belongs to Planner/Capability Runtime.
    """

    if not settings.warm_llm_on_startup:
        return
    try:
        await goal_interpreter.warm_model(
            timeout_s=max(0.1, settings.warm_llm_timeout_ms / 1000.0)
        )
    except Exception as exc:
        logger.warning(
            "Goal Interpreter LLM startup warm failed: model=%s error_type=%s error=%s",
            settings.model,
            type(exc).__name__,
            exc,
        )
    else:
        logger.info(
            "Goal Interpreter LLM startup warm succeeded: model=%s keep_alive=%s",
            settings.model,
            settings.llm_keep_alive or "default",
        )


def interpretation_profile() -> dict[str, Any]:
    """Describe the maintained Goal Interpretation authority."""

    return {
        "authority": "what_only",
        "model": settings.model,
        "output": ["responsibilities", "confidence", "unresolved"],
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


async def interpret_goal(
    request: GoalInterpretationRequest,
) -> GoalInterpretationDecision:
    """Interpret one already-admitted turn into provider-neutral WHAT evidence."""

    request.text = " ".join(request.text.strip().split())
    if not request.text:
        raise InterpretationUnavailableError("empty admitted input cannot be interpreted")
    return await goal_interpreter.interpret_goal(request)
