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
Evidence and per-run judgments: `.chromie/acceptance/playback-race-20261020/` (latest),
`answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`, `decided-activity-20261020/`,
`main-03974435e-20261020/` and `everyday-20261016/` (README.md in each).

## Resume point — 2026-10-21

- Agent `reentry-ownership-20261021` (= `chromie-agent:latest`) is built from the source this
  delivery records and deployed; the Situation repair runs in the host Orchestrator.
  Soridormi `main` (`e6257f4`, containing the pinned `51a2afa`) runs in the MCP container.
  Rollback: `answer-source-20261020`.
- The 2026-10-20 branches are merged to `main` (owner request, no post-merge gate). On
  `main` `3178a822c` (2026-10-21) the everyday run reached smoke 15/15 and core 13/14. It then
  stopped at `mix_water_time_zh`: both Goals were decided respond with their Evidence, and the
  re-entry re-listed the executed fetch and clock read as new Work. Replaying the recorded
  request gave the valid output 3/3, so the decoder now makes that shape impossible. The same
  run logged twice that ambient perception stopped updating (stale scene revisions crowded out
  the new one).
- The rerun with these repairs reached smoke 15/15 and core 12/14, with no ambient perception
  error. It stopped at `mix_water_time_zh`: UMI typed the time question as speech (STATUS open
  work 1).
- Next: implement the owner's decision for a question that needs a current fact, then rerun
  the complete cohort and repair STATUS open work 2 by earliest boundary.

Verification: the new regressions are red without their fixes. XGrammar compiles the
two-Goal re-entry schema in 0.38 s, against 0.28 s before on identical inputs. Gate on the GPU
host: pytest 3,992 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets
pass. Workflow corpus freeze 46 (`36b7702b…`) recaptures the 200 re-entry requests;
`scripts/run_workflow_replay.py` 6,000 cases passed, verdict counts equal to freeze 45.

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
- Mandatory members are serialized first for native decoders, which ignore `contains`.
  Each Responsibility decided work or clarify opens the Planner's counted Activities with
  its own Activity (live: "我考了满分！快跟我一起庆祝一下！" spent its one Activity on the
  sibling answer). Social Cognition's first act names every result need that must be
  said now (live: "我不会后空翻" said the limitation but named only the answer need).
- An information Responsibility that perception could answer first states `answer_source`
  ("a current observation shows it" or "a Capability or what Chromie knows answers it"),
  then `observed_refs`, then its decision (live: "帮我拿瓶水，顺便告诉我现在几点。" cited the
  scene for the time). Observations-first alone failed that; decision-first let "现在几点了？"
  cite the scene.
- Host playback waits take a waiter settled at the deadline as settled (live: playback
  started 7 ms before the 3.5 s timeout fired and played speech was reported undelivered).
- Evidence re-entry with up to two Goals: each decision assignment is a native decoder
  state in Goal order. An execute opens `new_work` owned only by the executing Goals, and no
  execute closes it (live: executed Work re-listed under respond decisions).
- Situation: a newer perception observation from the same owner replaces the one it
  supersedes, and the caller's sources and interpretations outrank inherited ones in the
  bounds (live: ambient perception kept stale objects, then stopped updating).

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
- A question about a current fact ("告诉我现在几点") is answered from a fresh read even when UMI
  types it as speech. SC says it will check, the Planner reads, and SC tells the result after
  Evidence (owner decision 2026-10-21, implementation pending).
- A person beyond the head's turning range is looked at by turning the body first, inside
  Soridormi (owner decision 2026-10-20). A standalone `look_at_person` turns on a walking
  arc at the slowest gait pace, because pure in-place yaw barely turns this gait. It keeps
  0.5 m clearance and never turns during a locomotion overlay.

## Next work

Ordered next work and blockers: [STATUS — Current open work](docs/STATUS.md#current-open-work).

Claim boundary: no qualified cohort, no physical evidence and no release. Do not
claim a native semantic pass or behavioral improvement beyond the judged runs.
