# Chromie LLM Context

This file is the canonical handoff document for future LLM / Claude / ChatGPT coding sessions working on Chromie.

Read this before changing code.

## Source of truth

The GitHub repository is the source of truth:

```text
https://github.com/TimeTreker/chromie.git
```

Before editing:

1. Pull or inspect the latest repo state.
2. Identify the exact files involved.
3. Explain the likely cause and proposed change.
4. Prefer small, surgical changes.
5. If generating a patch, verify it with `git apply --check`.
6. If generating full files, say exactly where each file should be copied.

Do not rely on older ZIPs, older patches, or stale snippets once the GitHub repo exists.

## Current architecture

Chromie is a local realtime voice assistant.

```text
Host:
  orchestrator/
    microphone
    VAD
    ASR websocket client
    Router HTTP client
    Agent HTTP client
    TTS websocket client
    playback
    interruption
    session logs

Docker:
  chromie-asr      Faster-Whisper websocket ASR, port 9001
  chromie-router   lightweight route/intent service, port 8091
  chromie-agent    multi-agent runtime / talking brain, port 8092
  chromie-llm      Ollama, port 11434
  chromie-tts      OuteTTS / llama.cpp websocket TTS, port 5000
```

The orchestrator stays on the host. Do not containerize the audio loop unless specifically requested; host audio and real device selection are simpler and more reliable outside Docker.

## Control flow

```text
microphone
  ↓
VAD valid speech
  ↓
ASR websocket
  ↓
Router /route
  ↓
Agent /run
  ↓
TTS websocket
  ↓
host playback
```

Router returns a `RouteDecision`.

Agent returns an `AgentResult`.

Orchestrator executes the result: speech, actions, memory updates, confirmations, and playback.

## Router design

The Router should be fast.

Recommended default:

```env
ROUTER_USE_LLM=0
ROUTER_MODEL=qwen3:0.6b
ROUTER_TIMEOUT_MS=1500
```

Router may use a tiny LLM later, but do not use a large talking model for routing. Large models make every voice turn slower.

Router output should be structured, not natural language.

Typical route:

```json
{
  "route": "chat",
  "agents": ["conversation_agent", "speaker_agent"],
  "intent": "general_conversation",
  "confidence": 0.45,
  "interrupt_current": false,
  "needs_agent": true
}
```

## Agent design

Agent is the talking brain.

Recommended default:

```env
AGENT_USE_LLM=1
AGENT_OLLAMA_URL=http://chromie-llm:11434
AGENT_MODEL=gemma4:26b
AGENT_TIMEOUT_MS=120000
AGENT_MAX_SPEAK_CHARS=220
```

For lower latency, use a smaller model:

```env
AGENT_MODEL=gemma4:e2b
# or gemma4:4b
# or qwen3:1.7b
```

The Agent must log whether it called the LLM:

```text
conversation_agent_start ... use_llm=True ollama_present=True
conversation_agent_llm_start ...
ollama_generate_start ...
ollama_generate_http_done ...
ollama_generate_done ...
conversation_agent_llm_done ...
```

If it falls back, the log must say why.

## Ollama client requirements

The Agent uses a single public API:

```python
await ollama.generate(
    prompt,
    system=system,
    options={...},
    response_format="text",  # default
)
```

For JSON:

```python
await ollama.generate(
    prompt,
    system=system,
    options={...},
    response_format="json",
)
```

The Ollama payload should include:

```json
{
  "stream": false,
  "think": false
}
```

Reason: thinking-capable models can put reasoning into a separate `thinking` field and return an empty final `response`. Chromie should speak the final response only, not hidden thinking.

Recommended short voice options:

```python
options={
    "temperature": 0.35,
    "top_p": 0.9,
    "num_predict": 32,
    "stop": ["\n", "User:", "Assistant:", "Chromie:"],
}
```

## Warm Ollama

Large models should be loaded before the user starts talking.

Use:

```bash
bash scripts/warm_ollama.sh "${AGENT_MODEL:-gemma4:26b}"
```

Recommended env:

```env
OLLAMA_KEEP_ALIVE=24h
OLLAMA_LOAD_TIMEOUT=10m
OLLAMA_CONTEXT_LENGTH=2048
OLLAMA_NUM_PARALLEL=1
OLLAMA_WARM_TIMEOUT_SECONDS=600
OLLAMA_WARM_REQUEST_TIMEOUT_SECONDS=300
```

If the first voice request triggers model loading, Ollama may show:

```text
context canceled
Load failed
POST "/api/generate" 500
```

This usually means the client timed out and canceled the load.

## Timeout rules

The orchestrator timeout must be longer than the Agent timeout.

Recommended for `gemma4:26b`:

```env
AGENT_TIMEOUT_MS=120000
ORCH_AGENT_TIMEOUT_MS=130000
```

If `ORCH_AGENT_TIMEOUT_MS` defaults to `3000`, the host orchestrator will fail after three seconds while the Agent is still waiting for Ollama.

## Import rules

The current preferred orchestrator launch style is:

```bash
cd /home/chromie/github/chromie
python -m orchestrator.orchestrator
```

So orchestrator internals should use package-style imports:

```python
from orchestrator.clients.agent_client import AgentClient
from orchestrator.schemas.agent import AgentResult
```

Do not switch back to:

```python
from clients.agent_client import AgentClient
from schemas.agent import AgentResult
```

unless the launch strategy changes.

Ensure these files exist:

