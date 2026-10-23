"""Real retained artifacts, offline only; no fabricated inference or executor."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from nl2sparql.evaluation.artifacts import load_and_verify_artifact
from nl2sparql.evaluation.contracts import CanonicalPredictionRun, EvaluationError

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/evidence/kaggle-b12-generation-matrix-2026-10-23.json"


def driver():
    path = ROOT / "scripts/28_prepare_t54_offline.py"
    assert path.is_file(), "offline preparation driver missing"
    spec = importlib.util.spec_from_file_location("t54_offline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def prepared():
    return driver().prepare(ROOT, MATRIX)


def test_real_campaign_keeps_all_cases_raw_failures_and_original_identities(prepared, tmp_path):
    files, protected = prepared
    audit = json.loads(files["audit.json"])
    assert len(audit["runs"]) == 12
    assert len(audit["failed_attempts"]) == 2
    assert audit["live_jobs_created"] == 0
    trace = [json.loads(line) for line in files["case-trace.jsonl"].splitlines()]
    assert len(trace) == 1200
    assert len({(r["run_id"], r["case_id"]) for r in trace}) == 1200
    for row in audit["runs"]:
        artifact = tmp_path / "run.json"
        artifact.write_bytes(files[row["canonical_path"]])
        run = load_and_verify_artifact(artifact)
        assert isinstance(run, CanonicalPredictionRun)
        assert run.test_case_count == 100 and not run.provenance.synthetic
        assert run.run_id == row["run_id"]
        assert all(c.privacy.documentation_status == "undocumented" for c in run.cases)
        native = [
            json.loads(s)
            for s in (ROOT / row["sources"]["predictions"]["path"]).read_text().splitlines()
        ]
        assert [c.case_id for c in run.cases] == [r["case_id"] for r in native]
        for case, original in zip(run.cases, native, strict=True):
            prediction = original["prediction"]
            assert (
                case.raw_output_sha256
                == hashlib.sha256(prediction["raw_output"].encode()).hexdigest()
            )
            assert case.predicted_sql == prediction["sql"]
            if prediction["extraction_status"] == "prose":
                assert (case.prediction_status, case.error_code) == ("no_output", "prose")
        assert row["native_scientific_ready"] is False
        assert row["native_blockers"] == [
            "latency_gate_failed",
            "live_evidence_missing",
            "reviewed_test_set_missing",
        ]
    assert len(protected) > 36
    assert sum(r["predicted_queries_static_ok"] for r in audit["runs"]) == 129
    assert sum(r["gold_queries_static_ok"] for r in audit["runs"]) == 1200


def test_agreement_keeps_one_observation_per_question(prepared):
    files, _ = prepared
    for group in json.loads(files["audit.json"])["agreement"]:
        assert group["denominator"] == 100
        assert group["all_three_raw_output_hash_equal_cases"] == 100
        assert group["all_three_canonical_observation_equal_cases"] == 100
        assert "interval" not in group


@pytest.mark.parametrize("mutation", ["hash", "missing", "duplicate", "ledger"])
def test_invalid_campaign_is_rejected_before_any_publication(tmp_path, mutation):
    matrix = json.loads(MATRIX.read_bytes())
    if mutation == "hash":
        matrix["rows"][0]["source_run_sha256"] = "0" * 64
    elif mutation == "missing":
        matrix["rows"].pop()
    elif mutation == "duplicate":
        matrix["rows"][-1] = matrix["rows"][0]
    else:
        matrix["retained_native_ledger"]["attempted_run_ids"].pop()
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(matrix))
    with pytest.raises(EvaluationError):
        driver().prepare(ROOT, path)


def test_publication_refuses_overwrite_and_is_byte_reproducible(prepared, tmp_path):
    files, protected = prepared
    module = driver()
    module.publish(tmp_path, files, protected)
    before = {name: (tmp_path / name).read_bytes() for name in files}
    with pytest.raises(EvaluationError):
        module.publish(tmp_path, files, protected)
    assert before == files
    assert before == {name: (tmp_path / name).read_bytes() for name in files}


def test_publication_checks_all_aliases_before_writing_any_artifact(prepared, tmp_path):
    files, protected = prepared
    source = ROOT / "data/dataset/test/test-100.jsonl"
    before = source.read_bytes()
    (tmp_path / "case-trace.jsonl").symlink_to(source)
    with pytest.raises(EvaluationError):
        driver().publish(tmp_path, files, protected)
    assert source.read_bytes() == before
    assert not list((tmp_path / "canonical").glob("*.json"))
