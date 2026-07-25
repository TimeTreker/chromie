from __future__ import annotations

import os


def router_mode_from_env() -> str:
    explicit_mode = os.getenv("ROUTER_MODE")
    if explicit_mode:
        return explicit_mode.strip().lower()

    use_llm = os.getenv("ROUTER_USE_LLM", "0").strip().lower() not in {"0", "false", "no", "off"}
    return "hybrid" if use_llm else "rules_only"
