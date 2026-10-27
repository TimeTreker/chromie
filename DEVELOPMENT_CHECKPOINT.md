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

Run the everyday live-text cohort (`scenarios/everyday/`, 119 cases since the 50 persona cases of 2026-10-26; `scenarios/model_limited/` holds cases the
owner skips as local-model limits) against
Soridormi MuJoCo, judge every case, and repair each failure at its earliest
responsible owner. One invocation and one debug bundle per run; a hard failure in
the 15-case `must_pass` smoke stage stops `core` and `challenge` (owner rule).
Evidence and per-run judgments: `.chromie/acceptance/iter8-20261026/`, `iter7-20261026/`, `iter6-20261026/`, `iter5-20261025/`, `iter4-20261025/`, `iter3-20261025/`, `iter2-20261025/`, `iter1-20261025/`, `acc3-20261024/` (stopped at 57/70), `acc2-focused-20261024/`,
`acc1-20261024/`, `perf2-20261024/` and `perf-4f64f5120-20261024/` (performance mode), `review-fixes-20261023/` (stopped),
`merge-reads-20261023/`, `span-owned-20261023/`, `main-20cce0dfa-20261023/` (complete cohorts),
`planner-fit-20261023/` and `ingress-awaiting-20261023/` (focused),
`sc-evidence-20261022/` (latest full run),
`sc-ask-uncertain-20261022/`, `main-ad898cf7f-20261022/`, `vj-facts-20261021/`,
`thirsty-offer-20261021/`,
`main-6f8525947-quiet-20261021/`, `umi-time-margin-20261021/`, `main-3178a822c-20261021/`,
`playback-race-20261020/`, `answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`, `decided-activity-20261020/`,
`main-03974435e-20261020/` and `everyday-20261016/` (README.md in each).

## Resume point — 2026-10-25 (owner iteration loop, performance mode)

- Owner 2026-10-25: up to 8 iterations of complete cohort → earliest-boundary root cause → fix → gate → commit and
  push; when a cohort passes every case, add everyday scenarios to `scenarios/everyday/`.
- Iteration 1 (2fd36c9ea) hard-stopped at 32/70 on an invalid GA re-plan DTO (fixed in a3b8e2b82: a link to a
  finished Goal keeps the running Plan; celebrate is common). Iteration 2 (a3b8e2b82) hard-stopped at 34/70 (smoke
  15/15, core 17/19 automatic, 16/19 judged): the Planner cited "上海" with outcome tokens one off. This delivery:
  an outcome citation that misses its value moves to the value's single verbatim run in that outcome (12bfb0e95).
  Iteration 3 (12bfb0e95) hard-stopped at 16/70: iteration 2 had enforced "an acknowledgement says no answer or
  result" by splitting every Social Cognition act branch by function, growing the output schema 1.5-1.66x, and a
  large call overflowed the context. This delivery moves that rule into the reuse variants of delivered
  acknowledgements; the schema is now smaller than before iteration 2 (3cdf06008). Iteration 4 (3cdf06008)
  hard-stopped at 32/70 (smoke 15/15, core 15/17): the validators still judged the function label, rejecting a
  fresh "Here you are!" result labelled acknowledge. This delivery rejects only the reuse of an earlier
  acknowledgement for an answer or result, and moves `multi_that_water_zh` to `scenarios/model_limited/` (owner
  2026-10-25: local-model limit, skip until fine-tuning) (e36ada5b9). Iteration 5 (e36ada5b9, 69 cases) is the
  owner's stop point: no automatic cognition failure before a hard stop at 33/69 caused by a transient
  weather-provider geocoding timeout (Chromie planned Shanghai tomorrow and said truthfully that the lookup timed
  out); smoke 15/15 automatic (14/15 judged: a joke came out as "Why did you do that?"), core 17/18 automatic
  (16/18 judged). Every earlier hard-stop point passed. Iteration 6 (e36ada5b9, 2026-10-26) ran in quiet mode
  with the performance-mode default timeouts and hard-stopped at 28/69 on a Planner timeout (smoke 15/15, core
  12/13 automatic). This delivery (owner 2026-10-26): configurable character styles — one choice sets personality
  and social expression together (`config/mind/character_styles.json`), and the factory Chromie is `lively_cute`
  with the new `lively` expression preset (Mind 0.10.0) (7e091a536). Iteration 7 (7e091a536, quiet mode with its
  overrides) got furthest: 47/69, smoke 15/15, core 31/32 automatic (30/32 judged; "那上海呢？" answered Shanghai
  tomorrow, the language preference held, the quiet nod passed), then Goal Association looped
  `replace_requirement_indices: [0, 0, ...]` until truncation. This delivery offers those indices to the decoder as
  exact unique subsets (or a bounded list). The lively style did not raise expression use (2/116 SC calls with an
  expression vs 3/80 under courteous): open. Iteration 8 (9358ba34c, the SGLang transport carries that bound) is
  the loop's first complete cohort: 69/69 automatic, no hard stop; judged smoke 15/15, core 47/49, challenge 3/5
  (65/69 = 94.2 %, previous best complete judged cohort acc1 62/70). Quiet-mode latency: first audio p50 28.2 s.
