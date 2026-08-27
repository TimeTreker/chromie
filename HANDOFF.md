# Chromie Latest Handoff

Audience: a coding agent or project operator resuming this exact GI iteration from another
checkout or machine.
Owner: the project owner; update or replace this snapshot whenever
`DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only. `DEVELOPMENT_CHECKPOINT.md` remains the current
resume authority, while source/tests/evidence remain technical truth.

This separate handoff exists because cross-machine commands, runtime identities, private
evidence locations, interrupted-process state, and negative claim boundaries are too
operational and volatile for the short authoritative checkpoint. It adds one current
document surface; no prior handoff document existed, and this file must be overwritten or
removed rather than accumulated into dated handoff files.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Implementation commit: `6a5619ab8552d733c20f11788b9b0639f452f3ee`
- Implementation subject: `Harden goal interpretation contracts and live test workflow`
- Resume commit: the latest `origin/main` commit containing this handoff
- Expected remote: `origin/main` contains the implementation commit and `HANDOFF.md`
- Expected worktree at handoff: clean
- Current scope: GI and its contract validator only; GA/Planner return later

Bootstrap:

```bash
git clone https://github.com/TimeTreker/chromie.git
cd chromie
git switch main
git pull --ff-only origin main
git status --short --branch
```

## What changed

The committed patch strengthens GI without moving WHAT/HOW authority:

- equivalent system-prompt compression: 17,325 -> 10,772 bytes;
- request-specific dynamic schemas and deterministic provenance/atomicity validation;
- one certificate-bound deep recovery pass with closed bindings and conservative count floor;
- preservation of validated consequential-effect siblings against a smaller stochastic audit;
- explicit dynamic-schema distinction between Chromie's own vocal performance (`singing`)
  and control of existing recorded media (`media_playback`);
- aggregate-first live test and one-bundle-per-cohort documentation.

No GA or Planner source was changed to hide downstream failures.

## Evidence ledger

### Current-content automated evidence

Before the commit request, the final dynamic-mode schema content passed:

```text
python -m unittest tests.test_goal_interpreter_llm_prompt tests.test_semantic_task_continuity
Ran 113 tests ... OK
```

No additional tests were run after the owner asked for an immediate commit/push. The prior
full local gate (2,123 tests, 20 legacy Agent tests, Level A 45/45) predates the last
dynamic-mode schema edit and must not qualify the current commit by itself.

### Last complete live aggregate

- Evidence directory:
  `.chromie/acceptance/full-live-e2e-iteration-34`
- Runtime identity:
  `.chromie/evidence/runtime-identity-full-live-iteration-34.json`
- Dirty source tree SHA-256:
  `ec90c7b790cd31102cd79e2c519edd29c5940963cd173e18515bc12ab68f4496`
- Runtime identity SHA-256:
  `9133e934580b655db19aa7f8d8808e34d95bff46ed67955a7e3dd1bc674a7e2a`
- Agent image:
  `sha256:c65d198fb5d63d843170d752df0c4e03dd2847273c4c6aa9d0cf8c6228de92a4`
- Result: Level C, 25/36 passed, 11 failed
- Exactly one bundle:
  `/home/chromie/Downloads/chromie_debug_bundle_20260827_212141.tar.gz`

GI judgment from iteration 34:

- no retained GI 503/contract hard failure;
- both prior three-effect omission cases emitted three Responsibilities in the complete
  aggregate;
- `debug_bundle_run_15_while_singing` exposed a new GI modality error:
  `sing while running forward` was labeled `media_playback`;
- the remaining cohort failures were attributed to GA/Planner, capability timeout,
  response/user-outcome, WorkDAG/harness, or latency boundaries and remain deferred.

### Interrupted current-code focused run

Iteration 35 used current file contents and Agent image
`sha256:0b5f59a2110b691570410c53b4d05a5c6abb0aeb3b7fd647d762de7c4c9fc787`,
but its identity was captured before committing and therefore says revision `d0b94def`,
dirty source tree `f31daccde8b9...`, identity `1e9049b79eaf...`. The three-case focused
cohort was interrupted during case 1/3. Do not reuse that identity, do not collect a bundle
for that incomplete run, and do not count it as evidence.

## Resume procedure

### 1. Build and verify runtime

```bash
docker compose build chromie-agent
docker compose up -d --no-deps chromie-agent
docker compose ps chromie-agent
ss -ltn '( sport = :8000 or sport = :5555 )'
```

If Soridormi is not listening, follow `CHROMIE_RUNBOOK.md`; on the original sibling-repo
layout the simulator was started with:

```bash
../soridormi/scripts/start_soridormi_mujoco.sh --no-viewer --keep-running
```

### 2. Capture clean current-commit identity

Use the next unused iteration number; `36` is suggested:

```bash
python scripts/capture_runtime_identity.py \
  --orchestrator-env .env.runtime \
  --output .chromie/evidence/runtime-identity-full-live-iteration-36.json
