# Chromie project principles and implementation audit

**Audit date:** 2026-09-12. **Revision:** `191083dc85ef8f9131eaadb2223660f58ad6f217`, `main`. The tracked working tree was clean before and after the audit.

**Audience:** project owner and maintainers implementing the linked Issues. **Owner:** the project owner owns audit decisions; the linked Issues own follow-up work. This is a point-in-time review, not a maintained architecture authority. [Project Charter](docs/PROJECT_CHARTER.md) and [Current Status](docs/STATUS.md) retain their existing authority.

**Publication scope:** the owner requested this report in GitHub, actionable Issues, and a committed checkpoint/handoff. The audit itself changed no implementation, configuration or deployed service. This publication replaces the existing report at this path; the [2026-08-28 review remains in Git history](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/ARCHITECTURE_AUDIT.md). No new standing document is needed: maintained Markdown files remain 102, root-level docs remain 58, and the core reading path remains 15. No runtime switch or architecture term is added. Consolidating older handoff narrative after retaining its evidence remains an opportunity.

The reproducible synthetic probe code and observed outputs are included below. Full local audit artifacts remain under `.chromie/acceptance/project-wide-audit-20260912/`; older private model/service evidence is referenced by exact path but is not published. A fresh clone can rerun the synthetic probes; it cannot independently recover the private live evidence from this report.

**Assessment:** the central ownership model is broadly coherent: GI owns WHAT, GA owns Goal continuity, Planner owns HOW and ordinary speech, and Runtime/Providers own execution and evidence. The strongest problems found are failures to carry that model through input projection, concurrent execution, staged progress, cancellation reporting, and Reflection integration. The current target profile also remains unqualified. A broad redesign is not supported by this audit; several concrete existing-owner repairs are.

The distinction matters: some current failures cannot be fixed by selecting a better model. A model cannot preserve authoritative Goal meaning omitted from its prompt, repair contradictory execution-permission instructions, or enforce resource exclusion between independent Runtime submissions.

**Evidence and coverage**

This review examined the Charter and current interaction/authority contracts; current checkpoint, status and relevant retained handoffs; GI/GA/Planner invocation and normalization paths; Host completion/Reflection wiring; resource arbitration; confirmation, cancellation and evidence boundaries; configuration and qualification claims; and relevant tests. Historical artifacts were used as revision-specific evidence. Source inspection was risk-based across components, not a line-by-line proof of every file. Soridormi's implementation and actual device behavior were not audited here.

Fresh verification on this revision:

| Check | Observed result | Claim limit |
| --- | --- | --- |
| `./scripts/run_tests.sh` | Exit 0; 2,480 tests, 771 subtests, 145 benchmark tests, 20 legacy Agent tests; two existing FastAPI deprecation warnings | Local source/contracts; no model or robot qualification |
| Included policy/configuration/docs/static gates | Passed; 15 policy families, zero reviewed exceptions | Their declared rule sets only; Mypy currently checks five source files |
| `python scripts/semantic_authority_audit.py` | Passed | Declared ownership guard coverage |
| `python -m tools.chromie_cli capability check` | Passed; seven Agent records and 27 tools | Static manifest; live probe not requested |
| Fresh Planner projection probe | Eight valid retained Goals became three Goals' meanings in both Fast and Deep prompts | Reproduced input loss; no inference was invoked |
| Fresh resource probe | Same-resource work rejected in one parallel Plan, but two separate interactions both completed with peak concurrency 2 | In-process mock providers; no physical safety incident claimed |
| Fresh Reflection workflow probe | Result Planner did not start while Reflection was pending; actual Reflection context had no Mind | Real Host closure method with scripted dependencies |
| Fresh Reflection advisory probe | Advisory present in request context but absent from both rendered Planner prompts | Prompt boundary only |

The reproduction appendix retains the synthetic probe code and outputs for the audited revision. Logs, individual probe outputs and the original source identity remain in the local artifact directory above. Passing the existing suite alongside these reproductions shows specific coverage gaps; it does not invalidate the suite's existing protections. No new live-model cohort, general-ability acceptance run, microphone/speaker test, deployment, simulator exercise, or physical motion was performed.

**Issue order**

A01–A08 are report finding IDs. The GitHub mapping below is verified at publication; priorities are audit recommendations. P1 means resolve before the affected target qualification or promotion. P2 means a concrete integration or documentation defect with narrower immediate impact. Opening an Issue records the work; it does not mean the defect is fixed or a contract amendment is approved.

