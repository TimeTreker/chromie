# Fast Planner Multi-Goal Contract Path

Status: Implemented with automated evidence; live Fast-terminal qualification open
Decision date: 2026-07-17
Scope: Goal-driven Fast Planner model DTO, validation, escalation, observability,
response-claim discipline, rollout, and acceptance

- **Implementation:** complete in the repository snapshot
- **Automated verification:** complete at Level A
- **Target validation:** prior Deep-recovery diagnostic baseline retained; Fast-terminal
  warm simulator qualification open
- **Release readiness:** unchanged

## 1. Decision

Chromie's Fast Planner will support complete, simple multi-goal turns directly
instead of relying on a model-contract failure followed by Deep Planner
recovery.

For every Fast Planner request containing more than one authoritative Goal ID,
the flat model-facing DTO must always include `goal_outcomes`. The field has two
legal meanings:

1. **Terminal fast plan:** `goal_outcomes` is a complete object keyed exactly
   once by every authoritative Goal ID.
2. **Semantic escalation:** `goal_outcomes` is the empty object, `steps` is
   empty, coverage is `partial` or `uncertain`, and `escalation_reason` is
   non-empty.

The Fast Planner may return `mixed` when all independent responsibilities are
simple, fully covered, and limited to common unlocked capabilities plus direct
conversational responses. A conversational goal is represented by a `respond`
outcome and `response_text`; it is never represented by `chromie.speak` or a
substitute body gesture.

A normal semantic escalation is not a contract error. A schema or semantic
contract failure after one bounded same-tier repair remains a technical failure
and must stay visible in diagnostics even when Deep Planner recovers the turn.

## 2. Evidence and earliest wrong boundary

The July 17, 2026 operator-supplied live-text simulator diagnostic passed all
four `multi_goal_daily_life` cases at the final interaction boundary. Goal
Association, Deep Planner, Response Composer, the trusted runtime adapter,
Skill Runtime, TTS scheduling, Soridormi execution, and safe-idle closure all
worked.

The Fast Planner did not successfully produce one valid multi-goal terminal or
semantic-escalation contract in those four cases:

- initial outputs often contained correct steps and ownership but omitted the
  entire `goal_outcomes` field;
- the repair attempt often converted physical goals into `respond` outcomes,
  removed all executable steps, or otherwise produced another invalid object;
- Deep Planner then recovered the request, adding roughly ten to eleven seconds
  of avoidable cognitive latency per case.

The earliest wrong boundary is therefore the Fast Planner model-facing contract
and its prompt/validation interaction. It is not a Router, Soridormi, provider,
Skill Runtime, or timeout defect.

## 3. Goals and non-goals

### 3.1 Goals

- Make simple common-catalog multi-goal planning a real Fast Planner terminal
  path.
- Preserve exact per-goal accounting and step ownership.
- Permit simple `execute + respond` plans without requiring Deep Planner.
- Make semantic escalation a valid first-class output rather than a validation
  accident.
- Preserve one bounded repair for genuinely malformed model output.
- Distinguish semantic escalation, repaired output, and technical contract
  failure in retained evidence.
- Reduce median cognitive-runtime latency for the retained simple multi-goal
  matrix by at least 35 percent against the July 17 baseline.

### 3.2 Non-goals

- Do not create a second semantic authority.
- Do not let Fast Planner execute, authorize, or commit side effects.
- Do not add action-name keyword branches, phrase tables, or hardcoded
  case-specific plans.
- Do not expose rare, safety-locked, unavailable, or full-registry-only skills
  to the Fast Planner terminal surface.
- Do not remove Deep Planner or its one-way escalation role.
- Do not weaken confirmation, provider validation, resource validation,
  idempotency, interruption, cancellation, evidence, or safe-idle boundaries.
- Do not use `chromie.speak` as a planner leaf.
- Do not claim microphone, speaker, physical-hardware, or release evidence from
  simulator text runs.

