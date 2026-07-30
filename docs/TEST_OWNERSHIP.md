# Behavioral, Architecture, and Artifact Test Ownership

Chromie tests are classified by the fact they own. Tests should assert the
highest-level observable contract available rather than implementation strings.

## Behavioral tests

Behavioral tests call public or deliberately testable boundaries and assert
schemas, decisions, state transitions, execution evidence, or user-visible
outcomes. They must not read Python implementation text to infer behavior.

Examples include deterministic reflex behavior, Goal Association output,
Planner prompt capture through the model-client boundary, Capability execution,
and grounded failure speech.

## Architecture policy tests

Forbidden architecture is owned by dependency-light AST or structured policy
checks, primarily `scripts/check_repository_policies.py`. Tests should exercise
the policy checker with synthetic violating trees instead of checking that one
particular source string is absent.

## Generated-artifact contract tests

Some committed scripts and generated configuration sources are themselves the
public development/deployment artifact. Literal-content tests may remain where
executing the artifact would require unavailable hardware, Docker, or process
replacement. These exceptions are listed exactly in
`config/test_source_ownership.json` with a reviewed reason.

## Enforcement

Run:

```bash
python scripts/check_test_ownership.py
```

The checker rejects an unclassified test that reads a `.py` implementation file,
invalid ownership categories, weak or unsafe registry entries, duplicate entries,
and stale approvals. It is part of `./scripts/run_tests.sh`.

The registry is not a blanket baseline. New user/runtime behavior must use
executable assertions; new forbidden architecture belongs in the repository
policy checker; only genuine generated-artifact contracts may be added to the
registry.
