# Chromie Router

`chromie-router` is a CPU-only routing service on port `8091` by default. It is
Chromie's robot-brain router: it turns user text and bounded session context
into a validated `RouteDecision` that lets downstream agents produce voice
and/or body actions. It never opens audio devices, performs speech recognition
or synthesis, invokes skills, or controls hardware.

## Processing modes

```text
text + bounded context
  -> emergency filter: deterministic interrupt/noise safety rules
  -> optional post-interrupt semantic review after an interrupt is applied
  -> shared Agent capability catalog snapshot/search for ability context
  -> quick intent router: qwen-class semantic understanding with compact unlocked common catalog
  -> route validation guardrails for impossible/unsafe choices
  -> deep_thought handoff with full catalog when quick confidence is low or planning is needed
  -> schema finalization
  -> RouteDecision
```

Supported modes:

- `rules_only` — hard interrupt/noise rules, then a deterministic safe fallback; it is compatibility-only and does not choose normal catalog actions;
- `hybrid` — hard interrupt/noise rules first, then Ollama quick routing for normal intent, with deterministic validators afterward;
- `llm_only` — use Ollama for normal routing without the hybrid compatibility
  fallback; deterministic emergency filtering and schema/policy validation
  still run before and after the model.

`ROUTER_USE_LLM=1` selects `hybrid` unless `ROUTER_MODE` is explicitly set.
That default uses the small `ROUTER_MODEL` as a fast semantic route classifier
while `AGENT_MODEL` remains the larger deep-thinking/conversation model.
Operational interruption/noise handling remains deterministic even when a
conversational model is available. The hard filter lives in
`router/app/rules.py` and is limited to `interrupt` and `ignore` outputs,
including obvious repeated filler or acknowledgment ASR hallucinations. Normal
language understanding is handled by the catalog-aware Router model and later
validators, not by phrase rules, regex action parsers, or hardcoded skill-alias
tables. In `hybrid` and `llm_only`, the quick Router prompt receives
`common_ability_catalog`/`common_ability_ids` as the compact unlocked common
ability menu for the small Qwen-class model. Rare, full-catalog, and
`prompt_tier_locked` safety-sensitive abilities are delegated to deepthinking
rather than treated as immediate fast-router actions. Per-query catalog search
matches are not part of the fast Router decision surface. The
Agent repeats catalog validation inside native
InteractionRuntime, so Router unavailability cannot authorize or suppress
execution by itself.

The Router model is a proposer, not the authority. A model route must still pass
catalog constraints, confidence policy, schema finalization, Agent validation,
host Skill Runtime authorization, and Soridormi provider checks before anything
meaningful can execute. See
[`../docs/MODEL_ASSISTED_ROUTING_GUARDRAILS.md`](../docs/MODEL_ASSISTED_ROUTING_GUARDRAILS.md).
If the quick model returns a deterministic-only route such as `interrupt` or
`ignore` after the emergency filter has already passed, Router treats that as a
model mistake. The review model may correct it semantically; if review fails,
Router falls back to safe chat instead of stopping, ignoring, or executing
catalog motion. Low-confidence normal decisions delegate to `deep_thought`
rather than being recovered by a catalog action rule.

The Router has four decision stages. Only the first stage may use phrase rules
to determine a route:

| Stage | What handles it | Purpose |
|---|---|---|
| Emergency filter | Deterministic Router rules | Stop, cancel, emergency-style interruption, silence, unusable audio, repeated filler hallucinations, and obvious noise. |
| Post-interrupt review | Review model after the interrupt has already been applied | Confirm the stop/cancel interpretation or propose a corrected non-interrupt task when ASR/wording was misheard. |
| Quick intent | Common compact catalog plus fast LLM router, normally `qwen3:4b` warmed at Router startup | Understand normal requests, combine voice/body/tool intent, use bounded memory/context, and propose one or more supported common routes/capability tasks by meaning. |
| Deep thought | Agent `deepthinking_agent` using the larger Agent model and full catalog | Split complex tasks, plan, debug, revise/supersede quick proposals, and answer using bounded session memory when the quick router is low confidence or explicitly chooses `deep_thought`. |

Deterministic route validation sits between those stages as a guardrail, not as
another understanding layer. Validators may reject, repair, or clarify
impossible and unsafe model outputs, but they must not answer the user or select
normal chat, tool, memory, or body intent by phrase matching.

