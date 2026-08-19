# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-19
Base main before this delivery: `5e134b98f240bd7f23d2df07b5e120faf5f31253`

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source and executable evidence win over old
milestone prose.

Current delivery focus: Goal-driven single semantic authority with human-like,
evidence-grounded interaction behavior.

## Current verdict

**Do not treat this tree as fully behavior-qualified.** The current dirty-tree
Level C replay now passes the retained two-turn user-outcome case: both walks
execute once, both finish with terminal Evidence and safe idle, and the second
turn continues the retained Goal with continuation-aware speech. It still misses
the qualified warm Planner-local timing budget: validated-GI-handoff to first
Communicative-Activity commitment is about 2.90 seconds on both turns, versus the
2.00-second target. The run used injected text, generated TTS, discarded output,
and a simulator; it proves no physical microphone, audible speaker, or physical
robot behavior. Because Chromie was dirty, it is development evidence rather
than clean current-revision qualification.

The main probe is `你往前走 10 秒。` → `刚才那个事情继续。`. Treat it as a
general continuity/action ability, never as a phrase target.

## 2026-08-19 debug-bundle defect closure

The uploaded `chromie_debug_bundle_20260819_100305.tar.gz` exposed two general workflows. The weather case translated `北京`, spent DTO repair on semantics, invented a travel-confirmation Goal, and later narrowed a whole day to night. Current GI deepens once from source, preserves exact entity surfaces, and keeps unrequested stated plans as context; GA commits one weather Goal; the typed Capability contract permits only `period=day` without a `day_part`.
The run/sing case lost the singing effect and admitted a false start claim. Current GI/GA keep separate body/singing Goals, truth review suppresses that claim, Fast Advance fails closed cleanly, and Deep retains `walk_forward(duration_s=15)` while truthfully reporting singing unavailable with no substitute vocal promise.
A later physical-Host SID `7cd09453` exposed one decoder gap: qwen3:4b chose speech for fresh weather evidence, and Ollama accepted the illegal tuple because the schema expressed it with `if`/`then`. The first disjoint-schema fix blocked `fresh=true + speech` but still permitted `work=true + fresh=false + speech`.
The current-revision bundle `chromie_debug_bundle_20260819_134519.tar.gz`, SID `b9894ca6`, exercised that remaining tuple for `下午重庆会不会下雨啊？`: GI mislabeled the absent forecast as ordinary speech with unfinished work; GA committed a non-provider speech Goal; canonical Fast treated the acknowledgement as completion; Runtime cancelled provisional weather Work and played the same acknowledgement twice; the weather provider was never invoked.
The earliest responsible fix is now one shared completion contract plus three complete decoder branches: fresh evidence is capability work, immediate speech has no downstream work, and non-fresh downstream effects cannot be speech. The prompt's over-broad rule that treated any question as ordinary conversation was replaced by a provider-neutral evidence gate over external, private, runtime, observed, or changing facts. No phrase mapping or Host semantic inference was added.
Exact current-image replay `direct-canonical-after-fix-b9894ca6` passes Core → GA → canonical Fast Plan with one fresh provider-required information Goal and `chromie.weather.lookup(location=重庆,period=afternoon)`; Agent image digest `sha256:9f938c0db927b4559d97bb2551ad5cfcea12eba9eff8a9ffb4a97c488d836fe0`. The exact utterance is retained in the truthful-embodied-speech live cohort, while the illegal tuple and all three schema branches have deterministic contract coverage.
The operator Host still owns the exclusive lock, so maintained live-text, weather result, audible TTS, simulator, and physical behavior remain unclaimed. No document, environment key, switch, compatibility path, or architecture layer was added.

## Latest actual workflow

Retained v31 evidence:
`.chromie/acceptance/general-ability/20260819-user-probe-continue-six-gates-v31-context-reuse/`.
The runner passes 1/1 at Level C and records one completed simulator walk on
each turn.

| Module / owner | Authoritative input | Actual output and handoff | Verdict |
|---|---|---|---|
| Gateway + Goal Interpretation / admission and WHAT | Exact admitted Chinese turn plus bounded continuity | First turn: one forward `body_action` Responsibility with duration 10 seconds. Second turn: one `continue` Responsibility targeting the retained walking Goal. The same evidence fans out to Fast Planner and Goal Association. | Correct |
| Fast first response / Communicative Activity and truth | Accepted GI Responsibility, interaction context, and no terminal Evidence | `好，我这就往前走10秒。`, then `好的，我这就继续往前走。`; both pass the mandatory same-owner truth check and reach discarded-output playback. GI handoff to commitment: 2,894.680 ms and 2,940.814 ms; commitment to playback: 1,293.917 ms and 1,254.552 ms. | Semantics, provenance, and delivery correct; **Planner-local timing still fails** |
| Fast Advance / HOW | The same Responsibility plus executable catalog and retained Goal context | One `soridormi.walk_forward(duration_s=10,speed=normal)` Activity per turn; no Deep Planner. | Correct; the stage events at about 13.72 s and 15.98 s remain slow diagnostics |
| Goal Association / canonical Goal authority | GI Responsibility plus no Goal on turn one, then the retained completed Goal on turn two | Turn one creates one ordinary `body_action` Goal with typed direction/duration/unit bindings. Turn two emits one `continue` association and no new Goal. | Correct; 19.18 s and 9.57 s remain slow diagnostics |
| Trusted Capability Runtime + Soridormi / execution and Evidence | Canonical Goal-bound Fast Plan at pinned Soridormi `fa8080d2…` | Exactly one 10-second walk completes on each turn; terminal Evidence re-enters cognition; duplicate completion speech is suppressed; both turns end safe idle. | Correct Level C simulator evidence |

