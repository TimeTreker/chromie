# Chromie Orchestrator

The Orchestrator is Chromie's host-side realtime runtime. It stays outside Docker because it owns microphone capture, speaker playback, VAD, barge-in, session state, and optional hardware execution.

## Services

- `chromie-asr`: PCM audio to final text over WebSocket
- `chromie-router`: text and context to a `RouteDecision`
- `chromie-agent`: route and context to an `AgentResult`
- `chromie-tts`: text to a PCM audio stream over WebSocket
- optional `hardware/daemon.py`: host hardware action executor

Router and Agent return decisions and plans. Only the Orchestrator should access ASR, TTS, playback, and host hardware.

## Configuration

Prepare the recommended Conda environment from the repository root:

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
```

Create the host-specific environment file:

```bash
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Set `ORCH_INPUT_DEVICE` and `ORCH_OUTPUT_DEVICE` to explicit device indexes or names. Relative `RECORDINGS_DIR` values are resolved from the repository root.

The Orchestrator loads generated root `.env.runtime` first and then fills unset host values from `orchestrator/.env.local`. Environment variables already exported by the launching process retain precedence.

## Recommended Startup

From the repository root:

```bash
./scripts/start_orchestrator.sh
```

This path generates `.env.runtime`, activates the configured Conda environment, installs changed requirements, warms Ollama, prevents duplicate processes, and runs the Orchestrator as a module.

## Manual Startup

With dependencies already installed:

```bash
./scripts/build_runtime_env.sh
python -m orchestrator.orchestrator
```

Always run the module from the repository root. Do not use `cd orchestrator && python orchestrator.py`; package imports and repository-relative paths assume the root layout.

## Fallback Behavior

If `ORCH_ENABLE_ROUTER=false`, the Orchestrator uses the legacy flow:

```text
ASR -> Ollama streaming LLM -> TTS -> playback
```

If Router or Agent fails during a turn, the Orchestrator falls back to the legacy LLM path. If `ORCH_ACTION_DRY_RUN=true`, returned actions are logged but not sent to the hardware daemon.
