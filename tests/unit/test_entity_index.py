"""Tests for durable, content-addressed entity embedding indexes."""

from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import numpy as np
import pytest

from nl2sparql.linking.entity import (
    DEFAULT_LINKER_POLICY,
    EntityCachePaths,
    EntityCorpus,
    EntityEncoderUnavailableError,
    EntityIndexError,
    EntityLinkerPolicy,
    EntityTarget,
    build_index,
    load_index,
)
from nl2sparql.linking.entity import index as index_module

MODEL_ID = "fake/model"


class FakeEncoder:
    """Small deterministic encoder that mirrors the production boundary."""

    def encode(self, sentences, *, normalize_embeddings=True):
        assert normalize_embeddings is True
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        rows = np.asarray(
            [[float(len(text)), float(text.count("Owner")), 1.0] for text in texts],
            dtype=np.float64,
        )
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


class AlternateEncoder(FakeEncoder):
    def encode(self, sentences, *, normalize_embeddings=True):
        return super().encode(sentences, normalize_embeddings=normalize_embeddings)[:, ::-1]


class BrokenEncoder:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def encode(self, sentences, *, normalize_embeddings=True):
        count = len(list(sentences))
        if self.mode == "wrong_rows":
            count += 1
        if self.mode == "rank":
            return np.ones(count, dtype=np.float64)
        if self.mode == "non_numeric":
            return [["not a number"]] * count
        rows = np.ones((count, 3), dtype=np.float64)
        if self.mode not in {"unnormalized", "nan", "infinite"}:
            rows /= np.linalg.norm(rows, axis=1, keepdims=True)
        if self.mode == "nan":
            rows[0, 0] = np.nan
        if self.mode == "infinite":
            rows[0, 0] = np.inf
        return rows


class SimulatedCrash(BaseException):
    pass


def _target(target_id: str, owner: str) -> EntityTarget:
    document = f"Owner: {owner}"
    return EntityTarget(
        target_id=target_id,
        target_kind="owner",
        owner=owner,
        addresses=(),
        primary_labels=(owner,),
        aliases=(owner.casefold(),),
        categories=("exchange",),
        concept_classes=("ExchangeAccount",),
        address_roles=(),
        description=f"Ethereum owner target {owner}.",
        document=document,
        document_sha256=hashlib.sha256(document.encode()).hexdigest(),
    )


@pytest.fixture
def corpus() -> EntityCorpus:
    targets = (_target("owner:Alpha", "Alpha"), _target("owner:Beta", "Beta"))
    return EntityCorpus(
        targets=targets,
        targets_by_id={target.target_id: target for target in targets},
        phrase_targets={target.aliases[0]: (target.target_id,) for target in targets},
        address_targets={},
        entities_sha256="a" * 64,
        aliases_sha256="b" * 64,
        concepts_sha256="c" * 64,
    )


@pytest.fixture
def changed_corpus(corpus: EntityCorpus) -> EntityCorpus:
    return replace(corpus, aliases_sha256="d" * 64)


def _matrix_path(paths: EntityCachePaths) -> Path:
    payload = json.loads(paths.manifest.read_bytes())
    return paths.manifest.parent / payload["matrices_file"]


