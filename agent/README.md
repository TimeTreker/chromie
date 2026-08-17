# Chromie Agent

`chromie-agent` is Chromie's containerized reasoning, compatibility-response,
structured-interaction, capability-registry, and TaskGraph service. It listens
on port `8092` by default.

For the authoritative project status, see [`../docs/STATUS.md`](../docs/STATUS.md).
For the complete HTTP surface, see
[`../docs/API_REFERENCE.md`](../docs/API_REFERENCE.md).

## Current implementation boundary

The Agent:

- accepts text, routing decisions, and bounded context;
- returns the established `AgentResult` contract from `POST /run`;
- returns the strict `InteractionResponse` contract from `POST /interaction`;
- loads and validates trusted external capability manifests at startup;
- plans, validates, simulates, and—behind explicit gates—executes TaskGraphs;
- never opens the microphone, plays audio, or controls robot hardware directly.

The host Orchestrator owns realtime audio, conversation state, interruption, and
the Trusted Capability Runtime. Soridormi owns embodied planning, execution policy,
resource exclusivity, cancellation, emergency behavior, and hardware
commissioning.

`POST /interaction` now uses `InteractionRuntime` by default. Specialized agents
write through a native accumulator that creates `InteractionSpeech` and
`CapabilityRequest` objects as the pipeline runs; the endpoint does not convert a
final `AgentResult`. The serialized result is validated again against the strict
shared contract before it is returned.

`AgentResultInteractionAdapter` remains available for rollback through
separate and default-off; enable it only with

## Specialized agents

| Agent | Current behavior |
|---|---|
| `conversation_agent` | Produces short conversational speech with Ollama or deterministic fallback behavior. |
| `deepthinking_agent` | Handles `deep_thought` requests by using session working memory to split complex tasks, plan, debug, and produce a spoken final answer. |
| `speaker_agent` | Normalizes wording, brevity, and speaking style. It never plays audio. |
| `safety_agent` | Rejects or clamps unsafe action proposals. |
| `tool_agent` | Handles read-only weather lookup directly; preserves the canonical resolved place while the provider adapter may use bounded equivalent geocoding forms and typed `location_not_found`; produces a validated TaskGraph when LLM TaskGraph planning is enabled; otherwise emits a compatibility `tool.*` action that this repository does not automatically execute. |
| `memory_agent` | Applies an exact model-authored, schema-validated session-memory proposal. It does not infer memory kind or content from keywords. Chromie's current conversation state is process-local and not a durable memory store. |
| `chromie.memory.retrieve_verified_tool_result` | Read-only Host-runtime capability that retrieves one exact fresh prior tool result after Goal Association has already resolved references and bound material arguments. It never resolves pronouns or performs loose semantic search. Its model-visible result uses a closed envelope and retains the original provider payload as canonical JSON text rather than advertising an unsafe open object schema. |
| `vision_agent` | Produces a compatibility `vision.query` proposal. No vision executor is included in this repository. |

The native capability planner prompt follows the project-wide prompt context
group shape documented in [`../docs/chromie_mind.md`](../docs/chromie_mind.md):
Global Context Group, Session Context Group, Current Job, Task Context Group,
Cost Function, and Output Contract. It uses the owner-approved mind profile as
upper context, then plans only through exact catalog skill IDs and schemas.

## HTTP API

Core endpoints:

- `GET /health`
- `GET /agents`
- `GET /capabilities`
- `GET /capabilities/catalog`
- `POST /capabilities/search`
- `GET /capabilities/llm-context?language=en&text=...`
- `GET /semantic-authority`
- `POST /run`
- `POST /interaction`
- `POST /goal-association`
- `POST /fast-plan`
- `POST /deep-plan`
- `POST /social-attention/plan`
- `POST /compose-response-plan`

