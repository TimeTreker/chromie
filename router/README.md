# Chromie Router

`chromie-router` is a CPU-only routing service on port `8091` by default. It
turns user text and bounded session context into a validated `RouteDecision`.
It never opens audio devices, performs speech recognition or synthesis, invokes
skills, or controls hardware.

## Processing modes

```text
text + bounded context
  -> deterministic interrupt/noise safety rules
  -> shared Agent capability-catalog search
  -> optional legacy rules / Ollama route classifier
  -> schema finalization
  -> RouteDecision
```

Supported modes:

- `rules_only` — capability-catalog routing, compatible non-robot rules, then a deterministic fallback;
- `hybrid` — rules first when enabled, then Ollama for unmatched requests;
- `llm_only` — send routing decisions directly to Ollama.

`ROUTER_USE_LLM=0` selects `rules_only` unless `ROUTER_MODE` is explicitly set.
Operational interruption/noise handling remains deterministic even when a
conversational model is available. Robot routing is catalog-first; the old
phrase-based robot rules are an explicit compatibility rollback only. The Agent
repeats the same catalog search inside native InteractionRuntime, so Router
unavailability cannot authorize or suppress execution by itself.

## HTTP API

- `GET /health` — active mode, model, Ollama URL, and rules-first flag
- `GET /routes` — route and specialized-agent identifiers known by the service
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
ROUTER_MODE=rules_only
ROUTER_USE_LLM=0
ROUTER_RULES_FIRST=1
ROUTER_OLLAMA_URL=http://chromie-llm:11434
ROUTER_MODEL=qwen3:0.6b
ROUTER_TIMEOUT_MS=800
ROUTER_LLM_TIMEOUT_MS=800
ROUTER_CONFIDENCE_THRESHOLD=0.55
ROUTER_CAPABILITY_CATALOG_URL=http://chromie-agent:8092
ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS=600
ROUTER_CAPABILITY_MATCH_LIMIT=8
ROUTER_ALLOW_LEGACY_ROBOT_RULES=0
ROUTER_LOG_LEVEL=INFO
```

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
