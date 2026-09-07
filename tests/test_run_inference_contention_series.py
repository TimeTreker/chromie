from __future__ import annotations

import pytest

from scripts.run_inference_contention_series import _normalize_forwarded_args


def test_series_requires_contention_only_and_strips_separator() -> None:
    args = _normalize_forwarded_args(
        ["--", "--provider", "sglang", "--contention-only", "--model", "candidate"]
    )

    assert args[0:2] == ["--provider", "sglang"]
    assert "--contention-only" in args


def test_series_rejects_caller_owned_output() -> None:
    with pytest.raises(ValueError, match="owns trial output paths"):
        _normalize_forwarded_args(
            ["--provider", "sglang", "--contention-only", "--output", "wrong.json"]
        )


def test_series_rejects_non_comparable_full_provider_contract() -> None:
    with pytest.raises(ValueError, match="require --contention-only"):
        _normalize_forwarded_args(["--provider", "sglang"])


def test_series_rejects_semantic_probe_mixed_into_latency_distribution() -> None:
    with pytest.raises(ValueError, match="goal-interpreter-probe"):
        _normalize_forwarded_args(
            ["--provider", "sglang", "--contention-only", "--goal-interpreter-probe"]
        )
