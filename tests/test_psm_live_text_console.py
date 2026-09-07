from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import chromie_psm_live_text_console as console


ROOT = Path(__file__).resolve().parents[1]


def test_console_defaults_to_no_speaker_and_no_capabilities() -> None:
    args = console.build_parser().parse_args([])

    assert args.speaker is False
    assert args.capabilities is False
    assert args.language == "auto"


def test_console_parses_manual_trusted_source_options() -> None:
    assert console._csv("person:dad,self:chromie") == [
        "person:dad",
        "self:chromie",
    ]
    assert console._kv_options(
        ["identity=resolved", "confidence=0.95", "audience=person:dad,self:chromie"]
    ) == {
        "identity": "resolved",
        "confidence": "0.95",
        "audience": "person:dad,self:chromie",
    }


@pytest.mark.parametrize("value", ["missing", "=value"])
def test_console_rejects_malformed_key_value_options(value: str) -> None:
    with pytest.raises(ValueError):
        console._kv_options([value])


def test_console_accepts_explicit_chromie_repo_root() -> None:
    assert console._discover_repo_root(ROOT) == ROOT


def test_feedback_default_targets_latest_delivered_activity() -> None:
    context = SimpleNamespace(
        model_dump=lambda mode="json": {
            "already_spoken": [
                {
                    "text": "第一句",
                    "metadata": {"communicative_activity_ids": ["activity-1"]},
                },
                {
                    "text": "第二句",
                    "metadata": {
                        "communicative_activity_ids": ["activity-2", "activity-3"]
                    },
                },
            ]
        }
    )
    ledger = SimpleNamespace(context=lambda *_args, **_kwargs: context)
    assistant = SimpleNamespace(
        cognitive_runtime=SimpleNamespace(interaction_ledger=ledger),
        session_id="sid-test",
    )

    assert console._latest_delivered_activity_id(assistant, "sid-test") == "activity-3"
