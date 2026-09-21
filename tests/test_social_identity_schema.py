"""SC identity survives native decoding and repeated delivery receipts."""

import itertools
import json
import re

import pytest
from jsonschema import Draft202012Validator

from agent.app.social_cognition import social_cognition_response_schema
from tests.test_social_cognition import request, response


@pytest.mark.parametrize("delivered_turn,expected", [("turn:current", True), ("turn:old", False), (None, False)])
def test_need_accounting_projection_uses_user_turn_identity_not_invocation_order(delivered_turn, expected):
    from agent.app.social_cognition import social_cognition_prompt
    from shared.chromie_contracts.social_cognition import SocialCommunicationNeed
    current = request(
        source_turn={"turn_id": "turn:current"},
        communication_needs=[SocialCommunicationNeed(need_id="need:answer", owner="planner", kind="answer",
                                                     reference_id="plan:1", source_goal_ids=["goal:1"])],
        context={"interaction_context": {"already_spoken": [
            {"turn_id": delivered_turn, "text": "Previously delivered.",
             "metadata": {"communicative_activity_ids": ["act:answer"]}},
        ]}},
    )
    before = current.model_dump(mode="json")
    prompt = social_cognition_prompt(current, [], num_ctx=8192)
    cue = json.loads(prompt.split("Immediate interaction opportunity:\n", 1)[1]
                     .split("\nTrusted interaction snapshot:\n", 1)[0])
    assert cue["need_accounting"] == {"current_turn_id": "turn:current", "supplied_need_count": 1,
                                      "same_turn_delivery_present": expected}
    assert current.model_dump(mode="json") == before


@pytest.mark.parametrize("known", [
    ["rain_info_001", "weather_ack_001"],
    ["a", "aa", "ab", "b.a", "[id]", "中文"],
])
def test_native_identity_exclusion_preserves_safe_fresh_and_retained_spellings(known):
    current = request(context={"interaction_context": {"already_spoken": [
        {"text": "Previously delivered.", "metadata": {"communicative_activity_ids": [identity]}}
        for identity in known
    ]}})
    schema = social_cognition_response_schema(current, [])
    fresh = schema["$defs"]["SocialCommunicativeAct"]["oneOf"][0]["properties"]["activity_id"]
    pattern = re.compile(fresh["pattern"])
    contrasts = known + ["fresh", "rain_info_002", "[new]", "另一条"]
    contrasts += ["".join(chars) for size in range(1, 5)
                  for chars in itertools.product("ab.", repeat=size)]
    for identity in contrasts:
        assert bool(pattern.fullmatch(identity)) == (identity not in known)
    for identity in ['fresh"x', 'fresh\\x', 'fresh\nx', 'fresh\x00x']:
        assert not pattern.fullmatch(identity)
    validator = Draft202012Validator(schema)
    for identity in known:
        assert validator.is_valid(response(activity_id=identity, text="Previously delivered."))
        assert not validator.is_valid(response(activity_id=identity, text="Different words."))
    assert validator.is_valid(response(activity_id="fresh", text="Different words."))


def _delivered_metadata(**changes):
    return {"wording_owner": "social_cognition", "playback_completed": True,
            "turn_id": "turn:1", "communicative_activity_ids": ["act:1"], **changes}


def test_reused_delivery_enriches_history_without_repeating_console_reply():
    from types import SimpleNamespace
    from orchestrator.runtime.conversation_state import ConversationStateManager
    from scripts.chromie_psm_live_text_console import _publish_history_delta

    state = ConversationStateManager(base_conversation_id="reuse")
    assistant = SimpleNamespace(conversation_state=state)
    spoken = []
    state.record_assistant_turn("sid", "The answer.", metadata=_delivered_metadata())
    before = _publish_history_delta(assistant, [], spoken.append)
    original = before[0]
    state.record_assistant_turn("sid", "The answer.", metadata=_delivered_metadata(
        addressed_need_ids=["need:1"], evidence_bound=True, evidence_refs=["evidence:1"],
    ))
    after = _publish_history_delta(assistant, before, spoken.append)
    assert spoken == ["The answer."]
    assert after == [original]
    assert after[0]["metadata"]["addressed_need_ids"] == ["need:1"]
    assert after[0]["metadata"]["evidence_bound"] is True


@pytest.mark.parametrize("sid,changes", [
    ("other-sid", {}), ("sid", {"turn_id": "turn:2"}),
    ("sid", {"communicative_activity_ids": ["distinct-repeat"]}),
    ("sid", {"communicative_activity_ids": []}),
])
def test_distinct_or_unproven_speech_is_not_collapsed_by_word_similarity(sid, changes):
    from orchestrator.runtime.conversation_state import ConversationStateManager
    state = ConversationStateManager(base_conversation_id="distinct")
    state.record_assistant_turn("sid", "The answer.", metadata=_delivered_metadata())
    state.record_assistant_turn(sid, "The answer.", metadata=_delivered_metadata(**changes))
    assert len(state.get_history()) == 2


def test_reused_delivery_cannot_replace_words_in_history():
    from orchestrator.runtime.conversation_state import ConversationStateManager
    state = ConversationStateManager(base_conversation_id="immutable")
    state.record_assistant_turn("sid", "Original.", metadata=_delivered_metadata())
    with pytest.raises(ValueError, match="wording cannot change"):
        state.record_assistant_turn("sid", "Different.", metadata=_delivered_metadata())
    assert [row["text"] for row in state.get_history()] == ["Original."]
