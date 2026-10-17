# Documentation Authority

Status: current normative documentation-governance contract

## One owner per current fact

Authorities are listed in precedence order and match the `authorities` list in
`config/documentation_authority.json` one to one. When documents disagree,
correct the lower-authority document.

| Fact class | Authoritative owner |
|---|---|
| stable mission, brain/body boundary, engineering principles, non-goals | [Project Charter](PROJECT_CHARTER.md) |
| interaction input, protective reflexes, attention review and turn admission | [Cognitive Gateway](COGNITIVE_GATEWAY.md) |
| admitted-turn lifecycle through delegation, Evidence re-entry and communication | [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md) |
| Goal continuity, planning, validation and interaction principles | [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md) |
| Agent, Agent Skill, Plan and Capability boundaries | [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md) |
| root-cause rules for natural, grounded behavior | [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md) |
| evidence levels, validation requirements and claim limits | [Acceptance](ACCEPTANCE.md) |
| delivery order and Issue/evidence exit criteria | [Roadmap](../ROADMAP.md) |
| implementation, automatic verification, target validation, deployment state, ordered open work | [Current Status](STATUS.md) |
| coordinated source-bound target-evidence workflow and profiles | [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md) |
| active Issue, resume point, repairs and owner decisions in force, claim boundary | [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) |
| exact deploy/run commands, runtime identities and private evidence paths | [Handoff](../HANDOFF.md) |
| operation, startup, inspection, and recovery | [Runbook](../CHROMIE_RUNBOOK.md) |
| environment and generated-runtime configuration | [Configuration](CONFIGURATION.md) |
| HTTP, WebSocket, and typed interface contracts | [API Reference](API_REFERENCE.md) |
| vulnerability, secret, and physical-safety policy | [Security Policy](../SECURITY.md) |
| complete documentation navigation | [Documentation Index](README.md) |
| notable changes | [Changelog](../CHANGELOG.md) |

Lower-authority documents link to these owners instead of restating full current
claims. Component documents own local implementation details only.

The [Documentation Index](README.md) maintains a focused core reading path.
Its length is reported for review, not capped. The complete reference catalog is
not a required reading list. A specialized document needs a current component/operator
audience or a concrete mechanically checked contract; being linked only from the index is not
permanent justification.

## Four-axis status vocabulary

Current claims use four separate axes:

1. **Implementation** — what exists in source.
2. **Automatic verification** — which deterministic gates pass.
3. **Target validation** — which live model, service, simulator, audio, or physical evidence is retained.
4. **Deployment state** — what is enabled in maintained profiles.

A passing unit test does not establish target validation or release readiness.

## Historical material

Detailed historical narrative belongs in Git history after current facts have
been consolidated into their owners. Status, checkpoint and handoff are
current-state documents: a delivery replaces their current sections and never
appends a dated entry; a notable change gets a short CHANGELOG entry. In-tree historical archives are not part
of the maintained documentation surface and must not be cited as current
authority.

## Mechanical governance

`config/documentation_authority.json` is the machine-readable authority map.
`scripts/check_docs.py` verifies:

- required authority roles are present once;
- paths are repository-local and exist;
- historical narrative is removed from the working tree after consolidation;
- owner-document paths and size-measurement baselines are valid;
- every maintained Markdown file is indexed;
- every specialized document is reachable from a current authority or component
  entry point, or is covered by a declared mechanical-contract checker;
- current-focus, link, API, configuration, and reproducibility checks still pass.

The machine-readable `specialized_ownership` section distinguishes component
entry points from mechanically checked package documentation. The documentation
index is intentionally excluded as an ownership root, so an index-only document
fails the gate.

Owner-document line counts, the core reading-path length, total maintained
Markdown files and root-level docs counts are informational in every delivery
phase. `line_baselines` and `surface_baselines` record measured values at
`size_baseline_revision`; the checker prints current values and signed deltas,
including when ownership checks fail. These are review anchors, not ceilings or
automatic permission to grow. Preserve the recorded revision and measurements;
any later rebaselining needs a reviewed reason and before/after evidence, not a
pass-condition workaround. The [engineering policy](REPOSITORY_ENGINEERING_POLICIES.md)
owns this distinction; no temporary size exception remains.

## Addition and consolidation rule

A new maintained document is justified only when an existing authority or
component owner cannot hold the fact clearly. Apply the same irreducibility review
used for architecture: first prove the fact cannot be expressed correctly as a
refinement of an existing owner. The same change must link the new document from an
entry point and remove or merge duplicated current prose, or record why no subtraction
is possible. Documentation checks prove paths and ownership; human review still owns
semantic consistency and plain-language quality.
