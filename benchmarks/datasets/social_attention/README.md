# Social Attention Benchmark Dataset v1

This dataset contains 128 reviewed Social Attention benchmark cases. It is an
evaluation asset, not production behavior policy. Cases express acceptable
behavior regions, deterministic invariants, review rubrics, and distribution
observations. They never map a phrase to one required gesture.

Coverage includes greetings, daily conversation, questions, tool use, explicit
robot actions, multi-turn interaction, interruption, empathy, styles, user
preferences, repetition/cooldown, policy modes, safety/resource conflicts,
bilingual input, ASR ambiguity, and historical regressions.

Every case keeps `none` as a valid auxiliary decision. `off` and `report_only`
remain isolated from execution. Explicit actions, stop/emergency controls, user
stillness, provider contracts, and primary response latency remain hard gates.

The cases were LLM-generated and reviewed as benchmark content. They are not a
release qualification: final release decisions still require human approval and
execution evidence from the declared evidence level.

Validate without writing generated reports:

```bash
python -m benchmarks.datasets.social_attention.validate --check
```

Generate the deterministic coverage report:

```bash
python -m benchmarks.datasets.social_attention.validate
```

The generated report belongs under `benchmarks/reports/` and should only be
committed when a release process intentionally retains it as evidence.
