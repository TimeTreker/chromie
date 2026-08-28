from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, ORJSONResponse

from .settings import (
    GoalInterpreterSettings,
    Settings,
    agent_service_settings as settings,
    goal_interpreter_settings,
)
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
    )
    from shared.chromie_contracts.user_turn import (
        AttentionReviewRequest,
        AttentionReviewResult,
        CoreTurnRequest,
    )
from .goal_association import GoalAssociationResolver
from .fast_planner import FastPlannerResolver
from .deep_planner import DeepPlannerResolver
from .reflection import ReflectionResolver
try:
    from chromie_contracts.reflection import ReflectionRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.reflection import ReflectionRequest
from .social_attention import (
    SocialAttentionContextBuilder,
    SocialAttentionPlanner,
    SocialAttentionServices,
)
from .schema import HealthResponse
from .cognitive_core.goal_interpreter import (
    GoalInterpretationRequest,
    initialize_goal_interpreter,
    interpret_goal,
)
from .cognitive_core.goal_interpreter.errors import InterpretationUnavailableError
from .work_dag import (
    ExecutionTrace,
    WorkDAG,
    WorkDAGCancelResponse,
    WorkDAGConfirmationGrantRequest,
    WorkDAGConfirmationGrantResponse,
    WorkDAGDryRunRequest,
    WorkDAGExecuteRequest,
    WorkDAGGuardedExecuteRequest,
    DAGEngineStatus,
    DAGEngineService,
    WorkDAGValidationResponse,
)
from .tool_invocation import McpStreamableHttpInvoker

try:
    from chromie_contracts.semantic_authority import semantic_authority_route_matrix
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.semantic_authority import semantic_authority_route_matrix





logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.agent")


def _fast_first_response_context_window(
    service_settings: Settings,
    interpreter_settings: GoalInterpreterSettings,
) -> int:
    if service_settings.cognitive_budget_profile == "qualification":
        return service_settings.fast_planner_num_ctx
    # Prefer exact reuse of the Fast or GI runner. A dedicated response model is
    # intentionally bounded; it must not inherit a large context merely because
    # the same weights are also assigned to a deliberative role.
    if (
        service_settings.fast_first_response_model
        == service_settings.fast_planner_model
    ):
        return service_settings.fast_planner_num_ctx
    if service_settings.fast_first_response_model == interpreter_settings.model:
        return interpreter_settings.llm_num_ctx
    return min(service_settings.fast_planner_num_ctx, 6144)

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
social_attention_services = SocialAttentionServices(
    social_attention_mode=settings.social_attention_mode,
    social_attention_ollama=social_attention_client,
    social_attention_num_ctx=settings.social_attention_num_ctx,
    social_attention_num_predict=settings.social_attention_num_predict,
    social_attention_max_behaviors=settings.social_attention_max_behaviors,
    social_attention_capability_ids=settings.social_attention_capability_ids,
    capability_catalog=capability_catalog,
)
social_attention_context_builder = SocialAttentionContextBuilder(social_attention_services)
social_attention_planner = SocialAttentionPlanner(social_attention_services)
read_only_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_read_only_dag_execution
    else None
)
planning_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_planning_dag_execution
    else None
)
if settings.enable_physical_dag_execution and not settings.enable_guarded_dag_execution:
    raise ValueError(
        "AGENT_ENABLE_GUARDED_DAG_EXECUTION is required when physical WorkDAG execution is enabled"
    )
if settings.enable_guarded_dag_execution and not settings.dag_engine_execution_token:
    raise ValueError(
        "AGENT_DAG_ENGINE_EXECUTION_TOKEN is required when guarded WorkDAG execution is enabled"
    )
