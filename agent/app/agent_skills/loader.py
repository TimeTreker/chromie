from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

import yaml
from pydantic import ValidationError

class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that also rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


try:
    from chromie_contracts.agent_skill import (
        AgentSkillDocument,
        AgentSkillLoadFailure,
        AgentSkillLoadFailureReason,
        AgentSkillMetadata,
        AgentSkillProjection,
        AgentSkillProjectionName,
        AgentSkillRegistrySnapshot,
        AgentSkillSummary,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.agent_skill import (
        AgentSkillDocument,
        AgentSkillLoadFailure,
        AgentSkillLoadFailureReason,
        AgentSkillMetadata,
        AgentSkillProjection,
        AgentSkillProjectionName,
        AgentSkillRegistrySnapshot,
        AgentSkillSummary,
    )

_METADATA_NAME = "skill.yaml"
_SKILL_DOCUMENT_NAME = "SKILL.md"
_MAX_METADATA_BYTES = 64 * 1024
_MAX_PACKAGE_FILES = 128
_MAX_PACKAGE_BYTES = 4 * 1024 * 1024
_MAX_MARKDOWN_BYTES = 256 * 1024


class AgentSkillLoadError(ValueError):
    """Typed fail-closed error raised for one invalid configured Skill root/package."""

    def __init__(
        self,
        reason: AgentSkillLoadFailureReason,
        source: str | Path,
        message: str,
        *,
        agent_skill_id: str | None = None,
    ) -> None:
        self.failure = AgentSkillLoadFailure(
            reason=reason,
            source=str(source),
            message=message,
            agent_skill_id=agent_skill_id,
        )
        super().__init__(f"{reason}: {source}: {message}")


@dataclass(frozen=True)
class _LoadedAgentSkillPackage:
    metadata: AgentSkillMetadata
    root: Path
    package_dir: Path
    metadata_path: Path
    document_path: Path
    projection_paths: Mapping[AgentSkillProjectionName, Path]

    @property
    def summary(self) -> AgentSkillSummary:
        return AgentSkillSummary(
            agent_skill_id=self.metadata.agent_skill_id,
            version=self.metadata.version,
            title=self.metadata.title,
            description=self.metadata.description,
            content_digest=self.metadata.content_digest,
            extends=self.metadata.extends,
            required_capabilities=self.metadata.required_capabilities,
            optional_capabilities=self.metadata.optional_capabilities,
            applicable_routes=self.metadata.applicable_routes,
            available_projections=tuple(
                sorted(item.name for item in self.metadata.projections)
            ),
        )


@dataclass(frozen=True)
class ConfiguredAgentSkillRegistry:
    registry: "AgentSkillRegistry"
    roots: tuple[str, ...]
    package_files: tuple[str, ...]

    def snapshot(self) -> AgentSkillRegistrySnapshot:
        return self.registry.snapshot(
            roots=self.roots,
            package_files=self.package_files,
        )


def parse_agent_skill_roots(raw: str | None) -> list[str]:
    """Parse an explicit comma-separated list of Agent Skill roots."""

    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _raise(
    reason: AgentSkillLoadFailureReason,
    source: str | Path,
    message: str,
    *,
    agent_skill_id: str | None = None,
) -> None:
    raise AgentSkillLoadError(
        reason,
        source,
        message,
        agent_skill_id=agent_skill_id,
    )


def _assert_regular_file_within(
    path: Path,
    *,
    package_dir: Path,
    root: Path,
    missing_reason: AgentSkillLoadFailureReason = "content_missing",
) -> Path:
    if path.is_symlink():
        _raise("unsafe_path", path, "symlinked Skill content is not allowed")
    if not path.exists():
        _raise(missing_reason, path, "required file does not exist")
    if not path.is_file():
        _raise("unsafe_path", path, "Skill content must be a regular file")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(package_dir)
        resolved.relative_to(root)
    except ValueError:
        _raise("unsafe_path", path, "Skill content escapes its configured package/root")
    return resolved


def _iter_package_content_files(package_dir: Path, *, root: Path) -> list[Path]:
    files: list[Path] = []
    total_bytes = 0
    for candidate in sorted(package_dir.rglob("*"), key=lambda item: item.as_posix()):
        if candidate == package_dir / _METADATA_NAME:
            continue
        if candidate.is_symlink():
            _raise("unsafe_path", candidate, "symlinks are not allowed inside Agent Skill packages")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            _raise("unsafe_path", candidate, "package content must be regular files or directories")
        resolved = _assert_regular_file_within(candidate, package_dir=package_dir, root=root)
        files.append(resolved)
        total_bytes += resolved.stat().st_size
        if len(files) > _MAX_PACKAGE_FILES:
            _raise(
                "content_too_large",
                package_dir,
                f"package contains more than {_MAX_PACKAGE_FILES} content files",
            )
        if total_bytes > _MAX_PACKAGE_BYTES:
            _raise(
                "content_too_large",
                package_dir,
                f"package content exceeds {_MAX_PACKAGE_BYTES} bytes",
            )
    return files


def compute_agent_skill_content_digest(package_dir: str | Path) -> str:
    """Return a deterministic digest for all package files except skill.yaml.

    The digest frames each package-relative path and byte length before its bytes,
    so renames and ambiguous concatenations cannot preserve the digest.
    """

    package = Path(package_dir).expanduser()
    if not package.exists() or not package.is_dir():
        _raise("root_not_directory", package, "Agent Skill package must be a directory")
    if package.is_symlink():
        _raise("unsafe_path", package, "symlinked Agent Skill packages are not allowed")
    package = package.resolve(strict=True)
    root = package.parent.resolve(strict=True)
    files = _iter_package_content_files(package, root=root)
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(package).as_posix().encode("utf-8")
        size = path.stat().st_size
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_yaml_mapping(metadata_path: Path) -> dict[str, object]:
    size = metadata_path.stat().st_size
    if size > _MAX_METADATA_BYTES:
        _raise(
            "metadata_invalid",
            metadata_path,
            f"metadata exceeds {_MAX_METADATA_BYTES} bytes",
        )
    try:
        raw = yaml.load(
            metadata_path.read_text(encoding="utf-8"),
            Loader=_UniqueKeySafeLoader,
        )
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        _raise("metadata_invalid", metadata_path, f"cannot parse safe YAML: {exc}")
    if not isinstance(raw, dict):
        _raise("metadata_invalid", metadata_path, "metadata must be one YAML mapping")
    return raw


def _load_package(package_dir: Path, *, root: Path) -> _LoadedAgentSkillPackage:
    if package_dir.is_symlink():
        _raise("unsafe_path", package_dir, "symlinked Agent Skill packages are not allowed")
    package_dir = package_dir.resolve(strict=True)
    try:
        package_dir.relative_to(root)
    except ValueError:
        _raise("unsafe_path", package_dir, "Agent Skill package escapes its configured root")

    metadata_path = _assert_regular_file_within(
        package_dir / _METADATA_NAME,
        package_dir=package_dir,
        root=root,
        missing_reason="metadata_missing",
    )
    try:
        metadata = AgentSkillMetadata.model_validate(_read_yaml_mapping(metadata_path))
    except ValidationError as exc:
        _raise("metadata_invalid", metadata_path, str(exc))

    if not metadata.owner_approved:
        _raise(
            "owner_approval_required",
            metadata_path,
            "only explicitly owner-approved Agent Skills may be loaded",
            agent_skill_id=metadata.agent_skill_id,
        )

    document_path = _assert_regular_file_within(
        package_dir / _SKILL_DOCUMENT_NAME,
        package_dir=package_dir,
        root=root,
    )
    projection_paths: dict[AgentSkillProjectionName, Path] = {}
    for declaration in metadata.projections:
        projection_paths[declaration.name] = _assert_regular_file_within(
            package_dir / declaration.path,
            package_dir=package_dir,
            root=root,
        )

    actual_digest = compute_agent_skill_content_digest(package_dir)
    if actual_digest != metadata.content_digest:
        _raise(
            "content_digest_mismatch",
            package_dir,
            f"metadata declares {metadata.content_digest}, computed {actual_digest}",
            agent_skill_id=metadata.agent_skill_id,
        )

    return _LoadedAgentSkillPackage(
        metadata=metadata,
        root=root,
        package_dir=package_dir,
        metadata_path=metadata_path,
        document_path=document_path,
        projection_paths=MappingProxyType(projection_paths),
    )


def _validate_inheritance(packages: Mapping[str, _LoadedAgentSkillPackage]) -> None:
    for agent_skill_id, package in packages.items():
        for parent_id in package.metadata.extends:
            if parent_id not in packages:
                _raise(
                    "unknown_parent_skill",
                    package.metadata_path,
                    f"extends unknown Agent Skill {parent_id!r}",
                    agent_skill_id=agent_skill_id,
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(agent_skill_id: str, chain: tuple[str, ...]) -> None:
        if agent_skill_id in visited:
            return
        if agent_skill_id in visiting:
            cycle = " -> ".join((*chain, agent_skill_id))
            package = packages[agent_skill_id]
            _raise(
                "inheritance_cycle",
                package.metadata_path,
                f"Agent Skill inheritance contains a cycle: {cycle}",
                agent_skill_id=agent_skill_id,
            )
        visiting.add(agent_skill_id)
        for parent_id in packages[agent_skill_id].metadata.extends:
            visit(parent_id, (*chain, agent_skill_id))
        visiting.remove(agent_skill_id)
        visited.add(agent_skill_id)

    for agent_skill_id in sorted(packages):
        visit(agent_skill_id, ())


def _read_markdown(path: Path, *, package: _LoadedAgentSkillPackage) -> str:
    _assert_regular_file_within(
        path,
        package_dir=package.package_dir,
        root=package.root,
    )
    if path.stat().st_size > _MAX_MARKDOWN_BYTES:
        _raise(
            "content_too_large",
            path,
            f"Markdown content exceeds {_MAX_MARKDOWN_BYTES} bytes",
            agent_skill_id=package.metadata.agent_skill_id,
        )
    actual_digest = compute_agent_skill_content_digest(package.package_dir)
    if actual_digest != package.metadata.content_digest:
        _raise(
            "content_digest_mismatch",
            package.package_dir,
            "package content changed after registry load",
            agent_skill_id=package.metadata.agent_skill_id,
        )
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        _raise(
            "content_missing",
            path,
            f"cannot read UTF-8 Markdown content: {exc}",
            agent_skill_id=package.metadata.agent_skill_id,
        )
    if not content:
        _raise(
            "content_missing",
            path,
            "Markdown content must not be empty",
            agent_skill_id=package.metadata.agent_skill_id,
        )
    return content


def _content_sha256(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


class AgentSkillRegistry:
    """Immutable index with explicit, lazy, digest-checked content reads."""

    def __init__(self, packages: Mapping[str, _LoadedAgentSkillPackage]) -> None:
        self._packages = MappingProxyType(dict(packages))

    def __len__(self) -> int:
        return len(self._packages)

    def list_summaries(self) -> tuple[AgentSkillSummary, ...]:
        return tuple(self._packages[key].summary for key in sorted(self._packages))

    def get_metadata(self, agent_skill_id: str) -> AgentSkillMetadata:
        try:
            return self._packages[agent_skill_id].metadata
        except KeyError as exc:
            raise KeyError(f"unknown Agent Skill {agent_skill_id!r}") from exc

    def load_projection(
        self,
        agent_skill_id: str,
        projection: AgentSkillProjectionName,
    ) -> AgentSkillProjection:
        try:
            package = self._packages[agent_skill_id]
        except KeyError as exc:
            raise KeyError(f"unknown Agent Skill {agent_skill_id!r}") from exc
        try:
            path = package.projection_paths[projection]
        except KeyError as exc:
            raise KeyError(
                f"Agent Skill {agent_skill_id!r} has no projection {projection!r}"
            ) from exc
        content = _read_markdown(path, package=package)
        return AgentSkillProjection(
            agent_skill_id=agent_skill_id,
            version=package.metadata.version,
            projection=projection,
            content=content,
            content_digest=package.metadata.content_digest,
            projection_digest=_content_sha256(content),
            source=str(path),
        )

    def load_document(self, agent_skill_id: str) -> AgentSkillDocument:
        try:
            package = self._packages[agent_skill_id]
        except KeyError as exc:
            raise KeyError(f"unknown Agent Skill {agent_skill_id!r}") from exc
        content = _read_markdown(package.document_path, package=package)
        return AgentSkillDocument(
            agent_skill_id=agent_skill_id,
            version=package.metadata.version,
            content=content,
            content_digest=package.metadata.content_digest,
            document_digest=_content_sha256(content),
            source=str(package.document_path),
        )

    def snapshot(
        self,
        *,
        roots: tuple[str, ...] | None = None,
        package_files: tuple[str, ...] | None = None,
    ) -> AgentSkillRegistrySnapshot:
        return AgentSkillRegistrySnapshot(
            roots=roots or (),
            package_files=package_files or (),
            summaries=self.list_summaries(),
        )


def load_agent_skill_registry(roots: Iterable[str | Path]) -> ConfiguredAgentSkillRegistry:
    packages: dict[str, _LoadedAgentSkillPackage] = {}
    configured_roots: list[str] = []
    package_files: list[str] = []

    for raw_root in roots:
        root = Path(raw_root).expanduser()
        if not root.exists():
            _raise("root_not_found", root, "configured Agent Skill root does not exist")
        if root.is_symlink():
            _raise("unsafe_path", root, "symlinked Agent Skill roots are not allowed")
        if not root.is_dir():
            _raise("root_not_directory", root, "configured Agent Skill root is not a directory")
        root = root.resolve(strict=True)
        configured_roots.append(str(root))

        for candidate in sorted(root.iterdir(), key=lambda item: item.name):
            if candidate.is_symlink():
                _raise("unsafe_path", candidate, "symlinks are not allowed in Agent Skill roots")
            if not candidate.is_dir():
                continue
            metadata_path = candidate / _METADATA_NAME
            if not metadata_path.exists():
                continue
            package = _load_package(candidate, root=root)
            agent_skill_id = package.metadata.agent_skill_id
            if agent_skill_id in packages:
                _raise(
                    "duplicate_agent_skill_id",
                    package.metadata_path,
                    f"Agent Skill ID {agent_skill_id!r} is already loaded from "
                    f"{packages[agent_skill_id].metadata_path}",
                    agent_skill_id=agent_skill_id,
                )
            packages[agent_skill_id] = package
            package_files.append(str(package.metadata_path))

    _validate_inheritance(packages)
    return ConfiguredAgentSkillRegistry(
        registry=AgentSkillRegistry(packages),
        roots=tuple(configured_roots),
        package_files=tuple(package_files),
    )


def build_configured_agent_skill_registry(raw_roots: str | None) -> ConfiguredAgentSkillRegistry:
    return load_agent_skill_registry(parse_agent_skill_roots(raw_roots))
