# Behavior Scenario Fixtures

This directory stores one frozen behavior scenario per JSON file. The files are
Level A regression fixtures: they are deterministic, dependency-light, and do
not prove GPU, microphone, speaker, simulator, or robot behavior.

Run behavior-quality gates through the general ability manifest:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
```

`scripts/scenario_runner.py` remains a low-level fixture engine for authoring
and focused debugging, but it should not be used by itself as a claim that
Chromie behaves naturally.

Create and validate scenarios with:

```bash
python scripts/scenario_author.py templates
python scripts/scenario_author.py new --suite router --id draft_case \
  --text "Hello Chromie."
python scripts/scenario_author.py edit --suite router --id draft_case
python scripts/scenario_author.py validate scenarios/router/draft_case.json
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
  router/           Router module and scripted-model recovery scenarios
  router_dialogue/  Multi-turn Router-to-Agent replay scenarios
  interaction/      InteractionRuntime scenarios
  dialogue/         Multi-turn InteractionRuntime conversation scenarios
  templates/        Authoring templates, not executed as scenarios
```

Each file contains exactly one scenario object. The file stem must match the
scenario `id`; for example `router/normal_greeting.json` must contain
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
That path attaches static preflight and `task_proposal_ledger` metadata without
executing live TTS, simulator, or hardware work. Expectations can use
`metadata_json_contains` and `metadata_json_forbid` for ledger-level evidence
such as `not_committed`, `superseded`, `chromie.speak`, or rejected
capabilities. The `look_out_warning_correction` scenario covers the correction
case where a quick window-gaze proposal for "Look out!" is superseded by
warning speech and no physical skill is emitted.

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


### Scripted Router recovery scenarios

Router fixtures may use `stub.llm_script` instead of one final
`stub.llm_decision`. The scenario runner then executes the real
`OllamaLLMRouter.route()` normalization, review, semantic-repair, and validation
pipeline while replacing only external model completions. Each scripted item
may declare the expected model stage and a compact decision:

```json
{
  "llm_script": [
    {
      "stage": "quick_intent",
      "decision": {
        "route": "chat",
        "intent": "weather_query",
        "confidence": 0.95
      }
    },
    {
      "stage": "semantic_route_repair",
      "decision": {
        "route": "robot_action",
        "intent": "capability:soridormi.walk_velocity",
        "confidence": 0.97
      }
    }
  ]
}
```

`router_dialogue` scenarios run ordered Router turns with one bounded
conversation-state snapshot. A turn may set `run_interaction=true` to pass the
final Router decision through the dependency-light native InteractionRuntime
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

That runner reports the evidence level and claim scope for each run. A passing
Level A general-ability run is deterministic regression evidence only; it does
not prove live Router/Agent services, microphone/speaker behavior, simulator
execution, or robot hardware behavior. The reconstruction plan is documented in
[General Ability Test Reconstruction](../docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md).

The planned experience loop for turning low-scoring real dialogue/task episodes
into reviewed scenario candidates is described in
[Experience Evaluation and Scenario Mining](../docs/EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

To score recorded runtime episodes and write candidate scenarios for review:

```bash
python scripts/evaluate_experience_episodes.py \
  --episodes .chromie/experience/episodes.jsonl \
  --output .chromie/experience/evaluations.jsonl \
  --candidate-dir .chromie/scenario_candidates
```
