"""Fail-closed local verification evidence for the B4/B5 implementation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOCAL_VERIFICATION_MANIFEST = Path("docs/evidence/t5-3-local-verification.json")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REQUIRED_FILES = (
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("scripts/18_large_llm_baselines.py"),
    Path("scripts/generate_b45_local_verification.py"),
    Path("scripts/large_llm_baselines_workflow.py"),
)
_BASE_CHECK_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("full_pytest", ("uv", "run", "python", "-m", "pytest", "-q")),
    ("ruff_check", ("uv", "run", "ruff", "check", ".")),
    ("ruff_format", ("uv", "run", "ruff", "format", "--check", ".")),
    (
        "cli_help",
        ("uv", "run", "python", "scripts/18_large_llm_baselines.py", "--help"),
    ),
    (
        "offline_validate",
        (
            "uv",
            "run",
            "python",
            "scripts/18_large_llm_baselines.py",
            "validate",
            "--baseline",
            "b4",
            "--provider",
            "deepinfra",
            "--max-cost-usd",
            "20",
        ),
    ),
)


@dataclass(frozen=True)
class LocalVerificationEvidence:
    """Validated status of the canonical local-verification manifest."""

    ready: bool
    blockers: tuple[str, ...]
    manifest_sha256: str | None = None
    source_sha256: str | None = None


class LocalVerificationGenerationError(RuntimeError):
    """Raised when a required local verification command does not pass."""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verification_source_records(project_root: Path) -> tuple[dict[str, str], ...]:
    """Return deterministic content identities for every local-gate input."""
    root = project_root.resolve()
    candidates = {
        *(root / "src/nl2sparql/models/b45").glob("*.py"),
        *(root / "tests/unit").glob("test_b45_*.py"),
        *(root / "tests/fixtures/b45").glob("**/*"),
        *(root / relative for relative in _REQUIRED_FILES),
    }
    missing = [
        relative.as_posix() for relative in _REQUIRED_FILES if not (root / relative).is_file()
    ]
    b45_sources = [
        path for path in candidates if path.is_file() and "models/b45" in path.as_posix()
    ]
    b45_tests = [path for path in candidates if path.is_file() and "test_b45_" in path.name]
    if missing or not b45_sources or not b45_tests:
        raise ValueError("local verification source set is incomplete")
    return tuple(
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path.read_bytes()),
        }
        for path in sorted((path for path in candidates if path.is_file()), key=str)
    )


def expected_verification_commands(project_root: Path) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the exact commands accepted by the canonical manifest schema."""
    root = project_root.resolve()
    focused_tests = tuple(
        path.relative_to(root).as_posix()
        for path in sorted((root / "tests/unit").glob("test_b45_*.py"), key=str)
    )
    focused = (
        "focused_pytest",
        ("uv", "run", "python", "-m", "pytest", *focused_tests, "-q"),
    )
    return (focused, *_BASE_CHECK_COMMANDS)


