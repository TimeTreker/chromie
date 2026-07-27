from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_attention_review_imports_under_agent_container_package_layout(tmp_path: Path) -> None:
    """The Agent image exposes app and chromie_contracts as top-level packages."""

    (tmp_path / "app").symlink_to(PROJECT_ROOT / "agent" / "app", target_is_directory=True)
    (tmp_path / "chromie_contracts").symlink_to(
        PROJECT_ROOT / "shared" / "chromie_contracts",
        target_is_directory=True,
    )
    (tmp_path / "chromie_runtime").symlink_to(
        PROJECT_ROOT / "shared" / "chromie_runtime",
        target_is_directory=True,
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.cognitive_gateway.attention_review import AttentionReviewer; "
            "assert AttentionReviewer.__name__ == 'AttentionReviewer'",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
