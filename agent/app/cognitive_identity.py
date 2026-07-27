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
    "short_self_description",
    "identity_answer_guidance",
)


def owner_approved_identity_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return prompt-safe identity evidence from the active owner-approved MindProfile.

    This helper does not answer identity questions or choose wording.  It only
    projects the stable semantic facts that the cognitive models may use when
    the user asks about the configured robot identity.
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
        payload["self_model"] = self_model
    return payload


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
    "The owner-approved robot identity JSON is authoritative semantic evidence "
    "about the first-person speaking entity. When the user asks who the robot is, "
    "its name, its age, or requests a self-introduction, use the supplied identity "
    "facts exactly and naturally, following identity.identity_answer_guidance and "
    "using identity.name and identity.age_description when that guidance calls for them. Do not substitute a "
    "generic AI-assistant description or treat an internal language/reasoning model "
    "as the speaker. Do not volunteer age or internal architecture in unrelated "
    "conversation. "
)


__all__ = [
    "IDENTITY_SEMANTIC_CONTRACT",
    "bounded_identity_json",
    "owner_approved_identity_context",
]
