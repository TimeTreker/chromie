from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from shared.chromie_runtime.atomic_files import (
    atomic_write_json,
    atomic_write_text,
    json_document_bytes,
)


def test_json_document_is_sorted_indented_and_newline_terminated() -> None:
    assert json_document_bytes({"b": 1, "a": "é"}) == (
        '{\n  "a": "é",\n  "b": 1\n}\n'.encode("utf-8")
    )


def test_atomic_write_replaces_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.json"
    atomic_write_json(target, {"value": 1})
    atomic_write_json(target, {"value": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"value": 2}
    assert sorted(path.name for path in target.parent.iterdir()) == ["report.json"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_atomic_write_applies_requested_mode(tmp_path: Path) -> None:
    target = tmp_path / "memory.json"
    atomic_write_text(target, "{}\n", mode=0o600)

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_failed_write_keeps_previous_content(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write_json(target, {"value": 1})

    with pytest.raises(TypeError):
        atomic_write_json(target, {"value": object()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"value": 1}
    assert sorted(path.name for path in tmp_path.iterdir()) == ["state.json"]