| ID | Priority | Issue / proposed work | Basis / existing work |
| --- | --- | --- | --- |
| A01 | P1 | [#49](https://github.com/TimeTreker/chromie/issues/49) — Enforce declared resource conflicts across concurrent interactions | New local reproduction |
| A02 | P1 | [#50](https://github.com/TimeTreker/chromie/issues/50) — Preserve all authoritative Planner inputs or reject before inference | New local reproduction |
| A03 | P1 | [#51](https://github.com/TimeTreker/chromie/issues/51) — Separate valid next-stage progress from whole-Goal satisfaction | Existing unresolved #35 contract conflict |
| A04 | P1 | [#52](https://github.com/TimeTreker/chromie/issues/52) — Keep cancellation reporting permission separate from Goal meaning and capability availability | Existing unresolved #35 projection/oracle conflict |
| A05 | P2 | [#53](https://github.com/TimeTreker/chromie/issues/53) — Remove Reflection from the aggregate result-response critical path | New local reproduction |
| A06 | P2 | [#54](https://github.com/TimeTreker/chromie/issues/54) — Complete the Stable Mind → Reflection → Planner context handoff | New source/projection reproductions |
| A07 | P1 | Qualify one complete deployable cognition profile and close current-revision evidence | Existing [#24](https://github.com/TimeTreker/chromie/issues/24) / [#32](https://github.com/TimeTreker/chromie/issues/32) / [#35](https://github.com/TimeTreker/chromie/issues/35) blockers |
| A08 | P2 | [#55](https://github.com/TimeTreker/chromie/issues/55) — Make current evidence summaries and capability documentation revision-accurate | Current documentation drift |

Suggested implementation sequence: A01 → A02 → A03 → A04 → A05 → A06 → A07. Incorporate A08 corrections into the relevant deliveries. Keep A07's evidence work attached to the existing qualification line. A03 and A04 are bounded repair follow-ups under #35; they do not duplicate its complete qualification scope. A07 stays with the three existing qualification Issues.

<a id="a01"></a>

**A01 — Enforce declared resource conflicts across concurrent interactions**

**Conflict:** the Charter requires Runtime to contain resource conflicts and permits overlap only when declared resource contracts allow it. The implementation checks a resource set within a Plan but its shared execution arbiter locks only one `exclusive_group` string. Different interactions therefore do not receive the same protection.

Sources: [Charter scheduling contract](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/PROJECT_CHARTER.md#L589), [within-Plan conflict check](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/runtime/cognitive_runtime.py#L679), [Runtime acquisition](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/runtime/capability_runtime.py#L2641), [ResourceArbiter](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/shared/chromie_runtime/scheduling.py#L47).

| Boundary / owner | Actual probe input → output | Expected / verdict |
| --- | --- | --- |
| Capability definitions | Two valid definitions; both parallel-capable; same `resource_claims=[audit.shared.output]`; distinct exclusive groups | Resource overlap remains authoritative across submissions |
| Plan adapter | Both steps in one parallel Plan → `runtime_parallel_resource_conflict` | Correct local validation |
| CapabilityRuntime | Each capability submitted in a separate interaction → both accepted | Individually valid submissions still need shared arbitration |
| ResourceArbiter → mock provider | Distinct group locks → both provider calls active simultaneously; both completed | **Incorrect cross-interaction exclusion**; peak should be 1 or one submission should reject |

The initiating condition is concurrent independent submissions. The earliest missing guarantee is shared Runtime resource acquisition, not Planner capability selection. Within-Plan checks cannot protect later independent submissions. This is a code/contract enforcement gap. Soridormi may independently reject physical conflicts; that separate containment was not exercised and does not establish the general Host guarantee.

**Proposed repair:** make the existing arbitration/registration boundary enforce the declared overlapping resource sets, or reject contracts it cannot enforce. Define how provider resource namespaces and compiled groups map to those locks. Preserve Soridormi's provider-local physical safety authority; do not add a second resource manager.

**Closure:** concurrent separate Plans and separate interactions sharing any declared exclusive resource serialize or reject; disjoint resources overlap; acquisition is deadlock-free for multiple resources; cancellation while waiting releases capacity; personal-voice exclusion and provider-group compilation still pass. Retain a real Runtime test, not only a Plan-validator test.

Evidence: `resource-arbitration-probe.json` and `combined-probes.json`.

<a id="a02"></a>

**A02 — Preserve all authoritative Planner inputs or reject before inference**

**Conflict:** principles 30–31 require complete accepted meaning to remain authoritative downstream. Both Planner prompts use an optional-context truncator for final canonical Goals. That truncator silently removes whole list entries. The request and output contract can still expect all Goal IDs.

Sources: [lossy helper and existing lossless alternative](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/prompt_projection.py#L33), [Fast final grounding](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_prompt.py#L475), [Deep final grounding](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_prompt.py#L1211), [canonical projection](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_context.py#L262).

| Boundary / owner | Actual probe input → output | Expected / verdict |
| --- | --- | --- |
| Typed Goal / GA contracts | Eight valid retained speech Goals and eight continuation associations | Correct admitted inputs for the probe |
| Planner Goal context | Eight canonical expected Goal IDs and all eight meanings | Correct |
| Fast and Deep prompt rendering | Final blocks each contain only three Goals; the other five unique meaning markers occur nowhere in either prompt | **Incorrect: silent loss before model invocation** |
| Model / result validator | Not invoked by this probe | Their behavior is unproven; downstream rejection or omission is a risk, not an observed spoken outcome |

This reproduces a general context-budget boundary, using moderate repeated descriptions and success criteria. It is not a claim that eight Goals always fail. The important contrast is within-budget versus over-budget authoritative state. Exact source wording cannot authorize Planner to reconstruct missing upstream meaning, particularly for retained Goals whose details are absent from the new turn.

The same helper appears on trusted execution outcome, terminal Evidence, source Plan and retained Work projections. Their overflow behavior needs inclusion in this issue; only Goal loss was dynamically reproduced here.

**Proposed repair:** use the existing lossless/fail-explicit projection mechanism for required transaction inputs and keep the output Schema's scope aligned with what is actually supplied. Reduce incidental duplication or formally scope a transaction before projection. Do not silently select a smaller semantic scope or simply increase a character limit and call the problem solved.

**Closure:** bilingual one/multiple-Goal and evidence-reentry contrasts at, below and above budgets; every required Goal/binding/Evidence field reaches inference intact, or the call is rejected before any commitment. Include both depths and layered production prompts. No omitted Goal may acquire a fabricated completion outcome.

Evidence: `planner-projection-probe.json`. Classification: `context_or_harness`, specifically production prompt projection.

<a id="a03"></a>

**A03 — Separate valid next-stage progress from whole-Goal satisfaction**

**Conflict:** event-driven cognition permits acquisition followed by further planning when new Evidence arrives. Deep's prompt permits read-first work, but its whole-Goal satisfaction threshold rejects that same valid intermediate stage.

Sources: [read/then-reentry architecture](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/PROJECT_CHARTER.md#L382), [Deep prompt](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_prompt.py#L1183), [threshold enforcement](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_deep_validation.py#L48), [existing diagnosis](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/HANDOFF.md#L136).

Retained episode: “Check Hangzhou tomorrow morning and remind me at 7:30 only if rain is forecast.” Case `dpdl_v1_fast_escalation_without_candidate_leakage_02_boundary_en`.

| Boundary / owner | Retained input → actual output | Expected / verdict |
| --- | --- | --- |
| Canonical Goal and catalog | Conditional reminder plus exact location/time bindings and an available weather read | Read can establish the condition; no reminder effect yet |
| Deep primary result | Correct `acquire_information` step; reminder deferred; overall satisfaction `partial`, score 0.6 | Legitimate next-stage proposal; not complete fulfillment |
| Deep Host validator | 0.6 below 0.75 → `goal_satisfaction_below_threshold` | **Contract conflict** between stage admission and whole-Goal adequacy |
| Resolver → Runtime | Silent fail-closed clarification result; zero steps, `execution_allowed=false` | Correct containment of its current rule; useful acquisition is blocked |

This is already explicitly retained as a failed case under #35. It is not evidence of bad weather arguments and should not be repaired by telling the model to inflate satisfaction. The Chinese counterpart's different judgment does not close the contract ambiguity.

**Proposed decision and repair:** agree what a complete admissible *current stage* means while an overall Goal stays open. Express that consistently in the existing Plan/outcome contract, Schema, prompt, validator and reconciler. Preserve all deferred requirements and forbid conditional effects before qualifying Evidence. This changes contract meaning and should receive explicit owner agreement when implemented.

**Closure:** this exact case and its language contrast progress through read → immutable Evidence → next Planner decision; the Goal stays open until the reminder obligation is resolved; the negative forecast path does not write a reminder; honest intermediate satisfaction is accepted without weakening effect/confirmation/completion barriers. Rerun full Fast and Deep cohorts.

Evidence: retained Host replay: `.chromie/acceptance/open-issue-closure-20260911/deep-final/conditional-read-host-replay.json` (private local artifact), retained 40-case review: `.chromie/acceptance/open-issue-closure-20260911/deep-final/semantic-review.json` (private local artifact). No fresh model inference was run in this audit.

<a id="a04"></a>

**A04 — Keep cancellation reporting permission separate from Goal meaning and capability availability**

**Conflict:** principles 18, 28, 31 and 38 separate execution facts, user meaning, capability truth and current authority. Cancellation reentry sets `response_only`; Deep then empties the executable catalog and describes the canonical Goals as “provider-free direct speech responsibilities.” A restricted invocation has been confused with different Goal meaning and absent capabilities.

Sources: [cancellation context](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_context.py#L687), [catalog suppression](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/deep_planner.py#L154), [misleading prompt contract](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/planner_prompt.py#L1106). Fast uses the same response-only wording pattern and should be covered by the repair.

| Boundary / owner | Retained input → actual output | Expected / verdict |
| --- | --- | --- |
| Control/Evidence | One case reports cancellation; another reports `not_cancelled` with stale confirmation released | Preserve exact control outcome and open sibling/effect obligations |
| Planner context/prompt | Effect Goal + communication-only permission → empty executable catalog and direct-speech description | **Earliest wrong projection:** scope is neither a WHAT rewrite nor global capability absence |
| Deep primary result | Cancellation cases: truthful speech, no Work, `unavailable`; released-confirmation cases: fresh confirmation request in English, “reminder unavailable” in Chinese | First pair has oracle/contract ambiguity; second pair shows incorrect interpretation encouraged by the projection |
| Host/oracle | Host accepts the reported cancellation outputs; frozen oracle requires `respond` | Resolve legitimate disposition semantics; do not relabel the frozen failures retroactively |
| Runtime/provider | No reminder dispatch | Correct effect containment; speech truth/continuity remains defective |

**Proposed repair:** preserve canonical effect Goal meaning and separately state this invocation's permission to communicate. Provide the capability facts needed for truthful reporting without making them executable in a restricted scope. Specify cancellation-confirmed versus stop-unverified versus confirmation-released outcomes. Do not reopen execution or borrow a sibling's authorization.

**Closure:** all four retained bilingual cancellation cases plus available/unavailable provider contrasts; zero unintended Work; no false global limitation; no fabricated successful cancellation; stale tokens stay revoked; unfinished effects remain accurately represented. Freeze a new oracle identity with a written justification, retain old failed outputs, then rerun both Planner cohorts. Attach to existing #35.

<a id="a05"></a>

**A05 — Remove Reflection from the aggregate result-response critical path**

**Conflict:** the interaction contract says foreground cognition must outrank background Reflection, and the architecture permits useful action whenever local inputs are ready. Aggregate closure waits for Reflection before invoking its result Planner, even when trusted terminal Evidence is already available.

Sources: [foreground contract](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/HUMAN_LIKE_INTERACTION_CONTRACT.md#L537), [blocking gather](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/orchestrator.py#L4449), [later result planning](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/orchestrator.py#L4613).

The fresh probe exercised `_close_cognitive_execution` with one failed and one completed mock capability. Real reconciliation generated a slow opportunity. A controlled Reflection stub remained pending: the result Planner had not been called. Releasing Reflection allowed the Planner call. No elapsed live latency is claimed; the dependency itself was reproduced. The call uses the Deep timeout, whose default is 125 seconds.

**Earliest boundary:** Host closure scheduling, not inference-provider throughput. Incremental result paths can communicate earlier in other episodes; this finding concerns the aggregate fallback/closure path and does not claim all responses block.

**Proposed repair:** let the result Planner consume ready authoritative Evidence without awaiting optional learning. Run permitted Reflection under bounded existing background lifecycle ownership, with explicit cancellation and expiry. Its later result must remain future advisory context and must not force review of an already-complete semantic decision.

**Closure:** a deliberately blocked/timed-out Reflection does not delay eligible result planning; shutdown and cancellation leave no orphan tasks; no duplicate response or Work; a late Reflection result cannot reopen terminal Goals. An event-order test is required in addition to latency measurements.

Evidence: `reflection-workflow-probe.json`. Classification: code/workflow mismatch.

<a id="a06"></a>

**A06 — Complete the Stable Mind → Reflection → Planner context handoff**

**Conflict:** principle 26 and the configuration contract say Reflection receives owner-approved worldview/values. The actual Host request omits `mind`. Separately, Host forwards `reflection_advisories` into Planner context, but both Planner prompt renderers omit them.

Sources: [documented Reflection input](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/CONFIGURATION.md#L332), [actual context assembly](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/orchestrator.py#L4410), [Reflection prompt](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/agent/app/reflection.py#L158), [advisory forwarding](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/orchestrator.py#L6107).

| Boundary / owner | Probe input → actual output | Expected / verdict |
| --- | --- | --- |
| Configured Host Mind → Reflection request | Host has a Mind owner; generated request contains Goal snapshots/Plan/outcome but no `mind` | **Incorrect missing configured context** |
| Reflection request → prompt | Owner-approved Stable Mind JSON renders `null` | Required configured worldview/value projection should be present |
| Reflection advisory → Planner request | A bounded advisory is present under `reflection_advisories` | Retain its advisory status and exact evidence scope |
| Planner request → Fast/Deep prompt | Unique advisory marker absent in both prompts | **Incorrect dropped handoff**, unless the feature is explicitly retired |

The Host also uses advisory presence to bypass already-handled Evidence suppression. Thus an omitted advisory is not merely unused metadata: it can affect whether another Planner call happens while its content is absent from that call. A duplicate spoken response was not demonstrated in this audit.

**Proposed repair:** use the existing canonical Mind projection in Reflection requests. Decide whether Reflection's current-turn advisories belong in the authorized architecture; if retained, project them explicitly as bounded, evidence-grounded advisory input. If they do not justify another call, remove that reentry dependency instead. Preserve Planner's sole speech authority and Reflection's prohibition on rewriting history or global policy.

**Closure:** test the real Host-to-Agent request, not only a hand-assembled resolver request; changing an allowed worldview/value changes Reflection input; unsafe/private material stays filtered; an accepted advisory either reaches its intended consumer intact or causes no reentry. No advisory may reopen a completed decision or directly author delivered speech.

Evidence: `reflection-workflow-probe.json`, `reflection-advisory-probe.json`. This can be implemented with A05, but separate acceptance criteria prevent a scheduling fix from hiding the missing context.

<a id="a07"></a>

**A07 — Qualify one complete deployable cognition profile and close current-revision evidence**

**Mismatch:** the implemented concurrency/interaction design is ahead of the available target evidence. The current Status correctly says unqualified. This is an existing product-delivery blocker, not a newly discovered reason to weaken principles.

Reviewed retained evidence:

- The rebuilt-Agent 51-case preview stopped after one complete GI failure, one partial startup and 49 unrun cases. The reviewed episode requested ordered walk at speed 0.2 for 10 seconds, two nods, then a left turn. GI merged it into one Responsibility; its guard rejected. GA, Planner and requested provider dispatch were not invoked. Correlation: SID `4800df1d`, call `llmcall_goal_interpreter_4d9954acf7ff4523`.
- Native Fast probes recorded 2/8 Host acceptances for each of the three local candidates. Early presentation acceptance did not establish a valid terminal Plan, and generated/discarded audio did not establish playback.
- Offline surrogate Fast passed 204/204; Deep retained 35/40 frozen hard passes, with the five failures discussed above. This does not qualify the local models or the deployed HTTP/Skill-disclosure transaction.
- The current handoff records single-resident-model observations and foreground first-token delays of 6.256–6.351 seconds under the contention probe. Those measurements are not the specified GI-handoff-to-commit or commit-to-playback intervals and do not establish interactive qualification.

Sources: [current Status](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/STATUS.md#L15), reviewed live episode: `.chromie/acceptance/open-issue-closure-20260911/iteration-04/manual-review.json` (private local artifact), native Fast results: `.chromie/acceptance/open-issue-closure-20260911/model-comparison/json-stream-final/summary.json` (private local artifact), [resource/latency handoff](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/HANDOFF.md#L102).

**Causality:** the reviewed live case first fails at GI output, with correct fail-closed containment. The Deep failures include contract/projection problems, so they cannot all be attributed to model capability. Provider contention is a separately measured contributor. No single diagnosis explains every failed case.

**Proposed work:** after repairing proven contract defects, qualify one declared model/provider/resource configuration through the exact production transactions. Measure semantics first and preserve failed slices. Then run contention with TTS, retaining queue/first-token/validated-commit/first-PCM/playback intervals separately. Finally run the complete directory-discovered live cohort and current-revision target-evidence profile on one fixed revision/runtime identity.

**Closure:** role/cohort hard gates and semantic judgments pass; the complete current-revision evidence profile closes; the warm communication targets are met under the declared workload; current voice proof is retained under supervision. Simulator qualification is the core embodied target. Physical-robot deployment remains optional. Keep #24, #32 and #35 open according to their own unsatisfied criteria; do not substitute surrogate or older-revision evidence.

<a id="a08"></a>

**A08 — Make current evidence summaries and capability documentation revision-accurate**

**Mismatch:** some maintained summaries still present historical or obsolete information under current labels, despite accurate current Status/checkpoint entries.

Concrete examples:

- [Acceptance's “Current evidence summary”](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/ACCEPTANCE.md#L81) includes a “Narrow current-revision live voice loop” row supported by `90aa72a`, `a36444b` and an August 9 supervised turn. Those are explicitly identifiable historical revisions, not evidence for audited `191083dc`.
- [Capability README](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/capabilities/README.md) says the checked-in snapshot has six Agent records and twenty tools. The current static audit reports seven and 27. The same README still describes an “Orchestrator Skill Registry” and says the Agent Skill registry is planned, while the current implementation uses Capability terminology and implemented Agent Skill discovery/disclosure.

**Cause:** duplicated current-state claims outside their authoritative owners drift. The documentation gate passes because link/config/ownership checks do not establish semantic freshness of every paragraph.

**Proposed repair:** label historical evidence with its exact revision and keep the current row explicitly unqualified until closure. Correct or derive manifest counts, remove obsolete registry terminology, and link implementation status to its existing owner. Preserve historical evidence rather than deleting it. Handoff history is a consolidation opportunity, not a file-length defect by itself.

**Closure:** a new reader can identify the current revision's implementation, automated verification, target evidence and release status without reconciling contradictory “current” summaries. No new standing document, architecture term, or runtime flag is needed.

**Core-principle review: boundaries that should be preserved**

| Principle family | Audit conclusion |
| --- | --- |
| GI WHAT / GA continuity / Planner HOW; primary-result authority | The main implementation follows the declared split. No general same-tier semantic repair chain was found in the inspected primary GI/Fast/Deep paths. GA's narrow repair has explicit preservation checks. A02, A04 and A06 are concrete input/handoff defects, not a reason for a second semantic judge. |
| Immutable Evidence, exact correlation, truthful completion | The retained live GI failure was correctly contained before Work. Source/tests cover request correlation, output-schema qualification, stop uncertainty and actual delivery. A03/A04 show why coverage, completion, permission and capability truth must remain distinct. No physical completion guarantee is claimed by this review. |
| Fail-closed execution, deterministic controls and provider safety | Confirmation binds request identity, expiry and single use; Runtime validates registered capability, arguments, confirmation and monitor requirements. A01 exposes a missing cross-interaction resource guarantee. Soridormi continues to own physical safety. |
| Event-driven progress, independent planning and responsive speech | The main asynchronous/typed-stream design is implemented. A05 is a remaining blocking dependency; A07 is a qualification gap. Parallel Python tasks alone do not establish inference concurrency. |
| Stable identity, bounded Memory, privacy and forward learning | The person-like social Self and truthful robotic embodiment are compatible design layers. Existing tests cover consent/retention and bounded learning; A06 finds a real configured-context omission. Multi-person social quality and concrete perception remain unqualified. |
| One Planner speech owner; optional social decoration | Inspected ordinary paths preserve Planner wording and distinct delivery evidence; decoration is subordinate. Optional startup speech is a separate documented opt-in and deserves the clarification below. |
| Simulated versus physical embodiment | Different realization/provider safety does not justify different cognitive semantics. Sequential physical WorkDAG nodes and provider-internal compilation of compatible body actions are different granularity contracts, not automatically contradictory. |
| Simplicity and reconstructability | Do not split large files solely to meet counts. The demonstrated repairs belong to existing prompt projection, Runtime arbitration, Plan contracts and Host context/scheduling owners. |

**Design clarification to keep separate from confirmed defects**

The [optional startup greeting path](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/orchestrator/orchestrator.py#L7337) still performs direct Host-owned generation and can try a second candidate after failure. The [interaction contract](https://github.com/TimeTreker/chromie/blob/191083dc85ef8f9131eaadb2223660f58ad6f217/docs/HUMAN_LIKE_INTERACTION_CONTRACT.md#L800) explicitly permits opt-in startup speech, while ordinary communication is Planner-owned and same-owner semantic review is prohibited. Startup speech is default-off and occurs outside an admitted user turn, so this audit does **not** classify it as a proven violation of the ordinary-turn rule.

Clarify whether that narrow lifecycle exception intentionally includes direct generation and retry, or whether it should use the existing Goal-free Planner communication path. An explicit documented exception or consolidation is preferable to extending the special path. This is an owner decision, not a request to introduce another speech service.

**Implementation and qualification discipline for the proposed Issues**

For each implemented repair: retain its originating probe/episode, add a regression at the first wrong boundary, prove the predicted mechanism, run the affected general-ability class when behavior changes, and run canonical gates. Semantic changes require fresh frozen Fast/Deep inputs and full reruns; live revision-level claims require the aggregate cohort and target evidence. Keep source, surrogate inference, deployed models, audio and simulator/robot evidence separate.

This audit's fresh findings are source/Level-A evidence. Fail-first repair testing is not applicable because no fix was made. Live behavior and unseen-language completeness remain unproven. No P0 physical safety incident or unconditional system-wide correctness claim is made.

**Reproduction appendix**

The following code uses existing in-process fixtures, actual prompt rendering and real Runtime/Host boundaries. It invokes no model, service or device. Its results expose defects; a successful script exit does not mean those contracts pass. Results are specific to the audited revision and must be reassessed after repairs. Use the repository test environment described in [Contributing](CONTRIBUTING.md).

From the repository root, run the Python block embedded in this report:

```bash
python - <<'PY'
from pathlib import Path
report = Path("ARCHITECTURE_AUDIT.md").read_text()
code = report.split("```python\n", 1)[1].split("\n```", 1)[0]
exec(compile(code, "audit-probes-20260912", "exec"), {"__name__": "__main__"})
PY
```

<details>
<summary>Reproducible synthetic probes — audited revision 191083dc</summary>

```python
"""Read-only diagnostic reproductions for the 191083dc project audit.

Run from the repository root with PYTHONPATH=. . No model, service, or device is
invoked. Existing test fixtures supply in-process providers and Host setup.
Outputs describe observed behavior, not passing regression expectations.
"""
import asyncio
import json
from types import SimpleNamespace

from agent.app.deep_planner import DeepPlannerResolver
from agent.app.planner_context import planner_goal_context
from agent.app.planner_prompt import fast_plan_prompt, deep_plan_prompt
from agent.app.reflection import ReflectionResolver
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition, CapabilityRegistry, CapabilityRuntime,
    CapabilityRuntimeResult, MockCapabilityProvider,
)
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from shared.chromie_contracts.goal import GoalAssociation, GoalAssociationResolution
from shared.chromie_contracts.interaction import CapabilityResult, InteractionResponse
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.semantic_task import SemanticGoal
from tests.capability_runtime_test_support import submit_and_wait_terminal
from tests.cognitive_work_test_support import cognitive_work_request
from tests.test_cognitive_turn_loop_closure import (
    CognitiveTurnLoopClosureTests, _plan, _response, _Runtime,
)


def projection_probe():
    goals = []
    for i in range(8):
        description = (
            f'Responsibility {i}: explain the supplied topic with its qualifications. '
            + 'Preserve the specific boundary and the requested comparison. ' * 5
            + f' REQUIRED_DETAIL_{i}'
        )
        goals.append(SemanticGoal(
            goal_id=f'audit-goal-{i}', description=description,
            source_text=description, success_criteria=[description],
            metadata={'output_mode': 'speech'},
        ))
    association = GoalAssociationResolution(
        turn_id='audit-turn', resolution_status='resolved', confidence=1.0,
        associations=[GoalAssociation(
            association_id=f'audit-assoc-{i}', relationship='continue',
            target_goal_ids=[goal.goal_id], confidence=1.0,
        ) for i, goal in enumerate(goals)],
    )
    context = {
        'goal_association_resolution': association.model_dump(mode='json'),
        'active_goal_snapshots': [
            {'goal_id': goal.goal_id, 'goal': goal.model_dump(mode='json')}
            for goal in goals
        ],
    }
    request = cognitive_work_request(
        sid='audit-context', text='Continue the eight retained requests.', context=context,
    )
    result = {}
    for tier, render in [('fast', fast_plan_prompt), ('deep', deep_plan_prompt)]:
        kwargs = {'response_schema': {}}
        if tier == 'deep':
            kwargs['expected_goal_ids'] = [goal.goal_id for goal in goals]
        prompt = render(request, [], **kwargs)
        label = 'FINAL CANONICAL GOALS JSON'
        if tier == 'deep':
            label += ' (copy goal IDs exactly and satisfy these meanings only)'
        final = json.JSONDecoder().raw_decode(prompt.split(label + ':\n')[-1])[0]
        result[tier] = {
            'input_goal_count': len(goals),
            'context_expected_goal_count': len(planner_goal_context(context).expected_goal_ids),
            'final_goal_count': len(final),
            'missing_meanings_from_entire_prompt': [
                i for i in range(8) if f'REQUIRED_DETAIL_{i}' not in prompt
            ],
        }
    return result


def advisory_probe():
    request = cognitive_work_request(
        sid='audit-reflection', text='Continue the retained request.',
        context={
            'goal_association_resolution': {'associations': [], 'new_goals': [{
                'goal_id': 'goal-audit', 'description': 'Give a short answer.',
                'source_text': 'Give a short answer.', 'metadata': {'output_mode': 'speech'},
            }]},
            'reflection_advisories': [{
                'goal_id': 'goal-audit', 'actions': ['replan'],
                'reason_summary': 'AUDIT_REFLECTION_ADVICE_4721',
                'evidence_refs': ['evidence-audit'], 'authority': 'planner_advisory_only',
            }],
        },
    )
    return {
        'fast_prompt_contains_advisory': 'AUDIT_REFLECTION_ADVICE_4721' in fast_plan_prompt(
            request, [], response_schema={}),
        'deep_prompt_contains_advisory': 'AUDIT_REFLECTION_ADVICE_4721' in deep_plan_prompt(
            request, [], response_schema={}, expected_goal_ids=['goal-audit']),
    }


async def resource_probe():
    active = peak = 0
    class Provider(MockCapabilityProvider):
        async def execute(self, request, definition, context):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            await asyncio.sleep(0.03)
            active -= 1
            return await super().execute(request, definition, context)
    definitions = [CapabilityDefinition(
        capability_id=f'audit.output.{i}', provider_id='audit.mock',
        input_schema={'type': 'object', 'additionalProperties': False},
        can_run_parallel=True, exclusive_group=f'group-{i}',
        metadata={'resource_claims': ['audit.shared.output'], 'parallel_metadata_declared': True},
    ) for i in range(2)]
    steps = [SimpleNamespace(step_id=f'step-{i}', capability_id=d.capability_id)
             for i, d in enumerate(definitions)]
    errors = CanonicalPlanRuntimeAdapter._parallel_errors(
        steps, {s.step_id: d for s, d in zip(steps, definitions)}, plan_step_count=2)
    registry = CapabilityRegistry()
    for definition in definitions:
        registry.register(definition)
    runtime = CapabilityRuntime(registry, max_concurrency=2)
    runtime.register_provider(Provider('audit.mock'))
    results = await asyncio.gather(*(submit_and_wait_terminal(runtime, InteractionResponse(
        interaction_id=f'audit-{i}', capabilities=[{
            'request_id': f'req-{i}', 'capability_id': definition.capability_id,
        }])) for i, definition in enumerate(definitions)))
    return {'same_plan_errors': errors, 'separate_interaction_statuses': [r.status for r in results],
            'peak_concurrent_provider_calls': peak}


async def reflection_probe():
    plan = _plan()
    response = _response(plan)
    execution = CapabilityRuntimeResult(
        interaction_id=response.interaction_id, status='failed', results=[
            CapabilityResult(request_id='request-first', capability_id='chromie.test.first',
                             provider_id='test.provider', status='failed', reason_code='provider_failed'),
            CapabilityResult(request_id='request-second', capability_id='chromie.test.second',
                             provider_id='test.provider', status='completed',
                             output={'user_summary': 'Second completed.'}),
        ],
    )
    assistant, sid, _ = CognitiveTurnLoopClosureTests()._assistant(_Runtime(execution), response)
    assistant.cognitive_runtime_policy = SimpleNamespace(deep_planner_timeout_ms=125000)
    assistant.mind = SimpleNamespace(context=lambda: {
        'owner_approved': True, 'profile_id': 'audit-owner-mind'})
    started, release, planner = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests = []
    async def reflect(session, *, request, **kwargs):
        requests.append(request)
        started.set()
        await release.wait()
        return ReflectionResolution(
            opportunity_id=request.opportunity.opportunity_id,
            goal_ids=request.opportunity.goal_ids, evidence_refs=request.opportunity.evidence_refs,
            reason_codes=request.opportunity.reason_codes, actions=[],
        )
    async def get_session():
        return None
    async def plan_response(**kwargs):
        planner.set()
        return None
    assistant.agent_client = SimpleNamespace(resolve_reflection=reflect)
    assistant.get_http_session = get_session
    assistant._outcome_response_is_stale = lambda **kwargs: False
    assistant._plan_evidence_bound_capability_result_response = plan_response
    task = asyncio.create_task(assistant._close_cognitive_execution(
        response=response, execution=execution, session_id=sid, generation=4, provider_status=None))
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.sleep(0)
    result = {
        'planner_entered_while_reflection_pending': planner.is_set(),
        'mind_in_actual_reflection_context': 'mind' in requests[0].context,
        'stable_mind_prompt_is_null': 'Owner-approved Stable Mind worldview/values JSON:\nnull'
        in ReflectionResolver(None)._prompt(requests[0], requests[0].opportunity),
    }
    release.set()
    result['closure_result'] = await asyncio.wait_for(task, 2)
    result['planner_entered_after_reflection'] = planner.is_set()
    return result


async def main():
    print(json.dumps({
        'planner_projection': projection_probe(),
        'reflection_advisory': advisory_probe(),
        'resources': await resource_probe(),
        'reflection_workflow': await reflection_probe(),
    }, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
```

</details>

<details>
<summary>Observed probe output excerpt — audited revision 191083dc</summary>

Only the two synthetic step IDs are omitted from this excerpt; verdicts and all other fields are unchanged. The replay emits the complete output.

```json
{
  "planner_projection": {
    "fast": {
      "input_goal_count": 8,
      "context_expected_goal_count": 8,
      "final_goal_count": 3,
      "missing_meanings_from_entire_prompt": [
        3,
        4,
        5,
        6,
        7
      ]
    },
    "deep": {
      "input_goal_count": 8,
      "context_expected_goal_count": 8,
      "final_goal_count": 3,
      "missing_meanings_from_entire_prompt": [
        3,
        4,
        5,
        6,
        7
      ]
    }
  },
  "reflection_advisory": {
    "fast_prompt_contains_advisory": false,
    "deep_prompt_contains_advisory": false
  },
  "resources": {
    "same_plan_errors": [
      {
        "type": "runtime_parallel_resource_conflict",
        "resources": [
          "audit.shared.output"
        ]
      }
    ],
    "separate_interaction_statuses": [
      "completed",
      "completed"
    ],
    "peak_concurrent_provider_calls": 2
  },
  "reflection_workflow": {
    "planner_entered_while_reflection_pending": false,
    "mind_in_actual_reflection_context": false,
    "stable_mind_prompt_is_null": true,
    "closure_result": "planner_reentry_unavailable",
    "planner_entered_after_reflection": true
  }
}
```

</details>
