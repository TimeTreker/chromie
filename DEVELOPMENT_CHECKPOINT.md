# Chromie Development Checkpoint

Status: current resume point; GI contract closure awaiting current-commit live proof
Updated: 2026-08-27
Implementation baseline: `6a5619ab8552d733c20f11788b9b0639f452f3ee`
(`Harden goal interpretation contracts and live test workflow`)
Resume branch: the latest `origin/main` commit containing this checkpoint and `HANDOFF.md`

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md),
[Acceptance](docs/ACCEPTANCE.md), and the operational [Latest Handoff](HANDOFF.md).
Source, tests, and retained executable evidence win over this summary.

## Active scope

This iteration preserves Chromie's Goal-driven single semantic authority and narrows work
to its earliest Goal Interpretation boundary.

Close only Goal Interpretation (GI), its DTO/schema validators, and directly related
contract evidence. Do not fix Goal Association (GA), Planner, weather-provider,
WorkDAG, response wording, or latency failures in this iteration. Record those failures
for the later GA/Planner pass.

GI remains WHAT-only:

```text
admitted turn
  -> fast GI candidate
  -> deterministic authority/provenance/shape validation
  -> independent atomic coverage certificate
  -> at most one certificate-bound deep resegmentation
  -> typed Responsibilities
  -> GA / Planner (out of current fix scope)
```

## Current committed implementation

- The GI system prompt was equivalently compressed from 17,325 to 10,772 bytes without
  changing the WHAT/HOW contract.
- Dynamic schemas and deterministic validation now enforce exact prior-speech evidence,
  canonical counts, explicit-number preservation, exact location/speed provenance,
  typed sibling coordination, closed recovery binding grammars, and rejection of hidden
  effect/HOW fields.
- Coverage certificates carry an explicit independent-outcome count. Smaller stochastic
  audits cannot erase already validated consequential effects, and invalid DTO structure
  can impose a conservative minimum responsibility count on the one deep recovery pass.
- Primary and coverage schemas now describe vocal modes per enum value: Chromie's own
  singing is `singing`; `media_playback` is only control/playback of existing recorded
  media. No phrase router or deterministic semantic-lane selector was added.
- Aggregate-first live iteration rules are documented in `AGENTS.md`, `CONTRIBUTING.md`,
  `docs/ACCEPTANCE.md`, and `docs/SCENARIO_DRIVEN_DEVELOPMENT.md`.

## Evidence retained before the current commit

| Evidence | Result | Qualification limit |
|---|---|---|
| Focused GI unit tests after the final dynamic-mode schema change | 113/113 passed | Automated source evidence only |
| Full local gate before the final dynamic-mode schema change | 2,123 tests plus 20 legacy Agent tests passed; Level A 45/45 | Stale for the last schema-only change; rerun required |
| Live iteration 34, dirty source tree `ec90c7b790cd...`, identity `9133e934580b...` | Complete Level C cohort: 25/36 passed | Diagnostic only; not the current clean commit |
| Iteration 34 debug bundle | `/home/chromie/Downloads/chromie_debug_bundle_20260827_212141.tar.gz` | Local private runtime evidence; exactly one bundle was collected |

Iteration 34 proved both earlier GI omission cases in the complete cohort:

- `weather_then_chinese_walk_blink_song`: weather completed, then GI emitted three
  Responsibilities for run, blink, and singing without stale-weather contamination.
- `user_probe_walk_sing_blink_simultaneously`: GI emitted three Responsibilities and GA
  received all three.

The same cohort exposed one new GI error in
`debug_bundle_run_15_while_singing`: both the primary candidate and coverage auditor
misclassified Chromie's own singing as `media_playback`. The committed dynamic-schema
change addresses that exact general modality distinction. Iteration 35 focused live proof
was intentionally interrupted during its first of three cases at the project owner's
request to commit and push; it is incomplete and must not be reported as passing.

## Exact resume point

Start from the latest clean `origin/main`; it must contain implementation commit
`6a5619ab8552...` and this handoff update. The deployed image on the original machine was
`sha256:0b5f59a2110b691570410c53b4d05a5c6abb0aeb3b7fd647d762de7c4c9fc787`, but another
machine must build and capture its own deployment identity.

1. Build/verify the current Agent and Soridormi simulator.
2. Capture a **new clean current-commit** runtime identity. Do not reuse iteration 35
   identity `1e9049b79eaf...`; it records the pre-commit dirty revision.
3. In one focused invocation, run:
   `user_probe_walk_while_singing`, `debug_bundle_run_15_while_singing`, and
   `user_probe_walk_sing_blink_simultaneously`.
4. Require GI output modes/counts of respectively:
   `body_action + singing`, `body_action + singing`, and
   `body_action + singing + body_action`; reject any GI 503 or `media_playback` substitution.
5. If focused GI passes, run the complete 36-case manifest-owned live cohort once on the
   same identity, with no source edit, rebuild, restart, or isolated-case substitution
   between cases.
6. After the complete cohort, run `./scripts/collect_debug_bundle.sh` exactly once, judge
   every case, and cluster failures by earliest shared boundary. Defer confirmed non-GI
   failures.
7. Update this checkpoint, `HANDOFF.md`, and `docs/STATUS.md`, then run the canonical gates.

Exact commands and evidence paths are in [HANDOFF.md](HANDOFF.md).

## Claim boundary

Current status is development-only. Iteration 34 is injected live-text + Soridormi
simulator Level C evidence, not physical microphone, audible speaker, or physical robot
evidence. The current clean commit has not completed focused live proof, a complete live
cohort, or the final canonical gates. Do not claim release qualification.
