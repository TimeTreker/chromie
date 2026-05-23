# CLAUDE.md

Guidelines for Claude Code / other coding agents working on Chromie.

## Project summary

Chromie is a local realtime voice assistant.

Current architecture:

```text
Host:
  orchestrator = mic + VAD + ASR client + Router client + Agent client + TTS client + playback

Docker:
  chromie-asr     Faster-Whisper websocket ASR
  chromie-router  fast route/intent service
  chromie-agent   multi-agent runtime / talking brain
  chromie-llm     Ollama
  chromie-tts     OuteTTS / llama.cpp websocket TTS
```

Read `LLM_CONTEXT.md` before changing code.

## Source of truth

Use the GitHub repo as source of truth:

```text
https://github.com/TimeTreker/chromie.git
```

Before changing anything:

1. Inspect the latest files.
2. Identify the exact bug.
3. Name the files that need modification.
4. Make the smallest working change.
5. Verify syntax/tests/commands before giving the result.

Do not make broad refactors unless explicitly requested.

## Launch model

The host orchestrator should be launched from repo root:

```bash
python -m orchestrator.orchestrator
```

Preferred script:

```bash
bash scripts/start_orchestrator.sh
```

Do not assume `cd orchestrator && python orchestrator.py`.

For package-style launch, use package-style imports:

```python
from orchestrator.clients.agent_client import AgentClient
from orchestrator.schemas.agent import AgentResult
```

Do not switch to local imports unless changing the launch model too.

## Conda environment

User uses conda env:

```text
Chromie
```

`start_orchestrator.sh` should activate `Chromie`.

## Docker service rules

Inside Docker containers, use service names, not host loopback.

Correct:

```env
AGENT_OLLAMA_URL=http://chromie-llm:11434
ROUTER_OLLAMA_URL=http://chromie-llm:11434
```

Wrong inside Docker:

```env
http://127.0.0.1:11434
```

because `127.0.0.1` points to the container itself.

## Router vs Agent

Router should be fast.

Default:

```env
ROUTER_USE_LLM=0
```

If LLM router is enabled, use a tiny model and short timeout.

Agent is the talking brain.

Default:

```env
AGENT_USE_LLM=1
AGENT_MODEL=gemma4:26b
AGENT_TIMEOUT_MS=120000
ORCH_AGENT_TIMEOUT_MS=130000
```

For realtime testing, smaller models are acceptable.

## Ollama request rules

Use a single public `generate()` method in the Agent Ollama client.

Text:

```python
await ollama.generate(prompt, system=system, options=options)
```

JSON:

```python
await ollama.generate(
    prompt,
    system=system,
    options=options,
    response_format="json",
)
```

Payload must include:

```python
"stream": False,
"think": False,
```

Do not speak hidden thinking text.

For voice replies, keep output short:

```python
options={
    "temperature": 0.35,
    "top_p": 0.9,
    "num_predict": 32,
    "stop": ["\n", "User:", "Assistant:", "Chromie:"],
}
```

## Warm model before microphone

Large models can take longer than normal voice-turn timeouts to load.

Use:

```bash
bash scripts/warm_ollama.sh "${AGENT_MODEL:-gemma4:26b}"
```

Starting microphone before warmup can cause:

```text
context canceled
Load failed
/api/generate 500
```

## One orchestrator only

Never run two host orchestrators at once.

Duplicate reply symptom:

```text
TTS input request_id=553c8a1f-0 text="same text"
TTS input request_id=d93f5765-0 text="same text"
```

Different session IDs mean two sessions, usually two orchestrator processes.

Check:

```bash
pgrep -af "orchestrator"
```

Kill old ones:

```bash
pkill -f "python.*orchestrator"
pkill -f "start_orchestrator.sh"
```

## TTS safety

OuteTTS / llama.cpp should have only one active generation at a time.

Use:

```env
TTS_MAX_CONCURRENT_SYNTHESIS=1
TTS_GENERATION_RETRIES=1
TTS_RESET_LLAMA_STATE=1
```

Do not introduce concurrent calls to the same global OuteTTS interface.

## Logging expectations

Do not add silent fallback. Always log why fallback happened.

Agent logs should show:

```text
conversation_agent_start ... use_llm=True ollama_present=True
conversation_agent_llm_start
ollama_generate_start
ollama_generate_http_done
ollama_generate_done
conversation_agent_llm_done
```

If failure:

```text
conversation_agent_llm_failed error_type=...
conversation_agent_done mode=fallback fallback=...
```

## Common bugs and correct diagnosis

### `I understand` for every prompt

Usually hardcoded Agent fallback. Make the conversation agent call Ollama.

### `my language model is not responding`

Check:

```bash
docker compose exec chromie-agent env | grep -E "AGENT_USE_LLM|AGENT_OLLAMA_URL|AGENT_MODEL|AGENT_TIMEOUT_MS"
docker compose exec chromie-llm ollama list
```

### `/api/generate` 404

Model missing or model name wrong.

```bash
docker compose exec chromie-llm ollama pull "$AGENT_MODEL"
```

### `ReadTimeout`

Timeout too short or model not warmed.

```env
AGENT_TIMEOUT_MS=120000
ORCH_AGENT_TIMEOUT_MS=130000
```

### HTTP 200 with empty response

Likely thinking-capable model behavior or prompt issue. Ensure `think:false`, log raw body, and do not speak empty text.

### TTS speaks same reply twice

Check TTS request IDs. If different session IDs, it is not TTS retry; usually two orchestrators are running.

## Patch / file generation rules

When asked for patches:

- Generate a real unified diff.
- Verify with `git apply --check`.
- Do not provide hand-written pseudo-diffs.

When asked for full files:

- Provide the entire file.
- Say exact destination path.
- Do not hide required companion file changes.

When unsure, inspect the repo first.

## Keep changes surgical

Do not:

- rewrite unrelated code;
- rename modules without reason;
- change launch style accidentally;
- remove logging that helps diagnose runtime failures;
- add speculative abstractions;
- change ASR/TTS/LLM model defaults without saying why.

Every changed line should trace back to the user's request or a directly required fix.
