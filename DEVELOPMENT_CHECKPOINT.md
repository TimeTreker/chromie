# Chromie Development Checkpoint

## Current resume point — water acceptance still fails, 2026-10-07

Delivery base `main` / fetched `origin/main` was
`073abb4daad94c8bb419db6b05ba8f6310c4a0a6`. This revision combines the
open-ended-help UMI prompt repair, the GA native wire ownership-row bound, the
SC terminal-failure result-accounting repair, regression tests and request-only
workflow fixture recapture. Canonical Schema/Host authority is unchanged. The
delivered revision is the commit containing this checkpoint and [Handoff](HANDOFF.md).

The original text episodes crossed two different boundaries. In SID `a87066b5`,
UMI split “I am a little thirsty, can you help me?” into overlapping speech and
invented information Responsibilities; Host rejected it before GA/Planner/SC. In
SID `d7e6f1a3`, UMI accepted the water delivery request, GA duplicated ownership
of its one source ref, Host rejected it and cancelled speculative planning, and
SC falsely asked for repetition after an internal failure. The source repair
addresses those earliest observed boundaries without creating a second semantic
authority. Direct same-model contrasts/replays passed their reported Schema/Host
checks, but do not establish general live behavior.

The canonical local gate now passes: `./scripts/run_tests.sh` exited 0 (169
benchmark, 3,983 main, five environment skips, 1,023 subtests, 20 legacy Agent
tests); repository policy and docs checks pass. Four relevant Level A ability
classes pass 22/22. Strict request-only workflow replay passed 6,000/6,000.
Evidence is private under `.chromie/acceptance/umi-help-split-20261007/`,
`.chromie/acceptance/ga-duplicate-20261007/`,
`.chromie/acceptance/sc-internal-failure-20261007/` and
`.chromie/acceptance/thirst-offer-20261007/`.