Catalog entries include `prompt_tier`, `prompt_tier_locked`,
`prompt_tier_source`, and `prompt_tier_reason`. Unlocked `common` entries are
compacted into the fast Goal Interpretation prompt; `rare` and safety-locked entries stay
available to deepthinking and other full-catalog planning paths. The initial
common/rare preset lives in `capabilities/prompt_tiers.json`, loaded by
`AGENT_CAPABILITY_PROMPT_TIER_PRESET`; it should be edited as data rather than
as Python code. Experience can change ordinary prompt tiers through an overlay
loaded by `AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES`, but safety-locked entries
cannot be promoted into the fast common catalog. The Fast Goal Interpreter sees
this catalog only as bounded ability awareness. It emits provider-neutral
`responsibilities[]`; it does not author Work, Primary Activities, Plan steps,
execution lanes, realization, exact Capability selection, executable arguments, or
action decomposition. Goal Association owns canonical Goal state; Fast/Deep Planner
owns the first Work/Activity contract afterward.
`chromie.speak` therefore does not turn ordinary acknowledgement or requested speech
into a Fast Goal Interpreter skill proposal. Deprecated compatibility requests that
already contain exact `actions[]` may still be materialized by the legacy Agent adapter,
but those fields are not current model-authored Fast Goal Interpretation output.

TaskGraph endpoints:

- `POST /task-graphs/validate`
- `POST /task-graphs/dry-run`
- `POST /task-graphs/execute-read-only`
- `POST /task-graphs/execute-planning`
- `POST /task-graphs/confirmation-grants`
- `POST /task-graphs/execute-guarded`
- `POST /task-graphs/{graph_id}/cancel`
- `GET /task-graphs/{graph_id}/trace`
- `GET /task-graphs/scheduler/status`

Guarded execution, confirmation grants, and cancellation require
`Authorization: Bearer <AGENT_TASK_GRAPH_EXECUTION_TOKEN>`. Dry-run, trace, and
scheduler diagnostics require `AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN`; a blank
diagnostics token falls back to the execution token, and both blank disables
those diagnostic endpoints with HTTP 503. Validation and capability inspection
remain available without that bearer token, so deploy the service only on a
trusted network boundary.

## Feature gates

Risk-bearing task execution remains default-off. Social Attention is maintained
`on` as an optional, bounded interaction policy; it cannot widen task or body
execution authority.

| Variable | Default | Effect |
|---|---:|---|
| `AGENT_SOCIAL_ATTENTION_MODE` | `on` | Embodiment-independent auxiliary interaction gate: `off`, `report_only`, or `on`. It never selects a simulator or physical backend; Soridormi/provider owns backend selection and body safety. See [Social Attention Behavior Domain](../docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md). |
| `AGENT_SOCIAL_ATTENTION_MODEL` | `qwen3:4b` | Dedicated model for structured `SocialAttentionPlan` output. |
| `AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS` | `0` | Deprecated compatibility input retained for diagnostics. Social Attention is never awaited after the primary response; the effective wait is always `0`. |
| `AGENT_SOCIAL_ATTENTION_CAPABILITIES` | social named capabilities | Exact catalog IDs eligible for semantic selection; this list does not force any gesture. |

