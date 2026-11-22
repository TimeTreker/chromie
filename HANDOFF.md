# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns current
four-axis state/open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns stable decisions.
Replace current facts; history remains in Git and [CHANGELOG](CHANGELOG.md).


## Current snapshot

- Checkout `/home/chromie/github/chromie`, feature branch
  `codex/sc-context-budget-failure-notice`, pre-delivery base `69af008ba`.
  Resume from the branch revision containing these three current-state owners.
  Main merge requires separate owner approval.
- Frozen final source SHA256 `97ea78530ef3e264ed91031a3e8054ed78e55cd5704b2c34712384cd8fe6de80`, common128 runtime identity
  `8c56160027cabde3af7828899d260fb02995129a5587faa8587d67018450e40e`. The tested dirty snapshot predates evidence bookkeeping.
  The deployed Agent package and checkout matched at
  `b390b18d3e129ade5260b90f7c3e16cfa51072ad6c01f0134fed035af2eb2d33`.
- `Gemma4 12B` revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`,
  SGLang 0.5.19 and XGrammar 0.2.1. All role models and 28 effective budget
  values matched the paired baseline. Soridormi simulator revision `a49a87f68`.
  Full image IDs, settings and startup state are in each cohort's identity files.
- Final testing restored Agent image `sha256:f9138d8641f0`
  and stopped the simulator and MCP after safe-idle checks.

## Retained evidence

- `.chromie/acceptance/optimize-fixed-model-20261121/comprehensive-review.zh.md` and `case-results.zh.md` give the
  original episode, paired and additional outcomes, earliest boundaries and
  evidence limits. `role-review.zh.md` records the eight engineering trials.
- `.chromie/acceptance/optimize-fixed-model-20261121/weather-only/` holds `evaluated-source.patch`, the component
  package digest and four cohort directories. Each retains identity, service
  start state, exits, one bundle path and final simulator state.
  Common128 recorded 111/128 automatic and 76/20/31/1 functional. Library79
  recorded 51/79 automatic and 42/17/20/0 functional. Neither qualifies.
- `original/manual-review.zh.md` and `original/episode-index.private.json`
  distinguish the UMI omission on 09 from the Planner substitution on 10.
  `full/reviewed-role-boundaries.private.json` retains primary role outputs
  for selected integrity, factual and safety failures.
- `full/raw-contract-audit.json`, `full/model-input-audit.json`,
  `full/context-component-breakdown.json` and `full/playback-receipt-audit.json`
  retain 1,007 calls and the case-linked delivery evidence. `canonical.log`,
  `level-a/summary.json` and `strict6000/summary.json` contain local gates.
- Main and old branch controls remain in
  `.chromie/acceptance/fair-main-branch-20261116/qualified-v2/`.
  The starting Host patch is frozen under
  `.chromie/acceptance/restore-baseline-20261120/reentry-once-final/`.
  `.chromie/acceptance/optimize-fixed-model-20261121/live/` holds the rejected Planner experiment, which had
  77 complete passes and used Beijing facts for a Shanghai question.

## Resume and verify

Inspect the frozen results and run the canonical checks on the checkout:

```bash
set -e
cd /home/chromie/github/chromie
proof=.chromie/acceptance/optimize-fixed-model-20261121/weather-only
cat "$proof/progress.json" "$proof/full/exits.json" "$proof/library79/exits.json"
cat "$proof/agent-source.json" "$proof/post-agent-image.txt" "$proof/original/manual-review.zh.md"
python -c 'import json,sys; print(json.load(open(sys.argv[1]))["totals"])' "$proof/full/manual-review.json"
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

For a newly authorized full replay on this diagnostic branch, the retained
driver binds the original container profile and scene, verifies the rebuilt
Agent against the checkout, checks all model and budget settings, executes
the exact original and both manifests, collects one bundle per cohort, and
restores the test environment. Start with the original Agent image running
and the qualification scene and MCP stopped. Use a fresh output directory.

```bash
set -e
cd /home/chromie/github/chromie
root=.chromie/acceptance/optimize-fixed-model-20261121
next_root="$(mktemp -d "$PWD/$root/next-XXXXXXXX")"
cp "$root/replay/qualify.py" "$root/replay/run_live.py" "$next_root/"
cp "$root/weather-only/library79-manifest.json" "$next_root/"
cp -R "$root/weather-only/library79-input" "$next_root/"
python "$next_root/qualify.py"
cat "$next_root/progress.json" "$next_root/original/exits.json" "$next_root/full/exits.json" "$next_root/library79/exits.json"
```

The common128 runner checks user outcomes and model integrity. The other 79
also enforce internal implementation-path assertions. Inspect individual
summaries, retained service logs and playback events after both finish.
`--keep-going` applies only to simulator diagnosis. Each recorded integrity
or safety failure still blocks qualification.
