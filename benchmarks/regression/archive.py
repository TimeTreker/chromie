from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from typing import Any, Iterator, Mapping

from benchmarks.contracts import ContractError


def restore_frozen_corpus(corpus: Path, *, repo_root: Path, fetch: bool = False) -> dict[str, Any]:
    """Restore immutable test inputs, never regenerate answers from current code.

    Present files must already match the freeze. Missing files are staged and
    verified before publication; a shallow checkout fetches only when requested.
    """
    manifest = load_json(corpus / "manifest.json")
    source = manifest.get("storage") or {}
    revision, source_path = source.get("git_revision", ""), source.get("git_path", "")
    if (not re.fullmatch(r"[a-f0-9]{40}", revision) or not source_path
            or Path(source_path).is_absolute() or ".." in Path(source_path).parts
            or Path(source_path).as_posix() != source_path
            or not re.fullmatch(r"[a-f0-9]{64}", source.get("manifest_sha256", ""))):
        raise ContractError("invalid frozen corpus source identity")
    expected = {**manifest["case_sha256"], **{
        f"artifacts/{name}": digest for name, digest in manifest["artifact_sha256"].items()
    }}
    if not expected or len(manifest["case_sha256"]) != manifest.get("count"):
        raise ContractError("frozen corpus count does not match the manifest")
    for name, digest in expected.items():
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or path.as_posix() != name
                or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            raise ContractError(f"invalid frozen corpus entry: {name}")
    actual = {str(p.relative_to(corpus)) for p in corpus.glob("workflow-*.json")}
    actual.update(str(p.relative_to(corpus)) for p in (corpus / "artifacts").glob("*.json"))
    if actual - expected.keys():
        raise ContractError("unexpected frozen corpus files; review the manifest explicitly")
    missing = set()
    for name, digest in expected.items():
        path = corpus / name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ContractError(f"frozen corpus path contains a link: {name}")
        if not path.exists():
            missing.add(name)
        elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ContractError(f"frozen corpus hash mismatch: {name}; refusing to overwrite")
    if not missing:
        return {"verified": len(expected), "restored": 0}
    git = ["git", "-C", str(repo_root)]
    available = subprocess.run(git + ["cat-file", "-e", f"{revision}^{{commit}}"], capture_output=True)
    if available.returncode and not fetch:
        raise ContractError(
            f"frozen corpus revision {revision} is unavailable; run "
            "python -m benchmarks.regression restore-fixtures --fetch once in this checkout"
        )
    try:
        if available.returncode:
            subprocess.run(git + ["fetch", "--no-tags", "--depth=1", "origin", revision],
                           check=True, capture_output=True, timeout=300)
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=corpus) as temp:
            stage = Path(temp)
            archive_path = stage / "corpus.tar"
            with archive_path.open("wb") as output:
                subprocess.run(git + ["archive", f"{revision}:{source_path}"], stdout=output,
                               stderr=subprocess.PIPE, check=True, timeout=120)
            archive_expected = {**expected, "manifest.json": source["manifest_sha256"]}
            seen = set()
            with tarfile.open(archive_path) as archive:
                for member in archive:
                    if member.isdir():
                        continue
                    if not member.isfile() or member.name not in archive_expected or member.name in seen:
                        raise ContractError(f"unexpected frozen archive entry: {member.name}")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ContractError(f"missing frozen archive content: {member.name}")
                    raw = stream.read()
                    if hashlib.sha256(raw).hexdigest() != archive_expected[member.name]:
                        raise ContractError(f"frozen archive hash mismatch: {member.name}")
                    seen.add(member.name)
                    if member.name in missing:
                        target = stage / "files" / member.name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(raw)
            if seen != archive_expected.keys():
                raise ContractError("frozen archive is incomplete")
            for name in sorted(missing):
                target = corpus / name
                target.parent.mkdir(parents=True, exist_ok=True)
                (stage / "files" / name).replace(target)
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
        raise ContractError(f"cannot restore frozen corpus: {exc}") from exc
    return {"verified": len(expected), "restored": len(missing), "git_revision": revision}


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
