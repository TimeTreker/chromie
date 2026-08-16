from __future__ import annotations

import logging
import secrets
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, ORJSONResponse

from .settings import Settings, agent_service_settings as settings
from .agents import AgentServices
from .capabilities.catalog import CapabilityCatalog, CapabilitySearchRequest, CapabilitySearchResult
from .capabilities.loader import build_configured_registry, parse_manifest_paths
from .agent_skills import (
    AgentSkillDisclosureService,
    AgentSkillProgressiveDisclosureCoordinator,
    AgentSkillSelectionService,
    attach_disclosure_metadata,
    attach_planner_disclosure_metadata_fail_closed,
    inherited_plan_agent_skill_provenance,
    build_configured_agent_skill_registry,
)
from .clients.external_information_client import HttpExternalInformationClient
from .clients.ollama_client import OllamaClient
from .clients.weather_client import OpenMeteoWeatherClient
from .local_tool_execution import LocalToolExecutor
from .cognitive_gateway import AttentionReviewer

try:
    from chromie_contracts.agent_skill import (
        AgentSkillDisclosureRequest,
        AgentSkillDisclosureResolution,
        AgentSkillRegistrySnapshot,
        AgentSkillSelectionRequest,
        AgentSkillSelectionResolution,
    )
    from chromie_contracts.core_interpretation import (
        CognitiveWorkRequest,
        CoreInterpretationResult,
        CoreInterpretationUnavailable,
    )
    from chromie_contracts.social_attention import SocialAttentionPlan, SocialAttentionRequest
    from chromie_contracts.tool_result import (
        ToolExecutionRequest,
        ToolExecutionResponse,
        ToolResultInterpretationRequest,
    )
    from chromie_contracts.user_turn import (
        AttentionReviewRequest,
        AttentionReviewResult,
        CoreTurnRequest,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.agent_skill import (
        AgentSkillDisclosureRequest,
        AgentSkillDisclosureResolution,
        AgentSkillRegistrySnapshot,
        AgentSkillSelectionRequest,
        AgentSkillSelectionResolution,
    )
    from shared.chromie_contracts.core_interpretation import (
        CognitiveWorkRequest,
        CoreInterpretationResult,
        CoreInterpretationUnavailable,
    )
    from shared.chromie_contracts.social_attention import SocialAttentionPlan, SocialAttentionRequest
    from shared.chromie_contracts.tool_result import (
        ToolExecutionRequest,
        ToolExecutionResponse,
        ToolResultInterpretationRequest,
    )
    from shared.chromie_contracts.user_turn import (
        AttentionReviewRequest,
        AttentionReviewResult,
        CoreTurnRequest,
    )
from .interaction import (
    AgentResultInteractionAdapter,
    InteractionOutputCoordinator,
    NativeInteractionOutputError,
)
from .runtime import AgentRuntime, InteractionRuntime
from .task_continuity import TaskContinuityResolver
from .goal_association import GoalAssociationResolver
from .fast_planner import FastPlannerResolver
from .deep_planner import DeepPlannerResolver
from .reflection import ReflectionResolver
from .response_composer import ResponseComposerResolver
from .tool_result_interpreter import ToolResultInterpreter
from .schema import AgentResult, AgentRunRequest, HealthResponse
from .cognitive_core.goal_interpreter import (
    RouteDecision as CoreRouteDecision,
    RouteRequest as CoreRouteRequest,
    initialize_goal_interpreter,
    interpret_goal,
    interpret_turn,
)
from .cognitive_core.goal_interpreter.fallback import InterpretationUnavailableError
from .task_graph import (
    ExecutionTrace,
    TaskGraph,
    TaskGraphCancelResponse,
    TaskGraphConfirmationGrantRequest,
    TaskGraphConfirmationGrantResponse,
    TaskGraphDryRunRequest,
    TaskGraphExecuteRequest,
    TaskGraphGuardedExecuteRequest,
    TaskGraphSchedulerStatus,
    TaskGraphPlanner,
    TaskGraphService,
    TaskGraphValidationResponse,
)
from .tool_invocation import McpStreamableHttpInvoker

try:
    from chromie_contracts.interaction import InteractionResponse
    from chromie_contracts.semantic_authority import semantic_authority_route_matrix
    from chromie_contracts.semantic_task import SemanticTaskOperationSet
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse
    from shared.chromie_contracts.semantic_authority import semantic_authority_route_matrix
    from shared.chromie_contracts.semantic_task import SemanticTaskOperationSet





logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.agent")

ollama_client = OllamaClient(
    settings.ollama_url,
    settings.model,
    timeout_ms=settings.timeout_ms,
    purpose="agent_default",
        service_settings=settings,
)
weather_client = OpenMeteoWeatherClient(service_settings=settings) if settings.weather_enabled else None
external_information_client = (
    HttpExternalInformationClient(
        settings.external_information_url,
        timeout_s=settings.external_information_timeout_ms / 1000.0,
        bearer_token=settings.external_information_token,
    )
    if settings.external_information_enabled and settings.external_information_url
    else None
)

response_reviewer_client = (
    OllamaClient(
        settings.ollama_url,
        settings.response_review_model,
        timeout_ms=settings.response_review_timeout_ms,
        purpose="response_review",
        service_settings=settings,
    )
    if settings.use_llm and settings.response_review_enabled
    else None
)
social_attention_client = (
    OllamaClient(
        settings.ollama_url,
        settings.social_attention_model,
        timeout_ms=settings.social_attention_timeout_ms,
        purpose="social_attention",
        service_settings=settings,
    )
    if settings.use_llm and settings.social_attention_mode != "off"
    else None
)
cognitive_gateway_attention_client = (
    OllamaClient(
        settings.ollama_url,
        settings.cognitive_gateway_attention_model,
        timeout_ms=settings.cognitive_gateway_attention_timeout_ms,
        purpose="cognitive_gateway_attention_review",
        service_settings=settings,
    )
    if settings.use_llm and settings.cognitive_gateway_attention_enabled
    else None
)
cognitive_gateway_attention_reviewer = AttentionReviewer(
    cognitive_gateway_attention_client,
    min_suppression_confidence=(
        settings.cognitive_gateway_attention_min_suppression_confidence
    ),
    num_ctx=settings.cognitive_gateway_attention_num_ctx,
    num_predict=settings.cognitive_gateway_attention_num_predict,
)

task_continuity_client = (
    OllamaClient(
        settings.ollama_url,
        settings.task_continuity_model,
        timeout_ms=settings.task_continuity_timeout_ms,
        purpose="task_continuity",
        service_settings=settings,
    )
    if settings.use_llm and settings.task_continuity_enabled
    else None
)
task_continuity_resolver = (
    TaskContinuityResolver(
        task_continuity_client,
        min_confidence=settings.task_continuity_min_confidence,
        max_active_tasks=settings.task_continuity_max_active_tasks,
        num_ctx=settings.task_continuity_num_ctx,
        num_predict=settings.task_continuity_num_predict,
    )
    if task_continuity_client is not None
    else None
)
configured_registry = build_configured_registry(
    parse_manifest_paths(settings.capability_manifests),
    environment=settings.environment,
)
capability_registry = configured_registry.registry
configured_agent_skill_registry = build_configured_agent_skill_registry(
    settings.agent_skill_roots
)
agent_skill_registry = configured_agent_skill_registry.registry
agent_skill_selection_client = (
    OllamaClient(
        settings.ollama_url,
        settings.agent_skill_selection_model,
        timeout_ms=settings.agent_skill_selection_timeout_ms,
        purpose="agent_skill_selection",
        service_settings=settings,
    )
    if settings.use_llm and settings.agent_skill_selection_enabled
    else None
)
agent_skill_selection_service = (
    AgentSkillSelectionService(
        agent_skill_selection_client,
        agent_skill_registry,
        max_candidates=settings.agent_skill_selection_max_candidates,
        max_selected=settings.agent_skill_selection_max_selected,
        min_confidence=settings.agent_skill_selection_min_confidence,
        num_ctx=settings.agent_skill_selection_num_ctx,
        num_predict=settings.agent_skill_selection_num_predict,
    )
    if agent_skill_selection_client is not None
    else None
)
agent_skill_disclosure_service = AgentSkillDisclosureService(
    agent_skill_registry,
    max_projection_chars=settings.agent_skill_projection_max_chars,
    max_total_chars=settings.agent_skill_projection_total_max_chars,
    projection_count_limit=settings.agent_skill_projection_count_limit,
)
agent_skill_progressive_disclosure = AgentSkillProgressiveDisclosureCoordinator(
    agent_skill_selection_service,
    agent_skill_disclosure_service,
    enabled=settings.agent_skill_progressive_disclosure_enabled,
)
local_tool_executor = LocalToolExecutor(
    capability_registry,
    weather_client=weather_client,
    external_information_client=external_information_client,
)
try:
    capability_registry.get_tool("soridormi.skill.list")
except KeyError:
    capability_catalog_invoker = None
else:
    capability_catalog_invoker = McpStreamableHttpInvoker(capability_registry)
capability_catalog = CapabilityCatalog(
    capability_registry,
    live_invoker=capability_catalog_invoker,
    refresh_ttl_s=settings.capability_catalog_refresh_sec,
    prompt_tier_preset=CapabilityCatalog.load_prompt_tier_preset(
        settings.capability_prompt_tier_preset
    ),
    prompt_tier_overrides=CapabilityCatalog.load_prompt_tier_overrides(
        settings.capability_prompt_tier_overrides
    ),
)
task_graph_planner = (
    TaskGraphPlanner(capability_registry, ollama_client)
    if settings.enable_task_graph_planning and settings.use_llm
    else None
)
tool_result_interpreter_client = (
    OllamaClient(
        settings.ollama_url,
        settings.tool_result_interpreter_model,
        timeout_ms=settings.tool_result_interpreter_timeout_ms,
        purpose="tool_result_interpreter",
        service_settings=settings,
    )
    if settings.use_llm and settings.tool_result_interpreter_enabled
    else None
)
tool_result_interpreter = (
    ToolResultInterpreter(
        tool_result_interpreter_client,
        num_ctx=settings.tool_result_interpreter_num_ctx,
        num_predict=settings.tool_result_interpreter_num_predict,
    )
    if tool_result_interpreter_client is not None
    else None
)
services = AgentServices(
    ollama=ollama_client,
    response_reviewer=response_reviewer_client,
    response_review_mode=settings.response_review_mode,
    use_llm=settings.use_llm,
    max_speak_chars=settings.max_speak_chars,
    expressive_body_cues=settings.expressive_body_cues,
    social_attention_mode=settings.social_attention_mode,
    social_attention_ollama=social_attention_client,
    social_attention_num_ctx=settings.social_attention_num_ctx,
    social_attention_num_predict=settings.social_attention_num_predict,
    social_attention_max_behaviors=settings.social_attention_max_behaviors,
    social_attention_wait_after_response_ms=settings.social_attention_wait_after_response_ms,
    social_attention_capability_ids=settings.social_attention_capability_ids,
    require_capability_plan_review=settings.require_capability_plan_review,
    legacy_capability_fallback_enabled=settings.legacy_capability_fallback_enabled,
    task_graph_planner=task_graph_planner,
    capability_catalog=capability_catalog,
    capability_match_limit=settings.capability_match_limit,
    local_tool_executor=local_tool_executor,
    tool_result_interpreter=tool_result_interpreter,
)
runtime = AgentRuntime(services)
interaction_runtime = InteractionRuntime(services)
interaction_adapter = AgentResultInteractionAdapter()
interaction_output = InteractionOutputCoordinator(
    interaction_runtime,
    runtime,
    mode=settings.interaction_output_mode,
    fallback_to_legacy=settings.native_interaction_fallback,
    adapter=interaction_adapter,
)
read_only_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_read_only_task_graph_execution
    else None
)
planning_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_planning_task_graph_execution
    else None
)
if settings.enable_physical_task_graph_execution and not settings.enable_guarded_task_graph_execution:
    raise ValueError(
        "AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION is required when physical TaskGraph execution is enabled"
    )
