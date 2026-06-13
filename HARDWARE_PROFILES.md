# Chromie Hardware Profiles

Chromie detects a hardware profile, combines it with common and local settings,
and generates `.env.runtime`.

```text
collect system info
-> detect/override profile
-> .env.common + env/profiles/<profile>.env + .env.local
-> .env.runtime
```

Profiles select model size, timeout, CUDA architecture, and resource defaults.
They do not change Chromie’s service contracts or Soridormi safety boundary.

## Files

| File | Purpose |
|---|---|
| `.env.common` | Shared committed defaults and feature gates |
| `env/profiles/*.env` | Hardware-specific committed values |
| `.env.local` | Machine-local overrides; do not commit |
| `.env.runtime` | Generated merged environment; do not edit or commit |
| `.chromie/system_info.env` | Generated detection facts |

## Commands

```bash
./scripts/show_profile.sh
./scripts/build_runtime_env.sh
BUILD=1 ./scripts/start_services.sh
./scripts/warm_ollama.sh
./scripts/start_orchestrator.sh
```

Override detection in `.env.local`:

```env
CHROMIE_HARDWARE_PROFILE=rtx4090_laptop
```

## Current profiles

| Profile | Intended class | ASR default | Agent model default | TTS context |
|---|---|---|---|---:|
| `default` | Unknown/conservative | `tiny.en` | `gemma4:e2b` | 2048 |
| `nvidia_ada` | RTX 4080/4070 class | `base.en` | `gemma4:e2b` | 2048 |
| `nvidia_blackwell` | RTX 5080/5070 and laptop Blackwell | `base.en` | `gemma4:e2b` | 2048 |
| `rtx4090` | Desktop RTX 4090 | `small.en` | `gemma4:e2b` | 4096 |
| `rtx4090_laptop` | RTX 4090 Laptop GPU | `small.en` | `gemma4:e2b` | 4096 |
| `rtx5090` | Desktop RTX 5090 | `small.en` | `gemma4:26b` | 4096 |
| `jetson_orin_nano_super` | 8 GB shared-memory Orin edge target | `tiny.en` | `gemma4:e2b` | 2048 |
| `jetson_agx_orin` | AGX Orin | `base.en` | `gemma4:e2b` | 2048 |
| `jetson_thor` | AGX Thor placeholder profile | `small.en` | `gemma4:26b` | 4096 |

Automatic detection prefers:

1. Jetson device-tree model;
2. exact NVIDIA GPU name;
3. compute capability and available memory;
4. `default` fallback.

The RTX 4090 Laptop check occurs before the desktop family check.

## Detection limitations

- Multi-GPU systems use the first `nvidia-smi` result.
- Unknown vendor strings may fall back by compute capability and memory.
- `jetson_thor` uses a provisional CUDA architecture value until verified on
  the actual toolchain.
- Jetson profiles do **not** prove that the current x86-oriented Dockerfiles and
  base images work on ARM64. A Jetson-specific image/Compose path may still be
  required.
- A detected profile is not target acceptance evidence.

## TTS limits

These variables have different meanings:

```text
TTS_MAX_TEXT_CHARS       text length sent to TTS
TTS_MAX_LENGTH           OuteTTS generation-token budget
MIN_TTS_GENERATION_LENGTH minimum safe generation budget
```

Do not use a small `TTS_MAX_LENGTH` such as 100 or 120 to shorten speech. That
can produce zero audio codec tokens. Use `TTS_MAX_TEXT_CHARS` instead.

Typical values:

```env
# Smaller edge profile
TTS_CONTEXT_SIZE=2048
TTS_MAX_LENGTH=2048
MIN_TTS_GENERATION_LENGTH=1024
TTS_MAX_TEXT_CHARS=120

# Desktop profile
TTS_CONTEXT_SIZE=4096
TTS_MAX_LENGTH=4096
MIN_TTS_GENERATION_LENGTH=1024
TTS_MAX_TEXT_CHARS=220
```

The TTS server clamps an unsafe generation length when the context allows and
logs the requested and effective values.

## Model and timeout pairing

`ORCH_AGENT_TIMEOUT_MS` must exceed `AGENT_TIMEOUT_MS`; the hardware profiles
already preserve that relationship. Large-model profiles also require model
warming before the microphone loop opens.

## Local overrides

Use `.env.local` for machine-specific model changes, Compose overrides, proxies,
and rollout gates. Avoid editing profile files for one machine unless the
change is intended for every machine of that class.

The old `PRESET_RTX4090_LAPTOP.txt` file is now only a legacy pointer; profile
selection is dynamic.
