# Chromie Hardware Profiles

Chromie automatically detects the current machine and generates a complete,
validated runtime environment before every supported build or startup.
Operators do not select a GPU profile on the command line and do not set one in
`.env.local`.

```text
fresh hardware snapshot
-> deterministic profile detection
-> .env.common
-> env/profiles/<detected-profile>.env
-> optional env/validation/<overlay>.env
-> allowed non-profile .env.local values
-> flattened .env.runtime + .env + runtime_profile.json
-> Compose validation
-> container environment verification after startup
```

The generator is `scripts/generate_runtime_env.py`; the stable shell entrypoint
is `scripts/build_runtime_env.sh`.

## Generated and source files

| File | Purpose |
|---|---|
| `.env.common` | Shared committed defaults and feature gates |
| `env/profiles/*.env` | Complete hardware-specific model and resource plans |
| `env/validation/*.env` | Explicit validation-only overlays |
| `.env.local` | Machine-local paths and non-profile rollout settings only |
| `.chromie/system_info.env` | Fresh hardware facts collected by the generator |
| `.chromie/runtime_profile.json` | Selected profile, model plan, hardware facts, and fingerprint |
| `.env.runtime` | Flattened generated runtime environment; exactly one value per key |
| `.env` | Generated Docker Compose compatibility copy |

Do not edit or commit generated files.

## Automatic entrypoints

These supported entrypoints regenerate and validate the runtime environment
automatically:

```bash
./scripts/start_chromie.sh
./scripts/start_voice_mujoco.sh
BUILD=1 ./scripts/start_services.sh
REBUILD_NO_CACHE=1 ./scripts/start_services.sh
./scripts/deploy_chromie.sh
./scripts/start_orchestrator.sh
./scripts/warm_ollama.sh
./scripts/compose.sh build
./scripts/compose.sh up -d
```

No `--hardware-profile` argument is required or supported. A direct plain
`docker compose` invocation bypasses Chromie's generator; use
`./scripts/compose.sh` instead.

## Profile authority

The detected profile owns every key it defines. When `.env.local` contains a
stale profile- or validation-owned hardware, model, timeout, ASR, or TTS value,
the generator ignores that local value, emits a warning, and records the key in
`.chromie/runtime_profile.json`. This prevents a copied local file from making
an RTX 5090 run the RTX 4090 Laptop model plan without blocking normal startup.

For CI or configuration cleanup, set `CHROMIE_ENV_STRICT=1`; the same conflict
then fails generation before `.env.runtime` or `.env` is written.

To change a hardware-class plan, update its committed file under
`env/profiles/` and run the tests. To create a genuinely different plan, add a
new detectable profile rather than bypassing detection.

A profile must explicitly define the complete cognitive model plan:

```text
AGENT_MODEL
OLLAMA_MODEL
ROUTER_MODEL
ROUTER_REVIEW_MODEL
AGENT_GOAL_ASSOCIATION_MODEL
AGENT_FAST_PLANNER_MODEL
AGENT_DEEP_PLANNER_MODEL
AGENT_RESPONSE_COMPOSER_MODEL
AGENT_TASK_CONTINUITY_MODEL
AGENT_SOCIAL_ATTENTION_MODEL
AGENT_RESPONSE_REVIEW_MODEL
```

Startup warms every active model in that plan and stops immediately if a model
is missing. After containers start, `scripts/verify_runtime_profile.sh` checks
that Router and Agent received the same profile and fingerprint as
`.env.runtime`.

During the current architecture-qualification phase, the maintained RTX 5090
and RTX 4090 Laptop profiles also own a deliberately generous cognitive timeout
plan. Agent model stages receive up to 120 seconds, host stage calls receive up
to 150 seconds, and the complete staged cognitive runtime receives up to 900
seconds. This is intentional: live acceptance should measure model capability
and workflow correctness before latency optimization. These budgets require no
launcher option and are regenerated automatically with the detected profile.

## Current profiles

| Profile | Intended class | Quality model | Fast model | TTS context |
|---|---|---|---|---:|
| `default` | Unknown/conservative | `gemma4:e2b` | `qwen3:4b` | 2048 |
| `nvidia_ada` | RTX 4080/4070 class | `gemma4:e2b` | `qwen3:4b` | 2048 |
| `nvidia_blackwell` | RTX 5080/5070 and laptop Blackwell | `gemma4:e2b` | `qwen3:4b` | 2048 |
| `rtx4090` | Desktop RTX 4090 | `gemma4:e2b` | `qwen3:4b` | 4096 |
| `rtx4090_laptop` | RTX 4090 Laptop GPU | `gemma4:e2b` | `qwen3:4b` | 4096 |
| `rtx5090` | Desktop RTX 5090 | `gemma4:26b` | `qwen3:4b` | 4096 |
| `jetson_orin_nano_super` | 8 GB shared-memory Orin edge target | `gemma4:e2b` | `qwen3:4b` | 2048 |
| `jetson_agx_orin` | AGX Orin | `gemma4:e2b` | `qwen3:4b` | 2048 |
| `jetson_thor` | AGX Thor placeholder profile | `gemma4:26b` | `qwen3:4b` | 4096 |

The quality model is used by Deep Planner and Response Composer. The fast model
is used by Router, Goal Association, Fast Planner, Task Continuity, and Social
Attention unless the profile explicitly states otherwise.

## Detection order

Automatic detection prefers:

1. Jetson device-tree model;
2. exact NVIDIA GPU name;
3. compute capability and available GPU memory;
4. `default` fallback.

The RTX 4090 Laptop check occurs before the desktop RTX 4090 check. The same
system-information snapshot is used for both selection and generated evidence.

## Validation and failure behavior

Generation fails before Docker build/start when:

- a detected profile file is missing;
- a profile omits part of the model plan;
- profile name, CPU architecture, GPU vendor, or CUDA architecture contradicts
  detected hardware;
- `CHROMIE_ENV_STRICT=1` and `.env.local` contains a profile- or
  validation-owned key;
- a user-managed `.env` would conflict with the generated Compose environment;
- Docker Compose cannot resolve the generated configuration.

Without strict mode, conflicting profile-owned local keys are ignored with an
`[env][warning]` message. Inspect `ignored_local_overrides` in
`.chromie/runtime_profile.json` to clean them up later. After startup, container
verification fails if Agent or Router received a stale profile, stale
fingerprint, or different model assignment.

Inspect the active result with:

```bash
./scripts/show_profile.sh
./scripts/verify_runtime_profile.sh
cat .chromie/runtime_profile.json | python -m json.tool
```

## Detection limitations

- Multi-GPU systems currently use the first `nvidia-smi` result.
- Unknown vendor strings may fall back by compute capability and memory.
- `jetson_thor` uses a provisional CUDA architecture until verified on the
  actual toolchain.
- Jetson profiles do not prove that the current base images work on ARM64.
- A detected profile is configuration evidence, not target acceptance evidence.

The old `PRESET_RTX4090_LAPTOP.txt` file is only a legacy pointer; profile
selection is dynamic and automatic.
