# Behavior Scenario Fixtures

This directory stores one frozen behavior scenario per JSON file. The files are
Level A regression fixtures: they are deterministic, dependency-light, and do
not prove GPU, microphone, speaker, simulator, or robot behavior.

Run maintained file-backed scenarios through the Benchmark Suite entrypoint:

```bash
python -m benchmarks.scenarios check
python -m benchmarks.scenarios run --suite dialogue --no-write
```

Run behavior-quality gates through the discovered general-ability scenario library:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
```

`scripts/scenario_runner.py` remains a compatibility entrypoint under the
criteria-based removal schedule in the Benchmark migration manifest. Neither it
nor a Level A pass alone proves natural live robot behavior.

Eligible planning/embodied pending-work regressions assert the typed Fast Planner
progress Communicative Activity in `cognitive_runtime.fast_advance`. Live-text
cases can set `require_fast_communicative_act=true` together with
`expected_fast_communicative_speech_acts`, or set
`forbid_fast_communicative_act=true` when pre-effect speech is not allowed.
These assertions inspect Planner-owned semantic activity evidence rather than a
separate Goal-Interpreter speech contract.

Create and validate scenarios with:

```bash
python scripts/scenario_author.py templates
python scripts/scenario_author.py new --suite goal_interpretation --id draft_case \
  --text "Hello Chromie."
python scripts/scenario_author.py edit --suite goal_interpretation --id draft_case
python scripts/scenario_author.py validate scenarios/goal_interpretation/draft_case.json
python scripts/scenario_author.py validate-all
```

To ask an LLM for reviewed candidate scenarios, generate a constrained prompt:

```bash
python scripts/scenario_author.py prompt --suite interaction --count 20 \
  --focus "normal social requests, ambiguous movement, and discourse markers"
```

The LLM should author candidate files only. The committed JSON expectations are
the deterministic judge.

## Layout

```text
scenarios/
  goal_interpretation/  Goal Interpretation module and scripted-model recovery scenarios
  cognitive_core_dialogue/  Multi-turn Cognitive Core replay scenarios
  interaction/      InteractionRuntime scenarios
  dialogue/         Multi-turn InteractionRuntime conversation scenarios
  cognitive_runtime/ Goal-driven planning and coordinated-response scenarios
  cognitive_turn_loop/ Deterministic outcome-closure and cancellation scenarios
  general_ability/ Self-describing staged live-text scenarios
  templates/        Authoring templates, not executed as scenarios
```

Each file contains exactly one scenario object. The file stem must match the
scenario `id`; for example `goal_interpretation/normal_greeting.json` must contain
`"id": "normal_greeting"`.

The maintained scenario registry is defined by `scripts/behavior_scenarios.py`.
Historical `scenarios/dialogue/` route-decision fixtures and their generator were retired
because they encoded the removed `route`/`intent` architecture rather than the current
Responsibility → canonical Goal → Planner → Capability/Evidence contracts. Multi-turn
behavior belongs in maintained suites that exercise the current typed owners directly.


### Scripted bounded Goal Interpretation scenarios

Goal Interpretation fixtures may use `stub.llm_script` instead of one final
`stub.llm_decision`. The scenario runner then executes the real bounded
`OllamaGoalInterpreter.route()` normalization and validation transaction while
replacing only external model completions. A script contains one primary stage
and, only when that output is mechanically invalid, one DTO-repair stage:

```json
{
  "llm_script": [
    {
      "stage": "goal_interpretation",
      "content": "{not valid JSON"
    },
    {
      "stage": "goal_interpretation_contract_repair",
      "decision": {
        "confidence": 0.85,
        "responsibilities": [],
        "unresolved": ["ambiguous reference"]
      }
    }
  ]
}
```

Standalone Goal Interpretation scenarios may also set `stub.context` to replay bounded host
request context, such as `interaction_engagement`. This context is passed to
the real Goal Interpretation pipeline; it must be a JSON object and should contain only the
minimum fields needed to reproduce the boundary under test.

`cognitive_core_dialogue` scenarios run ordered Cognitive Core turns with one bounded
conversation-state snapshot. A turn may set `run_interaction=true` to pass the
final Goal Interpretation decision through the dependency-light native InteractionRuntime
and assert emitted skills and arguments. This is deterministic Level A replay,
not a live-model, microphone, simulator, or robot claim.

## General ability scenario library

There is no central general-ability index. Live scenarios are discovered under
`general_ability/<must_pass|core|challenge>/<ability-class>/`; every file owns
its stage, difficulty, ability membership, hybrid oracle, and review metadata.
Optional scenario-local `provenance` records authoring origin, batch id, and
whether the case was derived from an existing scenario. When present, the runner
validates those fields and retains them in live summaries and semantic-review
bundles; it never changes the verdict or creates a central registry.
Maintained Level-A scenarios in the deterministic suites declare their own
`general_ability.memberships`, including multi-ability membership where needed.
Counts and ability-class reports are derived from those files.

Run the directory and metadata checks with:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
```

