# Documentation Authority

Status: current normative documentation-governance contract

## One owner per current fact

| Fact class | Authoritative owner |
|---|---|
| stable mission, brain/body boundary, engineering principles, non-goals | [Project Charter](PROJECT_CHARTER.md) |
| delivery order and Issue/evidence exit criteria | [Roadmap](../ROADMAP.md) |
| implementation, automatic verification, target validation, deployment state | [Current Status](STATUS.md) |
| coordinated source-bound target-evidence workflow and profiles | [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md) |
| current resume point and immediate commands | [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) |
| operation, startup, inspection, and recovery | [Runbook](../CHROMIE_RUNBOOK.md) |
| environment and generated-runtime configuration | [Configuration](CONFIGURATION.md) |
| HTTP, WebSocket, and typed interface contracts | [API Reference](API_REFERENCE.md) |
| vulnerability, secret, and physical-safety policy | [Security Policy](../SECURITY.md) |
| notable current changes | [Changelog](../CHANGELOG.md) |
| complete documentation navigation | [Documentation Index](README.md) |

Lower-authority documents link to these owners instead of restating full current
claims. Component documents own local implementation details only.

The [Documentation Index](README.md) maintains a core reading path of no more
than 15 documents. The complete reference catalog is not a required reading
list. A specialized document needs a current component/operator audience or a
concrete mechanically checked contract; being linked only from the index is not
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
been consolidated into their owners. In-tree historical archives are not part
of the maintained documentation surface and must not be cited as current
authority.

## Mechanical governance

`config/documentation_authority.json` is the machine-readable authority map.
`scripts/check_docs.py` verifies:

- required authority roles are present once;
- paths are repository-local and exist;
- historical narrative is removed from the working tree after consolidation;
- concise owner documents remain within reviewed line limits;
- every maintained Markdown file is indexed;
- current-focus, link, API, configuration, and reproducibility checks still pass.

## Addition and consolidation rule

A new maintained document is justified only when an existing authority or
component owner cannot hold the fact clearly. The same change must link it from
an entry point and remove or merge duplicated current prose, or record why no
subtraction is possible. Documentation checks prove paths and ownership; human
review still owns semantic consistency and plain-language quality.
