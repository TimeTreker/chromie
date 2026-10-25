# Changelog

This file records notable current changes. Detailed earlier development history
remains available in Git history.

## Unreleased

### A link to a finished Goal no longer re-plans; celebrate is in the common repertoire (iteration 1, 2026-10-25)

- When Goal Association only relates a new Goal to Goals that are already finished, the running Planner result
  stays in force instead of a second Planner planning from scratch and replacing it. Such re-plans erased a correct
  weather read for "那上海呢？" and, for "Yes, please.", produced an invalid Plan that stopped the live cohort.
- `celebrate` joins the common prompt tier: a loaded hand wave was always judged to fit a celebration, so the rare
  contract was never loaded.

### Said arguments are written, no progress line before a read's Evidence, kept preferences are honored (accuracy, 2026-10-24)

- The Fast decoder writes every argument a Capability declares as realizing what the person said, and every
  repetition count, instead of leaving it to a default: four reads of "明天" had read today, and "点两下头" omitted
  its count.
- A Plan that only reads information starts no Work-state Social Cognition call, and words said before Work
  Evidence cannot be reused to cover the answer: a progress line had said "Monday" on a Saturday and was then
  reused as the clock answer.
- A preference Social Cognition keeps is stored once its words have played, also when Work ends the turn, and the
  reply-language guard defers to it ("以后先用中文回答我" was kept, then English questions were answered in English).
- A Planner response that leaves its own Goal unmet with no Work and no named gap is a contract failure, so a failed
  GA revision keeps the first Plan's valid read ("那上海呢？" had planned nothing and said it was checking).
- The live-text harness reads declared defaults on the reflex path too.

### Smaller Social Cognition prompts and a playback wait above TTS latency (performance, 2026-10-24)

- Social Cognition's model snapshot replaces each repeated subtree with a pointer to its
  first copy, and a Goal-bound call (goal state, Work state, Evidence) keeps its bound Goals'
  canonical snapshots, Plan, Evidence and GA resolution instead of GA's association inputs and
  the legacy task views that restate them (owner choice). Live, one Goal list appeared three
  times and Evidence four times; a 165k-character prompt exceeded the context budget and
  stopped the cohort. On that run's real calls the Evidence prompts shrink about 28-33% and
  Work-state prompts about 20%.
- The interactive playback-start wait rises from 3.5 s to 6 s (owner choice): TTS first audio
  reached 3.0-3.3 s at p95 and three of four answer chunks were cancelled before playback.

### Argument spans stay inside the Responsibility's own words; one identical read serves both questions; stated preferences are kept (2026-10-23)

- A merged read must wait for the same state changes as its twin: a read after an action
  is a different read (second review: "read → walk → read" lost its second read, also in the
  committed same-Responsibility collapse), and a read with an unknown dependency is never
  merged, so validation still rejects it.
- When an information read's cited turn words lack its value, the value appears verbatim
  exactly once in the outcome of a Responsibility it serves, and earlier conversation already
  said it, the Host cites that outcome instead (owner decision); a value only the outcome holds
  still fails closed, so UMI cannot override the person's own words. Live, "Will it rain there this afternoon?" wrote "Beijing" (UMI's
  outcome) but cited "there", and the long conversation stopped.
- The repository policy check no longer treats an ignored `__pycache__`-only directory as a
  restored retired module.
- Social Cognition keeps a lasting preference the person states ("以后先用中文回答我") as a
  memory candidate at ingress; the Host stores it as session Memory and Social Cognition
  answers in the stated language on later turns (owner decision). Live, the preference was
  agreed aloud and the next English question was answered in English.

- When the Planner writes a second, byte-identical idempotent and side-effect-free read for
  another Responsibility, the Host merges it into the first before validation, and that read
  serves both (owner decision). Live, "明天北京会下雨吗？我要不要带伞？" planned a second
  weather read for the umbrella question that cited the first question's "北京", and the turn
  failed; no prompt or decoder change moved the 0.27-nat count near-tie.

