from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentProfile:
    """Configuration boundary for one production component under evaluation.

    The profile names configuration variables only. It deliberately does not
    encode deployment URLs, ports, model names, prompt revisions, or component
    behavior policy.
    """

    name: str
    layers: tuple[str, ...]
    url_env: str
    callable_env: str
    description: str


COMPONENT_PROFILES: dict[str, ComponentProfile] = {
    "cognitive_gateway": ComponentProfile(
        name="cognitive_gateway",
        layers=("module", "integration"),
        url_env="CHROMIE_BENCHMARK_COGNITIVE_GATEWAY_URL",
        callable_env="CHROMIE_BENCHMARK_COGNITIVE_GATEWAY_CALLABLE",
        description=(
            "Input normalization, protective reflex, attention review, context "
            "assembly, and turn admission boundary"
        ),
    ),
    "planner": ComponentProfile(
        name="planner",
        layers=("module", "integration"),
        url_env="CHROMIE_BENCHMARK_PLANNER_URL",
        callable_env="CHROMIE_BENCHMARK_PLANNER_CALLABLE",
        description="Canonical planning boundary",
    ),
    "mind_profile": ComponentProfile(
        name="mind_profile",
        layers=("module", "integration"),
        url_env="CHROMIE_BENCHMARK_MIND_PROFILE_URL",
        callable_env="CHROMIE_BENCHMARK_MIND_PROFILE_CALLABLE",
        description="Owner-approved MindProfile projection boundary",
    ),
    "capability_projection": ComponentProfile(
        name="capability_projection",
        layers=("module", "integration"),
        url_env="CHROMIE_BENCHMARK_CAPABILITY_PROJECTION_URL",
        callable_env="CHROMIE_BENCHMARK_CAPABILITY_PROJECTION_CALLABLE",
        description="Backend-neutral capability catalog projection boundary",
    ),
    "social_attention": ComponentProfile(
        name="social_attention",
        layers=("module", "integration"),
        url_env="CHROMIE_BENCHMARK_SOCIAL_ATTENTION_URL",
        callable_env="CHROMIE_BENCHMARK_SOCIAL_ATTENTION_CALLABLE",
        description=(
            "Planner-owned auxiliary Activity proposal and Host validation boundary"
        ),
    ),
}


def get_component_profile(name: str) -> ComponentProfile:
    try:
        return COMPONENT_PROFILES[name]
    except KeyError as exc:
        supported = ", ".join(sorted(COMPONENT_PROFILES))
        raise ValueError(f"unknown benchmark component {name!r}; choose one of: {supported}") from exc
