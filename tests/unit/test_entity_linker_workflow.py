"""Offline contracts for the production entity-linker workflow."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import stat
import subprocess
import sys
import types
from pathlib import Path

import httpx
import numpy as np
import pytest
from click.testing import CliRunner

from nl2sparql.linking.entity import EntityCorpus, EntityTarget

WORKFLOW_PATH = Path(__file__).parents[2] / "scripts/entity_linker_workflow.py"
WORKFLOW_SPEC = importlib.util.spec_from_file_location("entity_linker_workflow", WORKFLOW_PATH)
assert WORKFLOW_SPEC is not None and WORKFLOW_SPEC.loader is not None
workflow = importlib.util.module_from_spec(WORKFLOW_SPEC)
WORKFLOW_SPEC.loader.exec_module(workflow)


class FakeEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        return np.tile(np.asarray([1.0, 0.0], dtype=np.float32), (len(texts), 1))


def _corpus() -> EntityCorpus:
    document = "Owner: Binance"
    target = EntityTarget(
        target_id="owner:Binance",
        target_kind="owner",
        owner="Binance",
        addresses=(),
        primary_labels=("Binance",),
        aliases=("binance",),
        categories=("exchange",),
        concept_classes=("ExchangeAccount",),
        address_roles=(),
        description="fixture owner",
        document=document,
        document_sha256=hashlib.sha256(document.encode()).hexdigest(),
    )
    return EntityCorpus(
        targets=(target,),
        targets_by_id={target.target_id: target},
        phrase_targets={"binance": (target.target_id,)},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )


def _ground_truth(path: Path) -> Path:
    rows = [
        {
            "id": f"case-{number:03d}",
            "question": f"Binance case {number}",
            "mentions": [{"span": "Binance", "span_offset": [0, 7], "target_id": "owner:Binance"}],
        }
        for number in range(100)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _cli(calls: list[tuple[str, bool]]):
    return workflow.create_cli(
        encoder_loader=lambda model_id, local_files_only: (
            calls.append((model_id, local_files_only)) or FakeEncoder()
        ),
        corpus_builder=lambda artifacts: _corpus(),
        git_provenance_factory=lambda repository: workflow.GitProvenance("1" * 40, True),
    )


def _inputs(tmp_path: Path, calls: list[tuple[str, bool]]):
    cache = tmp_path / "cache"
    ground_truth = _ground_truth(tmp_path / "ground-truth.jsonl")
    report = tmp_path / "report.json"
    cli = _cli(calls)
    built = CliRunner().invoke(cli, ["build-index", "--cache-dir", str(cache)])
    assert built.exit_code == 0, built.output
    calls.clear()
    return cli, cache, ground_truth, report


def _fail_if_called(*args, **kwargs):
    raise AssertionError("the model must not load during CLI preflight")


def _concurrent_report_writer(
    report: str,
    payload: bytes,
    fail_after_replace: bool,
    ready: object,
    release: object,
    results: object,
    attempting: object | None = None,
    entered: object | None = None,
) -> None:
    destination = workflow._open_report_destination(Path(report))
    original_fsync = workflow.os.fsync
    after_replace = False

    def checkpoint(point: str) -> None:
        nonlocal after_replace
        if entered is not None and point == "report_replaced":
            entered.set()
        if fail_after_replace and point == "report_replaced":
            ready.set()
            release.wait(10)
            after_replace = True

    def fail_after_replacement(descriptor: int) -> None:
        if fail_after_replace and after_replace and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("post-replace fsync failure")
        original_fsync(descriptor)

    workflow._report_publication_checkpoint = checkpoint
    workflow.os.fsync = fail_after_replacement
    try:
        if attempting is not None:
            attempting.set()
        workflow._atomic_write(destination, payload)
        results.put("published")
    except workflow.ReportPublicationError:
        results.put("failed")
    finally:
        workflow.os.fsync = original_fsync
        destination.close()


@pytest.mark.parametrize(
    "args",
    (["--help"], ["build-index", "--help"], ["query", "--help"], ["evaluate", "--help"]),
)
def test_help_does_not_load_model(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(workflow, "load_encoder", _fail_if_called)

    assert workflow.main(args) == 0


def test_evaluate_missing_ground_truth_is_blocked_before_model_load(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(workflow, "load_encoder", _fail_if_called)

    assert workflow.main(["evaluate", "--ground-truth", str(tmp_path / "missing.jsonl")]) == 2

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked"
    assert output["cause"] == "external_evidence_unavailable"


@pytest.mark.parametrize(
    "args",
    (
        ["build-index", "--model-id", "  "],
        ["query", "--question", "  "],
        ["evaluate", "--model-id", ""],
    ),
)
def test_invalid_preflight_is_failed_without_model_load(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    monkeypatch.setattr(workflow, "load_encoder", _fail_if_called)

    assert workflow.main(args) == 1

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed"
    assert output["cause"] == "invalid_input"


def test_all_commands_succeed_lazily_and_local_files_only_is_propagated(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []
    cli, cache, ground_truth, report = _inputs(tmp_path, calls)
    runner = CliRunner()

    queried = runner.invoke(
        cli,
        [
            "query",
            "--cache-dir",
            str(cache),
            "--question",
            "Binance",
            "--local-files-only",
        ],
    )
    evaluated = runner.invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
            "--local-files-only",
        ],
    )

    assert queried.exit_code == evaluated.exit_code == 0, (queried.output, evaluated.output)
    assert all(local_files_only for _, local_files_only in calls)
    payload = json.loads(report.read_bytes())
    assert payload["status"] == "ready"
    assert payload["git_sha"] == "1" * 40
    assert payload["git_worktree_dirty"] is True
    assert payload["index_manifest_sha256"]
    assert payload["index_matrices_sha256"]
    assert "Binance case" not in report.read_text(encoding="utf-8")


def test_query_strict_load_does_not_rebuild_or_create_missing_lock(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []
    cli = _cli(calls)
    cache = tmp_path / "cache"

    result = CliRunner().invoke(cli, ["query", "--cache-dir", str(cache), "--question", "Binance"])

    assert result.exit_code == 2
    assert json.loads(result.output)["cause"] == "external_evidence_unavailable"
    assert calls == []
    assert not cache.exists()


@pytest.mark.parametrize("kind", ("same", "symlink", "hardlink", "future_generation"))
def test_evaluate_rejects_report_aliases_before_model(tmp_path: Path, kind: str) -> None:
    calls: list[tuple[str, bool]] = []
    cli, cache, ground_truth, report = _inputs(tmp_path, calls)
    manifest = workflow.EntityCachePaths.from_directory(cache).manifest
    if kind == "same":
        report = ground_truth
    elif kind == "symlink":
        report = tmp_path / "manifest-alias.json"
        report.symlink_to(manifest)
    elif kind == "hardlink":
        report = tmp_path / "ground-truth-hardlink.jsonl"
        os.link(ground_truth, report)
    else:
        report = cache / f"entity-index-{'f' * 64}.npz"

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "invalid_input"
    assert calls == []


def test_atomic_failure_preserves_prior_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []
    cli, cache, ground_truth, report = _inputs(tmp_path, calls)
    report.write_bytes(b"accepted evidence\n")
    monkeypatch.setattr(
        workflow.os,
        "replace",
        lambda source, destination: (_ for _ in ()).throw(OSError("disk failure")),
    )

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert report.read_bytes() == b"accepted evidence\n"


def test_malformed_model_output_is_failed_not_blocked(tmp_path: Path) -> None:
    cli = workflow.create_cli(
        encoder_loader=lambda model_id, local_files_only: object(),
        corpus_builder=lambda artifacts: _corpus(),
    )

    result = CliRunner().invoke(cli, ["build-index", "--cache-dir", str(tmp_path / "cache")])

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "cache_integrity_failure"


def test_evaluation_keeps_publication_in_preflight_parent_after_symlink_retarget(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, bool]] = []
    _, cache, ground_truth, _ = _inputs(tmp_path, calls)
    accepted_ground_truth = ground_truth.read_bytes()
    safe_parent = tmp_path / "safe-reports"
    safe_parent.mkdir()
    report_parent = tmp_path / "report-parent"
    report_parent.symlink_to(safe_parent, target_is_directory=True)
    report = report_parent / ground_truth.name

    def retargeting_encoder(model_id: str, local_files_only: bool) -> FakeEncoder:
        calls.append((model_id, local_files_only))
        report_parent.unlink()
        report_parent.symlink_to(ground_truth.parent, target_is_directory=True)
        return FakeEncoder()

    cli = workflow.create_cli(
        encoder_loader=retargeting_encoder,
        corpus_builder=lambda artifacts: _corpus(),
        git_provenance_factory=lambda repository: workflow.GitProvenance("1" * 40, False),
    )

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    assert ground_truth.read_bytes() == accepted_ground_truth
    assert (safe_parent / ground_truth.name).is_file()


def test_evaluate_lock_deletion_after_preflight_is_failed_without_recreation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []
    cli, cache, ground_truth, report = _inputs(tmp_path, calls)
    original_load_index = workflow.load_index

    def delete_lock_then_load(*args, **kwargs):
        workflow.EntityCachePaths.from_directory(cache).lock.unlink()
        return original_load_index(*args, **kwargs)

    monkeypatch.setattr(workflow, "load_index", delete_lock_then_load)

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "cache_integrity_failure"
    assert calls == []
    assert not workflow.EntityCachePaths.from_directory(cache).lock.exists()


def test_post_replace_directory_fsync_failure_restores_prior_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []
    cli, cache, ground_truth, report = _inputs(tmp_path, calls)
    report.write_bytes(b"accepted evidence\n")
    original_replace = workflow.os.replace
    original_fsync = workflow.os.fsync
    report_replaced = False
    directory_failure_used = False

    def observe_replace(source, destination, *args, **kwargs):
        nonlocal report_replaced
        original_replace(source, destination, *args, **kwargs)
        if destination == report.name:
            report_replaced = True

    def fail_first_directory_fsync_after_replace(descriptor: int) -> None:
        nonlocal directory_failure_used
        if (
            report_replaced
            and not directory_failure_used
            and stat.S_ISDIR(os.fstat(descriptor).st_mode)
        ):
            directory_failure_used = True
            raise OSError("directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(workflow.os, "replace", observe_replace)
    monkeypatch.setattr(workflow.os, "fsync", fail_first_directory_fsync_after_replace)

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "publication_failure"
    assert directory_failure_used is True
    assert report.read_bytes() == b"accepted evidence\n"


def test_incomplete_post_replace_rollback_retains_discoverable_prior_report_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.json"
    accepted_report = b"accepted evidence\n"
    report.write_bytes(accepted_report)
    destination = workflow._open_report_destination(report)
    original_replace = workflow.os.replace
    original_fsync = workflow.os.fsync
    report_replaced = False
    directory_failure_used = False

    def fail_backup_restore(source, target, *args, **kwargs):
        nonlocal report_replaced
        if target == report.name and str(source).endswith(".backup"):
            raise OSError("backup restore failure")
        original_replace(source, target, *args, **kwargs)
        if target == report.name:
            report_replaced = True

    def fail_post_replace_directory_fsync(descriptor: int) -> None:
        nonlocal directory_failure_used
        if (
            report_replaced
            and not directory_failure_used
            and stat.S_ISDIR(os.fstat(descriptor).st_mode)
        ):
            directory_failure_used = True
            raise OSError("directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(workflow.os, "replace", fail_backup_restore)
    monkeypatch.setattr(workflow.os, "fsync", fail_post_replace_directory_fsync)
    try:
        with pytest.raises(workflow.ReportPublicationError, match="rollback was incomplete"):
            workflow._atomic_write(destination, b"new report\n")
    finally:
        destination.close()

    backups = list(tmp_path.glob(f".{report.name}.*.backup"))
    assert directory_failure_used is True
    assert len(backups) == 1
    assert backups[0].read_bytes() == accepted_report


def test_concurrent_report_publication_serializes_rollback_and_success(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_bytes(b"accepted evidence\n")
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    results = context.Queue()
    failed_writer = context.Process(
        target=_concurrent_report_writer,
        args=(str(report), b"failed writer\n", True, ready, release, results),
    )
    successful_writer = context.Process(
        target=_concurrent_report_writer,
        args=(str(report), b"successful writer\n", False, ready, release, results),
    )
    failed_writer.start()
    assert ready.wait(10)
    successful_writer.start()
    release.set()
    failed_writer.join(10)
    successful_writer.join(10)

    assert failed_writer.exitcode == 0
    assert successful_writer.exitcode == 0
    assert sorted((results.get(timeout=1), results.get(timeout=1))) == ["failed", "published"]
    assert report.read_bytes() == b"successful writer\n"


def test_replacing_former_report_sidecar_cannot_bypass_publication_lock(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_bytes(b"accepted evidence\n")
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    attempting = context.Event()
    entered = context.Event()
    results = context.Queue()
    first = context.Process(
        target=_concurrent_report_writer,
        args=(str(report), b"first writer\n", True, ready, release, results),
    )
    second = context.Process(
        target=_concurrent_report_writer,
        args=(
            str(report),
            b"second writer\n",
            False,
            ready,
            release,
            results,
            attempting,
            entered,
        ),
    )
    first.start()
    assert ready.wait(10)
    former_sidecar = report.with_name(f".{report.name}.lock")
    former_sidecar.unlink(missing_ok=True)
    former_sidecar.write_bytes(b"replacement inode\n")
    second.start()
    assert attempting.wait(10)
    assert not entered.wait(0.3)
    release.set()
    first.join(10)
    second.join(10)

    assert first.exitcode == second.exitcode == 0
    assert entered.is_set()
    assert sorted((results.get(timeout=1), results.get(timeout=1))) == ["failed", "published"]
    assert report.read_bytes() == b"second writer\n"
    assert former_sidecar.read_bytes() == b"replacement inode\n"


@pytest.mark.parametrize(
    "error",
    (httpx.ConnectError("offline"), httpx.ReadTimeout("slow"), OSError("missing")),
)
def test_model_transport_and_local_failures_are_blocked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    class FailingSentenceTransformer:
        def __init__(self, *args, **kwargs) -> None:
            raise error

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FailingSentenceTransformer),
    )

    with pytest.raises(workflow.ExternalDependencyError):
        workflow.load_encoder("fixture/model", local_files_only=True)

    assert workflow._failure("query", workflow.ExternalDependencyError(str(error))) == 2
    assert json.loads(capsys.readouterr().out)["cause"] == "external_model_unavailable"


def test_unrelated_publication_file_not_found_is_failed_not_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []
    cli, cache, ground_truth, report = _inputs(tmp_path, calls)

    original_replace = workflow.os.replace

    def missing_destination(source, destination, *args, **kwargs) -> None:
        if destination == report.name:
            raise OSError("destination disappeared")
        original_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(workflow.os, "replace", missing_destination)

    result = CliRunner().invoke(
        cli,
        [
            "evaluate",
            "--cache-dir",
            str(cache),
            "--ground-truth",
            str(ground_truth),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["cause"] == "publication_failure"


def _initialize_git_repository(path: Path, content: str) -> str:
    path.mkdir()
    commands = (
        ("init",),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    )
    for arguments in commands:
        subprocess.run(["git", *arguments], cwd=path, check=True, capture_output=True, text=True)
    (path / "tracked.txt").write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.txt"], cwd=path, check=True, capture_output=True, text=True
    )
    subprocess.run(
        ["git", "commit", "-m", "fixture"], cwd=path, check=True, capture_output=True, text=True
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_git_provenance_ignores_ambient_repository_override_and_requires_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    expected_sha = _initialize_git_repository(repository, "primary\n")
    other_repository = tmp_path / "other-repository"
    _initialize_git_repository(other_repository, "other\n")
    monkeypatch.setenv("GIT_DIR", str(other_repository / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other_repository))

    provenance = workflow._git_provenance(repository)

    assert provenance == workflow.GitProvenance(expected_sha, False)
    nested = repository / "nested"
    nested.mkdir()
    with pytest.raises(workflow.ProvenanceError, match="top level"):
        workflow._git_provenance(nested)


def test_defaults_use_shared_linking_cache_and_numbered_script_names_subcommand(
    tmp_path: Path,
) -> None:
    assert workflow.DEFAULT_CACHE_DIRECTORY == Path("src/nl2sparql/linking/cache")
    notebook_path = WORKFLOW_PATH.parents[1] / "notebooks/12_entity_linker_eval.ipynb"
    notebook = json.loads(notebook_path.read_text())
    source = "".join(notebook["cells"][1]["source"])
    assert "src/nl2sparql/linking/cache" in source

    wrapper = WORKFLOW_PATH.parent / "14_entity_linker.py"
    completed = subprocess.run(
        [sys.executable, str(wrapper), "query", "--unknown-option"],
        check=False,
        capture_output=True,
        text=True,
        cwd=WORKFLOW_PATH.parents[1],
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["command"] == "query"
