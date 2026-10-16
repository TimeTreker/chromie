# Chromie Handoff

## Current work — B (answer from perception) and E (receipt), 2026-10-16

Checkout `/home/chromie/github/chromie`, branch `main`; pre-delivery base `origin/main` `79e26919c`; these changes are
pushed to `origin/main` (expected resume revision: the latest commit containing this file). Soridormi `origin/main`
`33b8a13`, water scene running. Live: `chromie-agent:latest` = `rootcause14-20261016`. Built, not deployed:
`chromie-agent:rootcause16-20261016` (`sha256:4e2c2595…`, 125 files identical, digest `643bc027d7828a4f`; also carries
the clock fix of `79e26919c`). Evidence: `.chromie/acceptance/everyday-20261016/` (README "Repairs B and E").
Gate worktree `scratchpad/gate29`. `.env.runtime` is in `mode:speech`: give the harness process the two voice_mujoco keys.

```bash
# owner: deploy (rollback: chromie-agent:rootcause14-20261016)
docker tag chromie-agent:rootcause16-20261016 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then smoke (SC and Planner changed for every turn), the history case, then core + challenge
ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --stage must_pass --goal-driven-runtime apply --execute --runtime-identity <identity> --evidence-dir .chromie/acceptance/everyday-20261016/run4/live
```

## Previous work — Clock common tier; scenario corrections, 2026-10-16

Checkout `/home/chromie/github/chromie`, branch `main`; pre-delivery base `origin/main` `e1d14b8ec`; these changes are
pushed to `origin/main` (expected resume revision: the latest commit containing this file). Soridormi `origin/main`
`33b8a13`, water scene running. Live: `chromie-agent:latest` = `rootcause14-20261016`. Built, not deployed:
`chromie-agent:rootcause15-20261016` (`sha256:529d7a25…`, 125 files identical, digest `a9e639daa055a708`). Evidence:
`.chromie/acceptance/everyday-20261016/` (README; `run2/`, `run2-history/`, `run3/` with bundles). Gate worktree
`scratchpad/gate28`. `.env.runtime` is in `mode:speech`; give the harness process the two voice_mujoco keys (below)
rather than editing it.

```bash
# owner: deploy (rollback: chromie-agent:rootcause14-20261016)
docker tag chromie-agent:rootcause15-20261016 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then core + challenge (smoke passed in run 2)
ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --stage core --stage challenge --goal-driven-runtime apply --execute --runtime-identity <identity> --evidence-dir .chromie/acceptance/everyday-20261016/run4/live
```

## Previous work — Everyday smoke repair (UMI demonstratives), 2026-10-16

Checkout `/home/chromie/github/chromie`, branch `main` (the earlier `planner-limitation-contracts` branch is merged
and deleted); pre-delivery base `origin/main` `c942172ae`; these changes are pushed to `origin/main` (expected resume
revision: the latest commit containing this file). Soridormi `origin/main` `33b8a13`, water scene running. Live:
`chromie-agent:latest` = `rootcause13-20261015`. Evidence: `.chromie/acceptance/everyday-20261016/` (README.md;
`run1/` smoke 13/15 with its bundle; `umi_*.txt` replays); probes `umi_variant_replay.py`, `umi_fork.py`,
`umi_regress.py`; `capture40.py`, `freeze40.py`, `freeze40-review.json`, `strict-replay-freeze40/` in
`.chromie/acceptance/remaining-defects-20261013/`. Gate worktree `scratchpad/gate27`. Built, not deployed: `chromie-agent:rootcause14-20261016` (`sha256:4fe9d3d4…`, 125 files identical, digest `def53b3786935f97`).

```bash
# owner: deploy (rollback: chromie-agent:rootcause13-20261015)
docker tag chromie-agent:rootcause14-20261016 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then the smoke stage again (the UMI change touches every turn), and the new history case
python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --stage must_pass --goal-driven-runtime apply --execute --runtime-identity <identity> --evidence-dir .chromie/acceptance/everyday-20261016/run2/live
python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --only-case multi_that_water_zh --goal-driven-runtime apply --execute --runtime-identity <identity> --evidence-dir .chromie/acceptance/everyday-20261016/run2-history/live
```

## Previous work — Everyday live cohort in the repo; clock common tier, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`773ad886c`; these changes are pushed to `origin/main` (expected resume revision: the latest commit containing this
file). Soridormi `origin/main` `33b8a13`, water scene running. Live: `chromie-agent:latest` = `rootcause12-20261015`;
`chromie-agent:rootcause13-20261015` (the `773ad886c` Agent source) built, not deployed. The clock tier lives in the
mounted `capabilities/prompt_tiers.json`, so recreating the Agent container applies it. Gate worktree `scratchpad/gate26`.

```bash
# owner: deploy (rollback: chromie-agent:rootcause12-20261015)
docker tag chromie-agent:rootcause13-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then the everyday smoke stage first (no --keep-going: a hard smoke failure stops core and challenge)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root scenarios/everyday --goal-driven-runtime apply --execute --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Focused run 16 repair, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`5526e71cb`; pushed as `773ad886c`. Soridormi `origin/main` `33b8a13`, water scene running. Evidence:
`.chromie/acceptance/remaining-defects-20261013/` (README "Live run 16 (focused) and the v2 everyday cohort";
`run16/`; `probes/planner_single_activity_refs_replay.py`; `daily-scenarios-v2/` and its builder). Live:
`chromie-agent:latest` = `rootcause12-20261015`. Gate worktree `scratchpad/gate25`. Built, not deployed:
`chromie-agent:rootcause13-20261015` (`sha256:354d6eec…`, 125 files identical, digest `5848cf023a42f77e`).

```bash
# owner: deploy (rollback: chromie-agent:rootcause12-20261015)
docker tag chromie-agent:rootcause13-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then the smoke stage first (no --keep-going: a hard smoke failure stops later stages)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root <everyday suite> --goal-driven-runtime apply --execute --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-15 repairs, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`5b29ea29b`; pushed as `5526e71cb`. Soridormi `origin/main` `33b8a13`; water scene running since the 2026-10-15 reboot. Evidence:
`.chromie/acceptance/remaining-defects-20261013/` (README "Live run 15" and "Repairs after run 15"; `run15/`;
`probes/planner_time_first_replay.py`; `capture39.py`, `freeze39.py`, `strict-replay-freeze39/`,
`level-a-run15-repairs/`). Live: `chromie-agent:latest` = `rootcause12-20261015` (deployed by the owner on 2026-10-15). Gate worktree
`scratchpad/gate24`. `chromie-agent:rootcause12-20261015` (`sha256:0c69f2fa…`, 125 files identical, digest `08def7a73277d66b`).

```bash
# deployed 2026-10-15 (rollback: chromie-agent:rootcause11-20261015)
docker tag chromie-agent:rootcause12-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then focused run 16 (done: run16/)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-14 repairs, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`ad4dfcf96`; pushed as `5b29ea29b`. Soridormi `origin/main` `33b8a13`; water scene restarted after the 2026-10-15 reboot. Evidence:
`.chromie/acceptance/remaining-defects-20261013/` (README "Live run 14" and "Repairs after run 14"; `run14/`;
`probes/calls.py`, `probes/sc_drop_need_replay.py`, `probes/planner_refs_first_replay.py`;
`strict-replay-run14-repairs/`, `level-a-run14-repairs/`). Live: `chromie-agent:latest` = `rootcause11-20261015` (deployed by the owner on 2026-10-15).
Gate worktree `scratchpad/gate23`. `chromie-agent:rootcause11-20261015` (`sha256:7aa59da6…`,
125 files identical, digest `3ef029f9a6cb7e73`).

```bash
# deployed 2026-10-15 (rollback: chromie-agent:rootcause10-20261015)
docker tag chromie-agent:rootcause11-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 15 (done: run15/)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-13 repairs, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`ce42d576d`; pushed as `ad4dfcf96`. Soridormi `origin/main` `33b8a13`; the water scene was restarted after a host reboot on 2026-10-15
(`./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile
open_duck_forward --viewer`). Evidence:
`.chromie/acceptance/remaining-defects-20261013/` (README "Live run 13" and "Repairs after run 13"; `run13/`;
`probes/binding/identity_pairs.json`, `probes/binding/cause_pairs.json`; `capture38.py`, `freeze38.py`,
`strict-replay-freeze38/`, `level-a-run13-repairs/`). Live: `chromie-agent:latest` = `rootcause10-20261015` (deployed by the owner on 2026-10-15; `chromie-llm` restarted).
Gate worktree `scratchpad/gate21` (lost in the reboot). `chromie-agent:rootcause10-20261015` (`sha256:5368e6a2…`, 125 files identical, digest `4bddd79b07cf8d62`).
The notice and scope-extension fixes are Host-side and run from this checkout. Watch scheduler RSS across cohorts (26 GB peak before the restart).

```bash
# deployed 2026-10-15 (rollback: chromie-agent:rootcause9-20261015)
docker tag chromie-agent:rootcause10-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 14 (done: run14/)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Live run 12; SC words survive the exact-words join, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`0ead8031f`; pushed as `ce42d576d`. Soridormi `origin/main` `33b8a13`, water scene running since 2026-10-15. Evidence:
`.chromie/acceptance/remaining-defects-20261013/` (README "Live run 12" and "Repair after run 12"; `run12/` with
identity, bundle and digests; `probes/planner_args_replay.py`, `probes/binding/date_replay.txt`). Live:
`chromie-agent:latest` = `rootcause9-20261015` (deployed by the owner on 2026-10-15). Gate worktree
`scratchpad/gate20`. `chromie-agent:rootcause9-20261015` (`sha256:bcc9ebed…`, 125 files identical, digest `60ec1216930957a5`).

```bash
# deployed 2026-10-15 (rollback: chromie-agent:rootcause8-20261015)
docker tag chromie-agent:rootcause9-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 13 (done: run13/)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-11 repairs, 2026-10-15

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`941f09796`; pushed as `0ead8031f`. Soridormi `origin/main` `33b8a13`; the water scene was restarted on 2026-10-15 after a host reboot
(`./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile
open_duck_forward --viewer`). Evidence: `.chromie/acceptance/remaining-defects-20261013/` (README "Live run 11" and
"Repairs after run 11"; `run11/` with identity, bundle and digests; `probes/binding/` and the replay probes;
`capture37.py`, `freeze37.py`, `strict-replay-freeze37/`, `level-a-run11-repairs/`). Live:
`chromie-agent:latest` = `rootcause8-20261015` (deployed by the owner on 2026-10-15). Gate worktree
`scratchpad/gate19`. `chromie-agent:rootcause8-20261015` (`sha256:0248c42d…`, 125 files identical to the gate worktree, digest
`169e55c8c36366dd`). The handover-phase fix is in `orchestrator/orchestrator.py` and runs from this checkout.

