# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-19
Base main before this delivery: `3f58dffdc9f26c92faf081c335aa0fc0b408333c`

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source and executable evidence win over old
milestone prose.

Current delivery focus: Goal-driven single semantic authority with human-like,
evidence-grounded interaction behavior.

## Current verdict

**Do not treat this tree as behavior-qualified.** It contains the current
cross-turn continuity, exact-speech provenance, evidence re-entry, Agent-Skill
filtering, Planner truth qualification, and runtime-profile work, but the
latest live-text probe fails before motion. All six owner-required gates remain
open: semantic correctness, behavior, timing, natural speech, no
repetition/fabrication, and human-like failure. Older 44/44 and canonical-gate
records in status history apply only to their recorded revisions.

The main probe is `你往前走 10 秒。` → `刚才那个事情继续。`. Treat it as a
general continuity/action ability, never as a phrase target.

## Latest actual workflow

Retained v23 evidence:
`.chromie/acceptance/general-ability/20260819-user-probe-continue-six-gates-v23-evidence-and-truth/`.
It failed 0/1 on the first turn, so the continuation did not run.

| Boundary | Authoritative input → actual output | Verdict |
|---|---|---|
| Gateway / GI | Exact admitted text → one `body_action` Responsibility for forward motion lasting `10 秒` | Correct |
| Fast first response | Responsibility → candidate speech rejected by the configured truth owner for perspective and ungrounded-claim defects | Correct containment; no natural replacement reached the user |
| Fast Advance | Same Responsibility → `soridormi.walk_forward(duration_s=10)` after one mechanical DTO revision; about 26.75 s | Correct action semantics; timing fails |
| Goal Association | Same Responsibility, no active Goals → three model calls, then `structured_output_validation`; about 32.13 s | **Earliest blocking wrong boundary in v23** |
| Trusted Runtime / output | No canonical Goal → no dispatch, TTS, response text, or motion | Honest containment, but behavior and human-like failure fail |

```text
admitted text
  -> GI Responsibility (correct)
  -> Fast speech truth rejection (contained)
  -> Fast body-action plan (correct, ~26.75 s)
  -> Goal Association schema failure (~32.13 s)
  -> no Goal commit -> no Runtime dispatch -> no speech or motion
```

The preceding v22 evidence is at
`.chromie/acceptance/general-ability/20260819-user-probe-continue-six-gates-v22-timing-boundaries/`.
It also failed 0/1, but both turns executed one walking action. The continuation
acknowledgement, `好，我这就往前走十秒。`, sounded like a new request; dispatch
took roughly 34–35 seconds and whole turns roughly 66–67 seconds. It also
exposed a generic post-evidence fallback after duplicate suppression and an
evidence-boundary rejection for completed body Work.

## Current source changes, not yet live-qualified together

- exact `fast_activity_id` speech reuse and delivery provenance;
- duplicate delivery suppression that does not trigger a fake generic fallback;
- exact terminal-Evidence re-entry for completed Goal-bound Work;
- declared Agent-Skill output/domain applicability;
- continuation-aware Responsibility retention and Work reconciliation;
- constrained Planner InformationGap DTOs;
- profile-owned first-response and truth models;
- regressions for playback, TTS alignment, conversation state, Cognitive
  Runtime, evidence re-entry, Planner contracts, Agent Skills, and profiles.

These are general boundary changes, not hardcoded utterance rules. v23 proves
that Goal Association model-contract integrity and Fast/GA latency still block
human behavior.

## Verification state

- Recently passed: 31 Agent-Skill domain/selection tests; three focused
  continuation/retained-Work Cognitive Runtime tests; focused evidence re-entry,
  Planner schema, profile/settings, playback, TTS-alignment, and conversation
  state tests.
- The complete current-tree Level A run passes 44/44. This is deterministic
  Level A evidence only and does not override the failed v23 live-text outcome.
- The current focused rerun confirms two Goal Association failures:
  `test_weather_material_modifier_and_planner_progress_recover_to_one_goal` and
  `test_body_actions_miscast_as_physical_resources_are_reconsidered`.
- The 2026-08-19 pre-handoff repository-policy check fails at three boundaries:
  two Host inspections of `request.goals` in Agent-Skill discovery, and a stale
  reviewed exception-handler checksum in `agent/app/deep_planner.py`.
- Documentation, test ownership, runtime structure, semantic-authority, and
  regenerated configuration-inventory checks pass. The inventory grows from
  401 to 403 keys for the two documented service-owned model variables; modes
  remain 4, public booleans 1, and aliases 0.
- Benchmark tests pass 119/119, then the benchmark gate stops on the same policy
  failures. `./scripts/run_tests.sh` also stops at repository policy before the
  maintained suite, so no current full-suite result is claimed. `git diff
  --check` passes. Physical microphone, audible speaker, simulator execution
  for these probes, and physical robot behavior are not proven.

## Exact resume order

1. Pull this handoff commit and generate a clean runtime. Rebuild rather than
   trusting manually recreated containers. The local v23 experiment used
   `qwen3.5:4b` for Fast first response/truth; committed profiles are the
   authority elsewhere. Never edit `.env.runtime` directly.
2. Reproduce the two Goal Association tests and v23
   `structured_output_validation`. Fix Goal Association, the earliest wrong
   owner; do not add a repair layer, semantic Host rule, or phrase rule.
3. Remove the Agent-Skill Host semantic inspection or restore model-owned
   selection without losing capability grounding. Re-audit the Deep Planner
   exception handler before refreshing its checksum; never update the checksum
   merely to silence the gate.
4. Rerun the exact live case:

   ```bash
   python scripts/general_ability_acceptance.py --mode live-text \
     --only-case user_probe_continue_recent_walk --execute \
     --evidence-dir .chromie/acceptance/general-ability/20260819-user-probe-continue-six-gates-v24 \
     --timeout-s 240 --capability-timeout-s 180 --case-timeout-s 420
   ```

5. Require all six gates on both turns. Fail-closed is not a behavioral pass;
   motion completion is not a natural-speech or timing pass.
6. Only after this case passes, run its general-ability class, all Level A
   cases, and canonical gates. Then resume the remaining user probes in
   scenario order. Do not add architecture while an existing owner can express
   correct behavior.

## Verification commands

```bash
git status --short
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_runtime_structure.py
python scripts/check_docs.py
python scripts/semantic_authority_audit.py
python scripts/general_ability_acceptance.py --mode level-a --no-write
./scripts/benchmark_check.sh
./scripts/run_tests.sh
```