def _rewrite_manifest(path: Path, payload: dict[str, object]) -> None:
    body = dict(payload)
    body.pop("manifest_sha256", None)
    canonical = (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
    body["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def _publish_test_matrix(paths: EntityCachePaths, matrix: np.ndarray) -> None:
    payload = json.loads(paths.manifest.read_bytes())
    buffer = io.BytesIO()
    np.savez_compressed(buffer, target_embeddings=matrix)
    matrix_bytes = buffer.getvalue()
    digest = hashlib.sha256(matrix_bytes).hexdigest()
    paths.matrix_generation(digest).write_bytes(matrix_bytes)
    payload["matrices_sha256"] = digest
    payload["matrices_file"] = paths.matrix_generation(digest).name
    _rewrite_manifest(paths.manifest, payload)


def test_build_and_load_entity_index_uses_content_addressed_generation(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)

    built = build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    loaded = load_index(paths, corpus, model_id=MODEL_ID)

    assert built.metadata.matrices_file == f"entity-index-{built.metadata.matrices_sha256}.npz"
    assert loaded.metadata.target_ids == tuple(target.target_id for target in corpus.targets)
    assert loaded.target_embeddings.dtype == np.float32
    assert loaded.target_embeddings.flags.writeable is False
    np.testing.assert_array_equal(loaded.target_embeddings, built.target_embeddings)
    assert not paths.matrices.exists()
    assert _matrix_path(paths).is_file()
    assert not list(tmp_path.glob("*.tmp"))


def test_index_manifest_binds_the_shared_linker_policy(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)

    built = build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    payload = json.loads(paths.manifest.read_bytes())

    assert payload["fuzzy_threshold"] == DEFAULT_LINKER_POLICY.fuzzy_threshold
    assert payload["embedding_threshold"] == DEFAULT_LINKER_POLICY.embedding_threshold
    assert payload["ambiguity_margin"] == DEFAULT_LINKER_POLICY.ambiguity_margin
    assert built.metadata.linker_policy == DEFAULT_LINKER_POLICY


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("fuzzy_threshold", None),
        ("embedding_threshold", True),
        ("ambiguity_margin", "0.03"),
        ("fuzzy_threshold", float("nan")),
        ("embedding_threshold", float("inf")),
        ("ambiguity_margin", -0.01),
        ("fuzzy_threshold", 0.0),
        ("embedding_threshold", 1.01),
        ("ambiguity_margin", 1.0),
    ),
)
def test_strict_load_rejects_missing_or_invalid_persisted_linker_policy(
    tmp_path: Path, corpus: EntityCorpus, field: str, invalid: object
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    payload = json.loads(paths.manifest.read_bytes())
    if invalid is None:
        payload.pop(field)
    else:
        payload[field] = invalid
    _rewrite_manifest(paths.manifest, payload)

    with pytest.raises(EntityIndexError, match="policy"):
        load_index(paths, corpus, model_id=MODEL_ID)


def test_strict_load_rejects_an_effective_linker_policy_mismatch(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    policy = EntityLinkerPolicy(0.86, 0.75, 0.03)
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID, linker_policy=policy)

    with pytest.raises(EntityIndexError, match="policy"):
        load_index(paths, corpus, model_id=MODEL_ID, linker_policy=DEFAULT_LINKER_POLICY)

    loaded = load_index(paths, corpus, model_id=MODEL_ID, linker_policy=policy)

    assert loaded.metadata.linker_policy == policy


def test_load_rejects_stale_dictionary_hash(
    tmp_path: Path, corpus: EntityCorpus, changed_corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)

    with pytest.raises(EntityIndexError, match="dictionary"):
        load_index(paths, changed_corpus, model_id=MODEL_ID)


def test_load_rejects_digest_tamper_and_current_document_tamper(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    built = build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    original_manifest = paths.manifest.read_bytes()

    payload = json.loads(original_manifest)
    payload["manifest_sha256"] = "0" * 64
    paths.manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EntityIndexError, match="manifest digest"):
        load_index(paths, corpus, model_id=MODEL_ID)

    paths.manifest.write_bytes(original_manifest)
    with _matrix_path(paths).open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(EntityIndexError, match="matrix digest"):
        load_index(paths, corpus, model_id=MODEL_ID)

    paths = EntityCachePaths.from_directory(tmp_path / "documents")
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    changed_target = replace(
        corpus.targets[0],
        document="Owner: Altered",
        document_sha256=hashlib.sha256(b"Owner: Altered").hexdigest(),
    )
    changed = replace(
        corpus,
        targets=(changed_target, corpus.targets[1]),
        targets_by_id={
            changed_target.target_id: changed_target,
            corpus.targets[1].target_id: corpus.targets[1],
        },
    )
    with pytest.raises(EntityIndexError, match="current document"):
        load_index(paths, changed, model_id=MODEL_ID)
    assert built.metadata.matrices_sha256


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("unnormalized", "normalized"),
        ("nan", "finite"),
        ("infinite", "finite"),
        ("wrong_rows", "row count"),
        ("rank", "row count or rank"),
        ("non_numeric", "numeric"),
    ),
)
def test_build_rejects_invalid_encoder_vectors_without_publishing(
    tmp_path: Path, corpus: EntityCorpus, mode: str, message: str
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)

    with pytest.raises(EntityIndexError, match=message):
        build_index(corpus, BrokenEncoder(mode), paths, model_id=MODEL_ID)

    assert not paths.manifest.exists()
    assert not list(tmp_path.glob("entity-index-*.npz"))


@pytest.mark.parametrize("error", (httpx.ConnectError("offline"), httpx.ReadTimeout("slow")))
def test_build_marks_encoder_transport_failures_unavailable(
    tmp_path: Path, corpus: EntityCorpus, error: Exception
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)

    class TransportFailingEncoder:
        def encode(self, sentences, *, normalize_embeddings=True):
            raise error

    with pytest.raises(EntityEncoderUnavailableError, match="unavailable"):
        build_index(corpus, TransportFailingEncoder(), paths, model_id=MODEL_ID)

    assert not paths.manifest.exists()