```bash
# deployed 2026-10-15 (rollback: chromie-agent:rootcause7-20261014)
docker tag chromie-agent:rootcause8-20261015 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 12 (done: run12/)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Repeated Activities; Planner-free identity, 2026-10-14

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`4ed5a5143`; pushed as `941f09796`. Soridormi `origin/main` `33b8a13`, scene running it. Evidence: `.chromie/acceptance/remaining-defects-20261013/`
(README "Repeated Activities — root cause and repair"; `probes/dup_*.py` and `probes/dup/`; `probes/identity_replay.py`
and `probes/identity3/`; `capture36.py`, `freeze36.py`, `strict-replay-freeze36/`, `level-a-repetition/`). Live:
`chromie-agent:latest` = `rootcause6-20261014`. Gate worktree `scratchpad/gate18`. Deployed by the owner on 2026-10-15 (measured as run 11):
`chromie-agent:rootcause7-20261014` (`sha256:71f279bf…`, 125 files identical to the gate worktree, digest
`4d7075dbae2047d9`). Restore the frozen corpus with `python -m benchmarks.regression restore-fixtures`; do not
untar `frozen.tar.xz` over `workflow_scenarios/` (its inner `manifest.json` lacks the storage identity).

```bash
# deployed 2026-10-15 (rollback: chromie-agent:rootcause6-20261014)
docker tag chromie-agent:rootcause7-20261014 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 11 (done: run11/)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Owner identity direction, 2026-10-14

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; base `95a8ee5aa`; committed by the
owner as `4ed5a5143`. Soridormi `/home/chromie/github/soridormi` = `origin/main` `33b8a13`, scene
running it. Evidence: `.chromie/acceptance/remaining-defects-20261013/` (README "Live run 10" and "Repairs after run
10"; `run10/`; `probes/identity2/` with `pairs_projected.json`; `capture35.py`, `freeze35.py`,
`strict-replay-freeze35/`, `level-a-identity/`). Gate worktree `scratchpad/gate16`. Live:
`chromie-agent:rootcause6-20261014` (`sha256:417b8cde…`, digest `ebfae93f9c0234ef`) was deployed by the owner on
2026-10-14.
The Mind profile is read by the host orchestrator from `config/mind/chromie_default.json` (`ORCH_MIND_PROFILE_PATH`),
so the identity texts take effect from the checkout; the SC prompt needs the new image.

```bash
# owner: deploy (rollback: chromie-agent:rootcause5-20261014)
docker tag chromie-agent:rootcause6-20261014 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 11 on the everyday cohort (one invocation, one bundle)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-9 repairs, 2026-10-14

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`c101d8272`; the run-9 repairs are pushed to `origin/main` (expected resume revision: the latest commit containing
this file). Soridormi `/home/chromie/github/soridormi` (branch `scenario-control-stall`): the declared
non-completion change is pushed to Soridormi `origin/main` on top of `af20f8b`; the water scene was restarted with it
on 2026-10-14 (sim and MCP bind-mount that checkout). Evidence: `.chromie/acceptance/remaining-defects-20261013/` (README "Live
run 9" and "Repairs after run 9"; `run9/` with bundle and digests; `probes/replay_generic.py` and its
`identity/`, `missing/`, `reentry/` outputs; `capture34.py`, `freeze34.py`, `strict-replay-freeze34/`,
`level-a-run9-repairs/`). Gate worktree `scratchpad/gate15`. Live:
`chromie-agent:latest` = `rootcause5-20261014` (`sha256:c592f99a…`, digest `94c0fec19599560d`), deployed by the
owner on 2026-10-14 and measured as run 10.

```bash
# deployed 2026-10-14 (rollback: chromie-agent:rootcause4-20261013)
docker tag chromie-agent:rootcause5-20261014 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# (already done) restart the Soridormi scene after a Soridormi change; it replaces the simulator only when idle
# cd /home/chromie/github/soridormi && ./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer
# then live run 10 on the everyday cohort (one invocation, one bundle)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-8 repairs, 2026-10-13

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`; pre-delivery base `origin/main`
`1d432208b`; the run-7 + run-8 repairs are pushed to `origin/main` (expected resume revision: the latest commit
containing this file). Evidence: `.chromie/acceptance/remaining-defects-20261013/` (README "Live
run 8" and "Repairs after run 8"; `run8/` with bundle and digests; `capture33.py`, `freeze33.py`,
`strict-replay-freeze33/`, `level-a-run8-repairs/`, `probes/recipient/`, `run8-soridormi/`). Gate worktree
`scratchpad/gate14`. `chromie-agent:rootcause4-20261013` (`sha256:e310f2b4…`, digest `52c25882a59fa651`) was
deployed by the owner on 2026-10-14 and measured as run 9.

Soridormi: the fix is pushed to Soridormi `origin/main` (on top of `afb6a1a`) from `/home/chromie/github/soridormi`
(branch `scenario-control-stall`, bind-mounted into sim and MCP). The water scene was restarted with it (`./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer`,
which replaces the simulator only when the runtime is idle and restarts the MCP).

```bash
# owner: deploy (rollback: chromie-agent:rootcause3-20261013)
docker tag chromie-agent:rootcause4-20261013 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 9 on the everyday cohort (one invocation, one bundle)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-7 cluster repairs, 2026-10-13

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts` = `origin/main` `1d432208b` plus the
run-7 repair diff (delivered with the run-8 repairs above). Evidence: `.chromie/acceptance/remaining-defects-20261013/` (README "Repairs after
run 7"; `capture32.py`, `freeze32.py`, `strict-replay-freeze32/`, `level-a-run7-repairs/`, `daily-scenarios/`).
Gate worktree `scratchpad/gate13`. Live: `chromie-agent:latest` = `rootcause2-20261013`; built and verified, not
deployed: `chromie-agent:rootcause3-20261013` (`sha256:a62d744a…`, digest `d19269a8c3864d4a`).

```bash
# owner: deploy (rollback: chromie-agent:rootcause2-20261013)
docker tag chromie-agent:rootcause3-20261013 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then live run 8 on the everyday cohort (one invocation, one bundle)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live
```

## Previous work — Run-5 root-cause repairs, 2026-10-13

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts` (= `origin/main`
`ff9e87417` plus the uncommitted repair diff); the expected resume revision is the latest commit
containing this file. Evidence: `.chromie/acceptance/remaining-defects-20261013/` (README with the
per-episode workflows; `capture30.py`, `freeze30.py`, `strict-replay-freeze30/`, `level-a/`, `probes/`
holding the weather, UMI, SC and Planner probes and their outputs). Gate worktree:
`/tmp/claude-1000/-home-chromie-github-chromie/e21d98fd-a592-451c-b8b4-95a68a5e25c7/scratchpad/gate11`
(diff applied, freeze-30 case files extracted).

Live state: `chromie-agent:latest` = `option-b2-e96811c56` (`cc4b1ca3`); TTS self-warming; Soridormi
water scene. Built and verified, not deployed: `chromie-agent:rootcause-20261013` (`sha256:91b4763d…`,
125 files identical to the gate tree, digest `a31918e2555535df`).

Live run 6 ran on `chromie-agent:rootcause-20261013` (`run6/`, judged in the README). The run-6 repairs
are in the tree; image `chromie-agent:rootcause2-20261013` (`sha256:46fab20a…`, 125 files identical to
`scratchpad/gate12`, digest `60242981da267ac0`) is deployed (owner). Freeze 31 archive `fa793952…`.
Run 7 (daily-life cohort, `daily-scenarios/`, `run7/`) is judged in the README; rerun it with
`python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/remaining-defects-20261013/daily-scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity <identity> --evidence-dir <dir>/live`.

```bash
# deployed 2026-10-13 (rollback: chromie-agent:rootcause-20261013, then option-b2-e96811c56)
docker tag chromie-agent:rootcause2-20261013 chromie-agent:latest
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# then: live run 6 on the full directory-discovered cohort (one invocation, one bundle), judged in the README
python scripts/run_workflow_replay.py --workers 8 --evidence-dir <new dir>   # strict replay, freeze 30
```

Network fact (2026-10-13): container egress does not reach Open-Meteo directly. The host runs Clash
Verge (mihomo) in TUN mode with fake-IP DNS; Open-Meteo matches the final `Match` rule → `PROXY` →
`bwg-hy2` (Hysteria2) over a phone hotspot. `trust_env=False` does not bypass the TUN.

## Previous work — Planner limitation contracts, 2026-10-12

Checkout `/home/chromie/github/chromie`, branch `planner-limitation-contracts`, base `origin/main`
`41570d182`, delivered to `origin/main`; the expected resume revision is the latest commit containing this
file. Soridormi's nod/shake minimum and runner stall tolerance are delivered on Soridormi `main`. Evidence: `.chromie/acceptance/planner-limitation-20261012/`
(`capture24.py`, `freeze24.py`, `capture24/`, `strict-replay-freeze24/`). The large corpus case files
are extracted from `benchmarks/integration/workflow_scenarios/frozen.tar.xz` (freeze 24, `4edf2a83…`).

Live state on this host is unchanged: `chromie-agent:latest` = stage B `41570d182`, `chromie-llm`
image `03ad9e33` (has the grammar-retention leak; its scheduler RSS grows ~2.4 GB per new Planner
schema, so restart it before any long cohort). Fixed LLM image built, not deployed:
`chromie-sglang:grammar-retention` (branch `sglang-grammar-retention`, worktree `scratchpad/sglang-fix`).

```bash
# deploy the LLM fix (owner OK required; idle service)
docker tag chromie-sglang:gemma4-fp8 chromie-sglang:gemma4-fp8-pre-retention
docker tag chromie-sglang:grammar-retention chromie-sglang:gemma4-fp8
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-llm
# gate from a clean worktree (the main checkout holds a peer worktree under .claude/worktrees that breaks check_docs)
git worktree add --detach <dir> HEAD && (cd <dir>/benchmarks/integration/workflow_scenarios && tar -xJf frozen.tar.xz --exclude=manifest.json) && (cd <dir> && ./scripts/run_tests.sh)
python scripts/run_workflow_replay.py --workers 8 --evidence-dir <new dir>
```

Live run 1 is judged in the evidence README. The owner deployed the LLM fix and
`chromie-agent:planlim-wt2-20261012` (run-1 fixes A/G/I), then asked for the nine pre-existing items
to be fixed before testing; those repairs are in the tree (README "Owner list after run 1"), with
freeze 26 (`capture26.py`, `freeze26.py`, archive `e8f7f805…`). The large corpus case files are
extracted from `frozen.tar.xz` (freeze 26).

Gate on the full working tree (clean worktree `scratchpad/gate5`, diff applied): pytest 3,791 + 5
skipped, benchmarks 169, legacy 20; strict replay 6,000/6,000 with zero model calls
(`strict-replay-freeze26/`); Level A 46/46 (`level-a-run1-repairs/`).

Run 2 (`chromie-agent:planlim-wt3-20261012`) is judged in the evidence README (`run2/`); the run-2
repairs and freeze 27 (`capture27.py`, `freeze27.py`, archive `ae3af4ea…`) are in the tree. Gate on the
full working tree (clean worktree `scratchpad/gate6`): pytest 3,799 + 5 skipped, benchmarks 169,
legacy 20; strict replay 6,000/6,000, zero model calls (`strict-replay-freeze27/`); Level A 46/46.

Images built from that worktree, sources verified byte for byte: `chromie-agent:planlim-wt4-20261012`
(`sha256:17668723…`, 118 files, digest `807cc483d4d03d35`) and `chromie-tts:selfwarm-20261012`
(`sha256:41ce0994…`, thin layer over `chromie-tts:latest` = `c544a0d0…`, built from
`.chromie/acceptance/planner-limitation-20261012/TTSDockerfile`). Soridormi nod/shake minimum and the
runner stall tolerance stay uncommitted on Soridormi branch `scenario-control-stall` (MCP bind-mounts it).