if settings.enable_guarded_task_graph_execution and not settings.task_graph_execution_token:
    raise ValueError(
        "AGENT_TASK_GRAPH_EXECUTION_TOKEN is required when guarded TaskGraph execution is enabled"
    )
guarded_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_guarded_task_graph_execution
    else None
)
task_graph_service = TaskGraphService(
    capability_registry,
    read_only_invoker=read_only_invoker,
    planning_invoker=planning_invoker,
    guarded_invoker=guarded_invoker,
    allow_physical_motion=settings.enable_physical_task_graph_execution,
    enable_parallel_execution=settings.enable_parallel_task_graph_execution,
    max_concurrency=settings.task_graph_max_concurrency,
    trace_max_entries=settings.task_graph_trace_max_entries,
    trace_ttl_s=settings.task_graph_trace_ttl_sec,
    grant_max_entries=settings.task_graph_grant_max_entries,
)
logger.info(
    "loaded capability registry sources=%s manifests=%s tools=%d",
    ",".join(configured_registry.sources),
    ",".join(configured_registry.manifest_files) or "<none>",
    len(capability_registry.list_tools()),
)
logger.info(
    "loaded read-only Agent Skill registry roots=%s packages=%s skills=%d",
    ",".join(configured_agent_skill_registry.roots) or "<none>",
    ",".join(configured_agent_skill_registry.package_files) or "<none>",
    len(agent_skill_registry),
)
logger.info(
    "Agent Skill model selection enabled=%s model=%s max_candidates=%s "
    "max_selected=%s min_confidence=%s",
    agent_skill_selection_service is not None,
    settings.agent_skill_selection_model,
    settings.agent_skill_selection_max_candidates,
    settings.agent_skill_selection_max_selected,
    settings.agent_skill_selection_min_confidence,
)
logger.info(
    "Agent Skill progressive disclosure enabled=%s max_projection_chars=%s "
    "max_total_chars=%s projection_count_limit=%s",
    settings.agent_skill_progressive_disclosure_enabled
    and agent_skill_selection_service is not None,
    settings.agent_skill_projection_max_chars,
    settings.agent_skill_projection_total_max_chars,
    settings.agent_skill_projection_count_limit,
)
goal_association_client = (
    OllamaClient(
        settings.ollama_url,
        settings.goal_association_model,
        timeout_ms=settings.goal_association_timeout_ms,
        purpose="goal_association",
        service_settings=settings,
    )
    if settings.use_llm and settings.goal_association_enabled
    else None
)
goal_association_resolver = (
    GoalAssociationResolver(
        goal_association_client,
        min_confidence=settings.goal_association_min_confidence,
        max_active_goals=settings.goal_association_max_active_goals,
        num_ctx=settings.goal_association_num_ctx,
        num_predict=settings.goal_association_num_predict,
    )
    if goal_association_client is not None
    else None
)

