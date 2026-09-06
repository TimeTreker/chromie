from __future__ import annotations

import json

from agent.app.prompt_projection import bounded_json, required_json


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


def test_required_json_preserves_complete_authoritative_list() -> None:
    payload = [
        {"local_ref": f"r{index}", "outcome": "material semantic detail " * 10}
        for index in range(1, 9)
    ]

    rendered = required_json(payload, 16000, label="GI Responsibility evidence")

    assert json.loads(rendered) == payload
    assert '"local_ref":"r8"' in rendered


def test_required_json_fails_instead_of_truncating() -> None:
    payload = [{"local_ref": "r1", "outcome": "x" * 200}]

    try:
        required_json(payload, 80, label="GI Responsibility evidence")
    except ValueError as exc:
        assert "exceeds required prompt projection budget" in str(exc)
        assert "GI Responsibility evidence" in str(exc)
    else:
        raise AssertionError("required authoritative JSON must not be truncated")