guarded_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_guarded_dag_execution
    else None
)
work_dag_service = DAGEngineService(
    capability_registry,
    read_only_invoker=read_only_invoker,
    planning_invoker=planning_invoker,
    guarded_invoker=guarded_invoker,
    allow_physical_motion=settings.enable_physical_dag_execution,
    enable_parallel_execution=settings.enable_parallel_dag_execution,
    max_concurrency=settings.dag_engine_max_concurrency,
    trace_max_entries=settings.dag_engine_trace_max_entries,
    trace_ttl_s=settings.dag_engine_trace_ttl_sec,
    grant_max_entries=settings.dag_engine_grant_max_entries,
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
fast_first_response_client = (
    fast_planner_client
    if settings.use_llm
    and settings.fast_planner_enabled
    and settings.fast_first_response_model == settings.fast_planner_model
    and settings.fast_first_response_timeout_ms == settings.fast_planner_timeout_ms
    else OllamaClient(
        settings.ollama_url,
        settings.fast_first_response_model,
        timeout_ms=settings.fast_first_response_timeout_ms,
        purpose="fast_planner_first_response",
        service_settings=settings,
    )
    if settings.use_llm and settings.fast_planner_enabled
    else None
)
fast_planner_resolver = (
    FastPlannerResolver(
        fast_planner_client,
        capability_catalog,
        first_response_ollama=fast_first_response_client,
        first_response_num_ctx=_fast_first_response_context_window(
            settings,
            goal_interpreter_settings,
        ),
        num_ctx=settings.fast_planner_num_ctx,
        num_predict=settings.fast_planner_num_predict,
        cognitive_budget_profile=settings.cognitive_budget_profile,
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

app = FastAPI(
    title="Chromie Agent",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)


def require_dag_engine_execution_auth(authorization: str | None) -> None:
    expected = f"Bearer {settings.dag_engine_execution_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid WorkDAG execution authorization")


def require_dag_engine_diagnostics_auth(authorization: str | None) -> None:
    if not settings.dag_engine_diagnostics_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "WorkDAG diagnostics are disabled; configure "
                "AGENT_DAG_ENGINE_DIAGNOSTICS_TOKEN"
            ),
        )
    expected = f"Bearer {settings.dag_engine_diagnostics_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail="invalid WorkDAG diagnostics authorization",
        )


