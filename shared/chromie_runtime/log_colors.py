from __future__ import annotations

import logging
import os
import sys


def colorize_for_cli(
    line: str,
    level: int,
    *,
    env_var: str = "CHROMIE_CLI_COLOR",
    fallback_env_var: str | None = "ORCH_CLI_COLOR",
) -> str:
    """Return ``line`` wrapped in ANSI color when terminal color is enabled.

    The helper is intentionally tiny and dependency-free so Router, Agent, and
    Orchestrator can share the same semantics without adding color libraries.
    It respects ``NO_COLOR`` and only auto-colors attached terminals unless the
    selected env var is forced on.
    """

    raw_mode = os.getenv(env_var)
    if raw_mode is None and fallback_env_var:
        raw_mode = os.getenv(fallback_env_var)
    color_mode = (raw_mode or "auto").strip().lower()
    if color_mode in {"0", "false", "no", "off", "never"}:
        return line
    color_forced = color_mode in {"1", "true", "yes", "on", "always"}
    if not color_forced and os.getenv("NO_COLOR"):
        return line
    if not color_forced:
        if not sys.stderr.isatty() or os.getenv("TERM", "").lower() == "dumb":
            return line
    if level >= logging.ERROR:
        return f"\033[31m{line}\033[0m"
    if level >= logging.WARNING:
        return f"\033[33m{line}\033[0m"
    return line
