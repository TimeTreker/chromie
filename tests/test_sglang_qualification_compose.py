from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.sglang-qualification.yml"


def _service() -> dict[str, object]:
    payload = yaml.safe_load(COMPOSE_PATH.read_text())
    assert isinstance(payload, dict)
    services = payload.get("services")
    assert isinstance(services, dict)
    service = services.get("chromie-llm-sglang-qualification")
    assert isinstance(service, dict)
    return service


def test_sglang_qualification_compose_is_real_isolated_service() -> None:
    service = _service()

    assert service["container_name"] == "chromie-llm-sglang-qualification"
    assert service["image"] == (
        "${SGLANG_IMAGE:?SGLANG_IMAGE must be set to a pinned SGLang image or digest}"
    )
    assert service["ports"] == ["127.0.0.1:30000:30000"]
    assert "depends_on" not in service


def test_sglang_qualification_compose_propagates_model_download_network_contract() -> None:
    service = _service()
    environment = service["environment"]
    assert isinstance(environment, dict)

    assert environment["HF_HUB_OFFLINE"] == "${HF_HUB_OFFLINE:-0}"
    assert environment["TRANSFORMERS_OFFLINE"] == "${TRANSFORMERS_OFFLINE:-0}"
    assert environment["HTTP_PROXY"] == "${HTTP_PROXY:-}"
    assert environment["HTTPS_PROXY"] == "${HTTPS_PROXY:-}"
    assert environment["NO_PROXY"] == (
        "${NO_PROXY:-localhost,127.0.0.1,host.docker.internal}"
    )
    assert service["extra_hosts"] == ["host.docker.internal:host-gateway"]


def test_sglang_qualification_compose_pins_model_identity_inputs() -> None:
    command = _service()["command"]
    assert isinstance(command, list)

    assert command[command.index("--model-path") + 1].startswith("${SGLANG_MODEL:?")
    assert command[command.index("--revision") + 1].startswith(
        "${SGLANG_MODEL_REVISION:?"
    )
    assert command[command.index("--served-model-name") + 1].startswith(
        "${SGLANG_SERVED_MODEL_NAME:?"
    )
    assert command[command.index("--context-length") + 1] == (
        "${SGLANG_CONTEXT_LENGTH:-32768}"
    )


def test_sglang_priority_scheduling_uses_fcfs_base_queue_and_preemption() -> None:
    command = _service()["command"]
    assert isinstance(command, list)

    assert command[command.index("--schedule-policy") + 1] == "fcfs"
    assert "--enable-priority-scheduling" in command
    assert command[command.index("--default-priority-value") + 1] == (
        "${SGLANG_DEFAULT_PRIORITY_VALUE:-0}"
    )
    assert "--abort-on-priority-when-disabled" in command
    assert "--priority-scheduling-preemption-threshold" in command
    assert "--chunked-prefill-size" in command
    assert "--schedule-conservativeness" in command
    assert command[command.index("--max-running-requests") + 1] == (
        "${SGLANG_MAX_RUNNING_REQUESTS:-2}"
    )
    assert command[command.index("--max-mamba-cache-size") + 1] == (
        "${SGLANG_MAX_MAMBA_CACHE_SIZE:-10}"
    )
    assert command[command.index("--mem-fraction-static") + 1] == (
        "${SGLANG_MEM_FRACTION_STATIC:-0.80}"
    )
    assert command[command.index("--cuda-graph-backend-prefill") + 1] == (
        "${SGLANG_CUDA_GRAPH_BACKEND_PREFILL:-breakable}"
    )


def test_sglang_shared_cache_is_bounded_independently_of_request_context() -> None:
    command = _service()["command"]
    assert isinstance(command, list)
    assert command[command.index("--max-total-tokens") + 1] == (
        "${SGLANG_MAX_TOTAL_TOKENS:-32768}"
    )
    assert "--context-length" in command
    assert command[command.index("--max-running-requests") + 1] == (
        "${SGLANG_MAX_RUNNING_REQUESTS:-2}"
    )
