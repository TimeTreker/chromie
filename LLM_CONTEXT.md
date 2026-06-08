# Chromie Engineering Context

This is a concise handoff for coding agents. Detailed setup and operations belong in the documents linked from `README.md`.

## Runtime Boundary

```text
Host:
  Orchestrator = microphone, VAD, sessions, interruption, playback, hardware actions

Docker:
  chromie-asr    = speech recognition
  chromie-router = route and intent decision
  chromie-agent  = conversation and action planning
  chromie-llm    = Ollama
  chromie-tts    = speech synthesis
```

Only the Orchestrator should directly coordinate ASR, TTS, playback, and host hardware.

## Control Flow

```text
microphone -> ASR -> Router -> Agent -> TTS -> playback
```

Router returns structured decisions. Agent returns speech, actions, and memory updates. If Router or Agent fails, the Orchestrator may use its legacy direct-LLM fallback.

## Configuration

Runtime configuration is generated in this order:

```text
.env.common + env/profiles/<profile>.env + .env.local -> .env.runtime
```

Use `./scripts/show_profile.sh` to inspect the selected model and timeout values. Do not hardcode one hardware profile's model as the project-wide default.

Inside Docker, use service names such as `http://chromie-llm:11434`. From the host, use published loopback ports.

## Invariants

- Launch with `python -m orchestrator.orchestrator` from the repository root.
- Keep `ROUTER_USE_LLM=0` as the normal low-latency default.
- Keep Agent LLM failures and fallback reasons visible in logs.
- Ensure the Orchestrator Agent timeout is longer than the Agent's Ollama timeout.
- Warm the selected Ollama model before opening the voice loop.
- Keep one active Orchestrator process.
- Keep one active TTS generation unless backend isolation is added.
- Use explicit audio devices when possible.
- Preserve `think: false` for spoken Ollama responses.

## Detailed Documents

- `DEVELOPMENT_CHECKPOINT.md`
- `README.md`
- `docs/PROJECT_GUIDE.zh-CN.md`
- `HARDWARE_PROFILES.md`
- `CHROMIE_RUNBOOK.md`
- `docs/conversation_state.md`
- `docs/agent_capability_registry.md`
- `docs/agent_task_graph.md`