fast_planner_client = (
    OllamaClient(
        settings.ollama_url,
        settings.fast_planner_model,
        timeout_ms=settings.fast_planner_timeout_ms,
        purpose="fast_planner",
        service_settings=settings,
    )
    if settings.use_llm and settings.fast_planner_enabled
    else None
)
fast_planner_resolver = (
    FastPlannerResolver(
        fast_planner_client,
        capability_catalog,
        communication_reviewer=ollama_client,
        min_confidence=settings.fast_planner_min_confidence,
        num_ctx=settings.fast_planner_num_ctx,
        num_predict=settings.fast_planner_num_predict,
        max_capabilities=settings.fast_planner_max_capabilities,
    )
    if fast_planner_client is not None
    else None
)
deep_planner_client = (
    OllamaClient(
        settings.ollama_url,
        settings.deep_planner_model,
        timeout_ms=settings.deep_planner_timeout_ms,
        purpose="deep_planner",
        service_settings=settings,
    )
    if settings.use_llm and settings.deep_planner_enabled
    else None
)
deep_planner_resolver = (
    DeepPlannerResolver(
        deep_planner_client, capability_catalog,
        min_confidence=settings.deep_planner_min_confidence,
        num_ctx=settings.deep_planner_num_ctx,
        num_predict=settings.deep_planner_num_predict,
        max_capabilities=settings.deep_planner_max_capabilities,
        min_goal_satisfaction=settings.deep_planner_min_goal_satisfaction,
    )
    if deep_planner_client is not None
    else None
)
reflection_client = (
    OllamaClient(
        settings.ollama_url,
        settings.deep_planner_model,
        timeout_ms=settings.deep_planner_timeout_ms,
        purpose="reflection",
        service_settings=settings,
    )
    if settings.use_llm and settings.deep_planner_enabled
    else None
)
reflection_resolver = (
    ReflectionResolver(
        reflection_client,
        num_ctx=settings.deep_planner_num_ctx,
        num_predict=settings.deep_planner_num_predict,
    )
    if reflection_client is not None
    else None
)