## 4. Model-facing contract

The model-facing DTO remains flat. Host-owned fields such as `plan_id`,
`planner_tier`, `schema_version`, and authoritative top-level Goal IDs remain
outside model authority.

For a multi-goal Fast Planner request, the model DTO has this conceptual shape:

```json
{
  "disposition": "respond|execute|mixed|escalate",
  "coverage": "complete|partial|uncertain",
  "confidence": 0.0,
  "response_text": "",
  "steps": [],
  "goal_outcomes": {},
  "goal_satisfaction": null,
  "escalation_reason": "",
  "plan_relation": "exact",
  "user_confirmation_required": false
}
```

`steps`, `goal_outcomes`, and `goal_satisfaction` are always present at the
multi-goal decoder boundary. Their legal content depends on `disposition`.

### 4.1 Terminal execute

A terminal `execute` result requires:

- `coverage=complete`;
- confidence at or above the configured Fast Planner threshold;
- one complete `goal_outcomes` entry for every authoritative Goal ID;
- every per-goal disposition equal to `execute`;
- one or more executable steps;
- every step using an exact common unlocked capability ID;
- every step carrying non-empty `source_goal_ids`;
- every execute outcome carrying non-empty `step_ids`;
- exact consistency between outcome `step_ids` and step ownership;
- non-null aggregate and per-goal prospective satisfaction.

### 4.2 Terminal respond

A terminal `respond` result requires:

- `coverage=complete`;
- confidence at or above threshold;
- a complete per-goal outcome map;
- every per-goal disposition equal to `respond`;
- non-empty per-goal `response_text`;
- non-empty top-level `response_text` suitable for Response Composer context;
- zero executable steps;
- no response transport skill in the plan;
- non-null aggregate and per-goal prospective satisfaction.

### 4.3 Terminal mixed

A terminal `mixed` result is legal only when all goals are completely covered
and each goal is independently simple. Fast terminal mixed output is limited to
per-goal `execute` and `respond` dispositions.

It requires:

- at least one `execute` goal and at least one `respond` goal;
- a complete exact outcome map;
- one or more common unlocked executable steps;
- no executable step for a `respond` goal;
- non-empty response text for every `respond` goal;
- exact step ownership for every `execute` goal;
- non-null aggregate and per-goal prospective satisfaction.

If any goal requires clarification, full-registry retrieval, an unavailable or
refused judgment, a material alternative, safety-sensitive reasoning, or a
capability outside the common unlocked catalog, the Fast Planner must escalate.

### 4.4 Semantic escalation

A legal semantic escalation requires:

```json
{
  "disposition": "escalate",
  "coverage": "partial",
  "steps": [],
  "goal_outcomes": {},
  "goal_satisfaction": null,
  "escalation_reason": "Specific reason Deep Planner is required"
}
```

`coverage=uncertain` is also legal. An escalation must not contain executable
steps, partial goal outcomes, completion claims, fabricated unavailable
judgments, or substitute capabilities.

### 4.5 Top-level disposition rule

For a terminal result:

- all per-goal outcomes `execute` -> top-level `execute`;
- all per-goal outcomes `respond` -> top-level `respond`;
- a mixture of `execute` and `respond` -> top-level `mixed`.

For escalation, `goal_outcomes` is empty and top-level disposition is
`escalate`.

## 5. Decoder-compatible schema strategy

The deployed structured decoder has previously mishandled a top-level `oneOf`
by selecting a branch without applying surrounding requirements. The Fast
Planner multi-goal contract must therefore remain one flat schema rather than a
top-level union.

The schema builder should implement these rules:

1. Add `goal_outcomes` to the top-level `required` list for multi-goal Fast
   requests.
2. Constrain outcome property names to the authoritative Goal IDs and reject
   additional properties.
3. Permit the outcome object to contain either zero properties or up to the
   exact authoritative goal count at the decoder layer.
