"""Offline tests for schema-linker ground truth, metrics, and workflow CLI."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from nl2sparql.linking.schema import (
    LinkResult,
    SchemaCachePaths,
    SchemaElement,
    SchemaLinkerError,
    SchemaMatch,
)
from nl2sparql.linking.schema import evaluate as evaluate_module
from nl2sparql.linking.schema.evaluate import (
    GroundTruthCase,
    evaluate_linker,
    load_ground_truth,
)
from nl2sparql.sql.schema import CATALOG_PATH

WORKFLOW_PATH = Path(__file__).parents[2] / "scripts/schema_linker_workflow.py"
WORKFLOW_SPEC = importlib.util.spec_from_file_location("schema_linker_workflow", WORKFLOW_PATH)
assert WORKFLOW_SPEC is not None and WORKFLOW_SPEC.loader is not None
workflow_module = importlib.util.module_from_spec(WORKFLOW_SPEC)
WORKFLOW_SPEC.loader.exec_module(workflow_module)
create_cli = workflow_module.create_cli


def _element(element_id: str, kind: str) -> SchemaElement:
    document = f"document for {element_id}"
    return SchemaElement(element_id, kind, document, hashlib.sha256(document.encode()).hexdigest())


VALID_ELEMENTS = (
    _element("blocks", "relation"),
    _element("transactions", "relation"),
    _element("blocks.number", "field"),
    _element("transactions.from_address", "field"),
    _element("transactions.to_address", "field"),
    _element("transactions.value", "field"),
)


def _ground_truth_rows(count: int = 50) -> list[dict[str, object]]:
    return [
        {
            "id": f"q-{index:03d}",
            "nl": f"question {index}",
            "gold_relations": ["transactions"],
            "gold_fields": ["transactions.value"],
        }
        for index in range(count)
    ]


def _write_jsonl(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _match(element_id: str, kind: str) -> SchemaMatch:
    return SchemaMatch(element_id, kind, 1.0, 1.0, 1.0, "a" * 64)


class RankedLinker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def link(self, question: str, top_k: int = 10) -> LinkResult:
        self.calls.append((question, top_k))
        rankings = {
            "first": LinkResult(
                relations=(_match("blocks", "relation"), _match("transactions", "relation")),
                fields=(
                    _match("transactions.from_address", "field"),
                    _match("transactions.value", "field"),
                    _match("blocks.number", "field"),
                ),
            ),
            "second": LinkResult(
                relations=(_match("transactions", "relation"), _match("blocks", "relation")),
                fields=(
                    _match("blocks.number", "field"),
                    _match("transactions.to_address", "field"),
                    _match("transactions.value", "field"),
                ),
            ),
        }
        return rankings[question]


class FakeEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        rows = np.asarray(
            [[float(len(text)), float(text.count("address")), 1.0] for text in texts],
            dtype=np.float64,
        )
        rows /= np.linalg.norm(rows, axis=1, keepdims=True)
        return rows[0] if isinstance(sentences, str) else rows


class NetworkEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        raise OSError("network unavailable")


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda rows: rows[:-1], "exactly 50"),
        (lambda rows: [*rows[:-1], {**rows[-1], "id": rows[0]["id"]}], "duplicate ID"),
        (lambda rows: [*rows[:-1], {**rows[-1], "nl": rows[0]["nl"]}], "duplicate NL"),
        (lambda rows: [*rows[:-1], {**rows[-1], "gold_fields": []}], "gold_fields"),
        (
            lambda rows: [
                *rows[:-1],
                {**rows[-1], "gold_fields": ["transactions.unknown"]},
            ],
            "unknown",
        ),
        (
            lambda rows: [
                *rows[:-1],
                {**rows[-1], "gold_relations": ["blocks"]},
            ],
            "consistent",
        ),
        (lambda rows: [*rows[:-1], {**rows[-1], "extra": True}], "exact keys"),
    ),
)
def test_load_ground_truth_rejects_invalid_dataset_with_line_context(
    tmp_path: Path, mutate, message: str
) -> None:
    path = tmp_path / "ground-truth.jsonl"
    _write_jsonl(path, mutate(_ground_truth_rows()))

    with pytest.raises(SchemaLinkerError, match=rf"line 50.*{message}"):
        load_ground_truth(path, VALID_ELEMENTS)


def test_load_ground_truth_rejects_malformed_json_with_line_context(tmp_path: Path) -> None:
    path = tmp_path / "ground-truth.jsonl"
    path.write_text(json.dumps(_ground_truth_rows(1)[0]) + "\nnot-json\n", encoding="utf-8")

    with pytest.raises(SchemaLinkerError, match=r"line 2.*JSON"):
        load_ground_truth(path, VALID_ELEMENTS, expected_count=2)


def test_load_ground_truth_returns_immutable_typed_cases(tmp_path: Path) -> None:
    path = tmp_path / "ground-truth.jsonl"
    rows = _ground_truth_rows(2)
    rows[0]["gold_fields"] = ["transactions.from_address", "transactions.value"]
    _write_jsonl(path, rows)

    cases = load_ground_truth(path, VALID_ELEMENTS, expected_count=2)

    assert cases == (
        GroundTruthCase(
            id="q-000",
            nl="question 0",
            gold_relations=("transactions",),
            gold_fields=("transactions.from_address", "transactions.value"),
        ),
        GroundTruthCase(
            id="q-001",
            nl="question 1",
            gold_relations=("transactions",),
            gold_fields=("transactions.value",),
        ),
    )


def test_evaluate_linker_computes_micro_recall_mrr_and_excludes_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linker = RankedLinker()
    cases = (
        GroundTruthCase(
            "q-1",
            "first",
            ("blocks", "transactions"),
            ("transactions.value", "transactions.to_address"),
        ),
        GroundTruthCase(
            "q-2",
            "second",
            ("transactions",),
            ("transactions.value",),
        ),
    )
    ticks = iter((10.0, 10.01, 20.0, 20.03))
    monkeypatch.setattr(evaluate_module, "perf_counter", lambda: next(ticks))

    report = evaluate_linker(linker, cases, field_k=2, relation_k=1)

    assert linker.calls == [("first", 2), ("first", 2), ("second", 2)]
    assert report.case_count == 2
    assert report.relation_recall_at_k == pytest.approx(2 / 3)
    assert report.field_recall_at_k == pytest.approx(1 / 3)
    assert report.field_mrr == pytest.approx(1 / 4)
    assert report.latency_p50_ms == pytest.approx(20.0)
    assert report.latency_p95_ms == pytest.approx(29.0)
    assert report.results[0].retrieved_fields == (
        "transactions.from_address",
        "transactions.value",
    )


def test_evaluate_linker_rejects_empty_cases_and_invalid_cutoffs() -> None:
    linker = RankedLinker()

    with pytest.raises(SchemaLinkerError, match="cases"):
        evaluate_linker(linker, ())
    with pytest.raises(SchemaLinkerError, match="field_k"):
        evaluate_linker(
            linker, (GroundTruthCase("q", "first", ("blocks",), ("blocks.number",)),), field_k=0
        )
    with pytest.raises(SchemaLinkerError, match="relation_k"):
        evaluate_linker(
            linker,
            (GroundTruthCase("q", "first", ("blocks",), ("blocks.number",)),),
            relation_k=True,
        )


def _cli(factory_calls: list[str]):
    def encoder_factory(model_id: str):
        factory_calls.append(model_id)
        return FakeEncoder()

    return create_cli(
        encoder_factory=encoder_factory,
        clock=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        git_sha_factory=lambda: "1" * 40,
    )


def test_cli_help_never_initializes_encoder() -> None:
    calls: list[str] = []
    runner = CliRunner()
    cli = _cli(calls)

    for arguments in (
        ["--help"],
        ["build-index", "--help"],
        ["query", "--help"],
        ["evaluate", "--help"],
    ):
        result = runner.invoke(cli, arguments)
        assert result.exit_code == 0, result.output

    assert calls == []


def test_cli_missing_ground_truth_is_blocked_without_factory_or_overwrite(tmp_path: Path) -> None:
    calls: list[str] = []
    report = tmp_path / "report.json"
    report.write_bytes(b"accepted report\n")

    result = CliRunner().invoke(
        _cli(calls),
        [
            "evaluate",
            "--ground-truth",
            str(tmp_path / "missing.jsonl"),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code != 0
    assert json.loads(result.output) == {
        "status": "blocked",
        "command": "evaluate",
        "reason": f"missing required file: {tmp_path / 'missing.jsonl'}",
    }
    assert report.read_bytes() == b"accepted report\n"
    assert calls == []


def test_cli_invalid_cache_is_failed_without_factory(tmp_path: Path) -> None:
    calls: list[str] = []
    cache = tmp_path / "cache"
    cache.mkdir()
    paths = SchemaCachePaths.from_directory(cache)
    paths.manifest.write_text("{}", encoding="utf-8")
    paths.matrices.write_bytes(b"invalid")
    paths.lock.write_bytes(b"")

    result = CliRunner().invoke(
        _cli(calls),
        ["query", "--cache-dir", str(cache), "--question", "largest transaction"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert payload["command"] == "query"
    assert "manifest digest" in payload["reason"]
    assert calls == []


def test_cli_query_does_not_create_a_missing_cache_lock(tmp_path: Path) -> None:
    calls: list[str] = []
    cli = _cli(calls)
    runner = CliRunner()
    cache = tmp_path / "cache"
    built = runner.invoke(cli, ["build-index", "--cache-dir", str(cache)])
    assert built.exit_code == 0, built.output
    calls.clear()
    lock = SchemaCachePaths.from_directory(cache).lock
    lock.unlink()

    result = runner.invoke(
        cli,
        ["query", "--cache-dir", str(cache), "--question", "transaction value"],
    )

    assert result.exit_code != 0
    assert json.loads(result.output)["status"] == "blocked"
    assert lock.exists() is False
    assert calls == []


def test_cli_invalid_query_cutoff_is_failed_before_factory(tmp_path: Path) -> None:
    calls: list[str] = []

    result = CliRunner().invoke(
        _cli(calls),
        ["query", "--field-k", "0", "--question", "transaction value"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert "field_k" in payload["reason"]
    assert calls == []


@pytest.mark.parametrize(
    "failing_factory",
    (
        lambda model_id: (_ for _ in ()).throw(ModuleNotFoundError("model package missing")),
        lambda model_id: NetworkEncoder(),
    ),
)
def test_cli_missing_model_or_network_is_structured_blocked(
    tmp_path: Path, failing_factory
) -> None:
    cache = tmp_path / "cache"
    built = CliRunner().invoke(_cli([]), ["build-index", "--cache-dir", str(cache)])
    assert built.exit_code == 0, built.output
    cli = create_cli(
        encoder_factory=failing_factory,
        clock=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        git_sha_factory=lambda: "1" * 40,
    )

    result = CliRunner().invoke(
        cli,
        ["query", "--cache-dir", str(cache), "--question", "transaction value"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert payload["command"] == "query"


def test_cli_model_commands_use_factory_lazily_and_emit_hashed_provenance(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    cli = _cli(calls)
    runner = CliRunner()
    cache = tmp_path / "cache"
    ground_truth = tmp_path / "ground-truth.jsonl"
    report = tmp_path / "evaluation.json"
    relation = "transaction_facts"
    field = "transaction_facts.value_wei"
    rows = _ground_truth_rows()
    for row in rows:
        row["gold_relations"] = [relation]
        row["gold_fields"] = [field]
    _write_jsonl(ground_truth, rows)

    built = runner.invoke(cli, ["build-index", "--cache-dir", str(cache)])
    queried = runner.invoke(
        cli,
        ["query", "--cache-dir", str(cache), "--question", "transaction value"],
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
        ],
    )

    assert built.exit_code == queried.exit_code == evaluated.exit_code == 0, (
        built.output,
        queried.output,
        evaluated.output,
    )
    assert len(calls) == 3
    payload = json.loads(report.read_bytes())
    assert payload["schema_version"] == 1
    assert payload["status"] == "ready"
    assert payload["generated_at"] == "2026-08-15T12:00:00Z"
    assert payload["git_sha"] == "1" * 40
    assert payload["model_id"] == calls[0]
    assert payload["weights"] == {"lexical": 0.35, "semantic": 0.65}
    assert payload["catalog_sha256"] == hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    assert payload["ground_truth_sha256"] == hashlib.sha256(ground_truth.read_bytes()).hexdigest()
    assert len(payload["cache_sha256"]) == 64
    assert payload["metrics"]["case_count"] == 50
    supplied_hash = payload.pop("report_sha256")
    canonical = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert supplied_hash == hashlib.sha256(canonical).hexdigest()
    assert report.read_bytes().endswith(b"\n")
    assert not list(report.parent.glob(f".{report.name}.*.tmp"))


def test_cli_never_overwrites_ground_truth_with_report(tmp_path: Path) -> None:
    calls: list[str] = []
    ground_truth = tmp_path / "ground-truth.jsonl"
    _write_jsonl(ground_truth, _ground_truth_rows())
    original = ground_truth.read_bytes()

    result = CliRunner().invoke(
        _cli(calls),
        ["evaluate", "--ground-truth", str(ground_truth), "--report", str(ground_truth)],
    )

    assert result.exit_code != 0
    assert json.loads(result.output)["status"] == "failed"
    assert ground_truth.read_bytes() == original
    assert calls == []