```text
admitted text
  -> GI Responsibility
  -> Fast speech + truth check -> TTS/discarded playback
  -> Fast Advance || Goal Association
  -> canonical Goal-bound Plan
  -> Trusted Runtime -> pinned Soridormi simulator
  -> terminal Evidence -> duplicate-speech suppression -> safe idle
  -> follow-up GI continue -> same retained Goal -> one second walk
```

The earliest v23 blocker was Goal Association, not Runtime. Its candidate
validator treated missing semantic bindings and wrong resource shape as a
mechanically malformed DTO before the independent coverage owner could reject
them, consuming the sole DTO repair and feeding a coverage certificate into the
wrong schema. A second live defect then showed that an ungrounded coverage
`source_excerpt` stopped the transaction instead of triggering the already-owned
fresh semantic reconsideration. Current source leaves those judgments with Goal
Association: the first coverage audit may reject ungrounded provenance and invoke
one fresh interpretation; the final audit still fails closed. The coverage
contract now states that constraints belong on their responsibility's same Goal
through typed bindings rather than requiring sibling Goals.

The v29 execution already passed semantics and behavior but measured about
10.76/10.90 seconds from GI handoff to Fast commitment. Trace evidence showed the
same `gemma4:12b` model being reloaded at context 6,144 for response authorship and
again at 32,768 for truth qualification. Agent assembly now reuses the same client
and context topology for same-model consecutive Fast phases. v31 reduces those
intervals to 2.89/2.94 seconds without removing the truth check. An isolated v32
`qwen3:4b` experiment was faster but emitted extra JSON after the structured
first-response object on both turns, so no profile model change was accepted.

## Current source changes

- Goal Association sends semantic representation failures to its independent
  coverage/reconsideration path instead of spending DTO repair;
- first-audit source-provenance failure can trigger the existing one-shot fresh
  interpretation, while final provenance failure remains fail-closed;
- coverage prompts preserve constraints as typed facts on the same Goal;
- Agent-Skill applicability selection is model-owned rather than inferred by
  Host inspection of Goal prose;
- a Goal Association update forces canonical Fast revision so a stale
  provisional clarification cannot commit;
- same-model Fast response/truth phases reuse one client and context topology;
- Goal Interpretation applies one evidence gate and a disjoint completion schema
  so ordinary speech cannot absorb unfinished or fresh-information work;
- the reviewed Deep Planner broad exception remains fail-closed and its policy
  checksum now matches the audited source.

No new document, environment variable, runtime switch, compatibility path, or
first-class architectural term was added.

## Verification state

- The directly affected Goal Association, Agent-Skill, Fast Planner, Goal
  Interpreter, Cognitive Runtime, control-plane, and communication suites pass
  357/357.
- `./scripts/run_tests.sh` passes, including all 13 repository-policy families,
  test ownership, pinned static analysis, configuration inventory, runtime
  structure, documentation, 119 benchmark tests, and the maintained tests.
- The complete deterministic Level A suite passes 44/44.
- Configuration inventory remains 403 keys, 4 modes, 1 public boolean, and 0
  aliases; documentation remains 96 Markdown files.
- v31 Level C execution passes the exact case 1/1 with score 100 and no outcome
  errors, but manual timing review keeps full behavior qualification open.
- Physical microphone, audible speaker, and physical robot behavior remain
  unproven. The clean-current-revision live proof also remains open.

## Exact resume order

1. Start from a clean committed Chromie revision, regenerate `.env.runtime`, and
   rebuild/recreate the Agent. Never edit `.env.runtime` directly.
2. Reduce the remaining Fast first-response interval from about 2.9 seconds to
   at most 2.0 seconds through the existing Fast Planner owner. Preserve the
   mandatory truth qualification, immutable wording, fail-closed behavior, and
   profile-owned model choice. Do not adopt the failed v32 smaller-model result.
3. Rerun the exact live case against a clean Soridormi checkout at the manifest
   revision:

   ```bash
   python scripts/general_ability_acceptance.py --mode live-text \
     --only-case user_probe_continue_recent_walk --execute \
     --soridormi-repo /path/to/clean/pinned/soridormi \
     --evidence-dir .chromie/acceptance/general-ability/<current-revision-exact-case> \
     --timeout-s 240 --capability-timeout-s 180 --case-timeout-s 420
   ```

4. Require all six gates on both turns. Fail-closed is not a behavioral pass;
   motion completion is not a natural-speech or timing pass.
5. Only after this case passes, run its general-ability class, all Level A
   cases, and canonical gates. Then resume the remaining user probes in
   scenario order. Do not add architecture while an existing owner can express
   correct behavior.
