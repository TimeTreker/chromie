# Chromie Development Checkpoint

This is the stable resume boundary: active Issue, implemented contracts, evidence limits,
repairs and owner decisions. Replace it on delivery. [STATUS](docs/STATUS.md#current-open-work)
owns the ordered open-work list; [Handoff](HANDOFF.md) owns volatile identities/commands.
History belongs in Git and [CHANGELOG](CHANGELOG.md).
The current focus remains Goal-driven single-authority architecture.


## Active Issue — everyday live-cohort root-cause repairs

The fixed-model simulator comparison used feature baseline `5368d2cab` plus the retained
catalog fix and Planner evidence-source selection. The later personal-profile store fix
was verified separately. Preserve WHAT-only UMI, Goal identity,
Planner ownership of work, SC wording and all 28 role-budget settings.

## Resume point — Planner evidence and memory

The archived dog-name and bottle-count requests both supplied the needed information.
For recall, the old Planner had chosen new work or cited the current speaker. For counting,
its ordinary response form forced an empty observation list. The Planner now selects actual
dialogue, activated Memory and established scene records from the same candidate set. The
existing validators resolve exact source identifiers before generating an SC communication
need. Capability ranking strips English possessive suffixes while preserving the other
20 of 24 archived unmet-need rankings. No example words route a task.

The integrated fixed-input cohort passed five of seven. The original ten and all 207
simulator cases ran on the frozen Planner application. On the common 128, 85 were complete
and 13 of the original 28 regressions recovered. On the disjoint 79, 45 were complete.
The unshown drawing, date provenance, unavailable care and reminder promises, cross-session
facts and unapproved food substitution remain open. A timeout in the additional nine-turn
case left eight terminal summaries and did not prevent later cases from entering the Host.
[Handoff](HANDOFF.md) points to actual deliveries, per-case judgments and runtime identities.

The protected store now preserves two people's records with the same attribute, rechecks the
disk when managers share the file, respects the requester when forgetting, and rolls back
failed writes. Three new reproductions failed before the fix. All 14 profile tests passed
on the delivery branch, including a fourth check for retained legacy identifiers. Existing schema-version-1
entries retain their original identifiers. The approved close-time experiment remains
outside the runtime. Its fixed native outputs gave correct profile contents in 16/19 cases,
but the model marked every overview private. Honouring that output withheld every
substantive summary. Hapi survived a restart and remained visible only to the bound speaker.

## Owner decisions in force

- One close-time summary may recover a missed enduring self-fact from the original user
  utterance. Validate this independently, retain provenance and respect withdrawals.
- Keep complete WHAT-only UMI, Planner HOW/Skills, SC expression and model/budgets/rules.
  Branch-only diagnostic commit/push is authorized; never merge Main without approval.
- Pure action demonstrations are functional tests and remain in Smoke; artificial
  compound/ordering probes remain functional Core. Daily scenes need plausible life
  or communication motivation. Do not remove failed cases to raise reported quality.
- Current keep-going completes diagnosis but waives no hard gate. Next general repairs
  follow STATUS in existing owners; global cardinality/meaning/lifecycle changes require
  an explicit concrete amendment. The eight authorized iterations have ended.

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
  by UMI as the requested information, without an execution/output category. The Planner reads it; SC only communicates: it may say it will check
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
  a valid proposal attached to an unplayed ingress acknowledgement can still be lost when the final Work response supplies the spoken promise (prior cohort85; current comparison87). The delivery-bound handoff needs repair; do not replace the primary SC memory decision with a second extractor.
- Value Judgment asks before Chromie takes or uses another family member's personal things
  (a parent's wallet or phone) unless the words show that person agreed; the person's own
  things and things the household shares proceed (owner decision 2026-10-21).
- A provider that declared it did not complete and did not move, with a safe-idle final
  state, reported honest Evidence: the acceptance runner judges that case by its expectations
  and keeps collecting (owner decision 2026-10-21). Safety, service, provenance, contract and
  LLM-integrity failures remain hard gates. The current owner-authorized diagnostic run uses
  keep-going to retain all cases without treating those failures as passes.
- A person beyond the head's turning range is looked at by turning the body first, inside
  Soridormi (owner decision 2026-10-20). A standalone `look_at_person` turns on a walking
  arc at the slowest gait pace, because pure in-place yaw barely turns this gait. It keeps
  0.5 m clearance and never turns during a locomotion overlay.

## Next work

Ordered next work and blockers: [STATUS — Current open work](docs/STATUS.md#current-open-work).

Claim boundary: no qualified cohort, no physical evidence and no release. Do not
claim a native semantic pass or behavioral improvement beyond the judged runs.
