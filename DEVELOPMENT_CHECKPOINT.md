# Chromie Development Checkpoint

Status: Planner-owned auxiliary social decoration and Issue #32 streaming Fast-Planner presentation are source-gated; Prompt/model promotion and live behavior evidence remain open
Updated: 2026-08-29
Starting baseline: `7b4a25d8c8343b7f67509d3916e32272d6afc86f`
(`Add external architecture audit`)
Resume branch: the latest `origin/main` commit containing this checkpoint and `HANDOFF.md`

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md),
[Acceptance](docs/ACCEPTANCE.md), and [Latest Handoff](HANDOFF.md).
Source, tests, and retained executable evidence win over this summary.

## Active issue and boundary

This is the current Goal-driven single-semantic-authority delivery line.
Charter principles 30–31 require each semantic authority to produce its complete
grounding/conservation evidence in its primary model result. GI, Goal Association,
and Fast/Deep Planner now follow that source contract. Do not treat whole-pipeline
source closure as target-model or live behavior qualification.

The maintained GI workflow is now:

```text
admitted turn + bounded semantic context + closed source-token table
  -> one primary WHAT-only GI result
     (Responsibilities + modes + bindings + relations + source_evidence)
  -> trusted mechanical validation
  -> accept resolved valid meaning
     OR one same-stage DTO repair for malformed shape
     OR one source-based Deep GI delegation for genuine unresolved meaning
     OR fail closed for semantic/authority contradiction
  -> GA / Planner
```

There is no GI coverage auditor, critic, reviewer, or resegmentation call.

The maintained GA workflow is now:

```text
accepted GI Responsibilities + bounded Goal/dialogue state
  -> one primary Goal identity/continuity result
  -> optional one mechanical JSON repair only for a Pydantic-invalid DTO
  -> deterministic closed-reference/provenance/binding/conservation validation
  -> canonical Goal commit or fail closed
```

There is no GA coverage certificate, reviewer, fresh interpretation, final audit, or
semantic repair call. Grounding or conservation rejection is terminal.

The maintained initial Fast Planner workflow is now:

```text
immutable GI Responsibilities
  -> concurrently:
       GA continuity transaction
       one Fast Planner stream
          -> validated PresentationCommit (speech/silence + anchored auxiliary)
          -> terminal Fast result or typed pre/post-commit failure
  -> terminal result + GA mapping + accepted commit identity
  -> canonical Plan validation
  -> confirmation / Work dispatch / Deep escalation / silence / fail closed
```

Re-entry planning remains:

```text
Goal + bounded Situation/Work/Evidence
  -> one Fast or Deep primary HOW result
     (complete Goal coverage + truth strength + exact wording + provenance + satisfaction
      + optional non-Goal auxiliary_activities[])
  -> trusted schema/provenance/integrity validation
  -> accept the Plan
     OR one semantics-preserving DTO repair where that pass already permits it
     OR distinct deeper-cognition escalation from Fast to Deep
     OR fail closed
```

There is no same-owner Planner truth qualifier, coverage reviewer, communication
reviewer, Social Attention model, or audit model call. `PresentationCommit`, terminal
Fast output, and canonical Fast/Deep planning make optional decoration decisions only
under exact primary anchors. Raw tokens never reach TTS and Goal-owned Work never starts
before the complete terminal result, canonical Goal binding, and full validation.

## Implemented in the current worktree

- GI now requires per-Responsibility source evidence in its primary result. Trusted
  code validates closed mechanics; the former coverage/resegmentation model chain is
  removed, and only one DTO repair or one genuine Deep delegation remains eligible.
- GA now owns continuity in one primary result plus at most one mechanical DTO repair.
  Its coverage, fresh-interpretation, final-audit, and semantic-repair calls are gone.
- Fast/Deep Planner primary results now own Goal/Evidence truth, exact wording, step
  ownership, and satisfaction. Same-owner truth/coverage reviewers and their dedicated
  model/runtime surfaces are removed; existing DTO repair and Fast-to-Deep escalation
  retain their narrower contracts.
- The Agent `/fast-advance` endpoint now makes one Ollama streaming invocation and emits
  typed NDJSON frames. The Host starts that stream and GA concurrently, launches only a
  complete validated `PresentationCommit`, and requires the same commit identity in the
  terminal Fast result and CanonicalPlan.
- Failures before commit are silent; failures after commit preserve the already-launched
  truthful communication but dispatch no Goal Work. No read/effect Capability starts
  before the terminal result, GA binding, and canonical validation.