response_composer_client = (
    OllamaClient(
        settings.ollama_url,
        settings.response_composer_model,
        timeout_ms=settings.response_composer_timeout_ms,
        purpose="response_composer",
        service_settings=settings,
    )
    if settings.use_llm and settings.response_composer_enabled
    else None
)
response_composer_resolver = (
    ResponseComposerResolver(
        response_composer_client,
        num_ctx=settings.response_composer_num_ctx,
        num_predict=settings.response_composer_num_predict,
    )
    if response_composer_client is not None
    else None
)


app = FastAPI(
    title="Chromie Agent",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)


def require_task_graph_execution_auth(authorization: str | None) -> None:
    expected = f"Bearer {settings.task_graph_execution_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid TaskGraph execution authorization")


def require_task_graph_diagnostics_auth(authorization: str | None) -> None:
    if not settings.task_graph_diagnostics_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "TaskGraph diagnostics are disabled; configure "
                "AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN"
            ),
        )
    expected = f"Bearer {settings.task_graph_diagnostics_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail="invalid TaskGraph diagnostics authorization",
        )


@app.on_event("startup")
async def initialize_cognitive_core() -> None:
    await initialize_goal_interpreter()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    scheduler = task_graph_service.scheduler_status()
    return HealthResponse(
        ok=True,
        model=settings.model,
        ollama_url=settings.ollama_url,
        use_llm=settings.use_llm,
        available_agents=runtime.available_agents(),
        capability_sources=configured_registry.sources,
        capability_manifest_files=configured_registry.manifest_files,
        agent_skill_roots=list(configured_agent_skill_registry.roots),
        agent_skill_package_files=list(configured_agent_skill_registry.package_files),
        agent_skill_count=len(agent_skill_registry),
        agent_skill_model_selection_enabled=(agent_skill_selection_service is not None),
        agent_skill_selection_model=(
            settings.agent_skill_selection_model
            if agent_skill_selection_service is not None
            else None
        ),
        agent_skill_selection_max_candidates=settings.agent_skill_selection_max_candidates,
        agent_skill_selection_max_selected=settings.agent_skill_selection_max_selected,
        agent_skill_progressive_disclosure_enabled=(
            settings.agent_skill_progressive_disclosure_enabled
            and agent_skill_selection_service is not None
        ),
        agent_skill_projection_max_chars=settings.agent_skill_projection_max_chars,
        agent_skill_projection_total_max_chars=(
            settings.agent_skill_projection_total_max_chars
        ),
        agent_skill_projection_count_limit=settings.agent_skill_projection_count_limit,
        task_graph_planning_enabled=task_graph_planner is not None,
        read_only_task_graph_execution_enabled=read_only_invoker is not None,
        planning_task_graph_execution_enabled=planning_invoker is not None,
        parallel_task_graph_execution_enabled=(
            settings.enable_parallel_task_graph_execution
        ),
        task_graph_max_concurrency=settings.task_graph_max_concurrency,
        task_graph_active_count=scheduler.active_count,
        task_graph_waiting_count=scheduler.waiting_count,
        guarded_task_graph_execution_enabled=guarded_invoker is not None,
        physical_task_graph_execution_enabled=(
            guarded_invoker is not None and settings.enable_physical_task_graph_execution
        ),
        interaction_output_mode=settings.interaction_output_mode,
        native_interaction_fallback_enabled=settings.native_interaction_fallback,
        legacy_capability_fallback_enabled=settings.legacy_capability_fallback_enabled,
        capability_catalog_enabled=True,
        capability_catalog_version=capability_catalog.version,
        task_continuity_enabled=task_continuity_resolver is not None,
        goal_association_enabled=goal_association_resolver is not None,
        goal_association_model=(
            settings.goal_association_model if goal_association_resolver is not None else None
        ),
        fast_planner_enabled=fast_planner_resolver is not None,
        fast_planner_model=(settings.fast_planner_model if fast_planner_resolver is not None else None),
        deep_planner_enabled=deep_planner_resolver is not None,
        deep_planner_model=(settings.deep_planner_model if deep_planner_resolver is not None else None),
        response_composer_enabled=response_composer_resolver is not None,
        response_composer_model=(settings.response_composer_model if response_composer_resolver is not None else None),
        tool_result_interpreter_enabled=tool_result_interpreter is not None,
        tool_result_interpreter_model=(
            settings.tool_result_interpreter_model
            if tool_result_interpreter is not None
            else None
        ),
        task_continuity_model=(
            settings.task_continuity_model if task_continuity_resolver is not None else None
        ),
        social_attention_mode=settings.social_attention_mode,
        social_attention_model=(
            settings.social_attention_model if social_attention_client is not None else None
        ),
    )


