from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from nl2sparql.models.b12 import FewShotRetriever, SmallLLMError

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"
ENCODER_ID = "sentence-transformers/all-MiniLM-L6-v2"
ENCODER_REVISION = "b" * 40


class TableEncoder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls = 0

    def encode(self, sentences, *, normalize_embeddings=True):
        assert normalize_embeddings is True
        self.calls += 1
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        return np.asarray([self.vectors[text] for text in texts], dtype=np.float64)


class BrokenEncoder:
    def __init__(self, output: object) -> None:
        self.output = output

    def encode(self, sentences, *, normalize_embeddings=True):
        return self.output


def _rows(count: int = 7) -> list[dict[str, object]]:
    return [
        {
            "id": f"train-{index:03d}",
            "nl": f"question {index}",
            "sql": SAFE_SQL,
            "split": "train",
            "synthetic_fixture": False,
        }
        for index in range(1, count + 1)
    ]


def _write_rows(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _vectors(count: int = 7) -> dict[str, list[float]]:
    values = {"target": [1.0, 0.0], "same question": [1.0, 0.0]}
    values.update(
        {
            f"question {index}": [1.0, 0.0] if index <= 2 else [1.0, float(index)]
            for index in range(1, count + 1)
        }
    )
    return values


def _retriever(
    tmp_path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
    encoder: object | None = None,
    cache: bool = False,
) -> tuple[FewShotRetriever, Path, object]:
    selected_rows = rows or _rows()
    snapshot = _write_rows(tmp_path / "train.jsonl", selected_rows)
    selected_encoder = encoder or TableEncoder(_vectors(len(selected_rows)))
    retriever = FewShotRetriever.from_snapshot(
        snapshot,
        encoder=selected_encoder,
        encoder_id=ENCODER_ID,
        encoder_revision=ENCODER_REVISION,
        cache_path=tmp_path / "few-shot.npz" if cache else None,
    )
    return retriever, snapshot, selected_encoder


def test_retrieval_is_score_then_id_deterministic(tmp_path: Path) -> None:
    retriever, _, _ = _retriever(tmp_path)

    selected = retriever.retrieve("target")

    assert [item.record_id for item in selected] == [
        "train-001",
        "train-002",
        "train-003",
        "train-004",
        "train-005",
    ]
    assert selected[0].score == pytest.approx(1.0)
    assert selected[1].score == pytest.approx(1.0)


def test_retrieval_excludes_same_id_and_normalized_question(tmp_path: Path) -> None:
    rows = _rows(8)
    rows[1]["nl"] = "Same question"
    vectors = _vectors(8)
    vectors.pop("question 2")
    vectors["Same question"] = [1.0, 0.0]
    vectors["Ｓａｍｅ   QUESTION"] = [1.0, 0.0]
    retriever, _, _ = _retriever(tmp_path, rows=rows, encoder=TableEncoder(vectors))

    selected = retriever.retrieve("Ｓａｍｅ   QUESTION", target_id="train-001")

    assert len(selected) == 5
    assert all(item.record_id not in {"train-001", "train-002"} for item in selected)


def test_training_fingerprint_uses_exact_snapshot_bytes(tmp_path: Path) -> None:
    retriever, snapshot, _ = _retriever(tmp_path)

    assert retriever.training_sha256 == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert retriever.encoder_id == ENCODER_ID
    assert retriever.encoder_revision == ENCODER_REVISION


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: rows + [dict(rows[0])], "duplicate ID"),
        (lambda rows: rows[:-1] + [{**rows[-1], "nl": " QUESTION 1 "}], "duplicate question"),
        (lambda rows: [{**rows[0], "split": "test"}, *rows[1:]], "split"),
        (lambda rows: [{**rows[0], "synthetic_fixture": True}, *rows[1:]], "synthetic"),
        (lambda rows: [{**rows[0], "sql": "DELETE FROM x"}, *rows[1:]], "SQL"),
    ],
)
def test_snapshot_contract_fails_closed(tmp_path: Path, mutate, message: str) -> None:
    rows = mutate(_rows())
    snapshot = _write_rows(tmp_path / "train.jsonl", rows)

    with pytest.raises(SmallLLMError, match=message):
        FewShotRetriever.from_snapshot(
            snapshot,
            encoder=TableEncoder(_vectors()),
            encoder_id=ENCODER_ID,
            encoder_revision=ENCODER_REVISION,
        )


