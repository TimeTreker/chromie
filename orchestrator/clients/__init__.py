from __future__ import annotations

__all__ = ["AgentClient", "ActionClient", "ASRClient", "TTSClient"]


def __getattr__(name: str):
    if name == "AgentClient":
        from .agent_client import AgentClient

        return AgentClient
    if name == "ActionClient":
        from .action_client import ActionClient

        return ActionClient
    if name == "ASRClient":
        from .asr_client import ASRClient

        return ASRClient
    if name == "TTSClient":
        from .tts_client import TTSClient

        return TTSClient
    raise AttributeError(name)
