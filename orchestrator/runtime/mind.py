from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shared.chromie_contracts.mind import (
    MindProfile,
    SocialInteractionStyle,
    active_customer_mind_profile_path,
    default_mind_profile,
    default_mind_profile_path,
    load_mind_profile,
    validate_customer_mind_profile,
)

if TYPE_CHECKING:
    from orchestrator.runtime.host_settings import MindSettings


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
    def from_settings(cls, settings: "MindSettings") -> "MindManager":
        profile = cls._load_profile(settings.profile_path)
        if settings.social_style_preset:
            profile = profile.model_copy(
                update={
                    "social_interaction_style": SocialInteractionStyle(
                        preset=settings.social_style_preset
                    )
                }
            )
        return cls(
            profile,
            profile_path=settings.profile_path,
            context_max_chars=settings.context_max_chars,
        )

    @classmethod
    def from_env(cls, *, project_root: Path | None = None) -> "MindManager":
        raw_path = os.getenv("ORCH_MIND_PROFILE_PATH", "").strip()
        if raw_path:
            profile_path = Path(raw_path).expanduser()
            if not profile_path.is_absolute() and project_root is not None:
                profile_path = project_root / profile_path
        else:
            customer_path = (
                active_customer_mind_profile_path(project_root)
                if project_root is not None
                else None
            )
            profile_path = (
                customer_path
                if customer_path is not None and customer_path.is_file()
                else default_mind_profile_path(project_root)
            )
        profile = cls._load_profile(profile_path)
        social_style_preset = os.getenv("ORCH_SOCIAL_INTERACTION_STYLE_PRESET", "").strip().lower()
        if social_style_preset:
            profile = profile.model_copy(
                update={
                    "social_interaction_style": SocialInteractionStyle(
                        preset=social_style_preset
                    )
                }
            )
        return cls(
            profile,
            profile_path=profile_path,
            context_max_chars=int(os.getenv("ORCH_MIND_CONTEXT_MAX_CHARS", "1600")),
        )

    @staticmethod
    def _load_profile(path: Path | None) -> MindProfile:
        if path is None:
            return default_mind_profile()
        profile = load_mind_profile(path)
        if profile.customer_personalization is not None:
            validate_customer_mind_profile(profile, default_mind_profile())
        return profile

    def context(self) -> dict[str, Any]:
        context = self.profile.prompt_context(max_chars=self.context_max_chars)
        if self.profile_path is not None:
            context["profile_path"] = str(self.profile_path)
        return context

    def prompt_summary(self) -> str:
        return self.profile.prompt_summary(max_chars=self.context_max_chars)
