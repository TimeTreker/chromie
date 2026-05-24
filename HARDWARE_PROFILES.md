# Chromie Hardware Profiles

Chromie now supports a hardware/profile based environment flow.

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

## Current profiles

- `default`
- `rtx4090`
- `rtx5090`
- `jetson_orin_nano_super`
- `jetson_agx_orin`
- `jetson_thor`

Jetson profiles define runtime/model choices, but ARM64/Jetson-compatible Dockerfiles or a Jetson compose override may still be required before full Jetson deployment.