| `AGENT_CONVERSATION_NUM_CTX` | `2048` | Context window for normal conversation prompts. |
| `AGENT_CONVERSATION_NUM_PREDICT` | `64` | Output budget for normal conversation replies. |
| `AGENT_DEEPTHINKING_NUM_CTX` | `8192` | Context window for deep-thinking prompts with session memory. |
| `AGENT_DEEPTHINKING_NUM_PREDICT` | `384` | Output budget for deep-thinking replies. |
| `AGENT_CAPABILITY_CATALOG_REFRESH_SEC` | `30` | Refresh live named capabilities while keeping the last known-good catalog. |
| `AGENT_CAPABILITY_MATCH_LIMIT` | `8` | Bound the model-neutral catalog preview attached at the native interaction boundary; it does not score user language. |
| `AGENT_CAPABILITY_NUM_CTX` | `24576` | Verification-mode context window for LLM capability selection prompts. Optimize downward only after feasibility and latency evidence are both acceptable. |
| `AGENT_CAPABILITY_NUM_PREDICT` | `512` | Output budget for LLM capability-selection JSON. |
| `AGENT_CAPABILITY_REVIEW_NUM_PREDICT` | `160` | Output budget for semantic capability-plan review JSON. |
| `AGENT_CAPABILITY_PARAMETER_REPAIR_NUM_PREDICT` | `384` | Output budget for the semantic parameter-resolution retry used only when a proposed skill plan fails its supplied schema. |
| `AGENT_ENABLE_TASK_GRAPH_PLANNING` | `0` | Allow LLM-authored TaskGraph planning for tool routes. |
| `AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION` | `0` | Enable side-effect-free read-only execution. |
| `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION` | `0` | Enable stateful `planning_only` execution. |
| `AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION` | `0` | Permit eligible independent nodes to use bounded parallel scheduling. |
| `AGENT_TASK_GRAPH_MAX_CONCURRENCY` | `4` | Process-local scheduler concurrency bound. |
| `AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN` | blank | Protect dry-run, trace, and scheduler endpoints; falls back to the execution token. |
| `AGENT_TASK_GRAPH_TRACE_MAX_ENTRIES` | `128` | Bound retained in-memory traces with LRU eviction. |
| `AGENT_TASK_GRAPH_TRACE_TTL_SEC` | `900` | Expire retained traces after this many seconds. |
| `AGENT_TASK_GRAPH_GRANT_MAX_ENTRIES` | `128` | Bound unconsumed in-memory confirmation grants. |
| `AGENT_WEATHER_ENABLED` | `1` | Enable read-only weather lookup through Open-Meteo. |
| `AGENT_WEATHER_TIMEOUT_S` | `8` | Weather provider HTTP timeout in seconds. |
| `AGENT_EXTERNAL_INFORMATION_ENABLED` | `0` | Enable the provider-neutral grounded external-information adapter. |
| `AGENT_EXTERNAL_INFORMATION_URL` | blank | Exact HTTP endpoint accepting one evidence-retrieval request and returning the declared structured evidence contract. |
| `AGENT_EXTERNAL_INFORMATION_TOKEN` | blank | Optional bearer token sent only to the configured external-information endpoint. |
| `AGENT_EXTERNAL_INFORMATION_TIMEOUT_MS` | `15000` | Provider request timeout. |
| `AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION` | `0` | Enable authorized guarded side effects. Requires an execution token. |
| `AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION` | `0` | Permit physical nodes after confirmation and active-monitor proof. Requires guarded execution. |

See [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) for all settings.

## Model-driven social attention

Social Attention is background social-decoration cognition, not an execution
lane, Goal, fixed gesture list, or Vocal-expression channel. The maintained
Goal-driven Host creates an event-scoped `/social-attention/plan` opportunity only
for a concrete **semantic primary human-observable Activity**: what Chromie is doing,
such as greeting somebody, telling a joke, walking toward a person, singing a song,
handing something over, or showing/playing something. A scheduled pre-Goal Fast
acknowledgement may itself be a concrete conversational Activity while Goal Association
continues. After Goal Association, Responsibility/Goal meaning remains above Activity,
while canonical conversational acts and Plan-step Work provide the concrete Activity
granularity. One Goal may therefore own several Activities; conversely, a sufficiently
high-level provider capability may realize one whole Activity atomically. Provider
readiness, Goal milestones, planning, waiting, evidence arrival, execution-lane
transitions, and Capability identities are not anchors.

