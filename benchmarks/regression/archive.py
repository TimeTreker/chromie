from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
from typing import Any, Iterator, Mapping

from benchmarks.contracts import ContractError


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return payload


def _safe_members(archive: tarfile.TarFile, destination: Path) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    destination = destination.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise ContractError(f"archive contains unsupported link: {member.name}")
        target = (destination / member.name).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise ContractError(f"archive path escapes destination: {member.name}") from exc
        members.append(member)
    return members


@contextmanager
def materialize_source(source: Path) -> Iterator[Path]:
    source = source.resolve()
    if source.is_dir():
        yield source
        return
    if not source.is_file():
        raise ContractError(f"qualification source does not exist: {source}")
    try:
        with tempfile.TemporaryDirectory(prefix="chromie-regression-") as temp:
            root = Path(temp)
            with tarfile.open(source, "r:*") as archive:
                archive.extractall(root, members=_safe_members(archive, root), filter="data")
            yield root
    except (tarfile.TarError, OSError) as exc:
        raise ContractError(f"cannot open qualification archive {source}: {exc}") from exc


def find_single(root: Path, name: str, *, required: bool = True) -> Path | None:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if not matches:
        if required:
            raise ContractError(f"{root}: missing {name}")
        return None
    if len(matches) > 1:
        exact = [path for path in matches if path.parent == root]
        if len(exact) == 1:
            return exact[0]
        raise ContractError(
            f"{root}: expected one {name}, found {len(matches)}"
        )
    return matches[0]


def qualification_root(root: Path) -> Path:
    report = find_single(root, "collection-report.json")
    assert report is not None
    return report.parent


def verify_artifact_index(root: Path) -> dict[str, Any]:
    index_path = root / "artifact-index.json"
    if not index_path.is_file():
        return {"status": "missing", "verified": 0, "errors": []}
    payload = load_json(index_path)
    artifacts = payload.get("artifacts")
    if payload.get("schema_version") != 1 or not isinstance(artifacts, list):
        raise ContractError(f"{index_path}: invalid artifact index")
    errors: list[str] = []
    verified = 0
    for item in artifacts:
        if not isinstance(item, Mapping):
            errors.append("artifact record is not an object")
            continue
        relative = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            errors.append("artifact record is missing path or sha256")
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            errors.append(f"artifact path escapes root: {relative}")
            continue
        if not path.is_file():
            errors.append(f"artifact missing: {relative}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            errors.append(f"artifact digest mismatch: {relative}")
            continue
        verified += 1
    return {
        "status": "passed" if not errors else "failed",
        "verified": verified,
        "errors": errors,
    }
