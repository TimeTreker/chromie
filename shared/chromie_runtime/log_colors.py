from __future__ import annotations

import logging
import sys

from .settings import RuntimePolicySettings


def colorize_for_cli(
    line: str,
    level: int,
    *,
    env_var: str = "CHROMIE_CLI_COLOR",
    fallback_env_var: str | None = "ORCH_CLI_COLOR",
    accent: str | None = None,
) -> str:
    """Return ``line`` wrapped in ANSI color when terminal color is enabled.

    The helper is intentionally tiny and dependency-free so Agent and
    Orchestrator can share the same semantics without adding color libraries.
    It respects ``NO_COLOR`` and only auto-colors attached terminals unless the
    selected env var is forced on.
    """

    settings = RuntimePolicySettings.from_env()
    raw_mode = settings.color_value(env_var, fallback_env_var)
    color_mode = (raw_mode or "auto").strip().lower()
    if color_mode in {"0", "false", "no", "off", "never"}:
        return line
    color_forced = color_mode in {"1", "true", "yes", "on", "always"}
    if not color_forced and settings.environment.get("NO_COLOR"):
        return line
    if not color_forced:
        if not sys.stderr.isatty() or str(settings.environment.get("TERM", "")).lower() == "dumb":
            return line
    if level >= logging.ERROR:
        return f"\033[31m{line}\033[0m"
    if level >= logging.WARNING:
        return f"\033[33m{line}\033[0m"
    accent_codes = {
        "green": "32",
        "cyan": "36",
        "blue": "34",
        "magenta": "35",
        "yellow": "33",
        "red": "31",
    }
    accent_code = accent_codes.get(str(accent or "").strip().casefold())
    if accent_code:
        return f"\033[{accent_code}m{line}\033[0m"
    return line