```

The identity must report the currently checked-out `origin/main` handoff commit,
`dirty=false`, deployment complete, and the newly built Agent image. It must contain
implementation commit `6a5619ab8552...` in its history. Do not add `--allow-dirty` for
qualification evidence.

### 3. Run one focused vocal/compound cohort

```bash
python scripts/general_ability_acceptance.py \
  --mode live-text \
  --only-case user_probe_walk_while_singing \
  --only-case debug_bundle_run_15_while_singing \
  --only-case user_probe_walk_sing_blink_simultaneously \
  --execute \
  --grant-confirmation \
  --assertion-scope user-outcome \
  --runtime-identity .chromie/evidence/runtime-identity-full-live-iteration-36.json \
  --evidence-dir .chromie/acceptance/full-live-e2e-iteration-36-focused \
  --case-timeout-s 900
```

Judge GI even when a later GA/Planner assertion fails. The retained
`core_interpretation.json` files must show:

| Case | Required GI Responsibilities |
|---|---|
| `user_probe_walk_while_singing` | two: `body_action`, `singing` |
| `debug_bundle_run_15_while_singing` | two: `body_action`, `singing`; never `media_playback` |
| `user_probe_walk_sing_blink_simultaneously` | three: `body_action`, `singing`, `body_action` |

Any GI 503, responsibility omission, hidden effect binding, or vocal-mode substitution means
the GI iteration is not closed. Do not fix GA/Planner symptoms in this scope.

### 4. Run the complete cohort on the same identity

Only after focused GI passes:

```bash
python scripts/general_ability_acceptance.py \
  --mode live-text \
  --execute \
  --grant-confirmation \
  --assertion-scope user-outcome \
  --runtime-identity .chromie/evidence/runtime-identity-full-live-iteration-36.json \
  --evidence-dir .chromie/acceptance/full-live-e2e-iteration-36 \
  --case-timeout-s 900
```

Do not edit source, rebuild, restart, or substitute isolated cases during the 36-case run.
After it ends, collect exactly one bundle:

```bash
./scripts/collect_debug_bundle.sh
```

Then inspect all cases, including mechanical passes:

```bash
jq '{passed,failed,evidence_level,provenance,failures:[.ability_classes[].cases[] | select(.ok==false) | {case_id,earliest_suspect_boundary,errors}]}' \
  .chromie/acceptance/full-live-e2e-iteration-36/summary.json

while IFS= read -r file; do
  jq -r --arg file "$file" \
    '[($file | split("/")[-2]), (.responsibilities | length | tostring), ([.responsibilities[] | (.local_ref + ":" + .output_mode + ":" + .outcome)] | join(" | "))] | @tsv' \
    "$file"
done < <(find .chromie/acceptance/full-live-e2e-iteration-36 \
  -name core_interpretation.json -type f | sort -V)
```

### 5. Finish documentation and canonical gates

Update `DEVELOPMENT_CHECKPOINT.md`, this file, and `docs/STATUS.md` with the final identity,
cohort result, GI judgment, and one bundle path. Then run:

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Commit and push only after reporting any remaining evidence gaps honestly.

## Deferred failures

Iteration 34's 11 aggregate failures include downstream response wording, GA structured
output, deep-planner numeric realization, weather timeout/evidence observation, WorkDAG goal
revision, and warm-latency failures. They are real, but they are intentionally outside this
GI-only iteration. Do not broaden the patch to make the aggregate score look better.

## Claim boundary

The retained live evidence is Level C injected text through live services and the Soridormi
simulator. It is not physical microphone, audible speaker, or physical robot evidence. The
current clean commit has not yet completed focused live proof, a complete live aggregate, or
the final canonical gates. Release qualification remains false.