@app.get("/semantic-authority")
async def semantic_authority() -> dict[str, object]:
    return {
        "matching_turn_authority_required": True,
        "claim_is_caller_authentication": False,
        "claim_is_single_use_replay_protection": False,
        "legacy_capability_fallback_enabled": (
            settings.legacy_capability_fallback_enabled
        ),
        "route_matrix": semantic_authority_route_matrix(),
    }


@app.get("/agents")
async def agents() -> dict:
    return {
        "agents": runtime.available_agents(),
        "notes": {
            "speaker_agent": "decides wording/style only; it does not access audio devices",
            "safety_agent": "validates and clamps risky actions",
        },
    }




@app.post(
    "/cognitive-gateway/attention-review",
    response_model=AttentionReviewResult,
)
async def review_cognitive_gateway_attention(
    request: AttentionReviewRequest,
) -> AttentionReviewResult:
    """Review bounded addressedness before ordinary Core semantics."""
    return await cognitive_gateway_attention_reviewer.review(request)


@app.post(
    "/cognitive-core/interpret",
    response_model=CoreInterpretationResult,
    responses={503: {"model": CoreInterpretationUnavailable}},
)
async def interpret_cognitive_turn(
    request: CoreTurnRequest,
) -> CoreInterpretationResult | JSONResponse:
    """Interpret one already-admitted immutable turn inside the Core."""
    envelope = request.turn_envelope
    context = dict(request.context_snapshot.context)
    context["user_turn_envelope"] = envelope.model_dump(mode="json")
    context["gateway_context_snapshot"] = request.context_snapshot.model_dump(
        mode="json"
    )
    context["gateway_admission_complete"] = True
    try:
        interpretation = await interpret_goal(
            CoreRouteRequest(
                sid=envelope.session_id,
                text=envelope.normalized_input.text,
                language=envelope.normalized_input.language,
                context=context,
            )
        )
    except InterpretationUnavailableError as exc:
        unavailable = CoreInterpretationUnavailable(
            turn_id=envelope.turn_id,
            session_id=envelope.session_id,
            failure_class="goal_interpreter_unavailable",
            retryable=True,
            reason=exc.reason,
        )
        return JSONResponse(
            status_code=503,
            content=unavailable.model_dump(mode="json"),
        )
    return CoreInterpretationResult(
        turn_id=envelope.turn_id,
        session_id=envelope.session_id,
        confidence=interpretation.confidence,
        language=envelope.normalized_input.language or "auto",
        responsibilities=[
            item.model_dump(mode="json", exclude_none=True)
            for item in interpretation.responsibilities
        ],
        unresolved=list(interpretation.unresolved),
    )

