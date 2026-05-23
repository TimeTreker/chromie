# chromie-router

`chromie-router` is a small CPU-only routing service for Chromie.

It receives ASR text from the host orchestrator and returns a structured `RouteDecision`.
It does not touch microphone, speaker, ASR, TTS, robot hardware, CUDA, PyTorch, or model weights.

## Responsibilities

```text
text + session context
  -> rule router
  -> optional Ollama router
  -> JSON schema validation
  -> RouteDecision
```

## API

### `GET /health`

```bash
curl http://127.0.0.1:8091/health
```

### `POST /route`

```bash
curl -s http://127.0.0.1:8091/route \
  -H 'content-type: application/json' \
  -d '{
    "sid": "demo",
    "text": "转过来看着我",
    "language": "zh-CN",
    "context": {
      "is_speaking": false,
      "robot_state": {
        "is_moving": false
      }
    }
  }' | jq
```

Example response:

```json
{
  "route": "robot_action",
  "agents": ["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
  "intent": "look_at_user",
  "confidence": 0.95,
  "language": "zh-CN",
  "priority": "normal",
  "interrupt_current": false,
  "needs_agent": true,
  "should_speak": true,
  "speak_first": null,
  "actions": [],
  "reason": "Matched robot pose rule",
  "source": "rules"
}
```

## Environment

```env
ROUTER_HOST=0.0.0.0
ROUTER_PORT=8091
ROUTER_MODE=hybrid
ROUTER_RULES_FIRST=1
ROUTER_OLLAMA_URL=http://chromie-llm:11434
ROUTER_MODEL=qwen3:0.6b
ROUTER_TIMEOUT_MS=800
ROUTER_LLM_TIMEOUT_MS=800
ROUTER_CONFIDENCE_THRESHOLD=0.55
ROUTER_LOG_LEVEL=INFO
```

## Docker Compose snippet

Add the content from `compose.snippet.yml` into the root `docker-compose.yml` under `services:`.

## Orchestrator URL

Because the orchestrator runs on the host, use:

```env
ROUTER_URL=http://127.0.0.1:8091
```
