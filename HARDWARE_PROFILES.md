# Chromie Hardware Profiles

Chromie supports a hardware/profile based environment flow.

Startup flow:

```text
collect system info
→ detect hardware profile
→ merge .env.common + env/profiles/<profile>.env + .env.local
→ generate .env.runtime
→ build/start/warm/orchestrator use .env.runtime
```

## Files

- `.env.common`: shared defaults committed to git.
- `env/profiles/*.env`: hardware-specific build/runtime profiles committed to git.
- `.env.local`: user overrides, not committed.
- `.env.runtime`: generated file, not committed.
- `.chromie/system_info.env`: generated hardware/system detection results, not committed.

## Commands

Show detected profile and key variables:

```bash
./scripts/show_profile.sh
```

Start Docker services:

```bash
./scripts/start_services.sh
```

Build with cache:

```bash
BUILD=1 ./scripts/start_services.sh
```

Build from scratch:

```bash
REBUILD_NO_CACHE=1 ./scripts/start_services.sh
```

Warm the agent LLM model:

```bash
./scripts/warm_ollama.sh
```

Start the host orchestrator:

```bash
./scripts/start_orchestrator.sh
```

## Override profile manually

Copy the local example:

```bash
cp .env.local.example .env.local
```

Then edit `.env.local`:

```bash
CHROMIE_HARDWARE_PROFILE=rtx5090
AGENT_MODEL=gemma4:e2b
```

`.env.local` wins over `.env.common` and hardware profiles.

## TTS variable semantics

Be careful with these two different limits:

```text
TTS_MAX_TEXT_CHARS  = text character limit before sending text to TTS
TTS_MAX_LENGTH      = OuteTTS / llama generation token budget
```

Do **not** use this to make Chromie speak shorter:

```bash
TTS_MAX_LENGTH=120
```

That value is too small for OuteTTS generation and can make the model emit zero audio codec tokens. The symptom is:

```text
0it [00:00, ?it/s]
torch.cat(): expected a non-empty list of Tensors
```

Use this instead:

```bash
TTS_MAX_TEXT_CHARS=120
```

Recommended generation budgets:

```bash
# Jetson / small edge profile
TTS_CONTEXT_SIZE=2048
TTS_MAX_LENGTH=2048
MIN_TTS_GENERATION_LENGTH=1024
TTS_MAX_TEXT_CHARS=120

# Desktop RTX profile
TTS_CONTEXT_SIZE=4096
TTS_MAX_LENGTH=4096
MIN_TTS_GENERATION_LENGTH=1024
TTS_MAX_TEXT_CHARS=220
```

`tts/server.py` now clamps very small `TTS_MAX_LENGTH` values up to `MIN_TTS_GENERATION_LENGTH` when possible, and logs both requested and effective generation lengths.

## Current profiles

- `default`
- `nvidia_ada`
- `nvidia_blackwell`
- `rtx4090`
- `rtx4090_laptop`
- `rtx5090`
- `jetson_orin_nano_super`
- `jetson_agx_orin`
- `jetson_thor`

Detection prefers the Jetson device-tree model, then the NVIDIA GPU name, then
compute capability and memory as a fallback. RTX 4090 Laptop GPUs use a separate
profile because their typical VRAM and power envelope differ from the desktop
RTX 4090.

| Popular hardware | Automatic profile |
|---|---|
| GeForce RTX 5090 | `rtx5090` |
| GeForce RTX 4090 | `rtx4090` |
| GeForce RTX 4090 Laptop GPU | `rtx4090_laptop` |
| GeForce RTX 5080/5070 class | `nvidia_blackwell` |
| GeForce RTX 4080/4070 class | `nvidia_ada` |
| Jetson AGX Thor | `jetson_thor` |
| Jetson AGX Orin | `jetson_agx_orin` |
| Jetson Orin Nano Super | `jetson_orin_nano_super` |

Other NVIDIA GPUs remain compatible and select a conservative architecture
profile by GPU name, compute capability, and VRAM where possible. A profile can
still be chosen in `.env.local`. Model sizing is deliberately based on
available VRAM and power limits, not only the marketing family name.

GPU type is not part of Chromie's service or Soridormi integration contract.
It affects model size, latency, CUDA images, and deployment validation. Jetson
profiles define runtime/model choices, but ARM64/Jetson-compatible images or a
Compose override may still be required for full deployment.
