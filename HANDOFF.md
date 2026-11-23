# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns current
four-axis state/open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns stable decisions.
Replace current facts; history remains in Git and [CHANGELOG](CHANGELOG.md).


## Current snapshot

- Checkout `/home/chromie/github/chromie`, feature branch
  `codex/sc-context-budget-failure-notice`. The offline repair starts at
  `e5ced6afcb3e5cb12fa25d0fdcf08bceff63027b`. The latest commit carrying these status owners
  is the resume revision. Main merge requires owner approval.
- The retained weather provider separates forecast periods. The existing Host preserves
  playback order, waits for same-Goal evidence and consumes a rejected opportunity once.
- Eight fixed-model engineering trials are finished. The tested SC candidate is withdrawn. Its
  exact source-and-test diff remains in
  `.chromie/acceptance/paired28-20261123/sc-rejected.patch`, SHA256
  `d723cf0787b96df19a758ea825216538a3f26fd1fcfefad3a0ff3e3b58572a86`.
- Candidate Agent source digest
  `c10b56436aab066a170e423fb9e50ed44be242d17b225fe3fd5e06a81716354a`, common128 runtime
  identity `89b7cbb37cb2531bba2561e50602b0e54358acaadabe816cdc8b9fcd92f7efdf`. Gemma4 12B
  revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, SGLang 0.5.19, XGrammar 0.2.1, the same
  28 budgets and Soridormi revision `a49a87f68`. Exact image and environment identities are in
  each window. Initial Agent image `sha256:f9138d8641f0` was restored. Scene and MCP were
  stopped after safe-idle verification.

## Retained evidence

All new private reports are in `.chromie/acceptance/paired28-20261123/`. The comparison used
main `55f5587d4` and the previous branch application frozen under
`.chromie/acceptance/optimize-fixed-model-20261121/weather-only/`.

- `offline-stages/离线验收.md` indexes the two original Planner calls, before/after contract
  replay, CPU XGrammar membership results, focused checks, Level A and the archived Host audit.
  Of 270 historical calls, 17 stopped during contract loading. Among 253 complete
  documents, 251 kept the same result and the two late canonical failures were rejected early.
  Level A passed 45/45. `offline-stages/workflow-final/summary.json` records all 6,000 expected
  offline outcomes with stable source and zero model calls. `offline-stages/canonical-final.log`
  records the local gate on the repair.
  No service inference, redeployment, or new functional score was requested for this patch.
- `逐例对照.md`, the 28 numbered JSON records and `main-plan-current-invariant.json` bind case,
  input, both original role records and earliest error. `八轮同输入验证.md` records all 37 role
  probes. `现场专项.md` records the six-case live gate.
- `原始对话重放.md`, `site/original/episode-receipts.private.json`, `共同128结论.md`, `full-逐例结果.md` and
  `library79-逐例结果.md` record actual outputs, effects, failures and user-facing verdicts.
  `115-native-host.json` and `sc-matched-ingress.json` are offline checks.
- The initial disjoint 79 recorded 10/79 automatic passes with 64 nonadmissions. `额外集预检阻塞.md`,
  `recovery64/blocked-inputs.json` and `recovery64/library79/` retain the refusal and the 64
  previously unadmitted cases on the same candidate. The supplemental window had 39/64
  automatic passes. `regression-totals.json` preserves both windows.
- `site/` holds original, focused and full source proofs, exits, post-status and one bundle
  per window. `canonical.log`, `level-a/summary.json` and `strict6000/summary.json` cover the
  candidate's offline verification. The retained application's local checks are in
  `retained-canonical.log`, `retained-policy.log` and `retained-docs.log`.

## Resume and verify

Use the following commands to inspect existing evidence and run local checks.

```bash
set -e
cd /home/chromie/github/chromie
proof=.chromie/acceptance/paired28-20261123
cat "$proof/regression-totals.json" "$proof/115-native-host.json"
cat "$proof/site/full/exits.json" "$proof/site/library79/exits.json" "$proof/recovery64/library79/exits.json"
cat "$proof/recovery64/library79/post-status.json" "$proof/recovery64/post-agent-image.txt"
cat "$proof/offline-stages/native.json" "$proof/offline-stages/archived-host-audit.json"
python -m pytest -q tests/test_planner_streaming_commit.py tests/test_planner_staged_progress.py tests/test_planner_reentry_policy.py
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

No further model rounds are pending under the eight-round allowance. Any future comparison
should preserve the existing hashes, fixture sets, strict validators, model and budgets. The
previous branch baseline remains the live reference until a separately authorized trial.