A deployed text aggregate attempted all 79 discovered cases on the current dirty
source; 13 passed automatically and 66 failed, including 59 integrity failures.
The cohort and qualification are incomplete. The Agent endpoint became unavailable
partway through the run, and its runtime identity changed; outage cause is unknown.
One bundle was collected afterward:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_121723.tar.gz`. On the
water dialogue, Chromie offered help on the first turn but UMI reduced “Sure,
water is perfect!” to speech on a follow-up; separately, Fast Planner emitted an
invalid provider-resolved source for accepted “sure”. No physical work was
authorized in those failures. Candidate prompt/decoder experiments were rejected
and reverted because they introduced unsafe or ungrounded results; their retained
contrasts are in the thirst-offer evidence root. No safe general repair of these
new boundaries is claimed.

Next: establish a stable deployed identity and service, diagnose the UMI and
Planner acceptance boundaries from retained packets, and obtain owner approval
before any canonical semantic contract change. Repair the earliest boundary,
rerun focused scenarios and the complete live cohort, then perform narrow
current-revision supervised voice proof and default target-evidence closure.
Physical microphone, speaker and robot proof is still absent.

## Previous patch — open-ended help interpretation, 2026-10-07

Pre-delivery base `main` / `073abb4daad94c8bb419db6b05ba8f6310c4a0a6`
matched fetched `origin/main` before edits. Expected resume revision is the latest
commit containing this checkpoint and [Handoff](HANDOFF.md). At the time of that
patch's initial handoff it was not committed or pushed. The historical planned
delivery sequence was local gate, narrow current-revision voice proof, then
default target-evidence closure; current blockers and resume order are above.

The live text turn “I am a little thirsty, can you help me?” failed at primary UMI:
one response/acknowledgement Responsibility and one internal help-selection
`information` Responsibility cited overlapping source words. The UMI validator
correctly rejected that semantic split; Core returned 503 and Host spoke the safe
retry notice. The existing UMI prompt now states that an open-ended request with
a reported need is one conversational Responsibility unless the person separately
requests an effect, fact or speech act. UMI still owns WHAT; SC owns wording,
Planner owns HOW, GA owns continuity and Host does not repair semantics. No new
model, runtime switch, authority, document or environment variable was added.

Current evidence root: `.chromie/acceptance/umi-help-split-20261007/` (ignored,
private). A frozen eight-case English/Chinese contrast baseline had two primary
source-overlap failures; the selected prompt produced eight Schema/Host-valid
outputs, including the exact English originating turn. Its Chinese open-ended
help outcome remained in English, so bilingual semantic qualification is open.
No current-revision deployed Host/voice claim follows from these direct model calls.
The existing `thirsty_then_water_delivery` general-ability scenario already retains
the original two-turn episode; its full live run remains due.

The five prototypes and complete 6,000-case workflow archive were recaptured
request-only at freeze revision 17. Full replay passed 6,000/6,000 with zero
candidate calls and identical non-request fields; focused workflow replay passed
104/104. The robust-intent Level A class passed 8/8, UMI focused tests passed
44/44 with 77 subtests, benchmark tests passed 169/169, main tests passed
3,981 with five environment skips and 1,023 subtests, and 20 legacy Agent tests
passed. Policy, ownership, pinned Ruff/mypy, configuration, runtime and docs checks
passed. `./scripts/run_tests.sh` did not itself exit 0 in this session: it first
met pre-existing stale ignored freeze files, then a command termination (143),
then 83 stale request-packet failures. Those files were preserved and the pinned
archive restored; the final benchmark and main components passed separately after
request recapture. Do not report the single-command canonical gate as passed.

Next: run the single-command gate in an uninterrupted shell; then run the existing
two-turn thirst/water scenario with the current source and a bound service identity
when the active operator text console can be left undisturbed. Judge the complete
speech, Goal and Work path, not only UMI acceptance. Qualify Chinese outcome-language
and material-need retention before claiming a bilingual UMI fix or default-target
closure. Physical microphone, speaker and robot proof remains supervised.

## Previous delivery — UMI/Planner and historical Memory contracts

Pre-delivery base `main` / `0848b07d14886a0238ca71ceae3aa65fd0bcd103` matches
fetched `origin/main`; upstream was checked before source edits and again after the
native cohort. Expected resume revision is the latest `main` commit containing this
checkpoint and [Handoff](HANDOFF.md). The owner authorized non-model repairs, commit
and push, and explicitly forbids UMI-authored `bindings`.

The current focus remains Goal-driven single-authority architecture.
The active delivery line remains canonical local verification → current-revision
voice proof → default target-evidence closure. Local verification passes; voice and
target closure remain open. No new feature line, semantic owner, Memory store,
runtime switch or model/profile change is introduced.

## Implemented at existing owners

- UMI keeps complete natural WHAT, current-turn provenance, uncertainty and initial
  cognition requests. Primary/Deep Schema, parser and Decision reject the `bindings`
  key, including empty objects. Core rejects nonempty bindings; the shared DTO's
  empty default and read-only retained canonical Goal projections remain internal.
  Earlier Charter prose allowing sparse UMI bindings is removed to follow existing
  principle30. The principle and module responsibilities are unchanged.
- Planner alone extracts Capability parameters. Fast arguments may cite current-turn
  tokens or exact owning accepted outcome tokens with `source_responsibility_ref`.
  Host materializes the selected quote and binds it only to that Responsibility's
  GA Goal; it cannot infer missing meaning, borrow a sibling or fabricate a source.
  Provider-owned source resolution accepts cited reported search clues, while bare
  unresolved source cannot claim a citation. Retained typed constraints remain binding.
- Historical object/location Memory remains Planner context outside current sight.
  Both prompt-entry and cognitive projections retain existing creation/update times
  and source references. A past living-room water delivery suggests where to search;
  it does not prove current presence. This is a controlled projection regression,
  not proof of automatic action persistence, an executed search or actual acquisition.
- Stale UMI scenario/fixture outputs and the template are reconciled without dropping
  material meaning. All6000 workflow records and5 prototypes are request-only
  recaptured: inputs, raw reference decisions, complete meaning, parameters, prior
  Goals, faults, provider outcomes, assertions and splits remain unchanged. Strict
  replay and oracles are not weakened. The complete archive is freeze revision16.
- Superseded checkpoint/handoff narratives and resume commands are consolidated here
  and in Handoff. Historical evidence remains retained and recoverable from Git.
  No maintained document, environment variable or architectural owner is added.

## Current evidence ceiling

Evidence root: `.chromie/acceptance/umi-no-bindings-20261005/`.

| Axis | Observed result |
| --- | --- |
| Implementation | UMI binding authority conflict, Fast source/contextual provenance restriction and Memory timestamp projection loss are repaired at existing owners. Model, initial activation ownership and GA/SC/Host boundaries remain. Other conformance findings remain open. |
| Automatic verification | Frozen bilingual20 before8/20 → final20/20 Schema/Host; exact production wire/pinned native decoder20/20 without inference. UMI1496/Fast204 references valid. Focused215+84 tests pass. Level A19/19 across3 relevant classes. Strict6000/6000 replay passes with zero candidate calls; request-only6000+5 invariants hold. Canonical169 benchmarks,3981 main tests/5 environment skips/1023 subtests and20 legacy Agent tests pass; policy, ownership, pinned static, configuration and docs pass. |
| Target validation | Unchanged baseline79:22 automatic pass/57 fail, same-agent review6 pass/10 partial/61 fail/2 insufficient. Changed-source full79:13 automatic pass/66 fail, review5 pass/7 partial/67 fail. All cases attempted, zero skipped; blocked later turns make cohort/qualification incomplete. Overall behavior improvement is not established.86 native UMI primary outputs contain zero binding keys, but activation/meaning omissions remain. No independent, current voice, physical/audible or default-target qualification. |
| Deployment state | Agent-only source imagebc6577e4… retains original dependency layers; packaged/host source8140dcc3… matches before/after. Model/profile/environment unchanged. Native source/tree and service identities fixed for each aggregate. One pre-cohort grammar probe caused LLM OOM/automatic recovery; the changed-source cohort uses its recovered identity, with no further restart. No promotion/release; TTS dependency rebuild remains unqualified. |

The raw milk result now retains ahead/about50meters but requests GA only; Planner
and resource provider are not invoked. Controlled complete-WHAT references prove
only the downstream program repair. Native walk3s/right-turn2s completes in simulation,
but Planner falsely cites the walk's three-second phrase for its turn duration2s;
semantic provenance review therefore fails despite the automatic pass. Valid source
coordinates do not prove correct parameter mapping. Raw omissions or incorrect choices
are not proof of an intrinsic model-capacity limit and were not tuned or repaired downstream.

## Next work and blockers

1. Preserve the green canonical gate and exact workflow freeze. Next delivery evidence
   is narrow current-revision voice proof, then default target closure. Physical
   microphone/speaker/robot evidence remains supervised; text, discarded TTS and mock
   acquisition/handover do not replace it.
2. Preserve all79 before/after primary packets and adjudications. Do not claim a native
   semantic pass, motion/stop proof for unexecuted cases, or a behavioral improvement.
   UMI activation/result-type, accepted-offer continuity and genuine uncertainty remain
   unqualified; GA/Host cannot fill omissions. The owner excludes model-ability tuning.
3. Review retained Attention same-authority second-call and SC fresh-turn silence/
   provenance findings under the current Issue and existing Charter. They are not
   fixed by this patch. Broad/compound exact-Goal-count oracles and historical-memory
   search-to-execution coverage also need qualification; they must not dictate a new
   upstream split or promote historical candidates to current facts.
4. Resume only from fetched current source; preserve Soridormi's unrelated dirty work,
   running simulator and ignored evidence. Detailed identities, artifacts, failed
   iterations and copy-ready checks are in Handoff. No new architecture or authority
   amendment is authorized by this delivery.

Earlier delivery mechanisms and evidence are summarized in Handoff and
[the audit](ARCHITECTURE_AUDIT.md). Their older green/red totals and service identities
remain historical, not current qualification or commands to deploy retired images.
