# Chromie Handoff

Volatile operational snapshot: checkout, runtime identities, evidence paths and
exact commands. Replace it on each delivery; do not append history. The resume
boundary is in the [checkpoint](DEVELOPMENT_CHECKPOINT.md); current status and the
ordered open work are in [STATUS](docs/STATUS.md).

## Current snapshot — 2026-10-17

- Checkout `/home/chromie/github/chromie`, branch `main`; the expected resume revision
  is the latest `origin/main` commit containing this file.
- Soridormi `/home/chromie/github/soridormi`: check out `origin/main` `3766c79`, the
  revision pinned by `capabilities/soridormi.json` and `release/compatibility.json`,
  and restart the water scene from it (the last recorded running checkout was
  `33b8a13`).
- Last recorded live Agent: `chromie-agent:latest` = `rootcause18-20261016` (rollback
  image). No built image matches `main`: `rootcause19-20261016` predates the 2026-10-17
  source changes. Rebuild the Agent image from `main` before deploying.
- Workflow corpus: freeze 42 (`de7c4de6…`). Restore it with
  `python -m benchmarks.regression restore-fixtures`; do not untar `frozen.tar.xz` over
  `workflow_scenarios/` (its inner `manifest.json` lacks the storage identity).
- Evidence: `.chromie/acceptance/everyday-20261016/` (README; `run6/`, `run7/`).
- Last gate and strict replay: pytest 3,955 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets pass; `tests/test_workflow_replay.py` 94 passed over 6,046 restored fixtures.
- `.env.runtime` may be in `mode:speech`; give the harness process
  `ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco` instead of editing it.

## Deploy and run

```bash
# owner: rebuild the Agent from a clean main checkout and deploy it
# (rollback: docker tag chromie-agent:rootcause18-20261016 chromie-agent:latest)
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy ./scripts/compose.sh build chromie-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy ./scripts/compose.sh up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
# Soridormi water scene (replaces the simulator only when the runtime is idle)
(cd ../soridormi && ./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer)
# capture identity, then smoke; then core + challenge with --stage core --stage challenge
D=.chromie/acceptance/everyday-20261016
python scripts/capture_runtime_identity.py --orchestrator-env .chromie/voice-runtime/orchestrator.env --allow-dirty --output $D/run8/runtime-identity.json
ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --stage must_pass --goal-driven-runtime apply --execute --runtime-identity $D/run8/runtime-identity.json --evidence-dir $D/run8/live
./scripts/collect_debug_bundle.sh
```

Compose interpolates `${HTTP_PROXY:-}` from the deploying shell; a shell proxy on
`127.0.0.1` gives containers a proxy on their own loopback (TTS crash-loops, weather
lookups fail). Always deploy with the proxy variables unset as above. On this host,
container egress to Open-Meteo goes through the host's Clash TUN.

## Verify

Run the canonical gate from a clean worktree, then strict replay:

```bash
git worktree add --detach <dir> HEAD
(cd <dir> && ./scripts/run_tests.sh)
python scripts/run_workflow_replay.py --workers 8 --evidence-dir <new dir>
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

New live runs need a fresh evidence directory; do not overwrite an existing run.