`Vocal` and `Activity` are execution lanes. `speech`, `expressive_speech`,
`recitation`, `singing`, `humming`, and `nonverbal_vocalization` are modes of one
personal **Vocal Expression**. Speech transport items, Vocal modes, body/media
requests, Capability IDs, and request IDs therefore live under Activity
`realization`: they say **how** the semantic Activity is being carried out, not
**what** the Activity is. If a Goal is decomposed into “say hello” and “wave”, those
are two semantic Activities even though they share Goal ownership; if a qualified
high-level provider exposes one atomic greeting Activity, it remains one Activity.
The boundary follows canonical Work/Plan/provider granularity, never modality.
`InteractionResponse` is only a coordination envelope, never the Activity ontology. The model does not own Goal
meaning, response wording, completion, or authorization. Accepted Social Attention
body requests execute through the Activity Execution Lane as fail-soft auxiliary
decoration.

Candidate discovery uses catalog behavior-domain metadata supplemented by
`capabilities/behavior_domains.json`; `AGENT_SOCIAL_ATTENTION_CAPABILITIES` is
only an optional operator override. The response schema constrains behavior
`capability_id` to the exact live candidate set. Trusted code still validates
argument schemas, target evidence, availability, resource compatibility,
confirmation policy, and provider concurrency before the same Trusted Capability
Runtime executes any auxiliary behavior.

Auxiliary skills carry `metadata.auxiliary_social_attention=true`,
`metadata.execution_lane=activity`, and `metadata.execution_role=social_decoration`;
they have no Goal-completion authority. They are dropped rather than delaying or conflicting
with speech, emergency handling, or the primary task. A concrete user request
such as "blink twice" remains a normal, non-droppable CanonicalPlan Goal even
though its observable behavior belongs to the same domain. The maintained policy
is `on`;
`report_only` retains advisory plans without body requests and `off` suppresses
auxiliary planning. Target evidence is semantic only. Chromie does not accept installation calibration,
body coordinates, joint targets, or controller parameters in Social Attention
planning; Soridormi resolves the semantic request for its active embodiment.

See [Social Attention Behavior Domain](../docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md).

## Capability manifests

`AGENT_CAPABILITY_MANIFESTS` is a comma-separated list of JSON files or
directories. The root Compose deployment mounts `./capabilities` read-only at
`/app/capabilities`.

Startup fails on missing files, malformed manifests, unresolved required
environment variables, duplicate capability identifiers, or incompatible
registry content. This is intentional: runtime policy must not silently diverge
from deployment configuration.

The checked-in Soridormi snapshot is materialized from Soridormi's authoritative
export and pinned to the exact `metadata.upstream_commit` recorded in
`capabilities/soridormi.json`. See
[`../capabilities/README.md`](../capabilities/README.md).

## TaskGraph behavior

TaskGraph planning and execution are separate operations. A graph returned from
the legacy `/run` path in `AgentResult.task_graphs` is not automatically
dispatched by the Agent service. The native `/interaction` path emits planned
graphs as `chromie.task_graph.execute` Capability Runtime requests; the host
Orchestrator can dispatch those to the Agent's planning executor when
`AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1`, and otherwise the request fails
closed.

- Validation resolves every node against the active registry.
- Dry-run simulates policy and dependency behavior without remote MCP calls.
- Read-only execution accepts only eligible side-effect-free capabilities.
- Planning execution additionally accepts stateful `planning_only` capabilities.
- Guarded execution requires explicit authorization, graph-bound confirmation,
  and the capability's safety policy.
- Physical execution additionally requires an active covering monitor and an
  emergency fallback.
- Parallel execution is bounded and honors `can_run_parallel` and
  `exclusive_group`; physical work remains sequential.
- Execution traces keep the planner `summary` and add a deterministic
  `outcome_summary` from node results for report/speech use. Failed or
  aborted traces also include advisory `residual_replan` context so a future
  planner can preserve completed work and replan only the remaining safe goal.
- Planning execution can run `chromie.report` as a trace-only local fallback;
  audible `chromie.speak` stays outside the planning lane.
- LLM-planned Soridormi task-submit nodes receive a default trace-only report
  fallback when the model omits an explicit failure fallback.
