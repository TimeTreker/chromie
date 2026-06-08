from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local import build_chromie_registry
from .models import CapabilityBundle, CapabilityRegistry

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ConfiguredRegistry:
    registry: CapabilityRegistry
    sources: list[str]
    manifest_files: list[str]


def parse_manifest_paths(raw: str | None) -> list[str]:
    """Parse a comma-separated list of manifest files or directories."""

    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _expand_environment(value: Any, *, source: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: _expand_environment(item, source=source)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_expand_environment(item, source=source) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if not os.environ.get(name):
            raise ValueError(
                f"capability manifest {source} requires non-empty environment variable {name}"
            )
        return os.environ[name]

    return _ENV_REFERENCE.sub(replace, value)


def load_capability_bundle(path: str | Path) -> CapabilityBundle:
    source = Path(path)
    data = CapabilityBundle.load_file(source).model_dump(mode="json")
    return CapabilityBundle.model_validate(_expand_environment(data, source=source))


def load_capability_bundles(paths: list[str]) -> tuple[list[CapabilityBundle], list[str]]:
    bundles: list[CapabilityBundle] = []
    loaded_files: list[str] = []

    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"capability manifest path does not exist: {path}")

        candidates = sorted(path.glob("*.json")) if path.is_dir() else [path]
        if path.is_dir() and not candidates:
            raise ValueError(f"capability manifest directory contains no JSON files: {path}")

        for candidate in candidates:
            if not candidate.is_file():
                raise ValueError(f"capability manifest is not a file: {candidate}")
            bundles.append(load_capability_bundle(candidate))
            loaded_files.append(str(candidate))

    return bundles, loaded_files


def build_configured_registry(paths: list[str]) -> ConfiguredRegistry:
    bundles, loaded_files = load_capability_bundles(paths)
    registry = build_chromie_registry(bundles)
    return ConfiguredRegistry(
        registry=registry,
        sources=["chromie", *(bundle.source for bundle in bundles)],
        manifest_files=loaded_files,
    )
