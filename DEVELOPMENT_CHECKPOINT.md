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
Evidence and per-run judgments: `.chromie/acceptance/thirsty-offer-20261021/` (latest),
`main-6f8525947-quiet-20261021/`, `umi-time-margin-20261021/`, `main-3178a822c-20261021/`,
`playback-race-20261020/`, `answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`, `decided-activity-20261020/`,
`main-03974435e-20261020/` and `everyday-20261016/` (README.md in each).

## Resume point — 2026-10-21

- Agent `thirsty-offer-20261021` (= `chromie-agent:latest`) is built from the source this
  delivery records and deployed with the quiet-mode timeout override; the Situation split runs
  in the host Orchestrator. Soridormi `main` (`e6257f4`, containing the pinned `51a2afa`) runs
  in the MCP container. Rollback: `reentry-ownership-20261021`.
- The workstation runs in quiet mode (owner request): CPU turbo off, GPU clocks locked to
  1800 MHz, and raised Agent and Host timeouts (Handoff).
- "告诉我现在几点" was typed speech on one `chromie-llm` lifetime and information on the next two,
  with the same request bytes (logprob margin -, +4.2, +1.5 nats). A candidate UMI sentence did
  not raise that margin consistently, so it was not adopted; `mix_water_time_zh` passed in both
  later runs.
- On `main` `6f8525947` the cohort stopped at `multi_thirsty_yes_en`: Chromie only
  sympathized, "Yes, please." then accepted an offer never made, UMI took the first-listed
  milk and copied the fused scene string, and Soridormi could not match it. With this delivery
  Chromie offers water, the person's "Yes, please." fetches it, and the run reached smoke 15/15
  and core 18/24 before stopping at `errand_remote_en` (STATUS open work 1).
- Next: repair `errand_remote_en` at its earliest boundary, rerun the complete cohort, then
  STATUS open work 2 by earliest boundary.

Verification: the new projection regression is red without its fix. Gate on the GPU host:
pytest 3,993 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests
20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets pass. Workflow
corpus freeze 47 (`bdb8db08…`) recaptures the 6,500 UMI requests; `scripts/run_workflow_replay.py`
6,000 cases passed with unchanged verdicts.

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
- A Soridormi scene object is two interpretations of one subject: what it is
  (`scene.simulated_object`, "bottle of milk") and where it is (`scene.simulated_position`).
  The fused "bottle of milk, 9.899 meters to Chromie's left (simulated)" was copied whole into
  a resource description that Soridormi could not match.
- UMI understands a bodily need told without a request ("I'm really thirsty") as asking for
  help Chromie could give now; its speech Responsibility addresses the need and asks whether the
  person wants that help. A turn that also asks for something keeps that request as its only
  Responsibility.

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
- Wanting to know a changing fact ("告诉我现在几点", also beside another request) is understood
  by UMI as information. The Planner reads it; SC only communicates: it may say it will check
  and tells the result after Evidence. Speech never reads and SC never checks (owner decision
  2026-10-21).
- Chromie offers help a family member would offer when the person tells a need she can meet
  (owner decision 2026-10-21). The offer comes from UMI's understanding and SC's communication;
  SC checks nothing. With no offer made, "Yes, please" taking the first-listed perceived object
  is a known gemma4 12B limit: a UMI rule against it changed nothing (milk over water by 9 nats,
  and listing water first flips it).
- A person beyond the head's turning range is looked at by turning the body first, inside
  Soridormi (owner decision 2026-10-20). A standalone `look_at_person` turns on a walking
  arc at the slowest gait pace, because pure in-place yaw barely turns this gait. It keeps
  0.5 m clearance and never turns during a locomotion overlay.

## Next work

Ordered next work and blockers: [STATUS — Current open work](docs/STATUS.md#current-open-work).

Claim boundary: no qualified cohort, no physical evidence and no release. Do not
claim a native semantic pass or behavioral improvement beyond the judged runs.
