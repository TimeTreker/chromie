# Fast Planner Multi-Goal Contract Path

Status: model-authored plan contract implemented; supervised live requalification open
Decision date: 2026-07-17
Scope: Fast Planner multi-goal model DTO, semantic authority, validation,
escalation, observability, response-claim discipline, rollout, and acceptance

- **Implementation:** model-authored multi-goal plan contract is present in the repository snapshot.
- **Automated verification:** complete for the revised contract.
- **Target validation:** the earlier plan-shaped contract failed 20/20 measured cases; fresh warm simulator qualification is still required for this revision.
- **Release readiness:** unchanged.

## 1. Decision

Chromie's Fast Planner may terminate complete, simple multi-goal turns directly,
but the planner model remains the sole semantic author of the Fast plan.

For every Fast Planner request containing more than one authoritative Goal ID,
the model must author:

- top-level disposition, coverage, confidence, summary, response text, and escalation reason;
- every executable step, including `step_id`, exact catalog `skill_id`, arguments,
  timing, `source_goal_ids`, and rationale;
- one outcome for every authoritative Goal ID;
- every outcome disposition, coverage, response, unresolved need, step link,
  satisfaction judgment, and rationale;
- aggregate prospective goal satisfaction;
- plan relation and confirmation requirement.

The host adds only canonical envelope identity:

- `plan_id`;
- `planner_tier=fast`;
- `schema_version`;
- authoritative top-level `goal_ids` supplied by Goal Association.

The host validates the model output and converts the goal-keyed outcome map into
the CanonicalPlan list representation. It does **not** choose a skill, infer
arguments from words, generate step IDs, assign step ownership, derive aggregate
disposition, or manufacture satisfaction judgments.

A normal semantic escalation is a model-authored Fast plan with:

- `disposition=escalate`;
- `coverage=partial|uncertain`;
- zero steps;
- one `escalate` outcome for every authoritative goal;
- per-goal unresolved reasons and non-exact satisfaction;
- a non-empty top-level escalation reason.

A schema or semantic contract failure after one bounded same-tier repair remains
a technical failure and stays visible even when Deep Planner recovers the turn.

## 2. Why the previous repair was rejected

The first post-benchmark repair replaced a plan-shaped model DTO with a
per-goal decision map and a host decision compiler. It did not contain phrase
branches such as `if "blink"`, but it still crossed Chromie's semantic-authority
boundary because the host derived:

- step IDs;
- exact step ownership;
- CanonicalPlan outcomes;
- top-level disposition and coverage;
- exact prospective satisfaction.

That design could be described as mechanical compilation, but it was not the
architecture this project requires. Planner models own semantic dispositions,
step ownership, response content, and satisfaction judgments. The compiler was
therefore removed.

## 3. Evidence and earliest wrong boundary

The July 17, 2026 operator-supplied simulator run passed all four final
`multi_goal_daily_life` cases through Deep Planner recovery. Goal Association,
Deep Planner, Response Composer, the trusted runtime adapter, Skill Runtime,
TTS scheduling, Soridormi execution, and safe-idle closure worked.

The first Fast-terminal implementation was then measured over five warm runs,
20 cases total:

- 20/20 Fast paths were `contract_failure`;
- 20/20 invoked Deep Planner;
- median Fast Planner time was about 3.39 seconds;
- median cognitive runtime was 22.87 seconds;
- the retained baseline was 23.79 seconds;
- measured improvement was 3.9 percent instead of the required 35 percent.

The failure was not a timeout or GPU-capacity problem. The model-facing JSON
Schema allowed terminal objects with missing or incomplete nested fields that
the deterministic validator necessarily rejected. Mocked tests supplied ideal
complete objects and did not reproduce that live decoder gap.

The earliest wrong boundary is therefore the Fast Planner model-facing contract
and its decoder/validator alignment. It is not Router, Soridormi, Skill Runtime,
or provider execution.

## 4. Goals and non-goals

### 4.1 Goals

- Make simple common-catalog multi-goal planning a real Fast terminal path.
- Keep the LLM as semantic plan author.
- Preserve exact per-goal accounting and exact model-authored step ownership.
- Permit simple execute, respond, and execute-plus-respond mixed plans.
- Make semantic escalation valid without turning it into contract failure.
- Preserve one bounded fresh-object repair for malformed output.
- Distinguish terminal, semantic escalation, repair, and technical failure.
- Reduce median cognitive latency by at least 35 percent against the retained
  23.79-second baseline.