def _run_command(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _pytest_counts(output: str) -> tuple[int, int]:
    passed = re.search(r"(?:^|\s)(\d+) passed(?:,|\s)", output)
    skipped = re.search(r"(?:^|\s)(\d+) skipped(?:,|\s)", output)
    if passed is None:
        raise LocalVerificationGenerationError("pytest output did not contain a passing count")
    return int(passed.group(1)), int(skipped.group(1)) if skipped is not None else 0


def generate_local_verification_manifest(
    *,
    project_root: Path | None = None,
) -> LocalVerificationEvidence:
    """Run every accepted check and atomically publish canonical local evidence."""
    root = (project_root or _project_root()).resolve()
    checks: list[dict[str, object]] = []
    for check_id, command in expected_verification_commands(root):
        result = _run_command(command, root)
        if type(result.returncode) is not int or result.returncode != 0:
            raise LocalVerificationGenerationError(f"local verification check failed: {check_id}")
        stdout = result.stdout if isinstance(result.stdout, str) else ""
        stderr = result.stderr if isinstance(result.stderr, str) else ""
        check: dict[str, object] = {
            "check_id": check_id,
            "command": list(command),
            "exit_code": result.returncode,
            "stdout_sha256": _sha256(stdout.encode("utf-8")),
            "stderr_sha256": _sha256(stderr.encode("utf-8")),
        }
        if check_id.endswith("pytest"):
            passed, skipped = _pytest_counts(f"{stdout}\n{stderr}")
            if skipped:
                raise LocalVerificationGenerationError(
                    f"local verification check skipped tests: {check_id}"
                )
            check.update({"passed_tests": passed, "skipped_tests": skipped})
        checks.append(check)
    sources = list(verification_source_records(root))
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    body: dict[str, object] = {
        "schema_version": 1,
        "verified_at_utc": timestamp,
        "source_files": sources,
        "source_sha256": _sha256(_canonical_json(sources)),
        "checks": checks,
    }
    body["manifest_sha256"] = _sha256(_canonical_json(body))
    manifest_path = root / LOCAL_VERIFICATION_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=manifest_path.parent, delete=False) as handle:
        temporary_path = Path(handle.name)
        handle.write(_canonical_json(body))
        handle.flush()
    try:
        temporary_path.replace(manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    evidence = load_local_verification_evidence(project_root=root)
    if not evidence.ready:
        raise LocalVerificationGenerationError("generated local verification manifest is invalid")
    return evidence


def _valid_check(raw: object, expected_id: str, expected_command: tuple[str, ...]) -> bool:
    if not isinstance(raw, dict):
        return False
    pytest_check = expected_id.endswith("pytest")
    expected_keys = {
        "check_id",
        "command",
        "exit_code",
        "stdout_sha256",
        "stderr_sha256",
    }
    if pytest_check:
        expected_keys.update({"passed_tests", "skipped_tests"})
    if set(raw) != expected_keys:
        return False
    if raw["check_id"] != expected_id or raw["command"] != list(expected_command):
        return False
    if type(raw["exit_code"]) is not int or raw["exit_code"] != 0:
        return False
    if any(
        not isinstance(raw[field], str) or _SHA256_RE.fullmatch(raw[field]) is None
        for field in ("stdout_sha256", "stderr_sha256")
    ):
        return False
    if pytest_check and (
        type(raw["passed_tests"]) is not int
        or raw["passed_tests"] <= 0
        or type(raw["skipped_tests"]) is not int
        or raw["skipped_tests"] != 0
    ):
        return False
    return True


def _valid_source_records(raw: object) -> bool:
    if not isinstance(raw, list) or not raw:
        return False
    paths: list[str] = []
    for record in raw:
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            return False
        path = record["path"]
        digest = record["sha256"]
        if (
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or not isinstance(digest, str)
            or _SHA256_RE.fullmatch(digest) is None
        ):
            return False
        paths.append(path)
    return paths == sorted(paths) and len(paths) == len(set(paths))


def _load_manifest(path: Path, project_root: Path) -> tuple[dict[str, Any] | None, str]:
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "local_verification_manifest_invalid"
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "verified_at_utc",
        "source_files",
        "source_sha256",
        "checks",
        "manifest_sha256",
    }:
        return None, "local_verification_manifest_invalid"
    if raw_bytes != _canonical_json(payload):
        return None, "local_verification_manifest_invalid"
    manifest_sha256 = payload["manifest_sha256"]
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if (
        payload["schema_version"] != 1
        or not isinstance(payload["verified_at_utc"], str)
        or _UTC_RE.fullmatch(payload["verified_at_utc"]) is None
        or not isinstance(manifest_sha256, str)
        or manifest_sha256 != _sha256(_canonical_json(body))
        or not _valid_source_records(payload["source_files"])
        or not isinstance(payload["source_sha256"], str)
        or payload["source_sha256"] != _sha256(_canonical_json(payload["source_files"]))
    ):
        return None, "local_verification_manifest_invalid"
    commands = expected_verification_commands(project_root)
    checks = payload["checks"]
    if (
        not isinstance(checks, list)
        or len(checks) != len(commands)
        or any(
            not _valid_check(check, check_id, command)
            for check, (check_id, command) in zip(checks, commands, strict=True)
        )
    ):
        return None, "local_verification_manifest_invalid"
    return payload, ""


def load_local_verification_evidence(
    *, project_root: Path | None = None
) -> LocalVerificationEvidence:
    """Load and validate canonical local evidence without trusting a caller boolean."""
    root = (project_root or _project_root()).resolve()
    manifest_path = root / LOCAL_VERIFICATION_MANIFEST
    if not manifest_path.is_file():
        return LocalVerificationEvidence(
            ready=False,
            blockers=("local_verification_manifest_missing",),
        )
    try:
        payload, blocker = _load_manifest(manifest_path, root)
    except OSError:
        payload, blocker = None, "local_verification_manifest_invalid"
    if payload is None:
        return LocalVerificationEvidence(ready=False, blockers=(blocker,))
    try:
        current_sources = verification_source_records(root)
    except (OSError, ValueError):
        current_sources = ()
    if list(current_sources) != payload["source_files"]:
        return LocalVerificationEvidence(
            ready=False,
            blockers=("local_verification_source_stale",),
            manifest_sha256=_sha256(manifest_path.read_bytes()),
            source_sha256=payload["source_sha256"],
        )
    return LocalVerificationEvidence(
        ready=True,
        blockers=(),
        manifest_sha256=_sha256(manifest_path.read_bytes()),
        source_sha256=payload["source_sha256"],
    )
