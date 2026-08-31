#!/usr/bin/env python3
"""Validate the Fast Planner corpus after its frozen manifest is completed."""

from __future__ import annotations

from .qualification import (
    DATASET_ROOT,
    load_cases,
    scenario_paths,
    scenario_tree_digest,
    validate_dataset,
)

__all__ = [
    "DATASET_ROOT",
    "load_cases",
    "scenario_paths",
    "scenario_tree_digest",
    "validate_dataset",
]


if __name__ == "__main__":
    import json

    print(json.dumps(validate_dataset(), ensure_ascii=False, indent=2, sort_keys=True))
