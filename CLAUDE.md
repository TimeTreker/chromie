# CLAUDE.md

Guidance for coding agents working on Chromie.

## Read First

- `README.md`: current architecture, setup, and verification
- `LLM_CONTEXT.md`: concise engineering boundaries
- `HARDWARE_PROFILES.md`: generated runtime configuration
- `CHROMIE_RUNBOOK.md`: operational commands

Treat the repository and current implementation as the source of truth. Do not rely on old patches, exported ZIP instructions, or historical snippets.

## Working Rules

- Inspect the relevant code before editing.
- Keep changes scoped and preserve existing ownership boundaries.
- Run the Orchestrator from the repository root with `python -m orchestrator.orchestrator`.
- Use `.env.common`, `env/profiles/*.env`, and `.env.local`; do not edit generated `.env.runtime`.
- Use Docker service names for container-to-container traffic.
- Keep Router decisions fast and deterministic by default.
- Keep realtime audio, playback, interruption, and hardware execution in the host Orchestrator.
- Keep TTS generation serialized unless the backend is redesigned for concurrency.
- Log fallback causes; do not silently hide model or service failures.
- Use `docker compose --env-file .env.runtime ...` for manual Compose commands.
- Run `./scripts/run_tests.sh` for control-plane changes.
- Verify syntax and relevant tests before finishing.
