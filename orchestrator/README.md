# Chromie Orchestrator

Host-side real-time orchestrator for Chromie.

This directory is intended to run directly on the host, not in Docker, because it
owns microphone capture, speaker playback, VAD, barge-in/interruption, session
state, and latency logs.

## Services it calls

- `chromie-asr`: WebSocket, raw PCM16 mono audio -> JSON final text
- `chromie-router`: HTTP JSON, user text -> `RouteDecision`
- `chromie-agent`: HTTP JSON, route/context -> `AgentResult`
- `chromie-tts`: WebSocket, text -> PCM audio stream
- optional host `hardware/daemon.py`: HTTP JSON action executor

Only the orchestrator should talk to ASR/TTS/playback directly. Router and agent
produce decisions/plans only.

## Setup

```bash
cd orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.local.example .env.local
python list_devices.py
python orchestrator.py
```

## Fallback behavior

If `ORCH_ENABLE_ROUTER=false`, the orchestrator uses the legacy flow:

```text
ASR -> Ollama streaming LLM -> TTS -> playback
```

If router or agent fails, it falls back to the legacy LLM flow for that turn.

If `ORCH_ACTION_DRY_RUN=true`, actions returned by the agent are logged but not
sent to the hardware daemon.
