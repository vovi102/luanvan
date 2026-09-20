"""Behavior tests for canonical B4/B5 local-verification evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import nl2sparql.models.b45.local_verification as local_verification
import scripts.generate_b45_local_verification as verification_generator
from nl2sparql.models.b45.local_verification import load_local_verification_evidence


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _write_minimal_project(root: Path) -> None:
    files = {
        ".python-version": "3.11\n",
        "pyproject.toml": "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        "uv.lock": "version = 1\n",
        "src/nl2sparql/models/b45/contracts.py": "MODEL_ID = 'model'\n",
        "src/nl2sparql/models/b45/local_verification.py": "def verify():\n    return True\n",
        "src/nl2sparql/models/b4_zero_shot.py": "from .b45 import BaselineB4\n",
        "src/nl2sparql/models/b5_few_shot.py": "from .b45 import BaselineB5\n",
        "scripts/18_large_llm_baselines.py": "print('wrapper')\n",
        "scripts/generate_b45_local_verification.py": "print('generator')\n",
        "scripts/large_llm_baselines_workflow.py": "print('workflow')\n",
        "tests/fixtures/b45/journal.jsonl": "{}\n",
        "tests/unit/test_b45_contracts.py": "def test_contract():\n    assert True\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _source_records(root: Path) -> list[dict[str, str]]:
    candidates = {
        *root.glob("src/nl2sparql/models/b45/*.py"),
        *root.glob("tests/unit/test_b45_*.py"),
        *root.glob("tests/fixtures/b45/**/*"),
        root / ".python-version",
        root / "pyproject.toml",
        root / "uv.lock",
        root / "scripts/18_large_llm_baselines.py",
        root / "scripts/generate_b45_local_verification.py",
        root / "scripts/large_llm_baselines_workflow.py",
        root / "src/nl2sparql/models/b4_zero_shot.py",
        root / "src/nl2sparql/models/b5_few_shot.py",
    }
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted((path for path in candidates if path.is_file()), key=str)
    ]


def _checks(root: Path) -> list[dict[str, object]]:
    focused_tests = sorted(
        path.relative_to(root).as_posix() for path in root.glob("tests/unit/test_b45_*.py")
    )
    commands = (
        ("focused_pytest", ["uv", "run", "python", "-m", "pytest", *focused_tests, "-q"]),
        ("full_pytest", ["uv", "run", "python", "-m", "pytest", "-q"]),
        ("ruff_check", ["uv", "run", "ruff", "check", "."]),
        ("ruff_format", ["uv", "run", "ruff", "format", "--check", "."]),
        ("cli_help", ["uv", "run", "python", "scripts/18_large_llm_baselines.py", "--help"]),
        (
            "offline_validate",
            [
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
            ],
        ),
    )
    empty_sha = hashlib.sha256(b"").hexdigest()
    checks: list[dict[str, object]] = []
    for check_id, command in commands:
        check: dict[str, object] = {
            "check_id": check_id,
            "command": command,
            "exit_code": 0,
            "stdout_sha256": empty_sha,
            "stderr_sha256": empty_sha,
        }
        if check_id.endswith("pytest"):
            check.update({"passed_tests": 1, "skipped_tests": 0})
        checks.append(check)
    return checks


def _write_valid_manifest(root: Path) -> Path:
    sources = _source_records(root)
    body: dict[str, object] = {
        "schema_version": 1,
        "verified_at_utc": "2026-09-13T03:00:00Z",
        "source_files": sources,
        "source_sha256": hashlib.sha256(_canonical(sources)).hexdigest(),
        "checks": _checks(root),
    }
    body["manifest_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    path = root / "docs/evidence/t5-3-local-verification.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(_canonical(body))
    return path


def test_valid_canonical_manifest_confers_local_readiness(tmp_path: Path) -> None:
    """Rejecting valid, complete command and source evidence would fail this test."""
    _write_minimal_project(tmp_path)
    manifest_path = _write_valid_manifest(tmp_path)

    evidence = load_local_verification_evidence(project_root=tmp_path)

    assert evidence.ready is True
    assert evidence.blockers == ()
    assert evidence.manifest_sha256 == hashlib.sha256(manifest_path.read_bytes()).hexdigest()


@pytest.mark.parametrize("second_read", ["replacement", "disappearance"])
def test_manifest_evidence_uses_the_single_validated_snapshot(
    second_read: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path race cannot change the digest or crash after manifest validation."""
    _write_minimal_project(tmp_path)
    manifest_path = _write_valid_manifest(tmp_path)
    accepted = manifest_path.read_bytes()
    original_read_bytes = Path.read_bytes
    manifest_reads = 0

    def raced_read_bytes(path: Path) -> bytes:
        nonlocal manifest_reads
        if path == manifest_path:
            manifest_reads += 1
            if manifest_reads > 1:
                if second_read == "disappearance":
                    raise FileNotFoundError(manifest_path)
                return b'{"unvalidated":"replacement"}\n'
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", raced_read_bytes)

    evidence = load_local_verification_evidence(project_root=tmp_path)

    assert evidence.ready is True
    assert evidence.manifest_sha256 == hashlib.sha256(accepted).hexdigest()
    assert manifest_reads == 1


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    """Defaulting readiness to true when evidence is absent would fail this test."""
    _write_minimal_project(tmp_path)

    evidence = load_local_verification_evidence(project_root=tmp_path)

    assert evidence.ready is False
    assert evidence.blockers == ("local_verification_manifest_missing",)