```text
orchestrator/__init__.py
orchestrator/clients/__init__.py
orchestrator/runtime/__init__.py
orchestrator/schemas/__init__.py
```

## Start scripts

`start_services.sh` should:

- create `hf_cache`, `ollama_data`, and `recordings` independently if missing;
- fail clearly if one of those paths exists as a file;
- not rebuild images by default;
- build only when `BUILD=1` or `REBUILD_NO_CACHE=1`.

`start_orchestrator.sh` should:

- run from repo root;
- activate conda env `Chromie`;
- load `.env`;
- optionally warm Ollama before launching;
- run `python -m orchestrator.orchestrator`.

Use one orchestrator process only.

## Duplicate speech diagnosis

If the user hears the same reply twice, check TTS logs.

If TTS logs show:

```text
TTS input request_id=553c8a1f-0 text="same text"
TTS input request_id=d93f5765-0 text="same text"
```

then TTS received two separate requests from two separate orchestrator sessions.

Most likely cause: two host orchestrator processes are running.

Check:

```bash
pgrep -af "orchestrator"
ps aux | grep -E "python.*orchestrator|start_orchestrator" | grep -v grep
```

Kill old ones:

```bash
pkill -f "python.*orchestrator"
pkill -f "start_orchestrator.sh"
```

Then start one:

```bash
bash scripts/start_orchestrator.sh
```

Do not blame OuteTTS for duplicate speech until request IDs prove whether there was one request or two.

## Known failures and fixes

### `ModuleNotFoundError: orchestrator.schemas; 'orchestrator' is not a package`

Cause: running `cd orchestrator && python orchestrator.py` while code uses package-style imports.

Fix: run from repo root:

```bash
python -m orchestrator.orchestrator
```

### `ModuleNotFoundError: No module named 'pydantic'`

Install host orchestrator deps in conda env:

```bash
conda activate Chromie
pip install -r orchestrator/requirements.txt
```

### Agent always says `I understand`

Cause: Agent fallback/default path, not real LLM call.

Fix: make `conversation_agent` call Ollama and log LLM start/done/failure.

### Agent says `I heard you, but my language model is not responding`

Common causes:

- `AGENT_USE_LLM` missing or false.
- `AGENT_OLLAMA_URL` points to `127.0.0.1` inside Docker instead of `http://chromie-llm:11434`.
- model not installed.
- Agent timeout too short.
- Ollama model loading canceled.

Check:

```bash
docker compose exec chromie-agent env | grep -E "AGENT_USE_LLM|AGENT_OLLAMA_URL|AGENT_MODEL|AGENT_TIMEOUT_MS"
docker compose exec chromie-llm ollama list
```

### Ollama `404 Not Found` from `/api/generate`

Usually model name missing or wrong.

Fix:

```bash
docker compose exec chromie-llm ollama list
docker compose exec chromie-llm ollama pull "$AGENT_MODEL"
```

### Ollama `ReadTimeout`

For large models:

```env
AGENT_TIMEOUT_MS=120000
ORCH_AGENT_TIMEOUT_MS=130000
```

Also warm the model.

### Ollama returns HTTP 200 but empty response

Add raw-body logging and check whether the model is returning `thinking` but empty `response`.

Make sure payload includes:

```json
"think": false
```

### `/api/chat` returns 404

Usually a service is using a model that is not installed, or a wrong endpoint/model path. Router should usually run with:

```env
ROUTER_USE_LLM=0
```

until the Agent brain is stable.

### TTS crash / CUDA illegal memory access

Likely concurrent access to one global OuteTTS / llama.cpp interface.

Use:

```env
TTS_MAX_CONCURRENT_SYNTHESIS=1
TTS_GENERATION_RETRIES=1
TTS_RESET_LLAMA_STATE=1
```

TTS generation is blocking; do not expect hard cancellation of an active GPU generation call. You can cancel queued/playback audio, but active generation may need process-level isolation for true preemption.

## Logs to inspect

Host orchestrator:

```text
session_start
vad_valid_end
asr_send_start
asr_final
router_start / router_done
agent_start / agent_done / agent_exception
tts_schedule
tts_request_start
tts_stream_start / tts_stream_end
playback_start / playback_end
session_done
```

Agent container:

```text
conversation_agent_start
conversation_agent_llm_start
ollama_generate_start
ollama_generate_http_done
ollama_generate_done
conversation_agent_llm_done
conversation_agent_llm_failed
conversation_agent_done mode=fallback
```

TTS container:

```text
New TTS websocket connection
TTS input request_id=...
TTS done request_id=...
```

LLM container:

```text
inference compute ... CUDA ... RTX 5090
loading model
Load failed
context canceled
/api/generate 500
/api/generate 200
```

## Do not regress these decisions

- Keep host orchestrator as host process.
- Run orchestrator as `python -m orchestrator.orchestrator`.
- Keep Router fast; do not default Router to a huge model.
- Keep Agent LLM enabled with explicit logs.
- Use `AGENT_OLLAMA_URL=http://chromie-llm:11434` inside Docker.
- Use `think: false` for realtime spoken responses.
- Warm large Ollama models before opening microphone.
- Ensure `ORCH_AGENT_TIMEOUT_MS > AGENT_TIMEOUT_MS`.
- Keep TTS concurrency at one active generation.
- Do not run two orchestrator processes.
- Avoid generic audio devices when selecting microphone/speaker.
- Do not reintroduce `sd.play(..., blocking=True)` if persistent output stream is already implemented.
- Do not silently swallow LLM errors; log the exact error type and reason.