4. Do not mark every inner Goal ID as JSON-Schema-required for Fast Planner,
   because a valid escalation uses `{}`.
5. Continue to require every inner Goal ID for multi-goal Deep Planner output.
6. Let deterministic cross-field validation enforce the only two legal Fast
   shapes: empty escalation or complete terminal map.
7. Continue to constrain step skills to the common unlocked catalog and
   `source_goal_ids` to authoritative IDs.

This avoids a fragile union while still preventing the model from omitting the
entire field.

## 6. Validation, repair, and escalation flow

```text
Fast model generation
  -> decoder schema
  -> PlannerModelOutput validation
  -> complete non-short-circuit diagnostics
  -> at most one fresh schema-constrained repair
  -> valid terminal plan
       or valid semantic escalation
       or visible technical contract failure
  -> Deep Planner only when escalation or failure requires it
```

Rules:

- Repair regenerates a fresh object from the authoritative turn, goals,
  catalog, and complete diagnostics. It does not splice the invalid JSON.
- A valid semantic escalation sets normal Fast Planner status to `escalate` and
  must not appear as `structured_output_validation` in stage diagnostics.
- A failed contract repair may still hand the original authoritative goals to
  Deep Planner because both tiers are inside the same semantic authority. It
  must be labelled as technical recovery, not normal semantic escalation.
- Deep Planner never depends on malformed Fast Planner JSON for semantic truth.
- No Fast Planner step may be committed before the terminal plan has passed the
  shared deterministic validator.

## 7. Response Composer claim discipline

Fast terminal mixed planning does not transfer speech ownership away from
Response Composer.

For a plan such as blink plus joke, this is a valid planner shape:

```json
{
  "disposition": "mixed",
  "coverage": "complete",
  "confidence": 0.98,
  "steps": [
    {
      "step_id": "step_blink",
      "skill_id": "soridormi.blink_eyes",
      "args": {"count": 2},
      "source_goal_ids": ["goal_blink"]
    }
  ],
  "goal_outcomes": {
    "goal_blink": {
      "disposition": "execute",
      "coverage": "complete",
      "step_ids": ["step_blink"],
      "satisfaction": {"score": 1.0, "status": "exact"}
    },
    "goal_joke": {
      "disposition": "respond",
      "coverage": "complete",
      "response_text": "Why did the robot cross the road? Because it was programmed by the chicken!",
      "step_ids": [],
      "satisfaction": {"score": 1.0, "status": "exact"}
    }
  },
  "goal_satisfaction": {"score": 1.0, "status": "exact"}
}
```

Before execution evidence exists, Response Composer may say:

> I’ll blink twice. Here’s a quick one: Why did the robot cross the road?

It must not say or stage-direct:

> *Blinks twice* ...

when the blink has not yet completed. Stage directions that narrate a pending
physical action count as unsupported completion claims. Exact user-requested
ordering must be represented through plan timing and response phases rather
than fabricated narration.

## 8. Observability contract

The implementation must make the Fast path measurable without parsing error
strings.

Every Fast Planner result should expose a normalized path classification:

```text
terminal
semantic_escalation
contract_failure
```

Retained metadata should include:

- whether contract repair was attempted and succeeded;
- whether Deep Planner was invoked;
- why Deep Planner was invoked: `semantic_escalation`,
  `fast_contract_failure`, or later host replan;
- terminal planner tier;
- number of authoritative goals, outcome entries, and executable steps;
- Fast and Deep stage timings;
- whether a contract failure appeared in stage diagnostics.

Required counters or equivalent trace aggregates:

- Fast terminal multi-goal count;
- Fast semantic escalation count;
- Fast contract repair count;
- Fast contract failure count;
- Deep Planner invocation count by reason;
- Deep Planner avoided count;
- Fast terminal latency and end-to-end cognitive latency.

A successful turn recovered by Deep Planner does not erase a Fast Planner
contract failure from evidence.

## 9. Implementation map

