#!/usr/bin/env python3
"""Dependency-free documentation consistency checks for Chromie.

The checker intentionally verifies high-value facts that commonly drift:
local links, documentation indexing, current development-focus declarations, and HTTP
route coverage in the API reference. It is not a Markdown style linter.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    from release_provenance import (
        declared_images,
        exact_requirement_errors,
        model_lock_errors,
        source_environment,
    )
except ImportError:
    from scripts.release_provenance import (
        declared_images,
        exact_requirement_errors,
        model_lock_errors,
        source_environment,
    )

ROOT = Path(__file__).resolve().parents[1]
DOC_INDEX = ROOT / "docs" / "README.md"
API_REFERENCE = ROOT / "docs" / "API_REFERENCE.md"
CONFIGURATION_REFERENCE = ROOT / "docs" / "CONFIGURATION.md"
PROJECT_CHARTER = ROOT / "docs" / "PROJECT_CHARTER.md"
ROADMAP = ROOT / "ROADMAP.md"
COMMON_ENV = ROOT / ".env.common"
DOCUMENTATION_AUTHORITY = ROOT / "config" / "documentation_authority.json"

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
STATUS_FILES = [
    ROOT / "README.md",
    ROOT / "ROADMAP.md",
    ROOT / "DEVELOPMENT_CHECKPOINT.md",
    ROOT / "docs" / "STATUS.md",
]
CURRENT_GATE_SUMMARY_FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "ACCEPTANCE.md",
    ROOT / "docs" / "PROJECT_GUIDE.zh-CN.md",
]
CURRENT_RUNTIME_TERM_FILES = [
    ROOT / "docs" / "COGNITIVE_TURN_LOOP.md",
    ROOT / "docs" / "COGNITIVE_GATEWAY.md",
    ROOT / "docs" / "GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md",
]
HARDCODED_GATE_COUNT_RE = re.compile(
    r"(?:\b\d{1,3},\d{3}\s+primary tests\b|\b\d{1,3},\d{3}\s+个主要测试)"
)

ROUTE_SOURCES = [
    ROOT / "agent" / "app" / "main.py",
    ROOT / "agent" / "app" / "main.py",
    ROOT / "hardware" / "daemon.py",
]

RUNTIME_CONFIG_SOURCES = [
    ROOT / "orchestrator" / "orchestrator.py",
    ROOT / "agent" / "app" / "main.py",
    ROOT / "asr" / "server.py",
    ROOT / "asr" / "settings.py",
    ROOT / "tts" / "server.py",
    ROOT / "agent" / "app" / "main.py",
]

# Generated dependency, cache, coverage, and build directories are not project
# documentation. Keep this list explicit so repository-owned hidden directories
# such as .github can still contain indexed Markdown files.
IGNORED_MARKDOWN_DIRS = {
    ".git",
    ".chromie",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "hf_cache",
    "node_modules",
    "site",
    "venv",
}

STALE_PHRASES = {
    "tool actions for a future executor": "TaskGraph execution is implemented",
    "vision_agent`: placeholder": "vision is a compatibility proposal, not an undocumented placeholder",
    "taskgraph execution is not connected": "TaskGraph execution endpoints are implemented",
    "/interaction still adapts": "native InteractionRuntime is now the default",
    "currently implemented by adapting the `/run` result": "native InteractionRuntime is now the default",
    "the native interaction agent is not present yet": "native InteractionRuntime is implemented",
    "replace `agentresultinteractionadapter` with native": "native output is already implemented",
    "non-skippable body-skill confirmation is not yet a complete spoken": "spoken request-bound confirmation is implemented",
    "complete non-skippable confirmation conversation": "spoken request-bound confirmation is implemented",
    "add request-bound confirmation dialogue": "spoken request-bound confirmation is implemented",
    "spoken-confirmation blocker remains": "only retained confirmation evidence remains open",
    "8c448e2de2cd8a602b0d48e31461f9be9f1b8d08": "stale repository snapshot revision",
    "current host has no microphone": "retained physical input now reaches VAD/ASR; the intelligible required utterance remains open",
}

MILESTONE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])M(?:0|[1-9][0-9]*)(?=\b|_)"
)
NUMBERED_STEP_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])step(?:\s+|[_-]?)(?:0|[1-9][0-9]*)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
NUMBERED_PHASE_PATH_RE = re.compile(
    r"(?:^|[._/-])(?:m|step)(?:0|[1-9][0-9]*)(?=$|[._/-])",
    re.IGNORECASE,
)
ABANDONED_RELEASE_VERSION_RE = re.compile(
    r"(?<![0-9.])0\.0\.1(?![0-9.])"
)
TEXT_SCAN_SUFFIXES = {
    ".env",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_SCAN_FILENAMES = {
    ".dockerignore",
    ".gitignore",
    "Dockerfile",
    "VERSION",
}


def markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        relative_parts = path.relative_to(ROOT).parts
        parent_parts = relative_parts[:-1]
        if any(part in IGNORED_MARKDOWN_DIRS for part in parent_parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def repository_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(ROOT).parts
        if any(part in IGNORED_MARKDOWN_DIRS for part in relative_parts[:-1]):
            continue
        if path.suffix.lower() in TEXT_SCAN_SUFFIXES or path.name in TEXT_SCAN_FILENAMES:
            files.append(path)
    return sorted(files)


def check_semantic_project_naming(errors: list[str]) -> None:
    """Reject development-order identifiers from the maintained source tree."""

    for path in repository_text_files():
        relative = path.relative_to(ROOT).as_posix()
        if NUMBERED_PHASE_PATH_RE.search(relative):
            errors.append(
                f"{relative}: path uses a numbered project-phase identifier; "
                "use a capability or issue-oriented name"
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in ABANDONED_RELEASE_VERSION_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{relative}:{line}: abandoned fixed release version is forbidden; "
                "use the development identity until a future version is explicitly planned"
            )
        forbidden_tokens = (
            (MILESTONE_TOKEN_RE, "numbered milestone"),
            (NUMBERED_STEP_TOKEN_RE, "numbered implementation-stage"),
        )
        for pattern, token_kind in forbidden_tokens:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{relative}:{line}: {token_kind} token is forbidden in "
                    "maintained source; use a semantic capability, issue, or evidence name"
                )


def normalized_link_target(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    # Optional Markdown title: path "title". Repository links do not rely on
    # spaces in local filenames, so splitting here is safe and avoids treating
    # titles as part of the path.
    value = value.split(" ", 1)[0]
    return unquote(value.split("#", 1)[0].split("?", 1)[0])


def is_external_or_anchor(target: str) -> bool:
    lowered = target.lower()
    return (
        not target
        or target.startswith("#")
        or lowered.startswith(("http://", "https://", "mailto:", "ftp://", "tel:"))
    )


def check_local_links(errors: list[str]) -> None:
    for source in markdown_files():
        text = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            raw = match.group(1).strip()
            if is_external_or_anchor(raw):
                continue
            target = normalized_link_target(raw)
            if not target:
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(
                    f"{source.relative_to(ROOT)}: local link escapes repository: {raw}"
                )
                continue
            if not resolved.exists():
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{source.relative_to(ROOT)}:{line}: missing local link target: {raw}"
                )


def index_targets() -> set[Path]:
    text = DOC_INDEX.read_text(encoding="utf-8")
    targets: set[Path] = set()
    for raw in MARKDOWN_LINK_RE.findall(text):
        if is_external_or_anchor(raw):
            continue
        target = normalized_link_target(raw)
        if target:
            targets.add((DOC_INDEX.parent / target).resolve())
    return targets


def check_document_index(errors: list[str]) -> None:
    linked = index_targets()
    for path in markdown_files():
        if path.resolve() == DOC_INDEX.resolve():
            continue
        if path.resolve() not in linked:
            errors.append(
                f"docs/README.md does not index {path.relative_to(ROOT).as_posix()}"
            )


def check_current_focus(errors: list[str]) -> None:
    for path in STATUS_FILES:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        if "goal-driven" not in lowered or "authority" not in lowered:
            errors.append(
                f"{path.relative_to(ROOT)} does not declare the current "
                "Goal-driven single-authority focus"
            )

    for path in markdown_files():
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase, reason in STALE_PHRASES.items():
            if phrase in lowered:
                errors.append(
                    f"{path.relative_to(ROOT)} contains stale phrase {phrase!r}: {reason}"
                )


def check_current_gate_summaries(errors: list[str]) -> None:
    """Keep current-facing summaries from copying revision-specific test counts."""

    for path in CURRENT_GATE_SUMMARY_FILES:
        text = path.read_text(encoding="utf-8")
        match = HARDCODED_GATE_COUNT_RE.search(text)
        if match is not None:
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{path.relative_to(ROOT)}:{line}: current gate summary hardcodes "
                "a test count; quote a fresh ./scripts/run_tests.sh result instead"
            )


def check_current_runtime_terminology(errors: list[str]) -> None:
    """Keep canonical architecture docs on the current runtime term."""

    for path in CURRENT_RUNTIME_TERM_FILES:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?<!Trusted Capability )Skill Runtime", text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{path.relative_to(ROOT)}:{line}: canonical architecture uses "
                "legacy Skill Runtime terminology; use Trusted Capability Runtime"
            )


def check_project_direction(errors: list[str]) -> None:
    charter = PROJECT_CHARTER.read_text(encoding="utf-8")
    for heading in (
        "## Mission",
        "## System boundaries",
        "## Engineering principles",
        "## Non-goals",
        "## Definition of success",
    ):
        if heading not in charter:
            errors.append(f"docs/PROJECT_CHARTER.md is missing {heading!r}")

    roadmap = ROADMAP.read_text(encoding="utf-8")
    for heading in (
        "## Current priorities",
        "## Completed foundations",
        "## Active source work",
        "## Open evidence track - Physical audio validation",
        "## Target-evidence closure track",
        "## Future phase - Physical pilot preparation",
        "## Later work",
        "## Anti-drift review",
    ):
        if heading not in roadmap:
            errors.append(f"ROADMAP.md is missing {heading!r}")
    obsolete_heading = re.search(
        r"^##\s+(?:M|R)\d+\b",
        roadmap,
        flags=re.MULTILINE,
    )
    if obsolete_heading is not None:
        errors.append(
            "ROADMAP.md still contains a numbered project-phase heading: "
            f"{obsolete_heading.group(0)!r}"
        )
    if "Earlier incremental work is represented by two completed" not in roadmap:
        errors.append(
            "ROADMAP.md does not describe the completed foundations semantically"
        )
    if re.search(
        r"Sequential milestone\s+codes are not part of the current project model",
        roadmap,
    ) is None:
        errors.append(
            "ROADMAP.md does not prohibit development-order milestone codes"
        )
    for question in (
        "Does it close the active milestone",
        "Is the behavior owned by Chromie or Soridormi",
        "Is the required evidence level explicit",
    ):
        if question not in roadmap:
            errors.append(f"ROADMAP.md is missing anti-drift check: {question!r}")


def fastapi_routes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
                and func.attr in {"get", "post", "put", "patch", "delete"}
            ):
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                value = decorator.args[0].value
                if isinstance(value, str):
                    routes.add(value)
    return routes


def check_api_reference(errors: list[str]) -> None:
    api_text = API_REFERENCE.read_text(encoding="utf-8")
    for source in ROUTE_SOURCES:
        for route in sorted(fastapi_routes(source)):
            if route not in api_text:
                errors.append(
                    f"docs/API_REFERENCE.md is missing route {route} from {source.relative_to(ROOT)}"
                )


def os_getenv_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getenv"
        ):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
    return names


def common_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in COMMON_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def check_configuration_reference(errors: list[str]) -> None:
    text = CONFIGURATION_REFERENCE.read_text(encoding="utf-8")
    active_names: set[str] = set()
    for source in RUNTIME_CONFIG_SOURCES:
        active_names.update(os_getenv_names(source))
    for name in sorted(active_names):
        if f"`{name}`" not in text:
            errors.append(
                f"docs/CONFIGURATION.md is missing active runtime variable {name}"
            )

    values = common_env_values()
    safety_default_names = (
        "ORCH_ENABLE_INTERACTION_RESPONSE",
        "ORCH_ENABLE_SORIDORMI_CAPABILITIES",
        "ORCH_GOAL_ASSOCIATION_MODE",
        "ORCH_FAST_PLANNER_MODE",
        "ORCH_DEEP_PLANNER_MODE",
        "ORCH_RESPONSE_COMPOSER_MODE",
        "ORCH_COGNITIVE_RUNTIME_MODE",
        "ORCH_COGNITIVE_APPLY_LANES",
        "AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED",
        "ORCH_AGENT_TIMEOUT_MS",
    )
    for name in safety_default_names:
        value = values.get(name)
        if value is None:
            errors.append(f".env.common is missing safety-critical setting {name}")
            continue
        row = re.search(
            rf"^\|\s*`{re.escape(name)}`\s*\|([^\n]+)$",
            text,
            flags=re.MULTILINE,
        )
        if row is None:
            errors.append(f"docs/CONFIGURATION.md is missing a table row for {name}")
        elif f"`{value}`" not in row.group(1):
            errors.append(
                f"docs/CONFIGURATION.md does not document {name}={value!r} "
                "from .env.common"
            )
    try:
        goal_interpreter_base_ms = int(values["AGENT_GOAL_INTERPRETER_TIMEOUT_MS"])
        goal_interpreter_llm_ms = int(values.get("AGENT_GOAL_INTERPRETER_LLM_TIMEOUT_MS", str(goal_interpreter_base_ms)))
        goal_interpreter_review_ms = int(
            values.get("AGENT_GOAL_INTERPRETER_REVIEW_TIMEOUT_MS", values.get("AGENT_GOAL_INTERPRETER_LLM_TIMEOUT_MS", str(goal_interpreter_base_ms)))
        )
        goal_interpreter_internal_ms = goal_interpreter_llm_ms + goal_interpreter_review_ms
        goal_interpreter_host_ms = int(values["ORCH_AGENT_TIMEOUT_MS"])
    except (KeyError, ValueError) as exc:
        errors.append(f".env.common has invalid Goal Interpreter timeout configuration: {exc}")
    else:
        catalog_ms = int(values.get("AGENT_GOAL_INTERPRETER_CAPABILITY_CATALOG_TIMEOUT_MS", "0"))
        if goal_interpreter_host_ms <= goal_interpreter_internal_ms + catalog_ms:
            errors.append(
                "ORCH_AGENT_TIMEOUT_MS must exceed AGENT_GOAL_INTERPRETER_CAPABILITY_CATALOG_TIMEOUT_MS "
                "plus AGENT_GOAL_INTERPRETER_LLM_TIMEOUT_MS and AGENT_GOAL_INTERPRETER_REVIEW_TIMEOUT_MS, so Goal Interpretation "
                "can finish or report its own timeout first"
            )




def _local_markdown_targets(source: Path) -> set[Path]:
    targets: set[Path] = set()
    text = source.read_text(encoding="utf-8", errors="replace")
    for raw in MARKDOWN_LINK_RE.findall(text):
        if is_external_or_anchor(raw):
            continue
        target = normalized_link_target(raw)
        if not target:
            continue
        resolved = (source.parent / target).resolve()
        if resolved.suffix.lower() == ".md" and resolved.is_file():
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                continue
            targets.add(resolved)
    return targets


def _matches_any(relative: str, patterns: list[str]) -> bool:
    path = Path(relative)
    return any(path.match(pattern) for pattern in patterns)


def _check_specialized_document_ownership(
    payload: dict[str, object], errors: list[str]
) -> None:
    ownership = payload.get("specialized_ownership")
    if not isinstance(ownership, dict):
        errors.append("specialized_ownership must be an object")
        return

    raw_entrypoints = ownership.get("entrypoint_paths")
    raw_globs = ownership.get("entrypoint_globs")
    raw_contracts = ownership.get("mechanical_contracts")
    if not isinstance(raw_entrypoints, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_entrypoints
    ):
        errors.append("specialized_ownership.entrypoint_paths must be non-empty strings")
        raw_entrypoints = []
    if not isinstance(raw_globs, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_globs
    ):
        errors.append("specialized_ownership.entrypoint_globs must be non-empty strings")
        raw_globs = []
    if not isinstance(raw_contracts, list):
        errors.append("specialized_ownership.mechanical_contracts must be a list")
        raw_contracts = []

    contract_globs: list[str] = []
    for item in raw_contracts:
        if not isinstance(item, dict):
            errors.append("mechanical contract ownership entry must be an object")
            continue
        pattern = str(item.get("glob") or "").strip()
        checker = str(item.get("checker") or "").strip()
        if not pattern or not checker:
            errors.append("mechanical contract ownership requires glob and checker")
            continue
        checker_path = (ROOT / checker).resolve()
        try:
            checker_path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"mechanical contract checker escapes repository: {checker}")
            continue
        if not checker_path.is_file():
            errors.append(f"mechanical contract checker does not exist: {checker}")
            continue
        contract_globs.append(pattern)

    documents = markdown_files()
    relative_by_path = {
        path.resolve(): path.relative_to(ROOT).as_posix() for path in documents
    }
    roots: set[Path] = set()
    for entry in payload.get("authorities") or []:
        if not isinstance(entry, dict):
            continue
        raw_path = str(entry.get("path") or "").strip()
        if raw_path and raw_path != "docs/README.md":
            roots.add((ROOT / raw_path).resolve())
    for raw_path in payload.get("core_reading_path") or []:
        if isinstance(raw_path, str) and raw_path.strip() and raw_path != "docs/README.md":
            roots.add((ROOT / raw_path).resolve())
    for raw_path in raw_entrypoints:
        path = (ROOT / str(raw_path)).resolve()
        if not path.is_file():
            errors.append(f"specialized documentation entrypoint does not exist: {raw_path}")
        else:
            roots.add(path)
    for path, relative in relative_by_path.items():
        if _matches_any(relative, [str(item) for item in raw_globs]):
            roots.add(path)
        if _matches_any(relative, contract_globs):
            roots.add(path)

    reachable: set[Path] = set()
    pending = [path for path in roots if path in relative_by_path]
    while pending:
        source = pending.pop()
        if source in reachable:
            continue
        reachable.add(source)
        if source == DOC_INDEX.resolve():
            continue
        for target in _local_markdown_targets(source):
            if target in relative_by_path and target not in reachable:
                pending.append(target)

    for path, relative in sorted(relative_by_path.items(), key=lambda item: item[1]):
        if path == DOC_INDEX.resolve():
            continue
        if path not in reachable:
            errors.append(
                f"specialized documentation has no current owner entrypoint or "
                f"mechanical contract: {relative}"
            )


def check_documentation_authority(errors: list[str]) -> None:
    required_roles = {
        "mission_architecture",
        "delivery_order",
        "implementation_and_evidence_status",
        "target_evidence_closure",
        "resume_point",
        "operations",
        "configuration",
        "api_contracts",
        "security",
        "documentation_index",
        "notable_changes",
    }
    try:
        payload = json.loads(DOCUMENTATION_AUTHORITY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot read documentation authority registry: {exc}")
        return
    if payload.get("schema_version") != "1.0":
        errors.append("documentation authority registry must use schema_version=1.0")

    authorities = payload.get("authorities")
    if not isinstance(authorities, list):
        errors.append("documentation authority registry authorities must be a list")
        return
    roles: set[str] = set()
    paths: set[str] = set()
    for entry in authorities:
        if not isinstance(entry, dict):
            errors.append("documentation authority entry must be an object")
            continue
        role = str(entry.get("role") or "").strip()
        raw_path = str(entry.get("path") or "").strip()
        if not role or role in roles:
            errors.append(f"documentation authority role is missing or duplicated: {role!r}")
        else:
            roles.add(role)
        if not raw_path or raw_path in paths:
            errors.append(f"documentation authority path is missing or duplicated: {raw_path!r}")
            continue
        paths.add(raw_path)
        path = (ROOT / raw_path).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"documentation authority path escapes repository: {raw_path}")
            continue
        if not path.is_file():
            errors.append(f"documentation authority path does not exist: {raw_path}")
    missing = sorted(required_roles - roles)
    if missing:
        errors.append(f"documentation authority registry is missing roles: {missing}")

    _check_specialized_document_ownership(payload, errors)

    archives = payload.get("historical_archives")
    if not isinstance(archives, list):
        errors.append("historical_archives must be a list")
    else:
        for raw_path in archives:
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append("historical archive path must be a non-empty string")
                continue
            path = (ROOT / raw_path).resolve()
            try:
                path.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"historical archive path escapes repository: {raw_path}")
                continue
            if not path.is_file():
                errors.append(f"historical archive does not exist: {raw_path}")
                continue
            text = path.read_text(encoding="utf-8")
            if "Status: historical archive; not current authority" not in text:
                errors.append(f"historical archive lacks authority marker: {raw_path}")

    core_path = payload.get("core_reading_path")
    if not isinstance(core_path, list) or not core_path:
        errors.append("core_reading_path must be a non-empty list")
    else:
        if len(core_path) != len(set(core_path)):
            errors.append("core_reading_path contains duplicate documents")
        ratchets = payload.get("surface_ratchets") or {}
        try:
            max_core = int(ratchets.get("max_core_reading_path", 15))
        except (TypeError, ValueError):
            errors.append("surface_ratchets.max_core_reading_path must be an integer")
            max_core = 15
        if len(core_path) > max_core:
            errors.append(
                f"core_reading_path has {len(core_path)} documents; maximum is {max_core}"
            )
        index_text = DOC_INDEX.read_text(encoding="utf-8") if DOC_INDEX.is_file() else ""
        for raw_path in core_path:
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append("core_reading_path entries must be non-empty strings")
                continue
            path = (ROOT / raw_path).resolve()
            try:
                path.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"core reading path escapes repository: {raw_path}")
                continue
            if not path.is_file():
                errors.append(f"core reading document does not exist: {raw_path}")
                continue
            relative_from_index = Path(raw_path)
            try:
                link_target = path.relative_to(DOC_INDEX.parent).as_posix()
            except ValueError:
                link_target = "../" + relative_from_index.as_posix()
            if link_target not in index_text and raw_path not in index_text:
                errors.append(
                    f"core reading document is not linked from docs/README.md: {raw_path}"
                )

    surface_ratchets = payload.get("surface_ratchets")
    if not isinstance(surface_ratchets, dict):
        errors.append("surface_ratchets must be an object")
    else:
        markdown_count = len(markdown_files())
        docs_root_count = len(list((ROOT / "docs").glob("*.md")))
        for key, actual in (
            ("max_markdown_files", markdown_count),
            ("max_docs_root_markdown_files", docs_root_count),
        ):
            try:
                maximum = int(surface_ratchets[key])
            except (KeyError, TypeError, ValueError):
                errors.append(f"surface_ratchets.{key} must be an integer")
                continue
            if actual > maximum:
                errors.append(
                    f"documentation surface grew: {key}={actual}, ratchet={maximum}"
                )

    limits = payload.get("concise_line_limits")
    if not isinstance(limits, dict):
        errors.append("concise_line_limits must be an object")
    else:
        for raw_path, raw_limit in limits.items():
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                errors.append(f"invalid documentation line limit for {raw_path!r}")
                continue
            path = ROOT / str(raw_path)
            if not path.is_file():
                errors.append(f"concise authority document does not exist: {raw_path}")
                continue
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > limit:
                errors.append(
                    f"{raw_path} has {line_count} lines, exceeding reviewed authority limit {limit}"
                )

    authority_doc = ROOT / "docs" / "DOCUMENTATION_AUTHORITY.md"
    if not authority_doc.is_file():
        errors.append("docs/DOCUMENTATION_AUTHORITY.md is missing")
    else:
        text = authority_doc.read_text(encoding="utf-8")
        for phrase in (
            "One owner per current fact",
            "Four-axis",
            "In-tree historical archives",
            "config/documentation_authority.json",
        ):
            if phrase not in text:
                errors.append(
                    f"docs/DOCUMENTATION_AUTHORITY.md is missing {phrase!r}"
                )

def check_artifact_reproducibility(errors: list[str]) -> None:
    errors.extend(exact_requirement_errors(ROOT))
    declared_images(ROOT, source_environment(ROOT))
    errors.extend(model_lock_errors(ROOT, source_environment(ROOT)))
    try:
        compatibility = json.loads(
            (ROOT / "release" / "compatibility.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (ROOT / "capabilities" / "soridormi.json").read_text(encoding="utf-8")
        )
        compatibility_revision = compatibility["soridormi"]["upstream_commit"]
        manifest_revision = manifest["metadata"]["upstream_commit"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot read Soridormi artifact provenance: {exc}")
    else:
        if compatibility_revision != manifest_revision:
            errors.append(
                "release/compatibility.json Soridormi revision does not match "
                "capabilities/soridormi.json metadata.upstream_commit"
            )
        release_state = str(compatibility.get("release_state") or "").strip()
        gaps = compatibility.get("known_evidence_gaps")
        chromie = compatibility.get("chromie") or {}
        declared_version = str(chromie.get("version") or "").strip()
        if release_state != "development":
            errors.append(
                "release/compatibility.json must remain in development state "
                "while no publication target is configured"
            )
        if declared_version != "development":
            errors.append(
                "release/compatibility.json must use chromie.version=development"
            )
        if chromie.get("release_tag"):
            errors.append(
                "development compatibility must not declare a release_tag"
            )
        if not isinstance(gaps, list) or any(
            not isinstance(item, str) or not item.strip() for item in gaps
        ):
            errors.append(
                "known_evidence_gaps must be a list of non-empty strings"
            )
        if not (ROOT / "release" / "development.md").is_file():
            errors.append("release/development.md is missing")
    release_text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    for required in ("build-provenance.json", "model-lock.json"):
        if required not in release_text:
            errors.append(f"docs/RELEASE.md does not describe {required}")

def main() -> int:
    errors: list[str] = []
    check_local_links(errors)
    check_document_index(errors)
    check_semantic_project_naming(errors)
    check_current_focus(errors)
    check_current_gate_summaries(errors)
    check_current_runtime_terminology(errors)
    check_project_direction(errors)
    check_api_reference(errors)
    check_configuration_reference(errors)
    check_artifact_reproducibility(errors)
    check_documentation_authority(errors)

    if errors:
        print("Documentation checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Documentation checks passed: "
        f"{len(markdown_files())} Markdown files, project direction, "
        "local links, semantic project naming, current focus, API routes, "
        "runtime configuration coverage and safety defaults, "
        "reproducible development artifact inputs, and documentation authority."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
