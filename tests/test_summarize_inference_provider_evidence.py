from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.summarize_inference_provider_evidence import build_summary


def _sample(*, index: int, provider: str = "sglang", planner_before_deep: bool = True) -> dict:
    fast_start = float(index * 10)
    planner_finish = fast_start + 0.4 + index * 0.01
    deep_finish = planner_finish + 1.0 if planner_before_deep else planner_finish - 0.1
    return {
        "schema_version": 2,
        "provider": provider,
        "provider_version": "0.5.19",
        "qualification_mode": "contention_control",
        "runtime_image": "lmsysorg/sglang:v0.5.19-cu130@sha256:test",
        "cuda_runtime": "13.0",
        "accelerator_identity": {
            "status": "observed",
            "devices": [{"name": "RTX 5090", "uuid": "GPU-test", "driver_version": "test"}],
        },
        "model": "Qwen/Qwen3.5-9B",
        "model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "base_url": "http://127.0.0.1:30000/v1",
        "git_revision": "abc123",
        "git_dirty": False,
        "status": "pass",
        "scheduler_config": {
            "operator_record": {"context_length": 32768},
            "provider_priority_semantics": "larger_value_first",
        },
        "workload_config": {
            "contention_protocol_version": 1,
            "contention_only": True,
            "deliberative_context_repeat": 800,
            "deliberative_max_tokens": 2048,
            "tts_enabled": True,
            "tts_speaker": "chromie_mixed",
        },
        "phases": {
            "foreground_under_deliberative_load": {
                "status": "pass" if planner_before_deep else "control_observed",
                "deep_active_at_fast_planner_start": planner_before_deep,
                "foreground_completed_before_deep": planner_before_deep,
                "requests": {
                    "deliberative": {
                        "started_s": fast_start - 0.2,
                        "finished_s": deep_finish,
                        "ttft_ms": 100 + index,
                        "elapsed_ms": 2000 + index * 10,
                    },
                    "fast_gi_canary": {
                        "started_s": fast_start,
                        "finished_s": fast_start + 0.2,
                        "ttft_ms": 20 + index,
                        "elapsed_ms": 200 + index,
                    },
                    "fast_planner_canary": {
                        "started_s": fast_start + 0.21,
                        "finished_s": planner_finish,
                        "ttft_ms": 30 + index,
                        "elapsed_ms": 190 + index,
                    },
                },
                "tts": {
                    "under_foreground_and_deliberative_load": {
                        "first_audio_ms": 80 + index,
                        "elapsed_ms": 150 + index,
                    }
                },
            }
        },
        "resources": {
            "peak_gpu_memory_used_mib": 20000 + index,
            "peak_gpu_utilization_percent": 90 + index,
        },
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summary_builds_p50_p95_p99_from_repeated_contention_samples(tmp_path: Path) -> None:
    for index in range(1, 6):
        _write(tmp_path / f"trial-{index}.json", _sample(index=index))

    report = build_summary([tmp_path], label="sglang-test")

    assert report["report_type"] == "chromie.inference_provider_contention_summary"
    assert report["source"]["included_sample_count"] == 5
    assert report["identity"]["provider"] == "sglang"
    assert report["metrics"]["fast_gi_ttft_ms"]["count"] == 5
    assert "p50" in report["metrics"]["fast_gi_ttft_ms"]
    assert "p95" in report["metrics"]["fast_gi_ttft_ms"]
    assert "p99" in report["metrics"]["fast_gi_ttft_ms"]
    assert report["outcomes"]["foreground_completed_before_deep_rate"] == 1.0
    assert report["outcomes"]["tts_sample_count"] == 5


def test_summary_retains_control_observed_as_measurement_not_missing_sample(tmp_path: Path) -> None:
    _write(tmp_path / "trial-1.json", _sample(index=1, planner_before_deep=False))

    report = build_summary([tmp_path], label="ollama-style-control")

    assert report["source"]["included_sample_count"] == 1
    assert report["outcomes"]["phase_status_counts"] == {"control_observed": 1}
    assert report["outcomes"]["foreground_completed_before_deep_rate"] == 0.0
    assert report["metrics"]["foreground_window_ms"]["count"] == 1


def test_summary_rejects_mixed_qualification_identity(tmp_path: Path) -> None:
    first = _sample(index=1)
    second = _sample(index=2)
    second["model_revision"] = "different"
    _write(tmp_path / "trial-1.json", first)
    _write(tmp_path / "trial-2.json", second)

    with pytest.raises(ValueError, match="model_revision"):
        build_summary([tmp_path])
