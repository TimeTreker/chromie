from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .local import build_chromie_registry
from .models import CapabilityBundle, CapabilityRegistry


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
            bundles.append(CapabilityBundle.load_file(candidate))
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
