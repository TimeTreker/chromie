"""Construct maintained Host collaborators from one typed settings snapshot.

The composition root delegates startup wiring here so environment parsing and
compatibility factories never leak back into the realtime turn loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.clients.agent_client import AgentClient
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.episode import EpisodeRecorder
from orchestrator.runtime.experience import ExperienceManager
from orchestrator.runtime.host_settings import HostSettingsSnapshot
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
    build_soridormi_invoker,
)
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.session import SessionTracker
from shared.chromie_runtime.accelerator_telemetry import (
    ACCELERATOR_SAMPLE_MODULE,
    AcceleratorTelemetryConfig,
    AcceleratorTelemetrySampler,
)


@dataclass(frozen=True)
class HostSupportComponents:
    accelerator_sampler: AcceleratorTelemetrySampler
    sessions: SessionTracker
    conversation_state: ConversationStateManager
    mind: MindManager
    experience: ExperienceManager
    episode_recorder: EpisodeRecorder


def build_host_support(
    settings: HostSettingsSnapshot,
    *,
    timing_enabled: bool,
) -> HostSupportComponents:
    telemetry = settings.telemetry
    accelerator_sampler = AcceleratorTelemetrySampler(
        AcceleratorTelemetryConfig(
            mode=telemetry.accelerator_mode,
            provider=telemetry.accelerator_provider,
            timeout_ms=telemetry.accelerator_timeout_ms,
            min_interval_s=telemetry.accelerator_min_interval_s,
        )
    )
    sessions = SessionTracker(
        enabled=timing_enabled,
        event_log_path=settings.session.event_log_path,
        resource_sampling_mode=telemetry.system_resource_mode,
    )
    sessions.register_resource_snapshot_provider(
        module=ACCELERATOR_SAMPLE_MODULE,
        name="accelerator_resource_sample",
        provider=accelerator_sampler.cached_sample,
    )
    return HostSupportComponents(
        accelerator_sampler=accelerator_sampler,
        sessions=sessions,
        conversation_state=ConversationStateManager.from_settings(settings.conversation),
        mind=MindManager.from_settings(settings.mind),
        experience=ExperienceManager.from_settings(settings.experience),
        episode_recorder=EpisodeRecorder.from_settings(settings.episode),
    )


def build_agent_client(settings: HostSettingsSnapshot) -> AgentClient:
    cognition = settings.cognition
    return AgentClient(
        cognition.agent_url,
        cognition.agent_timeout_ms,
        task_graph_execution_token=cognition.task_graph_execution_token,
    )


def build_interaction_runtime(
    assistant: Any,
    settings: HostSettingsSnapshot,
) -> InteractionRuntimeCoordinator:
    cognition = settings.cognition
    session = settings.session
    invoker = None
    if cognition.enable_soridormi_skills:
        invoker = build_soridormi_invoker(
            manifest_path=cognition.soridormi_manifest,
        )
    return InteractionRuntimeCoordinator(
        assistant._schedule_interaction_speech,
        speech_cancel_scheduler=assistant._cancel_interaction_speech,
        soridormi_invoker=invoker,
        task_graph_handler=assistant._execute_planning_task_graph,
        task_graph_cancel_handler=assistant._cancel_planning_task_graph,
        agent_tool_handler=assistant._execute_agent_tool,
        conversation_memory_handler=(
            assistant.conversation_state.retrieve_verified_tool_memory
        ),
        capability_manifest_paths=cognition.capability_manifest_paths,
        max_concurrency=settings.interaction.skill_max_concurrency,
        catalog_refresh_ttl_s=settings.interaction.catalog_refresh_ttl_s,
        body_recovery_max_attempts=session.body_recovery_max_attempts,
        body_recovery_confirmation_ttl_s=(
            session.body_recovery_confirmation_ttl_s
        ),
    )
