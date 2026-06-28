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
  -> shared Agent capability-catalog search for ability context
  -> quick intent router: qwen-class semantic understanding with catalog bounds
  -> route validation guardrails for impossible/unsafe choices
  -> deep_thought handoff when quick confidence is low or planning is needed
  -> schema finalization
  -> RouteDecision
```

Supported modes:

- `rules_only` — hard interrupt/noise rules, capability-catalog routing, then a deterministic fallback;
- `hybrid` — hard interrupt/noise rules first, then Ollama quick routing for normal intent, with deterministic validators afterward;
- `llm_only` — send routing decisions directly to Ollama.

`ROUTER_USE_LLM=1` selects `hybrid` unless `ROUTER_MODE` is explicitly set.
That default uses the small `ROUTER_MODEL` as a fast semantic route classifier
while `AGENT_MODEL` remains the larger deep-thinking/conversation model.
Operational interruption/noise handling remains deterministic even when a
conversational model is available. The hard filter lives in
`router/app/rules.py` and is limited to `interrupt` and `ignore` outputs,
including obvious repeated filler or acknowledgment ASR hallucinations. Normal
language understanding is handled by the catalog-bounded Router model and later
validators, not by phrase rules, regex action parsers, or hardcoded skill-alias
tables. In `hybrid` and `llm_only`, catalog search supplies current ability
descriptions and schemas to the model; it does not choose normal robot actions
by itself. The Agent repeats the same catalog search inside native
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

The Router has three decision stages. Only the first stage may use phrase rules
to determine a route:

| Stage | What handles it | Purpose |
|---|---|---|
| Emergency filter | Deterministic Router rules | Stop, cancel, emergency-style interruption, silence, unusable audio, repeated filler hallucinations, and obvious noise. |
| Quick intent | Catalog search plus small LLM router, normally `qwen3:0.6b` | Understand normal requests, combine voice/body/tool intent, use bounded memory/context, and select supported routes/capabilities. |
| Deep thought | Agent `deepthinking_agent` using the larger Agent model | Split complex tasks, plan, debug, and answer using bounded session memory when the quick router is low confidence or explicitly chooses `deep_thought`. |

Deterministic route validation sits between those stages as a guardrail, not as
another understanding layer. Validators may reject, repair, or clarify
impossible and unsafe model outputs, but they must not answer the user or select
normal chat, tool, memory, or body intent by phrase matching.

Each stage receives the context produced above it. The quick intent prompt gets
the emergency-filter result, bounded session/world context, and catalog
candidates. The deepthinking Agent receives the final `RouteDecision`, including
quick-route source, confidence, intent, reason, and candidate capabilities.

Each stage can also produce task/action proposals. Router merges those proposals
into `RouteDecision.metadata.task_list` while retaining the original per-stage
records in `RouteDecision.metadata.route_stage_outputs`:

```text
metadata.route_stage_outputs[]  # emergency_filter / quick_intent / deep_thought
  -> tasks[] and actions[]      # proposed high-level work from that stage
metadata.task_list[]            # merged, priority/stage ordered task list
```

For task continuity, the quick Router model may also propose
`metadata.task_relation`, `metadata.target_task_id`, and
`metadata.task_context_patch`. These fields tell the host whether an utterance
looks like a new task, a continuation, a modification, a closure, side
conversation, or a clarification, and what compact facts should be merged into
the task context. They are advisory only: the Orchestrator task manager owns the
actual task-context write, persistence, confirmation, cancellation, and safety
state.

`RouteDecision.actions` remains the compatibility/execution hint for concrete
capability actions, such as ordered Soridormi skill requests. The merged
`task_list` is broader: it can include emergency cancellation, thinking
acknowledgement, deepthinking work, speech, memory, tool, and skill-execution
proposals. The Agent and Skill Runtime still validate every executable item
against registered capabilities and safety policy.

## Current route list

| Route | Purpose |
|---|---|
| `chat` | Normal conversation and questions that do not need tools. |
| `deep_thought` | Complex reasoning or planning delegated to `deepthinking_agent` with session working memory. |
| `robot_action` | High-level body, head, pose, or motion request selected from available capabilities. |
| `tool` | External information or planning tools, such as web/weather/API work. |
| `memory` | User asks Chromie to remember or update a preference/fact. |
| `clarify` | The request is ambiguous or outside current bounded abilities. |
| `interrupt` | Stop/cancel/shut up/emergency-style operational controls. |
| `ignore` | Empty, noisy, accidental, repeated filler, or unusable ASR input. |

When LLM routing is enabled, the prompt tells the model to consider:

- current candidate capabilities as Chromie's available ability list;
- bounded memory and context such as `session_memory`, pending tasks, robot
  state, position, and user preferences;
- speech plus body intent, while still returning only a route decision;
- safety boundaries: memory is not authorization, and the model must not invent
  capabilities or low-level robot controls.

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
ROUTER_RULES_FIRST=1
ROUTER_OLLAMA_URL=http://chromie-llm:11434
ROUTER_MODEL=qwen3:0.6b
ROUTER_REVIEW_MODEL=gemma4:e2b
ROUTER_TIMEOUT_MS=800
ROUTER_LLM_TIMEOUT_MS=800
ROUTER_REVIEW_TIMEOUT_MS=3000
ROUTER_CONFIDENCE_THRESHOLD=0.55
ROUTER_CAPABILITY_CATALOG_URL=http://chromie-agent:8092
ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS=600
ROUTER_CAPABILITY_MATCH_LIMIT=8
ROUTER_LOG_LEVEL=INFO
```

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