def test_tampered_manifest_fails_closed(tmp_path: Path) -> None:
    """Trusting edited check claims without the canonical self-hash would fail this test."""
    _write_minimal_project(tmp_path)
    manifest_path = _write_valid_manifest(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["checks"][0]["passed_tests"] = 999
    manifest_path.write_bytes(_canonical(payload))

    evidence = load_local_verification_evidence(project_root=tmp_path)

    assert evidence.ready is False
    assert evidence.blockers == ("local_verification_manifest_invalid",)


def test_source_change_makes_manifest_stale(tmp_path: Path) -> None:
    """Accepting verification after bound implementation bytes change would fail this test."""
    _write_minimal_project(tmp_path)
    _write_valid_manifest(tmp_path)
    source = tmp_path / "src/nl2sparql/models/b45/contracts.py"
    source.write_text("MODEL_ID = 'changed-model'\n", encoding="utf-8")

    evidence = load_local_verification_evidence(project_root=tmp_path)

    assert evidence.ready is False
    assert evidence.blockers == ("local_verification_source_stale",)


@pytest.mark.parametrize("module_name", ["b4_zero_shot.py", "b5_few_shot.py"])
def test_compatibility_module_change_makes_manifest_stale(module_name: str, tmp_path: Path) -> None:
    """Leaving a task compatibility export outside the source digest would fail this test."""
    _write_minimal_project(tmp_path)
    _write_valid_manifest(tmp_path)
    assert load_local_verification_evidence(project_root=tmp_path).ready is True
    module = tmp_path / "src/nl2sparql/models" / module_name
    module.write_text("raise RuntimeError('changed compatibility module')\n", encoding="utf-8")

    evidence = load_local_verification_evidence(project_root=tmp_path)

    assert evidence.ready is False
    assert evidence.blockers == ("local_verification_source_stale",)


def test_generator_runs_exact_checks_and_writes_loadable_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping a required command or emitting unchecked claims would fail this test."""
    _write_minimal_project(tmp_path)
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd == tmp_path
        calls.append(command)
        stdout = "1 passed in 0.01s\n" if command[4:5] == ("pytest",) else "ok\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(local_verification, "_run_command", runner)

    evidence = local_verification.generate_local_verification_manifest(project_root=tmp_path)

    assert evidence.ready is True
    assert calls == [command for _check_id, command in _checks_as_tuples(tmp_path)]
    assert load_local_verification_evidence(project_root=tmp_path).ready is True


def _checks_as_tuples(root: Path) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((str(check["check_id"]), tuple(check["command"])) for check in _checks(root))


def test_generator_does_not_publish_failed_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writing a manifest after a failed command would fail this test."""
    _write_minimal_project(tmp_path)

    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="failed\n", stderr="")

    monkeypatch.setattr(local_verification, "_run_command", runner)

    with pytest.raises(local_verification.LocalVerificationGenerationError):
        local_verification.generate_local_verification_manifest(project_root=tmp_path)

    assert not (tmp_path / "docs/evidence/t5-3-local-verification.json").exists()


def test_generator_preserves_manifest_when_source_changes_during_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publishing evidence for a source set not tested by every check would fail this test."""
    _write_minimal_project(tmp_path)
    manifest_path = _write_valid_manifest(tmp_path)
    original_manifest = manifest_path.read_bytes()
    source = tmp_path / "src/nl2sparql/models/b45/contracts.py"
    changed = False

    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        nonlocal changed
        if not changed:
            source.write_text("MODEL_ID = 'changed-during-verification'\n", encoding="utf-8")
            changed = True
        stdout = "1 passed in 0.01s\n" if command[4:5] == ("pytest",) else "ok\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(local_verification, "_run_command", runner)

    with pytest.raises(
        local_verification.LocalVerificationGenerationError,
        match="^local verification source changed during checks$",
    ):
        local_verification.generate_local_verification_manifest(project_root=tmp_path)

    assert manifest_path.read_bytes() == original_manifest


def test_generator_cli_documents_canonical_output() -> None:
    """Removing the operator-facing generator entry point would fail this test."""
    result = subprocess.run(
        [sys.executable, "scripts/generate_b45_local_verification.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "docs/evidence/t5-3-local-verification.json" in result.stdout


def test_generator_emits_through_click_output_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """The generator must share the CLI-safe output seam instead of raw print."""
    emitted: list[str] = []
    evidence = type(
        "Evidence",
        (),
        {"manifest_sha256": "a" * 64, "source_sha256": "b" * 64},
    )()
    monkeypatch.setattr(
        verification_generator,
        "generate_local_verification_manifest",
        lambda: evidence,
    )
    monkeypatch.setattr(verification_generator.click, "echo", emitted.append)

    assert verification_generator.main([]) == 0
    assert json.loads(emitted[0])["status"] == "ready"