- The workstation came up in quiet mode on 2026-10-26: deploy with the quiet-mode timeout overrides (Handoff).
  After a reboot start the Soridormi scene detached (Handoff).
- The owner's 8-iteration loop is complete (8 of 8 used). Per the owner, 50 everyday cases written for three buyer personas (a child, a
  working parent, a grandparent; `provenance.persona`) were added on 2026-10-26 and approved by the owner. Their first
  cohort (`personas-20261026/`) stopped at 30/119: the streaming Planner read the weather for "明天早上上班要不要带伞？"
  with an invented place "current_location" (the cross-script citation check cannot test a Latin value against a
  Chinese span), the provider answered location_not_found and the runner treated it as a Runtime failure. Read-only
  local tools now declare an unservable request as the owner's honest non-completion (`provider_output`), never a
  timeout or outage. Owner direction (2026-10-26): ask where the person works the first time and remember it until
  they say it changed; the case is now that three-turn flow. Owner loop 2 (2026-10-26: up to 6 iterations,
  my recommendations decide, commit and push each). Iterations 1-3 build that memory the way a person keeps what a friend tells them (owner
  decision 2026-10-27: no "要我记住吗？" question; the Charter's memory principle is amended): Social Cognition states
  `personal_fact` at ingress (key + text, `stated` first) only from the person's own Responsibility; Host keeps it as
  a fact about the speaker (`person_fact_entry`: subject, source and audience are the person, disclosure
  `shared_with_audience`, visible to UMI, GA and Planner) — as profile Memory when it is on (`.env.common`), replaced
  by key, otherwise for the conversation. Without speaker identification the speaker is `person:primary`; another
  speaker's facts are not shown. A kept fact grounds a later information read's value its turn words lack
  (`turn_citation_reanchored_to_memory`), counted once per key across tiers. A cross-script value stands only where
  a served outcome or a kept fact states it ("unknown" had been geocoded to Bangladesh); a required free-text read
  input no source states is asked for (`ungrounded_input_clarified`); the turn that answered a Goal's open input gap
  owns the value it states; a value the person said in this turn outside UMI's span moves to the outcome citation
  ("我明天要去广州出差，那边热不热？" had cited only "那边" and asked which district). GA's native decoder shapes: change
  branches carry their whole shape, a new Goal relates to or supersedes a retained Goal but never both, and an
  array whose items nothing can satisfy (`{"not": {}}`, no UMI binding to copy) is decoded empty (the shopping-list
  follow-up had written a free-form binding change and stopped the iteration-2 cohort at 70/119); a requirement
  keeps its Goal's outcome modality, so a speech answer to an information Goal resolves its gap or takes another
  relationship instead of replacing the question (only such requests change shape; the frozen corpus has none);
  modify and clarify are decoded only with a requirement change or a resolved gap (SGLang transport branches). The weather
  contract no longer carries the worked example "current-local-night realizes as date=today", which pulled a
  period-scoped "明天早上" to today (replayed live calls: 2.6 → 10.7 nats, and a wrong T4 corrected). A GA continuation or
  reference that answers a Goal's open input gap now closes it (only modify/clarify did). The silence
  reflex also takes a hush and a duration ("嘘，安静一会儿，我在打电话。" had been planned as a body action).
  Iteration 4: SenseVoice's own emotion and notable sound (`voice_cues`, owner decision 2026-10-27) reach Social
  Cognition with that utterance and shape only its tone, never the person's words. The streaming Planner decoder's mixed
  state now needs two different dispositions: "I have a headache. Can I take some of grandpa's pills?" decided answer
  and answer_from_perception (both respond) under mixed and stopped the iteration-3 cohort. The acceptance oracle
  listed the retired sidestep field `vy_mps`, so a sidestep that did go right failed; the library check now rejects an
  expected argument the oracle never observes, and `child_spin_en` accepts the truthful limitation (turn_in_place
  covers at most about 4 rad per request). The iteration-3 cohort (`it3-person-20261027/cohort/`, fabf2c910) stopped
  at 89/119 on that decoder state: smoke 15/15, core 71/74 automatic and 61/74 judged (63/74 with the two oracle
  defects corrected); challenge not reached. Open judged failures: "给我倒杯水。" says it was poured when the bottle
  was brought; a drawing or shirt Chromie cannot see is praised (two general SC wordings replayed at temperature 0
  changed nothing; model-limited candidate or a perception-scope fact from the provider); "你都会做些什么呀？" names
  abilities she lacks; boredom and loneliness get no offer of company; wave_friend has no greeting; the celebrate
  reply echoes the user. Compound fetch-and-read turns take 344-490 s. Next: the iteration-4 cohort, then iteration
  5 (a remember-this ability for "帮我记一下"), then latency (prefix caching, prompt size, serial UMI and SC ingress),
  then the standing-attention skill plan (`.chromie/plans/`).
  Measure the schema size of any Social Cognition schema change before deploying it.

Verification: clean-worktree gate on this delivery's source (2026-10-27): pytest 4,072 passed + 5 skipped
(`xgrammar` not installed), benchmarks 172, legacy Agent tests 20, all checks; the orchestrator line ratchet is
lowered to 1993 because the file shrank. Workflow replay tests 94/94; strict replay not rerun (last 6,000/6,000 on
freeze 47, 2026-10-23).

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

- The Fast decoder writes every argument a Capability declares as realizing what the person said
  (`argument_realization`) or as its repetition count; its own default needs no span (live: four reads of
  "明天" omitted date and read today; "点两下头" omitted count). Host still removes an unowned exact default.
- A Plan whose every step acquires information starts no Work-state Social Cognition call; its Evidence speaks next
  (live: a progress call after the clock read said "Monday" on a Saturday).
- An act said before Work Evidence reached Social Cognition cannot be reused to cover a need that reports that
  Evidence (`completed_work_dependencies`); the Agent decoder offers no such reuse and Host rejects it.
- Social Cognition's stated preference is kept once its words have played (`record_social_delivery`), also when Work
  ends the turn; the reply-language guard defers to a kept language preference (live: a kept "以后先用中文回答我",
  then the last guard line "Reply language: en-US" won).
- A Planner `respond` outcome that leaves its own Goal unmet with no Work, unresolved need or named unmet requirement
  is a contract failure (`validate_unmet_response_accounting`), so a failed GA revision keeps the first Plan (live:
  the GA-requested Plan for "那上海呢？" planned no read and replaced the first Plan's valid read).
- The live-text harness keeps Capability contracts on the reflex path too, so acceptance reads declared defaults.
- The SGLang transport decodes Goal Association's requirement replacement indices as exact unique subsets (up to
  four requirements) or a bounded list; the native decoder ignores `uniqueItems` (live: `[0, 0, ...]` until the
  output truncated). The DTO schema and the recorded replay requests are unchanged.
- A GA result whose new Goal only links to finished Goals (no association, supersession or referent change, no link
  to a still-open Goal) leaves the running UMI Plan in force instead of re-planning from scratch (live: such re-plans
  erased a correct weather read and failed the Planner contract; acc1 had 7 of 8 GA re-plans of this shape).
- An outcome citation whose tokens miss its value moves to that value's single verbatim run in the same outcome
  (extends the 2026-10-23 re-anchoring decision; a value the outcome does not hold still fails closed).
- An acknowledgement or wordless act said before an answer existed cannot be reused to cover that answer or a
  result: its reuse variant does not offer the need and the Agent and Host validators reject it (live: the ingress
  "嗯，我看看。" covered the answer need). A fresh act may report a result in its own words ("Here you are!").

## Owner decisions in force

- 2026-10-26: personality and social expression are one configurable character style; the factory Chromie is
  lively and cute (`lively_cute`, `lively` preset). SC orchestrates Soridormi skills, never motions (2026-10-25).

- 2026-10-25: a cohort case that fails only because of the local model's own judgment (shown by replays or
  margins after structural fixes) moves to `scenarios/model_limited/` until the model is fine-tuned; first
  `multi_that_water_zh`.

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
