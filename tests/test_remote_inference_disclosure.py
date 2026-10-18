from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agent.app.remote_disclosure import (
    apply_remote_inference_disclosure,
    disclose_request_context,
    memory_entry_is_public,
)
from agent.app.settings import Settings
from shared.chromie_contracts.social_cognition import SocialCognitionRequest

PUBLIC = {"id": "mem_1", "kind": "fact", "text": "The kettle is in the kitchen", "disclosure_scope": "public"}
SELF = {"id": "mem_2", "kind": "self_note", "text": "I like the window seat", "disclosure_scope": "self_context"}
LEGACY = {"id": "mem_3", "kind": "note", "text": "Grandma visits on Sundays"}
RELATIONAL = {
    "id": "mem_4", "kind": "person_relationship", "text": "Lin is Mei's mother",
    "subject_refs": ["person:lin"], "disclosure_scope": "public",
}
AUDIENCE = {
    "id": "mem_5", "kind": "fact", "text": "The spare key is under the pot",
    "disclosure_scope": "shared_with_audience", "audience_refs": ["person:mei"],
}


def _context() -> dict:
    return {
        "mind": {"owner_approved": True},
        "session_memory": {
            "active_memory": {"entries": [PUBLIC, SELF, LEGACY, RELATIONAL, AUDIENCE]},
            "extracted_memory": [LEGACY, PUBLIC],
            "relational_memory": [RELATIONAL],
            "working_goal_memory": {"goals": []},
        },
    }


def test_remote_provider_requires_an_explicit_policy() -> None:
    with patch.dict(os.environ, {"AGENT_LLM_PROVIDER": "anthropic"}, clear=True):
        with pytest.raises(ValueError, match="AGENT_REMOTE_INFERENCE_DISCLOSURE"):
            Settings()
    with patch.dict(os.environ, {"AGENT_LLM_PROVIDER": "openai", "AGENT_OPENAI_MODEL": "gpt-5"}, clear=True):
        with pytest.raises(ValueError, match="AGENT_REMOTE_INFERENCE_DISCLOSURE"):
            Settings()
    with patch.dict(
        os.environ, {"AGENT_LLM_PROVIDER": "anthropic", "AGENT_REMOTE_INFERENCE_DISCLOSURE": "public_only"}, clear=True,
    ):
        settings = Settings()
        assert settings.remote_inference and settings.remote_inference_disclosure == "public_only"
    # Local providers never need the key and ignore it.
    with patch.dict(os.environ, {"AGENT_LLM_PROVIDER": "sglang"}, clear=True):
        assert not Settings().remote_inference
    with patch.dict(os.environ, {}, clear=True):
        assert Settings().remote_inference_disclosure == ""


def test_public_only_keeps_explicitly_public_non_relational_memory() -> None:
    assert memory_entry_is_public(PUBLIC) and memory_entry_is_public(SELF)
    assert not memory_entry_is_public(LEGACY)  # unclassified is not public
    assert not memory_entry_is_public(RELATIONAL)  # people and relationships never leave
    assert not memory_entry_is_public(AUDIENCE)
    assert not memory_entry_is_public({**PUBLIC, "audience_refs": ["person:mei"]})
    assert not memory_entry_is_public("not an entry")


def test_public_only_projects_every_memory_list_and_leaves_the_rest() -> None:
    context = _context()
    projected = apply_remote_inference_disclosure(context, policy="public_only", purpose="fast_planner")
    memory = projected["session_memory"]
    assert memory["active_memory"]["entries"] == [PUBLIC, SELF]
    assert memory["extracted_memory"] == [PUBLIC]
    assert memory["relational_memory"] == []
    assert memory["working_goal_memory"] == {"goals": []}
    assert projected["mind"] == {"owner_approved": True}
    # The caller's context is untouched.
    assert len(context["session_memory"]["active_memory"]["entries"]) == 5


def test_full_policy_returns_the_same_context() -> None:
    context = _context()
    assert apply_remote_inference_disclosure(context, policy="full", purpose="fast_planner") is context
    with pytest.raises(ValueError, match="disclosure policy"):
        apply_remote_inference_disclosure(context, policy="", purpose="fast_planner")  # type: ignore[arg-type]


def test_request_projection_keeps_the_request_type_and_other_fields() -> None:
    request = SocialCognitionRequest(
        request_id="req-1", trigger="work_state", source_refs=["work:1"], goal_ids=["goal:1"],
        context={**_context(), "work": [{"id": "work:1", "status": "running"}],
                 "active_goal_snapshots": [{"goal_id": "goal:1", "status": "active"}]},
    )
    projected = disclose_request_context(request, policy="public_only", purpose="social_cognition")
    assert isinstance(projected, SocialCognitionRequest)
    assert projected.request_id == "req-1"
    assert projected.context["session_memory"]["active_memory"]["entries"] == [PUBLIC, SELF]
    assert disclose_request_context(request, policy="full", purpose="social_cognition") is request
    without_memory = request.model_copy(update={"context": {"work": request.context["work"]}})
    assert disclose_request_context(without_memory, policy="public_only", purpose="social_cognition") is without_memory
