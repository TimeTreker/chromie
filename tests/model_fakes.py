"""Fake model clients shared by resolver tests.

Every fake records each call as ``(prompt, kwargs)`` in ``prompts``; ``calls``
counts them and ``prompt`` is the latest prompt text. An ``Exception`` reply is
raised instead of returned. ``shape`` optionally rewrites a reply for the
call's ``response_format`` (for example ``declared_ability_needs``).
"""

from __future__ import annotations

from typing import Any, Callable

Shape = Callable[[Any, Any], Any]


class _RecordingModel:
    def __init__(self, *, shape: Shape | None = None) -> None:
        self.shape = shape
        self.prompts: list[tuple[str, dict[str, Any]]] = []

    @property
    def calls(self) -> int:
        return len(self.prompts)

    @property
    def prompt(self) -> str:
        return str(self.prompts[-1][0]) if self.prompts else ""

    def _next_reply(self) -> Any:
        raise NotImplementedError

    async def generate(self, prompt: str, **kwargs: Any) -> Any:
        self.prompts.append((prompt, kwargs))
        reply = self._next_reply()
        if isinstance(reply, Exception):
            raise reply
        if self.shape is not None:
            return self.shape(reply, kwargs.get("response_format"))
        return reply


class FakeOllama(_RecordingModel):
    """Return (or raise) the same reply for every call."""

    def __init__(self, payload: Any, *, shape: Shape | None = None) -> None:
        super().__init__(shape=shape)
        self.payload = payload

    def _next_reply(self) -> Any:
        return self.payload


class ScriptedOllama(_RecordingModel):
    """Return (or raise) the scripted replies in order; an extra call fails the test."""

    def __init__(self, responses: list[Any], *, shape: Shape | None = None) -> None:
        super().__init__(shape=shape)
        self.responses = list(responses)

    def _next_reply(self) -> Any:
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        return self.responses.pop(0)
