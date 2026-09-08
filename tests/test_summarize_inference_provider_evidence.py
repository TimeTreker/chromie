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
        "schema_version": 3,
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
        "model_artifact": {
            "source_model_id": "Qwen/Qwen3.5-9B",
            "weight_format": "safetensors",
            "quantization": "none",
        },
        "base_url": "http://127.0.0.1:30000/v1",
        "git_revision": "abc123",
        "git_dirty": False,
        "git_worktree_state_sha256": "worktree-test",
        "status": "pass",
        "scheduler_config": {
            "operator_record": {"context_length": 32768},
            "provider_priority_semantics": "larger_value_first",
        },
        "workload_config": {
            "contention_protocol_version": 2,
            "contention_only": True,
            "model_topology": {
                "fast_gi": {
                    "model": "Qwen/Qwen3.5-9B",
                    "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
                    "artifact": {
                        "source_model_id": "Qwen/Qwen3.5-9B",
                        "weight_format": "safetensors",
                        "quantization": "none",
                    },
                },
                "fast_planner": {
                    "model": "Qwen/Qwen3.5-9B",
                    "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
                    "artifact": {
                        "source_model_id": "Qwen/Qwen3.5-9B",
                        "weight_format": "safetensors",
                        "quantization": "none",
                    },
                },
                "deliberative": {
                    "model": "Qwen/Qwen3.5-9B",
                    "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
                    "artifact": {
                        "source_model_id": "Qwen/Qwen3.5-9B",
                        "weight_format": "safetensors",
                        "quantization": "none",
                    },
                },
            },
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


def test_summary_rejects_clean_dirty_or_worktree_identity_drift(tmp_path: Path) -> None:
    first = _sample(index=1)
    second = _sample(index=2)
    second["git_dirty"] = True
    second["git_worktree_state_sha256"] = "different-worktree"
    _write(tmp_path / "trial-1.json", first)
    _write(tmp_path / "trial-2.json", second)

    with pytest.raises(ValueError, match="git_dirty|git_worktree_state_sha256"):
        build_summary([tmp_path])


def test_summary_rejects_model_artifact_drift(tmp_path: Path) -> None:
    first = _sample(index=1)
    second = _sample(index=2)
    second["model_artifact"] = {
        "source_model_id": "Qwen/Qwen3.5-9B",
        "weight_format": "gguf",
        "quantization": "Q4_K_M",
    }
    _write(tmp_path / "trial-1.json", first)
    _write(tmp_path / "trial-2.json", second)

    with pytest.raises(ValueError, match="model_artifact"):
        build_summary([tmp_path])

def test_summary_rejects_contention_model_topology_drift(tmp_path: Path) -> None:
    first = _sample(index=1)
    second = _sample(index=2)
    second["workload_config"]["model_topology"]["fast_planner"] = {
        "model": "Other/Fast-Model",
        "revision": "different-fast-revision",
        "artifact": {
            "source_model_id": "Other/Fast-Model",
            "weight_format": "safetensors",
            "quantization": "none",
        },
    }
    _write(tmp_path / "trial-1.json", first)
    _write(tmp_path / "trial-2.json", second)

    with pytest.raises(ValueError, match="workload_config"):
        build_summary([tmp_path])

def test_summary_reads_tts_and_control_latency_from_presentation_lease(tmp_path: Path) -> None:
    for index in range(1, 4):
        sample = _sample(index=index)
        sample["workload_config"]["contention_protocol_version"] = 3
        sample["workload_config"]["presentation_lease"] = {
            "enabled": True,
            "mode": "in_place",
            "scope": "sglang_engine",
            "pause_settle_ms": 100.0,
            "continue_torch_empty_cache": False,
        }
        phase = sample["phases"]["foreground_under_deliberative_load"]
        phase["tts"] = {
            "measurement_mode": "presentation_lease",
            "presentation_lease": {
                "first_audio_ms": 60 + index,
                "elapsed_ms": 120 + index,
            },
        }
        phase["presentation_lease"] = {
            "deep_active_before_continue": True,
            "deep_deltas_during_tts": 0,
            "deep_resumed_after_continue": True,
            "pause": {"elapsed_ms": 5 + index},
            "continue": {"elapsed_ms": 7 + index},
            "resume_to_next_delta_ms": 11 + index,
        }
        _write(tmp_path / f"trial-{index}.json", sample)

    report = build_summary([tmp_path], label="sglang-presentation-lease")

    assert report["outcomes"]["presentation_lease_sample_count"] == 3
    assert report["outcomes"]["deep_paused_during_tts_count"] == 3
    assert report["outcomes"]["deep_resumed_after_lease_count"] == 3
    assert report["metrics"]["tts_first_audio_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_pause_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_continue_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_resume_to_next_delta_ms"]["count"] == 3


def test_summary_reads_presentation_lease_revocation_metrics(tmp_path: Path) -> None:
    for index in range(1, 4):
        sample = _sample(index=index)
        sample["workload_config"]["contention_protocol_version"] = 5
        sample["workload_config"]["presentation_lease"] = {
            "enabled": True,
            "mode": "in_place",
            "scope": "sglang_engine",
            "pause_settle_ms": 100.0,
            "continue_torch_empty_cache": False,
            "revocation_probe": True,
            "revocation_trigger": "tts_first_audio",
            "revocation_roundtrip": "resume_new_gi_planner_then_reacquire_for_tts",
        }
        phase = sample["phases"]["foreground_under_deliberative_load"]
        phase["requests"]["interruption_fast_gi_canary"] = {
            "started_s": 20.0 + index,
            "finished_s": 20.1 + index,
            "ttft_ms": 25 + index,
            "elapsed_ms": 100 + index,
        }
        phase["requests"]["interruption_fast_planner_canary"] = {
            "started_s": 20.1 + index,
            "finished_s": 20.2 + index,
            "ttft_ms": 30 + index,
            "elapsed_ms": 105 + index,
        }
        phase["tts"] = {
            "measurement_mode": "presentation_lease_revocation",
            "interrupted_presentation_lease": {
                "first_audio_ms": 70 + index,
                "elapsed_ms": 75 + index,
                "close_ms": 3 + index,
            },
            "post_interruption_recovery": {
                "first_audio_ms": 80 + index,
                "elapsed_ms": 140 + index,
                "end": {
                    "queue_wait_seconds": 0.004 + index / 1000.0,
                    "native_first_audio_seconds": 0.050 + index / 1000.0,
                },
            },
        }
        phase["presentation_lease"] = {
            "deep_active_before_continue": True,
            "deep_deltas_during_tts": 0,
            "deep_resumed_after_continue": True,
            "pause": {"elapsed_ms": 5 + index},
            "continue": {"elapsed_ms": 7 + index},
            "resume_to_next_delta_ms": 11 + index,
            "revocation": {
                "deep_active_at_interrupt_gi_start": True,
                "interrupt_gi_completed_before_deep": True,
                "interrupt_planner_completed_before_deep": True,
                "tts_recovery_completed": True,
                "interrupt_gi_first_delta_from_interrupt_trigger_ms": 40 + index,
                "interrupt_planner_finished_from_interrupt_trigger_ms": 70 + index,
                "tts": {"close_ms": 3 + index},
                "reacquired_presentation_lease": {
                    "deep_deltas_during_recovery_tts": 0,
                    "deep_resumed_after_continue": True,
                    "pause": {"elapsed_ms": 4 + index},
                    "continue": {"elapsed_ms": 5 + index},
                    "resume_to_next_delta_ms": 6 + index,
                },
            },
        }
        _write(tmp_path / f"trial-{index}.json", sample)

    report = build_summary([tmp_path], label="sglang-presentation-lease-revocation")

    assert report["outcomes"]["presentation_lease_revocation_sample_count"] == 3
    assert report["outcomes"]["interruption_fast_gi_completed_before_deep_count"] == 3
    assert report["outcomes"]["interruption_fast_planner_completed_before_deep_count"] == 3
    assert report["outcomes"]["reacquired_lease_paused_deep_during_recovery_count"] == 3
    assert report["outcomes"]["deep_resumed_after_reacquired_lease_count"] == 3
    assert report["outcomes"]["post_interruption_tts_recovery_count"] == 3
    assert report["metrics"]["tts_first_audio_ms"]["count"] == 3
    assert report["metrics"]["interruption_fast_gi_ttft_ms"]["count"] == 3
    assert report["metrics"]["interruption_fast_planner_ttft_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_revocation_to_gi_first_delta_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_revocation_to_planner_finish_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_tts_cancel_close_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_reacquire_pause_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_reacquire_continue_ms"]["count"] == 3
    assert report["metrics"]["presentation_lease_reacquire_resume_to_next_delta_ms"]["count"] == 3
    assert report["metrics"]["post_interruption_tts_recovery_first_audio_ms"]["count"] == 3
    assert report["metrics"]["post_interruption_tts_recovery_queue_wait_ms"]["count"] == 3
    assert report["metrics"]["post_interruption_tts_recovery_native_first_audio_ms"]["count"] == 3
