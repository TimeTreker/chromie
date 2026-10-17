# Chromie Development Checkpoint

This is the stable resume point: active Issue, implemented contract, evidence
limits, owner decisions in force and ordered next work. Replace it on each
delivery; do not append history. Current status lives in
[STATUS](docs/STATUS.md), volatile commands and identities in [Handoff](HANDOFF.md),
and earlier history in Git and the [CHANGELOG](CHANGELOG.md).

The current focus remains Goal-driven single-authority architecture. The active
delivery line remains canonical local verification, then current-revision voice
proof, then default target-evidence closure.

## Active Issue — everyday live-cohort root-cause repairs

Run the everyday live-text cohort (`scenarios/everyday/`, 70 cases) against
Soridormi MuJoCo, judge every case, and repair each failure at its earliest
responsible owner. One invocation and one debug bundle per run; a hard failure in
the 15-case `must_pass` smoke stage stops `core` and `challenge` (owner rule).
Evidence and per-run judgments: `.chromie/acceptance/everyday-20261016/` (README.md).

## Resume point — 2026-10-16

- Latest delivered repair (UMI spans): the UMI prompt lists Responsibilities in word
  order, each ending at a later token, and says a reply to news or feelings ends where
  the sharing ends (one aside example; placed inside the rule it retyped a time
  request as speech). Cause: in run 7, "我考了满分！快跟我一起庆祝一下！" ended both the
  celebration and the reply at the last token, so Host rejected overlapping spans (503).
- Live: `chromie-agent:latest` = `rootcause18-20261016`. Built, not deployed:
  `rootcause19-20261016` with the UMI span repair.
- Run 6 smoke on `rootcause18`: 15/15 mechanical ("把那个拿给我" → "你是说牛奶瓶还是水瓶呀？").
  Run 7 core stopped at 4/55 on the UMI 503 above.

Verification of the latest delivery: recorded UMI replays (the celebrate case 4/4,
eight compound and information controls unchanged or better); workflow corpus freeze
41 (`a36b1ebf…`, every UMI request recaptured, no reply re-authored); strict replay
6,000/6,000 with zero model calls; canonical gate in a clean worktree (pytest 3,845
passed + 5 skipped, benchmarks 169, legacy 20, policies, docs, test ownership).

## Repairs in force from this Issue

- An unsettled referent ("把那个拿给我") is clarified, never reported as a missing
  ability or limitation; the decoder requires a clarify state's Activity and lets an
  `unresolved_meaning` gap cite only the exact UMI wording.
- UMI decodes `meaning_uncertainties` before its Responsibilities and `confidence`
  after them; a bare demonstrative names a perceived object only when the conversation
  or trusted target evidence singles it out. Known cost: a "那个" named by the previous
  turn is also flagged; Goal Association may resolve it from history
  (`multi_that_water_zh` measures that live).
- While any Responsibility of a turn waits for Value Judgment, SC ingress offers and
  Host admits only an acknowledgement; sibling speech is answered after Value Judgment
  through its Planner need.
- An information Responsibility with citable current perception states `observed_refs`
  before its decision; only a non-empty list opens `answer_from_perception`, which Host
  binds as a cited response need.
- SC receives a fresh request or question without agreeing ("嗯，我看看。") and shares
  in news; it no longer says "好的。" before a limitation.
- The local clock provider declares `prompt_tier: common` (a provider declaration wins
  over the owner preset).

## Owner decisions in force

- Chromie never calls herself a robot, AI or device, answers as herself and asserts
  nothing false about her nature (Charter and interaction contract).
- An unsettled referent is resolved from the conversation when possible, otherwise
  Chromie asks the person.
- Value Judgment does not review speech-only deception; `protect_children` is not in
  the Stable Mind (owner undecided).
- UMI never authors `bindings`; Planner alone extracts Capability parameters.

## Next work and blockers

1. Deploy `rootcause19-20261016` (owner), rerun the smoke stage, then `core` and
   `challenge`.
2. Open defects: homework decline over-offers reminders; "去那边等我" acknowledged with
   "好的。"; Value Judgment asks consent/meaning questions (hug); SC echoes the user's
   words (celebrate). The corpus lacks SC and perceived-answer steps.
3. Constrained Planner decoding is slow in grammar-heavy regions (about 12-15
   tokens/s); a second Planner pass can miss the deadline.
4. After the cohort: narrow current-revision voice proof, then default target-evidence
   closure. Physical microphone, speaker and robot evidence remain supervised; text,
   discarded TTS and simulated acquisition do not replace them.

Claim boundary: no qualified cohort, no physical evidence and no release. Do not
claim a native semantic pass or behavioral improvement beyond the judged runs.
