"""Tests for safe, fingerprinted schema-index publication and loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from nl2sparql.linking.schema import (
    DOCUMENT_VERSION,
    SchemaCachePaths,
    SchemaIndexError,
    build_index,
    build_schema_elements,
    load_index,
    load_synonyms,
)
from nl2sparql.linking.schema import index as index_module
from nl2sparql.sql.schema import CATALOG_PATH, load_catalog

MODEL_ID = "test/deterministic-encoder"


def _rewrite_manifest(path: Path, payload: dict[str, object]) -> None:
    body = dict(payload)
    body.pop("manifest_sha256", None)
    canonical = (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
    body["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


class FakeEncoder:
    """Small deterministic encoder that mirrors the production array boundary."""

    def encode(self, sentences, *, normalize_embeddings=True):
        assert normalize_embeddings is True
        texts = [sentences] if isinstance(sentences, str) else list(sentences)
        rows = np.asarray(
            [[float(len(text)), float(text.count("address")), 1.0] for text in texts],
            dtype=np.float64,
        )
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


class BrokenEncoder:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls = 0

    def encode(self, sentences, *, normalize_embeddings=True):
        self.calls += 1
        count = len(list(sentences))
        if self.mode == "wrong_rows":
            count += 1
        dimension = 4 if self.mode == "second_dimension" and self.calls == 2 else 3
        rows = np.ones((count, dimension), dtype=np.float64)
        if self.mode == "nan":
            rows[0, 0] = np.nan
        if self.mode != "unnormalized":
            rows /= np.linalg.norm(rows, axis=1, keepdims=True)
        return rows


def _inputs(tmp_path: Path):
    elements = build_schema_elements(load_catalog(), load_synonyms())
    return elements, CATALOG_PATH.read_bytes(), SchemaCachePaths.from_directory(tmp_path)


def test_build_and_load_index_preserves_order_and_validated_float32_matrices(
    tmp_path: Path,
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)

    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    loaded = load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)

    assert [row.element_id for row in loaded.metadata.relation_elements] == [
        "block_facts",
        "contract_dimension",
        "entity_labels_v1",
        "token_dimension",
        "token_transfer_facts",
        "transaction_facts",
    ]
    assert len(loaded.metadata.field_elements) == 62
    assert loaded.relation_embeddings.shape == (6, 3)
    assert loaded.field_embeddings.shape == (62, 3)
    assert loaded.relation_embeddings.dtype == np.float32
    assert loaded.field_embeddings.dtype == np.float32
    assert loaded.relation_embeddings.flags.writeable is False
    assert paths.manifest.is_file()
    assert paths.matrices.is_file()
    assert len(loaded.metadata.matrices_sha256) == 64
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    ("catalog_sha256", "model_id", "document_version", "message"),
    (
        ("f" * 64, MODEL_ID, DOCUMENT_VERSION, "catalog"),
        (None, "different/model", DOCUMENT_VERSION, "model"),
        (None, MODEL_ID, "different-version", "document"),
    ),
)
def test_load_index_rejects_stale_identity(
    tmp_path: Path,
    catalog_sha256: str | None,
    model_id: str,
    document_version: str,
    message: str,
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)

    with pytest.raises(SchemaIndexError, match=message):
        load_index(
            paths,
            catalog_sha256 or built.metadata.catalog_sha256,
            model_id,
            document_version,
        )


def test_load_index_rejects_tampered_manifest_and_matrix_bytes(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    original_manifest = paths.manifest.read_bytes()

    payload = json.loads(original_manifest)
    payload["manifest_sha256"] = "z" * 64
    paths.manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaIndexError, match="manifest digest"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)

    payload = json.loads(original_manifest)
    payload["dimension"] = 99
    paths.manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaIndexError, match="manifest digest"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)

    paths.manifest.write_bytes(original_manifest)
    with paths.matrices.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(SchemaIndexError, match="matrix digest"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)


def test_load_index_wraps_self_consistent_invalid_element_metadata(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    payload = json.loads(paths.manifest.read_bytes())
    payload["relation_elements"][0]["kind"] = "property"
    _rewrite_manifest(paths.manifest, payload)

    with pytest.raises(SchemaIndexError, match="relation elements"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)


def test_load_index_rejects_self_consistent_document_tampering(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    payload = json.loads(paths.manifest.read_bytes())
    payload["field_elements"][0]["document"] = "tampered document"
    _rewrite_manifest(paths.manifest, payload)

    with pytest.raises(SchemaIndexError, match="document hash"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("schema_version", True, "schema version"),
        ("dimension", True, "dimension"),
        ("dimension", "3", "dimension"),
    ),
)
def test_load_index_rejects_weakly_typed_manifest_numbers(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    payload = json.loads(paths.manifest.read_bytes())
    payload[field] = value
    _rewrite_manifest(paths.manifest, payload)

    with pytest.raises(SchemaIndexError, match=message):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("wrong_rows", "row count"),
        ("nan", "finite"),
        ("unnormalized", "normalized"),
        ("second_dimension", "dimension"),
    ),
)
def test_build_index_rejects_invalid_encoder_output(
    tmp_path: Path, mode: str, message: str
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)

    with pytest.raises(SchemaIndexError, match=message):
        build_index(elements, BrokenEncoder(mode), MODEL_ID, catalog_bytes, paths)

    assert not paths.manifest.exists()
    assert not paths.matrices.exists()


def test_failed_rebuild_preserves_previous_accepted_index(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    accepted = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    manifest_before = paths.manifest.read_bytes()
    matrices_before = paths.matrices.read_bytes()

    with pytest.raises(SchemaIndexError):
        build_index(elements, BrokenEncoder("nan"), MODEL_ID, catalog_bytes, paths)

    loaded = load_index(paths, accepted.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)
    assert loaded.metadata.catalog_sha256 == accepted.metadata.catalog_sha256
    assert paths.manifest.read_bytes() == manifest_before
    assert paths.matrices.read_bytes() == matrices_before


def test_publication_failure_restores_previous_accepted_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    accepted = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    manifest_before = paths.manifest.read_bytes()
    matrices_before = paths.matrices.read_bytes()
    real_replace = index_module.os.replace
    failed = False

    def fail_manifest_once(source: object, target: object) -> None:
        nonlocal failed
        if Path(target) == paths.manifest and not failed:
            failed = True
            raise OSError("injected manifest publication failure")
        real_replace(source, target)

    monkeypatch.setattr(index_module.os, "replace", fail_manifest_once)

    with pytest.raises(SchemaIndexError, match="publish"):
        build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)

    loaded = load_index(paths, accepted.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION)
    assert loaded.metadata.manifest_sha256 == accepted.metadata.manifest_sha256
    assert paths.manifest.read_bytes() == manifest_before
    assert paths.matrices.read_bytes() == matrices_before
