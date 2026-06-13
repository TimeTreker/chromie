# Support

Chromie is currently a prepared alpha candidate, not a published or supported
production product.

## Before asking for help

Run and include the non-secret output of:

```bash
./scripts/show_profile.sh
docker compose --env-file .env.runtime ps
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8092/health
./scripts/run_tests.sh
```

For GPU or model issues, also run:

```bash
./scripts/gpu_smoke_test.sh
```

Use `DRY_RUN=1` only to inspect the planned checks; it is not evidence that the
GPU path works.

## Useful issue information

- Chromie revision;
- selected hardware profile and GPU model;
- operating system, Docker, driver, and Python versions;
- deployment mode: compatibility voice, structured speech-only, MuJoCo, or
  hardware experiment;
- exact command and sanitized logs;
- whether the problem reproduces with all experimental feature gates off.

Do not include tokens, `.env.local`, full `.env.runtime`, personal recordings,
raw session-event JSONL, or private endpoint credentials.

## Scope

Reasonable public support topics include installation, profile detection,
container health, contracts, deterministic tests, and simulator integration.
Real hardware commissioning and safety approval remain device-specific and must
follow Soridormi’s procedures.
