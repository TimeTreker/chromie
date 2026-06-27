# Behavior Scenario Fixtures

This directory stores one frozen behavior scenario per JSON file. The files are
Level A regression fixtures: they are deterministic, dependency-light, and do
not prove GPU, microphone, speaker, simulator, or robot behavior.

Run them with:

```bash
python scripts/scenario_runner.py --suite router --suite interaction
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
  templates/    Authoring templates, not executed as scenarios
```

Each file contains exactly one scenario object. The file stem must match the
scenario `id`; for example `router/normal_greeting.json` must contain
`"id": "normal_greeting"`.

LLMs may help author new candidate scenarios, but committed scenario files must
contain deterministic expectations. Normal regression runs must not depend on
an LLM to decide whether the robot behaved correctly.
