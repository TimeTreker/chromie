#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "shared"))

from app.agent_skills import compute_agent_skill_content_digest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute the deterministic content_digest for one Agent Skill package."
    )
    parser.add_argument("package", help="package directory containing SKILL.md")
    args = parser.parse_args()
    print(compute_agent_skill_content_digest(Path(args.package)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
