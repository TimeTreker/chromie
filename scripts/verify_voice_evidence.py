#!/usr/bin/env python3
"""Verify the structure and pass state of a voice acceptance evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.runtime.evidence_identity import (  # noqa: E402
    RuntimeEvidenceIdentityError,
    load_runtime_evidence_identity,
)

REQUIRED_CASES = {
    "speech-only",
    "speech-capability",
    "refusal",
    "barge-in",
    "body-cancel",
    "stop",
    "follow-up",
}
REQUIRED_FILES = {
    "metadata.json",
    "cases.json",
    "summary.md",
    "events.jsonl",
    "cognitive-runtime.jsonl",
    "orchestrator.log",
    "runtime.env.redacted",
    "audio-devices.log",
    "acceptance-overrides.env",
}
FULL_VOICE_MUJOCO_PROFILE = "full-voice-mujoco"
CURRENT_REVISION_LIVE_VOICE_PROFILE = "current-revision-live-voice"
VERIFICATION_PROFILES = (
    FULL_VOICE_MUJOCO_PROFILE,
    CURRENT_REVISION_LIVE_VOICE_PROFILE,
)
LIVE_VOICE_REQUIRED_FILES = REQUIRED_FILES | {
    "bundle-manifest.json",
    "command.txt",
    "compose-ps.log",
    "git-status.log",
    "runtime-env.log",
    "runtime-identity.json",
    "runtime-identity.log",
    "runtime-profile.json",
}
LIVE_VOICE_REQUIRED_SERVICES = {
    "chromie-agent",
    "chromie-asr",
    "chromie-llm",
    "chromie-tts",
}
LIVE_VOICE_BLOCKING_EVENTS = {
    "cognitive_core_exception",
    "cognitive_core_exception_safe_fallback",
    "llm_output_truncated",
    "llm_prompt_truncated",
    "playback_aborted_by_interrupt",
    "playback_drop_stale_before_order",
    "playback_skip_drop_stale",
}
LIVE_VOICE_BLOCKING_FAILURE_CLASSES = {
    "latency_budget_exhausted",
    "outer_timeout",
    "output_truncated",
    "prompt_budget_exceeded",
    "prompt_truncated",
    "timeout",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _message_field(message: str, name: str) -> str | None:
    match = re.search(rf"(?:^|\s){re.escape(name)}=([^\s]+)", message)
    return match.group(1) if match else None


def _validate_artifact_manifest(
    evidence_dir: Path,
    *,
    required_files: set[str],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    artifacts_by_path: dict[str, dict[str, Any]] = {}
    try:
        manifest = load_json(evidence_dir / "bundle-manifest.json")
    except Exception as exc:
        return [f"bundle-manifest.json is invalid: {exc}"], artifacts_by_path
    if not isinstance(manifest, dict):
        return ["bundle-manifest.json must contain an object"], artifacts_by_path
    if manifest.get("schema_version") != 1:
        errors.append("bundle-manifest.json must declare schema_version=1")
    if manifest.get("release_qualified") is not False:
        errors.append("bundle-manifest.json must record release_qualified=false")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return [*errors, "bundle-manifest.json has no artifacts"], artifacts_by_path
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            errors.append(f"bundle-manifest artifact {index} is not an object")
            continue
        raw_path = str(item.get("path") or "")
        relative = Path(raw_path)
        if (
            not raw_path
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() == "bundle-manifest.json"
        ):
            errors.append(f"bundle-manifest artifact {index} has invalid path {raw_path!r}")
            continue
        normalized = relative.as_posix()
        if normalized in artifacts_by_path:
            errors.append(f"bundle-manifest duplicates artifact {normalized}")
            continue
        artifacts_by_path[normalized] = item
        artifact_path = evidence_dir / relative
        if artifact_path.is_symlink():
            errors.append(f"bundle-manifest artifact must not be a symlink: {normalized}")
            continue
        if not artifact_path.is_file():
            errors.append(f"bundle-manifest artifact is missing: {normalized}")
            continue
        expected_size = item.get("bytes")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool):
            errors.append(f"bundle-manifest artifact has invalid size: {normalized}")
        elif artifact_path.stat().st_size != expected_size:
            errors.append(f"bundle-manifest artifact size mismatch: {normalized}")
        expected_sha = str(item.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            errors.append(f"bundle-manifest artifact has invalid SHA-256: {normalized}")
        elif _sha256_file(artifact_path) != expected_sha:
            errors.append(f"bundle-manifest artifact digest mismatch: {normalized}")
    missing_required = sorted(
        (required_files - {"bundle-manifest.json"}) - set(artifacts_by_path)
    )
    if missing_required:
        errors.append(
            "bundle-manifest is missing required artifacts: "
            + ", ".join(missing_required)
        )
    return errors, artifacts_by_path


def _validate_live_voice_runtime_identity(
    identity: dict[str, Any],
    *,
    evidence_dir: Path,
    expected_revision: str | None,
) -> list[str]:
    errors: list[str] = []
    chromie = identity.get("chromie")
    runtime_profile = identity.get("runtime_profile")
    deployment = identity.get("deployment")
    qualification = identity.get("qualification")
    if not isinstance(chromie, dict):
        return ["runtime identity has no Chromie object"]
    if chromie.get("dirty") is not False:
        errors.append("runtime identity does not record a clean Chromie worktree")
    revision = str(chromie.get("revision") or "")
    if expected_revision and revision != expected_revision:
        errors.append(
            f"runtime identity revision {revision!r} does not match expected "
            f"{expected_revision!r}"
        )
    if not isinstance(runtime_profile, dict):
        errors.append("runtime identity has no generated runtime profile")
        runtime_profile = {}
    else:
        if not runtime_profile.get("fingerprint"):
            errors.append("runtime identity has no runtime profile fingerprint")
        if not runtime_profile.get("sha256"):
            errors.append("runtime identity has no runtime profile digest")
        if not isinstance(runtime_profile.get("models"), dict) or not runtime_profile.get(
            "models"
        ):
            errors.append("runtime identity has no model topology")
        retained_profile_path = evidence_dir / "runtime-profile.json"
        try:
            retained_profile = load_json(retained_profile_path)
        except Exception as exc:
            errors.append(f"retained runtime profile is invalid: {exc}")
        else:
            if not isinstance(retained_profile, dict):
                errors.append("retained runtime profile must contain an object")
            else:
                if _sha256_file(retained_profile_path) != runtime_profile.get("sha256"):
                    errors.append(
                        "retained runtime profile digest does not match runtime identity"
                    )
                if retained_profile.get("fingerprint") != runtime_profile.get(
                    "fingerprint"
                ):
                    errors.append(
                        "retained runtime profile fingerprint does not match runtime identity"
                    )
    if not isinstance(deployment, dict) or deployment.get("complete") is not True:
        errors.append("runtime identity does not bind every required running service image")
        service_images: dict[str, Any] = {}
    else:
        raw_service_images = deployment.get("service_images")
        if not isinstance(raw_service_images, dict):
            errors.append("runtime identity service image map is invalid")
            service_images = {}
        else:
            service_images = raw_service_images
    missing_services = sorted(LIVE_VOICE_REQUIRED_SERVICES - set(service_images))
    if missing_services:
        errors.append(
            "runtime identity is missing required services: "
            + ", ".join(missing_services)
        )
    for service in sorted(LIVE_VOICE_REQUIRED_SERVICES.intersection(service_images)):
        item = service_images.get(service)
        if not isinstance(item, dict) or not str(item.get("image_id") or "").strip():
            errors.append(f"runtime identity has no immutable image ID for {service}")
    agent = service_images.get("chromie-agent")
    if isinstance(agent, dict):
        effective_runtime = agent.get("effective_runtime")
        if not isinstance(effective_runtime, dict) or (
            effective_runtime.get("CHROMIE_RUNTIME_ENV_FINGERPRINT")
            != runtime_profile.get("fingerprint")
        ):
            errors.append(
                "running Agent runtime fingerprint does not match the retained profile"
            )
        effective_models = agent.get("effective_models")
        if not isinstance(effective_models, dict) or not effective_models:
            errors.append("runtime identity has no effective Agent model topology")
    orchestrator_runtime = identity.get("orchestrator_runtime")
    if not isinstance(orchestrator_runtime, dict) or not isinstance(
        orchestrator_runtime.get("effective_models"), dict
    ) or not orchestrator_runtime.get("effective_models"):
        errors.append("runtime identity has no launcher-effective model topology")
    if not isinstance(qualification, dict):
        errors.append("runtime identity has no qualification state")
    else:
        if qualification.get("source_clean") is not True:
            errors.append("runtime identity is not source clean")
        if qualification.get("deployment_complete") is not True:
            errors.append("runtime identity deployment is incomplete")
        if qualification.get("release_qualified") is not False:
            errors.append("runtime identity must record release_qualified=false")
    return errors


def _validate_live_voice_turn(
    evidence_dir: Path,
    *,
    case: dict[str, Any],
    runtime_events: list[dict[str, Any]],
    cognitive_events: list[dict[str, Any]],
    identity_sha256: str,
) -> list[str]:
    errors: list[str] = []
    raw_session_ids = case.get("session_ids")
    session_ids = [
        str(item)
        for item in raw_session_ids
        if item
    ] if isinstance(raw_session_ids, list) else []
    if len(session_ids) != 1:
        return [
            "The current-revision live voice profile requires exactly one "
            "correlated speech-only session"
        ]
    sid = session_ids[0]
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", sid):
        return ["Speech-only evidence contains an unsafe session identity"]
    session_runtime = [
        item for item in runtime_events if str(item.get("sid") or "") == sid
    ]
    session_cognitive = [
        item for item in cognitive_events if str(item.get("sid") or "") == sid
    ]

    gateways = [
        item
        for item in session_cognitive
        if item.get("event") == "cognitive_gateway_admission"
        and item.get("admission") in {"admit", "reflex_and_admit"}
        and item.get("channel") == "voice"
        and isinstance(item.get("quality"), dict)
        and item["quality"].get("source") == "asr_final"
    ]
    if not gateways:
        errors.append(
            "Speech-only evidence has no admitted voice Gateway event sourced from asr_final"
        )
    resolutions = [
        item
        for item in session_cognitive
        if item.get("event") == "cognitive_runtime_resolution"
        and item.get("mode") == "apply"
        and item.get("status") == "applied"
    ]
    if len(resolutions) != 1:
        errors.append(
            "Speech-only evidence must contain exactly one applied Core resolution"
        )
    for item in [*gateways, *resolutions]:
        reference = item.get("run_identity")
        if not isinstance(reference, dict) or (
            reference.get("identity_sha256") != identity_sha256
            or reference.get("complete") is not True
        ):
            errors.append(
                "Gateway/Core evidence is not bound to the retained runtime identity"
            )
            break

    for resolution in resolutions:
        terminal = resolution.get("terminal_plan")
        interaction = resolution.get("interaction")
        terminal_capabilities = (
            terminal.get("capability_ids") if isinstance(terminal, dict) else None
        )
        interaction_capabilities = (
            interaction.get("capability_ids")
            if isinstance(interaction, dict)
            else None
        )
        if terminal_capabilities not in (None, []) or interaction_capabilities not in (
            None,
            [],
        ):
            errors.append("Speech-only evidence contains executable capabilities")
        if not isinstance(interaction, dict) or not isinstance(
            interaction.get("speech_count"), int
        ) or interaction.get("speech_count", 0) < 1:
            errors.append("Speech-only Core resolution has no validated speech output")
        fallback_reason = str(resolution.get("fallback_reason") or "").strip().lower()
        if fallback_reason and fallback_reason != "none":
            errors.append(
                "Speech-only Core resolution used fallback after authority acquisition"
            )
        metadata = resolution.get("metadata")
        failure_class = (
            str(metadata.get("failure_class") or "").strip().lower()
            if isinstance(metadata, dict)
            else ""
        )
        if failure_class in LIVE_VOICE_BLOCKING_FAILURE_CLASSES:
            errors.append(
                f"Speech-only Core resolution has critical failure class {failure_class!r}"
            )

    speech_capability_results = [
        item
        for item in session_runtime
        if item.get("event") == "capability_result"
        and re.search(
            r"(?:^|\s)capability_id=chromie\.speak(?:\s|$)",
            str(item.get("message") or ""),
        )
        and re.search(
            r"(?:^|\s)status=completed(?:\s|$)",
            str(item.get("message") or ""),
        )
    ]
    for item in session_runtime:
        event_name = str(item.get("event") or "")
        message = str(item.get("message") or "")
        runtime_result_count = _message_field(message, "results")
        expected_speech_runtime_event = (
            event_name == "capability_result" and item in speech_capability_results
        ) or (
            event_name == "capability_runtime_done"
            and bool(speech_capability_results)
            and _message_field(message, "status") == "completed"
            and runtime_result_count == str(len(speech_capability_results))
        )
        if not expected_speech_runtime_event and event_name.startswith(
            ("cognitive_capability_", "confirmation_", "capability_", "soridormi_")
        ):
            errors.append(
                f"Speech-only runtime contains executable work event {event_name!r}"
            )
        if event_name in LIVE_VOICE_BLOCKING_EVENTS or (
            "stale" in event_name and event_name.startswith(("playback", "tts"))
        ):
            errors.append(f"Speech-only runtime contains blocking event {event_name!r}")
        match = re.search(r"(?:^|\s)failure_class=([^\s]+)", message)
        if match and match.group(1).strip().lower() in LIVE_VOICE_BLOCKING_FAILURE_CLASSES:
            errors.append(
                "Speech-only runtime contains critical model failure "
                f"{match.group(1)!r}"
            )
    done_indexes = [
        index
        for index, item in enumerate(session_runtime)
        if item.get("event") == "session_done"
    ]
    if done_indexes:
        last_done = done_indexes[-1]
        if any(
            item.get("event") in {"tts_schedule", "playback_start", "playback_end"}
            for item in session_runtime[last_done + 1 :]
        ):
            errors.append("Speech-only runtime contains stale playback after session completion")

    try:
        device_text = (evidence_dir / "audio-devices.log").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"audio-devices.log cannot be read: {exc}")
    else:
        if "Input device name=" not in device_text:
            errors.append("Audio evidence has no running input-device identity")
        if "Output device name=" not in device_text:
            errors.append("Audio evidence has no running output-device identity")
    recordings = evidence_dir / "recordings"
    recording_files = (
        [item for item in recordings.iterdir() if item.is_file()]
        if recordings.is_dir()
        else []
    )
    input_recordings = [
        item
        for item in recording_files
        if item.name.startswith(f"input_{sid}_")
        and item.suffix == ".raw"
        and item.stat().st_size > 0
    ]
    output_recordings = [
        item
        for item in recording_files
        if item.name.startswith(f"output_{sid}_")
        and item.suffix == ".raw"
        and item.stat().st_size > 0
    ]
    if not input_recordings:
        errors.append("Speech-only evidence has no correlated physical microphone recording")
    if not output_recordings:
        errors.append("Speech-only evidence has no correlated audible-output recording")
    return errors


def _git_revision(root: Path = ROOT) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _version(root: Path = ROOT) -> str | None:
    path = root / "VERSION"
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _soridormi_revisions(root: Path = ROOT) -> tuple[str | None, str | None]:
    manifest_revision: str | None = None
    compatibility_revision: str | None = None
    try:
        manifest = load_json(root / "capabilities" / "soridormi.json")
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
        if isinstance(metadata, dict) and metadata.get("upstream_commit"):
            manifest_revision = str(metadata["upstream_commit"]).strip() or None
    except Exception:
        pass
    try:
        compatibility = load_json(root / "release" / "compatibility.json")
        soridormi = (
            compatibility.get("soridormi")
            if isinstance(compatibility, dict)
            else None
        )
        if isinstance(soridormi, dict) and soridormi.get("upstream_commit"):
            compatibility_revision = str(soridormi["upstream_commit"]).strip() or None
    except Exception:
        pass
    return manifest_revision, compatibility_revision


def verify_bundle(
    evidence_dir: Path,
    *,
    profile: str = FULL_VOICE_MUJOCO_PROFILE,
    require_clean: bool = False,
    allow_automated: bool = False,
    expected_chromie_revision: str | None = None,
    expected_chromie_version: str | None = None,
    expected_soridormi_revision: str | None = None,
    source_root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    provenance_errors: list[str] = []
    if profile not in VERIFICATION_PROFILES:
        return {
            "passed": False,
            "errors": [f"Unknown voice evidence verification profile: {profile!r}"],
            "warnings": [],
        }
    live_voice_profile = profile == CURRENT_REVISION_LIVE_VOICE_PROFILE
    required_cases = {"speech-only"} if live_voice_profile else REQUIRED_CASES
    required_files = LIVE_VOICE_REQUIRED_FILES if live_voice_profile else REQUIRED_FILES

    def provenance_error(message: str) -> None:
        errors.append(message)
        provenance_errors.append(message)

    def positive_event_count(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    def nonempty_string_list(value: Any) -> list[str] | None:
        if not isinstance(value, list) or not value:
            return None
        if any(not isinstance(item, str) or not item.strip() for item in value):
            return None
        return [item.strip() for item in value]

    if expected_chromie_revision is None:
        expected_chromie_revision = _git_revision(source_root)
        if not expected_chromie_revision:
            provenance_error("Cannot determine the expected Chromie source revision")
    if expected_chromie_version is None:
        expected_chromie_version = _version(source_root)
        if not expected_chromie_version:
            provenance_error("Cannot determine the expected Chromie VERSION")
    if not live_voice_profile and expected_soridormi_revision is None:
        manifest_revision, compatibility_revision = _soridormi_revisions(source_root)
        if not manifest_revision:
            provenance_error(
                "Cannot determine the Soridormi revision from the capability manifest"
            )
        if not compatibility_revision:
            provenance_error(
                "Cannot determine the Soridormi revision from release compatibility"
            )
        if (
            manifest_revision
            and compatibility_revision
            and manifest_revision != compatibility_revision
        ):
            provenance_error(
                "Soridormi source provenance is inconsistent: capability manifest "
                f"{manifest_revision!r} != release compatibility "
                f"{compatibility_revision!r}"
            )
        expected_soridormi_revision = manifest_revision or compatibility_revision

    if not evidence_dir.is_dir():
        return {
            "passed": False,
            "errors": [f"Evidence directory not found: {evidence_dir}"],
            "warnings": [],
        }

    for name in sorted(required_files):
        path = evidence_dir / name
        if not path.is_file():
            errors.append(f"Missing required evidence file: {name}")
        elif path.stat().st_size == 0:
            errors.append(f"Required evidence file is empty: {name}")

    metadata: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []
    try:
        loaded_metadata = load_json(evidence_dir / "metadata.json")
        if isinstance(loaded_metadata, dict):
            metadata = loaded_metadata
        else:
            errors.append("metadata.json must contain an object")
    except Exception as exc:
        errors.append(f"metadata.json is invalid: {exc}")
    try:
        loaded_cases = load_json(evidence_dir / "cases.json")
        if isinstance(loaded_cases, list):
            cases = [item for item in loaded_cases if isinstance(item, dict)]
            invalid_case_count = len(loaded_cases) - len(cases)
            if invalid_case_count:
                errors.append(
                    f"cases.json contains {invalid_case_count} non-object case entries"
                )
        else:
            errors.append("cases.json must contain a list")
    except Exception as exc:
        errors.append(f"cases.json is invalid: {exc}")

    if metadata.get("schema_version") != 2:
        provenance_error(
            "metadata.json must declare voice acceptance schema_version=2"
        )
    if metadata.get("status") != "passed":
        errors.append(f"Acceptance status is not passed: {metadata.get('status')!r}")
    runner = metadata.get("runner")
    if not isinstance(runner, dict):
        errors.append("metadata.json runner must be an object")
        runner = {}
    raw_mode = runner.get("mode")
    mode = str(raw_mode) if isinstance(raw_mode, str) and raw_mode else "unknown"
    if mode not in {"synthetic", "virtual-mic", "acoustic", "supervised"}:
        errors.append(f"Unknown acceptance mode: {mode!r}")
    if live_voice_profile and mode != "supervised":
        errors.append(
            "The current-revision live voice profile requires supervised physical "
            "microphone and speaker evidence"
        )
    elif mode != "supervised" and not allow_automated:
        errors.append(
            f"Acceptance mode {mode!r} is automated evidence and cannot close a "
            "human-supervised voice-device release gate; run --mode supervised "
            "for human release-closing evidence or narrow the release claim"
        )
    if runner.get("dry_run") is not False:
        errors.append("Dry-run evidence cannot close a release gate")
    if live_voice_profile:
        if runner.get("verification_profile") != CURRENT_REVISION_LIVE_VOICE_PROFILE:
            errors.append(
                "metadata.json runner does not identify the current-revision live "
                "voice profile"
            )
        command = nonempty_string_list(runner.get("command"))
        if command is None:
            errors.append("metadata.json runner has no exact command")
        else:
            try:
                retained_command = (evidence_dir / "command.txt").read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                errors.append(f"command.txt cannot be read: {exc}")
            else:
                if retained_command != shlex.join(command):
                    errors.append("command.txt does not match metadata.json runner command")
    if not positive_event_count(metadata.get("event_count")):
        errors.append("metadata.json reports no structured session events")
    selected_cases = metadata.get("selected_cases")
    normalized_selected_cases = nonempty_string_list(selected_cases)
    if (
        normalized_selected_cases is None
        or len(normalized_selected_cases) != len(required_cases)
        or set(normalized_selected_cases) != required_cases
    ):
        expected_scope = (
            "only speech-only"
            if live_voice_profile
            else "the full required matrix"
        )
        errors.append(f"metadata.json selected_cases must explicitly contain {expected_scope}")

    chromie_value = metadata.get("chromie")
    if isinstance(chromie_value, dict):
        chromie = chromie_value
    else:
        chromie = {}
        provenance_error("metadata.json chromie must be an object")
    if not chromie.get("revision") or chromie.get("revision") == "unknown":
        provenance_error("Chromie revision is missing")
    elif (
        expected_chromie_revision
        and str(chromie.get("revision")) != expected_chromie_revision
    ):
        provenance_error(
            f"Evidence Chromie revision {chromie.get('revision')!r} does not match "
            f"expected source revision {expected_chromie_revision!r}"
        )
    if not chromie.get("version"):
        provenance_error("Chromie version is missing")
    elif (
        expected_chromie_version
        and str(chromie.get("version")) != expected_chromie_version
    ):
        provenance_error(
            f"Evidence Chromie version {chromie.get('version')!r} does not match "
            f"expected VERSION {expected_chromie_version!r}"
        )
    chromie_dirty = chromie.get("dirty")
    if (require_clean or live_voice_profile) and chromie_dirty is not False:
        provenance_error(
            "Evidence does not explicitly record a clean Chromie worktree"
        )
    elif chromie_dirty is True:
        warnings.append("Chromie worktree was dirty during acceptance")

    manifest: dict[str, Any] = {}
    endpoint_source_bound = False
    if not live_voice_profile:
        manifest_value = metadata.get("soridormi_manifest")
        if isinstance(manifest_value, dict):
            manifest = manifest_value
        else:
            provenance_error("metadata.json soridormi_manifest must be an object")
        if not manifest.get("upstream_commit"):
            provenance_error("Pinned Soridormi upstream revision is missing")
        elif (
            expected_soridormi_revision
            and str(manifest.get("upstream_commit")) != expected_soridormi_revision
        ):
            provenance_error(
                "Evidence Soridormi manifest revision "
                f"{manifest.get('upstream_commit')!r} does not match expected revision "
                f"{expected_soridormi_revision!r}"
            )
        local_revision = metadata.get("soridormi_local_revision")
        if expected_soridormi_revision:
            if local_revision in {None, "", "not-provided", "unknown"}:
                provenance_error(
                    "Evidence does not identify the declared paired Soridormi checkout revision"
                )
            elif str(local_revision) != expected_soridormi_revision:
                provenance_error(
                    f"Evidence Soridormi checkout revision {local_revision!r} does not match "
                    f"expected revision {expected_soridormi_revision!r}"
                )
        if metadata.get("soridormi_local_dirty") is not False:
            provenance_error(
                "Evidence does not record a clean declared paired Soridormi checkout"
            )
        source_binding = metadata.get("soridormi_source_binding")
        endpoint_revision = (
            source_binding.get("endpoint_revision")
            if isinstance(source_binding, dict)
            else None
        )
        endpoint_source_bound = bool(
            isinstance(source_binding, dict)
            and source_binding.get("kind") == "endpoint_reported_revision"
            and expected_soridormi_revision
            and endpoint_revision == expected_soridormi_revision
        )
        if not endpoint_source_bound:
            warnings.append(
                "Soridormi checkout provenance is declared but not bound to an "
                "endpoint-reported source revision; this bundle cannot enter release policy"
            )
        soridormi_mcp_url = metadata.get("soridormi_mcp_url")
        if (
            not isinstance(soridormi_mcp_url, str)
            or not soridormi_mcp_url.strip()
            or soridormi_mcp_url == "not-configured"
        ):
            errors.append("Soridormi MCP endpoint is missing from metadata")

    by_id = {
        str(item.get("case_id")): item
        for item in cases
        if item.get("case_id")
    }
    missing_cases = sorted(required_cases - set(by_id))
    extra_cases = sorted(set(by_id) - required_cases)
    if missing_cases:
        errors.append("Missing required cases: " + ", ".join(missing_cases))
    if extra_cases:
        warnings.append("Additional cases present: " + ", ".join(extra_cases))

    for case_id in sorted(required_cases & set(by_id)):
        item = by_id[case_id]
        verdict = item.get("operator_verdict")
        expected_verdicts = {"pass"} if mode == "supervised" else {"automated"}
        if verdict not in expected_verdicts:
            errors.append(
                f"Case {case_id} verdict is {verdict!r}; expected one of "
                f"{sorted(expected_verdicts)} for mode {mode!r}"
            )
        checks = item.get("checks")
        if not isinstance(checks, list) or not checks:
            errors.append(f"Case {case_id} has no automated checks")
        else:
            failed: list[str] = []
            for check_index, check in enumerate(checks):
                if not isinstance(check, dict):
                    failed.append(f"invalid-check-{check_index}")
                elif check.get("passed") is not True:
                    failed.append(str(check.get("name") or "unnamed"))
            if failed:
                errors.append(
                    f"Case {case_id} has failed checks: " + ", ".join(failed)
                )
        if not positive_event_count(item.get("event_count")):
            errors.append(f"Case {case_id} has no correlated events")
        if nonempty_string_list(item.get("session_ids")) is None:
            errors.append(f"Case {case_id} has no correlated session IDs")

    override_text = ""
    try:
        override_text = (evidence_dir / "acceptance-overrides.env").read_text(
            encoding="utf-8"
        )
    except Exception:
        pass
    override_values: dict[str, str] = {}
    try:
        for line_number, raw_line in enumerate(override_text.splitlines(), 1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            tokens = shlex.split(stripped, comments=True, posix=True)
            if len(tokens) != 1 or "=" not in tokens[0]:
                raise ValueError(f"line {line_number} is not one exact assignment")
            key, value = tokens[0].split("=", 1)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(f"line {line_number} has invalid key {key!r}")
            if key in override_values:
                raise ValueError(f"line {line_number} duplicates {key}")
            override_values[key] = value
    except ValueError as exc:
        provenance_error(f"acceptance-overrides.env is invalid: {exc}")

    required_overrides = {
        "ORCH_ENABLE_INTERACTION_RESPONSE": "1",
        "ORCH_ENABLE_SORIDORMI_CAPABILITIES": "0" if live_voice_profile else "1",
    }
    required_semantic_overrides = {
        "ORCH_COGNITIVE_RUNTIME_MODE": "apply",
        "ORCH_COGNITIVE_EVIDENCE_ENABLED": "1",
    }
    if mode == "synthetic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "stdin",
                "ORCH_AUDIO_OUTPUT_MODE": "discard",
            }
        )
    elif mode == "virtual-mic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": "discard",
            }
        )
    elif mode == "acoustic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
            }
        )
    else:
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": "device",
            }
        )
    for key, expected in sorted(required_overrides.items()):
        if override_values.get(key) != expected:
            errors.append(f"Acceptance override must set {key}={expected}")
    for key, expected in sorted(required_semantic_overrides.items()):
        if override_values.get(key) != expected:
            provenance_error(f"Acceptance override must set {key}={expected}")
    if live_voice_profile:
        identity_override = override_values.get("ORCH_COGNITIVE_RUN_IDENTITY_PATH")
        if not identity_override:
            provenance_error(
                "Acceptance override must bind ORCH_COGNITIVE_RUN_IDENTITY_PATH"
            )
        elif Path(identity_override).expanduser().resolve() != (
            evidence_dir / "runtime-identity.json"
        ).resolve():
            provenance_error(
                "Acceptance runtime identity path does not bind the retained identity"
            )
    if mode == "virtual-mic" and not override_values.get("PULSE_SOURCE"):
        errors.append("Acceptance override must set a non-empty PULSE_SOURCE")
    if mode == "acoustic" and override_values.get("ORCH_AUDIO_OUTPUT_MODE") not in {
        "discard",
        "device",
    }:
        errors.append(
            "Acceptance override is missing acoustic output mode: "
            "ORCH_AUDIO_OUTPUT_MODE=discard or ORCH_AUDIO_OUTPUT_MODE=device"
        )

    if mode in {"synthetic", "virtual-mic", "acoustic"}:
        generated_dir = evidence_dir / "generated-input"
        manifest_path = generated_dir / "manifest.json"
        if not manifest_path.is_file():
            errors.append("Automated evidence is missing generated-input/manifest.json")
        if not any(generated_dir.glob("*.wav")):
            errors.append("Automated evidence contains no generated input WAV files")

    cognitive_events: list[dict[str, Any]] = []
    cognitive_path = evidence_dir / "cognitive-runtime.jsonl"
    if cognitive_path.is_file():
        try:
            for line_number, raw_line in enumerate(
                cognitive_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line)
                if not isinstance(item, dict):
                    raise ValueError(f"line {line_number} is not a JSON object")
                cognitive_events.append(item)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            provenance_error(f"cognitive-runtime.jsonl is invalid: {exc}")

    acceptance_session_ids = {
        str(session_id)
        for item in by_id.values()
        for session_id in (
            item.get("session_ids")
            if isinstance(item.get("session_ids"), list)
            else []
        )
        if session_id
    }
    runtime_events: list[dict[str, Any]] = []
    runtime_path = evidence_dir / "events.jsonl"
    if runtime_path.is_file():
        try:
            for line_number, raw_line in enumerate(
                runtime_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line)
                if not isinstance(item, dict):
                    raise ValueError(f"line {line_number} is not a JSON object")
                runtime_events.append(item)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            provenance_error(f"events.jsonl is invalid: {exc}")

    from scripts.voice_acceptance import analyze_case

    for case_id in sorted(required_cases & set(by_id)):
        raw_case_session_ids = by_id[case_id].get("session_ids")
        case_session_ids = {
            str(value)
            for value in (
                raw_case_session_ids
                if isinstance(raw_case_session_ids, list)
                else []
            )
            if value
        }
        case_runtime_events = [
            item
            for item in runtime_events
            if str(item.get("sid") or "") in case_session_ids
        ]
        if not case_runtime_events:
            errors.append(f"Case {case_id} has no raw correlated runtime events")
            continue
        recomputed = analyze_case(case_id, case_runtime_events)
        recomputed_failures = [item.name for item in recomputed if not item.passed]
        if recomputed_failures:
            errors.append(
                f"Case {case_id} fails recomputed raw-event checks: "
                + ", ".join(recomputed_failures)
            )

        case_cognitive_events = [
            item
            for item in cognitive_events
            if str(item.get("sid") or "") in case_session_ids
        ]
        applied = [
            item
            for item in case_cognitive_events
            if item.get("mode") == "apply"
            and item.get("status") == "applied"
        ]
        minimum_applied = 2 if case_id == "follow-up" else 1
        if len(applied) < minimum_applied:
            provenance_error(
                f"Case {case_id} has {len(applied)} correlated applied cognitive events; "
                f"expected at least {minimum_applied}"
            )
        if any(item.get("status") == "error" for item in case_cognitive_events):
            provenance_error(
                f"Case {case_id} contains a correlated cognitive runtime error"
            )

        if case_id in {"speech-capability", "body-cancel"}:
            case_provider_modes = {
                match.group(1)
                for item in case_runtime_events
                if item.get("event") == "capability_runtime_done"
                for match in [
                    re.search(
                        r"(?:^|\s)provider_mode=([^\s]+)",
                        str(item.get("message") or ""),
                    )
                ]
                if match is not None and match.group(1) != "not-used"
            }
            cancelled_sim_status = bool(
                case_id == "body-cancel"
                and any(
                    item.get("event") == "soridormi_post_status"
                    and "mode=sim" in str(item.get("message") or "")
                    and "backend=runtime" in str(item.get("message") or "")
                    for item in case_runtime_events
                )
            )
            if case_provider_modes != {"sim"} and not cancelled_sim_status:
                provenance_error(
                    f"Case {case_id} does not prove exclusive simulator provider "
                    f"execution: {sorted(case_provider_modes)!r}"
                )
    provider_modes = {
        match.group(1)
        for item in runtime_events
        if str(item.get("sid") or "") in acceptance_session_ids
        and item.get("event") == "capability_runtime_done"
        for match in [
            re.search(
                r"(?:^|\s)provider_mode=([^\s]+)",
                str(item.get("message") or ""),
            )
        ]
        if match is not None and match.group(1) != "not-used"
    }
    if live_voice_profile and provider_modes:
        provenance_error(
            "Current-revision live voice evidence contains executable provider work: "
            + ", ".join(sorted(provider_modes))
        )
    elif not live_voice_profile and provider_modes != {"sim"}:
        provenance_error(
            "Voice evidence does not prove exclusive Soridormi simulator execution; "
            f"observed provider modes: {sorted(provider_modes)!r}"
        )
    correlated_cognitive_events = [
        item
        for item in cognitive_events
        if str(item.get("sid") or "") in acceptance_session_ids
    ]
    applied_events = [
        item
        for item in correlated_cognitive_events
        if item.get("mode") == "apply" and item.get("status") == "applied"
    ]
    if not applied_events:
        provenance_error(
            "Voice evidence is missing correlated applied cognitive runtime events"
        )
    cognitive_errors = [
        item
        for item in correlated_cognitive_events
        if item.get("status") == "error"
    ]
    if cognitive_errors:
        provenance_error(
            "Voice evidence contains cognitive runtime errors for acceptance sessions"
        )

    runtime_identity: dict[str, Any] = {}
    runtime_identity_source_bound = False
    artifact_manifest_valid = False
    artifact_count = 0
    if live_voice_profile:
        artifact_errors, artifacts_by_path = _validate_artifact_manifest(
            evidence_dir,
            required_files=required_files,
        )
        errors.extend(artifact_errors)
        artifact_count = len(artifacts_by_path)
        try:
            loaded_identity = load_runtime_evidence_identity(
                evidence_dir / "runtime-identity.json"
            )
        except RuntimeEvidenceIdentityError as exc:
            provenance_error(f"runtime-identity.json is invalid: {exc}")
            loaded_identity = None
        if loaded_identity is None:
            provenance_error("runtime-identity.json is missing")
        else:
            runtime_identity = loaded_identity
            identity_errors = _validate_live_voice_runtime_identity(
                runtime_identity,
                evidence_dir=evidence_dir,
                expected_revision=expected_chromie_revision,
            )
            for message in identity_errors:
                provenance_error(message)
            runtime_identity_source_bound = not identity_errors
            speech_case = by_id.get("speech-only")
            if isinstance(speech_case, dict):
                errors.extend(
                    _validate_live_voice_turn(
                        evidence_dir,
                        case=speech_case,
                        runtime_events=runtime_events,
                        cognitive_events=cognitive_events,
                        identity_sha256=str(
                            runtime_identity.get("identity_sha256") or ""
                        ),
                    )
                )
        recording_paths = {
            path.relative_to(evidence_dir).as_posix()
            for path in (evidence_dir / "recordings").glob("*.raw")
            if path.is_file() and path.stat().st_size > 0
        }
        missing_recording_artifacts = sorted(recording_paths - set(artifacts_by_path))
        if missing_recording_artifacts:
            errors.append(
                "bundle-manifest is missing correlated recordings: "
                + ", ".join(missing_recording_artifacts)
            )
        artifact_manifest_valid = not artifact_errors and not missing_recording_artifacts

    clean_provenance = bool(
        chromie.get("dirty") is False
        and (
            live_voice_profile
            or metadata.get("soridormi_local_dirty") is False
        )
    )
    source_binding_ready = (
        runtime_identity_source_bound if live_voice_profile else endpoint_source_bound
    )
    policy_evaluation_ready = bool(
        not errors and clean_provenance and source_binding_ready
    )
    live_voice_claim_eligible = bool(
        live_voice_profile
        and mode == "supervised"
        and policy_evaluation_ready
        and artifact_manifest_valid
    )
    return {
        "schema_version": 4 if live_voice_profile else 3,
        "verification_profile": profile,
        "evidence_dir": str(evidence_dir),
        "passed": not errors,
        "errors": errors,
        "provenance_errors": provenance_errors,
        "warnings": warnings,
        "acceptance_id": metadata.get("acceptance_id"),
        "chromie_revision": chromie.get("revision"),
        "chromie_version": chromie.get("version"),
        "soridormi_revision": manifest.get("upstream_commit"),
        "expected_provenance": {
            "chromie_revision": expected_chromie_revision,
            "chromie_version": expected_chromie_version,
            "soridormi_revision": expected_soridormi_revision,
        },
        "cognitive_runtime": {
            "event_count": len(correlated_cognitive_events),
            "applied_event_count": len(applied_events),
            "error_count": len(cognitive_errors),
        },
        "soridormi_mode": "sim" if provider_modes == {"sim"} else None,
        "case_count": len(by_id),
        "mode": mode,
        "clean_provenance": clean_provenance,
        "endpoint_source_bound": endpoint_source_bound,
        "runtime_identity": {
            "identity_sha256": runtime_identity.get("identity_sha256"),
            "source_bound": runtime_identity_source_bound,
        },
        "artifact_manifest": {
            "valid": artifact_manifest_valid,
            "artifact_count": artifact_count,
        },
        "policy_evaluation_ready": policy_evaluation_ready,
        "human_voice_device_claim_eligible": (
            not live_voice_profile
            and mode == "supervised"
            and policy_evaluation_ready
        ),
        "current_revision_live_voice_claim": {
            "eligible": live_voice_claim_eligible,
            "claim": (
                "one reviewed current-revision speech-only conversation completed "
                "through the physical microphone-to-audible-response loop"
            ),
            "release_qualified": False,
            "soridormi_claimed": False,
            "simulator_claimed": False,
            "physical_robot_claimed": False,
        },
        "release_qualified": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument(
        "--profile",
        choices=VERIFICATION_PROFILES,
        default=FULL_VOICE_MUJOCO_PROFILE,
        help=(
            "Verification claim profile. The default preserves the complete "
            "voice/MuJoCo matrix; current-revision-live-voice verifies only the "
            "strict supervised speech-only loop."
        ),
    )
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument(
        "--allow-automated",
        action="store_true",
        help=(
            "Permit automated evidence to enter compatibility-policy evaluation; "
            "this does not establish a human physical voice-device claim."
        ),
    )
    parser.add_argument("--expected-chromie-revision")
    parser.add_argument("--expected-chromie-version")
    parser.add_argument("--expected-soridormi-revision")
    parser.add_argument("--write-report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_bundle(
        args.evidence_dir,
        profile=args.profile,
        require_clean=args.require_clean,
        allow_automated=args.allow_automated,
        expected_chromie_revision=args.expected_chromie_revision,
        expected_chromie_version=args.expected_chromie_version,
        expected_soridormi_revision=args.expected_soridormi_revision,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
