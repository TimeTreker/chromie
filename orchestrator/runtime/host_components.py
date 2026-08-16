"""Construct maintained Host collaborators from one typed settings snapshot.

The composition root delegates startup wiring here so environment parsing and
compatibility factories never leak back into the realtime turn loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.clients.agent_client import AgentClient
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.evidence_identity import load_runtime_evidence_identity
from orchestrator.runtime.episode import EpisodeRecorder
from orchestrator.runtime.experience import ExperienceManager
from orchestrator.runtime.host_settings import (
    HostConfigurationError,
    HostSettingsSnapshot,
)
from orchestrator.runtime.interaction_session_evidence import (
    InteractionSessionEvidenceCollector,
    LocalInteractionSessionCapturePolicyProvider,
)
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
    build_soridormi_invoker,
)
from orchestrator.runtime.interaction_ledger import InteractionLedger
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
    interaction_ledger: InteractionLedger


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
    policy_provider = LocalInteractionSessionCapturePolicyProvider(
        settings.evidence.interaction_session_capture_policy_path
    )
    if settings.evidence.interaction_session_capture_policy_path is not None:
        # Fail invalid startup configuration before the realtime loop. Later
        # refresh failures retain the provider's last valid cached snapshot.
        startup_policy = policy_provider.resolve()
        if startup_policy.enabled and settings.evidence.runtime_event_root is None:
            raise HostConfigurationError(
                "CHROMIE_RUNTIME_EVENT_ROOT is required when "
                "ORCH_DATA_LOOP_INTERACTION_SESSION_CAPTURE_POLICY_PATH selects "
                "an enabled policy"
            )
    interaction_session_capture = InteractionSessionEvidenceCollector(
        policy_provider=policy_provider,
        event_root=settings.evidence.runtime_event_root,
        trigger_root=settings.evidence.data_loop_trigger_root,
        runtime_identity=load_runtime_evidence_identity(
            settings.evidence.runtime_identity_path
        ),
    )
    sessions = SessionTracker(
        enabled=timing_enabled,
        event_log_path=settings.session.event_log_path,
        workflow_report_root=(
            settings.evidence.cognitive_path.parent / "session-workflows"
            if settings.evidence.cognitive_enabled
            else None
        ),
        workflow_report_include_text=(
            settings.evidence.cognitive_include_text
        ),
        resource_sampling_mode=telemetry.system_resource_mode,
        interaction_session_capture=interaction_session_capture,
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
        interaction_ledger=InteractionLedger(),
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
    *,
    interaction_ledger: InteractionLedger,
) -> InteractionRuntimeCoordinator:
    cognition = settings.cognition
    session = settings.session
    invoker = None
    if cognition.enable_soridormi_capabilities:
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
        interaction_ledger=interaction_ledger,
    )