@app.post("/fast-advance")
async def resolve_fast_advance(request: CognitiveWorkRequest):
    if fast_planner_resolver is None:
        raise HTTPException(status_code=503, detail="Fast planner is disabled")
    # This is the same Fast Planner before canonical Goal binding.  Agent Skill
    # disclosure remains deferred until canonical planning because pre-Goal
    # advancement may author only a conversational Activity and continuation
    # dispositions, never executable Capability steps.
    return await fast_planner_resolver.resolve_advance(request)


@app.post("/fast-plan")
async def resolve_fast_plan(request: CognitiveWorkRequest):
    if fast_planner_resolver is None:
        raise HTTPException(status_code=503, detail="Fast planner is disabled")
    prepared, disclosure = await agent_skill_progressive_disclosure.prepare_agent_request(
        request,
        "fast_planner",
    )
    result = await fast_planner_resolver.resolve(prepared)
    return attach_planner_disclosure_metadata_fail_closed(result, disclosure)


@app.post("/deep-plan")
async def resolve_deep_plan(request: CognitiveWorkRequest):
    if deep_planner_resolver is None:
        raise HTTPException(status_code=503, detail="Deep planner is disabled")
    prepared, disclosure = await agent_skill_progressive_disclosure.prepare_agent_request(
        request,
        "deep_planner",
    )
    result = await deep_planner_resolver.resolve(prepared)
    return attach_planner_disclosure_metadata_fail_closed(
        result,
        disclosure,
        inherited_plan_provenance=inherited_plan_agent_skill_provenance(
            prepared.context
        ),
    )


@app.post("/reflection")
async def resolve_reflection(request: CognitiveWorkRequest):
    if reflection_resolver is None:
        raise HTTPException(status_code=503, detail="Reflection is disabled")
    return await reflection_resolver.resolve(request)


@app.post("/social-attention/plan", response_model=SocialAttentionPlan)
async def plan_social_attention(request: SocialAttentionRequest) -> SocialAttentionPlan:
    """Plan one independent, event-scoped auxiliary Social-Attention proposal."""
    await interaction_runtime.prepare_social_attention_context(request)
    plan = await interaction_runtime.social_attention_planner.plan(request)
    if plan is None:
        return SocialAttentionPlan(
            decision="none",
            reason="No eligible Social-Attention proposal was available for this event.",
            metadata={"resolver": "social_attention", "event": request.event},
        )
    return plan