- The Planner decoder now offers a turn-span citation only inside the source words of a
  Responsibility the Capability can serve. Live, "帮我拿瓶水，顺便告诉我现在几点。" cited
  "瓶水，" with the comma past the fetch's words; Host rejected the citation and the cohort
  stopped in core.

### Unavailable only when an ability is missing; the ingress question covers the Planner's (2026-10-23)

- Before deciding a Responsibility that could be a limitation, the Planner states whether the
  abilities it needs fit: true offers work, answer or clarify, false only unavailable. Live,
  every ability need fit, yet "把那个拿给我" named the uncertain referent as missing and was
  decided unavailable, so Social Cognition said it could not fetch right after asking which
  one. Replayed recorded requests: both uncertain referents now clarify; backflip, dance,
  singing, reminders and coffee stay unavailable; work, answers and perceived answers are
  unchanged (margins 6-10 nats).
- A question Social Cognition asked at ingress about meaning UMI left uncertain may cover the
  Planner's later input need for that same meaning; the ledger must record it as that
  question. Live, reusing it was rejected and the turn ended in "抱歉，我没能完成刚才那个任务。".

### A question asked at ingress waits for the person's answer (2026-10-23)

- After Chromie asks which thing the person means, a later Goal-state wake-up in the same
  turn no longer asks Social Cognition again: the question stands as the turn's reply until
  the person answers. Live, a goal_state Social Cognition read "你是说那个牛奶瓶吗？" as the
  answer, said "是的，就是那个。", and the Planner's question then became "好的，我这就拿给你。".
- One contract definition of a question about uncertain meaning replaces the copies in the
  contract and Agent validation.
- The Host runtime file's size ratchet rises by four lines for this check and its log line.

### Asking right away, no results before Evidence, decoder control characters (2026-10-22)

- When UMI lists a meaning uncertainty for a task ("把那个拿给我" with two bottles in view),
  Social Cognition may ask at ingress, as a person would (owner decision). The question is
  context-grounded and claims nothing about the Work; Host and the decoder allow it only for
  that Responsibility and not while Value Judgment is pending. Live, the question was said as
  an acknowledgement and rejected, and the Planner's later question was never said.
- The ingress task receipt no longer suggests "好的", which preceded later refusals; it
  matches the authority prompt's "嗯，我看看。".
- Before a task's Evidence or a supplied need, Social Cognition speaks of that Work only as
  received, being checked or in progress, at every moment (owner decision). Live, Chromie said
  "It's Wednesday" before the clock read and repeated it after Evidence said Thursday.
- Model JSON parsing accepts raw control characters inside strings, which the native decoder
  admits; a tab ending a Planner reason_summary had stopped a live cohort.

### Consistent Value Judgment facts, family members' personal things, honest non-completion (2026-10-21)

- Value Judgment's facts now narrow what follows, in the decoder and the DTO: a concern about
  someone else's things, privacy, consent, deception or family needs someone besides the person
  asking, and no concern decides proceed. It had written "nobody_else" with "others_property"
  and asked whose a household TV remote was; with no concern it asked where to wait.
- Value Judgment asks before taking or using another family member's personal things (a
  parent's wallet or phone) unless that person agreed; the person's own things and things the
  household shares proceed (owner decision).
- The acceptance runner no longer stops a cohort when a provider declared it did not complete,
  did not move and left Chromie safe idle; the case is judged by its own expectations (owner
  decision). `errand_remote_en` now allows looking for the remote and forbids only a completed
  fetch.

### Offering help for a stated need, and scene objects named apart from their position (freeze 47, 2026-10-21)

