"""Offline contracts for entity-linker evidence evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl2sparql.linking.entity import EntityCorpus, EntityMatch, EntityTarget
from nl2sparql.linking.entity.evaluate import (
    EntityEvaluationError,
    GroundTruthCase,
    GroundTruthMention,
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
                {
                    "span": "Binance",
                    "span_offset": [0, 7],
                    "target_id": "owner:Binance",
                }
            ],
        }
        for number in range(count)
    ]


def _write_cases(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _match(question: str, target_id: str, stage: str = "exact") -> EntityMatch:
    start = question.index("Binance")
    target_kind = "owner" if target_id.startswith("owner:") else "concept"
    return EntityMatch(
        span="Binance",
        span_offset=(start, start + 7),
        target_id=target_id,
        target_kind=target_kind,
        owner="Binance" if target_kind == "owner" else None,
        addresses=(),
        categories=(),
        concept_classes=(),
        stage=stage,
        confidence=1.0,
        alternatives=(),
        target_sha256="d" * 64,
    )


class FakeLinker:
    def __init__(self, corpus: EntityCorpus, answers: dict[str, tuple[EntityMatch, ...]]) -> None:
        self.corpus = corpus
        self.index_sha256 = "e" * 64
        self.answers = answers
        self.calls: list[str] = []

    def link(self, question: str) -> tuple[EntityMatch, ...]:
        self.calls.append(question)
        return self.answers[question]


def test_ground_truth_requires_exactly_one_hundred_rows(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    path = _write_cases(tmp_path / "gt.jsonl", _rows(99))

    with pytest.raises(EntityEvaluationError, match="exactly 100"):
        load_ground_truth(path, corpus)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda rows: [*rows[:-1], {**rows[-1], "id": rows[0]["id"]}], "duplicate ID"),
        (
            (
                lambda rows: [
                    *rows[:-1],
                    {**rows[-1], "question": rows[0]["question"]},
                ]
            ),
            "duplicate question",
        ),
        (
            (
                lambda rows: [
                    *rows[:-1],
                    {**rows[-1], "mentions": rows[-1]["mentions"] * 2},
                ]
            ),
            "duplicate mention",
        ),
        (
            (
                lambda rows: [
                    *rows[:-1],
                    {
                        **rows[-1],
                        "mentions": [
                            rows[-1]["mentions"][0],
                            {
                                "span": "nance",
                                "span_offset": [2, 7],
                                "target_id": "owner:Binance",
                            },
                        ],
                    },
                ]
            ),
            "overlap",
        ),
        (
            (
                lambda rows: [
                    *rows[:-1],
                    {
                        **rows[-1],
                        "mentions": [
                            {
                                **rows[-1]["mentions"][0],
                                "span": "wrong",
                            }
                        ],
                    },
                ]
            ),
            "slice",
        ),
        (
            (
                lambda rows: [
                    *rows[:-1],
                    {
                        **rows[-1],
                        "mentions": [
                            {
                                **rows[-1]["mentions"][0],
                                "target_id": "owner:Unknown",
                            }
                        ],
                    },
                ]
            ),
            "unknown target",
        ),
        (
            (
                lambda rows: [
                    *rows[:-1],
                    {
                        **rows[-1],
                        "mentions": [
                            {
                                **rows[-1]["mentions"][0],
                                "target_id": "concept:dex",
                            }
                        ],
                    },
                ]
            ),
            "named-entity",
        ),
    ),
)
def test_ground_truth_rejects_invalid_rows_with_line_context(
    tmp_path: Path, corpus: EntityCorpus, mutate, message: str
) -> None:
    path = _write_cases(tmp_path / "gt.jsonl", mutate(_rows()))

    with pytest.raises(EntityEvaluationError, match=rf"line 100.*{message}"):
        load_ground_truth(path, corpus)


def test_ground_truth_rejects_malformed_json_and_non_object_rows(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    path = tmp_path / "gt.jsonl"
    path.write_text(json.dumps(_rows()[0]) + "\nnot-json\n", encoding="utf-8")

    with pytest.raises(EntityEvaluationError, match=r"line 2.*JSON"):
        load_ground_truth(path, corpus)

    path.write_text("\n".join(json.dumps(row) for row in [*_rows()[:-1], []]), encoding="utf-8")
    with pytest.raises(EntityEvaluationError, match=r"line 100.*object"):
        load_ground_truth(path, corpus)


def test_load_ground_truth_returns_immutable_typed_cases(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    cases = load_ground_truth(_write_cases(tmp_path / "gt.jsonl", _rows()), corpus)

    assert cases[0] == GroundTruthCase(
        id="case-000",
        question="Binance question 0",
        mentions=(GroundTruthMention("Binance", (0, 7), "owner:Binance"),),
    )
    assert isinstance(cases, tuple)


def test_evaluator_computes_top1_mention_metrics_stages_and_warm_latency(
    corpus: EntityCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = (
        GroundTruthCase(
            "one", "Binance one", (GroundTruthMention("Binance", (0, 7), "owner:Binance"),)
        ),
        GroundTruthCase(
            "two", "Binance two", (GroundTruthMention("Binance", (0, 7), "owner:Binance"),)
        ),
    )
    linker = FakeLinker(
        corpus,
        {
            "Binance one": (_match("Binance one", "owner:Binance", "exact"),),
            "Binance two": (_match("Binance two", "concept:dex", "embedding"),),
        },
    )
    from nl2sparql.linking.entity import evaluate as evaluate_module

    ticks = iter((10.0, 10.010, 20.0, 20.030))
    monkeypatch.setattr(evaluate_module, "perf_counter", lambda: next(ticks))

    report = evaluate_linker(linker, cases, model_id="fake/model", git_sha="f" * 40)

    assert linker.calls == ["Binance one", "Binance one", "Binance two"]
    assert report.named_entity_top1_accuracy == pytest.approx(0.5)
    assert report.mention_precision == pytest.approx(0.5)
    assert report.mention_recall == pytest.approx(0.5)
    assert report.mention_f1 == pytest.approx(0.5)
    assert report.stage_counts == {"embedding": 1, "exact": 1}
    assert report.warm_latency_p50_ms == pytest.approx(20.0)
    assert report.warm_latency_p95_ms == pytest.approx(29.0)
    assert report.ready is False
    assert "Binance one" not in repr(report)
    assert report.entities_sha256 == "a" * 64
    assert report.index_sha256 == "e" * 64
    assert report.model_sha256 == hashlib.sha256(b"fake/model").hexdigest()
    assert report.git_sha == "f" * 40


def test_evaluator_counts_duplicate_predictions_as_false_positives(corpus: EntityCorpus) -> None:
    case = GroundTruthCase(
        "one", "Binance one", (GroundTruthMention("Binance", (0, 7), "owner:Binance"),)
    )
    linker = FakeLinker(corpus, {"Binance one": (_match("Binance one", "owner:Binance"),) * 2})

    report = evaluate_linker(linker, (case,), model_id="fake/model", git_sha="f" * 40)

    assert report.mention_precision == pytest.approx(0.5)
    assert report.mention_recall == pytest.approx(1.0)
    assert report.mention_f1 == pytest.approx(2 / 3)


def test_evaluator_handles_zero_match_divisions_and_linker_failures(corpus: EntityCorpus) -> None:
    case = GroundTruthCase(
        "one", "Binance one", (GroundTruthMention("Binance", (0, 7), "owner:Binance"),)
    )
    report = evaluate_linker(
        FakeLinker(corpus, {"Binance one": ()}),
        (case,),
        model_id="fake/model",
        git_sha="f" * 40,
    )
    assert report.mention_precision == 0.0
    assert report.mention_recall == 0.0
    assert report.mention_f1 == 0.0

    class BrokenLinker(FakeLinker):
        def link(self, question: str) -> tuple[EntityMatch, ...]:
            raise RuntimeError("boom")

    with pytest.raises(EntityEvaluationError, match="linker failed"):
        evaluate_linker(BrokenLinker(corpus, {}), (case,), model_id="fake/model", git_sha="f" * 40)


def test_percentile_uses_linear_interpolation_and_rejects_invalid_inputs() -> None:
    assert _percentile((10.0, 20.0, 30.0), 0.95) == pytest.approx(29.0)
    with pytest.raises(EntityEvaluationError, match="values"):
        _percentile((), 0.5)
    with pytest.raises(EntityEvaluationError, match="percentile"):
        _percentile((1.0,), 1.1)


def test_evaluator_rejects_invalid_provenance(corpus: EntityCorpus) -> None:
    case = GroundTruthCase(
        "one", "Binance one", (GroundTruthMention("Binance", (0, 7), "owner:Binance"),)
    )
    linker = FakeLinker(corpus, {"Binance one": (_match("Binance one", "owner:Binance"),)})
    linker.index_sha256 = "not-a-digest"

    with pytest.raises(EntityEvaluationError, match="index hash"):
        evaluate_linker(linker, (case,), model_id="fake/model", git_sha="f" * 40)
    with pytest.raises(EntityEvaluationError, match="git SHA"):
        evaluate_linker(
            FakeLinker(corpus, {"Binance one": ()}),
            (case,),
            model_id="fake/model",
            git_sha="F" * 40,
        )


def test_evaluator_rejects_index_provenance_that_disagrees_with_the_corpus(
    corpus: EntityCorpus,
) -> None:
    case = GroundTruthCase(
        "one", "Binance one", (GroundTruthMention("Binance", (0, 7), "owner:Binance"),)
    )
    linker = FakeLinker(corpus, {"Binance one": (_match("Binance one", "owner:Binance"),)})
    linker._index = SimpleNamespace(
        metadata=SimpleNamespace(
            model_id="different/model",
            entities_sha256=corpus.entities_sha256,
            aliases_sha256=corpus.aliases_sha256,
            concepts_sha256=corpus.concepts_sha256,
            manifest_sha256="e" * 64,
        )
    )
    del linker.index_sha256

    with pytest.raises(EntityEvaluationError, match="model ID"):
        evaluate_linker(linker, (case,), model_id="fake/model", git_sha="f" * 40)