@app.post("/compose-response-plan")
async def compose_response_plan(request: CognitiveWorkRequest):
    if response_composer_resolver is None:
        raise HTTPException(status_code=503, detail="Response composer is disabled")
    prepared, disclosure = await agent_skill_progressive_disclosure.prepare_agent_request(
        request,
        "response_composer",
    )
    result = await response_composer_resolver.resolve(prepared)
    return attach_disclosure_metadata(result, disclosure)


@app.post("/tools/execute", response_model=ToolExecutionResponse)
async def execute_local_tool(request: ToolExecutionRequest) -> ToolExecutionResponse:
    """Execute one exact planner-selected local read-only capability."""
    return await local_tool_executor.execute(request)


@app.post("/tool-result/interpret")
async def interpret_tool_result(request: ToolResultInterpretationRequest):
    if tool_result_interpreter is None:
        raise HTTPException(status_code=503, detail="Tool result interpreter is disabled")
    prepared, disclosure = (
        await agent_skill_progressive_disclosure.prepare_tool_result_request(request)
    )
    result = await tool_result_interpreter.interpret(prepared)
    return attach_disclosure_metadata(result, disclosure)


@app.post("/goal-association")
async def resolve_goal_association(request: CognitiveWorkRequest):
    if goal_association_resolver is None:
        raise HTTPException(status_code=503, detail="Goal association resolver is disabled")
    prepared, disclosure = await agent_skill_progressive_disclosure.prepare_agent_request(
        request,
        "goal_association",
    )
    result = await goal_association_resolver.resolve(prepared)
    return attach_disclosure_metadata(result, disclosure)


