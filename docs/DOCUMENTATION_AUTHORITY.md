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

## Four-axis status vocabulary

Current claims use four separate axes:

1. **Implementation** — what exists in source.
2. **Automatic verification** — which deterministic gates pass.
3. **Target validation** — which live model, service, simulator, audio, or physical evidence is retained.
4. **Deployment state** — what is enabled in maintained profiles.

A passing unit test does not establish target validation or release readiness.

## Historical material

Historical archives are preserved for investigation and provenance, but every
archive must state:

```text
Status: historical archive; not current authority
```

Current archives are indexed from [Documentation Index](README.md). They must not
be cited as the owner of current architecture, status, or delivery order.

## Mechanical governance

`config/documentation_authority.json` is the machine-readable authority map.
`scripts/check_docs.py` verifies:

- required authority roles are present once;
- paths are repository-local and exist;
- historical archives carry the non-authoritative marker;
- concise owner documents remain within reviewed line limits;
- every maintained Markdown file is indexed;
- current-focus, link, API, configuration, and reproducibility checks still pass.
