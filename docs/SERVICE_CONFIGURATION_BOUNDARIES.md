# Service Configuration Boundaries

Status: current engineering contract

## Ownership

Generated runtime configuration remains authoritative:

```text
env/profiles/*.env + env/validation/*.env + allowed local overrides
        ↓
scripts/generate_runtime_env.py
        ↓
.env.runtime
        ↓
service-owned typed startup snapshot
        ↓
internal collaborators
```

A service-owned settings object validates and normalizes its environment once at
startup. Internal modules receive typed values; they do not reinterpret the same
environment variable independently. This boundary does not change hardware
profile precedence and does not move owner-editable identity or personality into
Python defaults.

## Migrated boundary: ASR

`asr.settings.ASRServiceSettings` owns the complete maintained ASR service
environment surface. It provides:

- strict boolean, integer, float, optional-text, port, sample-rate, and duration
  parsing;
- one immutable snapshot copied from the startup environment;
- an `ASRBackendConfig` projection for the backend factory;
- a safe health-diagnostic projection that omits installation-local override
  file paths;
- explicit startup failures naming the invalid environment variable.

`asr/server.py` no longer calls `os.getenv`. The server, warm-up, health response,
transcription executor, and backend factory all consume the same immutable
settings instance.


## Continuation objective

The first ASR migration is a proven slice, not closure of the configuration
problem. The current archive still contains about 276 distinct environment keys
read directly by maintained runtime sources. Before changing names, inventory
each key as profile authority, service setting, operator override, diagnostics,
experiment, or stale compatibility. Ordinary behavior should be composed from a
small set of orthogonal profile axes rather than freely combined Boolean flags.

Further migrations remain queued until current-revision target evidence closes.
Each migrated service must delete duplicate parsing and obsolete keys instead of
adding another compatibility layer indefinitely.

## Remaining migration map

The 2026-07-31 source audit found 295 distinct literal environment keys read by
the maintained Orchestrator, Agent, ASR, TTS, and shared runtime Python, while
the Configuration reference documents 321 keys. These counts mix public
choices, profile-owned constants, service internals, acceptance overrides, and
compatibility aliases. They are a baseline for classification, not a claim that
every key is a supported operator switch.

The remaining services keep their current behavior and are future ratchet work:

| Boundary | Current concentration | Recommended next seam |
|---|---|---|
| Agent service | `agent/app/main.py` | extract Agent startup settings by functional groups, preserving generated profile authority |
| TTS service | `tts/server.py`, `tts/candidate_server.py` | common transport/watchdog snapshot with provider-owned model settings |
| Host Orchestrator | `orchestrator/orchestrator.py` | compose typed audio, cognition, playback, and evidence settings rather than one global object |
| Shared runtime | trace/resource modules | inject narrow typed policy values where repeated reads remain |

Each future migration must be independently tested and must not become one global
cross-service settings object. The active sequence first retains a
current-revision live voice loop, then classifies broad failure boundaries,
then establishes typed Host settings before reducing supported deployment
combinations. See
[Repository Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).
