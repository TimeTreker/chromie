# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns current
four-axis state/open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns stable decisions.
Replace current facts; history remains in Git and [CHANGELOG](CHANGELOG.md).


## Current snapshot

Feature branch `codex/sc-context-budget-failure-notice` in `/home/chromie/github/chromie`.
The singing comparison used feature baseline `e3307868b` and historical main
`55f5587d4`. The evaluated Agent source digest was
`8b87dab24dd721379f97c463b3f1b6cf28a45bea54ad31a3dd76459718465850`.
The common-suite runtime identity was
`a91063b4d84bd4889fb0dcd49f48b130c978a0a41f0e12bde6ffbe6c6cb7a5a0`.
Gemma4 12B revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, Soridormi
`a49a87f68` and 28 role budgets were held fixed. The simulator restored the original
Agent image `sha256:f9138d8641f0`. The feature candidate remains unqualified overall.

## Retained evidence

The current evidence root is `.chromie/acceptance/planner-effect-c30-20261128/`.

- `C30验证.md`, `c30-comparison.json` and `manifest.json` bind the main and
  feature traces, the eight archived requests and their criteria. The two diagnostic
  changes to ordering or general instructions still failed singing. The delivery-scope
  prompt passed singing and reminders and preserved dog recall and object counting.
- `site/focused/exits.json` and its two case summaries bind the realized answers.
  Both also passed in the full run. The earlier baseline is under
  `.chromie/acceptance/planner-memory-sources-20261127/`.
- `site/original/original/episode-summary.json` records ten terminal notifications.
  Milk delivery was still substituted for food help. The last reply mentioned only
  a water bottle. Some earlier replies repeated.
- `full-逐例结果.md`, `library79-逐例结果.md` and `失败清单.md` index all judgments.
  The common set scored 93/12/23 complete/partial/failed and the extra set scored
  43/13/23. Eight common and twelve extra cases registered integrity failures.
  `adverse-cases.json` and `adverse-before.private.jsonl` compare the two
  newly failing requests with the previous prompt on the same inputs.
- `site/{original,full,library79}/exits.json`, each debug bundle path in `bundle.log`
  and the service and runtime identities retain execution and restoration evidence.
  `canonical-local.log`, `level-a/summary.json` and `strict6000/summary.json` contain
  the successful local gate, 45 ability cases and 6,000 offline workflow variants.
  `canonical.log` records the separate attempt where local test sockets were disabled.

The local independent memory report is `.chromie/acceptance/conversation-close-20261127/验证报告.md`.
The terminal review, final candidate patch against `30bf180d7`, exact-input replay and
storage before/after tests are under `.chromie/acceptance/conversation-close-adjudicated-20261127/`.
All 19 fixed requests have native model outputs. Seven came from the earlier identical
source-classification run and twelve from its held-out cases. The final Host replay did
not call the model. It excluded the withdrawn parrot name and protected other speakers.
The profile oracle passed 16/19. No substantive summary survived its privacy signal.
The current feature keeps the tested storage improvements and ordinary at-turn write path.
Its `branch-canonical.log` records 4,433 main tests, 1,046 subtests and 20 legacy checks.
`concurrent-store.json` records 12 concurrent owner processes and six correctly scoped deletions.

## Resume and verify

```bash
set -e
cd /home/chromie/github/chromie
proof=.chromie/acceptance/planner-effect-c30-20261128
cat "$proof/site/full/exits.json" "$proof/site/library79/exits.json" "$proof/site/post-agent-image.txt"
cat "$proof/C30验证.md" "$proof/失败清单.md"
memory=.chromie/acceptance/conversation-close-adjudicated-20261127
cat "$memory/逐例判定.md" "$memory/store-after.log"
python -m pytest -q tests/test_intent_only_handoff.py tests/test_durable_profile_memory.py
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Use the retained failures before funding another comparison. The simulator grade remains
below main. Physical voice, robot and release qualification remain open.