| Component | Required change |
|---|---|
| `agent/app/planner_contract.py` | Make multi-goal Fast `goal_outcomes` top-level-required; permit empty-or-complete decoder shape; retain complete Deep requirements; allow Fast terminal `mixed`; enforce empty escalation versus complete terminal map deterministically. |
| `agent/app/fast_planner.py` | Update system and user prompts to describe the two legal shapes; permit simple common-catalog `mixed`; require explicit `{}` on escalation; preserve fresh-object repair. |
| `orchestrator/runtime/cognitive_runtime.py` | Distinguish semantic escalation from Fast contract failure; record Deep invocation reason; keep one-way authority and no partial execution. |
| `agent/app/response_composer.py` | Treat physical stage directions as completion claims before evidence and keep mixed-plan wording prospective. |
| `tests/test_fast_planner_pr3.py` | Add schema, terminal execute/respond/mixed, semantic escalation, ownership, unknown-key, and repair regressions. |
| `tests/test_cognitive_runtime_pr7.py` and `tests/test_cognitive_runtime_acceptance_pr7.py` | Prove Fast terminal plans skip Deep Planner and technical failure remains visible while recovering safely. |
| `tests/test_response_composer_pr6.py` and `tests/test_response_plan_claims.py` | Reject premature stage-direction completion claims for pending physical steps. |
| `scripts/general_ability_acceptance.py` and scenario expectations | Assert terminal planner tier, Deep invocation reason, absence of Fast contract failure, correct skills, truthful speech, and latency evidence. |

## 10. Implementation evidence

The repository now implements the accepted contract path:

- the flat Fast schema requires the multi-goal `goal_outcomes` envelope while
  permitting only `{}` escalation or a deterministically complete terminal map;
- Fast Planner accepts simple common-catalog `execute`, `respond`, and
  `execute + respond` mixed plans;
- valid semantic escalation is classified separately from repaired or failed
  contracts;
- the coordinator records Fast path classification, Deep invocation reason,
  terminal planner tier, and goal/outcome/step counts;
- malformed Fast semantics are removed from Deep Planner context while the
  authoritative turn, goals, and catalog remain available;
- Response Composer rejects marked stage directions that narrate a still-pending
  physical skill as already performed;
- the live acceptance manifest now requires Fast terminal output, no Deep
  invocation, no Fast contract failure, and no pending-action stage direction
  for the four retained simple multi-goal cases.

Automated evidence from the implementation revision:

- 79 focused Fast Planner, coordinator, Response Composer, claim, and acceptance
  tests passed;
- 67 wider Deep Planner, cognitive-runtime, satisfaction, architecture-invariant,
  and semantic-authority tests passed;
- deterministic `multi_goal_daily_life` Level A acceptance passed 8/8;
- the full repository suite passed 1,054 main tests and 20 legacy Agent tests;
- documentation governance passed across 65 Markdown files.

This evidence proves the implementation and deterministic boundaries only. It
does not prove that the deployed Fast model will terminate the retained live
matrix or meet the latency target. That remains the next supervised simulator
qualification.

## 11. Implementation sequence

### Phase 1 — contract and unit evidence

- Implement the decoder-compatible schema shape.
- Add Fast terminal `mixed` to the model enum and validators.
- Add deterministic empty-escalation versus complete-terminal enforcement.
- Add focused unit tests before prompt changes.

### Phase 2 — prompt and repair behavior

- Update Fast Planner instructions with the exact two-shape contract.
- Include one concise valid execute, mixed, and escalation example.
- Keep invalid previous JSON out of the repair prompt body.
- Verify that semantic escalation succeeds without invoking contract repair.

### Phase 3 — coordinator and observability

- Record terminal, semantic escalation, and contract failure separately.
- Record Deep invocation reason.
- Prove that Fast terminal output bypasses Deep Planner and still crosses the
  same validator, Response Composer, trusted adapter, and Skill Runtime.

### Phase 4 — response claim regression

