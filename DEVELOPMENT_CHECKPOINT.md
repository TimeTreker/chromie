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
Evidence and per-run judgments: `.chromie/acceptance/perf2-20261024/` and `perf-4f64f5120-20261024/` (performance
mode), `review-fixes-20261023/` (stopped),
`merge-reads-20261023/`, `span-owned-20261023/`, `main-20cce0dfa-20261023/` (complete cohorts),
`planner-fit-20261023/` and `ingress-awaiting-20261023/` (focused),
`sc-evidence-20261022/` (latest full run),
`sc-ask-uncertain-20261022/`, `main-ad898cf7f-20261022/`, `vj-facts-20261021/`,
`thirsty-offer-20261021/`,
`main-6f8525947-quiet-20261021/`, `umi-time-margin-20261021/`, `main-3178a822c-20261021/`,
`playback-race-20261020/`, `answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`, `decided-activity-20261020/`,
`main-03974435e-20261020/` and `everyday-20261016/` (README.md in each).

## Resume point — 2026-10-24 (performance mode)

- The workstation runs in performance mode (CPU turbo on, GPU 575 W default); the Agent and Host use the profile's
  default timeouts, not the quiet-mode overrides. `./scripts/start_chromie.sh --keep-services --no-orchestrator`
  regenerates the env files.
- Agent `perf2-20261024` (= `chromie-agent:latest`, `b27810d373c0`) is built from this delivery's source;
  `--verify-agent-source` matched (`.chromie/acceptance/perf2-20261024/`).
- Complete cohorts today: on `4f64f5120` smoke 15/15, core 29/33 then a hard stop (SC prompt 165k characters over
  the budget); with the SC snapshot dedup, Goal-bound trimming and the 6 s playback wait, every case was attempted
  for the first time: smoke 15/15, core 47/50 (42 judged), challenge 5/5 (3 judged).
- Next: STATUS open work 1-2 by general mechanisms (no case-by-case prompt rules, owner 2026-10-24); further latency
  work (UMI and SC ingress run before first audio; Planner prompt p50 about 81k characters).

Verification: gate on this delivery's source: pytest 4,024 passed + 5 skipped (`xgrammar` not installed),
benchmarks 172, legacy Agent tests 20, all checks. Strict replay 6,000/6,000 on freeze 47 (unchanged corpus).
300 SC schema shapes compile on live SGLang (2026-10-23; the SC schema is unchanged since).

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
- Before validation, a byte-identical idempotent, side-effect-free read the Planner wrote again
  for another Responsibility is merged into the first, which then serves both and is validated
  (owner decision 2026-10-23; live: "我要不要带伞？" got a second weather read citing the
  first question's "北京"). Both read merges require the same state snapshot: identical reads
  merge only when they wait for the same state-changing Activities, and a read with an unknown
  dependency is never merged (second review 2026-10-23).
- Social Cognition's model snapshot points each repeated subtree at its first copy, and a
  Goal-bound call keeps its bound Goals' canonical snapshots, Plan, Evidence and GA resolution,
  not GA's association inputs or the legacy task views (owner choice 2026-10-24, performance;
  live: a 165k-character prompt exceeded the context budget).
- The interactive playback-start wait is 6 s, above TTS first-audio p95 (owner choice
  2026-10-24; at 3.5 s three of four answer chunks were cancelled).