### 4.2 Non-goals

- Do not add keyword branches, phrase tables, intent-to-action dictionaries, or
  case-specific plans.
- Do not let the host select actions from user wording.
- Do not let Fast Planner execute, authorize, or commit effects.
- Do not expose rare, locked, unavailable, or full-registry-only capabilities to
  the Fast terminal surface.
- Do not remove Deep Planner or weaken one-way escalation.
- Do not weaken confirmation, provider validation, resource validation,
  idempotency, cancellation, interruption, evidence, or safe-idle boundaries.
- Do not use `chromie.speak` as a planner step.
- Do not claim microphone, speaker, hardware, or release evidence from text-only
  simulator qualification.

## 5. Model-facing contract

The decoder-facing schema is `FastPlannerMultiGoalPlanOutput`. It remains flat
at the top level to avoid the deployed decoder's earlier top-level union issue,
but every semantic plan field is model-authored and decoder-required.

A representative mixed plan has this shape:

```json
{
  "disposition": "mixed",
  "coverage": "complete",
  "confidence": 0.98,
  "goal_summary": "Perform the physical goal and answer the conversational goal.",
  "response_text": "A short model-authored answer.",
  "steps": [
    {
      "step_id": "physical-step",
      "skill_id": "catalog.skill_id",
      "args": {"count": 2},
      "timing": "sequential",
      "source_goal_ids": ["goal-action"],
      "reason_summary": "Execute the physical goal exactly."
    }
  ],
  "escalation_reason": "",
  "unresolved": [],
  "parameter_resolutions": [],
  "goal_outcomes": {
    "goal-action": {
      "disposition": "execute",
      "coverage": "complete",
      "response_text": "",
      "unresolved": [],
      "step_ids": ["physical-step"],
      "satisfaction": {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": ["goal-action"],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": "The step fully plans this goal."
      },
      "rationale": "The physical step owns this goal."
    },
    "goal-answer": {
      "disposition": "respond",
      "coverage": "complete",
      "response_text": "A short model-authored answer.",
      "unresolved": [],
      "step_ids": [],
      "satisfaction": {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": ["goal-answer"],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": "The response fully answers this goal."
      },
      "rationale": "Answer the conversational goal directly."
    }
  },
  "goal_satisfaction": {
    "score": 1.0,
    "status": "exact",
    "satisfied_goal_ids": ["goal-action", "goal-answer"],
    "unmet_goal_ids": [],
    "unmet_requirements": [],
    "rationale": "Every goal is fully planned."
  },
  "plan_relation": "exact",
  "user_confirmation_required": false
}
```

No production code interprets the words in the user turn to create this object.
The model selects from the dynamic executable catalog and returns the plan.

## 6. Decoder-compatible schema strategy

The schema closes the live decoder gap without transferring semantic authority
to the host:

1. Every top-level plan field is required.
2. `goal_outcomes` is required.
3. Every authoritative Goal ID is required inside `goal_outcomes`.
4. Additional Goal IDs are forbidden.
5. Every outcome field is required.
6. Every satisfaction field is required.
7. Every step field is required, including non-empty model-authored `step_id`,
   timing, ownership, and rationale.
8. Skill IDs are constrained to the exact executable common catalog.
9. Goal references are constrained to the exact authoritative Goal IDs.
10. Per-goal dispositions are limited to `execute`, `respond`, or `escalate`.
11. Cross-field semantic invariants are validated after decoding.
12. One fresh schema-constrained repair is permitted; the host never fills a
    missing semantic field.

The schema contains no user-utterance examples that act as dispatch rules. The
capability catalog and canonical goals are dynamic request inputs.

## 7. Semantic invariants

### 7.1 Terminal plan

- Outcomes cover every authoritative goal exactly once.
- Every execute outcome references at least one real model-authored step.
- Every respond outcome has non-empty response text and no step IDs.
- Every step's `source_goal_ids` exactly match the execute outcomes that
  reference it.
- Every executable step is referenced by at least one execute outcome.
- Aggregate disposition exactly matches outcome dispositions.
- Aggregate and per-goal satisfaction are exact for terminal Fast plans.
- `chromie.speak` and other response transport are not planner leaves.

