from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from shared.chromie_contracts.mind import MindProfile, default_mind_profile


class MindManager:
    """Runtime access to Chromie's owner-approved mind profile."""

    def __init__(
        self,
        profile: MindProfile | None = None,
        *,
        profile_path: Path | None = None,
        context_max_chars: int = 1600,
    ) -> None:
        self.profile = profile or default_mind_profile()
        self.profile_path = profile_path
        self.context_max_chars = max(400, int(context_max_chars))

    @classmethod
    def from_env(cls, *, project_root: Path | None = None) -> "MindManager":
        raw_path = os.getenv("ORCH_MIND_PROFILE_PATH", "").strip()
        profile_path = Path(raw_path).expanduser() if raw_path else None
        if profile_path and not profile_path.is_absolute() and project_root is not None:
            profile_path = project_root / profile_path
        profile = cls._load_profile(profile_path) if profile_path else default_mind_profile()
        return cls(
            profile,
            profile_path=profile_path,
            context_max_chars=int(os.getenv("ORCH_MIND_CONTEXT_MAX_CHARS", "1600")),
        )

    @staticmethod
    def _load_profile(path: Path | None) -> MindProfile:
        if path is None:
            return default_mind_profile()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"mind profile {path} must contain a JSON object")
        return MindProfile.model_validate(payload)

    def context(self) -> dict[str, Any]:
        context = self.profile.prompt_context(max_chars=self.context_max_chars)
        if self.profile_path is not None:
            context["profile_path"] = str(self.profile_path)
        return context

    def prompt_summary(self) -> str:
        return self.profile.prompt_summary(max_chars=self.context_max_chars)
