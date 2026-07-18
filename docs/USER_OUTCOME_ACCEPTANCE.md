# User-Outcome Acceptance Framework

## Status

Implemented with Level A automated verification. Live GPU, simulator, audio, and
hardware qualification remain separate evidence steps.

## Purpose

Chromie's primary end-to-end acceptance gate evaluates the outcome visible to
the user rather than binding the test to today's Router, Goal Association, Fast
Planner, Deep Planner, or Response Composer implementation.

A case does not pass merely because a final service returns `ok=true`. It must
prove the requested observable behavior, truthful speech, complete LLM calls,
execution receipts, and final safety state.

## Assertion scopes

`scripts/general_ability_acceptance.py` supports two scopes:

- `user-outcome` is the default release-behavior scope. Internal route and
  planner-path mismatches are retained as diagnostics but do not fail an
  otherwise correct user outcome.
- `full` is an implementation qualification scope. It additionally enforces
  expected route, terminal planner tier, Fast Planner path, Deep Planner use,
  and contract-failure expectations.

Use `user-outcome` while cognitive internals are evolving. Use `full` only for
an explicit component claim, such as qualifying a Fast Planner optimization.

## Stable observations

User-visible effects are normalized into stable observations. Examples:

```json
{
  "type": "social_attention.blink",
  "domain": "social_attention",
  "status": "completed",
  "interaction_role": "explicit_user_goal",
  "args": {"count": 2}
}
```

```json
{
  "type": "speech.output",
  "domain": "speech",
  "status": "completed"
}
```

The mapping in `scenarios/observable_behaviors.json` is a test oracle. Production
planning never reads it. It converts runtime receipts into a vocabulary that
survives capability renames or implementation changes. Tests may still use
exact skill IDs under `full` scope when the skill implementation itself is the
subject of qualification.

A case may declare:

- `expected_observations`;
- `expected_observation_sequence`;
- occurrence bounds;
- required or forbidden speech;
- final safe-idle and execution evidence through the existing live runner.

## LLM integrity is a hard gate

Fallback recovery cannot hide an incomplete LLM call. A case fails when any
critical stage records:

- input or prompt truncation;
- output truncation or `finish_reason=length`;
- incomplete stream termination;
- incomplete structured output;
- request timeout or deadline exhaustion.

These failures are distinct from ordinary semantic or contract diagnostics. A
schema-valid but semantically wrong model answer may be recovered and diagnosed;
a truncated or timed-out call is always incomplete evidence and therefore
fails the end-to-end case.

The acceptance summary stores:

```json
{
  "user_outcome": {
    "assertion_scope": "user-outcome",
    "ok": true,
    "observations": [],
    "llm_integrity": {
      "ok": true,
      "violations": []
    },
    "internal_diagnostics": []
  }
}
```

## Qualification budgets

The architecture-validation profile deliberately uses long budgets so the first
question is whether the model and architecture can complete correctly:

- 120 seconds for critical Agent model stages;
- 150 seconds for corresponding host waits;
- 600 seconds for the cognitive pipeline;
- 1200 seconds for the outer live case;
- 120 seconds for supervised skill execution.

These are qualification budgets, not production latency targets. Once repeated
correctness is retained, latency can be optimized under a separate performance
qualification without weakening the integrity gate.

## Example

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --ability-class multi_goal_daily_life \
  --goal-driven-runtime apply \
  --assertion-scope user-outcome \
  --execute \
  --router-url http://127.0.0.1:8091 \
  --agent-url http://127.0.0.1:8092 \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --evidence-dir .chromie/acceptance/user-outcome \
  --json
```

A component-specific qualification can use `--assertion-scope full` with the
same scenarios.

## Governance

The main behavior report should include both deterministic regression and
repeated live evidence. Do not summarize quality only as a total unit-test
count. Report user-outcome accuracy, integrity-failure rate, unwanted-action
rate, goal omission rate, median and p95 latency, and any component fallback
rate relevant to the claim.
