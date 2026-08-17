from __future__ import annotations


class InterpretationUnavailableError(RuntimeError):
    """Raised when Goal Interpretation cannot produce trusted WHAT evidence."""

    def __init__(self, reason: str) -> None:
        self.reason = " ".join(str(reason or "interpretation unavailable").split())
        super().__init__(self.reason)
