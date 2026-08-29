# Chromie Development Checkpoint

Status: Planner-owned auxiliary social decoration is source-closed; current-revision Prompt/model and live behavior evidence remain open
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

The maintained Planner workflow is now:

```text
Responsibility/Goal + bounded Situation/Work/Evidence
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
reviewer, Social Attention model, or audit model call. Fast First Response has no
auxiliary surface; Fast Advance and canonical Fast/Deep planning make the optional
decoration decision in their primary result.

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
- The Host now starts and yields both critical GI consumers—Fast Advance and Goal
  Association—before dispatching the first Planner-authored speech to TTS. First speech
  may still start before Goal Association finishes; there is no merge barrier.
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
| Resource-admission regression | 147 cognitive/runtime/interaction/TTS/Social tests passed | Automated invocation-order evidence only |
| Repository engineering policy gate | 15 rule families passed, 0 exceptions | Mechanical source-policy evidence |
| Canonical full local gate | 2,017 maintained tests plus 20 legacy Agent tests passed | Automated source/integration evidence |
| Level A general abilities for this amendment | 18/18 distinct cases passed: composable planning 5/5; multi-Goal daily life 10/10; Planner/Goal semantic quality 4/4 | Deterministic Level A only; one case belongs to two classes |
| Documentation authority gate | 96 Markdown files passed | Current documentation consistency only |
| Pre-fix live iteration 50, RTX 4090/Qwen3 4B | 32/36 contract-valid; four legacy coverage HTTP 503 failures; about 25/36 strict semantic passes | Diagnostic baseline only; different implementation |
| Pre-Planner-fix 50-case must-pass aggregate | 1/50 machine passes; 29/29 first-response truth-review calls timed out; GA primary accepted 18/45 | Diagnostic comparison only |
| Post-Planner-fix 50-case must-pass aggregate | 8/50 machine passes; zero retired review calls; GA primary accepted 43/44; 16 foreground-deadline, 7 Runtime-timeout, 4 GA-stage failures | Dirty source-tree-bound C-preview identity; not target qualification |
| Post-admission-fix 50-case must-pass aggregate | 0/50 hard-pass; 24 GI overlap rejections, 8 GI transport timeouts, 1 GI whole-turn binding rejection, 6 GA timeouts, 7 Runtime/foreground timeouts | RTX 4090 Laptop/Qwen3 4B dirty C-preview diagnosis only |
| Pre-default qwen3.5:4b comparison cohort | 2/50 hard-pass; 18/48 GI turns accepted, 25 timed out, 5 failed closed validation; 16/18 accepted results retained spurious unresolved meaning | GI-only model override with one resident Ollama model; diagnostic C-preview only |
| Post-default qwen3.5:4b residency cohort | 2/50 mechanical hard-pass, 0/50 after manual semantic review; top-level retained GI results increased 17 -> 29 and explicit GI `ReadTimeout` cases fell 25 -> 6; 26/29 retained results carried false unresolved meaning | Dirty source-tree-bound C-preview identity; proves the residency fix but not semantic or end-to-end qualification |

The earlier post-admission aggregate is retained under
`.chromie/acceptance/general-ability/20260828T153643Z-live-text`, bound to runtime identity
SHA-256 `86a04a8da490c02918545d2dfe01674800b516e5cf0b80e838b34a06c9906546`.
Its one post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260828_234314.tar.gz`. All 50 cases are
hard failures, so core/challenge correctly did not start. Dominant raw primary outputs
duplicate atomic effects, cite overlapping spans, invent relation Responsibilities, and
label embodied requests as speech despite the explicit prompt/schema. Validation is
correctly fail-closed; this is not justification for resegmentation, a semantic repair
call, or optional Social Attention satisfying a requested effect.

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
