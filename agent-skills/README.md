# Agent Skills

This directory is the repository-owned, read-only root for passive Agent Skill
packages. A package is an immediate child directory containing `skill.yaml`,
`SKILL.md`, and one or more declared Markdown projections.

Directory presence never registers a Capability, provider, permission, or
confirmation exemption. The loader reads metadata, verifies package content,
and exposes bounded summaries and explicitly requested projections only. It
never imports or executes package code.

The initial metadata contract is:

```yaml
schema_version: "1.0"
agent_skill_id: chromie.example-method
version: 1.0.0
title: Example Method
description: One concise applicability summary for candidate discovery.
authority: agent_method_only
execution_authority: none
owner_approved: true
content_digest: sha256:<generated digest>
extends: []
required_capabilities: []
optional_capabilities: []
applicable_routes: []
projections:
  goal_association: projections/goal_association.md
  fast_planner: projections/fast_planner.md
  deep_planner: projections/deep_planner.md
  response_composer: projections/response_composer.md
  tool_result_interpreter: projections/tool_result_interpreter.md
```

Only declared projections that actually exist are required. Projection paths
must be normalized package-relative Markdown paths. Unknown fields, duplicate
YAML keys, executable/provider declarations, unapproved packages, unsafe paths,
symlinks, duplicate IDs, unknown parents, inheritance cycles, digest mismatch,
and oversized content fail closed.

Generate the digest after all content except `skill.yaml` is final:

```bash
python scripts/agent_skill_digest.py agent-skills/<package>
```

The digest covers every package file except `skill.yaml`, including inert
scripts or references. Package code is never imported or executed. Startup
retains metadata summaries only; explicit body/projection reads recheck the
package digest before returning immutable text/provenance DTOs.

## Repository-owned packages

- `chromie.grounded-external-information`: reusable evidence strategy for
  authoritative bindings, exact verified-memory versus fresh lookup, freshness,
  acknowledgement, typed failure stages, and grounded explanation.
- `chromie.weather-information`: weather specialization extending the grounded
  method for location/time/aspect bindings, exact weather-memory matching,
  canonical location preservation, and weather-result interpretation.

The selection model may choose zero, one, or both packages for a responsible
Agent. `extends` is dependency metadata, not automatic Host selection; when both
methods are useful, the model selects the base method before the specialization.
Package presence still grants no Capability registration or execution authority.
`applicable_routes` is a package-owned candidate-disclosure boundary. An empty
list permits every structured route for compatibility; a non-empty list keeps
the Skill out of the model's candidate set on other current-turn routes.