- The independent `SocialAttentionPlanner`, endpoint/client, model/config role, and
  background opportunity queue/worker are removed. `CanonicalPlan.auxiliary_activities[]`
  is fingerprinted separately from Goal-owned `steps[]`; it carries no Goal IDs or
  completion authority.
- Runtime validates, suppresses, or executes only the exact Planner-authored auxiliary
  Capability. It cannot reselect or retarget. Auxiliary-only changes/results never create
  `CognitiveOpportunity` or borrow its required Goal scope.
- Focused regressions cover Planner schema/candidate binding, canonical fingerprint and
  anchors, exact Runtime materialization, Goal isolation, and suppression without
  reselection. Repository guards reject restoration of the retired second writer.

## Evidence ledger

| Evidence | Result | Qualification limit |
|---|---|---|
| Pre-fix focused GI matrix at baseline | 110 passed | Reproduced the nonconforming extra coverage call; not target evidence |
| Current focused GI matrix | 38 passed | Automated module/contract evidence |
| Current retained GI + dialogue scenarios | 31/31 passed | Automated scripted module/dialogue evidence |
| Current focused Planner matrix | 308 passed, 9 subtests passed | Automated primary-result/call-budget evidence |
| Issue #32 focused stream matrix | Ordered commit/terminal, one-call, failure containment, exact commit identity, no early Work, auxiliary anchoring, client/Runtime/scenario regressions pass | Automated source/contract evidence |
| Exact local provider probe | Ollama 0.32.14 + current `qwen3.5:9b` emitted 25 structured chunks with `presentation_commit` before `terminal_result`, terminal `done=stop`, and no thinking/error fields | Protocol probe only; not semantic, latency-under-load, live voice, or physical evidence |
| Resource-admission regression | 147 cognitive/runtime/interaction/TTS/Social tests passed | Automated invocation-order evidence only |
| Repository engineering policy gate | 15 rule families passed, 0 exceptions | Mechanical source-policy evidence |
| Current canonical full local gate | 1,993 maintained tests plus 20 legacy Agent tests passed | Current automated source/integration evidence |
| Level A general abilities for this amendment | 18/18 distinct cases passed: composable planning 5/5; multi-Goal daily life 10/10; Planner/Goal semantic quality 4/4 | Deterministic Level A only; one case belongs to two classes |
| Documentation authority gate | 96 Markdown files passed | Current documentation consistency only |
| Pre-default qwen3.5:4b comparison cohort | 2/50 hard-pass; 18/48 GI turns accepted, 25 timed out, 5 failed closed validation; 16/18 accepted results retained spurious unresolved meaning | GI-only model override with one resident Ollama model; diagnostic C-preview only |
| Post-default qwen3.5:4b residency cohort | 2/50 mechanical hard-pass, 0/50 after manual semantic review; top-level retained GI results increased 17 -> 29 and explicit GI `ReadTimeout` cases fell 25 -> 6; 26/29 retained results carried false unresolved meaning | Dirty source-tree-bound C-preview identity; proves the residency fix but not semantic or end-to-end qualification |

## Exact resume point

1. Keep the source-closed Planner-owned auxiliary boundary intact. Do not restore
   compatibility environment fields, endpoint shims, or the retired social decision worker
   while tuning Prompt/model behavior.
2. Keep the removed review chains absent and keep atomicity, mode, non-overlap, and
   source-provenance validation fail-closed.
3. The RTX 4090 Laptop profile now uses `qwen3.5:4b` only for GI, with a bounded 16K/512
   runner and two-model residency. Every other cognition model remains unchanged. This
   removes the reproduced GI eviction boundary; it does not qualify qwen3.5 semantics.
4. The complete post-change must-pass cohort is retained under
   `.chromie/acceptance/general-ability/gi-qwen35-default-fixed`, bound to runtime identity
   `78847784d3ff08df8b606fb921eb28010a0e87f34b146da41c4fabe1cc9341b8`.
   Its exactly one post-cohort bundle is
   `/home/chromie/Downloads/chromie_debug_bundle_20260829_063447.tar.gz`. Mechanical
   scoring reported 2/50, but both passes carried invented unresolved meaning, so manual
   semantic review is 0/50. The remaining gaps are qwen3.5 false ambiguity/Deep-GI
   amplification and single-slot GA/Fast contention; do not weaken validation, resegment
   in Host, or add a same-authority repair call.

## Claim boundary

The implementation is development-only. Automated source evidence does not qualify
live model quality, audible voice, physical microphone behavior, simulator behavior,
or robot hardware. Historical iteration 50 proves the old coverage-chain failure and
must not be represented as proof of the new primary-result implementation.
