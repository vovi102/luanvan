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
    load_index,
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
        self.calls: list[tuple[str, int | None]] = []

    def link(self, question: str, top_k: int | None = 10) -> LinkResult:
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


class CauseChainedProgrammingEncoder:
    def encode(self, sentences, *, normalize_embeddings=True):
        try:
            raise OSError("incidental low-level cause")
        except OSError as exc:
            raise RuntimeError("programming bug") from exc


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


def test_load_ground_truth_reports_the_first_extra_row_line(tmp_path: Path) -> None:
    path = tmp_path / "ground-truth.jsonl"
    _write_jsonl(path, _ground_truth_rows(51))

    with pytest.raises(SchemaLinkerError, match=r"line 51.*exactly 50"):
        load_ground_truth(path, VALID_ELEMENTS)


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

    report = evaluate_linker(linker, cases, relation_k=1)

    assert linker.calls == [("first", None), ("first", None), ("second", None)]
    assert report.case_count == 2
    assert report.relation_recall_at_k == pytest.approx(2 / 3)
    assert report.field_recall_at_5 == pytest.approx(2 / 3)
    assert report.field_recall_at_10 == pytest.approx(2 / 3)
    assert report.field_mrr == pytest.approx(5 / 12)
    assert report.latency_p50_ms == pytest.approx(20.0)
    assert report.latency_p95_ms == pytest.approx(29.0)
    assert report.results[0].retrieved_fields == (
        "transactions.from_address",
        "transactions.value",
        "blocks.number",
    )


class FullFieldPoolLinker:
    def __init__(self, gold_ranks: tuple[int, ...]) -> None:
        self.gold_ranks = gold_ranks
        self.calls: list[int | None] = []

    def link(self, question: str, top_k: int | None = 10) -> LinkResult:
        self.calls.append(top_k)
        fields = tuple(_match(f"transactions.field_{rank:02d}", "field") for rank in range(1, 13))
        return LinkResult(relations=(_match("transactions", "relation"),), fields=fields)


def test_evaluate_linker_emits_hand_derived_fixed_field_recalls() -> None:
    linker = FullFieldPoolLinker((3, 7, 11))
    case = GroundTruthCase(
        "q-1",
        "ranked fields",
        ("transactions",),
        tuple(f"transactions.field_{rank:02d}" for rank in linker.gold_ranks),
    )

    report = evaluate_linker(linker, (case,))

    assert linker.calls == [None, None]
    assert report.field_recall_at_5 == pytest.approx(1 / 3)
    assert report.field_recall_at_10 == pytest.approx(2 / 3)
    assert report.field_mrr == pytest.approx(1 / 3)
    assert report.results[0].field_hits_at_5 == 1
    assert report.results[0].field_hits_at_10 == 2


def test_evaluate_linker_mrr_uses_first_relevant_field_beyond_rank_10() -> None:
    linker = FullFieldPoolLinker((11,))
    case = GroundTruthCase(
        "q-1",
        "rank eleven field",
        ("transactions",),
        ("transactions.field_11",),
    )

    report = evaluate_linker(linker, (case,))

    assert report.field_recall_at_5 == 0.0
    assert report.field_recall_at_10 == 0.0
    assert report.field_mrr == pytest.approx(1 / 11)
    assert report.results[0].field_reciprocal_rank == pytest.approx(1 / 11)


def test_evaluate_linker_rejects_empty_cases_and_invalid_cutoffs() -> None:
    linker = RankedLinker()

    with pytest.raises(SchemaLinkerError, match="cases"):
        evaluate_linker(linker, ())
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


def _workflow_inputs(tmp_path: Path, factory_calls: list[str]):
    tmp_path.mkdir(parents=True, exist_ok=True)
    catalog = tmp_path / "catalog.json"
    synonyms = tmp_path / "synonyms.json"
    cache = tmp_path / "cache"
    ground_truth = tmp_path / "ground-truth.jsonl"
    report = tmp_path / "evaluation.json"
    catalog.write_bytes(CATALOG_PATH.read_bytes())
    synonyms.write_bytes(workflow_module.DEFAULT_SYNONYMS_PATH.read_bytes())
    rows = _ground_truth_rows()
    for row in rows:
        row["gold_relations"] = ["transaction_facts"]
        row["gold_fields"] = ["transaction_facts.value_wei"]
    _write_jsonl(ground_truth, rows)
    cli = _cli(factory_calls)
    built = CliRunner().invoke(
        cli,
        [
            "build-index",
            "--catalog",
            str(catalog),
            "--synonyms",
            str(synonyms),
            "--cache-dir",
            str(cache),
        ],
    )
    assert built.exit_code == 0, built.output
    factory_calls.clear()
    return cli, catalog, synonyms, cache, ground_truth, report


def _evaluate_arguments(
    catalog: Path,
    synonyms: Path,
    cache: Path,
    ground_truth: Path,
    report: Path,
) -> list[str]:
    return [
        "evaluate",
        "--catalog",
        str(catalog),
        "--synonyms",
        str(synonyms),
        "--cache-dir",
        str(cache),
        "--ground-truth",
        str(ground_truth),
        "--report",
        str(report),
    ]


