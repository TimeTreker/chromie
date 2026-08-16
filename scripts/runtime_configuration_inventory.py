#!/usr/bin/env python3
"""Generate and verify Chromie's runtime configuration-surface inventory."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = ROOT / "config" / "runtime_configuration_surface.json"
INVENTORY_PATH = ROOT / "config" / "runtime_configuration_inventory.json"
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
COMPOSE_KEY_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::[-?+][^}]*)?\}")
ENV_LINE_RE = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=")
SERVICE_ROOTS = {"agent", "asr", "hardware", "tts"}
BOOL_TRUE = {"1", "true", "yes", "on"}
BOOL_FALSE = {"0", "false", "no", "off"}


class ConfigurationInventoryError(RuntimeError):
    """Raised when the configuration surface is incomplete or contradictory."""


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationInventoryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationInventoryError(f"{path} must contain a JSON object")
    return value


def _env_files(root: Path) -> list[Path]:
    candidates = [
        root / ".env.common",
        root / ".env.local.example",
        root / "orchestrator" / ".env.local.example",
    ]
    candidates.extend(sorted((root / "env" / "profiles").glob("*.env")))
    candidates.extend(sorted((root / "env" / "modes").glob("*.env")))
    candidates.extend(sorted((root / "env" / "validation").glob("*.env")))
    return [path for path in candidates if path.is_file()]


def parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE_RE.match(raw.strip())
        if match:
            keys.add(match.group(1))
    return keys


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if KEY_RE.fullmatch(node.value) else None
    return None


def python_env_keys(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return set()
    keys: set[str] = set()
    host_parsers = {"_raw", "_text", "_bool", "_boolean", "_int", "_integer", "_float", "_floating", "_csv", "_choice", "_path", "_optional_int", "_optional_path", "_device", "_phrases"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "getenv"
                    and node.args
                ):
                    key = _literal_string(node.args[0])
                    if key:
                        keys.add(key)
                elif (
                    func.attr == "get"
                    and isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Name)
                    and func.value.value.id == "os"
                    and func.value.attr == "environ"
                    and node.args
                ):
                    key = _literal_string(node.args[0])
                    if key:
                        keys.add(key)
            elif isinstance(func, ast.Name) and func.id in host_parsers:
                if len(node.args) >= 2:
                    key = _literal_string(node.args[1])
                    if key:
                        keys.add(key)
        elif isinstance(node, ast.Subscript):
            value = node.value
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "os"
                and value.attr == "environ"
            ):
                key = _literal_string(node.slice)
                if key:
                    keys.add(key)
    return keys


def compose_env_keys(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(COMPOSE_KEY_RE.findall(text))


def discover(root: Path = ROOT) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    owners: dict[str, set[str]] = defaultdict(set)
    env_sources: dict[str, set[str]] = defaultdict(set)

    for path in _env_files(root):
        relative = path.relative_to(root).as_posix()
        for key in parse_env_keys(path):
            owners[key].add(relative)
            env_sources[key].add(relative)

    source_paths: list[Path] = []
    for top in ("agent", "asr", "hardware", "orchestrator", "scripts", "shared", "tts"):
        source_paths.extend(
            path
            for path in (root / top).rglob("*.py")
            if not any(
                part in {"__pycache__", ".git", ".venv", "venv"}
                for part in path.parts
            )
        )
    for path in sorted(source_paths):
        relative = path.relative_to(root).as_posix()
        for key in python_env_keys(path):
            owners[key].add(relative)

    for path in (root / "docker-compose.yml", *sorted(root.glob("compose*.yaml"))):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        for key in compose_env_keys(path):
            owners[key].add(relative)

    return set(owners), owners, env_sources


def _is_boolean_key(key: str, env_sources: dict[str, set[str]], root: Path) -> bool:
    observed: set[str] = set()
    for raw_path in env_sources.get(key, set()):
        path = root / raw_path
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped.startswith(key + "="):
                continue
            observed.add(stripped.split("=", 1)[1].strip().strip("'\"").casefold())
    return bool(observed) and observed.issubset(BOOL_TRUE | BOOL_FALSE)


def _category(
    key: str,
    *,
    owners: set[str],
    env_sources: set[str],
    surface: dict,
) -> str:
    public_choices = set(surface["public_choices"])
    aliases = dict(surface["compatibility_aliases"])
    acceptance_prefixes = tuple(surface["acceptance_override_prefixes"])
    if key in public_choices:
        return "public_choice"
    if key in aliases:
        return "bounded_compatibility_alias"
    if key.startswith(acceptance_prefixes) or any(
        path.startswith("env/validation/") for path in env_sources
    ):
        return "acceptance_override"
    code_owners = {
        path.split("/", 1)[0]
        for path in owners
        if path.endswith(".py") and "/" in path
    }
    if code_owners and code_owners.issubset(SERVICE_ROOTS):
        return "service_internal"
    if any(
        path == ".env.common"
        or path.startswith("env/profiles/")
        or path.startswith("env/modes/")
        for path in env_sources
    ):
        return "profile_constant"
    return "service_internal"


def build_inventory(root: Path = ROOT) -> dict:
    surface = _load_json(root / SURFACE_PATH.relative_to(ROOT))
    if surface.get("schema_version") != "1.0":
        raise ConfigurationInventoryError("configuration surface must use schema_version=1.0")

    modes = surface.get("maintained_modes")
    if not isinstance(modes, dict) or not modes:
        raise ConfigurationInventoryError("maintained_modes must be a non-empty object")
    required_mode_keys = {
        "CHROMIE_OPERATOR_MODE",
        "ORCH_ACTION_DRY_RUN",
        "ORCH_COGNITIVE_APPLY_LANES",
        "ORCH_COGNITIVE_RUNTIME_MODE",
        "ORCH_ENABLE_AGENT",
        "ORCH_ENABLE_INTERACTION_RESPONSE",
        "ORCH_ENABLE_SORIDORMI_CAPABILITIES",
    }
    for name, spec in sorted(modes.items()):
        if not isinstance(spec, dict):
            raise ConfigurationInventoryError(f"mode {name} must be an object")
        mode_path = root / str(spec.get("file") or "")
        launcher = root / str(spec.get("launcher") or "")
        if not mode_path.is_file() or not launcher.is_file():
            raise ConfigurationInventoryError(f"mode {name} has missing file or launcher")
        values = parse_env_keys(mode_path)
        missing = sorted(required_mode_keys - values)
        if missing:
            raise ConfigurationInventoryError(
                f"mode {name} is missing required keys: {', '.join(missing)}"
            )
        launcher_text = launcher.read_text(encoding="utf-8")
        if name not in launcher_text and "CHROMIE_OPERATOR_MODE" not in launcher_text:
            raise ConfigurationInventoryError(
                f"mode launcher {spec['launcher']} does not select CHROMIE_OPERATOR_MODE"
            )

    keys, owners_by_key, env_sources_by_key = discover(root)
    entries = []
    counts: dict[str, int] = defaultdict(int)
    for key in sorted(keys):
        owners = owners_by_key[key]
        env_sources = env_sources_by_key[key]
        category = _category(
            key,
            owners=owners,
            env_sources=env_sources,
            surface=surface,
        )
        counts[category] += 1
        entries.append(
            {
                "key": key,
                "category": category,
                "boolean": _is_boolean_key(key, env_sources_by_key, root),
                "owners": sorted(owners),
            }
        )

    declared_public_booleans = set(surface.get("public_boolean_choices") or [])
    if not declared_public_booleans.issubset(set(surface["public_choices"])):
        raise ConfigurationInventoryError(
            "public_boolean_choices must be a subset of public_choices"
        )
    public_boolean_count = len(declared_public_booleans)
    for entry in entries:
        if entry["key"] in declared_public_booleans:
            entry["boolean"] = True
    alias_count = counts["bounded_compatibility_alias"]
    ratchets = surface.get("ratchets") or {}
    if public_boolean_count > int(ratchets.get("max_public_boolean_choices", 0)):
        raise ConfigurationInventoryError(
            f"public boolean choices grew to {public_boolean_count}"
        )
    if alias_count > int(ratchets.get("max_compatibility_aliases", 0)):
        raise ConfigurationInventoryError(
            f"compatibility aliases grew to {alias_count}"
        )

    return {
        "schema_version": "1.0",
        "maintained_modes": sorted(modes),
        "summary": {
            "total_keys": len(entries),
            "category_counts": dict(sorted(counts.items())),
            "public_boolean_choices": public_boolean_count,
            "compatibility_aliases": alias_count,
        },
        "entries": entries,
    }


def render(inventory: dict) -> str:
    return json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=INVENTORY_PATH)
    args = parser.parse_args(argv)
    try:
        inventory = build_inventory(ROOT)
        content = render(inventory)
        if args.check:
            current = args.output.read_text(encoding="utf-8")
            if current != content:
                raise ConfigurationInventoryError(
                    f"{args.output.relative_to(ROOT)} is stale; regenerate it"
                )
        else:
            args.output.write_text(content, encoding="utf-8")
    except (OSError, ConfigurationInventoryError) as exc:
        print(f"[configuration-inventory][error] {exc}", file=sys.stderr)
        return 1
    summary = inventory["summary"]
    print(
        "[configuration-inventory] "
        f"keys={summary['total_keys']} modes={len(inventory['maintained_modes'])} "
        f"public_booleans={summary['public_boolean_choices']} "
        f"aliases={summary['compatibility_aliases']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