- The Trusted Capability Runtime maps failed or cancelled TaskGraph traces back to
  failed/cancelled `chromie.task_graph.execute` results and suppresses
  completion speech after graph failure.
- Traces and confirmation grants are retained in process memory only. Traces
  have configurable TTL/LRU bounds; grants have a configurable capacity and
  purge expired entries before issue/consume.

Detailed semantics are in
[`../docs/agent_task_graph.md`](../docs/agent_task_graph.md) and
[`../docs/task_graph_concurrency_decision.md`](../docs/task_graph_concurrency_decision.md).

## Soridormi verification

From the `agent` directory with development dependencies installed:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=. python -m app.probe_capabilities \
  --manifest ../capabilities/soridormi.json

SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=. python -m app.soridormi_acceptance \
  --manifest ../capabilities/soridormi.json

SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=. python -m app.soridormi_acceptance \
  --manifest ../capabilities/soridormi.json \
  --task-agent-bridge
```

The probe checks the complete manifest by default. Acceptance workflows that
intentionally target a smaller surface may repeat `--exclude-effect EFFECT`;
The voice-interaction acceptance runner uses this only for the hidden `test_control` surface.

The Agent's direct Ollama client ignores ambient host proxy variables so
Compose-local model traffic cannot be redirected through an unreachable proxy.

The default acceptance uses safe status/planning behavior and does not authorize
physical motion. `--task-agent-bridge` exercises the no-motion
`soridormi.task.*` contract and requires declared no-motion task capability
before preview/submit. Additional guarded dry-run and
runtime-cancellation modes are documented in
[`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md).

## Current Soridormi capability direction

Chromie plans only across Soridormi's advertised semantic capabilities, not
low-level motion code. The paired provider currently declares bounded locomotion,
attention, gesture, sequence, stop, safe-idle, planning-hold, and a complete
`acquire_and_deliver_resource` leaf. That resource leaf is explicitly a
simulation-only scripted/mock implementation; its internal navigation,
acquisition, carrying, and handover stages stay provider-owned. Smaller real
navigation, perception, grasp, or delivery leaves remain unavailable unless the
provider later advertises and qualifies them. A different body backend changes
Soridormi commissioning and safety evidence, not Chromie's Goal or Planner shape.

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r agent/requirements.txt
PYTHONPATH=agent uvicorn app.main:app --host 0.0.0.0 --port 8092
```

The service can run with `AGENT_USE_LLM=0`; deterministic fallbacks remain
available for control-plane testing.

## Build the container

The Dockerfile requires the repository root as build context:

```bash
docker build -f agent/Dockerfile -t chromie-agent .
```

Normally start the complete service set through:

```bash
./scripts/start_services.sh
```

## Known limitations

- Native `/interaction` output and host request-bound confirmation are
  implemented; retained automatic and reviewed reference-host microphone
  evidence remain open.
- Tool, memory, and vision compatibility actions are proposals, not built-in executors.
- TaskGraph scheduler, grants, and traces are process-local rather than durable or distributed.
- Cross-process robot exclusivity is enforced by Soridormi, not by the Agent's local scheduler.
- Enabling physical execution is not equivalent to hardware commissioning or target acceptance.

## Compatibility planner semantic boundary

The emergency-only legacy CapabilityAgent preserves the exact named capability chosen
by its model and validates arguments only against that skill's advertised schema.
It does not replace `soridormi.look_direction` with
`soridormi.look_at_person`, reinterpret yaw/pitch fields, or silently clamp one
skill into another provider contract.

## Agent semantic contracts

The Agent implementation is further specified by these owned contracts:

- [Agent Skills Architecture](../docs/AGENT_SKILLS_ARCHITECTURE.md)
- [Goal-Driven Cognitive Architecture](../docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Goal-Driven Cognitive Architecture](../docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Tool Result Interpretation](../docs/TOOL_RESULT_INTERPRETATION.md)
- [Adding Agent Capabilities](../docs/ADDING_AGENT_CAPABILITIES.md)