def _current_matrix_path(cache: Path) -> Path:
    manifest = json.loads(SchemaCachePaths.from_directory(cache).manifest.read_bytes())
    return cache / manifest["matrices_file"]


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


def test_cli_exposes_field_cutoff_only_for_query() -> None:
    cli = _cli([])
    query_help = CliRunner().invoke(cli, ["query", "--help"])
    evaluate_help = CliRunner().invoke(cli, ["evaluate", "--help"])

    assert "--field-k" in query_help.output
    assert "--field-k" not in evaluate_help.output


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
    assert payload["schema_version"] == 2
    assert payload["status"] == "ready"
    assert payload["generated_at"] == "2026-08-15T12:00:00Z"
    assert payload["git_sha"] == "1" * 40
    assert payload["model_id"] == calls[0]
    assert payload["weights"] == {"lexical": 0.35, "semantic": 0.65}
    assert payload["catalog_sha256"] == hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    assert payload["ground_truth_sha256"] == hashlib.sha256(ground_truth.read_bytes()).hexdigest()
    assert len(payload["cache_sha256"]) == 64
    assert payload["metrics"]["case_count"] == 50
    assert "field_recall_at_5" in payload["metrics"]
    assert "field_recall_at_10" in payload["metrics"]
    assert "field_k" not in payload["metrics"]
    assert "field_recall_at_k" not in payload["metrics"]
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