Each stage receives the context produced above it. The quick intent prompt gets
the emergency-filter result, bounded session/world context,
`common_ability_catalog` as the compact commonly used unlocked ability menu.
The deepthinking Agent receives the final `RouteDecision`, including
quick-route source, confidence, intent, reason, and the full catalog context.

Each stage can also produce task/action proposals. Router now writes those
proposals through the shared `TaskProposal` schema while retaining the original
legacy task-list surface for compatibility:

```text
routes[]                        # preferred multi-route items on RouteDecision
metadata.route_items[]          # JSON mirror for older callers and traces
metadata.route_stage_outputs[]  # emergency_filter / quick_intent / post_interrupt_review / deep_thought
  -> route_items[]              # route items visible at that stage
  -> tasks[] and actions[]      # legacy proposed high-level work from that stage
  -> task_proposals[]           # shared-schema proposals from that stage
metadata.desired_abilities[]    # optional non-executable broad ability proposals
metadata.task_list[]            # legacy merged, priority/stage ordered task list
metadata.task_proposals[]       # preferred shared-schema merged proposals
metadata.route_merge            # merge strategy, final route, selected stage
```

For task continuity, the quick Router model may also propose
`metadata.task_relation`, `metadata.target_task_id`, and
`metadata.task_context_patch`. These fields tell the host whether an utterance
looks like a new task, a continuation, a modification, a closure, side
conversation, or a clarification, and what compact facts should be merged into
the task context. They are advisory only: the Orchestrator task manager owns the
actual task-context write, persistence, confirmation, cancellation, and safety
state.

`RouteDecision.routes[]` is the preferred surface for mixed utterances such as
greeting plus memory plus deep planning. Each route item carries its own
`route`, `intent`, `confidence`, `lane`, and `context_profile`. The fast Router
uses `fast_minimal` for simple immediate speech, `session_compact` for ordinary
chat/memory/tool work, `capability_safety` for Skill Runtime work, and
`full_mind` when worldview, lifeview, valueview, identity principles, risk
judgment, or long-horizon planning should be handled by deepthinking. Route
items or the top-level decision may carry `fast_speech`. A bare string and
partially structured object remain accepted only for wire compatibility; they
do not authorize immediate playback. On the top-level decision, non-empty
`fast_speech.text` may still fill the compatibility `speak_first` field when
that field is absent. Dynamic playback is default-off in the Orchestrator. If
`ORCH_ROUTER_GENERATED_FAST_SPEECH_ENABLED=1`, it still requires a structured
object containing safe `text`, an allowed process `purpose`, a non-terminal
`commitment`, and `must_not_claim_completion=true`. It must not claim a tool
result, memory commit, physical execution, or final answer. Compatibility chat
items may still parse `lane=immediate_speech`, `direct_to_tts=true`, and short
`text`, but those markers alone are not playback authority. Host-validated
`metadata.response_plan` immediate speech and startup-cached Orchestrator cues
use separate trusted paths.

`RouteDecision.actions` remains the compatibility/execution hint for concrete
capability actions inside robot-action work, such as ordered Soridormi skill
requests or a `chromie.speak` speech skill embedded in a physical task. The
quick Router may emit this array directly when a compound request is made from
unlocked common catalog skills; that is why “quick” means small model plus
compact unlocked common catalog, not “single task only.”
Missing, planned, or unsupported human-like abilities must not appear in
`actions`; the Router may preserve them in `metadata.desired_abilities` and
delegate or clarify.
Each action may carry its own 0.0-1.0 `confidence`; if any required compound
action is below the Router threshold, the route delegates to `deep_thought`
rather than executing the high-confidence subset. See
[`docs/QUICK_ROUTER_TASK_PLANNING.md`](../docs/QUICK_ROUTER_TASK_PLANNING.md).
The merged `task_proposals` surface is broader: it can include emergency
cancellation, thinking acknowledgement, deepthinking work, speech, memory, tool,
skill-execution proposals, and `state=missing_ability` ability proposals.
`task_list` remains present for older diagnostics. The Agent and Skill Runtime
still validate every executable item against registered capabilities and safety
policy.

