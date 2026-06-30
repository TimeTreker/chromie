# Behavior Scenario Fixtures

This directory stores one frozen behavior scenario per JSON file. The files are
Level A regression fixtures: they are deterministic, dependency-light, and do
not prove GPU, microphone, speaker, simulator, or robot behavior.

Run them with:

```bash
python scripts/scenario_runner.py --suite router --suite interaction --suite dialogue
```

Use `--baseline path/to/summary.json` to compare a new run with a previous
report and list regressions, improvements, new cases, and removed cases.

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
  router/       Router module scenarios
  interaction/  InteractionRuntime scenarios
  dialogue/     Multi-turn InteractionRuntime conversation scenarios
  templates/    Authoring templates, not executed as scenarios
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
`post_history_contains`, `post_session_memory_contains`, and
`current_task_context_contains`.

The committed dialogue suite includes 300 real-world conversation scenarios
that score social recall, preference memory, clarification, safe refusal,
tool/perception honesty, confirmation-gated movement, multilingual requests,
and low-level runtime boundaries. The `batch2_*` files are generated from
reviewable deterministic templates:

```bash
python scripts/generate_dialogue_scenario_batch.py --target-count 300
```

LLMs may help author new candidate scenarios, but committed scenario files must
contain deterministic expectations. Normal regression runs must not depend on
an LLM to decide whether the robot behaved correctly.

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
