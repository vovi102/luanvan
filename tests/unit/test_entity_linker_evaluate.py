"""Offline contracts for entity-linker evidence evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.linking.entity import EntityAlternative, EntityCorpus, EntityMatch, EntityTarget
from nl2sparql.linking.entity.evaluate import (
    EntityEvaluationError,
    GitProvenance,
    GroundTruthCase,
    GroundTruthDataset,
    GroundTruthMention,
    StageCount,
    _percentile,
    evaluate_linker,
    load_ground_truth,
)


def _target(target_id: str, *, owner: str | None, alias: str) -> EntityTarget:
    document = f"Target: {target_id}"
    return EntityTarget(
        target_id=target_id,
        target_kind="owner" if owner else "concept",
        owner=owner,
        addresses=(),
        primary_labels=(owner,) if owner else (),
        aliases=(alias,),
        categories=("exchange",) if owner else ("concept",),
        concept_classes=("ExchangeAccount",) if owner else ("Concept",),
        address_roles=(),
        description=f"Fixture target {target_id}.",
        document=document,
        document_sha256=hashlib.sha256(document.encode()).hexdigest(),
    )


@pytest.fixture
def corpus() -> EntityCorpus:
    targets = (
        _target("concept:dex", owner=None, alias="dex"),
        _target("owner:Binance", owner="Binance", alias="binance"),
        _target("owner:Kraken", owner="Kraken", alias="kraken"),
    )
    return EntityCorpus(
        targets=targets,
        targets_by_id={target.target_id: target for target in targets},
        phrase_targets={
            "binance": ("owner:Binance",),
            "dex": ("concept:dex",),
            "kraken": ("owner:Kraken",),
        },
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )


def _rows(count: int = 100) -> list[dict[str, object]]:
    return [
        {
            "id": f"case-{number:03d}",
            "question": f"Binance question {number}",
            "mentions": [
                {"span": "Binance", "span_offset": [0, 7], "target_id": "owner:Binance"}
            ],
        }
        for number in range(count)
    ]


def _write_cases(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _match(question: str, target_id: str, stage: str = "exact") -> EntityMatch:
    return EntityMatch(
        span="Binance",
        span_offset=(0, 7),
        target_id=target_id,
        target_kind="owner" if target_id.startswith("owner:") else "concept",
        owner="Binance" if target_id == "owner:Binance" else None,
        addresses=(),
        categories=(),
        concept_classes=(),
        stage=stage,
        confidence=1.0,
        alternatives=(),
        target_sha256="d" * 64,
    )


class FakeLinker:
    def __init__(self, corpus: EntityCorpus, handler) -> None:
        self.corpus = corpus
        self.index_manifest_sha256 = "e" * 64
        self.index_matrices_sha256 = "f" * 64
        self.handler = handler

    def link(self, question: str) -> tuple[EntityMatch, ...]:
        return self.handler(question)


def _dataset(tmp_path: Path, corpus: EntityCorpus) -> GroundTruthDataset:
    return load_ground_truth(_write_cases(tmp_path / "gt.jsonl", _rows()), corpus)


def _provenance() -> GitProvenance:
    return GitProvenance("1" * 40, False)


def test_ground_truth_requires_exactly_one_hundred_rows(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    with pytest.raises(EntityEvaluationError, match="exactly 100"):
        load_ground_truth(_write_cases(tmp_path / "gt.jsonl", _rows(99)), corpus)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda rows: [*rows[:-1], {**rows[-1], "id": rows[0]["id"]}], "duplicate ID"),
        (
            lambda rows: [*rows[:-1], {**rows[-1], "question": rows[0]["question"]}],
            "duplicate question",
        ),
        (
            lambda rows: [*rows[:-1], {**rows[-1], "mentions": rows[-1]["mentions"] * 2}],
            "duplicate mention",
        ),
        (
            lambda rows: [
                *rows[:-1],
                {
                    **rows[-1],
                    "mentions": [
                        rows[-1]["mentions"][0],
                        {"span": "nance", "span_offset": [2, 7], "target_id": "owner:Binance"},
                    ],
                },
            ],
            "overlap",
        ),
    ),
)
def test_ground_truth_rejects_invalid_rows_with_line_context(
    tmp_path: Path, corpus: EntityCorpus, mutate, message: str
) -> None:
    with pytest.raises(EntityEvaluationError, match=rf"line 100.*{message}"):
        load_ground_truth(_write_cases(tmp_path / "gt.jsonl", mutate(_rows())), corpus)


def test_ground_truth_rejects_duplicate_json_keys(tmp_path: Path, corpus: EntityCorpus) -> None:
    path = tmp_path / "gt.jsonl"
    path.write_text('{"id":"one","id":"two","question":"Binance","mentions":[]}\n')

    with pytest.raises(EntityEvaluationError, match=r"line 1.*duplicate JSON key"):
        load_ground_truth(path, corpus)


def test_ground_truth_dataset_hashes_exact_accepted_file_bytes(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    path = _write_cases(tmp_path / "gt.jsonl", _rows())
    dataset = load_ground_truth(path, corpus)

    assert dataset.ground_truth_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_public_contracts_validate_direct_instances_and_are_deeply_immutable(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    with pytest.raises(EntityEvaluationError, match="span_offset"):
        GroundTruthMention("Binance", [0, 7], "owner:Binance")  # type: ignore[arg-type]
    with pytest.raises(EntityEvaluationError, match="mentions"):
        GroundTruthCase("id", "Binance", ())
    with pytest.raises(EntityEvaluationError, match="git SHA"):
        GitProvenance("A" * 40, False)

    report = evaluate_linker(
        FakeLinker(corpus, lambda question: (_match(question, "owner:Binance"),)),
        _dataset(tmp_path, corpus),
        model_id="fake/model",
        git_provenance=_provenance(),
    )
    assert report.stage_counts == (StageCount("exact", 100),)
    assert report.stage_count_map == {"exact": 100}
    with pytest.raises(TypeError):
        report.stage_count_map["exact"] = 0  # type: ignore[index]
    serialized = json.dumps(asdict(report), sort_keys=True)
    assert "Binance question" not in serialized
    assert json.loads(serialized)["stage_counts"] == [{"count": 100, "stage": "exact"}]


def test_evaluator_requires_a_dataset_of_exactly_one_hundred_cases(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    dataset = _dataset(tmp_path, corpus)
    short_dataset = GroundTruthDataset(dataset.cases[:-1], dataset.ground_truth_sha256)

    with pytest.raises(EntityEvaluationError, match="exactly 100"):
        evaluate_linker(
            FakeLinker(corpus, lambda question: (_match(question, "owner:Binance"),)),
            short_dataset,
            model_id="fake/model",
            git_provenance=_provenance(),
        )


def test_evaluator_uses_span_only_mention_detection_and_primary_named_top1(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    ambiguous = EntityMatch(
        span="Binance",
        span_offset=(0, 7),
        target_id="concept:dex",
        target_kind="concept",
        owner=None,
        addresses=(),
        categories=(),
        concept_classes=(),
        stage="ambiguous",
        confidence=1.0,
        alternatives=(EntityAlternative("owner:Binance", "owner", 1.0),),
        target_sha256="d" * 64,
    )
    report = evaluate_linker(
        FakeLinker(corpus, lambda question: (ambiguous,)),
        _dataset(tmp_path, corpus),
        model_id="fake/model",
        git_provenance=_provenance(),
    )

    assert report.mention_precision == 1.0
    assert report.mention_recall == 1.0
    assert report.mention_f1 == 1.0
    assert report.named_entity_top1_accuracy == 0.0
    assert report.ready is False
    with pytest.raises(EntityEvaluationError, match="ready"):
        replace(report, ready=True)


@pytest.mark.parametrize(
    ("handler", "message"),
    (
        (
            lambda question: (_match(question, "owner:Binance"), _match(question, "owner:Kraken")),
            "duplicate prediction span",
        ),
        (
            lambda question: (
                _match(question, "owner:Binance"),
                EntityMatch(
                    span="nance q",
                    span_offset=(2, 9),
                    target_id="owner:Kraken",
                    target_kind="owner",
                    owner="Kraken",
                    addresses=(),
                    categories=(),
                    concept_classes=(),
                    stage="exact",
                    confidence=1.0,
                    alternatives=(),
                    target_sha256="d" * 64,
                ),
            ),
            "overlapping prediction spans",
        ),
    ),
)
def test_evaluator_rejects_duplicate_and_overlapping_predictions(
    tmp_path: Path, corpus: EntityCorpus, handler, message: str
) -> None:
    with pytest.raises(EntityEvaluationError, match=message):
        evaluate_linker(
            FakeLinker(corpus, handler),
            _dataset(tmp_path, corpus),
            model_id="fake/model",
            git_provenance=_provenance(),
        )


def test_readiness_has_exact_accuracy_boundary(tmp_path: Path, corpus: EntityCorpus) -> None:
    def at_least_85(question: str) -> tuple[EntityMatch, ...]:
        number = int(question.rsplit(" ", 1)[1])
        target = "owner:Binance" if number < 85 else "concept:dex"
        return (_match(question, target),)

    ready = evaluate_linker(
        FakeLinker(corpus, at_least_85),
        _dataset(tmp_path, corpus),
        model_id="fake/model",
        git_provenance=_provenance(),
    )
    assert ready.named_entity_top1_accuracy == pytest.approx(0.85)
    assert ready.ready is True
    with pytest.raises(EntityEvaluationError, match="ready"):
        replace(ready, ready=False)


def test_readiness_requires_p95_strictly_below_two_hundred_ms(
    tmp_path: Path, corpus: EntityCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nl2sparql.linking.entity import evaluate as evaluate_module

    ticks = iter(value for _ in range(100) for value in (0.0, 0.2))
    monkeypatch.setattr(evaluate_module, "perf_counter", lambda: next(ticks))
    report = evaluate_linker(
        FakeLinker(corpus, lambda question: (_match(question, "owner:Binance"),)),
        _dataset(tmp_path, corpus),
        model_id="fake/model",
        git_provenance=_provenance(),
    )

    assert report.warm_latency_p95_ms == pytest.approx(200.0)
    assert report.ready is False


def test_report_has_explicit_model_index_and_git_provenance(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    report = evaluate_linker(
        FakeLinker(corpus, lambda question: (_match(question, "owner:Binance"),)),
        _dataset(tmp_path, corpus),
        model_id="fake/model",
        git_provenance=GitProvenance("2" * 40, True),
    )

    assert report.model_id_sha256 == hashlib.sha256(b"fake/model").hexdigest()
    assert report.index_manifest_sha256 == "e" * 64
    assert report.index_matrices_sha256 == "f" * 64
    assert report.git_sha == "2" * 40
    assert report.git_worktree_dirty is True
    with pytest.raises(EntityEvaluationError, match="git provenance"):
        evaluate_linker(
            FakeLinker(corpus, lambda question: ()),
            _dataset(tmp_path, corpus),
            model_id="fake/model",
            git_provenance=None,
        )
    with pytest.raises(EntityEvaluationError, match="git provenance"):
        evaluate_linker(
            FakeLinker(corpus, lambda question: ()),
            _dataset(tmp_path, corpus),
            model_id="fake/model",
        )


def test_percentile_rejects_boolean_values_and_parameters() -> None:
    assert _percentile((10.0, 20.0, 30.0), 0.95) == pytest.approx(29.0)
    with pytest.raises(EntityEvaluationError, match="values"):
        _percentile((True,), 0.5)
    with pytest.raises(EntityEvaluationError, match="percentile"):
        _percentile((1.0,), True)


@pytest.mark.parametrize(
    ("content", "message"),
    (
        ("not-json\n", r"line 1.*JSON"),
        ("[]\n", r"line 1.*object"),
    ),
)
def test_ground_truth_rejects_malformed_json_and_non_object_rows(
    tmp_path: Path, corpus: EntityCorpus, content: str, message: str
) -> None:
    path = tmp_path / "gt.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(EntityEvaluationError, match=message):
        load_ground_truth(path, corpus)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda rows: [
                *rows[:-1],
                {**rows[-1], "mentions": [{**rows[-1]["mentions"][0], "span": "wrong"}]},
            ],
            "original question slice",
        ),
        (
            lambda rows: [
                *rows[:-1],
                {
                    **rows[-1],
                    "mentions": [{**rows[-1]["mentions"][0], "target_id": "owner:Unknown"}],
                },
            ],
            "unknown target",
        ),
        (
            lambda rows: [
                *rows[:-1],
                {
                    **rows[-1],
                    "mentions": [{**rows[-1]["mentions"][0], "target_id": "concept:dex"}],
                },
            ],
            "named-entity",
        ),
    ),
)
def test_ground_truth_rejects_invalid_slices_targets_and_owner_coverage(
    tmp_path: Path, corpus: EntityCorpus, mutate, message: str
) -> None:
    with pytest.raises(EntityEvaluationError, match=rf"line 100.*{message}"):
        load_ground_truth(_write_cases(tmp_path / "gt.jsonl", mutate(_rows())), corpus)


def test_evaluator_handles_zero_predictions_and_linker_failures(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    report = evaluate_linker(
        FakeLinker(corpus, lambda question: ()),
        _dataset(tmp_path, corpus),
        model_id="fake/model",
        git_provenance=_provenance(),
    )
    assert report.mention_precision == 0.0
    assert report.mention_recall == 0.0
    assert report.mention_f1 == 0.0
    assert report.stage_counts == ()

    class BrokenLinker(FakeLinker):
        def link(self, question: str) -> tuple[EntityMatch, ...]:
            raise RuntimeError("boom")

    with pytest.raises(EntityEvaluationError, match="linker failed"):
        evaluate_linker(
            BrokenLinker(corpus, lambda question: ()),
            _dataset(tmp_path, corpus),
            model_id="fake/model",
            git_provenance=_provenance(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (("target_ids", ("owner:Binance",)), ("target_document_sha256", ("0" * 64,))),
)
def test_evaluator_rejects_index_target_identity_disagreement(
    tmp_path: Path, corpus: EntityCorpus, field: str, value: tuple[str, ...]
) -> None:
    linker = FakeLinker(corpus, lambda question: (_match(question, "owner:Binance"),))
    metadata = SimpleNamespace(
        model_id="fake/model",
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
        manifest_sha256="e" * 64,
        matrices_sha256="f" * 64,
        target_ids=tuple(target.target_id for target in corpus.targets),
        target_document_sha256=tuple(target.document_sha256 for target in corpus.targets),
    )
    setattr(metadata, field, value)
    linker._index = SimpleNamespace(metadata=metadata)

    with pytest.raises(EntityEvaluationError, match=field):
        evaluate_linker(
            linker,
            _dataset(tmp_path, corpus),
            model_id="fake/model",
            git_provenance=_provenance(),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("model_id", "other/model", "model ID"),
        ("entities_sha256", "0" * 64, "entities_sha256"),
        ("aliases_sha256", "0" * 64, "aliases_sha256"),
        ("concepts_sha256", "0" * 64, "concepts_sha256"),
    ),
)
def test_evaluator_rejects_index_model_and_dictionary_disagreement(
    tmp_path: Path, corpus: EntityCorpus, field: str, value: str, message: str
) -> None:
    linker = FakeLinker(corpus, lambda question: (_match(question, "owner:Binance"),))
    metadata = SimpleNamespace(
        model_id="fake/model",
        entities_sha256=corpus.entities_sha256,
        aliases_sha256=corpus.aliases_sha256,
        concepts_sha256=corpus.concepts_sha256,
        manifest_sha256="e" * 64,
        matrices_sha256="f" * 64,
        target_ids=tuple(target.target_id for target in corpus.targets),
        target_document_sha256=tuple(target.document_sha256 for target in corpus.targets),
    )
    setattr(metadata, field, value)
    linker._index = SimpleNamespace(metadata=metadata)

    with pytest.raises(EntityEvaluationError, match=message):
        evaluate_linker(
            linker,
            _dataset(tmp_path, corpus),
            model_id="fake/model",
            git_provenance=_provenance(),
        )
