from __future__ import annotations

import json

from agent.app.prompt_projection import bounded_json


def test_bounded_json_never_slices_object_syntax() -> None:
    payload = {
        "first": "x" * 500,
        "second": {"kept": True},
        "third": [1, 2, 3],
    }

    rendered = bounded_json(payload, 80)

    decoded = json.loads(rendered)
    assert isinstance(decoded, dict)
    assert len(rendered) <= 80
    assert not rendered.endswith("...")
    assert "second" in decoded or "third" in decoded


def test_bounded_json_keeps_only_complete_list_items() -> None:
    payload = [
        {"index": 1, "text": "short"},
        {"index": 2, "text": "y" * 200},
        {"index": 3, "text": "later"},
    ]

    rendered = bounded_json(payload, 70)

    decoded = json.loads(rendered)
    assert decoded == [{"index": 1, "text": "short"}]
    assert len(rendered) <= 70


def test_bounded_json_truncates_scalar_then_reencodes_it() -> None:
    rendered = bounded_json('quoted " text ' * 100, 48)

    decoded = json.loads(rendered)
    assert isinstance(decoded, str)
    assert len(rendered) <= 48