- Reject unsupported stage directions for pending physical actions.
- Retain prospective wording and exact goal coverage.

### Phase 5 — deterministic and live qualification

- Run focused tests and the full repository suite.
- Run the Level A multi-goal ability class.
- Run supervised live-text simulator qualification with repeated warm cases.
- Update `STATUS.md`, `ROADMAP.md`, `DEVELOPMENT_CHECKPOINT.md`, API/configuration
  references, and retained evidence only after implementation and validation
  exist.

## 12. Acceptance matrix

### 12.1 Fast terminal cases

| User turn | Expected Fast result | Deep Planner |
|---|---|---|
| Look at me for two seconds, then blink twice. | `execute`, two complete outcomes, two owned steps | Not invoked |
| Nod twice, then blink once. | `execute`, two complete outcomes, two owned steps | Not invoked |
| Walk forward for one second, then blink twice. | `execute`, two complete outcomes, two owned steps | Not invoked |
| Blink twice and tell me a short joke. | `mixed`, one execute outcome, one respond outcome, one blink step | Not invoked |

For all four cases:

- Fast Planner must not report `structured_output_validation`;
- contract repair should not be required in the retained warm qualification;
- the terminal plan must have `planner_tier=fast`;
- response speech must cover every Goal ID;
- no speech may claim a pending physical action already completed;
- emitted skills and arguments must match the user request;
- Skill Runtime and Soridormi must complete successfully in `sim` mode;
- post-execution status must be standing and safe idle.

### 12.2 Semantic escalation cases

Retain cases where Fast Planner must escalate cleanly:

- one goal needs a rare or safety-locked capability;
- one goal is unsupported by the common catalog;
- one goal needs clarification or material alternative reasoning;
- ordering, concurrency, or consequence cannot be decided from bounded Fast
  context;
- provider or environment state required for planning is unavailable.

Expected result:

- `disposition=escalate`;
- `coverage=partial|uncertain`;
- `steps=[]`;
- `goal_outcomes={}`;
- non-empty specific `escalation_reason`;
- no contract repair and no contract-failure diagnostic;
- Deep Planner invoked with reason `semantic_escalation`.

### 12.3 Technical failure case

Inject two invalid Fast model outputs and prove:

- one repair attempt occurs;
- Fast result is classified as `contract_failure`;
- no partial step is committed;
- Deep Planner receives the authoritative turn and goals, not malformed Fast
  semantics;
- Deep recovery, if successful, does not erase the Fast failure diagnostic.

## 13. Required commands

Focused deterministic evidence:

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
  --evidence-dir .chromie/acceptance/gpu-live/multi-goal-fast \
  --json
```

Target qualification should retain at least three consecutive warm runs. The
median cognitive-runtime latency should improve by at least 35 percent relative
to the retained July 17 diagnostic baseline while preserving execution and
safe-idle evidence.

## 14. Exit criteria

### Implementation

- The two-shape Fast multi-goal contract is implemented without a top-level
  schema union.
- Simple execute, respond, and mixed multi-goal plans can terminate at Fast
  Planner.
- Normal semantic escalation is valid and distinct from contract failure.

### Automated verification

- Focused planner, coordinator, response-claim, and full regression tests pass.
- Level A `multi_goal_daily_life` passes with explicit Fast-tier assertions.
- Documentation checks pass.

### Target validation

- Three consecutive warm live-text simulator runs satisfy the Fast terminal
  matrix.
- No retained terminal-simple case invokes Deep Planner.
- No retained case hides a Fast contract failure.
- Soridormi execution and safe-idle evidence remain valid.
- Median cognitive-runtime latency improves by at least 35 percent.

### Release readiness

This work alone does not close release readiness. Endpoint-reported Soridormi
revision identity, source-bound running images/models, immutable release inputs,
and the separately claimed audio or physical-hardware evidence remain governed
by `STATUS.md` and `RELEASE.md`.
