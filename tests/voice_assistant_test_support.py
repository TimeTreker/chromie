"""Shared construction of a bare VoiceAssistant test double."""

from __future__ import annotations

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.input_turn_lifecycle import InputTurnLifecycle
from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle


def bare_voice_assistant() -> VoiceAssistant:
    """Return a VoiceAssistant built without ``__init__``.

    It carries only the two lifecycle collaborators that ``__init__`` always
    constructs; each test wires whatever else it exercises.
    """

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.input_turn_lifecycle = InputTurnLifecycle()
    assistant.playback_delivery = PlaybackDeliveryLifecycle()
    return assistant
