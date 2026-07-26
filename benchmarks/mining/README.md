# Continuous Scenario Mining and Review

Runtime episodes may produce immutable scenario candidates. Candidates are not
regression tests, prompt updates, training data, or Runtime policy. The
Benchmark mining workflow keeps four boundaries separate:

1. index and cluster candidates against committed scenarios;
2. create a separate human review record bound to the candidate fingerprint;
3. produce controlled variation authoring briefs without generating behavior
   rules or silently rewriting inputs;
4. promote only an approved, fingerprint-matched candidate into a deterministic
   scenario file.

Commands:

```bash
python -m benchmarks.mining index \
  --candidate-dir .chromie/scenario_candidates \
  --output .chromie/benchmark-artifacts/candidate_catalog.json

python -m benchmarks.mining review candidate.json \
  --decision approved --reviewer owner-id \
  --rationale "Reproduces the earliest wrong planning boundary." \
  --output candidate.review.json

python -m benchmarks.mining variations candidate.json \
  --axis language=zh-CN --axis politeness=low \
  --output candidate.variations.json

python -m benchmarks.mining promote candidate.json \
  --review candidate.review.json --id reviewed_regression_case
```

Promotion never commits changes, edits prompts, modifies personality, changes
Runtime policy, or grants release qualification. Related committed scenarios
require an explicit human override; exact input duplicates are rejected.