- A Planner argument's turn-span citation is offered only inside the source words of a
  Responsibility its Capability can serve, which the Host requires (live 2026-10-23:
  "瓶水，" ran past the fetch's words into the comma and stopped the cohort).
- A Responsibility that could be a limitation states `needed_abilities_fit` right before its
  decision; only `false` opens `unavailable` (live 2026-10-22: every ability need fit, yet
  "把那个拿给我" named the uncertain referent as missing and was decided unavailable, so SC
  had to say it could not fetch right after asking which one). An answer from perception
  states no fit.
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
- Ingress Social Cognition may ask about a task Responsibility only when UMI listed a meaning
  uncertainty for it: the decoder offers that question branch and Host and the DTO admit it
  only then. Its task receipt no longer suggests "好的", matching the authority prompt's
  "嗯，我看看。" (live 2026-10-22: "好的，请问是哪一个？" was rejected as an acknowledgement).
- A question Social Cognition asked about a Responsibility's uncertain meaning stands as the
  turn's reply until the person answers: a later goal_state wake-up for only those
  Responsibilities in the same turn returns that delivered result and is not sent to SC (live
  2026-10-22: a goal_state SC read "你是说那个牛奶瓶吗？" as the answer, "是的，就是那个。").
  The Planner's clarify need for the same meaning may stay pending or reuse the question:
  a prior act may cover a later input need only when the ledger records it as a question
  about that uncertain meaning and every gap of the need is that meaning (the 2026-10-11
  relabelled "Okay." stays rejected).
- After ingress, an informing, answering, asking or repairing act about task Work needs that
  Work's Evidence (post_evidence), a supplied need, or only speech Responsibilities; otherwise it
  is pre_evidence. The decoder offers pre_evidence at every trigger with task Work, and Host and
  the DTO enforce the same rule.
- Model JSON parsing accepts raw control characters inside strings, which the native decoder's
  string rule admits (live: a tab ending a Planner reason_summary failed the contract after
  decoding).
- Value Judgment writes who is affected, then the concern, then the decision, and each fact
  narrows what follows in the decoder and the DTO: a concern about someone else's things,
  privacy, consent, deception or family needs someone besides the person asking, and no concern
  decides proceed (live: "nobody_else" with "others_property" asked whose a household TV remote
  was; with no concern it asked where to wait).

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
- When UMI cannot tell what the person wants and lists a meaning uncertainty for a task
  (which of two bottles "那个" is), Social Cognition asks the person right away at ingress,
  as a person would; UMI's goal is to know what the person wants and SC communicates to
  clarify it (owner decision 2026-10-22). The question is context-grounded and claims
  nothing about the Work; a turn waiting for Value Judgment still only acknowledges.
- Before a task's Evidence or a supplied need exists, Social Cognition speaks of that Work only
  as received, being checked or in progress, at every moment and not only at ingress (owner
  decision 2026-10-22; live: "It's Wednesday" was said before the clock read and repeated after
  Evidence said Thursday).
- Two identical idempotent reads written for two Responsibilities become one read serving
  both, merged by the Host before validation (owner decision 2026-10-23). This is an exception
  to the freeze-36 direction to fix repeated Activities at the model input: the count was a
  0.27-nat near-tie, and a prompt sentence, a new answer source and an Evidence-bound answer
  form each failed to move it.
- When an information read's cited turn words lack its free-text value and the value occurs
  verbatim exactly once in the outcome of a Responsibility the Activity serves and earlier talk
  already said it, the Host re-anchors that citation to the outcome span before validation
  (a value only the outcome holds still fails closed); the value is unchanged
  (owner decision 2026-10-23; live: "there" was cited for "Beijing" that UMI had resolved; the
  turn-versus-outcome choice was a 0.1-nat near-tie and a decoder reorder flipped either way).
- Social Cognition may propose memory candidates in ordinary turns (for example the answer
  language a person asked for); the Host validates them and Memory stores them, and Social
  Cognition reads the preference back from Active Memory (owner decision 2026-10-23; live: a
  Chinese-answer preference was agreed and then not kept). The decoder requires the field at
  ingress, the Host carries it as a session `preference` Memory update on the turn's response;
  a preference stated in a turn whose final response comes from Work is not yet kept.
- Value Judgment asks before Chromie takes or uses another family member's personal things
  (a parent's wallet or phone) unless the words show that person agreed; the person's own
  things and things the household shares proceed (owner decision 2026-10-21).
- A provider that declared it did not complete and did not move, with a safe-idle final
  state, reported honest Evidence: the acceptance runner judges that case by its expectations
  and keeps collecting (owner decision 2026-10-21). Safety, service, provenance, contract and
  LLM-integrity failures still stop the cohort.
- A person beyond the head's turning range is looked at by turning the body first, inside
  Soridormi (owner decision 2026-10-20). A standalone `look_at_person` turns on a walking
  arc at the slowest gait pace, because pure in-place yaw barely turns this gait. It keeps
  0.5 m clearance and never turns during a locomotion overlay.

## Next work

Ordered next work and blockers: [STATUS — Current open work](docs/STATUS.md#current-open-work).

Claim boundary: no qualified cohort, no physical evidence and no release. Do not
claim a native semantic pass or behavioral improvement beyond the judged runs.
