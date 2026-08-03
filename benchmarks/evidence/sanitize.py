from __future__ import annotations

from dataclasses import dataclass
import getpass
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import tarfile
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from benchmarks.contracts import ContractError
from benchmarks.regression.archive import materialize_source, qualification_root

_REDACTED = "<redacted>"
_SECRET_KEY = re.compile(
    r"^(authorization|proxy[_-]?authorization|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret|password|passwd|private[_-]?key|secret|"
    r"aws[_-]?secret[_-]?access[_-]?key)$",
    re.IGNORECASE,
)
_SAFE_TOKEN_KEYS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "max_tokens",
    "token_count",
    "token_budget",
    "context_tokens",
    "required_context_tokens",
}
_SECRET_ASSIGNMENT = re.compile(
    r"(?im)^(?P<prefix>\s*(?:export\s+)?(?:[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|"
    r"REFRESH_TOKEN|PASSWORD|PASSWD|CLIENT_SECRET|PRIVATE_KEY|AUTHORIZATION))\s*=\s*)"
    r"(?P<value>[^\r\n]*)$"
)
_AUTH_HEADER = re.compile(
    r"(?im)^(?P<prefix>\s*(?:authorization|proxy-authorization)\s*:\s*)"
    r"(?P<value>[^\r\n]+)$"
)
_INLINE_SECRET = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})"
)
_HOME_PATH = re.compile(r"(?<![A-Za-z0-9_])(?:/home/[^/\s]+|/Users/[^/\s]+)")
_TEXT_SUFFIXES = {
    ".txt", ".log", ".json", ".jsonl", ".tsv", ".csv", ".md", ".yaml",
    ".yml", ".env", ".ini", ".toml", ".xml", ".html", ".sh", ".py",
}
_AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}


@dataclass
class SanitizeStats:
    copied: int = 0
    redacted_files: int = 0
    redaction_count: int = 0
    excluded: list[dict[str, str]] | None = None
    redacted: list[dict[str, Any]] | None = None
    unresolved: list[dict[str, str]] | None = None

    def __post_init__(self) -> None:
        self.excluded = [] if self.excluded is None else self.excluded
        self.redacted = [] if self.redacted is None else self.redacted
        self.unresolved = [] if self.unresolved is None else self.unresolved


def _is_secret_key(key: str) -> bool:
    normalized = key.strip().casefold().replace("-", "_")
    if normalized in _SAFE_TOKEN_KEYS:
        return False
    return bool(_SECRET_KEY.fullmatch(normalized)) or (
        normalized.endswith("_api_key")
        or normalized.endswith("_access_token")
        or normalized.endswith("_refresh_token")
        or normalized.endswith("_client_secret")
        or normalized.endswith("_password")
    )


def _redact_json(value: Any, replacements: Sequence[str]) -> tuple[Any, int]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        count = 0
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_key(key_text):
                result[key_text] = _REDACTED
                count += 1
            else:
                rendered, child_count = _redact_json(item, replacements)
                result[key_text] = rendered
                count += child_count
        return result, count
    if isinstance(value, list):
        result = []
        count = 0
        for item in value:
            rendered, child_count = _redact_json(item, replacements)
            result.append(rendered)
            count += child_count
        return result, count
    if isinstance(value, str):
        return _redact_text(value, replacements)
    return value, 0


def _redact_text(text: str, replacements: Sequence[str]) -> tuple[str, int]:
    count = 0

    def assignment(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group('prefix')}{_REDACTED}"

    def auth(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group('prefix')}{_REDACTED}"

    text = _SECRET_ASSIGNMENT.sub(assignment, text)
    text = _AUTH_HEADER.sub(auth, text)
    text, inline_count = _INLINE_SECRET.subn(_REDACTED, text)
    count += inline_count
    text, home_count = _HOME_PATH.subn("$HOME", text)
    count += home_count
    for value in replacements:
        if not value or value == _REDACTED:
            continue
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])"
        )
        text, occurrences = pattern.subn(_REDACTED, text)
        count += occurrences
    return text, count


def _looks_text(path: Path, data: bytes) -> bool:
    if path.suffix.casefold() in _TEXT_SUFFIXES or path.name.startswith(".env"):
        return True
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not decoded:
        return True
    printable = sum(char.isprintable() or char in "\r\n\t" for char in decoded)
    return printable / len(decoded) >= 0.95


def _excluded_reason(relative: Path, *, exclude_audio: bool) -> str | None:
    lowered = [part.casefold() for part in relative.parts]
    joined = "/".join(lowered)
    if relative.name == "artifact-index.json":
        return "regenerated_artifact_index"
    if (
        "/memory/" in f"/{joined}/"
        and relative.name.casefold() in {"profile.json", "durable-profile.json", "profile-memory.json"}
    ) or any(token in joined for token in ("durable_profile_memory", "durable-profile-memory")):
        return "durable_profile_memory_excluded"
    if exclude_audio and relative.suffix.casefold() in _AUDIO_SUFFIXES:
        return "audio_excluded_by_policy"
    return None


