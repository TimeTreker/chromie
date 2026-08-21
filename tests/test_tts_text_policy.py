from __future__ import annotations

from orchestrator.runtime.tts_text import (
    ends_with_tts_natural_boundary,
    ends_with_tts_sentence_boundary,
    should_merge_tts_chunks,
    split_oversized_tts_unit,
    split_tts_clause_units,
    split_tts_sentence_units,
)


def test_sentence_units_preserve_cjk_sentence_boundaries() -> None:
    assert split_tts_sentence_units("你好。今天怎么样？我很好！") == [
        "你好。",
        "今天怎么样？",
        "我很好！",
    ]


def test_clause_split_does_not_break_quoted_material() -> None:
    text = 'She said "alpha, beta", and then continued, with enough trailing text.'
    chunks = split_tts_clause_units(text, min_chars=8, trigger_chars=20)
    assert '"alpha, beta"' in chunks[0]
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_oversized_unit_prefers_natural_cut_before_hard_limit() -> None:
    chunks = split_oversized_tts_unit(
        "alpha beta gamma delta epsilon zeta eta theta iota",
        24,
    )
    assert len(chunks) > 1
    assert all(len(chunk) <= 24 for chunk in chunks)


def test_merge_policy_respects_boundaries_and_hard_limit() -> None:
    assert ends_with_tts_sentence_boundary("Done。") is True
    assert ends_with_tts_natural_boundary("continuing,") is True
    assert should_merge_tts_chunks(
        "short",
        "continuation",
        limit=30,
        hard_limit=40,
        min_chars=10,
    ) is True
    assert should_merge_tts_chunks(
        "already long enough.",
        "another long sentence",
        limit=30,
        hard_limit=30,
        min_chars=10,
    ) is False
