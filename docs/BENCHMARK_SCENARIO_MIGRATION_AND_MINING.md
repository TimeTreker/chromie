# Benchmark Scenario Migration and Continuous Review

Status: implemented Benchmark Suite closure

## Purpose

Chromie now has one evaluation authority for maintained scenarios and one
reviewed path from runtime experience to permanent regression coverage. This
work does not change production cognition or Social Attention behavior.

## Maintained scenario authority

`benchmarks/manifests/scenario_migration_v1.json` is the authoritative source
classification. Existing deterministic files remain referenced in place so Git
history, stable scenario IDs, general-ability metadata, and retained evidence
remain comparable.

`benchmarks/manifests/suites.json` is only a compatibility redirect. It no
longer duplicates source classification.

Validate inventory and normalized parity:

```bash
python -m benchmarks.scenarios check
```

Run maintained file-backed scenarios through the Benchmark-native entrypoint:

```bash
python -m benchmarks.scenarios run --suite cognitive_core_dialogue --no-write
```

The old scenario runner, authoring script, and general-ability acceptance
command remain supported under explicit criteria-based removal schedules. They
do not form a second classification authority.

## Continuous candidate review

The experience evaluator may write immutable candidate files. A candidate is a
proposal only. It cannot become a regression, training input, Prompt update,
personality change, or Runtime policy without a separate review and promotion
operation.

The flow is:

```text
runtime episode
-> offline evaluation
-> immutable candidate
-> deterministic index and duplicate analysis
-> separate human review record bound to candidate fingerprint
-> reviewed promotion into a committed deterministic scenario
```

Index and cluster candidates:

```bash
python -m benchmarks.mining index \
  --candidate-dir .chromie/scenario_candidates \
  --output .chromie/benchmark-artifacts/candidate_catalog.json
```

Create an auditable review record:

```bash
python -m benchmarks.mining review candidate.json \
  --decision approved \
  --reviewer owner-id \
  --rationale "Reproduces the earliest wrong planning boundary." \
  --output candidate.review.json
```

Promote only the reviewed candidate:

```bash
python -m benchmarks.mining promote candidate.json \
  --review candidate.review.json \
  --id reviewed_regression_case
```

Exact committed-input duplicates are rejected. Related scenarios require an
explicit reviewer override. Promotion validates the deterministic scenario
schema but never commits files, edits Prompts, changes Runtime policy, or grants
release qualification.

## Controlled variation briefs

Language, politeness, interaction context, and failure-condition variations are
represented as authoring briefs. The tool does not mechanically translate,
paraphrase, or select expected robot actions.

```bash
python -m benchmarks.mining variations candidate.json \
  --axis language=zh-CN \
  --axis politeness=low \
  --output candidate.variations.json
```

Each brief requires human review and keeps the generated scenario empty until a
human or explicitly invoked authoring model supplies reviewed content.

## Closure guarantees

- Benchmark metadata has no Runtime policy authority.
- LLMs may propose or critique but cannot silently promote content.
- Review decisions are separate immutable records bound to candidate hashes.
- Source episode and evaluation IDs survive promotion.
- Existing evidence claims remain unchanged.
- The full repository and Benchmark checks remain deterministic without a live
  model, microphone, simulator, or physical robot.
