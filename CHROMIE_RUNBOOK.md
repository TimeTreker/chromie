# Chromie Operations Runbook

This file is optional. It summarizes the commands most often needed while debugging Chromie.

## Start services

```bash
bash scripts/start_services.sh
```

## Warm Ollama

```bash
./scripts/warm_ollama.sh
```

## Start host orchestrator

```bash
bash scripts/start_orchestrator.sh
```

## GPU smoke test

Check already-running services:

```bash
./scripts/gpu_smoke_test.sh
```

Start existing images first and synthesize a short TTS sample:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

Preview the checks without running Docker or GPU commands:

```bash
DRY_RUN=1 ./scripts/gpu_smoke_test.sh
```

## Verify only one orchestrator

```bash
pgrep -af "orchestrator"
```

Kill all old ones:

```bash
pkill -f "python.*orchestrator"
pkill -f "start_orchestrator.sh"
```

## Check Docker env

```bash
docker compose --env-file .env.runtime exec chromie-agent env | grep -E "AGENT_USE_LLM|AGENT_OLLAMA_URL|AGENT_MODEL|AGENT_TIMEOUT_MS"
docker compose --env-file .env.runtime exec chromie-router env | grep -E "ROUTER_USE_LLM|ROUTER_OLLAMA_URL|ROUTER_MODEL|ROUTER_TIMEOUT_MS"
```

## Check installed models

```bash
docker compose --env-file .env.runtime exec chromie-llm ollama list
```

Pull model:

```bash
set -a
source .env.runtime
set +a
docker compose --env-file .env.runtime exec chromie-llm ollama pull "$AGENT_MODEL"
```

## Verify Soridormi MCP capabilities

Add the deployment endpoint and manifest to `.env.local`, then regenerate the
runtime configuration:

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json
SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp
AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1
```

```bash
./scripts/build_runtime_env.sh
docker compose --env-file .env.runtime run --rm --no-deps chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

Do not enable read-only or guarded TaskGraph execution until the probe reports
`status: ready`. A missing tool means the Soridormi server and Chromie manifest
do not yet share an accepted contract.

Run the safe status/planning acceptance after the probe succeeds:

```bash
docker compose --env-file .env.runtime run --rm --no-deps chromie-agent \
  python -m app.soridormi_acceptance \
  --manifest /app/capabilities/soridormi.json
```

The default planning request contains zero velocity and yaw. It calls only
`soridormi.robot.get_status` and `soridormi.motion.create_plan`; it never calls
the physical execution tool.

Run the full dry-run acceptance against Soridormi's dedicated MCP container:

```bash
docker compose --env-file .env.runtime run --rm --no-deps chromie-agent \
  python -m app.soridormi_acceptance \
  --manifest /app/capabilities/soridormi.json \
  --guarded-dry-run
```

This verifies confirmation, monitor activation, dry-run execution, and
`soridormi.motion.stop` fallback over the network. It requires
`dry_run_only=true` and does not accept the result as hardware evidence.

Add `--exercise-emergency-stop` only on a disposable or restartable Soridormi
process. The command verifies retained e-stop state and intentionally leaves
that process stopped.

On the supervised target host, verify cancellation against the runtime-backed
MCP adapter with:

```bash
docker compose --env-file .env.runtime run --rm --no-deps chromie-agent \
  python -m app.soridormi_acceptance \
  --manifest /app/capabilities/soridormi.json \
  --exercise-runtime-cancellation
```

The default cancellation plan holds zero velocity for five seconds. Chromie
waits until `execute_plan` is dispatched, cancels the graph after one second,
requires the emergency fallback to succeed, and verifies retained e-stop
state. This intentionally leaves Soridormi stopped; complete its documented
recovery procedure before any further motion.

Chromie and Soridormi remain separate deployments. Start `soridormi-mcp` from
the Soridormi repository, then point Chromie at its published endpoint.

## Watch logs

```bash
docker compose --env-file .env.runtime logs -f chromie-agent
docker compose --env-file .env.runtime logs -f chromie-llm
docker compose --env-file .env.runtime logs -f chromie-tts
```

## TTS duplicate diagnosis

Two different request IDs with the same text means two requests were sent:

```text
request_id=aaaa1111-0 text="..."
request_id=bbbb2222-0 text="..."
```

Usually two orchestrator processes are running.
