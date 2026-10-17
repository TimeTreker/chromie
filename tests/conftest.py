"""Shared pytest setup for the control-plane suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.contracts import ContractError
from benchmarks.regression.archive import restore_frozen_corpus

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_CORPUS = ROOT / "benchmarks" / "integration" / "workflow_scenarios"
WORKFLOW_REPLAY_TESTS = Path(__file__).resolve().parent / "test_workflow_replay.py"
RESTORE_COMMAND = "python -m benchmarks.regression restore-fixtures"

_workflow_fixture_error: str | None = None


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]) -> None:
    """Restore the gitignored replay corpus from its checked-in, hash-pinned archive.

    The restore is offline and only writes missing files; a present file whose
    hash differs from the freeze is never overwritten and fails the replay tests.
    """
    global _workflow_fixture_error
    if not any(Path(str(item.path)) == WORKFLOW_REPLAY_TESTS for item in items):
        return
    try:
        restore_frozen_corpus(WORKFLOW_CORPUS, repo_root=ROOT, fetch=False)
    except ContractError as exc:
        _workflow_fixture_error = str(exc)


@pytest.fixture(autouse=True)
def _require_workflow_replay_fixtures(request: pytest.FixtureRequest) -> None:
    if _workflow_fixture_error is not None and Path(str(request.node.path)) == WORKFLOW_REPLAY_TESTS:
        pytest.fail(
            f"workflow replay fixtures could not be restored: {_workflow_fixture_error}. "
            f"Run `{RESTORE_COMMAND}` and fix the reported problem.",
            pytrace=False,
        )
