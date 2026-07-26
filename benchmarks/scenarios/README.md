# Maintained Scenario Migration

The Benchmark Suite references the existing deterministic scenario files in
place. This preserves stable IDs, Git provenance, general-ability manifests, and
historical evidence while making the Benchmark migration manifest the sole
classification authority.

Validate count and normalization parity:

```bash
python -m benchmarks.scenarios check
```

Run the maintained file-backed suites through the Benchmark entrypoint:

```bash
python -m benchmarks.scenarios run --suite dialogue --no-write
```

`scripts/scenario_runner.py`, `scripts/scenario_author.py`, and the general
ability acceptance entrypoint remain supported only under the explicit removal
gates in `benchmarks/manifests/scenario_migration_v1.json`. Their retention does
not create a second scenario classification authority.