### 7.2 Semantic escalation

- All per-goal outcomes are `escalate`; escalation cannot be mixed with execute
  or respond outcomes.
- Coverage is partial or uncertain.
- Steps are empty.
- Every goal has a model-authored unresolved reason or rationale.
- Aggregate and per-goal satisfaction are non-exact.
- The top-level escalation reason is non-empty.

### 7.3 Host responsibilities

The host may:

- add canonical envelope identity;
- verify schema and semantic invariants;
- verify catalog membership and arguments;
- apply confidence, confirmation, safety, provider, and runtime gates;
- fail closed or invoke Deep Planner with explicit reason.

The host may not:

- choose a skill from user words;
- generate or repair plan steps locally;
- generate step IDs for multi-goal Fast output;
- assign goal ownership;
- convert a physical goal into a response or vice versa;
- derive model satisfaction or aggregate disposition.

## 8. Proof against phrase-to-action hardcoding

The focused regression suite includes a test that submits the **same user text
and the same authoritative Goal IDs** twice while changing only the mocked LLM
output. The two resulting CanonicalPlans preserve the different model-authored
skills, arguments, step IDs, and ownership. This proves the host does not map the
utterance to a fixed action plan.

A second regression supplies a missing multi-goal `step_id` with contract repair
disabled. The host fails closed instead of generating an ID. This protects the
model-authored plan boundary.

Source audit for the Fast multi-goal path must also remain free of:

- checks for words such as action names or conversational topics;
- case IDs;
- fixed capability selection by utterance;
- hardcoded production plans.

Concrete action names are permitted in tests and capability manifests only as
fixtures or catalog data.

## 9. Validation, repair, and escalation flow

```text
Fast model generation
  -> FastPlannerMultiGoalPlanOutput decoder schema
  -> complete non-short-circuit diagnostics
  -> at most one fresh schema-constrained model repair
  -> shared semantic plan validation
  -> host adds identity-only CanonicalPlan envelope
  -> shared CanonicalPlan validation
  -> valid Fast terminal plan
       or valid Fast semantic escalation
       or visible technical contract failure
  -> Deep Planner only when escalation or technical failure requires it
```

Malformed Fast semantics are not copied into Deep Planner as an authoritative
plan. The original user turn, Goal Association output, and capability catalog
remain available because they belong to the same goal-driven semantic authority.

## 10. Observability

Each retained turn should record:

- Fast path classification: terminal, semantic escalation, repaired terminal,
  repaired escalation, or contract failure;
- whether Deep Planner ran and why;
- terminal planner tier;
- authoritative goal count;
- outcome count;
- executable step count;
- contract repair attempt and result;
- Fast, Deep, Response Composer, cognitive total, and end-to-end timings.

A successful Deep recovery must not erase a Fast contract failure.

## 11. Implementation map

| Component | Responsibility |
|---|---|
| `agent/app/planner_contract.py` | Build the decoder-tight model-authored plan schema, validate exact goal coverage and cross-references, and materialize only the goal-keyed map into the CanonicalPlan list form. |
| `agent/app/fast_planner.py` | Select the multi-goal plan schema, prompt the model as semantic author, add identity-only envelope fields, retain fresh-object repair, and classify terminal/escalation/failure paths. |
| `shared/chromie_contracts/plan.py` | Represent model-authored Fast per-goal escalation outcomes without forcing the host to discard per-goal semantics. |
| `orchestrator/runtime/cognitive_runtime.py` | Distinguish semantic escalation from technical failure, record Deep invocation reason, and prevent partial execution. |
| `agent/app/response_composer.py` | Keep pending-action speech prospective and reject unsupported stage-direction completion claims. |
| Tests and general-ability acceptance | Prove semantic authority, exact ownership, Fast terminal bypass, visible recovery, truthful speech, execution, and latency. |

## 12. Automated evidence

For this revision:

- focused Fast Planner tests pass, including same-text/different-model-plan and
  no-host-step-ID regressions;
- 121 wider cognitive, contract, response, and semantic-authority tests pass,
  plus 13 retained subtests;
- deterministic `multi_goal_daily_life` Level A acceptance passes 8/8;
- the full repository suite passes 1,032 main tests and 20 legacy Agent tests;
- documentation governance passes across 65 Markdown files;
- Python compilation and diff checks pass.

