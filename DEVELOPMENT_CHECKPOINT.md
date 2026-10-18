# Chromie Development Checkpoint

This is the stable resume point: active Issue, implemented contract, evidence
limits, repairs and owner decisions in force, and the claim boundary. Replace it on
each delivery; do not append history. Current status and the single ordered
open-work list live in [STATUS](docs/STATUS.md#current-open-work), volatile commands
and identities in [Handoff](HANDOFF.md), and earlier history in Git and the
[CHANGELOG](CHANGELOG.md).

The current focus remains Goal-driven single-authority architecture. The active
delivery line remains canonical local verification, then current-revision voice
proof, then default target-evidence closure.

## Active Issue — everyday live-cohort root-cause repairs

Run the everyday live-text cohort (`scenarios/everyday/`, 70 cases) against
Soridormi MuJoCo, judge every case, and repair each failure at its earliest
responsible owner. One invocation and one debug bundle per run; a hard failure in
the 15-case `must_pass` smoke stage stops `core` and `challenge` (owner rule).
Evidence and per-run judgments: `.chromie/acceptance/everyday-20261016/` (README.md).

## Resume point — 2026-10-17

- Since the last live run, the 2026-10-17 audit fix PRs (#70, #71) and their
  follow-up changed Agent, Orchestrator and shared-contract source. No built image
  matches `main`; `rootcause19-20261016` predates these changes, so rebuild the
  Agent image from `main` before the next live run.
- Latest live-relevant repair (UMI spans): the UMI prompt lists Responsibilities in word
  order, each ending at a later token, and says a reply to news or feelings ends where
  the sharing ends (one aside example; placed inside the rule it retyped a time
  request as speech). Cause: in run 7, "我考了满分！快跟我一起庆祝一下！" ended both the
  celebration and the reply at the last token, so Host rejected overlapping spans (503).
- Last recorded live Agent: `chromie-agent:latest` = `rootcause18-20261016`.
- Run 6 smoke on `rootcause18`: 15/15 mechanical ("把那个拿给我" → "你是说牛奶瓶还是水瓶呀？").
  Run 7 core stopped at 4/55 on the UMI 503 above.

Verification of the UMI span repair: recorded UMI replays (the celebrate case 4/4,
eight compound and information controls unchanged or better); workflow corpus freeze
42 (`de7c4de6…`, every UMI request recaptured for the widened `value_review` mark, no
reply re-authored; previous freeze 41 `a36b1ebf…`). Freeze 43 (`09813fa8…`) then
recaptured only the Planner request formats changed by the native disposition/step
assignment branches (4,700 cases, 5,300 steps, 5 prototypes); every verdict unchanged. Freeze 44
(`c808be23…`) recaptured every UMI request for shared source spans (6,000 cases, 6,500
steps, 5 prototypes); every verdict and every reply's schema validity unchanged. Gate and strict replay at the
delivery revision: pytest 3,955 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets pass; `tests/test_workflow_replay.py` 94 passed over 6,046 restored fixtures.

## Repairs in force from this Issue

- The Planner decoder exposes each permitted disposition/step assignment as a native
  branch: clarify, respond and unavailable carry no steps and execute carries at
  least one. The assignment previously lived only in `allOf`, which native decoders
  ignore, so the DTO rejected shapes the decoder allowed.
- An unsettled referent ("把那个拿给我") is clarified, never reported as a missing
  ability or limitation; the decoder requires a clarify state's Activity and lets an
  `unresolved_meaning` gap cite only the exact UMI wording.
- UMI decodes `meaning_uncertainties` before its Responsibilities and `confidence`
  after them; a bare demonstrative names a perceived object only when the conversation
  or trusted target evidence singles it out. Known cost: a "那个" named by the previous
  turn is also flagged; Goal Association may resolve it from history
  (`multi_that_water_zh` measures that live).
- While a speech Responsibility UMI marked `value_review` waits for Value Judgment, SC
  ingress offers and Host admits only an acknowledgement for the whole turn; sibling speech
  is answered after Value Judgment through its Planner need. A value-reviewed Capability
  alone does not hold back sibling speech.
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
- Value Judgment reviews a Responsibility that UMI marks `value_review`: a deception
  request (owner choice B, 2026-10-12) or a request whose doing or answering could hurt,
  humiliate, frighten or endanger someone, whatever Capability it uses (owner decision
  2026-10-17, Charter VALUE-JUDGMENT-001); `protect_children` is not in the Stable Mind
  (owner undecided).
- Soridormi calls describe body targets in one format: person by referent (the
  current speaker is the reserved `"requester"`), object by description, place by
  cited name; Soridormi resolves the physical target, Chromie never sends look
  yaw/pitch, and a typed not-found is a reported limitation, never completion. SC
  decoration may use expressive gestures Soridormi declares low-risk; locomotion stays
  excluded (owner decision 2026-10-17).
- UMI never authors `bindings`; Planner alone extracts Capability parameters.

## Next work

Ordered next work and blockers: [STATUS — Current open work](docs/STATUS.md#current-open-work).

Claim boundary: no qualified cohort, no physical evidence and no release. Do not
claim a native semantic pass or behavioral improvement beyond the judged runs.
