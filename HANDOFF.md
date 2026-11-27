# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns current
four-axis state/open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns stable decisions.
Replace current facts; history remains in Git and [CHANGELOG](CHANGELOG.md).


## Current snapshot

Feature branch `codex/sc-context-budget-failure-notice` in `/home/chromie/github/chromie`.
The source comparison began at `5368d2cab`; the latest commit carrying these three status
owners is the resume revision. Historical main was `55f5587d4`. The Agent source digest
was `38834b8c3f35efbe344c4d72d0ff752d90e23ef7fe33828e8e0fe46b6fe5538f` and the
common-suite runtime identity was `2c0febc91fcee4a4e1cebd270f4268727bc4c3b9bb396608f978fc3e6ff38231`.
The Gemma4 12B revision was `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, Soridormi
`a49a87f68`, with unchanged SGLang and XGrammar builds and 28 unchanged role budgets.
The original Agent image `sha256:f9138d8641f0` was restored following simulation.
`30bf180d7` binds the Planner delivery. The separate profile-store change has local
regression evidence. The experimental close-time summarizer did not qualify for integration.

## Retained evidence

The local evidence root is `.chromie/acceptance/planner-memory-sources-20261127/`.

- `验证报告.md`, `product-manifest.json`, `product-focus-host.private.json` and
  `product-rest-host.private.json` contain the archived input fingerprints, real model
  output, canonical projection and source records. Seven identical requests improved from
  1/7 to 5/7. The separate catalog contrast is in `.chromie/acceptance/planner-first-need-fix/lexical.json`.
- `site/original/original/episode-summary.json` and the adjacent dialogue and playback
  logs retain ten terminal notifications. Food became an unapproved milk delivery,
  the follow-up claimed ongoing search without Work, and several replies played twice.
- `full-逐例结果.md`, `full-review.json`, `原28例本次结果.md`, `与main剩余21例.md` and
  `library79-逐例结果.md` cover every case. Common 128 had 85/16/26/1 complete/partial/
  failed/insufficient. Extra 79 had 45/13/21/0. The runner recorded 9 and 13 integrity
  failures respectively. The unsafe child-supervision promise was a separate manual failure.
- `site/{original,full,library79}/exits.json`, the adjacent post-status files and the
  single debug bundle for each window bind identity, exits and safe idle. The complete
  earlier main/branch comparison is in `.chromie/acceptance/paired28-20261123/逐例对照.md`.
- `canonical.log`, `level-a/summary.json` and `strict6000-local/summary.json` contain the
  offline verification. The earlier restricted-loopback attempt is retained separately.

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
proof=.chromie/acceptance/planner-memory-sources-20261127
cat "$proof/site/full/exits.json" "$proof/site/library79/exits.json" "$proof/site/post-agent-image.txt"
cat "$proof/与main剩余21例.md"
memory=.chromie/acceptance/conversation-close-adjudicated-20261127
cat "$memory/逐例判定.md" "$memory/store-after.log"
python -m pytest -q tests/test_intent_only_handoff.py tests/test_durable_profile_memory.py
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Use the retained failures before funding another comparison. The simulator grade remains
below main. Physical voice, robot and release qualification remain open.