@app.on_event("startup")
async def initialize_cognitive_core() -> None:
    await initialize_goal_interpreter()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    engine = work_dag_service.engine_status()
    return HealthResponse(
        ok=True,
        model=settings.model,
        ollama_url=settings.ollama_url,
        use_llm=settings.use_llm,
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
        read_only_work_dag_execution_enabled=read_only_invoker is not None,
        planning_work_dag_execution_enabled=planning_invoker is not None,
        parallel_work_dag_execution_enabled=(
            settings.enable_parallel_dag_execution
        ),
        dag_engine_max_concurrency=settings.dag_engine_max_concurrency,
        work_dag_active_count=engine.active_count,
        work_dag_waiting_count=engine.waiting_count,
        guarded_work_dag_execution_enabled=guarded_invoker is not None,
        physical_work_dag_execution_enabled=(
            guarded_invoker is not None and settings.enable_physical_dag_execution
        ),
        capability_catalog_enabled=True,
        capability_catalog_version=capability_catalog.version,
        goal_association_enabled=goal_association_resolver is not None,
        goal_association_model=(
            settings.goal_association_model if goal_association_resolver is not None else None
        ),
        fast_planner_enabled=fast_planner_resolver is not None,
        fast_planner_model=(settings.fast_planner_model if fast_planner_resolver is not None else None),
        fast_first_response_model=(
            settings.fast_first_response_model
            if fast_planner_resolver is not None
            else None
        ),
        deep_planner_enabled=deep_planner_resolver is not None,
        deep_planner_model=(settings.deep_planner_model if deep_planner_resolver is not None else None),
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
        "route_matrix": semantic_authority_route_matrix(),
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
            GoalInterpretationRequest(
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
    # Fast Planner authors the first Activity Plan over GI Responsibility refs.
    # Agent Skill disclosure remains deferred; the endpoint may select only the
    # bounded common Capability catalog supplied by the Fast Planner resolver.
    return await fast_planner_resolver.resolve_advance(request)


@app.post("/fast-first-response")
async def resolve_fast_first_response(request: CognitiveWorkRequest):
    if fast_planner_resolver is None:
        raise HTTPException(status_code=503, detail="Fast planner is disabled")
    # This is Fast Planner's latency phase, not a separate response author.
    # Capability selection and parameter completeness remain in /fast-advance.
    return await fast_planner_resolver.resolve_first_response(request)


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
async def resolve_reflection(request: ReflectionRequest):
    if reflection_resolver is None:
        raise HTTPException(status_code=503, detail="Reflection is disabled")
    return await reflection_resolver.resolve(request)


@app.post("/social-attention/plan", response_model=SocialAttentionPlan)
async def plan_social_attention(request: SocialAttentionRequest) -> SocialAttentionPlan:
    """Plan one independent, event-scoped auxiliary Social-Attention proposal."""
    await social_attention_context_builder.prepare(request)
    plan = await social_attention_planner.plan(request)
    if plan is None:
        return SocialAttentionPlan(
            decision="none",
            reason="No eligible Social-Attention proposal was available for this event.",
            metadata={"resolver": "social_attention", "event": request.event},
        )
    return plan


@app.post("/tools/execute", response_model=ToolExecutionResponse)
async def execute_local_tool(request: ToolExecutionRequest) -> ToolExecutionResponse:
    """Execute one exact planner-selected local read-only capability."""
    return await local_tool_executor.execute(request)


@app.post("/goal-association")
async def resolve_goal_association(request: CognitiveWorkRequest):
    if goal_association_resolver is None:
        raise HTTPException(status_code=503, detail="Goal association resolver is disabled")
    return await goal_association_resolver.resolve(request)


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


@app.post("/work-dags/validate", response_model=WorkDAGValidationResponse)
async def validate_work_dag(dag: WorkDAG) -> WorkDAGValidationResponse:
    return work_dag_service.validate(dag)


@app.post("/work-dags/dry-run", response_model=ExecutionTrace)
async def dry_run_work_dag(
    request: WorkDAGDryRunRequest,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_dag_engine_diagnostics_auth(authorization)
    try:
        return work_dag_service.dry_run(request.dag, auto_confirm=request.auto_confirm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/work-dags/execute-read-only", response_model=ExecutionTrace)
async def execute_read_only_work_dag(request: WorkDAGExecuteRequest) -> ExecutionTrace:
    try:
        return await work_dag_service.execute_read_only(request.dag)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/work-dags/execute-planning", response_model=ExecutionTrace)
async def execute_planning_work_dag(request: WorkDAGExecuteRequest) -> ExecutionTrace:
    try:
        return await work_dag_service.execute_planning(request.dag)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/work-dags/execute-guarded", response_model=ExecutionTrace)
async def execute_guarded_work_dag(
    request: WorkDAGGuardedExecuteRequest,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_dag_engine_execution_auth(authorization)
    try:
        return await work_dag_service.execute_guarded(
            request.dag,
            request.confirmation_grant,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/work-dags/confirmation-grants",
    response_model=WorkDAGConfirmationGrantResponse,
)
async def create_work_dag_confirmation_grant(
    request: WorkDAGConfirmationGrantRequest,
    authorization: str | None = Header(default=None),
) -> WorkDAGConfirmationGrantResponse:
    require_dag_engine_execution_auth(authorization)
    try:
        return work_dag_service.issue_confirmation_grant(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/work-dags/{dag_id}/cancel",
    response_model=WorkDAGCancelResponse,
)
async def cancel_work_dag(
    dag_id: str,
    authorization: str | None = Header(default=None),
) -> WorkDAGCancelResponse:
    require_dag_engine_execution_auth(authorization)
    return work_dag_service.cancel_execution(dag_id)


@app.get("/work-dags/{dag_id}/trace", response_model=ExecutionTrace)
async def get_work_dag_trace(
    dag_id: str,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_dag_engine_diagnostics_auth(authorization)
    trace = work_dag_service.get_trace(dag_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No WorkDAG trace found for {dag_id!r}")
    return trace


@app.get("/work-dags/engine/status", response_model=DAGEngineStatus)
async def get_dag_engine_status(
    authorization: str | None = Header(default=None),
) -> DAGEngineStatus:
    require_dag_engine_diagnostics_auth(authorization)
    return work_dag_service.engine_status()




if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