def test_retrieval_requires_five_eligible_examples(tmp_path: Path) -> None:
    retriever, _, _ = _retriever(tmp_path, rows=_rows(5), encoder=TableEncoder(_vectors(5)))

    with pytest.raises(SmallLLMError, match="five eligible"):
        retriever.retrieve("question 1", target_id="train-002")


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (np.ones((6, 2)), "row count"),
        (np.asarray([[np.nan, 1.0]] * 7), "finite"),
        (np.zeros((7, 2)), "non-zero"),
        (np.ones(7), "two-dimensional"),
    ],
)
def test_encoder_output_is_validated(tmp_path: Path, output: object, message: str) -> None:
    snapshot = _write_rows(tmp_path / "train.jsonl", _rows())

    with pytest.raises(SmallLLMError, match=message):
        FewShotRetriever.from_snapshot(
            snapshot,
            encoder=BrokenEncoder(output),
            encoder_id=ENCODER_ID,
            encoder_revision=ENCODER_REVISION,
        )


def test_valid_cache_can_preflight_without_encoder(tmp_path: Path) -> None:
    built, snapshot, encoder = _retriever(tmp_path, cache=True)
    calls_after_build = encoder.calls

    loaded = FewShotRetriever.from_snapshot(
        snapshot,
        encoder=None,
        encoder_id=ENCODER_ID,
        encoder_revision=ENCODER_REVISION,
        cache_path=tmp_path / "few-shot.npz",
    )

    assert loaded.training_sha256 == built.training_sha256
    assert encoder.calls == calls_after_build
    with pytest.raises(SmallLLMError, match="query encoder unavailable"):
        loaded.retrieve("target")


def test_tampered_cache_is_rejected_without_encoder(tmp_path: Path) -> None:
    _, snapshot, _ = _retriever(tmp_path, cache=True)
    cache_path = tmp_path / "few-shot.npz"
    cache_path.write_bytes(cache_path.read_bytes() + b"tampered")

    with pytest.raises(SmallLLMError, match="cache.*encoder unavailable"):
        FewShotRetriever.from_snapshot(
            snapshot,
            encoder=None,
            encoder_id=ENCODER_ID,
            encoder_revision=ENCODER_REVISION,
            cache_path=cache_path,
        )


def test_stale_cache_is_rebuilt_when_encoder_is_available(tmp_path: Path) -> None:
    _, snapshot, _ = _retriever(tmp_path, cache=True)
    metadata_path = tmp_path / "few-shot.npz.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["training_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    encoder = TableEncoder(_vectors())

    rebuilt = FewShotRetriever.from_snapshot(
        snapshot,
        encoder=encoder,
        encoder_id=ENCODER_ID,
        encoder_revision=ENCODER_REVISION,
        cache_path=tmp_path / "few-shot.npz",
    )

    assert encoder.calls == 1
    assert rebuilt.training_sha256 == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_cache_path_cannot_alias_training_snapshot(tmp_path: Path) -> None:
    snapshot = _write_rows(tmp_path / "train.jsonl", _rows())

    with pytest.raises(SmallLLMError, match="alias"):
        FewShotRetriever.from_snapshot(
            snapshot,
            encoder=TableEncoder(_vectors()),
            encoder_id=ENCODER_ID,
            encoder_revision=ENCODER_REVISION,
            cache_path=snapshot,
        )