Run the focused daily-life multi-goal Level A suite with:

```bash
python scripts/general_ability_acceptance.py \
  --mode level-a \
  --ability-class multi_goal_daily_life \
  --no-write
```

Run the focused evidence-bound cognitive turn-closure suite with:

```bash
python scripts/general_ability_acceptance.py \
  --mode level-a \
  --ability-class evidence_bound_cognitive_turn_closure \
  --no-write
```

These turn-loop cases use the real turn envelope, canonical-plan runtime
adapter, Trusted Capability Runtime cancellation path, outcome reconciler, goal-state
commit, stale-turn gate, and deterministic final-response assembly backed by scripted
providers. They are Level A synthetic integration evidence only; they do not
prove a live model, microphone, speaker, simulator, or robot run.

The retained cases cover supported sequential gestures, repeated identical
skills, body action plus conversation, body action plus clarification,
supported action plus unavailable manipulation, and three-goal
execute/respond/clarify combinations. They assert per-goal step ownership,
timing, arguments, speech coverage, and final interaction status.

With deployed Agent/Cognitive Core, Ollama, and Soridormi services, preview or execute
the live text probes through the goal-driven runtime:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --ability-class multi_goal_daily_life \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi

conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --ability-class multi_goal_daily_life \
  --goal-driven-runtime apply \
  --execute \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

The first command is live service preview evidence only. The second is MuJoCo
execution evidence only when Soridormi reports `sim`, every expected skill
completes through the trusted runtime, and the retained run ends safe-idle.
The declared Soridormi checkout is recorded for diagnostic provenance only and
does not identify the source executing behind the MCP endpoint.

Manifest live cases may contain an ordered `turns` array. Those turns run with
one bounded conversation ID and fresh per-turn SIDs, allowing the same retained
episode to test stale Goal, tool, confirmation, and dialogue-state failures.
The episode summary reports deterministic hard-gate failures, an objective
diagnostic score, and the earliest suspect boundary. A score cannot turn Goal
omission, stale provenance, unsafe execution, service failure, LLM-integrity
failure, or unsafe final state into a pass.

That runner reports the evidence level and claim scope for each run. A passing
Level A general-ability run is deterministic regression evidence only; it does
not prove live Cognitive Core/Agent services, microphone/speaker behavior, simulator
execution, or robot hardware behavior. The reconstruction plan is documented in
[General Ability Test Reconstruction](../docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md).

The planned experience loop for turning low-scoring real dialogue/task episodes
into reviewed scenario candidates is described in
[Experience Evaluation and Scenario Mining](../docs/EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

To score recorded runtime episodes and write immutable candidate scenarios for review:

```bash
python scripts/evaluate_experience_episodes.py \
  --episodes .chromie/experience/episodes.jsonl \
  --output .chromie/experience/evaluations.jsonl \
  --candidate-dir .chromie/scenario_candidates
```

Index, review, and promote candidates through the Benchmark workflow:

```bash
python -m benchmarks.mining index --candidate-dir .chromie/scenario_candidates
python -m benchmarks.mining review candidate.json --decision approved \
  --reviewer owner-id --rationale "Reviewed regression boundary." \
  --output candidate.review.json
python -m benchmarks.mining promote candidate.json \
  --review candidate.review.json --id reviewed_regression_case
```