def test_load_rejects_traversal_symlink_and_hardlink_aliases(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    built = build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    original_manifest = paths.manifest.read_bytes()
    generation = _matrix_path(paths)

    payload = json.loads(original_manifest)
    payload["matrices_file"] = f"../entity-index-{payload['matrices_sha256']}.npz"
    _rewrite_manifest(paths.manifest, payload)
    with pytest.raises(EntityIndexError, match="filename"):
        load_index(paths, corpus, model_id=MODEL_ID)

    paths.manifest.write_bytes(original_manifest)
    saved = tmp_path / "saved-generation.npz"
    generation.rename(saved)
    generation.symlink_to(saved)
    with pytest.raises(EntityIndexError, match="alias"):
        load_index(paths, corpus, model_id=MODEL_ID)

    generation.unlink()
    os.link(saved, generation)
    with pytest.raises(EntityIndexError, match="alias"):
        load_index(paths, corpus, model_id=MODEL_ID)
    assert built.metadata.matrices_file


def test_load_rejects_symlink_and_hardlink_manifest_aliases(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    saved_manifest = tmp_path / "saved-manifest.json"
    paths.manifest.rename(saved_manifest)
    paths.manifest.symlink_to(saved_manifest)

    with pytest.raises(EntityIndexError, match="manifest.*alias"):
        load_index(paths, corpus, model_id=MODEL_ID)

    paths.manifest.unlink()
    os.link(saved_manifest, paths.manifest)
    with pytest.raises(EntityIndexError, match="manifest.*alias"):
        load_index(paths, corpus, model_id=MODEL_ID)


def test_strict_load_does_not_recreate_lock_deleted_before_open(
    tmp_path: Path, corpus: EntityCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    original_lock = index_module._index_lock

    @contextmanager
    def delete_then_open(path: Path, **kwargs):
        path.unlink()
        with original_lock(path, **kwargs):
            yield

    monkeypatch.setattr(index_module, "_index_lock", delete_then_open)

    with pytest.raises(EntityIndexError, match="lock"):
        load_index(paths, corpus, model_id=MODEL_ID)

    assert not paths.lock.exists()


@pytest.mark.parametrize(
    ("matrix", "message"),
    (
        (np.ones((2, 3), dtype=np.float32), "normalized"),
        (np.asarray([[np.nan, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32), "finite"),
        (np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64), "float32"),
    ),
)
def test_load_rejects_self_consistent_malformed_persisted_vectors(
    tmp_path: Path, corpus: EntityCorpus, matrix: np.ndarray, message: str
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    _publish_test_matrix(paths, matrix)

    with pytest.raises(EntityIndexError, match=message):
        load_index(paths, corpus, model_id=MODEL_ID)


def test_build_rejects_future_generation_symlink_or_hardlink_alias(
    tmp_path: Path, corpus: EntityCorpus
) -> None:
    source_paths = EntityCachePaths.from_directory(tmp_path / "source")
    baseline = build_index(corpus, AlternateEncoder(), source_paths, model_id=MODEL_ID)
    source_generation = _matrix_path(source_paths)
    target_paths = EntityCachePaths.from_directory(tmp_path / "target")
    target_paths.manifest.parent.mkdir()
    future = target_paths.matrix_generation(baseline.metadata.matrices_sha256)

    future.symlink_to(source_generation)
    with pytest.raises(EntityIndexError, match="alias"):
        build_index(corpus, AlternateEncoder(), target_paths, model_id=MODEL_ID)

    future.unlink()
    os.link(source_generation, future)
    with pytest.raises(EntityIndexError, match="alias"):
        build_index(corpus, AlternateEncoder(), target_paths, model_id=MODEL_ID)
    assert not target_paths.manifest.exists()


@pytest.mark.parametrize(
    ("crash_point", "manifest_exists"),
    (("matrix_generation_durable", False), ("manifest_durable", True)),
)
def test_publication_failures_before_and_after_manifest_switch_are_recoverable(
    tmp_path: Path,
    corpus: EntityCorpus,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
    manifest_exists: bool,
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)

    def crash(point: str) -> None:
        if point == crash_point:
            raise SimulatedCrash(point)

    monkeypatch.setattr(index_module, "_publication_checkpoint", crash)
    with pytest.raises(SimulatedCrash):
        build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)

    assert paths.manifest.exists() is manifest_exists
    assert len(list(tmp_path.glob("entity-index-*.npz"))) == 1
    if manifest_exists:
        assert (
            load_index(paths, corpus, model_id=MODEL_ID).metadata.matrices_file
            == _matrix_path(paths).name
        )


@pytest.mark.parametrize("crash_point", ("matrix_generation_durable", "manifest_durable"))
def test_interrupted_rebuild_preserves_a_readable_accepted_generation(
    tmp_path: Path,
    corpus: EntityCorpus,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    paths = EntityCachePaths.from_directory(tmp_path)
    accepted = build_index(corpus, FakeEncoder(), paths, model_id=MODEL_ID)
    old_manifest = paths.manifest.read_bytes()
    old_generation = _matrix_path(paths)

    def crash(point: str) -> None:
        if point == crash_point:
            raise SimulatedCrash(point)

    monkeypatch.setattr(index_module, "_publication_checkpoint", crash)
    with pytest.raises(SimulatedCrash):
        build_index(corpus, AlternateEncoder(), paths, model_id=MODEL_ID)

    loaded = load_index(paths, corpus, model_id=MODEL_ID)
    assert old_generation.is_file()
    assert len(list(tmp_path.glob("entity-index-*.npz"))) == 2
    if crash_point == "matrix_generation_durable":
        assert paths.manifest.read_bytes() == old_manifest
        assert loaded.metadata.matrices_sha256 == accepted.metadata.matrices_sha256
    else:
        assert loaded.metadata.matrices_sha256 != accepted.metadata.matrices_sha256
