from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts import evidence_io


def test_write_and_read_json_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.json"
    evidence_io.write_json(target, {"b": 1, "a": "é"})

    assert target.read_text(encoding="utf-8") == '{\n  "a": "é",\n  "b": 1\n}\n'
    assert evidence_io.read_json_object(target) == {"a": "é", "b": 1}
    assert [path.name for path in target.parent.iterdir()] == ["report.json"]


def test_read_json_object_rejects_non_objects(tmp_path: Path) -> None:
    target = tmp_path / "list.json"
    target.write_text("[1]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        evidence_io.read_json_object(target)


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"chromie")
    assert evidence_io.sha256_file(target) == hashlib.sha256(b"chromie").hexdigest()


def test_run_id_is_a_compact_utc_timestamp() -> None:
    assert re.fullmatch(r"\d{8}T\d{6}Z", evidence_io.run_id())


def test_scenario_turns_requires_exactly_one_input_shape() -> None:
    assert evidence_io.scenario_turns({"text": " hi "}) == ["hi"]
    assert evidence_io.scenario_turns({"turns": [" a", "b "]}) == ["a", "b"]
    for inputs in ({}, {"text": "hi", "turns": ["a"]}, {"turns": ["a", " "]}, {"text": " "}):
        with pytest.raises(ValueError, match="either non-empty text or non-empty turns"):
            evidence_io.scenario_turns(inputs)


def test_git_revision_is_none_outside_a_checkout(tmp_path: Path) -> None:
    assert evidence_io.git_revision(tmp_path) is None
    with mock.patch.object(evidence_io.subprocess, "check_output", side_effect=FileNotFoundError("git")):
        assert evidence_io.git_revision() is None


def test_git_revision_does_not_hide_unexpected_failures() -> None:
    with mock.patch.object(evidence_io.subprocess, "check_output", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            evidence_io.git_revision()


def test_git_state_reports_revision_and_dirty_flag(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    clean = evidence_io.git_state(tmp_path)
    assert clean["dirty"] is False
    assert clean["revision"] == evidence_io.git_revision(tmp_path)
    (tmp_path / "new.txt").write_text("x", encoding="utf-8")
    assert evidence_io.git_state(tmp_path)["dirty"] is True
