from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.runtime.journal_io import append_jsonl, float_or_none
from shared.chromie_contracts.text import (
    compact_text,
    normalize_unique_text_list,
    require_identifier,
    split_comma_separated,
)


def test_compact_text_collapses_whitespace_and_marks_cuts() -> None:
    assert compact_text("  a \n b  ", limit=10) == "a b"
    assert compact_text("abcdef ghij", limit=7) == "abcdef..."
    assert compact_text("", limit=3) == ""


def test_require_identifier_strips_and_rejects_blank() -> None:
    assert require_identifier("  weather.read ") == "weather.read"
    with pytest.raises(ValueError, match="identifier must not be empty"):
        require_identifier("   ")


def test_split_comma_separated_drops_blank_items() -> None:
    assert split_comma_separated(None) == []
    assert split_comma_separated(" one.json, ,two.json ") == ["one.json", "two.json"]


def test_normalize_unique_text_list_keeps_first_seen_order() -> None:
    assert normalize_unique_text_list(["b", " a ", "b", ""]) == ["b", "a"]
    assert normalize_unique_text_list("x") == ["x"]
    with pytest.raises(ValueError):
        normalize_unique_text_list(3)


def test_journal_helpers(tmp_path: Path) -> None:
    path = tmp_path / "journal" / "log.jsonl"
    append_jsonl(path, {"b": 1, "a": "é"})
    append_jsonl(path, {"c": 2})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"a": "é", "b": 1}, {"c": 2}]
    assert float_or_none("1.5") == 1.5
    assert float_or_none(None) is None
    assert float_or_none("nope") is None
