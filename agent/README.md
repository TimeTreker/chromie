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
the trusted Skill Runtime. Soridormi owns embodied planning, execution policy,
resource exclusivity, cancellation, emergency behavior, and hardware
commissioning.

`POST /interaction` now uses `InteractionRuntime` by default. Specialized agents
write through a native accumulator that creates `InteractionSpeech` and
`SkillRequest` objects as the pipeline runs; the endpoint does not convert a
final `AgentResult`. The serialized result is validated again against the strict
shared contract before it is returned.

`AgentResultInteractionAdapter` remains available for rollback through
`AGENT_INTERACTION_OUTPUT_MODE=legacy-adapter`. Native validation fallback is
separate and default-off; enable it only with
`AGENT_NATIVE_INTERACTION_FALLBACK=1`.

## Specialized agents

| Agent | Current behavior |
|---|---|
| `conversation_agent` | Produces short conversational speech with Ollama or deterministic fallback behavior. |
| `deepthinking_agent` | Handles `deep_thought` requests by using session working memory to split complex tasks, plan, debug, and produce a spoken final answer. |
| `speaker_agent` | Normalizes wording, brevity, and speaking style. It never plays audio. |
| `robot_pose_controller_agent` | Legacy compatibility-only phrase parser for old `/run` callers; disabled unless `context.allow_legacy_rule_agents=true`. |
| `motion_planner_agent` | Legacy compatibility-only phrase parser for old `/run` callers; disabled unless `context.allow_legacy_rule_agents=true`. |
| `safety_agent` | Rejects or clamps unsafe action proposals. |
| `tool_agent` | Handles read-only weather lookup directly; produces a validated TaskGraph when LLM TaskGraph planning is enabled; otherwise emits a compatibility `tool.*` action that this repository does not automatically execute. |
| `memory_agent` | Produces refined `extracted_memory` updates plus compatibility `memory.store` actions. Chromie's current conversation state is process-local and not a durable memory store. |
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
- `POST /run`
- `POST /interaction`

Catalog entries include `prompt_tier`, `prompt_tier_locked`,
`prompt_tier_source`, and `prompt_tier_reason`. Unlocked `common` entries are
compacted into the fast Router prompt; `rare` and safety-locked entries stay
available to deepthinking and other full-catalog planning paths. The initial
common/rare preset lives in `capabilities/prompt_tiers.json`, loaded by
`AGENT_CAPABILITY_PROMPT_TIER_PRESET`; it should be edited as data rather than
as Python code. Experience can change ordinary prompt tiers through an overlay
loaded by `AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES`, but safety-locked entries
cannot be promoted into the fast common catalog. `chromie.speak` is a common,
interaction-executable catalog entry so the quick Router can keep spoken parts
of physical requests as normal skill proposals instead of dropping them into
unstructured reply text.
When Router compound `actions[]` include per-action confidence, the native
runtime preserves it in each emitted `SkillRequest.metadata` as
`router_action_confidence` for trace and evidence review.

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

Risk-bearing behavior is default-off.

