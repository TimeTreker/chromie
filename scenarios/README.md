# Behavior Scenario Fixtures

This directory stores one frozen behavior scenario per JSON file. The files are
Level A regression fixtures: they are deterministic, dependency-light, and do
not prove GPU, microphone, speaker, simulator, or robot behavior.

Run maintained file-backed scenarios through the Benchmark Suite entrypoint:

```bash
python -m benchmarks.scenarios check
python -m benchmarks.scenarios run --suite dialogue --no-write
```

Run behavior-quality gates through the retained general ability manifest:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
```

`scripts/scenario_runner.py` remains a compatibility entrypoint under the
criteria-based removal schedule in the Benchmark migration manifest. Neither it
nor a Level A pass alone proves natural live robot behavior.

Eligible planning/embodied pending-work regressions should assert the typed
`fast_speech` object as well as the final route: purpose, non-terminal
commitment, and `must_not_claim_completion=true`. Live-text cases can set
`require_fast_speech=true` and `expected_fast_speech_purposes`. Tool routes may
use the exact reviewed `acknowledge_and_check`/`checking_only` contract before a
result; it carries no result or completion authority. Memory routes still set
`forbid_fast_speech=true` until a commit exists. The Host's generic cache remains
a separate fallback presentation path.

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
  templates/        Authoring templates, not executed as scenarios
```

Each file contains exactly one scenario object. The file stem must match the
scenario `id`; for example `goal_interpretation/normal_greeting.json` must contain
`"id": "normal_greeting"`.

`dialogue` scenarios contain ordered turns instead of a single `input.text`.
Each turn can use `ask` plus a deterministic `stub` and `expect` block:

```json
{
  "schema_version": 1,
  "id": "walk_then_followup_status",
  "suite": "dialogue",
  "turns": [
    {
      "id": "walk_request",
      "ask": "Walk forward slowly.",
      "stub": {"route_decision": {"route": "robot_action"}},
      "expect": {"skills": ["soridormi.walk_velocity"]}
    },
    {
      "id": "followup_status",
      "ask": "Did you do that?",
      "stub": {"route_decision": {"route": "chat"}},
      "expect": {"history_contains": ["Walk forward slowly."]}
    }
  ]
}
```

Dialogue expectations can check the same speech, skill, confirmation, status,
and metadata fields as interaction scenarios. They can also check
`history_contains`, `history_any`, `session_memory_contains`,
`post_history_contains`, `post_session_memory_contains`,
`extracted_memory_contains`, `post_extracted_memory_contains`,
`memory_summary_contains`, `post_memory_summary_contains`, and
`current_task_context_contains`. Prefer the extracted-memory fields when the
scenario is proving that refined memory, not raw transcript history, survives
into the next turn.

Interaction scenarios may set `stub.host_prepare_response=true` when they need
to exercise the host `InteractionRuntimeCoordinator.prepare_response()` layer.
That path attaches static `preflight_validation` metadata without executing live
TTS, simulator, or hardware work. Expectations can use `metadata_json_contains`
and `metadata_json_forbid` for preflight diagnostics. Preflight does not create a
second proposal ledger and does not prove execution.

The committed dialogue suite includes 300+ real-world conversation scenarios
that score social recall, preference memory, clarification, safe refusal,
tool/perception honesty, confirmation-gated movement, multilingual requests,
low-level runtime boundaries, and daily-life human-like judgment around
privacy, uncertainty, nearby people, spills, calls, medicine, allergies, and
truthful correction. The `batch2_*` files are generated from reviewable
deterministic templates:

```bash
python scripts/generate_dialogue_scenario_batch.py --target-count 300
```

LLMs may help author new candidate scenarios, but committed scenario files must
contain deterministic expectations. Normal regression runs must not depend on
an LLM to decide whether the robot behaved correctly.


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
      "stage": "quick_intent",
      "content": "{not valid JSON"
    },
    {
      "stage": "quick_intent_contract_repair",
      "decision": {
        "route": "clarify",
        "intent": "ambiguous_reference",
        "confidence": 0.85
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

## General ability acceptance manifest

[`general_ability_acceptance.json`](general_ability_acceptance.json) groups
representative scenarios by the broader robot ability they protect. It is not a
scenario file itself and is not loaded by `scripts/scenario_runner.py`.

Run the manifest-level checks with:

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