- UMI now understands a bodily need told without a request ("I'm really thirsty") as asking
  for help Chromie could give, so Social Cognition offers it ("Would you like me to help you get
  some water?"). Chromie used to only sympathize; "Yes, please." then accepted an offer never
  made and fetched the first-listed milk.
- Each Soridormi scene object is now two Situation interpretations of one subject: what it is
  ("bottle of milk") and where it is. The fused "bottle of milk, 9.899 meters to Chromie's left
  (simulated)" was copied whole into a resource description that Soridormi could not match.
- Workflow corpus freeze 47 recaptures the 6,500 UMI requests. No reply is re-authored, and
  every reply's schema validity and every verdict are unchanged.

### Evidence re-entry ownership and fresh ambient perception (freeze 46, 2026-10-21)

- With up to two Goals, the Evidence re-entry decoder makes each decision assignment
  its own native state. New Work can belong only to Goals decided execute; on
  `main` the turn "帮我拿瓶水，顺便告诉我现在几点。" had answered both Goals and still
  re-listed the executed fetch and clock read, and Host rejected it.
- A newer perception observation from the same owner now replaces the one it
  supersedes in the Situation projection. Ambient refreshes used to carry every earlier
  scene revision forward, so Chromie kept stale object positions and, after 16
  revisions, stopped updating.
- Workflow corpus freeze 46 recaptures the 200 re-entry requests. No reply is
  re-authored, and every reply's schema validity and every verdict are unchanged.

### Incremental image builds (2026-10-20)

- `--build` (`BUILD=1 ./scripts/start_services.sh`) now recreates only the
  containers whose image ID changed, instead of force-recreating every service; an
  unchanged model server keeps running.
- The Agent, ASR and TTS Dockerfiles install packages through BuildKit pip/uv
  cache mounts, so a changed dependency layer reinstalls from the local cache
  instead of downloading every package again.
- The ASR and TTS Dockerfiles no longer declare the proxy variables. As Docker's
  predefined build args, they still reach `RUN` but no longer invalidate the
  layer cache when a build runs with or without a proxy.
- The first build after this change reruns those layers once.

### Everyday live repairs: mandatory members, answer source, playback race (2026-10-20)

- Native decoders ignore `contains`, so a required member could be crowded out. The
  streaming Planner now opens its counted Activities with each work or clarify
  decision's own Activity: "我考了满分！快跟我一起庆祝一下！" had decided the
  celebration as work, counted one Activity and spent it on the sibling answer, and
  Host rejected the turn. Social Cognition's first act now names every result need
  that must be said now: "我不会后空翻" said the limitation but bound only the answer
  need, and Host rejected the reply (422). Validation is unchanged, and so is
  workflow corpus freeze 45, which does not store these request formats.
- An information Responsibility that current perception could answer first states
  its `answer_source`, then its observations, then its decision: "帮我拿瓶水，顺便告诉我
  现在几点。" had cited the scene objects for the time, and Host rejected the turn.
- Host playback waits take a waiter settled at the deadline as settled: speech that
  started playing 7 ms before the 3.5 s timeout was reported undelivered.
- Soridormi is pinned at `51a2afa`. A standalone `look_at_person` turns the body
  toward a person beyond the head's turning range (owner decision), and "转过来看着我"
  now passes. Live everyday runs on the local gemma4 12B: smoke 15/15 four times;
  the latest core run reached 12/18 before a transient weather-provider timeout.

### Live smoke of main on the GPU host (2026-10-20)

- An Agent built from `main` `03974435e` is deployed; the everyday `must_pass` smoke
  passed 15/15 on Soridormi MuJoCo, GPU smoke 17/17, gate and strict replay green.
  Status, checkpoint and handoff record the new image and evidence.

### Host derives the Planner's aggregate goal_satisfaction (freeze 45, 2026-10-18)

- The `/plan` model contract no longer has a model-writable Plan-level
  `goal_satisfaction`: the decoder schema and `PlannerModelOutput`
  (`additionalProperties: false`) reject it, and `satisfaction` is now required on
  every Goal outcome of every answer, single-Goal included. Host folds the
  aggregate mechanically from those judgments (lowest score, worst status, unions
  of satisfied/unmet Goal IDs and unmet requirements, joined rationales) through
  one shared helper (`derive_goal_satisfaction`), the rule the Evidence re-entry
  lift already used; in the 6,000-case frozen corpus the model-written aggregate
  equalled this fold in every reference. Plan metadata records
  `model_authored_goal_satisfaction: false` and `host_derived_goal_satisfaction: true`.
  Every semantic check (unavailable cannot claim exact, foreign Goal IDs,
  conservation) now applies to the per-Goal values or the derived aggregate.
  Removing the field from every schema pass and native assignment branch shrinks
  the compact request schema from 138,295 to 101,519 bytes for one Goal and from
  315,090 to 201,819 bytes for two. `/plan-advance` and the Evidence re-entry
  output are unchanged. Authored workflow corpus references drop the retired
  key (`current_contract_reference` projects it out of stored fast replies);
  workflow corpus freeze 45 recaptures every Planner request and projects the
  key out of stored fast replies; no reply otherwise re-authored.

### UMI Responsibilities may share source words (freeze 44, 2026-10-18)

- A Responsibility's `source_evidence` names the first and last token of the
  words it depends on. The model used to name only the end; the Host derived
  every start so spans partitioned the turn, and two Responsibilities that needed
  the same words (news and the feeling about it) failed the whole turn with a 503.
  An authored start is now kept, an absent one is still derived from the previous
  cited end, spans may share words, and only the same Responsibility repeated over
  one span fails closed. Workflow corpus freeze 44 recaptures every UMI request;
  no reply re-authored, every verdict equal to freeze 43.

### Remote inference disclosure policy (2026-10-18)

- A remote provider (`AGENT_LLM_PROVIDER=anthropic` or `openai`) now needs
  `AGENT_REMOTE_INFERENCE_DISCLOSURE` to be set, or the Agent refuses to start.
  `full` keeps the prompts unchanged; `public_only` withholds relational Memory
  and any entry not marked `public` or `self_context` from every role's context at
  the Agent ingress and logs what it withheld. Local providers are unaffected.

### Remote OpenAI-compatible provider: model resolution and schema state (2026-10-18)

- `AGENT_LLM_PROVIDER=openai` no longer reuses a role model key as the remote
  model name: a tag without a colon (`chromie-gemma4-12b` on the RTX 5090 profile)
  used to be sent to the remote service in place of `AGENT_OPENAI_MODEL`. Role keys
  stay local; `AGENT_OPENAI_MODEL_<PURPOSE>` names a remote model for one role.
- The OpenAI-compatible client re-validates each answer against the schema of its
  own request instead of a schema stored on the shared client, so concurrent role
  calls can no longer skip or cross validation.

### Planner decoder shows each disposition/step assignment (2026-10-18)

- The canonical and multi-Goal Planner schemas kept the disposition/step
  assignment only in `allOf`, which native decoders ignore, so the decoder could
  emit clarify, respond or unavailable with steps and execute with none, all
  rejected by the DTO. The final decoder pass now exposes each permitted
  assignment as a native branch (repeated Goal outcomes shared as `$defs`);
  validation is unchanged. Workflow corpus freeze 43 recaptures only the changed
  Planner request formats.

### Claude as a selectable inference provider (2026-10-18)

- `AGENT_LLM_PROVIDER=anthropic` runs every Agent role, UMI included, on Claude
  through the Anthropic Messages API with no code change; Ollama stays the default.
  Local-only assumptions (context window preflight, `num_predict`, sampling options,
  warmup, GPU-tuned timeouts) are translated or skipped at the provider boundary,
  and the full request schema is re-validated before any role parser runs.
- `AGENT_LLM_PROVIDER=openai` does the same for any other remote OpenAI-compatible
  service (`AGENT_OPENAI_BASE_URL`, `AGENT_OPENAI_MODEL`, bearer key from
  `OPENAI_API_KEY`), over the qualified SGLang request shape minus engine fields.
- `scripts/run_workflow_replay.py --candidate-provider anthropic` answers one role
  of the frozen corpus with Claude; a recorded-reference Messages endpoint replays
  each role through the Claude wire path offline.

### Body target descriptions (owner decision, 2026-10-17)

- Soridormi calls describe targets in one format: person by referent (the current
  speaker is the reserved `"requester"`), object by description, place by cited
  name. Soridormi resolves the physical target; Chromie never sends look yaw/pitch,
  and a typed not-found is a reported limitation, never completion.
- Social Cognition decoration may use expressive gestures (nod, look, bow) that
  Soridormi declares low-risk; locomotion stays excluded.

### Everyday live cohort and root-cause repairs (2026-10-13 to 2026-10-16)

- Added the everyday live-text cohort `scenarios/everyday/` (70 cases: a 15-case
  `must_pass` smoke stage that gates `core` and `challenge`) and repaired each
  live failure at its owner: UMI decides meaning uncertainty before meaning and
  orders Responsibility spans; an unsettled referent is clarified, never reported
  as a limitation; information already perceived is answered from the cited
  observation; SC receives a request without agreeing before its Work is decided;
  while a speech Responsibility UMI marked `value_review` waits for Value
  Judgment, its turn admits only an acknowledgement; the local clock is a
  common-tier read.
- Owner identity direction (2026-10-14): Chromie answers as herself and never
  calls herself a robot, AI or device, without false claims about her nature.
- Status, checkpoint and handoff are current-state documents; per-delivery
  history is no longer appended to them. Status holds the single ordered
  open-work list (2026-10-17).

### One Planner: Deep Planner retired (2026-10-11)

- Retired the Deep Planner, `/deep-plan`, Fast-to-Deep escalation and their
  settings (PLANNER-AUTHORITY-001). A Responsibility with no usable Capability
  ends in an honest streamed `unavailable` limitation; conditional composition
  keeps the dependent action in one Plan (2026-10-12).

### Value Judgment (2026-10-11)

- Added Value Judgment (VALUE-JUDGMENT-001, `POST /value-judgment`): one call per
  apply-mode turn whose final Plan uses a Capability listed in
  `capabilities/value_review.json`. `proceed` leaves effects free, `ask` adds a
  confirmation carrying `value_question`, and `decline`, a failed judgment or an
  unreachable endpoint withholds the reviewed effects before provider start.
  Stable Mind adds `respect_others_property`, `respect_privacy` and
  `act_lawfully_and_honestly`, and the Planner projection keeps every core
  principle.

### Need-first Planner and WorkDAG topology (2026-10-09 to 2026-10-10)

- Planner Work begins with `ability_needs`; a non-fitting need triggers one Agent
  library (BM25) search and one more plan with at most eight contracts.
- Planner Activities carry `depends_on`; Host derives execution groups with
  DAGEngine wave semantics.
- The SGLang image backports XGrammar int32 FSM rule IDs so large Planner
  grammars compile, and bounds grammar retention (2026-10-12).

### Social Cognition owns communication

- Social Cognition authors every user-facing Communicative Activity, including
  the first receipt; the Planner returns Work and communication Needs only. This
  supersedes the earlier entry below that moved the first Communicative Activity
  under Fast Planner.

### Goal Association execution projection removal

- Removed the remaining Goal-Association execution projection: `information` and
  `stateful_effect` now survive unchanged from User Meaning Interpretation into canonical Goals,
  and Planner is the first owner allowed to decide Capability-backed HOW.
- Re-grounded Planner capability filtering and direct-speech detection on canonical WHAT
  instead of deleted Goal execution metadata. Typed information-resource Goals cannot be
  answered factually without trusted acquisition/retrieval Evidence, while ordinary
  information may still be answered from already trusted context.
- Removed legacy `capability_work` translation from Goal continuity/Agent Skills and aligned current architecture/API/execution-lane docs.
- Returned `VoiceAssistant` to the structural ratchet (`105` methods) by moving fresh
  capability-state projection into the existing Planner re-entry policy module and
  collapsing restart revalidation helpers into the one orchestration path.

- Bounded Fast User Meaning Interpretation to one mechanical DTO repair and one risk-tiered Deep handoff: benign low-confidence chat stays fast, consequential uncertainty escalates, and repeated malformed or contradictory output fails closed.
- Collapsed physical-object and information fetch/delivery into one canonical
  `AcquireAndDeliverResource` semantic responsibility. `resource.kind` and
  `delivery_mode` now drive provider matching; legacy `responsibility_variant` is
  input-only compatibility, not a planner concept. Capability semantic scopes may
  advertise multiple `delivery_modes`, allowing Soridormi physical delivery and
  weather/external-information acquisition to implement the same human-level
  responsibility without sharing a provider or planning authority.

### Goal Progress Communication

- Restored User Meaning Interpretation to WHAT-only authority. `CognitiveResponsibilityProposal`
  no longer carries work/fresh-evidence readiness flags and cannot emit the old
  `capability_work` planning category; information and durable state-change requests
  remain provider-neutral WHAT categories until Goal Association/Planner project them.
- Moved the latency-critical first Communicative Activity fully under Fast Planner.
  The model may choose one useful progress/complete response **or explicit silence**;
  entering a planning phase never forces a spoken acknowledgement.
- Removed confidence-only Fast/Deep gates. Confidence remains telemetry; material
  uncertainty, consequence, dependency complexity, or a bounded Fast failure decides
  whether deeper planning is warranted.
- Made Reflection an internal evidence-bound advisory path rather than a synthetic
  user Responsibility. Reflection does not directly mutate Goal lifecycle state; any
  replan, clarification, correction, or silence decision returns through Planner.

### Interaction-delta cognition contract

- Restored planner-authored prospective `response_text` for executable Plans;
  response transport remains outside task steps, while Interaction Context—not a
  blanket execute-speech ban—prevents duplicate acknowledgements.
- Made the shared Interaction Ledger / still-needed-delta rule explicit across
  User Meaning Interpretation, Goal Association, Fast and Deep Planning, Tool Result
  Interpretation, and Response Composition.
- Kept the Interaction Ledger as the only cross-stage continuity authority for
  Goal progress speech. Later stages infer the still-needed communication delta from
  actual delivered/pending speech and Goal/runtime evidence; the obsolete
  `fast_interaction_decision` reviewer projection was removed.
- Replaced scenario-answer instructions in coordinated-action review with
  general semantic entailment and Capability-contract principles; concrete
  distinctions remain benchmark/regression responsibilities.
- Reduced Goal Association's canonical contract to provider-neutral `output_mode`
  (plus media operation when applicable). The old `capability_work`,
  `responsibility_kind`, `execution_lane`, and `provider_required` Goal projections
  are removed rather than materialized by the Host; Planner derives HOW from current
  Goal meaning, trusted state/Evidence, and the Capability catalog.
- Removed route-specific hard-coded pre-dispatch failure speech; the bounded
  failure composer now receives the trusted facts and must describe only the
  user-visible missing result/effect without exposing planner/workflow language.

### Post-merge audit remediation

- Registered every normally scheduled interaction utterance in the same
  delivered-turn evidence ledger used by fast-first and cached speech, so played
  final speech can be correlated instead of appearing as an empty delivery.
- Updated generated-speech acceptance to recognize the current
  `cognitive_core_done` semantic receipt and deterministic
  `cognitive_gateway_reflex_applied` interrupt receipt while retaining the old
  User Meaning Interpretation event only for compatibility evidence.
- Made Goal Association resegment mechanical action-collection and location-
  provenance failures from the authoritative turn rather than anchoring repair
  on an invalid DTO, and clarified that stable knowledge and ordinary reasoning
  are spoken responsibilities unless fresh non-vocal evidence is required.
- Replaced the repeated invalid User Meaning Interpreter retry with an error-directed
  typed-contract repair. If the repaired model response still adds durable-only
  fields to explicit session/ephemeral memory, a logged mechanical recovery may
  only remove authority; durable, profile, forget, and clear contradictions
  remain fail-closed.
- Restored source-authored tool acknowledgements under the exact
  `acknowledge_and_check`/`checking_only` claim contract. Playback start remains
  the delivery boundary and de-duplication uses event identity and structured act
  state rather than text comparison. The Interaction-delta contract above
  supersedes the temporary pure-safe-read mute: later stages reuse an equivalent
  Fast act, or may author only a genuinely new prospective conversational delta
  before grounded result/failure speech.
- Added the independently controlled, typed, versioned
  `chromie.interaction_session_capture` Data Loop policy. Each SID snapshots its
  policy at start, reuses existing input/trace/Episode evidence providers, and
  seals complete, abandoned, or recovered immutable packages with explicit
  artifact digests, missing state, governance, runtime identity, and downstream
  candidate provenance. Debug audio and offline evaluation remain independent.
- Added one bounded evidence-preserving repair when Tool Result Interpreter
  output is otherwise grounded but violates its response contract, and made
  decision follow-ups answer the requested decision before the smallest useful
  supporting evidence. Retained-Goal responses now receive an executable
  model-owned communication review from the existing stronger Agent model;
  review may revise response text only and fails closed without effects.
- Preserved valid planless direct speech when optional Social Attention is
  malformed or empty by reducing the auxiliary proposal to explicit stillness
  before nested validation, without selecting behavior or rewriting speech.
- Required direct and planned response composition to ground user-specific
  circumstances in the current turn, Goals, or supplied conversation instead
  of inventing a helpful-sounding personal schedule or situation.
- Corrected semantic-authority, compatibility-fallback, current-status,
  acceptance, configuration, latency, scenario-authoring, and resume-point
  documentation found stale by the audit. Executable weather scenarios now
  assert dynamic pre-effect suppression instead of the obsolete acknowledgement
  requirement.
- Prevented the comprehensive runner from rebuilding an image underneath its
  own running containers, made built services recreate against the new image,
  removed an unsupported dirty-verifier option, and stopped applying the full
  seven-case MuJoCo release verifier to a three-case diagnostic voice bundle.

### Semantic authority and failure honesty

- Added a typed `CoreInterpretationUnavailable` response. A non-empty turn that
  cannot be interpreted no longer becomes generic chat or another invented
  semantic lane.
- Added strict catalog-backed action proposals to capability-grounding repair,
  including ordered compound robot actions with schema validation.
- Moved maintained memory turns into the Goal-driven apply lanes and made
  excluded mapped lanes fail closed without legacy semantic re-entry.
- Kept emergency compatibility planning separately gated and unavailable to
  ordinary maintained turns.
- Split vocal Goal semantics into typed completion modality, lane, output mode,
  and exact-provider need. Mode-specific vocal performance now fails closed
  instead of being completed by generic response text, ordinary TTS, media, or
  body behavior. Mutually inconsistent typed Goal tuples now trigger a fresh
  model-owned resegmentation from the authoritative turn without supplying the
  invalid DTO as semantic evidence.
- Added the exact `chromie.vocal.perform` contract. Qualified providers declare
  mode-specific retained evidence, streaming, timing, sample, concurrency,
  cancellation, and immutable provenance properties; unsupported modes and
  silent downgrades fail closed. Provider vocal Goals now pass through canonical
  planning instead of the ordinary direct-speech shortcut, remain in Vocal
  during cross-lane coordination, and retain one identity through cancellation
  and outcome evidence. The default catalog still advertises no qualified mode.
- Retained clean default-provider Level C evidence for `e558ff4`: the original
  walk/sing/blink turn completed both body members in Soridormi/MuJoCo, kept
  singing unavailable with no step, played all four ordinary-TTS chunks without
  failure, and returned to safe idle. This closes Issue #6's declared source
  scope without claiming a real singing provider or physical audio.
- Added the exact peer-media Activity family
  `chromie.media.play|pause|resume|seek|stop|volume|status`. Qualified providers
  now declare supported media kinds, persistent lifecycle/progress,
  cancellation, mixer parameters, immutable provenance, and operation-specific
  evidence. Exact operation/state mismatches fail closed, speech overlap carries
  an explicit ducking contract without Goal mutation, and stop-talking,
  stop-media, and stop-all produce distinct scoped receipts. The default catalog
  remains unavailable and no physical playback claim is implied.
- Retained default-provider text-to-MuJoCo evidence that keeps media play as an
  unavailable Activity, keeps singing as planless Vocal, completes the
  independent Soridormi walk in a mixed request, and returns safe-idle. The
  primary-text live runner now dispatches deterministic controls through the
  production Cognitive Gateway path and retains its cancellation receipt; a
  Chinese stop-media probe bypasses cognition with exact `media_output` scope.

### Verification and reproducibility

- Made speech-start barge-in reversible: the Host now ducks only the active
  playback generation while ASR distinguishes external speech from likely TTS
  echo, compares distorted ASR against the relevant scheduled output chunks,
  then either resumes the next unplayed chunk or closes and invalidates output
  before the Cognitive Gateway owns semantic cancellation. Focused voice
  acceptance now replays retained output PCM, enforces 250 ms acoustic budgets,
  waits for clean case completion, and retains application-level TTS readiness.
- Replaced the obsolete GPU control-plane smoke flow with immutable Gateway/Core
  requests, typed Core results, current Fast Planner projection, and no `/run`
  dependency.
- Added deterministic source-tree identity for archive builds that do not
  contain `.git`, while retaining Git revision and dirty-state metadata for
  development checkouts.
- Added benchmark integrity checks to the canonical test entrypoint.
- Restored the incremental Mypy gate to its last dependency-complete, verified
  four-file baseline after an unexecuted package-scope expansion exposed 169
  pre-existing type errors in CI. Package expansion remains separate cleanup
  work and may return only after the complete added scope passes.
- Added a fail-closed vocal Issue #1 closure runner that binds the canonical gate,
  deployment identity, exact typed Goal/Plan evidence, Soridormi/MuJoCo body
  completion, honest singing unavailability, and optional authenticated Issue
  closure to one clean revision. The runner now understands the canonical keyed
  `goal_outcomes` map, reuses or starts the maintained headless paired stack,
  stops before downstream work when a prerequisite fails, and retains the exact
  command error instead of a generic failure label.
- Pinned third-party GitHub Actions by commit and added Python 3.11/3.12 CI
  coverage for the GPU-free control plane.
- Reduced default unit-test console noise while preserving warnings and errors.

### Architecture and documentation

- Updated semantic-authority, runtime-rollout, API, configuration, runbook, and
  status documentation to match the maintained lanes and typed unavailable
  contract.
- Replaced stale copied source metrics with executable ratchets and marked the
  composition-root method-count reduction as active rather than complete.
- Removed obsolete implementation plans, handoff snapshots, historical audit
  narratives, and legacy runtime documents after migrating durable facts to
  current architecture, policy, status, roadmap, API, and operations owners.
- Lowered documentation-surface ratchets to the consolidated current tree.

### Existing maintained foundations

- Cognitive Gateway admission, immutable turn envelopes, User Meaning Interpretation,
  Goal Association, Fast/Deep planning, response composition, trusted capability
  execution, and outcome evidence remain the maintained control-plane path.
- Deterministic stop, cancellation, confirmation revocation, playback ordering,
  typed configuration ownership, repository policies, benchmark integrity, and
  release-provenance checks remain in force.
- Agent Skills remain passive cognitive content; capability providers and the
  Host retain effect authorization and execution authority.
