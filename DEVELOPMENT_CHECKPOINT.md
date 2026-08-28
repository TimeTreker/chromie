# Chromie Development Checkpoint

Status: GI/GA/Planner primary-result source closure retained; interactive resource admission blocks must-pass
Updated: 2026-08-28
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
     (complete Goal coverage + truth strength + exact wording + provenance + satisfaction)
  -> trusted schema/provenance/integrity validation
  -> accept the Plan
     OR one semantics-preserving DTO repair where that pass already permits it
     OR distinct deeper-cognition escalation from Fast to Deep
     OR fail closed
```

There is no same-owner Planner truth qualifier, coverage reviewer, communication
reviewer, or audit model call.

## Implemented in the current worktree

- Added `ResponsibilitySourceEvidence` with inclusive source-token refs to the
  shared Responsibility proposal and made the live GI schema require it.
- Primary and Deep GI prompts now own completeness, atomic decomposition, modality,
  material bindings, sibling relations, and source evidence in one result.
- Trusted validation checks only source-ref membership/order/non-overlap and the
  existing closed DTO/provenance/authority mechanics.
- Removed the GI coverage-certificate DTOs, projection/resegmentation machinery,
  coverage repair, and the `goal_interpretation_responsibility_coverage` stage.
- Resolved valid GI now uses one model call. Mechanical primary shape failure has
  one DTO repair; genuine unresolved meaning has one Deep delegation; semantic or
  authority rejection fails closed.
- Migrated retained GI/dialogue scenarios to primary evidence and logical call
  budgets. Noncanonical `pace` fixtures now return canonical `speed` in the primary
  DTO rather than relying on a semantic repair call.
- Added a repository-policy guard against reintroducing the removed GI stage,
  certificate, payload builder, or acceptance wrapper.
- Removed the GA responsibility-coverage DTO/schema/prompt/validation lifecycle and
  its coverage, fresh-interpretation, and final-audit model calls.
- Limited GA to one valid primary invocation plus at most one mechanical DTO repair;
  semantic/grounding/conservation validation runs after parsing and cannot enter repair.
- Migrated GA regressions to primary-result conservation and exact one/two-call budgets.
- Removed the Planner truth-qualification, retained-response review, and coordinated
  Goal-coverage review calls together with their DTOs, schemas, prompts, audit module,
  dedicated model client, runtime health field, environment key, and warm-model role.
- Strengthened Fast first-response, Fast Advance, canonical Fast Plan, and Deep Plan
  primary prompts so each result owns complete Goal/Evidence truth, exact wording,
  step ownership, satisfaction, and unresolved decisions before trusted validation.
- Migrated Fast/Deep Planner regressions to primary-result contracts and exact one-call
  logical budgets, while preserving only existing bounded mechanical DTO repair and
  distinct Fast-to-Deep escalation paths.

## Other owner-authorized closure in this checkpoint

- Removed the premature DBOS/durable-backend experiment completely: the optional
  dependency, backend abstraction, DBOS adapter, eligibility field, and dedicated tests
  are deleted. `CapabilityRuntime` directly owns its in-process `asyncio.Task` lifecycle
  again. This does not reject a future inter-process event transport; it avoids freezing
  a speculative backend contract before the in-process domain/event contract is proven.
- Replaced the monolithic `scenarios/general_ability_acceptance.json` index with
  self-describing, one-scenario-per-file discovery under
  `scenarios/general_ability/<must_pass|core|challenge>/<ability-class>/`.
  The retained cohort contains 50 must-pass, 15 core, and 8 challenge scenarios.
  Every selected must-pass case runs before its stage report is produced; a hard
  must-pass failure blocks core/challenge only after the complete must-pass stage.
- Scenario metadata is local to each file, so a future scheduler or database importer
  can shard/extract cases without synchronizing a central registry.

## Evidence ledger

| Evidence | Result | Qualification limit |
|---|---|---|
| Pre-fix focused GI matrix at baseline | 110 passed | Reproduced the nonconforming extra coverage call; not target evidence |
| Current focused GI matrix | 38 passed | Automated module/contract evidence |
| Current retained GI + dialogue scenarios | 31/31 passed | Automated scripted module/dialogue evidence |
| Current focused Planner matrix | 308 passed, 9 subtests passed | Automated primary-result/call-budget evidence |
| Repository engineering policy gate | 15 rule families passed, 0 exceptions | Mechanical source-policy evidence |
| Canonical full local gate | 2,023 maintained tests plus 20 legacy Agent tests passed | Automated source/integration evidence |
| Level A general abilities | 12/12 passed: robust intent 8/8; Planner/Goal semantic quality 4/4 | Deterministic Level A only |
| Documentation authority gate | 96 Markdown files passed | Current documentation consistency only |
| Pre-fix live iteration 50, RTX 4090/Qwen3 4B | 32/36 contract-valid; four legacy coverage HTTP 503 failures; about 25/36 strict semantic passes | Diagnostic baseline only; different implementation |
| Pre-Planner-fix 50-case must-pass aggregate | 1/50 machine passes; 29/29 first-response truth-review calls timed out; GA primary accepted 18/45 | Diagnostic comparison only |
| Post-Planner-fix 50-case must-pass aggregate | 8/50 machine passes; zero retired review calls; GA primary accepted 43/44; 16 foreground-deadline, 7 Runtime-timeout, 4 GA-stage failures | Dirty source-tree-bound C-preview identity; not target qualification |

The post-change aggregate is retained under
`.chromie/acceptance/general-ability/20260828T101824Z-live-text` with runtime identity
SHA-256 `c8b3fc0991b72d38dade6c7b38020353199c04cc3126eaae735bd42c5e53c9cc`.
Its one valid post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260828_183021.tar.gz`. It is
headless C-preview evidence from a dirty source tree, not physical microphone/speaker,
simulator execution, physical robot, or release evidence. All 42 machine hard failures
remain failures; manual semantic inspection of the eight mechanical passes additionally
finds `capability_inventory_truthful` incomplete because it promises an introduction
without naming any capability. Independent multi-model semantic review remains pending.

## Exact resume point

1. Keep the removed GI/GA/Planner review chains absent. The next implementation boundary
   is priority/resource admission inside existing owners: optional Social Attention and
   TTS preparation must not consume the only runnable GPU slot ahead of GA/Fast/Deep
   critical-path work. Do not add a new semantic owner or use a model swap to conceal
   this scheduling defect.
2. Reconstruct the failing critical path against the retained aggregate: GI commonly
   consumed 2.5–5.4 seconds, concurrent GA/Fast Advance about 5–7 seconds, and required
   canonical Fast planning another 6–8 seconds under the 15-second foreground deadline.
   Preserve GA and Fast Advance as concurrent consumers; do not introduce a merge barrier.
3. After a focused source fix and local gates, run one complete must-pass aggregate on
   one unchanged identity. Only a hard-pass must-pass stage may permit core/challenge.

## Claim boundary

The implementation is development-only. Automated source evidence does not qualify
live model quality, audible voice, physical microphone behavior, simulator behavior,
or robot hardware. Historical iteration 50 proves the old coverage-chain failure and
must not be represented as proof of the new primary-result implementation.
