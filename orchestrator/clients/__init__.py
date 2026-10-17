from __future__ import annotations

__all__ = ["AgentClient", "ASRClient", "TTSClient"]


def __getattr__(name: str):
    if name == "AgentClient":
        from .agent_client import AgentClient

        return AgentClient
    if name == "ASRClient":
        from .asr_client import ASRClient

        return ASRClient
    if name == "TTSClient":
        from .tts_client import TTSClient

        return TTSClient
    raise AttributeError(name)
