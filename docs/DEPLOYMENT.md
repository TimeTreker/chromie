# Chromie Deployment

This document covers a fresh simulator deployment. Chromie is the brain: audio,
conversation, routing, memory, planning, and high-level skill selection.
Soridormi is deployed separately as the body runtime.

The deploy script prepares a checkout. The start scripts run the services.

## Fresh Checkout

Keep the two repositories next to each other:

```bash
mkdir -p ~/github
cd ~/github
git clone https://github.com/TimeTreker/soridormi.git
git clone https://github.com/TimeTreker/chromie.git
```

Deploy Soridormi first:

```bash
cd ~/github/soridormi
./scripts/deploy_soridormi.sh
```

Deploy Chromie:

```bash
cd ~/github/chromie
./scripts/deploy_chromie.sh
```

The Chromie deploy script:

- creates `.env.local` and `orchestrator/.env.local` from templates when they
  are missing;
- generates `.env.runtime`;
- pulls the external Ollama image;
- builds Chromie-owned ASR, TTS, Router, and Agent images;
- runs `INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh`.

## Start Separately

Terminal 1:

```bash
cd ~/github/soridormi
./scripts/start_soridormi_mujoco.sh --profile open_duck_forward --viewer --follow-camera
```

Terminal 2:

```bash
cd ~/github/chromie
./scripts/start_chromie.sh --mcp-url http://127.0.0.1:8000/mcp
```

## Start Together

From the Chromie checkout:

```bash
./scripts/start_voice_mujoco.sh --soridormi-repo ../soridormi
```

Use `--build` on the start script only when images changed after deployment.

## Useful Variants

```bash
./scripts/deploy_chromie.sh --skip-build
./scripts/deploy_chromie.sh --skip-tests
./scripts/deploy_chromie.sh --rebuild-no-cache
./scripts/deploy_chromie.sh --start --mcp-url http://127.0.0.1:8000/mcp
```

## Scope

This is simulator deployment. It does not claim physical microphone/speaker
quality, Jetson packaging, hardware motion, navigation autonomy, or unattended
operation.
