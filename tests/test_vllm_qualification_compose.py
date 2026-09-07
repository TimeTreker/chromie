from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.vllm-qualification.yml"


def _service() -> dict[str, object]:
    payload = yaml.safe_load(COMPOSE_PATH.read_text())
    assert isinstance(payload, dict)
    services = payload.get("services")
    assert isinstance(services, dict)
    service = services.get("chromie-llm-vllm-qualification")
    assert isinstance(service, dict)
    return service


def test_vllm_qualification_compose_is_real_isolated_service() -> None:
    service = _service()

    assert service["container_name"] == "chromie-llm-vllm-qualification"
    assert service["image"] == (
        "${VLLM_IMAGE:?VLLM_IMAGE must be set to a pinned vLLM image or digest}"
    )
    assert service["ports"] == ["127.0.0.1:8000:8000"]
    assert "depends_on" not in service


def test_vllm_qualification_compose_pins_model_identity_inputs() -> None:
    command = _service()["command"]
    assert isinstance(command, list)

    assert command[command.index("--model") + 1].startswith("${VLLM_MODEL:?")
    assert command[command.index("--revision") + 1].startswith(
        "${VLLM_MODEL_REVISION:?"
    )
    assert command[command.index("--served-model-name") + 1].startswith(
        "${VLLM_SERVED_MODEL_NAME:?"
    )
    assert command[command.index("--max-model-len") + 1] == (
        "${VLLM_CONTEXT_LENGTH:-32768}"
    )


def test_vllm_qualification_compose_enables_priority_and_chunked_prefill() -> None:
    command = _service()["command"]
    assert isinstance(command, list)

    assert command[command.index("--scheduling-policy") + 1] == "priority"
    assert "--enable-chunked-prefill" in command
    assert command[command.index("--max-num-batched-tokens") + 1] == (
        "${VLLM_MAX_NUM_BATCHED_TOKENS:-2048}"
    )
    assert command[command.index("--gpu-memory-utilization") + 1] == (
        "${VLLM_GPU_MEMORY_UTILIZATION:-0.70}"
    )