```bash
# owner: deploy (rollbacks: chromie-agent:stageB-41570d182, chromie-tts:pre-selfwarm-20261012)
docker tag chromie-agent:planlim-wt4-20261012 chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
docker tag chromie-tts:latest chromie-tts:pre-selfwarm-20261012
docker tag chromie-tts:selfwarm-20261012 chromie-tts:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-tts
```

Deploy pitfall (2026-10-12): Compose interpolates `${HTTP_PROXY:-}` from the deploying shell before
`--env-file`. A shell with `HTTP_PROXY=http://127.0.0.1:7897` gives containers a proxy on their own
loopback: TTS crash-looped (`huggingface_hub` re-raises ProxyError instead of using the local cache) and
the Agent's weather lookups were refused. Run Compose with `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy
-u https_proxy`; container egress then follows the host's Clash TUN (see the 2026-10-13 network fact).

Live state on this host (owner-deployed): `chromie-agent:latest` = `chromie-agent:planlim-wt4-20261012`,
`chromie-tts:latest` = `chromie-tts:selfwarm-20261012` (rollback `chromie-tts:pre-selfwarm-20261012`),
`chromie-llm` = the grammar-retention image, Soridormi MCP restarted on the working tree. Runs 3 and 4
(`run3/`, `run4/`) are judged in the evidence README; run 4 is on the delivered tree (host code from the
checkout, same images). Final gate on the full tree (`scratchpad/gate7`): pytest 3,801 + 5 skipped,
benchmarks 169, legacy 20; strict replay 6,000/6,000 (`strict-replay-final/`). Corpus freeze 27
(`frozen.tar.xz` archive `ae3af4ea…`); re-extract after pulling as in the previous delivery.

```bash
# resume: rerun the declared 35-case cohort on the deployed images (one invocation, one bundle)
D=.chromie/acceptance/planner-limitation-20261012
python scripts/capture_runtime_identity.py --orchestrator-env .chromie/voice-runtime/orchestrator.env --allow-dirty --output $D/runN/runtime-identity.json
python scripts/general_ability_acceptance.py --mode live-text --scenario-root $D/scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity $D/runN/runtime-identity.json --evidence-dir $D/runN/live
./scripts/collect_debug_bundle.sh
```

Option B (owner, 2026-10-12) is in this revision (see DEVELOPMENT_CHECKPOINT). Live state on this host
(2026-10-13): `chromie-agent:latest` = `chromie-agent:option-b2-e96811c56` (`sha256:cc4b1ca3…`, built from
`e96811c56`; rollback `chromie-agent:option-b-20261012`), `chromie-tts:latest` = self-warming TTS, Soridormi
water scene started with `(cd ../soridormi && ./scripts/run_scenario.sh --scenario
configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer)`. Corpus freeze 29
(`frozen.tar.xz` archive `e2f282fb…`). Evidence: `focused-b2/`, `run5/` (one bundle) in
`.chromie/acceptance/planner-limitation-20261012/`; the harness settle repair is host-side (no image change).

```bash
# rerun the declared cohort (one invocation, one bundle) after capturing identity
D=.chromie/acceptance/planner-limitation-20261012
python scripts/capture_runtime_identity.py --orchestrator-env .chromie/voice-runtime/orchestrator.env --allow-dirty --output $D/runN/runtime-identity.json
python scripts/general_ability_acceptance.py --mode live-text --scenario-root $D/scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity $D/runN/runtime-identity.json --evidence-dir $D/runN/live
./scripts/collect_debug_bundle.sh
```

Next: the owner-approved daily-life scenario suite (DEVELOPMENT_CHECKPOINT "Next").

## Previous delivery — Deep Planner retired (stage B), 2026-10-11

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `5ea034e35`; the
expected resume revision is the latest commit containing this file (developed in a temporary
worktree on branch `deep-removal`). After pulling, re-extract the corpus: delete
`benchmarks/integration/workflow_scenarios/workflow-*.json` and `artifacts/`, then
`python -m benchmarks.regression restore-fixtures`. Evidence: `.chromie/acceptance/deep-removal-20261011/` in the main checkout
(README.md, PLAN.md, `capture23.py`, `freeze23.py`, `make_cohort_b.py`, `oracle.json`,
`AgentDockerfile`, live runs and bundles).

Live state on this host: `chromie-agent:latest` = the stage B image built with
`.chromie/acceptance/deep-removal-20261011/AgentDockerfile` (it removes the base image's source trees so deleted modules cannot linger),
created from the main-checkout compose with a regenerated `.env.runtime`
(`CHROMIE_OPERATOR_MODE=voice_mujoco python scripts/generate_runtime_env.py`). Rollback image:
`chromie-agent:vj-3f19ecf0d`. `chromie-llm` `03ad9e33` unchanged.

```bash
# rollback to Value Judgment
docker tag chromie-agent:vj-3f19ecf0d chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
# rebuild/deploy this revision (main checkout)
docker build -q -f .chromie/acceptance/deep-removal-20261011/AgentDockerfile -t chromie-agent:stageB-$(git rev-parse --short=9 HEAD) .
docker tag chromie-agent:stageB-$(git rev-parse --short=9 HEAD) chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
# corpus freeze 23 (only if a Planner/UMI/GA request changes): restore freeze 22, then
PYTHONPATH=.:.chromie/acceptance/deep-removal-20261011 python3 .chromie/acceptance/deep-removal-20261011/capture23.py benchmarks/integration/workflow_scenarios
PYTHONPATH=.:.chromie/acceptance/deep-removal-20261011 python3 .chromie/acceptance/deep-removal-20261011/freeze23.py small && PYTHONPATH=.:.chromie/acceptance/deep-removal-20261011 python3 .chromie/acceptance/deep-removal-20261011/freeze23.py large
python scripts/run_workflow_replay.py --workers 8 --evidence-dir <new dir>
# live cohort (water scene running; restart chromie-llm first; Soridormi runner crashes ~25 min in)
python scripts/general_ability_acceptance.py --mode live-text --scenario-root .chromie/acceptance/deep-removal-20261011/scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity .chromie/acceptance/deep-removal-20261011/runtime-identity.json --evidence-dir .chromie/acceptance/deep-removal-20261011/<run>
./scripts/collect_debug_bundle.sh   # once per run
```

Gate: passed on `227aceb03` and on the refreeze commit `8165314a8` (pytest 3,758, benchmarks 169, legacy 20). For later revisions run
`./scripts/run_tests.sh` from a clean worktree.
Known failures and open decisions: see the checkpoint (conditional composition 0/4,
multi-Responsibility mixed limitation 0/4, SC silence on a limitation, speech-only deception).

## Previous delivery — Value Judgment (VALUE-JUDGMENT-001), 2026-10-11

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `1b7afb9ff`. The
expected resume revision is the latest commit containing this file. Evidence:
`.chromie/acceptance/value-judgment-impl-20261011/` (design evidence in
`.chromie/acceptance/value-judgment-20261010/`).

Changed:
- Code: `agent/app/{value_judgment,main,inference_compute,planner_prompt}.py`,
  `shared/chromie_contracts/value_judgment.py`, `orchestrator/clients/agent_client.py`,
  `orchestrator/orchestrator.py`, `orchestrator/runtime/{cognitive_runtime,capability_runtime}.py`.
- Config: `config/mind/chromie_default.json` (0.9.0), `capabilities/value_review.json`,
  `config/runtime_exception_boundaries.json`.
- Tests: `tests/test_value_judgment.py`, `tests/test_mind_profile.py`,
  `tests/test_cognitive_identity_context.py`.
- Docs: `docs/{PROJECT_CHARTER,API_REFERENCE,CONFIGURATION,STATUS}.md`, this file and the
  checkpoint.

Verification:

```bash
python -m pytest -q tests/test_value_judgment.py tests/test_mind_profile.py tests/test_cognitive_identity_context.py
# canonical gate from a clean worktree (the main checkout contains a peer's .claude/worktrees/):
git worktree add --detach <tmp>/gate HEAD && (cd <tmp>/gate && python scripts/check_repository_policies.py && python scripts/check_docs.py && python scripts/check_test_ownership.py && ./scripts/run_tests.sh)
```

Gate observed from a clean worktree (HEAD `1b7afb9ff` plus this patch): policies, docs and
test ownership exit 0. `run_tests.sh` exit 0: 169 / 4,060 / 5 skips / 1,065 subtests / 20
legacy. Strict replay is unaffected: the replay harness runs with an empty value-review list,
and neither the SC prompt nor any corpus request changed.

Deploy and live cohort (after this commit; the water scene must be running):

```bash
docker tag chromie-agent:latest chromie-agent:pre-value-judgment-20261011     # rollback = stageA-78fb2b871
docker build -q -f .chromie/acceptance/provider-source-branches-20261009/AgentDockerfile -t chromie-agent:vj-$(git rev-parse --short HEAD) .
docker tag chromie-agent:vj-$(git rev-parse --short HEAD) chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent --output .chromie/acceptance/value-judgment-impl-20261011/runtime-identity.json
docker restart chromie-llm     # fresh SGLang lifetime before the cohort
E=.chromie/acceptance/value-judgment-impl-20261011
python scripts/general_ability_acceptance.py --mode live-text --scenario-root $E/scenarios --goal-driven-runtime apply --execute --keep-going --runtime-identity $E/runtime-identity.json --evidence-dir $E/live
./scripts/collect_debug_bundle.sh      # once, after the cohort; copy into $E/bundle
(cd $E && python3 adjudicate.py live bundle)
```

`$E/scenarios/` holds the 20 design and 16 held-out cases; `oracle.json` holds the labels
declared on 2026-10-10.

Run 1 (Agent `chromie-agent:vj-cfafb7d9b`, rollback `chromie-agent:pre-value-judgment-20261011`,
Soridormi water scene running, LLM `03ad9e33`) stopped after 2 of 36 cases on an evidence
lineage failure. Evidence is in `$E/run1/` (live, live.log, bundle). The fix commit changes
only the Orchestrator and docs, so the deployed Agent image still matches; recapture the
identity at the new revision before the full cohort. Lineage-fix verification: strict replay
6,000/6,000 with zero model calls (`python scripts/run_workflow_replay.py --workers 8
--evidence-dir <dir>`); gate result below.

Fix gate from a clean worktree (`cfafb7d9b` plus the fix): policies, docs and test ownership exit
0; `run_tests.sh` exit 0: 169 / 4,060 / 5 skips / 1,065 subtests / 20 legacy.

Run 2 evidence: `$E/run2/` (incomplete: simulator crash at case 23;
`python3 adjudicate.py run2/live run2/bundle 23`). Run 3 evidence: `$E/live/`, `$E/bundle/` (cases 1-22; `python3 adjudicate.py live bundle 23`) and `$E/live_tail/`, `$E/bundle_tail/` (cases 23-36, `scenarios_tail/`). Summary: `$E/README.md`. SC qualification: `$E/sc_guard/` (`run_arm.py`, oracle,
arms A/B). The fix commit changes the Agent (SC), so rebuild and redeploy it before run 3. Restart
the scene with the same `run_scenario.sh` command, then `docker restart soridormi-runtime-mcp` and
wait for "Scenario clock reset" in the runner log.

Run 2 fix gate from a clean worktree (`38a5d2160` plus the fix): policies, docs and test ownership
exit 0; `run_tests.sh` exit 0: 169 / 4,063 / 5 skips / 1,065 subtests / 20 legacy.

Stage B (Deep Planner removal) is in progress on branch `deep-removal` (worktree under the session
scratchpad; plan in `.chromie/acceptance/deep-removal-20261011/PLAN.md`). Its WIP commit is local only.

## Previous delivery — Need-first Planner (stage A), 2026-10-10

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `08c93650d`.
Evidence: `.chromie/acceptance/need-first-20261010/` (README.md). The expected resume revision
is the latest commit containing this file.

Changed:
- Code: `agent/app/{planner_model_contract,planner_schema,planner_context,planner_prompt,
  fast_planner}.py`, `benchmarks/datasets/fast_planner_daily_life/qualification.py`
  (`declared_ability_needs`).
- Tests: the Fast, intent and replay suites.
- Corpora: `benchmarks/integration/{workflow_scenarios,scenarios}` at freeze 22.
- Docs: `docs/{PROJECT_CHARTER,API_REFERENCE,GOAL_DRIVEN_COGNITIVE_ARCHITECTURE,STATUS}.md`,
  this file and the checkpoint.

Verification:

```bash
python scripts/run_workflow_replay.py --workers 4 --evidence-dir <dir>       # 6000/6000, zero model calls
# canonical gate from a clean worktree (the main checkout contains a peer's .claude/worktrees/):
git worktree add --detach <tmp>/gate HEAD && (cd <tmp>/gate && python scripts/check_repository_policies.py && python scripts/check_docs.py && python scripts/check_test_ownership.py && ./scripts/run_tests.sh)
```

Freeze 22 was rebuilt with `.chromie/acceptance/need-first-20261010/{capture22,freeze22,
migrate_small_corpus22}.py` (backups `previous-*`). Not deployed; live is pending stage B.
Gate observed from a clean worktree (HEAD plus this patch): policies, docs and test ownership
exit 0. `run_tests.sh` exit 0: 169 / 4,043 / 5 skips / 1,065 subtests / 20 legacy. Stage B is
paused: on 2026-10-10 the owner raised value/legality deliberation (the original Deep intent);
see the checkpoint for the decisions.

Deployed on this host after commit: `chromie-agent:stageA-78fb2b871` (rollback
`chromie-agent:pre-need-first-20261010`), runtime identity `a4d72438…`
(`.chromie/acceptance/value-judgment-20261010/runtime-identity.json`), and `chromie-llm`
`03ad9e33`. The Soridormi water scene must be started after a reboot.

Value-judgment evidence: `.chromie/acceptance/value-judgment-20261010/`.
- Draft: `VALUE_JUDGMENT_DRAFT.md`, treated as approved on 2026-10-11.
- Prompts: `value_judgment.py`, `_v2.py`, `_v3.py`; merged-into-Planner variant
  `build_merged.py`.
- Cohorts: `scenarios/` (20) and `scenarios_heldout/` (16); labels in `oracle.json`.
- Live bundles: `chromie_debug_bundle_20261010_175400` and `chromie_debug_bundle_20261010_183134`.
- Scoring: `python3 score_all.py` from that directory.

## Previous delivery — SGLang image: XGrammar int32 rule IDs, 2026-10-10

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `03f4e7e20`.
The expected resume revision is the latest commit containing this file.

Changed: `llm/sglang/Dockerfile` (#652 backport and regression test),
`docs/CONFIGURATION.md`, `docs/STATUS.md`, this file and the checkpoint.

The canonical gate was run from a clean worktree (HEAD plus this patch; the main checkout
contains a peer's `.claude/worktrees/`, which breaks `check_docs`). Policies, docs and test
ownership exit 0. `run_tests.sh` exit 0: 169 / 4,040 / 5 skips / 1,065 subtests / 20 legacy.

Image and deployment (already done on this host):

```bash
docker build -t chromie-sglang:xgr652-20261010 llm/sglang          # all image-build tests pass
docker tag chromie-sglang:gemma4-fp8 chromie-sglang:pre-xgr652-20261010   # rollback (b419ac92)
docker tag chromie-sglang:xgr652-20261010 chromie-sglang:gemma4-fp8
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-llm
```

The Agent runs `chromie-agent:main-03f4e7e20`, clean source with a verified digest
(rollback `chromie-agent:pre-skill-lookup-20261010`). Runtime identity `c0b5a157…` is in
`.chromie/acceptance/skill-lookup-20261010/runtime-identity.json`. The host rebooted on
2026-10-10, so start Soridormi first: `(cd ../soridormi && ./scripts/run_scenario.sh
--scenario configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer)`.

Evidence `.chromie/acceptance/skill-lookup-20261010/`:
- `make_cohort.py` and `oracle.json`: the cohort, declared before inference.
- `wrap_harness.py`: live run with Fast DTO recording, writing to `fast_requests/`.
- `live/`, `bundle/`: live results and the debug bundle.
- `regen.py`, `regen_host.py`: production request regeneration and Host check inside the
  Agent container (22/22 byte-identical to live).
- `run_arm.py`, `adjudicate.py`: arms `A_live_requests`, `B_preloaded`, `D_all_loaded`
  (old image) and `*_xgr652` (new image).

The new Deep baseline replay is `../workdag-deep-20261009/deep_baseline_xgr652`. XGrammar
probes (`probe.py`, `hypo.py`, `count_compiled.py`, `synthetic.py`) and the test Dockerfiles
were in the session scratch area; the README records their results.

```bash
cd .chromie/acceptance/skill-lookup-20261010
python run_arm.py <arm> <requests.json>          # restarts chromie-llm first; keep the Agent idle
python adjudicate.py A_xgr652 B_xgr652 D_xgr652
python3 build_needfirst.py                        # candidate requests from frozen_first_requests.json
python run_arm.py N1_needfirst needfirst_requests.json && python3 adjudicate_needfirst.py
python run_arm.py N2_second second_requests.json  # second calls (built with regen2.py / jobs_second.json)
```

Live captures now need `runtime-identity-xgr652.json` (identity `e7f966c3…`). The older
identity is bound to the replaced SGLang image, and the harness refuses it.

## Previous delivery — Deep Planner Work is WorkDAG dependency topology, 2026-10-09

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `ede7acc15`.
Evidence: `.chromie/acceptance/workdag-deep-20261009/`. The expected resume revision is the
latest commit containing this file.

Changed:
- Code: `agent/app/{planner_model_contract,planner_validation,planner_schema,planner_prompt,
  deep_planner,fast_planner}.py`.
- Corpora: `benchmarks/integration/workflow_scenarios/{frozen.tar.xz,manifest.json}` and
  `benchmarks/integration/scenarios/*`, both at freeze 21. Archive sha256 `92efe58e…`.
- Tests: the Deep, Fast and planner contract suites.
- Docs: `docs/{work_dag,EXECUTION_LANES_AND_COORDINATION,COGNITIVE_RUNTIME_ROLLOUT,
  HUMAN_LIKE_INTERACTION_CONTRACT,COGNITIVE_TURN_LOOP,STATUS}.md`, this file and the
  checkpoint.

Verification already run (results in the checkpoint):

```bash
# The main checkout contains .claude/worktrees/ (peer session), so its check_docs fails; gate from a clean worktree:
git worktree add --detach <tmp>/gate-wt HEAD && (cd <tmp>/gate-wt && python scripts/check_repository_policies.py && python scripts/check_docs.py && python scripts/check_test_ownership.py && ./scripts/run_tests.sh)
(cd <tmp>/gate-wt && python scripts/run_workflow_replay.py --workers 4 --evidence-dir <dir>)   # 6000/6000
```

Corpus migration scripts (already applied, kept for audit): `migrate_responses.py`,
`migrate_conflicting_resource.py`, `capture_all_workflow_requests.py`, `freeze21.py`,
`migrate_small_corpus.py`. The previous corpus is in `prev-corpus/` and `previous-*`.

Pending (the Deep contrast was running at commit time; live not run):

```bash
cd /home/chromie/github/chromie
E=.chromie/acceptance/workdag-deep-20261009
# arms: each restarts chromie-llm first; keep chromie-agent idle and check ListAgents peers
for arm in baseline candidate candidate_repeat; do python $E/deep_contrast.py $arm; done   # skip arms already present
python $E/deep_adjudicate.py          # writes $E/deep_adjudication.json
docker tag chromie-agent:latest chromie-agent:pre-workdag-deep-20261009
docker build -f .chromie/acceptance/provider-source-branches-20261009/AgentDockerfile -t chromie-agent:workdag-deep-20261009 .
docker tag chromie-agent:workdag-deep-20261009 chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
docker restart chromie-llm
python scripts/general_ability_acceptance.py --mode live-text --goal-driven-runtime apply --execute --keep-going \
  --runtime-identity <identity> --evidence-dir $E/live --only-case <each case in the checkpoint's Next list>
./scripts/collect_debug_bundle.sh
```

The water scene needs `(cd ../soridormi && ./scripts/run_scenario.sh --scenario
configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer)`.
It was running at commit time.

## Previous delivery — Fast Work is WorkDAG dependency topology, 2026-10-09

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `690bee160`.
Evidence: `.chromie/acceptance/provider-source-branches-20261009/` (README.md).

Changed:
- Code: `shared/chromie_contracts/plan.py`, `agent/app/{planner_schema,planner_fast_validation,
  planner_validation,planner_prompt,fast_planner}.py`, `orchestrator/runtime/{cognitive_runtime,
  capability_runtime,interaction_coordinator}.py`, `scripts/behavior_scenarios.py`.
- Tests: the Fast, runtime and coordinator suites.
- Docs: `docs/PROJECT_CHARTER.md`, `AGENTS.md`, `docs/work_dag.md`,
  `docs/EXECUTION_LANES_AND_COORDINATION.md`, `docs/COGNITIVE_RUNTIME_ROLLOUT.md`,
  `docs/STATUS.md`, this file and the checkpoint.

Verification:

```bash
python scripts/run_workflow_replay.py --workers 4 --evidence-dir <dir>       # 6000/6000
./scripts/run_tests.sh   # run from a worktree without .claude/worktrees/ inside it; exit 0
cd .chromie/acceptance/provider-source-branches-20261009
./run_fresh_arms3.sh candidate_rev7_fresh candidate_rev7_fresh_repeat     # 37/37 reproducible
(cd deps-focus && python focus.py baseline && python focus.py p1)        # rewording rejected
```

Agent and live run (rollback `chromie-agent:pre-workdag-deps-20261009` = rev6):

```bash
docker build -f .chromie/acceptance/provider-source-branches-20261009/AgentDockerfile -t chromie-agent:workdag-deps-20261009 .
docker tag chromie-agent:workdag-deps-20261009 chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty --verify-agent-source chromie-agent   # 0b7cf09f…
docker restart chromie-llm   # fresh lifetime before every arm and the live run
```

The live cohort is the 4 water cases plus `look_while_blinking_twice`,
`user_probe_walk_while_singing`, `qualification_workdag_walk_blink_once`,
`compound_walk_nod_turn`, `walk_then_turn_right`, `multi_goal_look_then_blink`,
`nod_then_shake_head` and `multi_goal_walk_then_blink`. Results are in `live-rev7/`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261009_190505.tar.gz`.

## Previous delivery — Perception can ground a provider-owned resource source, 2026-10-09

Checkout `/home/chromie/github/chromie`, branch `main`, base `origin/main` `08f018296`.
Evidence: `.chromie/acceptance/provider-source-branches-20261009/` (README.md lists every arm).

Changed files: `shared/chromie_contracts/plan.py`, `agent/app/{planner_context,planner_schema,
planner_fast_validation,planner_prompt,fast_planner}.py`, `orchestrator/runtime/cognitive_runtime.py`,
`tests/test_intent_only_handoff.py`, `docs/RESOURCE_ACQUISITION_AND_DELIVERY.md`,
`docs/HUMAN_LIKE_INTERACTION_CONTRACT.md`, `docs/STATUS.md`, this file and the checkpoint.

Frozen native contrast. Greedy outputs depend on SGLang lifetime history: restart before
each arm and send no other traffic.

```bash
cd .chromie/acceptance/provider-source-branches-20261009
python contrast2.py freeze                                  # 37 cases; manifest2.json sha256 4d99c3fb…
./run_fresh_arms.sh candidate_rev6_fresh candidate_rev6_fresh_repeat   # 37/37 reproducible
python adjudicate2.py candidate_rev6_fresh baseline        # c2_baseline = fresh lifetime
```

Agent and live run:

```bash
docker tag chromie-agent:latest chromie-agent:pre-situation-source-20261009   # rollback
docker build -f .chromie/acceptance/provider-source-branches-20261009/AgentDockerfile -t chromie-agent:situation-source-rev6-20261009 .
docker tag chromie-agent:situation-source-rev6-20261009 chromie-agent:latest
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty --verify-agent-source chromie-agent   # 892bb7e1…
(cd ../soridormi && ./scripts/run_scenario.sh --scenario configs/simulation_scenarios/thirst_water_delivery.json --profile open_duck_forward --viewer)
docker restart chromie-llm
python scripts/general_ability_acceptance.py --mode live-text --goal-driven-runtime apply --execute --keep-going \
  --runtime-identity <identity> --evidence-dir <dir> --only-case thirsty_then_water_delivery \
  --only-case direct_water_delivery --only-case accepted_water_offer_executes --only-case user_probe_fetch_milk_fifty_meters
```

Notes:
- The water scene needs `--viewer`, because compose pins `MUJOCO_GL=glfw`.
- If the simulator died, stop a stale `soridormi-runtime-mcp` before relaunching.
- Live: `live-water-rev6/`; bundle `/home/chromie/Downloads/chromie_debug_bundle_20261009_144736.tar.gz`.
- SGLang image `b419ac92…` comes from the parallel memory session (rollback
  `chromie-sglang:pre-wrapper-cache-bound-20261009`).

## Previous delivery — Text harness runs live ambient perception, 2026-10-08

Base: local commit `89de55fb5`. Owner-requested defect: the text acceptance Host never
started the ambient scene poll (only `VoiceAssistant.run()` did), so every live text turn
planned with `situation: {}`. Repair: `VoiceAssistant.start_soridormi_ambient_perception()`
is the one idempotent starter used by `run()`. `scripts/interaction_text_mujoco_check.py`
primes one read after a passing preflight, starts the same poll and records
`ambient_perception.json`/summary `ambient_perception`. Regressions in
`tests/test_soridormi_scene_perception.py` are red→green; the canonical gate passes
(169/4,013/5/1,065/20, `.chromie/acceptance/ambient-perception-text-20261008/run-tests.log`).
Live proof is NOT done. The default Soridormi scene has zero objects. The
`thirst_water_delivery` scene fails to start: its scenario runner opens GLFW on `:0`
even with `--no-viewer` and with `MUJOCO_GL=egl`. That is a Soridormi environment defect,
not edited here. The simulator and MCP runtime were stopped by `run_scenario.sh` and must be
restarted before any live run.

Next (owner-requested): the water source is marked `known` without evidence. Replace the
decoder-ignored `allOf if/then` in `agent/app/planner_schema.py` with two `oneOf` branches:
unresolved forbids the source span, known requires it. Then run strict replay; a freeze
recapture is likely, using `.chromie/acceptance/water-context-repair-20261007/` tooling.

## Previous delivery — Information-query free text must cite its source span, 2026-10-08

Checkout `/home/chromie/github/chromie`, branch `main`. Base: local commit `20e394a3c`
(after-Work speech, not pushed) on `origin/main` `23d924ee2`.

Changed files:
- `agent/app/planner_schema.py` and `agent/app/planner_fast_validation.py`: decoder span
  requirement and Host same-script check.
- Tests: `tests/test_intent_only_handoff.py`, `tests/test_weather_goal_scope_contract.py`.
- `docs/STATUS.md`, this file and the checkpoint.

Commands and results:

```bash
cd .chromie/acceptance/string-input-provenance-20261008 && python contrast.py <scratch-with-extracted-bundles>   # freeze 20
ARM=baseline python contrast.py; ARM=candidate python contrast.py; ARM=baseline REPEAT=-repeat python contrast.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir .chromie/acceptance/string-input-provenance-20261008/strict-replay-final   # 6000/6000
./scripts/run_tests.sh   # final run-tests-final.log: exit 0, 169 / 4011 / 5 skipped / 1065 subtests / 20 legacy
```

The first gate (`run-tests.log`, broad rule) failed 9 tests; this led to the narrowed rule.

Agent redeploy:

```bash
docker tag chromie-agent:latest chromie-agent:pre-string-provenance-20261008   # rollback
docker build -f .chromie/acceptance/string-input-provenance-20261008/AgentDockerfile -t chromie-agent:latest .
docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml up -d --no-build --force-recreate --no-deps chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent   # matches, 8b820086...
```

Live: `live-flagged/summary.json` (13 cases, `--execute --keep-going`, identity
`runtime-identity.json`); bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_174448.tar.gz`.

## Previous delivery — SC answers ordered after body Work are spoken again, 2026-10-08

Checkout `/home/chromie/github/chromie`, branch `main`, base `23d924ee2` (= `origin/main`).

Changed files:
- `orchestrator/runtime/interaction_coordinator.py`: after-Work exemption accepts
  `source=social_cognition`.
- `tests/test_interaction_coordinator.py`: SC-source regression.
- `docs/STATUS.md`, this file and the checkpoint.

Commands and results:

```bash
python -m pytest -q tests/test_interaction_coordinator.py   # 50 passed; original source fails the new test
python scripts/general_ability_acceptance.py --mode level-a --ability-class multi_goal_daily_life --no-write   # 10/10
python scripts/run_workflow_replay.py --workers 8 --evidence-dir .chromie/acceptance/after-work-speech-20261008/strict-replay   # 6000/6000, 0 model calls
./scripts/run_tests.sh   # exit 0: 169 benchmark, 4007 main, 5 skipped, 1065 subtests, 20 legacy
```

Live: identity `.chromie/acceptance/after-work-speech-20261008/runtime-identity.json`
(diagnostic, dirty). One invocation of `--ability-class multi_goal_daily_life --execute
--keep-going` → `live-class/summary.json`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_162840.tar.gz`.

Resume (next: Planner provenance/readiness repair). Start from the retained failing
packets, not from prompt edits:

```bash
cd /home/chromie/github/chromie
git fetch origin && git status --short && git log --oneline -3
rg -n 'exact owned Goal source quote|cannot invent an unbound Capability input' agent/app orchestrator
```

Retained failures:
- `.chromie/acceptance/evidence-bound-claims-20261008/live-flagged/` — weather location,
  clock vs weather.
- `.chromie/acceptance/sc-act-identity-20261008/live-focused/` — water `acquire_and_deliver_resource`.
- `.chromie/acceptance/ga-revision-containment-20261008/live-focused/` — readiness quote.

## Previous delivery — GA-triggered Planner revision no longer erases a valid first plan, 2026-10-08

Checkout `/home/chromie/github/chromie`, branch `main`. Base: local commit `05af832a4`
(SC act identity, not yet pushed) on fetched `origin/main` `601b73f09`.

Changed files:
- `orchestrator/runtime/cognitive_runtime.py`: plan settlement in `_resolve`, flag
  `ga_revision_failure_contained`, diagnostics for either failure, `dataclasses.replace` import.
- `tests/test_cognitive_runtime_pr7.py`: four `IndependentPlanningTests` regressions.
- `tests/test_turn_local_continuity.py`: the late-failure test now fails both plans.
- `docs/COGNITIVE_TURN_LOOP.md`: failure rule.
- `docs/STATUS.md`, this file and the checkpoint.

Commands and results:

```bash
python -m pytest -q tests/test_cognitive_runtime_pr7.py tests/test_turn_local_continuity.py   # 105 passed; original source fails the 3 new containment/rescue tests
python scripts/run_workflow_replay.py --workers 8 --evidence-dir .chromie/acceptance/ga-revision-containment-20261008/strict-replay-final2   # 6000/6000, 0 model calls
./scripts/run_tests.sh   # final: exit 0, 169 benchmark, 4006 main, 5 skipped, 1065 subtests, 20 legacy (run-tests-final2.log)
```

The first gate attempt (`run-tests.log`) failed 2 tests by deadlock: settlement awaited a
GA plan that waits for goal-state SC. It was fixed by moving settlement after that launch.

Live: identity `runtime-identity.json` (diagnostic, dirty). One invocation over
`ambiguous_object_bring_that`, `accepted_water_offer_executes` and
`thirsty_then_water_delivery` → `live-focused/summary.json`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_160823.tar.gz`. GA-revision path:
turn `90114e51` (both plans rejected; honest failure).

Resume (next: deliver final-phase SC speech after body Work):

```bash
cd /home/chromie/github/chromie
git fetch origin && git status --short && git log --oneline -3
rg -n 'communication_after_step_ids|delivery_phase == "final"|phase == "final"' orchestrator/runtime/cognitive_runtime.py
```

Evidence for that defect is in `.chromie/acceptance/sc-act-identity-20261008/live-focused/`
(`multi_goal_blink_and_joke`, `nod_and_say_hello`) and `ab-original-code/`.

## Previous delivery — SC act identity no longer copies Planner Work IDs, 2026-10-08

Checkout `/home/chromie/github/chromie`, branch `main`, pre-delivery base
`601b73f09dfbcb0175233219f96d7b6ee11f8f89` (matched fetched `origin/main`).

Changed files:
- `orchestrator/runtime/cognitive_runtime.py`: Need `facts` exclude `activity_id`.
- `tests/test_planner_communication_pr6.py`: retained-episode regression.
- `docs/STATUS.md`, this file and the checkpoint.

Commands and results:

```bash
python -m pytest -q tests/test_planner_communication_pr6.py   # 7 passed; original source fails the new test
python scripts/run_workflow_replay.py --workers 8 --evidence-dir .chromie/acceptance/sc-act-identity-20261008/strict-replay   # 6000/6000, 0 model calls
./scripts/run_tests.sh   # exit 0: 169 benchmark, 4003 main, 5 skipped, 1063 subtests, 20 legacy
cd .chromie/acceptance/sc-act-identity-20261008 && python contrast.py <scratch-with-extracted-bundles>   # freeze 16 cases
ARM=baseline python contrast.py; ARM=candidate python contrast.py; ARM=baseline REPEAT=-repeat python contrast.py
```

The contrast replays each frozen request on `http://127.0.0.1:30000/v1/chat/completions`
(`chromie-gemma4-12b`, temperature 0). Its results are in `baseline/`, `candidate/`,
`baseline-repeat/` and `contrast.log`.

Live: identity `runtime-identity.json` (diagnostic, dirty). One invocation of
`--mode live-text --goal-driven-runtime apply --execute --keep-going` over 11 cases →
`live-focused/summary.json`. The A/B on original source (only `cognitive_runtime.py`
stashed; identity `runtime-identity-ab.json`) → `ab-original-code/`. Bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_153201.tar.gz`.

The Soridormi simulator (`run_sim_server.sh --profile open_duck_forward --no-viewer`) and
`soridormi-runtime-mcp` were left running for the next live item.

Resume (next: GA-triggered Planner as a non-destructive revision):

```bash
cd /home/chromie/github/chromie
git fetch origin && git status --short
rg -n 'umi_planning_superseded|ga_model_requested_reentry|cancel_uncommitted_fast_work' orchestrator/runtime/cognitive_runtime.py
python -m pytest -q tests/test_cognitive_runtime_pr7.py -k IndependentPlanning
```

## Previous delivery — Evidence-bound claim oracle, 2026-10-08

Checkout `/home/chromie/github/chromie`, branch `main`, pre-delivery base
`4208f001a841abb86d852398d088f6da82a0c62f` (matched fetched `origin/main`). The delivery
commit contains this file and the [checkpoint](DEVELOPMENT_CHECKPOINT.md).

Changed files:
- `scripts/general_ability_acceptance.py`: `require_evidence_bound_claims` field,
  `_unsupported_evidence_claims`, metric, hard-gate error, score cap, earliest boundary
  `social_cognition_claim_provenance`, and integrity stop `provenance:unsupported_evidence_claim`.
- 13 scenario JSON turns gain the declaration (date, time, eleven weather turns); the
  mixed `debug_bundle_beijing_tomorrow_rain` is deliberately excluded.
- Regressions in `tests/test_general_ability_acceptance.py`.
- Docs: `scenarios/README.md`, `docs/ACCEPTANCE.md`, `docs/STATUS.md`.

Commands run and results:

```bash
python -m pytest -q tests/test_general_ability_acceptance.py -k "evidence_bound or integrity_failure or context_grounded or mixed_social"  # 40 passed; original harness: 6 new regressions fail
./scripts/run_tests.sh                                   # exit 0: 169 benchmark, 4002 main, 5 skipped, 1063 subtests, 20 legacy
python scripts/general_ability_acceptance.py --mode check   # 15 classes, 45 Level A, 79 live
python scripts/general_ability_acceptance.py --mode level-a --ability-class evidence_coverage_and_claim_discipline --no-write  # 6/6
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent  # matches=true, 2b4f22989ef9...
```

Live proof needed the Soridormi simulator, which was not running at session start; it was
started per runbook §5.2 (`../soridormi/scripts/run_sim_server.sh --backend mujoco --profile
open_duck_forward --no-viewer` plus `docker compose -f compose.sim.yaml --profile mcp-runtime
up -d --no-build mcp-runtime`). The identity was captured with `--allow-dirty` (diagnostic,
dirty source) at `.chromie/acceptance/evidence-bound-claims-20261008/runtime-identity.json`.
The cohort was one invocation of `--mode live-text --goal-driven-runtime apply --execute
--keep-going` over the 13 declared cases. Summary:
`.chromie/acceptance/evidence-bound-claims-20261008/live-flagged/summary.json`; log
`live-flagged.log`; bundle `/home/chromie/Downloads/chromie_debug_bundle_20261008_134254.tar.gz`.

The run produced 4/13 automatic passes and 0 unsupported-claim hits. Failure clusters
are in the checkpoint; none is repaired by this delivery.
Original episode evidence: `.chromie/acceptance/thirst-offer-20261007/live-baseline/12-must_pass-evidence_coverage_and_claim_discipline-current_date_and_weekday/`.

Resume (item 2, SC act identity):

```bash
cd /home/chromie/github/chromie
git fetch origin && git status --short
rg -n 'facts=activity.model_dump' orchestrator/runtime/cognitive_runtime.py
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

## Previous isolation — decoder profile and late SC failure, 2026-10-07

Checkout `main`, pre-delivery base `ee74ee8f9cc76982e5a06170e50f2601d06f5788`;
fetched `origin/main` matches. The owner authorized commit and push of this
in-progress patch; the delivery revision is the commit containing this checkpoint
and handoff. This records local repairs and open qualification, not a complete fix.
Fixed deployed candidate `chromie-gemma4-12b`; no model promotion or scheduler change.

Implemented scope: UMI accepted-effect prompt/context projection (all facts retained),
explicit default array `items={}` in the shared decoder projection, preservation of the
primary Planner title through readiness/lookup wrappers, and typed Social Cognition
request/validation failures at the existing Host containment boundary. Canonical
semantic authority, DTO cardinality, confirmation and fail-closed Work remain intact.
The proposed relocation of native `oneOf`/`anyOf` behind `allOf` was withdrawn:
actual XGrammar admitted forbidden silence/covered. Current projection keeps those
alternatives intact; exact grammar proof rejects covered silence and accepts pending silence.

Observed failures: the original `sure` is now physical water intent, but two same-scope
Planner calls race and the canonical call previously failed HTTP 400 before inference.
The readiness wrapper had dropped the role title, bypassing array/shape/format settings.
An exact native replay with the retained title now returns HTTP 200, stop, complete JSON
in 22.959s; raw Schema and semantics still fail (invented location gaps and deferral).
All provider-owned source-resolution metadata was present in that request; missing
capability projection is not established. Planner correctness remains open.

The next bound aggregate stopped at compound UMI r4 relation-only/overlapping provenance
(1/79 attempted, 78 unrun; bundle `chromie_debug_bundle_20261007_171342.tar.gz`).
Focused water then stopped at its greeting: SC delivered the greeting, later emitted
forbidden silence/covered, Agent returned 422, and Host appended a generic apology.
Its bundle is `chromie_debug_bundle_20261007_172100.tar.gz`; water turns were unrun.
The Host repair classifies thrown RuntimeError/ValueError as `social_cognition` failure:
existing containment preserves a completed speech-only response while retaining failure
telemetry; body Work still fails and cannot dispatch. Four valid red regressions pass green;
combined focused suites pass 42 tests and 85 subtests. No corrected live proof yet.

Qualification: accepted-effect UMI 14 native contrasts pass that narrow scope, with
Chinese open-help language still unqualified. Frozen 25 compound/need contrasts:
baseline has six Schema/Host failures; the first candidate is mechanically valid but
loses relations/grouping. A later focused prompt improves ordering but does not qualify
independent effect/body-family coverage. Neither candidate is promoted. Field-order
experiment suffered global host OOM killing the provider scheduler at 17:35:27 +08
(112449912 kB anonymous RSS); causative compiler growth is unproven. It is an incomplete
service-integrity run, not five semantic failures. One bundle
`chromie_debug_bundle_20261007_173617.tar.gz`; provider auto-recovered with changed runtime
identity. Further syntax probes use isolated bounded containers, no GPU inference.

Historical freeze 19 strict replay passed 6000/6000, zero candidate calls; its full gate
passed 169 benchmark, 3985 main, five skips, 1063 subtests and 20 legacy tests, but covers
the withdrawn decoder projection. Final-source request capture passes 6000/6000 and five
prototypes; freeze 20 retains every non-request field and strict replay and the first full canonical gate passed; latest Host repair gates are recorded below. Agent was rebuilt and source-verified before the latest diagnostic live runs; final Host live proof remains pending.
No current voice, physical microphone/speaker/robot, release or target qualification.

Evidence root: `/home/chromie/github/chromie/.chromie/acceptance/water-context-repair-20261007/`.
Bundles above are under `/home/chromie/Downloads/`. Native receipts are in
`mixed-decoder-branches/`; red/green containment logs and request-only capture are retained.
Open blockers: UMI obsolete sibling-ref instructions versus natural WHAT, Planner semantic
completeness/provenance, same-scope invocation race (explicit owner scheduling approval
pending), and provider source-binding truth (provider not invoked in blocked episodes).

### Follow-up isolation — silent SC state erases a completed response

Corrected Agent source digest `2b4f22989ef91b38b4ec210d85c83ab77f8dbd40af999ac0b7062d897791d7c8`
matched the checkout before the next bound aggregate. That aggregate's first compound
case executed walk10s/vx0.2, default-count2 nod, then left turn in simulation and ended
safe_idle. It still fails: UMI omitted explicit ordering in outcomes, and a7-char
acknowledgement's first PCM took4883.5ms against3500ms start deadline. One bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261007_181405.tar.gz`.
1/79 attempted,78unrun; reviewed fail, not qualification. Provider performance cause
beyond this observed deadline miss remains unproven.

Same-runtime focused water attempted greeting and thirst, not accepted-water turn.
Greeting is mechanically accepted but SC authors identical words under `greet_and_status`
and later `resp_001`, causing two real synthetic playback occurrences. Thirst UMI is
one turn-scoped speech Responsibility; SC delivered `offer_water_help`. GA then requests
goal-state SC, which correctly chooses silence. Host replaces its sole social-task handle
with that silence. The redundant canonical Planner's score/status DTO fails; completed
speech containment now sees only silence, requests a failure update and leaves the
already addressed interaction Goal open/planning. One bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261007_181616.tar.gz`.
Every attempted turn reviewed fail; turn03unrun. No water provider invocation.

Current Host repair retains the initial task handle and joins original/current state tasks
without replacing delivered speech by silence. For newly materialized speech-only Goals,
it invokes the existing source-ref/Goal-ID completion join from SC respond + actual delivery.
Two regression cases prove retained speech and actual Goal closure versus non-speech
receipt: body Work remains error/open, no dispatch. Valid red pointer failure and separate
red lingering-Goal assertion are retained; green combined suites44 tests/85subtests,
adjacent8 tests pass. No scheduling, semantic re-authoring or text deduplication introduced.
The corrected Host source still needs renewed live evidence.

Freeze20: changed2700Fast/1900Deep requests, four prototype Planner requests; all6000+5
non-request records identical, zero candidate calls. Archive SHA256
`6f4c7e7986ead2a6b3bad5b0c2b00e1ecf7398fa69e55f9b69c992319a6ad052`.
Strict6000/6000 and first full gate20 pass:169 benchmark,3991 main,5skips,1063subtests,
20legacy. Those gates precede silent-state retention/closure. Pointer-only strict6000 also
passed. Its full gate was intentionally terminated before completion for the reproduced
Goal-closure repair; it is not a pass. Final-source canonical rerun passed:169 benchmark,3993 main,5 skips,1063 subtests,20 legacy. Final strict replay passed6000/6000 with source unchanged and zero model calls; Level A passed30 distinct cases across six ability classes. Policy, docs, test ownership and diff checks passed. Receipts: `run-tests-sc-final.log`, `strict-sc-final/`, `level-a-sc-final/`. These are local proofs, not live qualification.

Another private compound prompt candidate completed all25 fixed-model primary transactions:
source-language and retained order improve, but four hard cases fail (politeness creates
an extra speech result; mixed body-family grouping; one missing joke plus overlapping
provenance). Candidate rejected, source prompt unchanged. Same-agent post-hoc ledgers are
retained, not independent evaluation or a Runtime repair. The duplicate greeting has a focused namespace contrast in `live-current-water/identity-namespace/`: changing only Planner Need fact `activity_id` to existing name `fast_activity_id` in all three prompt mirrors changed the primary SC output from duplicate `resp_001` to existing delivered act `greet_and_status`. Both native grammars accept either ID. This supports context ambiguity, but the wider SC corpus is unrun and no source projection fix is applied. Pending owner approval is still
required for narrow same-scope Planner consolidation; no scheduler change applied.

Owner scope correction: keep subsequent turns to one defect and one focused fix.
The owner subsequently authorized delivery of the current patch without expanding it.
Resume with one defect and one focused fix per turn. Next candidate is SC act-ID
namespace qualification; do not bundle it with Planner scheduling or compound UMI work.
Final Host live proof remains pending; source and evidence gaps above remain open.

Resume from `/home/chromie/github/chromie`; inspect the retained SC namespace
contrast first, freeze its complete contrast matrix before another native batch, and
keep Planner scheduling and compound UMI repair out of that turn. Local receipts
above already cover the delivered source; do not rerun them just to restate a pass.

```bash
cd /home/chromie/github/chromie
git status --short
rg -n 'activity_id|fast_activity_id|communication_needs' agent/app/social_cognition.py
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

For subsequent live proof, bind a fresh identity and a new evidence directory; do not
reuse `runtime-identity-current.json` or overwrite the retained `live-current-*` runs.
Private evidence and bundles are local artifacts, not distributed by this commit.
Run the frozen full cohort without source changes, stop on hard integrity failure,
collect one bundle and judge every attempted case. No scheduler change is approved.

## Current delivery — open-ended help, GA ownership and SC failure update, 2026-10-07

Checkout `/home/chromie/github/chromie`, branch `main`; fetched upstream base
`073abb4daad94c8bb419db6b05ba8f6310c4a0a6`. The delivery commit includes
this file and [checkpoint](DEVELOPMENT_CHECKPOINT.md). The current source was
built into the Agent service for a diagnostic text aggregate, but the service
became unavailable mid-cohort and its runtime identity changed. Treat that
aggregate as incomplete, not as a fixed-identity release proof.

Originating text SID `d7e6f1a3`: after greeting and a thirst/help turn, the
person asked Chromie to bring a bottle of water. UMI accepted one complete
delivery Responsibility `r1` at confidence 1.0. SC delivered a short receipt
acknowledgement. GA's `chromie-gemma4-12b` primary response contained two
identical `continue` rows attaching `r1` to thirst Goal
`goal_b39473f14c95a7346417`. The canonical GA Host validator rejected the
duplicate (`expected=['r1']`, `actual=['r1','r1']`) and no Goal/Work commit
occurred. Concurrent speculative Fast planning was cancelled. The terminal
failure need then reached SC, whose recorded speech was “I'm sorry, I had a
little trouble processing that request. Could you say it again?” Meaning had
already been accepted, so the repeat request was false. A direct baseline
replay of that same SC packet instead reused its earlier “Got it.” act to cover
the later failure need, another invalid result-accounting path. Microphone and
ASR were not invoked for this text episode. Original bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_110927.tar.gz`.

Repair at existing owners: `agent/app/clients/sglang_protocol.py` derives the
current Responsibility-ref count from the canonical GA schema and applies a
per-array row bound only in the SGLang wire schema. This makes the existing
one-owner-per-ref limit visible to the native decoder without changing GA's
canonical request or weakening Host validation. `agent/app/social_cognition.py`
prevents a prior acknowledgement act from covering a later terminal result
need, requires a newly grounded result update, and tells the primary SC model
that accepted meaning with no input need is no reason to ask for repetition.
The Host continues to fail closed if the decoder produces a cross-array
duplicate or another invalid mapping. No new model call or semantic authority
was added.

Private evidence is retained in `.chromie/acceptance/ga-duplicate-20261007/`
and `.chromie/acceptance/sc-internal-failure-20261007/`. The three exact GA
packets replayed through the bound native decoder covered the expected refs
with no Schema errors. The original duplicate is in the recorded live bundle;
the baseline replay did not reproduce that stochastic output. The five-call SC
episode replay passed Schema and Host validation on current source, ending in
“I'm sorry, I couldn't bring the water bottle to you because of a technical
issue.” This is a truthful result update, not a claim of physical delivery.
Direct model replay is same-model, not independent or deployed integration proof.

Focused tests: 68 selected GA/SC/workflow replay tests pass. The final restored
source passed `python scripts/check_repository_policies.py`,
`./scripts/run_tests.sh` and `python scripts/check_docs.py`; the full test script
exited 0 with 169 benchmark, 3,983 main, five skipped, 1,023 subtests and 20
legacy Agent tests. Test ownership, pinned Ruff/mypy, configuration and runtime
checks passed within the canonical gate. Four relevant Level A ability classes
passed 22/22 (human-like continuity 4, natural uncertainty 6, robust intent 8,
truthful embodied speech 6); the
strict frozen workflow replay passed 6,000/6,000. An earlier experimental
`run_tests.sh` invocation failed workflow request comparisons while prompt
experiments were active; those experiments were reverted before the final pass.

Diagnostic deployed text aggregate:
`.chromie/acceptance/thirst-offer-20261007/live-baseline/summary.json` and
`case_review.json` in that evidence root. All 79 cases were attempted in one
invocation: 13 automatic passes, 66 failures, 59 integrity failures, 79 semantic
reviews retained; `cohort_complete=false` and `qualification_complete=false`.
Agent port 8092 became unavailable during the run; the cause is unknown. Exactly
one post-cohort bundle was collected:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_121723.tar.gz`.

For `thirsty_then_water_delivery`, the first turn offered help, but after “Sure,
water is perfect!” UMI's primary output reduced the accepted request to speech
instead of a physical get/deliver Responsibility. The exact private packet is
`.chromie/acceptance/thirst-offer-20261007/umi-water-acceptance-raw.json`.
For `accepted_water_offer_executes`, UMI and GA carried the accepted “sure” to
Fast Planner, whose primary output gave a provider-resolved source with an
unsupported description and missing `argument_sources.source`; Schema/Host
rejected it before Capability dispatch. The exact packet is
`.chromie/acceptance/thirst-offer-20261007/planner-accepted-water-raw.json`.
These are distinct new earliest boundaries. Host containment was correct; the
user-visible apology was downstream. Contrast variants that repaired one example
caused unauthorized action or provenance errors elsewhere, so they were reverted.
The canonical semantic contract amendment needed for a broader repair has not
been approved or implemented.

Resume from stable services and a bound runtime identity. Diagnose the retained
UMI/Planner packets; obtain owner approval before changing the canonical semantic
contract; implement and prove a general boundary repair. Rerun focused scenarios,
their ability classes, local gates and the complete directory-discovered live
cohort before a revision-level claim. Then run narrow current-revision supervised
voice proof and continue default target-evidence closure. Physical microphone,
speaker and robot evidence is absent. The earlier UMI patch and frozen workflow
archive remain part of this delivery.

## Previous patch — open-ended help interpretation, 2026-10-07

Checkout `/home/chromie/github/chromie`, branch `main`, remote
`https://github.com/TimeTreker/chromie.git`. Fetched pre-edit base
`073abb4daad94c8bb419db6b05ba8f6310c4a0a6` matched `origin/main`.
At this earlier handoff, this patch was uncommitted and unpushed. The current
resume revision is the newest commit containing this file and
[checkpoint](DEVELOPMENT_CHECKPOINT.md).

Originating live text SID `a87066b5` admitted “I am a little thirsty, can you
help me?” on the original source. UMI call
`llmcall_user_meaning_interpreter_0e8b52fbe1db4a4b` used
`chromie-gemma4-12b` through `sglang.chat`, completed with `done_reason=stop`,
then failed Host source-span validation because `r1` cited `t1–t10` and `r2`
cited `t6–t10`. Core returned 503 and Host selected the non-semantic retry
notice; GA, Planner and SC were not invoked for that turn. The original private
bundle is `/home/chromie/Downloads/chromie_debug_bundle_20261007_093607.tar.gz`
and its extracted files are under `.chromie/debug/debug_bundle_20261007_093607/`.
Review and redact complete prompts before sharing either artifact.

The existing UMI system prompt now makes a reported need plus open-ended help
request one Responsibility, excluding an invented information request to choose
help. No schema/DTO/Host, model or profile change was made. The selected prompt
is SHA256 `7e68853c4cd682dc410aae4f56a66f8400af2a9be37f808ee45148ae6d620152`
after trimming the trailing newline. The frozen contrast evidence is under
`.chromie/acceptance/umi-help-split-20261007/`: `scenarios/`, `baseline/`,
`candidate2_focused/`, `candidate2/`. Baseline 6/8 and selected candidate 8/8
passed Schema/Host; both baseline failures were overlapping English/Chinese
open-ended help outputs. The exact English turn now retains one complete speech
Responsibility and Planner/GA requests. Chinese still produced an English
outcome, despite mechanical acceptance; this is not bilingual qualification.
Later prompt experiments were rejected and restored to the selected hash.

Five prototypes were request-only captured from actual production packets;
`prototype-capture/` retains them. All 6,000 workflow requests were captured
against the same unchanged source using saved reference responses;
`full-request-capture/summary.json` reports zero failures. Only UMI packets
changed. The final archive is freeze revision 17, SHA256
`b8bc872fe60854a59bd982744aeeb05cc5c114701fe2e0c6fc22f158184281c8`.
`recapture-final-summary.json` records 6,200 primary and 300 Deep request
captures, all non-request fields identical. Previously ignored stale freeze
files are preserved in `preexisting-frozen-extra-artifacts/` and
`preexisting-stale-frozen-corpus/`, not deleted.

Observed checks:

- `python -m benchmarks.regression restore-fixtures`: 6,050 verified, zero restored
  after recapture.
- `python scripts/run_workflow_replay.py --workers 8 --evidence-dir
  .chromie/acceptance/umi-help-split-20261007/strict-full`: 6,000/6,000 pass,
  zero candidate calls, fixed source; see `strict-full/summary.json`.
- `pytest -q tests/test_workflow_replay.py`: 104 pass; focused UMI: 44 pass,
  77 subtests; robust-intent Level A: 8/8.
- `./scripts/benchmark_check.sh`: 169 pass; `pytest -q tests`: 3,981 pass,
  five environment skips, 1,023 subtests; legacy Agent: 20 pass. Policy,
  ownership, pinned static, configuration, runtime and docs checks passed.
- `./scripts/run_tests.sh` itself did not finish successfully here: initial
  ignored freeze files blocked restore, a second invocation ended at exit 143,
  and a later standalone main run exposed 83 stale request packets before the
  recapture. The final component checks above passed, but the single-command
  gate remains unverified.

The current operator text console remains active and `chromie-agent:latest`
still serves the pre-patch image. Do not describe the direct SGLang model calls
as deployed Host, audible voice, simulator or physical evidence. Next, from an
uninterrupted shell, run `./scripts/run_tests.sh`; bind a freshly built current
Agent source identity and run the existing
`scenarios/general_ability/must_pass/robust_intent_understanding/thirsty_then_water_delivery.json`
two-turn scenario when the operator Host is free. Review SC speech, Goal state,
Planner Work and follow-up continuity, then retain one bundle after any aggregate
live cohort. Qualify the Chinese language/need-retention slice separately.

## Previous delivery — UMI/Planner and historical Memory, 2026-10-05

Checkout `/home/chromie/github/chromie`, branch `main`, remote
`https://github.com/TimeTreker/chromie.git`. Pre-delivery base
`0848b07d14886a0238ca71ceae3aa65fd0bcd103` matches fetched `origin/main` before
edits and after the native aggregate. Expected resume revision is the newest commit
containing both this file and [checkpoint](DEVELOPMENT_CHECKPOINT.md).
Owner authorization: fix non-model defects, commit and push; UMI must not author
bindings. Principles and module responsibilities are unchanged; earlier contradictory
Charter allowance was removed. UMI and Planner prompt changes enforce this approved
contract, not general semantic tuning. Model/profile and SC prompt are unchanged.

The current local gate passes. Current-revision voice proof and default target closure
remain open. This is a bounded contract/projection repair, not a release or overall
behavior qualification. Attention second-call and SC silence/provenance findings remain
open. Do not repair UMI activation/meaning through GA, Planner or Host.

## Implemented workflow and provenance

- UMI primary/Deep Schema, parser and Decision reject even empty `bindings` keys.
  Complete WHAT, current-turn spans, uncertainty and initial activation remain UMI.
  Core rejects nonempty bindings; shared internal empty defaults/read-only retained
  canonical bindings are not fresh UMI authorship.
- Planner extracts arguments and cites original speech or exact owning accepted
  outcome tokens. `source_responsibility_ref` is an argument provenance selector,
  not another semantic owner. Host binds the exact quote only to that GA Goal;
  unknown tokens, owners and sibling citations fail closed. Typed retained constraints
  cannot be overridden. Valid coordinates alone do not prove semantic conversion.
- Provider-resolved resource sources may retain cited reported search clues. Perception
  verifies current conditions; a user report is not an observed object. Historical
  Memory remains Planner context outside sight, with original creation/update times
  and source refs. The controlled projection test does not prove search execution,
  automatic persistence of robot actions or that yesterday's water still exists.
- Stale UMI references/template are reconciled. Strict6000 records and5 prototypes
  change only captured production request packets; original inputs, reference decisions,
  meaning, relationships, parameters, prior Goals, provider/fault outcomes, assertions
  and splits are unchanged. No permissive replay or candidate-fitted answers.

## Evidence actually retained

Root `/home/chromie/github/chromie/.chromie/acceptance/umi-no-bindings-20261005/`
is ignored private evidence and does not travel with Git. Preserve/copy it before
cross-machine resume; review private prompts/payloads before external transfer.

| Artifact | Observed result and ceiling |
| --- | --- |
| `frozen-manifest.json`, `scenarios/`, `boundary.before.json`, `boundary.final-current.json` | Frozen bilingual20, initial8/20 → final20/20 through actual Schema/Host, one primary reference per case, zero external inference. |
| `grammar-conditional-wire-packets.json`, `native-grammar.conditional-wire.log` | Exact production response-format codec and pinned native decoder20/20; isolated container/network-none/2GB, no inference. Cross-field source/citation condition is Host enforced, not claimed native decoder semantics. |
| `memory.before.log`, `focused.owner-final.log` | Original Memory regression fails on missing created_ms; final runtime/Memory84 tests pass. No live water search. |
| `focused.pre-live.log`, `final-fixture-check.log` |215 focused tests/78 subtests pass; final2 fixture/hash checks pass. |
| `umi-corpus.after.log`, `fast-corpus.after.log`, `level-a/`, `level-a.log` | UMI1496/Fast204 references mechanically valid; Level A19/19 across3 relevant classes. No native behavior claim. |
| `capture-full-summary.json`, `workflow-invariant-review.json`, `prototype-request-capture.json` |6000+5 request-only maintenance; every non-request field unchanged, zero candidate inference. Original archive/cache/prototypes retained privately. |
| `strict-full/summary.json`, `strict-full.log` |6000/6000 pass, fixed production source, zero candidate calls:1400 complete workflows,1800 expected states,2500 expected rejections,300 safe nonexecuting rejections. |
| `canonical.final.log` | Exit0:169 benchmark tests,3981 main tests/5 environment skips/1023 subtests,20 legacy Agent tests pass; policy/ownership/pinned Ruff+mypy/configuration/runtime/docs pass. Initial `canonical.log`19 failures were a missing Unit source_text and stale5 prototype requests; original failed log retained. |
| `runtime.before.json`, `runtime.after-baseline.json`, `live-baseline/`, `llm_calls.baseline.jsonl`, `live-adjudication.baseline.json` | Unchanged-source native79,22 automatic pass/57 fail; same-agent review6 pass/10 partial/61 fail/2 insufficient. Nine primary nonempty binding outputs admitted by stale contract. |
| `runtime.native.before.json`, `runtime.native.after.json`, `live-after/`, `llm_calls.after-window.jsonl`, `live-adjudication.after.json` | Changed-source native79,13 automatic pass/66 fail; review5 pass/7 partial/67 fail. All cases attempted/zero skipped; blocked followups mean cohort/qualification incomplete. Native86 UMI primary outputs have zero binding keys. Source and service identities fixed. No overall behavioral gain established. |

Exactly one bundle per aggregate:

- Baseline: `/home/chromie/Downloads/chromie_debug_bundle_20261005_183008.tar.gz`.
- Changed source: `/home/chromie/Downloads/chromie_debug_bundle_20261005_192414.tar.gz`.

Native milk SID71d2b376 retains ahead/about50meters but requests GA only; Planner/
provider absent. Native walk/right-turn SIDb26d7667 completes simulator actions but
Planner call `llmcall_agent_6e97211283764259` falsely cites three-second walk tokens
for turn duration2s. This automatic pass is a semantic provenance failure, not a
proof of correct argument grounding. Current-time Planner is invoked (SID2b093bbb)
but authors response-only Work; no clock acquisition. Raw errors do not establish
intrinsic model incapacity. No model tuning, semantic lexer or second-call repair added.

Freeze revision16 archive: `benchmarks/integration/workflow_scenarios/frozen.tar.xz`,
1,294,716 bytes, SHA256
`17003c9696a28553d6ca1b888ede28c2ba76c9de79ecc6829837f98f90d9bb58`.
Strict cohort manifest SHA256
`51d9e344eb593d2fb474435fb3685a4fdf32b22318386d0732ea961094fd96fa`.
Original archive/cache remain in `workflow-frozen.before.tar.xz`,
`workflow-cache.before/`, with5 originals in `prototypes.before/`.
Final document consolidation follows the frozen native run; production bytes remain
identical. Do not treat the final documentation tree as that pre-document full-tree identity.

## Runtime and probe incident

Native frozen full tree:4492 paths, SHA256
`cc5de677facde4bc441fa9d141ee477339038b3d847796e046cb0939e5b1b273`;
identity SHA256 `d13bb2ac5787364a605da161735281784be71df48549f4492180dccf468bd671`.

Selected Agent image `chromie-agent:umi-boundary-memory-source-20261005` /
`bc6577e4b8996a55c3ea9ae6d996f757c8584460cd66a8a227871d3d4b17e9c7`;
container `1d73c9d3f87348308ee1f9d986aab5cec6adf0212cf71566b3e65661cdea59d3`.
Source-only rebuild preserves the original124a02f6… dependency layers. Environment
changed keys=[]; healthy/restart0. Packaged/host digest
`8140dcc34fdade7d6291bcb92b9dc5bd29f8a464ff4d7d1c35fd26d7dada0b25`
matches before/after in `agent-source.native.before.log` and `.after.log`.
The full official Agent build completed but was not deployed because its transitive
dependency resolution was outside the fixed-source comparison.

LLM remains `chromie-sglang:qwen35-4b-awq`, image2330d155… and model/options
unchanged. An initial manual grammar probe inside the running LLM omitted production
Schema sharing/shape codec, triggered OOM and automatic container recovery (exit137,
2026-10-05T10:46:14Z). `llm-service-after-probe.log` retains failure/recovery.
No manual LLM rebuild/restart or profile change. Native run binds the recovered
service identity; final healthy/restart1/start time unchanged. Subsequent grammar
proof is isolated/network-none/2GB and uses exact production transport. Experimental
three-branch source Schema failed pinned compilation and was rejected; final canonical
conditional plus existing transport shape passes. Never repeat heavyweight probes
inside the serving LLM. `services.native.after.log` retains final service states.

ASR42d3df2e…, TTSa56b2486… remain unchanged. TTS started2026-10-04T07:57:44Z,
ASR2026-10-04T01:08:44Z, both healthy/restart0. No microphone, audible speaker,
camera, grasp or physical robot qualification. Simulator acquisition is mock evidence.
Soridormi HEAD `2af3034a91842ecb9964a45ce24e9bdc18fcde58` has unrelated dirty owner
work; do not stage/reset it. Existing simulator and keepalive remain running.
Private `compose-files.private.json` and `agent-proof.private.json` retain the exact
Agent source proof service chain; use generated runtime env, never edit `.env.runtime`.

## Resume from Git

Fetch latest source and preserve dirty work before integrating. The current archive
restores complete exact records through existing checks; preserve a changed ignored
cache before replacement, never regenerate expected answers. Run from repository root:

```bash
cd /home/chromie/github/chromie
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

Next evidence is narrow supervised current-revision voice proof, then default target
closure. New native diagnostic runs need a fresh identity/evidence directory and a
full directory-discovered cohort; do not reuse or overwrite this root. Bind one source
and runtime, judge every case, collect exactly one bundle after the aggregate, then
select a fix. Prior/native automatic scores cannot authorize model promotion.

## Earlier evidence retained, not current resume commands

| Root under `.chromie/acceptance/` | Retained purpose |
| --- | --- |
| `project-audit-20261004T011454Z/` | Initial design audit, dirty36-path backup, Attention two-call/SC silence probes. |
| `audit-repair-20261004T014950Z/` | Text admission chronology and Level A metadata repair, dirty55 backup. |
| `root-cause-audit-20261004T061558Z/` | Original blink omission, TTS OOM/encoder proof, native17/79; no intrinsic capacity proof. |
| `contract-fixture-repair-20261004T084054Z/` | Original UMI/GA bytes and reference/adapter/oracle reconciliation, dirty68 backup. |
| `ga-relationship-contract-20261004T111406Z/` | GA identity/relations and Planner media repair. |
| `planner-compound-contract-20261004T140758Z/` | Compound/count/source repairs and historical native cohorts; `delivery/` retains first staged snapshot failures, owned patch/path inventory and count test recovery. |
| `sc-language-policy-20261004T125029Z/` | Rejected language trials4/8,4/8,3/8; original SC bytes restored. |
| `non-model-delivery-20261005/` | Prior347 focused pass and historical83 replay failures. |
| `workflow-contract-audit-20261005/` |6000 strict replay repair, archive/cold restoration, all original inputs/assertions preserved. |
| `ga-history-fixture-audit-20261005/` |70 current-description type repairs,1500 invariants,100 before/after reference workflows; canonical3968 main pass at0848b07d…. |
| `text-model-comparison-20260930/` | Historical237-case three-model matrix; incorrect then-user chronology prevents intrinsic ranking. |

Earlier detailed operational narrative is recoverable from `0848b07d…` in Git and
`resume-docs.before/` in the current root. Original ignored evidence and dirty backups
were not deleted. Earlier hashes, red gates and proof limits remain bound to their own
revisions; this consolidation does not convert them into current or physical evidence.
