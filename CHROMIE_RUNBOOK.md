# Chromie Operations Runbook

This file is optional. It summarizes the commands most often needed while debugging Chromie.

## Start services

```bash
bash scripts/start_services.sh
```

## Warm Ollama

```bash
bash scripts/warm_ollama.sh "${AGENT_MODEL:-gemma4:26b}"
```

## Start host orchestrator

```bash
bash scripts/start_orchestrator.sh
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
docker compose exec chromie-agent env | grep -E "AGENT_USE_LLM|AGENT_OLLAMA_URL|AGENT_MODEL|AGENT_TIMEOUT_MS"
docker compose exec chromie-router env | grep -E "ROUTER_USE_LLM|ROUTER_OLLAMA_URL|ROUTER_MODEL|ROUTER_TIMEOUT_MS"
```

## Check installed models

```bash
docker compose exec chromie-llm ollama list
```

Pull model:

```bash
docker compose exec chromie-llm ollama pull gemma4:26b
```

## Watch logs

```bash
docker compose logs -f chromie-agent
docker compose logs -f chromie-llm
docker compose logs -f chromie-tts
```

## TTS duplicate diagnosis

Two different request IDs with the same text means two requests were sent:

```text
request_id=aaaa1111-0 text="..."
request_id=bbbb2222-0 text="..."
```

Usually two orchestrator processes are running.
