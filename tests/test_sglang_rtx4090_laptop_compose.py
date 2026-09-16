from __future__ import annotations

from pathlib import Path

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


class _ComposeLoader(yaml.SafeLoader):
    pass


def _override(loader: _ComposeLoader, node):
    if isinstance(node, SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, ScalarNode):
        return loader.construct_scalar(node)
    raise TypeError(f"unsupported !override node: {type(node).__name__}")


_ComposeLoader.add_constructor("!override", _override)


ROOT = Path(__file__).resolve().parents[1]
LAPTOP_COMPOSE = ROOT / "docker-compose.sglang-rtx4090-laptop.yml"
RTX5090_COMPOSE = ROOT / "docker-compose.sglang.yml"
LAPTOP_PROFILE = ROOT / "env" / "profiles" / "rtx4090_laptop.env"


def _service(compose: Path = LAPTOP_COMPOSE) -> dict:
    payload = yaml.load(compose.read_text(encoding="utf-8"), Loader=_ComposeLoader)
    return payload["services"]["chromie-llm"]


def _value_after(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def _profile_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in LAPTOP_PROFILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def test_laptop_sglang_profile_uses_colon_free_served_alias() -> None:
    values = _profile_values()
    assert values["AGENT_MODEL"] == "chromie-qwen35-4b"
    assert ":" not in values["AGENT_MODEL"]
    for key in (
        "AGENT_GOAL_INTERPRETER_MODEL",
        "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL",
        "AGENT_GOAL_ASSOCIATION_MODEL",
        "AGENT_FAST_PLANNER_MODEL",
        "AGENT_DEEP_PLANNER_MODEL",
        "AGENT_TASK_CONTINUITY_MODEL",
        "AGENT_SKILL_SELECTION_MODEL",
    ):
        assert values[key] == values["AGENT_MODEL"]
    assert values["OLLAMA_MODEL"] == "qwen3.5:4b"
    assert values["TTS_COSYVOICE_OLLAMA_MODEL"] == "qwen3.5:4b"


def test_laptop_sglang_service_keeps_base_service_identity_and_pinned_model() -> None:
    service = _service()
    command = service["command"]
    assert service["image"] == "chromie-sglang:qwen35-4b-awq"
    assert service["entrypoint"] == ["python3", "-m", "sglang.launch_server"]
    assert _value_after(command, "--model-path") == "cyankiwi/Qwen3.5-4B-AWQ-4bit"
    assert _value_after(command, "--revision") == "ef85d23bebaba87b3c4672ba11c449c79dbdb23e"
    assert _value_after(command, "--served-model-name") == "${AGENT_MODEL:?AGENT_MODEL must be generated}"
    assert service["ports"] == ["127.0.0.1:30000:30000"]


def test_laptop_sglang_capacity_covers_current_single_request_planner_contract() -> None:
    command = _service()["command"]
    assert _value_after(command, "--context-length") == "49152"
    assert _value_after(command, "--max-total-tokens") == "49152"
    assert _value_after(command, "--max-running-requests") == "3"
    assert _value_after(command, "--max-mamba-cache-size") == "15"
    assert _value_after(command, "--mem-fraction-static") == "0.80"
    assert _value_after(command, "--chunked-prefill-size") == "2048"
    assert _value_after(command, "--cuda-graph-backend-prefill") == "breakable"


def test_rtx5090_sglang_admits_the_same_three_way_post_gi_fanout() -> None:
    command = _service(RTX5090_COMPOSE)["command"]
    assert _value_after(command, "--max-running-requests") == "3"


def test_laptop_sglang_enables_priority_and_preemption_without_new_semantic_owner() -> None:
    command = _service()["command"]
    assert _value_after(command, "--schedule-policy") == "fcfs"
    assert "--enable-priority-scheduling" in command
    assert "--abort-on-priority-when-disabled" in command
    assert _value_after(command, "--default-priority-value") == "0"
    assert _value_after(command, "--priority-scheduling-preemption-threshold") == "10"
    assert "--enable-metrics" in command
    assert "--enable-request-time-stats-logging" in command


def test_laptop_sglang_first_start_may_fetch_only_the_pinned_model_revision() -> None:
    environment = _service()["environment"]
    assert environment["HF_HOME"] == "/root/.cache/huggingface"
    assert environment["HF_HUB_OFFLINE"] == "${HF_HUB_OFFLINE:-0}"
    assert environment["TRANSFORMERS_OFFLINE"] == "${TRANSFORMERS_OFFLINE:-0}"
    assert "./hf_cache:/root/.cache/huggingface" in _service()["volumes"]