@app.post("/task-continuity", response_model=SemanticTaskOperationSet)
async def resolve_task_continuity(request: AgentRunRequest) -> SemanticTaskOperationSet:
    if task_continuity_resolver is None:
        raise HTTPException(status_code=503, detail="Task continuity resolver is disabled")
    try:
        return await task_continuity_resolver.resolve(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - final service-boundary guard
        logger.exception(
            "task_continuity_endpoint_degraded sid=%s error_type=%s error=%s",
            request.sid,
            type(exc).__name__,
            exc,
        )
        return SemanticTaskOperationSet(
            confidence=0.0,
            reason_summary="Task continuity service failed safely; no operation was accepted.",
            metadata={
                "resolver": "task_continuity_agent",
                "status": "service_unavailable",
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
                "sid": request.sid,
            },
        )


@app.post(
    "/agent-skills/select",
    response_model=AgentSkillSelectionResolution,
)
async def select_agent_skills(
    request: AgentSkillSelectionRequest,
) -> AgentSkillSelectionResolution:
    """Let the declared Agent role author a typed optional Skill selection."""
    if agent_skill_selection_service is None:
        raise HTTPException(
            status_code=503,
            detail="Agent Skill model selection is disabled",
        )
    try:
        return await agent_skill_selection_service.select(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/agent-skills/disclose",
    response_model=AgentSkillDisclosureResolution,
)
async def disclose_agent_skills(
    request: AgentSkillDisclosureRequest,
) -> AgentSkillDisclosureResolution:
    """Load only exact role projections from a validated model selection."""
    if not settings.agent_skill_progressive_disclosure_enabled:
        raise HTTPException(
            status_code=503,
            detail="Agent Skill progressive disclosure is disabled",
        )
    return agent_skill_disclosure_service.disclose(request)


@app.get("/agent-skills", response_model=AgentSkillRegistrySnapshot)
async def agent_skills() -> AgentSkillRegistrySnapshot:
    """Return bounded metadata only; no Skill body or projection is disclosed."""
    return configured_agent_skill_registry.snapshot()


@app.get("/capabilities")
async def capabilities() -> dict:
    payload = capability_registry.model_dump()
    payload["sources"] = configured_registry.sources
    payload["manifest_files"] = configured_registry.manifest_files
    return payload


@app.get("/capabilities/catalog")
async def capability_catalog_snapshot(refresh: bool = False) -> dict[str, object]:
    return await capability_catalog.snapshot(refresh=refresh)


@app.post("/capabilities/search", response_model=CapabilitySearchResult)
async def capability_search(request: CapabilitySearchRequest) -> CapabilitySearchResult:
    return await capability_catalog.search(
        request.text,
        language=request.language,
        limit=request.limit,
        refresh=request.refresh,
        prefer_interaction_executable=request.prefer_interaction_executable,
    )


@app.get("/capabilities/llm-context")
async def capability_llm_context(
    language: str = "en",
    text: str | None = None,
    limit: int = 20,
) -> dict[str, str]:
    return {
        "context": await capability_catalog.llm_context(
            text=text,
            language=language,
            limit=max(1, min(limit, 64)),
        )
    }


@app.post("/task-graphs/validate", response_model=TaskGraphValidationResponse)
async def validate_task_graph(graph: TaskGraph) -> TaskGraphValidationResponse:
    return task_graph_service.validate(graph)


@app.post("/task-graphs/dry-run", response_model=ExecutionTrace)
async def dry_run_task_graph(
    request: TaskGraphDryRunRequest,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_task_graph_diagnostics_auth(authorization)
    try:
        return task_graph_service.dry_run(request.graph, auto_confirm=request.auto_confirm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/task-graphs/execute-read-only", response_model=ExecutionTrace)
async def execute_read_only_task_graph(request: TaskGraphExecuteRequest) -> ExecutionTrace:
    try:
        return await task_graph_service.execute_read_only(request.graph)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/task-graphs/execute-planning", response_model=ExecutionTrace)
async def execute_planning_task_graph(request: TaskGraphExecuteRequest) -> ExecutionTrace:
    try:
        return await task_graph_service.execute_planning(request.graph)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/task-graphs/execute-guarded", response_model=ExecutionTrace)
async def execute_guarded_task_graph(
    request: TaskGraphGuardedExecuteRequest,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_task_graph_execution_auth(authorization)
    try:
        return await task_graph_service.execute_guarded(
            request.graph,
            request.confirmation_grant,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/task-graphs/confirmation-grants",
    response_model=TaskGraphConfirmationGrantResponse,
)
async def create_task_graph_confirmation_grant(
    request: TaskGraphConfirmationGrantRequest,
    authorization: str | None = Header(default=None),
) -> TaskGraphConfirmationGrantResponse:
    require_task_graph_execution_auth(authorization)
    try:
        return task_graph_service.issue_confirmation_grant(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/task-graphs/{graph_id}/cancel",
    response_model=TaskGraphCancelResponse,
)
async def cancel_task_graph(
    graph_id: str,
    authorization: str | None = Header(default=None),
) -> TaskGraphCancelResponse:
    require_task_graph_execution_auth(authorization)
    return task_graph_service.cancel_execution(graph_id)


@app.get("/task-graphs/{graph_id}/trace", response_model=ExecutionTrace)
async def get_task_graph_trace(
    graph_id: str,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_task_graph_diagnostics_auth(authorization)
    trace = task_graph_service.get_trace(graph_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No TaskGraph trace found for {graph_id!r}")
    return trace


@app.get("/task-graphs/scheduler/status", response_model=TaskGraphSchedulerStatus)
async def get_task_graph_scheduler_status(
    authorization: str | None = Header(default=None),
) -> TaskGraphSchedulerStatus:
    require_task_graph_diagnostics_auth(authorization)
    return task_graph_service.scheduler_status()


@app.post("/run", response_model=AgentResult)
async def run_agent(request: AgentRunRequest) -> AgentResult:
    start = time.perf_counter()
    result = await runtime.run(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "agent sid=%s route=%s intent=%s status=%s agents=%s actions=%d speak_immediate=%d speak_after=%d ms=%.1f",
        request.sid,
        request.route_decision.route,
        request.route_decision.intent,
        result.status,
        ",".join(result.handled_by),
        len(result.actions),
        len(result.speak_immediate),
        len(result.speak_after),
        elapsed_ms,
    )
    result.trace.append(f"runtime: total_ms={elapsed_ms:.1f}")
    return result


@app.post("/interaction", response_model=InteractionResponse)
async def run_interaction(request: AgentRunRequest) -> InteractionResponse:
    start = time.perf_counter()
    try:
        response = await interaction_output.run(request)
    except NativeInteractionOutputError as exc:
        logger.exception(
            "native_interaction_validation_failed sid=%s route=%s intent=%s fallback=%s",
            request.sid,
            request.route_decision.route,
            request.route_decision.intent,
            settings.native_interaction_fallback,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    response.metadata["runtime_ms"] = round(elapsed_ms, 1)
    logger.info(
        "interaction sid=%s route=%s intent=%s status=%s output_mode=%s speech=%d skills=%d confirmation=%s ms=%.1f",
        request.sid,
        request.route_decision.route,
        request.route_decision.intent,
        response.status,
        response.metadata.get("interaction_output_mode"),
        len(response.speech),
        len(response.skills),
        response.requires_confirmation,
        elapsed_ms,
    )
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