When the emergency filter triggers `interrupt`, the host may already have
cancelled current output or motion before slower semantic review finishes. If
`ROUTER_POST_INTERRUPT_REVIEW_ENABLED=1`, Router can attach
`metadata.post_interrupt_review`. A confirmed review adds no duplicate stop
task. A corrected review keeps the original urgent stop tasks and adds a normal
validated follow-up proposal in `metadata.post_interrupt_decision`; the
Orchestrator may run that corrected route after the interrupt, but it must not
resume interrupted physical work without the normal Agent/Skill validation and
confirmation path.

## Current route list

| Route | Purpose |
|---|---|
| `chat` | Normal conversation and questions that do not need tools. |
| `deep_thought` | Complex reasoning or planning delegated to `deepthinking_agent` with session working memory. |
| `robot_action` | Listed body, head, gaze, motion, or expression skill selected from available capabilities. |
| `tool` | External information or planning tools, such as web/weather/API work. |
| `memory` | User asks Chromie to remember or update a preference/fact. |
| `clarify` | The request is ambiguous or outside current bounded abilities. |
| `interrupt` | Stop/cancel/shut up/emergency-style operational controls. |
| `ignore` | Empty, noisy, accidental, repeated filler, or unusable ASR input. |

When LLM routing is enabled, the prompt tells the model to consider:

- the compact listed skill catalog as Chromie's fast-router ability menu;
- the unlocked common ability catalog snapshot, not per-query catalog matches;
- bounded memory and context such as `session_memory`, pending tasks, robot
  state, position, and user preferences;
- speech plus body intent, with speech represented as `chromie.speak` when it is
  part of a physical task;
- safety boundaries: memory is not authorization, and the model must not invent
  capabilities or low-level robot controls.

The maintained Router prompt follows the project-wide prompt context group
shape documented in [`../docs/chromie_mind.md`](../docs/chromie_mind.md):
Global Context Group, Session Context Group, Current Job, Task Context Group,
Cost Function, and Output Contract. Turn-specific targets belong in Current Job
or Task Context rather than at the top of the prompt.

## HTTP API

- `GET /health` — active mode, model, Ollama URL, and rules-first flag
- `GET /routes` — route, lane, mode, and specialized-agent identifiers known by the service
- `POST /route` — produce one `RouteDecision`

Example:

```bash
curl -s http://127.0.0.1:8091/route \
  -H 'Content-Type: application/json' \
  -d '{
    "sid": "demo",
    "text": "转过来看着我",
    "language": "zh-CN",
    "context": {"is_speaking": false, "robot_state": {"is_moving": false}}
  }' | jq
```

A route decision is advisory control-plane data. It does not authorize or
execute a tool, named skill, or physical action.

## Configuration

```env
ROUTER_HOST=0.0.0.0
ROUTER_PORT=8091
ROUTER_MODE=hybrid
ROUTER_USE_LLM=1
ROUTER_OLLAMA_URL=http://chromie-llm:11434
ROUTER_MODEL=qwen3:4b
ROUTER_REVIEW_MODEL=gemma4:e2b
ROUTER_TIMEOUT_MS=5400
ROUTER_LLM_TIMEOUT_MS=5400
ROUTER_LLM_NUM_PREDICT=512
ROUTER_LLM_KEEP_ALIVE=24h
ROUTER_WARM_LLM_ON_STARTUP=1
ROUTER_WARM_LLM_TIMEOUT_MS=60000
ROUTER_REVIEW_TIMEOUT_MS=2500
ROUTER_CONFIDENCE_THRESHOLD=0.55
ROUTER_CAPABILITY_CATALOG_URL=http://chromie-agent:8092
ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS=400
ROUTER_CAPABILITY_CATALOG_CACHE_TTL_MS=5000
ROUTER_CAPABILITY_MATCH_LIMIT=8
ROUTER_POST_INTERRUPT_REVIEW_ENABLED=0
ROUTER_SLOW_REVIEW_RECOVERY_ENABLED=1
ROUTER_LOG_LEVEL=INFO
```

Deterministic interrupt, stop, silence, and unusable-audio handling always runs
first and cannot be disabled by configuration.

In the normal hybrid path, non-emergency natural-language understanding belongs
to the quick Router model and low-confidence quick decisions delegate to
`deep_thought`.

The host Orchestrator normally connects through:

```env
ROUTER_URL=http://127.0.0.1:8091
```

See [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) for precedence and
profile behavior.

## Start

Use the repository-level service launcher:

```bash
./scripts/start_services.sh
```

For local development from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r router/requirements.txt
PYTHONPATH=router uvicorn app.main:app --host 0.0.0.0 --port 8091
```