This is deterministic repository evidence. It does not prove the deployed Fast
model now satisfies the contract. Fresh supervised warm simulator runs remain
required.

## 13. Acceptance matrix

### 13.1 Fast terminal cases

| User turn | Expected Fast result | Deep Planner |
|---|---|---|
| Look at me for two seconds, then blink twice. | `execute`, two complete outcomes, two model-authored owned steps | Not invoked |
| Nod twice, then blink once. | `execute`, two complete outcomes, two model-authored owned steps | Not invoked |
| Walk forward for one second, then blink twice. | `execute`, two complete outcomes, two model-authored owned steps | Not invoked |
| Blink twice and tell me a short joke. | `mixed`, one execute outcome, one respond outcome, one model-authored step | Not invoked |

For every retained terminal case:

- `planner_tier=fast`;
- Fast path is terminal;
- Deep Planner is not invoked;
- no Fast contract failure is hidden;
- every step ID and ownership relation originates in model output;
- skills and arguments match the request and catalog;
- speech covers every Goal ID without claiming pending physical completion;
- Skill Runtime and Soridormi complete in `sim` mode;
- post-execution status is standing and safe idle.

### 13.2 Semantic escalation cases

Retain cases where the common Fast context is insufficient, including rare or
locked capabilities, unsupported goals, clarification, material alternatives,
resource-sensitive concurrency, uncertain parameters, or missing trusted state.

Expected result:

- model-authored `disposition=escalate`;
- `coverage=partial|uncertain`;
- `steps=[]`;
- one `escalate` outcome per authoritative goal;
- non-exact model-authored satisfaction;
- non-empty specific escalation reason;
- no contract repair and no contract-failure diagnostic;
- Deep Planner invoked with reason `semantic_escalation`.

### 13.3 Technical failure case

Inject invalid output twice and prove:

- one repair attempt occurs;
- Fast result is classified as `contract_failure`;
- the host does not generate missing semantic fields;
- no partial step is committed;
- Deep Planner receives authoritative goals and catalog, not malformed Fast
  semantics;
- successful Deep recovery does not erase the Fast failure diagnostic.

## 14. Required commands

```bash
PYTHONPATH=agent:. python -m unittest -v \
  tests.test_fast_planner_pr3 \
  tests.test_cognitive_runtime_pr7 \
  tests.test_cognitive_runtime_acceptance_pr7 \
  tests.test_response_composer_pr6 \
  tests.test_response_plan_claims

python scripts/general_ability_acceptance.py \
  --mode level-a \
  --ability-class multi_goal_daily_life \
  --no-write

python scripts/check_docs.py
./scripts/run_tests.sh
```

Supervised simulator qualification:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --ability-class multi_goal_daily_life \
  --goal-driven-runtime apply \
  --execute \
  --router-url http://127.0.0.1:8091 \
  --agent-url http://127.0.0.1:8092 \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --evidence-dir .chromie/acceptance/gpu-live/multi-goal-fast-model-plan \
  --json
```

Retain at least three consecutive warm runs. The target median cognitive runtime
is at most 15.46 seconds, corresponding to at least 35 percent improvement over
the retained 23.79-second baseline.

## 15. Exit criteria

### Implementation

- The LLM authors the complete Fast multi-goal semantic plan.
- The host adds only canonical identity and performs validation/gating.
- No utterance-specific production rule chooses actions.
- Simple execute, respond, and mixed plans can terminate at Fast Planner.
- Semantic escalation is valid and distinct from contract failure.

### Automated verification

- Focused planner and anti-hardcoding regressions pass.
- Wider cognitive and semantic-authority suites pass.
- Level A `multi_goal_daily_life` passes 8/8.
- Full repository and documentation checks pass.

### Target validation

- Three consecutive warm live-text simulator runs satisfy the Fast terminal
  matrix.
- No retained terminal-simple case invokes Deep Planner.
- No retained case hides a Fast contract failure.
- Soridormi execution and safe-idle evidence remain valid.
- Median cognitive runtime is at most 15.46 seconds.

### Release readiness

This work alone does not close release readiness. Endpoint-reported Soridormi
revision identity, source-bound images/models, immutable release inputs, and
separately claimed audio or physical-hardware evidence remain governed by
`STATUS.md` and `RELEASE.md`.
