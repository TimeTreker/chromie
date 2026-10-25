# Chromie Handoff

Volatile operational snapshot: checkout, runtime identities, evidence paths and
exact commands. Replace it on each delivery; do not append history. The resume
boundary is in the [checkpoint](DEVELOPMENT_CHECKPOINT.md); current status and the
ordered open work are in [STATUS](docs/STATUS.md).

## Current snapshot — 2026-10-25

- Checkout `/home/chromie/github/chromie`, branch `main`; the expected resume revision is
  the latest `origin/main` commit containing this file (the 2026-10-20 repair and build
  branches are merged; the owner merged them without a post-merge gate).
- Soridormi `/home/chromie/github/soridormi` on `main` at `5b39f14` (its branches merged 2026-10-22), which contains `51a2afa`, the
  revision pinned by `capabilities/soridormi.json` and `release/compatibility.json`. The
  MCP container mounts its `src`, so a `docker restart soridormi-runtime-mcp` loads it and
  resets the scene (user at -90 degrees, 1.5 m).
- Live Agent: `chromie-agent:latest` = `acc2-20261024` (`1c7d4fecab20`), built from this delivery's source and
  recreated with the profile's default timeouts (performance mode, no quiet-mode override); `--verify-agent-source`
  matched (`.chromie/acceptance/acc2-focused-20261024/agent-source-verify.json`). This file is the single owner of the
  deployed identity. Rollback image: `perf2-20261024` (`b27810d373c0`, built from 399894a5a).
  LLM: `chromie-sglang:latest` = `gemma4-fp8`
  (`f59a042e6973`); compose resolves `chromie-sglang:${CHROMIE_IMAGE_TAG}`, so the
  `latest` tag must exist for `start_chromie.sh`.
- Workflow corpus: freeze 47 (`bdb8db08…`; scripts in `.chromie/acceptance/thirsty-offer-20261021/freeze47/`). Restore it with
  `python -m benchmarks.regression restore-fixtures`; do not untar `frozen.tar.xz` over
  `workflow_scenarios/` (its inner `manifest.json` lacks the storage identity).
- Evidence (README in each): `.chromie/acceptance/iter1-20261025/` (owner iteration loop, iteration 1 on 2fd36c9ea:
  hard stop at 32/70, root causes and probes), `acc3-20261024/` (stopped at 57/70 by the machine shutdown),
  `acc2-focused-20261024/`, `acc1-20261024/` (last complete judged cohort), `perf2-20261024/`,
  `perf-4f64f5120-20261024/` (performance-mode baseline), `review-fixes-20261023/` (stopped), `merge-reads-20261023/`, `span-owned-20261023/` (umbrella probes), `main-20cce0dfa-20261023/`,
  `planner-fit-20261023/` (probes, strict replay), `ingress-awaiting-20261023/`,
  `sc-evidence-20261022/` (latest full run; SC schema
  compile check in `.chromie/acceptance/tools/`), `sc-ask-uncertain-20261022/`, `main-ad898cf7f-20261022/`,
  `vj-facts-20261021/` (Value Judgment probes and focused reruns), `thirsty-offer-20261021/` (2026-10-21 run stopped at `errand_remote_en`; freeze 47 scripts), `main-6f8525947-quiet-20261021/` (stopped at
  `multi_thirsty_yes_en`), `umi-time-margin-20261021/` (LLM-lifetime drift), `main-3178a822c-20261021/`,
  `playback-race-20261020/`, `answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`,
  `decided-activity-20261020/`, `main-03974435e-20261020/`.
  Bundles `~/Downloads/chromie_debug_bundle_2026102*.tar.gz`. Earlier runs: `.chromie/acceptance/everyday-20261016/`.
- Last gate (this delivery's source, clean worktree, GPU host, 2026-10-24): pytest 4,039 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets pass (`agent/app/planner_validation.py` is at its line ratchet). Strict replay was not rerun for this delivery; its last pass is 6,000/6,000 on freeze 47 (2026-10-23). The gate needs `anthropic==1.15.0` from `requirements-test.txt` (`INSTALL_TEST_DEPS=1`).
- `start_chromie.sh --build` reuses the layer cache, takes package downloads from BuildKit
  cache mounts, and recreates only the services whose image changed. The first build
  after this change reruns the cache-mount layers once.
- After a host reboot start the Soridormi water scene (command below); its runner also starts
  `soridormi-runtime-mcp`. The runner stays in the foreground; stopping it (or a command
  timeout around it) removes the simulator container, so start it detached (`setsid nohup … &`); start long cohorts
  the same way so a closed session cannot stop them. `/tmp` (scratch probes) does not survive a reboot.
- Live runs use the local `chromie-gemma4-12b`. Restart `chromie-llm` before a cohort, never
  during one: SGLang greedy output depends on earlier traffic in one server lifetime, and a
  near-tie decision can also flip between lifetimes (about 3 nats observed for the same request).
  Compare prompt candidates by decision-token logprob margin (`logprobs: true`) on at least two
  lifetimes; replays within one lifetime are not stability evidence.
- Quiet mode (owner request 2026-10-21): `sudo .chromie/quiet-mode/quiet-mode.sh on` turns CPU
  turbo off, sets the power-saver profile, locks GPU clocks to 210-1800 MHz and caps GPU power
  at its minimum; `off` restores, `status` shows, `enable-at-boot` reapplies it after reboots
  (a reboot otherwise resets it). Only the owner runs it. Timeouts are raised
  by the ignored `.chromie/quiet-mode/agent-timeouts.env` (Agent, through
  `CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE`) and `host-timeouts.env` (exported in the harness shell;
  its 60 s TTS playback-start barrier lifts the 30 s speech request timeout to 65 s);
  `runtime-identity.json` still records the profile defaults.
- The main checkout's ignored `workflow_scenarios/` copy was stale on 2026-10-20 and the
  replay refused it; restore with `python -m benchmarks.regression restore-fixtures` after
  moving the stale files aside.
- `.env.runtime` may be in `mode:speech`; give the harness process
  `ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco` instead of editing it.
- `.chromie/voice-runtime/orchestrator.env` is generated by `start_chromie.sh`; regenerate
  it (`./scripts/start_chromie.sh --keep-services --no-orchestrator`) when
  `capture_runtime_identity.py` reports missing profile-owned budgets.

## Deploy and run

```bash
# resume the owner's iteration loop (up to 8): rebuild and deploy this revision, fresh LLM and scene, complete
# cohort, one bundle, judge every case, fix at the earliest boundary, gate, commit and push
# owner: rebuild the Agent from a clean main checkout and deploy it (performance mode; in quiet mode prefix
# CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE=.chromie/quiet-mode/agent-timeouts.env)
# (rollback: docker tag chromie-agent:perf2-20261024 chromie-agent:latest)
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy ./scripts/compose.sh build chromie-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy ./scripts/compose.sh up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
# Soridormi water scene (replaces the simulator only when the runtime is idle)
(cd ../soridormi && ./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer)
# fresh LLM lifetime and scene, identity, complete cohort
docker restart chromie-llm soridormi-runtime-mcp
D=.chromie/acceptance/<new-run-dir>
set -a; . .chromie/quiet-mode/host-timeouts.env; set +a   # quiet mode only
python scripts/capture_runtime_identity.py --orchestrator-env .chromie/voice-runtime/orchestrator.env --allow-dirty --output $D/runtime-identity.json
ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --goal-driven-runtime apply --execute --runtime-identity $D/runtime-identity.json --evidence-dir $D/live
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
