# Changelog

This file records notable current changes. Detailed earlier development history is
preserved in [Changelog Archive — through 2026-07-30](CHANGELOG_ARCHIVE_2026-07-30.md).

## Unreleased

### Agent Skills and grounded information

- Added passive owner-approved Agent Skill contracts, read-only loading,
  model-authored selection, role-specific disclosure, and content-free Canonical
  Plan provenance.
- Added grounded external-information and weather methods while preserving Goal
  Association, verified-memory, Capability, Provider, and Soridormi authority.

### Runtime and repository safeguards

- Canonicalized executable `capability_id` terminology with bounded legacy
  readers.
- Bound local development services to loopback and added executable repository
  policies for failure paths, architecture, Agent Skills, and deployment.
- Added high-signal Ruff and incremental Mypy ratchets plus explicit behavioral,
  architecture-policy, and generated-artifact test ownership.

### Maintainability

- Added immutable typed ASR startup configuration without changing generated
  profile precedence.
- Extracted runtime-ready greeting scheduling and playback barriers into an
  independently tested collaborator while retaining `VoiceAssistant` lifecycle
  ownership.
- Consolidated documentation authority, archived detailed superseded narratives,
  and added a machine-checked authority registry.

### Evidence status

- Automated repository gates remain distinct from live target evidence.
- Current source-bound Gateway/Core, Social Attention, provider-backed weather,
  physical audio, and supervised physical-robot validation remain governed by
  their owning evidence documents.
