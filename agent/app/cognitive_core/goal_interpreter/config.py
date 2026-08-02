from __future__ import annotations

from ...settings import GoalInterpreterSettings


def goal_interpretation_mode_from_env() -> str:
    """Compatibility factory; maintained startup uses the shared typed snapshot."""
    return GoalInterpreterSettings().mode
