"""Offline contracts for the production entity-linker workflow."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

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
