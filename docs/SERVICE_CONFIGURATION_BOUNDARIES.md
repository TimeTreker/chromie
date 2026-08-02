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

## Migrated boundaries: Agent, ASR, and TTS

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

`tts.settings.TTSServiceSettings` now owns the maintained TTS transport,
provider, generation-budget, worker-pool, speaker, alignment, and immutable
model-source environment surface. `tts/server.py`, `tts/candidate_server.py`,
`tts/create_speaker.py`, and `tts/model_sources.py` receive one typed snapshot
instead of reparsing environment values independently. Invalid ports, ranges,
booleans, and missing immutable model references fail with the owning key.

`agent.app.settings` now owns the Agent service and Goal Interpreter startup
surfaces. Main composition, model clients, weather, capability planning,
conversation, deep thinking, Goal Interpreter diagnostics, and manifest
expansion consume typed snapshots or explicitly supplied standalone settings.
Maintained startup passes the same Agent snapshot into every model and provider
client; compatibility factories remain only for isolated callers and tests.


## Continuation objective

The Agent, ASR, and TTS migrations are proven slices, not closure of the configuration
problem. The current archive still contains about 276 distinct environment keys
read directly by maintained runtime sources. Before changing names, inventory
each key as profile authority, service setting, operator override, diagnostics,
experiment, or stale compatibility. Ordinary behavior should be composed from a
small set of orthogonal profile axes rather than freely combined Boolean flags.

Shared-runtime policy migration remains source work. Each migrated service
must delete duplicate parsing and obsolete keys instead of adding another
compatibility layer indefinitely. Live startup proof remains target evidence.

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
| Shared runtime | trace/resource modules | inject narrow typed policy values where repeated reads remain |

Each future migration must be independently tested and must not become one global
cross-service settings object. The source sequence now continues with narrow shared-runtime policy ownership.
Physical startup and device proof remain in the target-evidence track. See
[Repository Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).