def _scan_secret_like(text: str) -> bool:
    if _INLINE_SECRET.search(text):
        return True
    if any(match.group("value").strip() != _REDACTED for match in _SECRET_ASSIGNMENT.finditer(text)):
        return True
    if any(match.group("value").strip() != _REDACTED for match in _AUTH_HEADER.finditer(text)):
        return True
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False

    def walk(value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(_is_secret_key(str(key)) and item != _REDACTED or walk(item) for key, item in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        if isinstance(value, str):
            return bool(_INLINE_SECRET.search(value))
        return False

    return walk(payload)


def _hash_index(root: Path) -> None:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "artifact-index.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(
            {
                "path": str(path.relative_to(root)),
                "size": path.stat().st_size,
                "sha256": digest,
            }
        )
    (root / "artifact-index.json").write_text(
        json.dumps({"schema_version": 1, "artifacts": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sanitize_evidence(
    source: Path,
    *,
    output_archive: Path,
    exclude_audio: bool = False,
    redact_values: Iterable[str] = (),
) -> dict[str, Any]:
    source = source.resolve()
    output_archive = output_archive.resolve()
    replacements = {
        str(value) for value in redact_values if str(value)
    }
    replacements.update({getpass.getuser(), socket.gethostname()})
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
    stats = SanitizeStats()
    with materialize_source(source) as materialized, tempfile.TemporaryDirectory(prefix="chromie-sanitize-") as temp:
        source_root = qualification_root(materialized)
        destination_root = Path(temp) / f"{source_root.name}-sanitized"
        destination_root.mkdir(parents=True)
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root)
            reason = _excluded_reason(relative, exclude_audio=exclude_audio)
            if reason:
                stats.excluded.append({"path": str(relative), "reason": reason})
                continue
            target = destination_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = path.read_bytes()
            if not _looks_text(path, data):
                shutil.copy2(path, target)
                stats.copied += 1
                continue
            text = data.decode("utf-8", errors="replace")
            count = 0
            rendered = text
            if path.suffix.casefold() == ".json":
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    rendered, count = _redact_text(text, sorted(replacements, key=len, reverse=True))
                else:
                    sanitized, count = _redact_json(payload, sorted(replacements, key=len, reverse=True))
                    rendered = json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            elif path.suffix.casefold() == ".jsonl":
                rendered_lines: list[str] = []
                for line in text.splitlines():
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        line_rendered, line_count = _redact_text(
                            line, sorted(replacements, key=len, reverse=True)
                        )
                    else:
                        sanitized, line_count = _redact_json(
                            payload, sorted(replacements, key=len, reverse=True)
                        )
                        line_rendered = json.dumps(
                            sanitized, ensure_ascii=False, sort_keys=True
                        )
                    rendered_lines.append(line_rendered)
                    count += line_count
                rendered = "\n".join(rendered_lines) + ("\n" if text.endswith("\n") else "")
            else:
                rendered, count = _redact_text(text, sorted(replacements, key=len, reverse=True))
            target.write_text(rendered, encoding="utf-8")
            stats.copied += 1
            if count:
                stats.redacted_files += 1
                stats.redaction_count += count
                stats.redacted.append({"path": str(relative), "redactions": count})
            if _scan_secret_like(rendered):
                stats.unresolved.append({"path": str(relative), "reason": "secret_like_content_remains"})

        safe_source, _ = _redact_text(
            str(source), sorted(replacements, key=len, reverse=True)
        )
        safe_output, _ = _redact_text(
            str(output_archive), sorted(replacements, key=len, reverse=True)
        )
        report = {
            "schema_version": 1,
            "kind": "chromie_evidence_sanitization_report",
            "source": safe_source,
            "source_sha256": source_digest,
            "output": safe_output,
            "policy": {
                "durable_profile_memory_included": False,
                "audio_included": not exclude_audio,
                "credentials_redacted": True,
                "local_identity_redacted": True,
                "raw_source_modified": False,
            },
            "summary": {
                "copied_files": stats.copied,
                "redacted_files": stats.redacted_files,
                "redaction_count": stats.redaction_count,
                "excluded_files": len(stats.excluded),
                "unresolved_findings": len(stats.unresolved),
            },
            "excluded": stats.excluded,
            "redacted": stats.redacted,
            "unresolved": stats.unresolved,
            "safe_to_upload": not stats.unresolved,
            "limitations": [
                "Conversational text and audio may remain private even after credential redaction.",
                "Review the sanitization report and archive contents before external upload.",
            ],
        }
        (destination_root / "sanitization-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _hash_index(destination_root)
        output_archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output_archive, "w:gz") as archive:
            archive.add(destination_root, arcname=destination_root.name)
    output_archive.with_suffix(output_archive.suffix + ".sha256").write_text(
        f"{hashlib.sha256(output_archive.read_bytes()).hexdigest()}  {output_archive.name}\n",
        encoding="utf-8",
    )
    return report
