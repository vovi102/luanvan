"""B2 must consume the exact accepted train projection, without schema forgery."""

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.models.b12.contracts import SmallLLMError
from nl2sparql.models.b12.retrieval import _load_records

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "data/dataset/processed/bilingual-training.jsonl"


def train_bytes():
    return b"".join(
        line
        for line in CANONICAL.read_bytes().splitlines(keepends=True)
        if json.loads(line)["split"] == "train"
    )


def test_real_canonical_train_rows_keep_original_schema():
    records = _load_records(train_bytes())
    assert len(records) == 7208
    assert len({r.semantic_family_id for r in records}) == 901
    assert sum(r.language == "vi" for r in records) == 3604


def test_export_is_lossless_deterministic_and_excludes_development():
    from nl2sparql.models.b12.canonical_training import build_training_export

    first, manifest = build_training_export()
    assert build_training_export() == (first, manifest)
    assert first == train_bytes()
    source = [json.loads(line) for line in CANONICAL.read_bytes().splitlines()]
    rows = [json.loads(line) for line in first.splitlines()]
    dev_ids = {r["id"] for r in source if r["split"] == "development"}
    dev_families = {r["semantic_family_id"] for r in source if r["split"] == "development"}
    assert len(dev_ids) == 792
    assert not dev_ids.intersection(r["id"] for r in rows)
    assert not dev_families.intersection(r["semantic_family_id"] for r in rows)
    assert all("synthetic_fixture" not in r and "text_variant" not in r for r in rows)
    assert json.loads(manifest)["training_sha256"] == hashlib.sha256(first).hexdigest()


@pytest.mark.parametrize(
    "change",
    [
        "development",
        "fixture",
        "sql",
        "question",
        "id",
        "family",
        "producer",
        "style",
        "digest",
        "reorder",
        "subset",
    ],
)
def test_modified_canonical_export_is_rejected(change):
    lines = train_bytes().splitlines(keepends=True)
    row = json.loads(lines[0])
    fields = {
        "development": ("split", "development"),
        "fixture": ("synthetic_fixture", True),
        "sql": ("sql", "DELETE FROM x"),
        "question": ("question", "changed"),
        "id": ("id", "t35-001"),
        "family": ("semantic_family_id", "forged"),
        "producer": ("producer_type", "fixture"),
        "style": ("style", "fake"),
        "digest": ("record_sha256", "0" * 64),
    }
    if change in fields:
        key, value = fields[change]
        row[key] = value
        lines[0] = (json.dumps(row) + "\n").encode()
    elif change == "reorder":
        lines.reverse()
    else:
        lines.pop()
    with pytest.raises(SmallLLMError, match="split=train|canonical train projection"):
        _load_records(b"".join(lines))


def test_full_canonical_cannot_be_used_as_training():
    with pytest.raises(SmallLLMError, match="canonical train projection|split=train"):
        _load_records(CANONICAL.read_bytes())


def test_missing_fixture_flag_still_rejected_for_legacy_schema():
    row = {"id": "train-001", "nl": "test question", "split": "train", "sql": "SELECT 1"}
    with pytest.raises(SmallLLMError, match="synthetic fixture"):
        _load_records((json.dumps(row) + "\n").encode())


def test_changed_source_binding_rejected(tmp_path):
    from nl2sparql.models.b12.canonical_training import SOURCE_SHA256S, build_training_export

    for name in SOURCE_SHA256S:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (tmp_path / "data/dataset/processed/bilingual-training-audit.jsonl").write_bytes(b"forged")
    with pytest.raises(SmallLLMError, match="source fingerprint mismatch"):
        build_training_export(root=tmp_path)


def test_fingerprint_binds_consumed_export_not_full_corpus():
    from nl2sparql.models.b12.retrieval import validate_training_snapshot

    payload = train_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    records, actual = validate_training_snapshot(payload, accepted_training_sha256=digest)
    assert len(records) == 7208
    assert actual == digest
    with pytest.raises(SmallLLMError, match="does not match"):
        validate_training_snapshot(
            payload, accepted_training_sha256=hashlib.sha256(CANONICAL.read_bytes()).hexdigest()
        )
    with pytest.raises(SmallLLMError, match="accepted bilingual training"):
        validate_training_snapshot(payload)


def test_real_retriever_preflights_export_without_encoder(tmp_path):
    from nl2sparql.models.b12.retrieval import FewShotRetriever

    payload = train_bytes()
    path = tmp_path / "train.jsonl"
    path.write_bytes(payload)
    # Actual production orchestration must pass data validation and stop at the cache boundary.
    with pytest.raises(SmallLLMError, match="encoder unavailable and no cache"):
        FewShotRetriever.from_snapshot(
            path,
            encoder=None,
            encoder_id="sentence-transformers/all-MiniLM-L6-v2",
            encoder_revision="b" * 40,
            accepted_training_sha256=hashlib.sha256(payload).hexdigest(),
        )


def test_actual_b2_loads_real_export_with_test_only_cache_and_no_encoder(tmp_path):
    import numpy as np

    from nl2sparql.models.b12.retrieval import (
        FewShotRetriever,
        _publish_cache,
        validate_training_snapshot,
    )

    payload = train_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    records, _ = validate_training_snapshot(payload, accepted_training_sha256=digest)
    path = tmp_path / "train.jsonl"
    path.write_bytes(payload)
    cache = tmp_path / "TEST-ONLY-synthetic-cache.npz"
    # This matrix only exercises the cache/data boundary; never publish as encoder evidence.
    _publish_cache(
        cache,
        cache.with_suffix(".npz.json"),
        training_sha256=digest,
        encoder_id="test-only-no-model",
        encoder_revision="b" * 40,
        records=records,
        matrix=np.ones((7208, 1), dtype=np.float32),
        accepted_training_sha256=digest,
    )
    loaded = FewShotRetriever.from_snapshot(
        path,
        encoder=None,
        encoder_id="test-only-no-model",
        encoder_revision="b" * 40,
        cache_path=cache,
        accepted_training_sha256=digest,
    )
    assert loaded.training_sha256 == digest
    assert loaded.training_accepted is True
    with pytest.raises(SmallLLMError, match="query encoder unavailable"):
        loaded.retrieve("offline boundary check")


def test_export_cli_is_immutable_and_reproducible(tmp_path):
    import importlib.util

    from click.testing import CliRunner

    spec = importlib.util.spec_from_file_location(
        "b2_training_cli", ROOT / "scripts/22_b2_training.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    digest = hashlib.sha256(train_bytes()).hexdigest()
    output = tmp_path / "export.jsonl"
    args = ["export", "--output", str(output), "--accepted-training-sha256", digest]
    runner = CliRunner()
    first = runner.invoke(module.main, args)
    assert first.exit_code == 0, first.output
    before = (output.read_bytes(), output.with_suffix(".manifest.json").read_bytes())
    assert runner.invoke(module.main, args).exit_code == 0
    assert (output.read_bytes(), output.with_suffix(".manifest.json").read_bytes()) == before
    assert runner.invoke(module.main, ["validate", *args[1:]]).exit_code == 0
    output.write_bytes(b"do not overwrite")
    assert runner.invoke(module.main, args).exit_code != 0
    assert output.read_bytes() == b"do not overwrite"
    assert runner.invoke(module.main, ["validate", *args[1:]]).exit_code != 0
