"""Tests for safe, fingerprinted schema-index publication and loading."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
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


def _matrix_path(paths: SchemaCachePaths) -> Path:
    payload = json.loads(paths.manifest.read_bytes())
    return paths.manifest.parent / payload["matrices_file"]


def test_build_and_load_index_preserves_order_and_validated_float32_matrices(
    tmp_path: Path,
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)

    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    loaded = load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)

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
    assert not paths.matrices.exists()
    assert _matrix_path(paths).is_file()
    assert _matrix_path(paths).name == loaded.metadata.matrices_file
    assert _matrix_path(paths) == paths.matrix_generation(loaded.metadata.matrices_sha256)
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
            elements,
        )


@pytest.mark.parametrize("change", ("document", "element_id"))
def test_load_index_rejects_current_document_fingerprint_mismatch(
    tmp_path: Path, change: str
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    changed = list(elements)
    if change == "document":
        document = changed[0].document + "\nSynonyms: newly reviewed phrase"
        changed[0] = replace(
            changed[0],
            document=document,
            document_sha256=hashlib.sha256(document.encode()).hexdigest(),
        )
    else:
        changed[0] = replace(changed[0], element_id="changed_relation")

    with pytest.raises(SchemaIndexError, match="current document|fingerprint"):
        load_index(
            paths,
            built.metadata.catalog_sha256,
            MODEL_ID,
            DOCUMENT_VERSION,
            changed,
        )


def test_load_index_rejects_tampered_manifest_and_matrix_bytes(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    original_manifest = paths.manifest.read_bytes()

    payload = json.loads(original_manifest)
    payload["manifest_sha256"] = "z" * 64
    paths.manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaIndexError, match="manifest digest"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)

    payload = json.loads(original_manifest)
    payload["dimension"] = 99
    paths.manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaIndexError, match="manifest digest"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)

    paths.manifest.write_bytes(original_manifest)
    with _matrix_path(paths).open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(SchemaIndexError, match="matrix digest"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)


def test_load_index_wraps_self_consistent_invalid_element_metadata(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    payload = json.loads(paths.manifest.read_bytes())
    payload["relation_elements"][0]["kind"] = "property"
    _rewrite_manifest(paths.manifest, payload)

    with pytest.raises(SchemaIndexError, match="relation elements"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)


def test_load_index_rejects_self_consistent_document_tampering(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    payload = json.loads(paths.manifest.read_bytes())
    payload["field_elements"][0]["document"] = "tampered document"
    _rewrite_manifest(paths.manifest, payload)

    with pytest.raises(SchemaIndexError, match="document hash"):
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)


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
        load_index(paths, built.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements)


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
    assert not list(tmp_path.glob("schema-index-*.npz"))


def test_failed_rebuild_preserves_previous_accepted_index(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    accepted = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    manifest_before = paths.manifest.read_bytes()
    matrix_before = _matrix_path(paths)
    matrices_before = matrix_before.read_bytes()

    with pytest.raises(SchemaIndexError):
        build_index(elements, BrokenEncoder("nan"), MODEL_ID, catalog_bytes, paths)

    loaded = load_index(
        paths, accepted.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements
    )
    assert loaded.metadata.catalog_sha256 == accepted.metadata.catalog_sha256
    assert paths.manifest.read_bytes() == manifest_before
    assert matrix_before.read_bytes() == matrices_before


def test_publication_failure_preserves_previous_readable_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    accepted = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    manifest_before = paths.manifest.read_bytes()
    matrix_before = _matrix_path(paths)
    matrices_before = matrix_before.read_bytes()
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

    loaded = load_index(
        paths, accepted.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements
    )
    assert loaded.metadata.manifest_sha256 == accepted.metadata.manifest_sha256
    assert paths.manifest.read_bytes() == manifest_before
    assert matrix_before.read_bytes() == matrices_before


class SimulatedCrash(BaseException):
    pass


class AlternateEncoder(FakeEncoder):
    def encode(self, sentences, *, normalize_embeddings=True):
        rows = super().encode(sentences, normalize_embeddings=normalize_embeddings)
        return rows[:, ::-1]


@pytest.mark.parametrize(
    ("crash_point", "manifest_exists"),
    (("matrix_generation_durable", False), ("manifest_durable", True)),
)
def test_first_publication_is_recoverable_at_deterministic_crash_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
    manifest_exists: bool,
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)

    def crash(point: str) -> None:
        if point == crash_point:
            raise SimulatedCrash(point)

    monkeypatch.setattr(index_module, "_publication_checkpoint", crash)
    with pytest.raises(SimulatedCrash):
        build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)

    assert paths.manifest.exists() is manifest_exists
    assert len(list(tmp_path.glob("schema-index-*.npz"))) == 1
    if manifest_exists:
        loaded = load_index(
            paths,
            hashlib.sha256(catalog_bytes).hexdigest(),
            MODEL_ID,
            DOCUMENT_VERSION,
            elements,
        )
        assert loaded.metadata.matrices_file == _matrix_path(paths).name


@pytest.mark.parametrize("crash_point", ("matrix_generation_durable", "manifest_durable"))
def test_rebuild_crash_keeps_a_readable_generation_and_retains_the_prior_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_point: str
) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    accepted = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    old_manifest = paths.manifest.read_bytes()
    old_generation = _matrix_path(paths)

    def crash(point: str) -> None:
        if point == crash_point:
            raise SimulatedCrash(point)

    monkeypatch.setattr(index_module, "_publication_checkpoint", crash)
    with pytest.raises(SimulatedCrash):
        build_index(elements, AlternateEncoder(), MODEL_ID, catalog_bytes, paths)

    loaded = load_index(
        paths, accepted.metadata.catalog_sha256, MODEL_ID, DOCUMENT_VERSION, elements
    )
    assert old_generation.is_file()
    assert len(list(tmp_path.glob("schema-index-*.npz"))) == 2
    if crash_point == "matrix_generation_durable":
        assert paths.manifest.read_bytes() == old_manifest
        assert loaded.metadata.matrices_file == old_generation.name
    else:
        assert paths.manifest.read_bytes() != old_manifest
        assert loaded.metadata.matrices_file != old_generation.name


def test_load_index_rejects_traversal_and_hardlink_alias(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    original_manifest = paths.manifest.read_bytes()
    original_generation = _matrix_path(paths)

    payload = json.loads(original_manifest)
    payload["matrices_file"] = "../schema-index-" + payload["matrices_sha256"] + ".npz"
    _rewrite_manifest(paths.manifest, payload)
    with pytest.raises(SchemaIndexError, match="filename"):
        load_index(
            paths,
            built.metadata.catalog_sha256,
            MODEL_ID,
            DOCUMENT_VERSION,
            elements,
        )

    paths.manifest.write_bytes(original_manifest)
    alias = tmp_path / "matrix-hardlink.npz"
    os.link(original_generation, alias)
    with pytest.raises(SchemaIndexError, match="alias"):
        load_index(
            paths,
            built.metadata.catalog_sha256,
            MODEL_ID,
            DOCUMENT_VERSION,
            elements,
        )


def test_load_index_rejects_symlinked_matrix_generation(tmp_path: Path) -> None:
    elements, catalog_bytes, paths = _inputs(tmp_path)
    built = build_index(elements, FakeEncoder(), MODEL_ID, catalog_bytes, paths)
    generation = _matrix_path(paths)
    real_generation = tmp_path / "saved-generation.npz"
    generation.rename(real_generation)
    generation.symlink_to(real_generation)

    with pytest.raises(SchemaIndexError, match="alias"):
        load_index(
            paths,
            built.metadata.catalog_sha256,
            MODEL_ID,
            DOCUMENT_VERSION,
            elements,
        )
