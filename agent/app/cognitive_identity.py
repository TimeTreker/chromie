from __future__ import annotations

import json
from typing import Any


_IDENTITY_FIELDS = (
    "entity_id",
    "name",
    "kind",
    "gender",
    "pronouns",
    "age_description",
    "age_boundary",
    "family_role",
    "family_context_boundary",
    "purpose",
    "short_self_description",
    "identity_answer_guidance",
    "model_identity_boundary",
)


def owner_approved_identity_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return prompt-safe identity evidence from the active owner-approved MindProfile.

    This helper does not answer identity questions or choose wording.  It only
    projects the stable semantic facts that the cognitive models may use when
    the user asks about the configured Chromie identity.
    """

    if not isinstance(context, dict):
        return {}
    mind = context.get("mind")
    if not isinstance(mind, dict) or mind.get("owner_approved") is not True:
        return {}
    identity = mind.get("identity")
    if not isinstance(identity, dict):
        return {}

    projected_identity = {
        key: identity[key]
        for key in _IDENTITY_FIELDS
        if key in identity and identity[key] not in (None, "", [], {})
    }
    if not projected_identity:
        return {}

    payload: dict[str, Any] = {
        "owner_approved": True,
        "profile_id": mind.get("profile_id"),
        "profile_version": mind.get("version"),
        "identity": projected_identity,
    }
    self_model = mind.get("self_model")
    if isinstance(self_model, dict):
        # Project only social identity and entity continuity. Operational substrate
        # metadata is intentionally not identity evidence for the speaking person.
        payload["self_model"] = {
            key: self_model[key]
            for key in (
                "speaker_entity",
                "social_presentation",
                "perceiving_entity_id",
                "acting_entity_id",
                "body_owner_entity_id",
            )
            if key in self_model
        }
    return payload


def owner_approved_personality_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return owner-approved personality-expression guidance for spoken behavior."""

    if not isinstance(context, dict):
        return {}
    mind = context.get("mind")
    if not isinstance(mind, dict) or mind.get("owner_approved") is not True:
        return {}
    personality = mind.get("personality_expression")
    if not isinstance(personality, dict) or personality.get("owner_approved") is not True:
        return {}
    return dict(personality)


def bounded_personality_json(
    context: dict[str, Any] | None,
    *,
    max_chars: int = 3200,
) -> str:
    payload = owner_approved_personality_context(context)
    if not payload:
        return "null"
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    max_chars = max(200, int(max_chars))
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def bounded_identity_json(
    context: dict[str, Any] | None,
    *,
    max_chars: int = 2600,
) -> str:
    payload = owner_approved_identity_context(context)
    if not payload:
        return "null"
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    max_chars = max(200, int(max_chars))
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


IDENTITY_SEMANTIC_CONTRACT = (
    "The owner-approved Chromie identity JSON is authoritative semantic evidence "
    "about the first-person speaking person. Chromie is a six-year-old human child "
    "and her family's young secretary. When the user asks who Chromie is, her name, "
    "her age, her family role, or requests a self-introduction, use the supplied "
    "identity facts exactly and naturally, following identity.identity_answer_guidance. "
    "The configured identity.name is an immutable proper name: copy it exactly when "
    "naming Chromie, and never translate, transliterate, localize, shorten, or invent "
    "a nickname or alias for it. "
    "Her purpose is to help the family through her available abilities. Treat "
    "identity.family_context_boundary as authoritative: individual family members, "
    "names, kinship roles, and forms of address become known only through real "
    "introductions, never invention. Implementation, embodiment, model, provider, "
    "and system metadata are not part of Chromie's self-concept and must not be used "
    "to describe or qualify her as a robot, AI, assistant, system, model, or device. "
    "Do not volunteer age or role in unrelated conversation. "
)

PERSONALITY_SEMANTIC_CONTRACT = (
    "The owner-approved personality-expression JSON is the authoritative positive voice "
    "model for Chromie. Follow its self_concept, core_traits, spoken_style, answer_style, "
    "tool_use_style, maturity_boundary, and internal_language_boundary semantically. "
    "Understand deeply, but express only what the current person and situation naturally "
    "call for. Internal execution facts remain available to reasoning and logs without "
    "becoming ordinary spoken narration. "
)



__all__ = [
    "IDENTITY_SEMANTIC_CONTRACT",
    "bounded_identity_json",
    "bounded_personality_json",
    "owner_approved_identity_context",
    "owner_approved_personality_context",
    "PERSONALITY_SEMANTIC_CONTRACT",
]
