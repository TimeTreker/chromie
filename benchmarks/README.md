# Chromie Benchmark Suite

This directory contains evaluation infrastructure, not production behavior policy.
Thinking remains in the LLM. Benchmark code may discover scenarios, validate
contracts and provenance, aggregate evidence, and report coverage. It must not
add phrase tables, regular-expression intent rules, scenario-ID branches, or
fixed input-to-action mappings.

## Phase 1 layout

- `benchmark.schema.json`: versioned generated-inventory contract.
- `manifests/suites.json`: authoritative source classification and taxonomy.
- `inventory/core.py`: deterministic discovery, validation, and coverage report.
- `modules/`, `integration/`, `e2e/`, `stress/`, `regression/`, `datasets/`:
  reserved homes for later benchmark phases; existing scenarios remain in place.
- `reports/`: generated local reports. Generated JSON should not be committed
  unless a release process explicitly retains it as evidence.

## Commands

Validate the repository inventory without writing generated files:

```bash
python -m benchmarks.inventory.core --check
```

Generate the inventory and coverage report locally:

```bash
python -m benchmarks.inventory.core
```

Run focused tests:

```bash
pytest -q benchmarks/tests/test_inventory.py
```

The inventory is deterministic: source rules and paths are sorted, IDs are
stable, and output contains no timestamps. A duplicate ID, unknown taxonomy
value, missing required source, malformed JSON, or broken source reference fails
closed with exit status `2`.

## Classification policy

One source scenario appears once in the inventory and may carry multiple dataset
tags. Source files and legacy runners are not moved or replaced in Phase 1.
Language detection is descriptive metadata only. Acceptance scripts are indexed
as entrypoints until Phase 2 introduces format adapters for their internal cases.

## Phase 2 common scenario contract

`contracts/scenario.schema.json` defines the normalized scenario boundary and
`contracts/result.schema.json` defines the retained execution-result envelope.
The contract keeps deterministic invariants, acceptable semantic outcomes,
auxiliary-behavior regions, qualitative review, and distribution observations as
separate fields. It does not require one exact model response.

`adapters/legacy_json.py` normalizes maintained JSON shapes in place. It preserves
declared IDs and legacy expectations, records source provenance, and derives a
stable content ID only when the source has no ID. Adapters do not execute a
scenario and do not interpret user phrases.

After generating the Phase 1 inventory, check all JSON scenario adapters with:

```bash
python -m benchmarks.adapters.normalize --check
```

Generate a local normalized view with:

```bash
python -m benchmarks.adapters.normalize
```

Generated normalized JSON belongs under `benchmarks/reports/` and is not an
authoritative source dataset.
