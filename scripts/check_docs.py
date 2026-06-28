#!/usr/bin/env python3
"""Dependency-free documentation consistency checks for Chromie.

The checker intentionally verifies high-value facts that commonly drift:
local links, documentation indexing, current milestone declarations, and HTTP
route coverage in the API reference. It is not a Markdown style linter.
"""

from __future__ import annotations

import ast
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

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
STATUS_FILES = [
    ROOT / "README.md",
    ROOT / "ROADMAP.md",
    ROOT / "DEVELOPMENT_CHECKPOINT.md",
    ROOT / "docs" / "STATUS.md",
]

ROUTE_SOURCES = [
    ROOT / "router" / "app" / "main.py",
    ROOT / "agent" / "app" / "main.py",
    ROOT / "hardware" / "daemon.py",
]

RUNTIME_CONFIG_SOURCES = [
    ROOT / "orchestrator" / "orchestrator.py",
    ROOT / "agent" / "app" / "main.py",
    ROOT / "asr" / "server.py",
    ROOT / "tts" / "server.py",
    ROOT / "router" / "app" / "main.py",
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
    "node_modules",
    "site",
    "venv",
}

STALE_PHRASES = {
    "current milestone is M6": "old current-milestone wording",
    "current engineering milestone: **M6": "old M6 status declaration",
    "the current milestone is **M6": "old M6 status declaration",
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
    "current engineering milestone: **m13": "historical milestone numbering is no longer the delivery model",
    "active milestone: m13": "historical milestone numbering is no longer the delivery model",
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
        if "M13" not in text or "text-to-MuJoCo" not in text:
            errors.append(
                f"{path.relative_to(ROOT)} does not declare the current "
                "M13 text-to-MuJoCo focus"
            )

    for path in markdown_files():
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase, reason in STALE_PHRASES.items():
            if phrase in lowered:
                errors.append(
                    f"{path.relative_to(ROOT)} contains stale phrase {phrase!r}: {reason}"
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
        "## Completed foundations",
        "## Completed phase - Text-to-MuJoCo interaction closure",
        "## Open evidence track - Physical audio validation",
        "## Completed phase - Robust simulation and provider readiness",
        "## Current phase - Physical pilot preparation",
        "## Later work",
    ):
        if heading not in roadmap:
            errors.append(f"ROADMAP.md is missing {heading!r}")
    for obsolete in (
        "## M13 ",
        "## M14 ",
        "## M15 ",
        "## M16 ",
        "## R1 ",
        "## R2 ",
        "## R3 ",
    ):
        if obsolete in roadmap:
            errors.append(f"ROADMAP.md still contains obsolete section {obsolete!r}")
    if "Earlier work previously labeled M0-M12" not in roadmap:
        errors.append("ROADMAP.md does not collapse historical M0-M12 work")
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
    try:
        router_internal_ms = int(values["ROUTER_TIMEOUT_MS"])
        router_host_ms = int(values["ORCH_ROUTER_TIMEOUT_MS"])
    except (KeyError, ValueError) as exc:
        errors.append(f".env.common has invalid Router timeout configuration: {exc}")
    else:
        catalog_ms = int(values.get("ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS", "0"))
        if router_host_ms <= router_internal_ms + catalog_ms:
            errors.append(
                "ORCH_ROUTER_TIMEOUT_MS must exceed ROUTER_TIMEOUT_MS plus "
                "ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS so the "
                "Router can finish or report its own timeout first"
            )



def check_release_reproducibility(errors: list[str]) -> None:
    errors.extend(exact_requirement_errors(ROOT))
    declared_images(ROOT, source_environment(ROOT))
    errors.extend(model_lock_errors(ROOT, source_environment(ROOT)))
    release_text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    for required in ("build-provenance.json", "model-lock.json"):
        if required not in release_text:
            errors.append(f"docs/RELEASE.md does not describe {required}")

def main() -> int:
    errors: list[str] = []
    check_local_links(errors)
    check_document_index(errors)
    check_current_focus(errors)
    check_project_direction(errors)
    check_api_reference(errors)
    check_configuration_reference(errors)
    check_release_reproducibility(errors)

    if errors:
        print("Documentation checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Documentation checks passed: "
        f"{len(markdown_files())} Markdown files, project direction, "
        "local links, current focus, API routes, runtime configuration, "
        "and reproducible release inputs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
