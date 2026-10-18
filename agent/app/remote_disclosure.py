"""Disclosure policy for cognitive context that leaves the device.

A remote provider (``AGENT_LLM_PROVIDER=anthropic`` or ``openai``) receives the
same role prompts as the local engine. Memory already filters by audience before
it reaches any prompt; this module applies the operator's remote policy on top,
at the Agent's HTTP ingress, so every role sees the same projection.

``full`` sends the context unchanged. ``public_only`` withholds Memory the
household has not explicitly marked public: every relational entry (people,
relationships, shared experiences, boundaries) and every entry whose
``disclosure_scope`` is not ``public`` or ``self_context``. Nothing here reads
raw stores, rewrites meaning, or fills in what it removed; the roles reason over
less, and record that they did.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

logger = logging.getLogger("chromie.agent.remote_disclosure")

RemoteInferenceDisclosure = Literal["", "full", "public_only"]

# Mirrors orchestrator/runtime/memory.py: the kinds Memory treats as relational.
RELATIONAL_MEMORY_KINDS = frozenset({
    "person_identity",
    "person_relationship",
    "shared_experience",
    "relationship_interpretation",
    "interaction_boundary",
})
PUBLIC_DISCLOSURE_SCOPES = frozenset({"public", "self_context"})
# Lists under session_memory that carry whole Memory entries toward a prompt.
_MEMORY_ENTRY_LISTS = ("extracted_memory", "memory_entries", "relational_memory")

_RequestT = TypeVar("_RequestT", bound=BaseModel)


def memory_entry_is_public(entry: Any) -> bool:
    """One entry the operator's ``public_only`` policy lets a remote model see."""

    if not isinstance(entry, dict):
        return False
    if str(entry.get("kind") or "note").strip().casefold() in RELATIONAL_MEMORY_KINDS:
        return False
    if entry.get("relation") or entry.get("subject_refs") or entry.get("source_person_refs") or entry.get("audience_refs"):
        return False
    return str(entry.get("disclosure_scope") or "").strip() in PUBLIC_DISCLOSURE_SCOPES


def apply_remote_inference_disclosure(
    context: dict[str, Any], *, policy: RemoteInferenceDisclosure, purpose: str,
) -> dict[str, Any]:
    """Return the context a remote provider may be shown under ``policy``."""

    if policy == "full":
        return context
    if policy != "public_only":
        raise ValueError(f"unsupported remote inference disclosure policy: {policy!r}")
    memory = context.get("session_memory")
    if not isinstance(memory, dict):
        return context
    projected = dict(context)
    memory = copy.deepcopy(memory)
    projected["session_memory"] = memory
    withheld = 0
    active = memory.get("active_memory")
    if isinstance(active, dict) and isinstance(active.get("entries"), list):
        kept = [entry for entry in active["entries"] if memory_entry_is_public(entry)]
        withheld += len(active["entries"]) - len(kept)
        active["entries"] = kept
    for key in _MEMORY_ENTRY_LISTS:
        entries = memory.get(key)
        if isinstance(entries, list):
            kept = [entry for entry in entries if memory_entry_is_public(entry)]
            withheld += len(entries) - len(kept)
            memory[key] = kept
    if withheld:
        logger.info(
            "remote_inference_disclosure purpose=%s policy=%s withheld_memory_entries=%s",
            purpose, policy, withheld,
        )
    return projected


def disclose_request_context(
    request: _RequestT, *, policy: RemoteInferenceDisclosure, purpose: str,
) -> _RequestT:
    """Apply the policy to a cognitive request's ``context`` without re-validating it."""

    context = getattr(request, "context", None)
    if not isinstance(context, dict):
        return request
    projected = apply_remote_inference_disclosure(context, policy=policy, purpose=purpose)
    if projected is context:
        return request
    return request.model_copy(update={"context": projected})