| Variable | Default | Effect |
|---|---:|---|
| `AGENT_RESPONSE_REVIEW_ENABLED` | `0` | Use a model critic to accept or rewrite spoken replies. Enable for stricter review; leave off for realtime latency. |
| `AGENT_RESPONSE_REVIEW_MODEL` | `gemma4:e2b` | Semantic reviewer model; defaults to the main Agent model so weak replies are judged with enough context. |
| `AGENT_RESPONSE_REVIEW_TIMEOUT_MS` | `4000` | Timeout for the semantic response-review call. |
| `AGENT_RESPONSE_REVIEW_MODE` | `auto` | In `auto`, skip the extra spoken-response review for clearly low-risk chat replies while still reviewing task/capability/action-risk replies. Use `always` for diagnostics. |
| `AGENT_SOCIAL_ATTENTION_MODE` | `off` | Model-authored optional social-attention policy: `off`, `report_only`, `sim_only`, or `on`. The model may select a bounded named gesture or `none`; runtime validates target evidence, schemas, resources, and confirmation policy. |
| `AGENT_SOCIAL_ATTENTION_MODEL` | `qwen3:4b` | Dedicated model for structured `SocialAttentionPlan` output. |
| `AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS` | `0` | Deprecated compatibility input retained for diagnostics. Social Attention is never awaited after the primary response; the effective wait is always `0`. |
| `AGENT_SOCIAL_ATTENTION_CAPABILITIES` | social named skills | Exact catalog IDs eligible for model selection; this list does not force any gesture. |
| `AGENT_SOCIAL_ATTENTION_FALLBACK_TARGET` | `none` | Optional installation-calibrated target used only when live perception is absent. |
| `AGENT_EXPRESSIVE_BODY_CUES` | `off` | Deprecated compatibility alias used only when `AGENT_SOCIAL_ATTENTION_MODE` is unset. |
| `AGENT_REQUIRE_CAPABILITY_PLAN_REVIEW` | `0` | Fail closed when semantic review is unavailable for an executable robot action; exact Router capability substitutions require a reviewer revision. Enable for stricter review. |
| `AGENT_CONVERSATION_NUM_CTX` | `2048` | Context window for normal conversation prompts. |
| `AGENT_CONVERSATION_NUM_PREDICT` | `64` | Output budget for normal conversation replies. |
| `AGENT_DEEPTHINKING_NUM_CTX` | `8192` | Context window for deep-thinking prompts with session memory. |
| `AGENT_DEEPTHINKING_NUM_PREDICT` | `384` | Output budget for deep-thinking replies. |
| `AGENT_INTERACTION_OUTPUT_MODE` | `native` | Select `native` or explicit `legacy-adapter` output for `/interaction`. |
| `AGENT_NATIVE_INTERACTION_FALLBACK` | `0` | On native contract-validation failure, opt in to legacy adapter fallback instead of failing closed. |
| `AGENT_CAPABILITY_CATALOG_REFRESH_SEC` | `30` | Refresh live named skills while keeping the last known-good catalog. |
| `AGENT_CAPABILITY_MATCH_MIN_SCORE` | `0.16` | Minimum score for automatic native route correction. |
| `AGENT_CAPABILITY_MATCH_LIMIT` | `8` | Bound candidates sent to capability selection. |
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
| `AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION` | `0` | Enable authorized guarded side effects. Requires an execution token. |
| `AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION` | `0` | Permit physical nodes after confirmation and active-monitor proof. Requires guarded execution. |

See [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) for all settings.

## Model-driven social attention

The native interaction runtime may start a dedicated social-attention planner in
parallel with the main response. The planner receives eligible named social
skills, the dialogue act, recent context, and evidence for the active user
target. It may select subtle gaze, blink, nod, another supplied expression, or
`none`. The plan is advisory until deterministic validation confirms exact
skill IDs, argument schemas, target evidence, availability, resource
compatibility, confirmation policy, and the small latency budget.

Attention skills carry `metadata.auxiliary_social_attention=true`, are excluded
from user task proposals, and are dropped rather than delaying or conflicting
with the primary task. Project defaults remain off. The maintained voice-MuJoCo
launcher enables `sim_only` with a calibrated right-side fallback; a future live
perception target overrides that calibration.

## Capability manifests

`AGENT_CAPABILITY_MANIFESTS` is a comma-separated list of JSON files or
directories. The root Compose deployment mounts `./capabilities` read-only at
`/app/capabilities`.

Startup fails on missing files, malformed manifests, unresolved required
environment variables, duplicate capability identifiers, or incompatible
registry content. This is intentional: runtime policy must not silently diverge
from deployment configuration.

The checked-in Soridormi snapshot is materialized from Soridormi's authoritative
export and pinned to upstream commit
`4afb4bc6411db4a4194e97349d9466a62efd2f24`. See
[`../capabilities/README.md`](../capabilities/README.md).

## TaskGraph behavior

TaskGraph planning and execution are separate operations. A graph returned from
the legacy `/run` path in `AgentResult.task_graphs` is not automatically
dispatched by the Agent service. The native `/interaction` path emits planned
graphs as `chromie.task_graph.execute` Skill Runtime requests; the host
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
- The host Skill Runtime maps failed or cancelled TaskGraph traces back to
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
M13 uses this only for the hidden `test_control` surface.

The Agent's direct Ollama client ignores ambient host proxy variables so
Compose-local model traffic cannot be redirected through an unreachable proxy.

The default acceptance uses safe status/planning behavior and does not authorize
physical motion. `--task-agent-bridge` exercises the no-motion
`soridormi.task.*` contract and requires declared no-motion task capability
before preview/submit. Additional guarded dry-run and
runtime-cancellation modes are documented in
[`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md).

## Next task-agent direction

The next implementation work is Chromie routing into Soridormi-declared
no-motion task types, not low-level motion code. The paired Soridormi manifest
already declares bounded locomotion, attention, gesture, sequence, stop,
safe-idle, and planning-hold task surfaces; navigation, approach, and delivery
remain structured refusals. Chromie can add routing, TaskGraph, and Skill
Runtime tests that submit and monitor only those declared contracts while
preserving Soridormi refusal metadata. Motion-control model training is
deferred until Soridormi has a selected target body or simulator, calibration
and telemetry, task-level metrics, and safety envelopes.

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
