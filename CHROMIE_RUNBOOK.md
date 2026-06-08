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
