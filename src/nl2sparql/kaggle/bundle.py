"""Allowlisted, reproducible transport for existing code and accepted inputs."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

MANIFEST = "kaggle-bundle.json"
INPUTS = "configs/kaggle-b12-inputs.json"
TRAINING = "data/dataset/processed/b2-training.jsonl"
TRAINING_SHA256 = "b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835"
ENGLISH = "data/dataset/test/test-100.jsonl"
VIETNAMESE = "data/dataset/test/test-100-vi.jsonl"
MAX_BYTES = 128 * 1024 * 1024


class PreparationError(ValueError):
    """A preparation or runtime prerequisite is not satisfied."""


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or str(path) != name
        or path.is_absolute()
        or any(p in {"..", "."} for p in name.split("/"))
    ):
        raise PreparationError(f"unsafe bundle path: {name}")
    if any(p.startswith(".") or p == "__pycache__" for p in path.parts):
        raise PreparationError(f"unapproved bundle path: {name}")
    return path


def read_file(root: Path, name: str) -> bytes:
    path = root / relative(name)
    try:
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise PreparationError(f"bundle symlink is forbidden: {name}")
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise PreparationError(f"unsafe bundle file: {name}")
        return path.read_bytes()
    except OSError as exc:
        raise PreparationError(f"missing/unreadable bundle file: {name}") from exc


def write_new(path: Path, payload: bytes) -> None:
    """Immutable publication; identical bytes are resumable."""
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise PreparationError(f"unsafe output: {path}")
        if path.read_bytes() != payload:
            raise PreparationError(f"refusing to replace existing output: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def build_bundle(root: Path, output: Path) -> dict:
    root = root.resolve()
    for name in ("src", "data", "scripts", "configs", "docs", "notebooks"):
        if output.resolve().is_relative_to(root / name):
            raise PreparationError("bundle output must not modify source inputs")
    spec = json.loads(read_file(root, INPUTS))
    names = set(spec["code_paths"]) | set(spec["inputs"]) | {INPUTS}
    payloads = {}
    files = {}
    for name in sorted(names):
        relative(name)
        if name not in spec["inputs"] and name != INPUTS:
            approved = (
                name.startswith("src/nl2sparql/")
                and Path(name).suffix in {".py", ".json", ".sql", ".yaml", ".yml"}
            ) or name in spec["support_paths"]
            if not approved:
                raise PreparationError(f"not in code allowlist: {name}")
        payload = read_file(root, name)
        expected = spec["inputs"].get(name)
        if expected and sha256(payload) != expected["sha256"]:
            raise PreparationError(f"accepted input fingerprint mismatch: {name}")
        payloads[name] = payload
        files[name] = {
            "sha256": sha256(payload),
            "bytes": len(payload),
            "role": expected["role"] if expected else "source",
        }
    manifest = {
        "schema_version": 1,
        "execution_languages": ["en", "vi"],
        "vietnamese_execution": "typed_paired_finalized_consumer",
        "training_sha256": TRAINING_SHA256,
        "files": files,
        "content_sha256": sha256(canonical(files)),
    }
    payloads[MANIFEST] = canonical(manifest)
    raw_tar = io.BytesIO()
    with tarfile.open(fileobj=raw_tar, mode="w", format=tarfile.USTAR_FORMAT) as handle:
        for name, payload in sorted(payloads.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(payload), 0o644, 0
            handle.addfile(entry, io.BytesIO(payload))
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as handle:
        handle.write(raw_tar.getvalue())
    write_new(output, buffer.getvalue())
    return manifest


def verify_bundle(root: Path) -> dict:
    root = root.resolve()
    try:
        manifest = json.loads(read_file(root, MANIFEST))
        files = manifest["files"]
        if manifest["schema_version"] != 1 or manifest["content_sha256"] != sha256(
            canonical(files)
        ):
            raise PreparationError("bundle manifest identity mismatch")
        if (
            manifest["execution_languages"] != ["en", "vi"]
            or manifest["training_sha256"] != TRAINING_SHA256
        ):
            raise PreparationError("bundle research contract mismatch")
        for name, evidence in files.items():
            payload = read_file(root, name)
            if len(payload) != evidence["bytes"] or sha256(payload) != evidence["sha256"]:
                raise PreparationError(f"bundle fingerprint mismatch: {name}")
        actual = {
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_symlink() or not p.is_dir()
        }
        if actual != set(files) | {MANIFEST}:
            raise PreparationError("unexpected or missing bundle files")
        spec = json.loads(read_file(root, INPUTS))
        expected = set(spec["code_paths"]) | set(spec["inputs"]) | {INPUTS}
        if set(files) != expected:
            raise PreparationError("bundle does not match explicit allowlist")
        for name, evidence in spec["inputs"].items():
            if files[name]["sha256"] != evidence["sha256"]:
                raise PreparationError(f"accepted input binding mismatch: {name}")
        return manifest
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PreparationError(f"invalid bundle: {exc}") from exc


def extract_bundle(archive: Path, destination: Path, expected_sha256: str) -> None:
    if sha256(archive.read_bytes()) != expected_sha256:
        raise PreparationError("archive SHA-256 mismatch")
    if destination.exists() or destination.is_symlink():
        raise PreparationError("extraction destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(dir=destination.parent, prefix=".kaggle-extract-"))
    try:
        with tarfile.open(archive) as handle:
            members = handle.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)) or sum(m.size for m in members) > MAX_BYTES:
                raise PreparationError("archive duplicate paths or size limit exceeded")
            for member in members:
                relative(member.name)
                if not member.isfile():
                    raise PreparationError("archive may contain only regular files")
                stream = handle.extractfile(member)
                if stream is None:
                    raise PreparationError("archive member unreadable")
                path = temporary / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(stream.read())
        verify_bundle(temporary)
        temporary.rename(destination)
    except tarfile.TarError as exc:
        raise PreparationError(f"invalid archive: {exc}") from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def preflight_data(root: Path) -> dict:
    """Validate the actual consumer boundaries, without model/encoder/cache loading."""
    root = root.resolve()
    verify_bundle(root)
    from nl2sparql.models.b12.catalog_summary import compile_catalog_summary
    from nl2sparql.models.b12.evaluate import load_evaluation_cases
    from nl2sparql.models.b12.retrieval import validate_training_snapshot

    records, digest = validate_training_snapshot(
        read_file(root, TRAINING), accepted_training_sha256=TRAINING_SHA256
    )
    english = load_evaluation_cases(root / ENGLISH)
    summary = compile_catalog_summary(root / "src/nl2sparql/sql/catalog/ethereum_analytics.json")
    vi = load_evaluation_cases(root / VIETNAMESE, language="vi", source_root=root)
    return {
        "status": "data_ready",
        "training_records": len(records),
        "training_sha256": digest,
        "english_records": len(english),
        "vietnamese_records": len(vi),
        "catalog_sha256": summary.catalog_sha256,
        "summary_sha256": summary.summary_sha256,
        "execution_languages": ["en", "vi"],
        "vietnamese_execution": "typed_paired_finalized_consumer",
        "scientific_ready": False,
    }