def test_evaluate_rejects_all_input_and_cache_report_aliases_before_model(
    tmp_path: Path,
) -> None:
    protected_names = (
        "ground_truth",
        "catalog",
        "synonyms",
        "manifest",
        "matrices",
        "lock",
        "manifest_symlink",
    )
    for protected_name in protected_names:
        calls: list[str] = []
        case_root = tmp_path / protected_name
        cli, catalog, synonyms, cache, ground_truth, _ = _workflow_inputs(case_root, calls)
        paths = SchemaCachePaths.from_directory(cache)
        matrix = _current_matrix_path(cache)
        targets = {
            "ground_truth": ground_truth,
            "catalog": catalog,
            "synonyms": synonyms,
            "manifest": paths.manifest,
            "matrices": matrix,
            "lock": paths.lock,
        }
        report = targets.get(protected_name)
        if protected_name == "manifest_symlink":
            report = case_root / "manifest-alias.json"
            report.symlink_to(paths.manifest)
        assert report is not None
        protected = {path: path.read_bytes() for path in targets.values()}

        result = CliRunner().invoke(
            cli,
            _evaluate_arguments(catalog, synonyms, cache, ground_truth, report),
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["status"] == "failed"
        assert "overwrite" in payload["reason"]
        assert calls == []
        assert {path: path.read_bytes() for path in targets.values()} == protected


def test_evaluate_parses_the_same_catalog_snapshot_it_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    cli, catalog, synonyms, cache, ground_truth, report = _workflow_inputs(tmp_path, calls)
    accepted_catalog = catalog.read_bytes()
    raced_catalog = json.loads(accepted_catalog)
    fields = raced_catalog["analytical_relations"]["transaction_facts"]["fields"]
    fields["value_wei_raced"] = fields.pop("value_wei")
    for mapping in raced_catalog["semantic_mappings"]:
        for target in mapping["targets"]:
            if target.get("relation") == "transaction_facts" and target.get("field") == "value_wei":
                target["field"] = "value_wei_raced"
    real_load_catalog = workflow_module.load_catalog

    def replace_before_second_read(path: Path, *, snapshot: bytes | None = None):
        if snapshot is None:
            path.write_text(json.dumps(raced_catalog), encoding="utf-8")
        return real_load_catalog(path, **({"snapshot": snapshot} if snapshot is not None else {}))

    monkeypatch.setattr(workflow_module, "load_catalog", replace_before_second_read)

    result = CliRunner().invoke(
        cli,
        _evaluate_arguments(catalog, synonyms, cache, ground_truth, report),
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_bytes())
    assert payload["catalog_sha256"] == hashlib.sha256(accepted_catalog).hexdigest()


def test_evaluate_provenance_survives_deterministic_ground_truth_and_cache_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    cli, catalog, synonyms, cache, ground_truth, report = _workflow_inputs(tmp_path, calls)
    accepted_ground_truth = ground_truth.read_bytes()
    accepted_synonyms = synonyms.read_bytes()
    paths = SchemaCachePaths.from_directory(cache)
    accepted_matrix_path = _current_matrix_path(cache)
    _, _, _, elements = workflow_module._catalog_inputs(catalog, synonyms)
    loaded = load_index(
        paths,
        hashlib.sha256(catalog.read_bytes()).hexdigest(),
        workflow_module.DEFAULT_MODEL_ID,
        workflow_module.DOCUMENT_VERSION,
        elements,
    )
    cache_identity = {
        "manifest_sha256": hashlib.sha256(paths.manifest.read_bytes()).hexdigest(),
        "matrices_sha256": loaded.metadata.matrices_sha256,
    }
    expected_cache_sha256 = hashlib.sha256(
        (json.dumps(cache_identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    real_evaluate = workflow_module.evaluate_linker

    def mutate_inputs_after_evaluation(*args, **kwargs):
        evaluation = real_evaluate(*args, **kwargs)
        ground_truth.write_bytes(b"raced ground truth\n")
        paths.manifest.write_bytes(b"raced manifest\n")
        accepted_matrix_path.write_bytes(b"raced matrices\n")
        return evaluation

    monkeypatch.setattr(workflow_module, "evaluate_linker", mutate_inputs_after_evaluation)

    result = CliRunner().invoke(
        cli,
        _evaluate_arguments(catalog, synonyms, cache, ground_truth, report),
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_bytes())
    assert payload["ground_truth_sha256"] == hashlib.sha256(accepted_ground_truth).hexdigest()
    assert payload["synonyms_sha256"] == hashlib.sha256(accepted_synonyms).hexdigest()
    assert payload["cache_manifest_sha256"] == cache_identity["manifest_sha256"]
    assert payload["cache_matrices_sha256"] == cache_identity["matrices_sha256"]
    assert payload["cache_sha256"] == expected_cache_sha256


@pytest.mark.parametrize(
    "git_sha_factory",
    (
        lambda: "unknown",
        lambda: (_ for _ in ()).throw(OSError("git unavailable")),
    ),
)
def test_evaluate_invalid_git_sha_fails_closed_before_model_and_publication(
    tmp_path: Path, git_sha_factory
) -> None:
    calls: list[str] = []
    _, catalog, synonyms, cache, ground_truth, report = _workflow_inputs(tmp_path, calls)
    report.write_bytes(b"accepted report\n")
    cli = create_cli(
        encoder_factory=lambda model_id: calls.append(model_id) or FakeEncoder(),
        clock=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        git_sha_factory=git_sha_factory,
    )

    result = CliRunner().invoke(
        cli,
        _evaluate_arguments(catalog, synonyms, cache, ground_truth, report),
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert "git SHA" in payload["reason"]
    assert calls == []
    assert report.read_bytes() == b"accepted report\n"


def test_cli_rejects_malformed_model_id_as_failed_before_factory(tmp_path: Path) -> None:
    calls: list[str] = []

    result = CliRunner().invoke(
        _cli(calls),
        ["query", "--model-id", " ", "--question", "transaction value"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert "model_id" in payload["reason"]
    assert calls == []


def test_cli_programming_factory_error_is_failed_not_blocked(tmp_path: Path) -> None:
    calls: list[str] = []
    _, catalog, synonyms, cache, _, _ = _workflow_inputs(tmp_path, calls)

    def broken_factory(model_id: str):
        raise RuntimeError("programming bug")

    cli = create_cli(encoder_factory=broken_factory)
    result = CliRunner().invoke(
        cli,
        [
            "query",
            "--catalog",
            str(catalog),
            "--synonyms",
            str(synonyms),
            "--cache-dir",
            str(cache),
            "--question",
            "transaction value",
        ],
    )

    assert result.exit_code != 0
    assert json.loads(result.output) == {
        "status": "failed",
        "command": "query",
        "reason": "programming bug",
    }


def test_cli_cause_chained_programming_error_is_failed_not_blocked(tmp_path: Path) -> None:
    calls: list[str] = []
    _, catalog, synonyms, cache, _, _ = _workflow_inputs(tmp_path, calls)
    cli = create_cli(encoder_factory=lambda model_id: CauseChainedProgrammingEncoder())

    result = CliRunner().invoke(
        cli,
        [
            "query",
            "--catalog",
            str(catalog),
            "--synonyms",
            str(synonyms),
            "--cache-dir",
            str(cache),
            "--question",
            "transaction value",
        ],
    )

    assert result.exit_code != 0
    assert json.loads(result.output)["status"] == "failed"


@pytest.mark.parametrize("command", ("query", "evaluate"))
def test_cli_rejects_cache_built_from_stale_synonym_documents_before_model(
    tmp_path: Path, command: str
) -> None:
    calls: list[str] = []
    cli, catalog, synonyms, cache, ground_truth, report = _workflow_inputs(tmp_path, calls)
    payload = json.loads(synonyms.read_bytes())
    payload["value"].append("newly reviewed amount phrase")
    synonyms.write_text(json.dumps(payload), encoding="utf-8")
    arguments = (
        [
            "query",
            "--catalog",
            str(catalog),
            "--synonyms",
            str(synonyms),
            "--cache-dir",
            str(cache),
            "--question",
            "transaction value",
        ]
        if command == "query"
        else _evaluate_arguments(catalog, synonyms, cache, ground_truth, report)
    )

    result = CliRunner().invoke(cli, arguments)

    assert result.exit_code != 0
    failure = json.loads(result.output)
    assert failure["status"] == "failed"
    assert "document" in failure["reason"] or "fingerprint" in failure["reason"]
    assert calls == []


def test_cli_uses_canonical_ground_truth_default_path() -> None:
    result = CliRunner().invoke(_cli([]), ["evaluate", "--help"])

    assert result.exit_code == 0
    assert "data/eval/schema_link_groundtruth.jsonl" in result.output
