from __future__ import annotations

import os


def goal_interpretation_mode_from_env() -> str:
    explicit_mode = os.getenv("AGENT_GOAL_INTERPRETER_MODE")
    if explicit_mode:
        return explicit_mode.strip().lower()

    use_llm = os.getenv("AGENT_GOAL_INTERPRETER_USE_LLM", "0").strip().lower() not in {"0", "false", "no", "off"}
    return "hybrid" if use_llm else "rules_only"
