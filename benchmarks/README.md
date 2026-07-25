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

## Phase 3 module and integration runners

`runners/` executes normalized scenarios through an explicit executor boundary.
It does not import production services or infer expected behavior from user text.
Two modes are available:

- `replay`: evaluate retained observations deterministically;
- `live_model`: invoke an explicit adapter command over JSON stdin/stdout.

Machine evaluation is intentionally limited to declared boundaries: reported
invariants, explicit `primary_task_passed`, and exact forbidden-behavior labels.
Naturalness, empathy, style fit, and other semantic dimensions are returned as
`review` when no reviewed evaluator supplies a result. Missing required invariant
evidence fails closed.

Run a module cohort from the generated inventory:

```bash
python -m benchmarks.modules.run \
  --inventory benchmarks/manifests/existing_scenarios.json \
  --mode replay \
  --replay-file /path/to/replay-observations.json \
  --output benchmarks/reports/module-replay.json
```

Run an integration cohort against an explicitly configured adapter:

```bash
python -m benchmarks.integration.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --mode live_model \
  --command "python scripts/my_benchmark_adapter.py" \
  --model local-model-name \
  --prompt-revision prompt-revision-id \
  --output benchmarks/reports/integration-live-model.json
```

The adapter receives one JSON request on stdin containing `scenario` and `run`,
and returns one observation object on stdout. This boundary allows later Router,
Planner, Composer, and deployed-runtime adapters without coupling benchmark code
to one backend or adding benchmark-specific production branches.

## Phase 4 runtime component adapters

`runtime_adapters/` connects the generic `live_model` runner to real Chromie
component boundaries without importing benchmark policy into production code.
Supported component profiles are:

- `cognitive_gateway`;
- `planner`;
- `response_composer`;
- `mind_profile`;
- `capability_projection`;
- `social_attention`.

Each profile supports exactly one explicitly configured transport:

- an HTTP JSON endpoint through its `CHROMIE_BENCHMARK_*_URL` variable; or
- a Python callable using `module.path:function` through its
  `CHROMIE_BENCHMARK_*_CALLABLE` variable.

No deployment URL, port, backend identity, model, or prompt revision is embedded
in the manifest. The component receives the full normalized scenario and run
profile and must return a Benchmark execution observation. The adapter does not
infer expected behavior from user text and does not translate phrases into
skills.

Example using a deployed Cognitive Gateway adapter endpoint:

```bash
export CHROMIE_BENCHMARK_COGNITIVE_GATEWAY_URL=http://127.0.0.1:8091/benchmark/cognitive-gateway
python -m benchmarks.modules.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --mode live_model \
  --command "python scripts/benchmark_runtime_adapter.py --component cognitive_gateway" \
  --model local-gateway-model \
  --prompt-revision cognitive-gateway-contract-v1 \
  --output benchmarks/reports/cognitive-gateway-live.json
```

Example using an in-process test harness callable:

```bash
export CHROMIE_BENCHMARK_SOCIAL_ATTENTION_CALLABLE=\
my_harness.social_attention:invoke
python scripts/benchmark_runtime_adapter.py --component social_attention
```

The callable or HTTP endpoint is an explicit test harness boundary. Production
modules remain unaware of scenario IDs and benchmark execution.


## Cognitive architecture terminology

The current ingress architecture is the **Cognitive Gateway**, which owns only
input normalization, protective reflex, attention review, context assembly, and
turn admission. Goal interpretation, planning, capability selection, and response
composition remain downstream in the Goal-Driven Cognitive Core.

The legacy `scenarios/goal_interpretation/` and `scenarios/cognitive_core_dialogue/` paths are retained
for source compatibility and historical comparison. Inventory classifies them as
`goal_interpretation` and `cognitive_core_dialogue` datasets; their directory names define
the current architecture. New benchmark component profiles must not reintroduce a
generic first-class `router` boundary.
