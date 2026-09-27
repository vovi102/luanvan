import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nl2sparql.evaluation.adapters.b12 import B12AdaptRequest, adapt_b12
from nl2sparql.evaluation.contracts import EvaluationError
from nl2sparql.models.b12 import Completion, SelectedExample, SmallLLMPrediction
from nl2sparql.models.b12.evaluate import (
    EvaluationMetrics,
    EvaluationPrediction,
    EvaluationRun,
)
from scripts.small_llm_baselines_workflow import publish_evaluation_run

SQL = "SELECT transaction_hash FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`"
SHA_A = "a" * 64
SHA_B = "b" * 64


def _gold(case_id: str) -> dict[str, object]:
    return {
        "ambiguity_flag": False,
        "categories": ["entity_lookup"],
        "cq_ids": ["CQ01"],
        "difficulty": "easy",
        "evidence_sha256": hashlib.sha256(SQL.encode()).hexdigest(),
        "expected_result_size": 1,
        "id": case_id,
        "nl": f"Question {case_id}",
        "pool_b_writer": "writer_1",
        "pool_c_reviewers": ["reviewer_1"],
        "schema_elements": ["transaction_facts.transaction_hash"],
        "source": "author_1",
        "sql": SQL,
        "verified_at": "2026-09-26T00:00:00Z",
        "verified_executable": True,
    }


def _test_set(path: Path) -> tuple[Path, str]:
    payload = "".join(json.dumps(_gold(case), sort_keys=True) + "\n" for case in ("q1", "q2"))
    path.write_text(payload)
    return path, hashlib.sha256(payload.encode()).hexdigest()


def _native_run(input_sha: str, run_id: str = "run-1", baseline: str = "b1") -> EvaluationRun:
    predictions = []
    for case_id, raw, sql, status, latency in (
        ("q1", SQL, SQL, "ok", 10.0),
        ("q2", "", None, "empty", 20.0),
    ):
        completion = Completion(raw, "meta-llama/Meta-Llama-3-8B-Instruct", "c" * 40, 8, 4)
        selected = tuple(
            SelectedExample(f"train-{index}", f"Example {index}", SQL, float(index) / 10)
            for index in range(5)
        )
        prediction = SmallLLMPrediction(
            baseline=baseline,
            question=f"Question {case_id}",
            raw_output=raw,
            sql=sql,
            extraction_status=status,
            completion=completion,
            catalog_sha256=SHA_A,
            summary_sha256=SHA_B,
            prompt_sha256="d" * 64,
            config_sha256="e" * 64,
            latency_ms=latency,
            training_sha256="f" * 64 if baseline == "b2" else None,
            encoder_id="sentence-transformer" if baseline == "b2" else None,
            encoder_revision="1" * 40 if baseline == "b2" else None,
            training_accepted=baseline == "b2",
            selected_examples=selected if baseline == "b2" else (),
        )
        predictions.append(
            EvaluationPrediction(case_id, SQL, "easy", ("entity_lookup",), prediction)
        )
    metrics = EvaluationMetrics(
        total=2,
        generated=1,
        extraction_ok=1,
        extraction_failed=1,
        p50_latency_ms=15.0,
        p95_latency_ms=19.5,
        input_tokens=16,
        output_tokens=8,
        status_counts=(("empty", 1), ("ok", 1)),
        difficulty_counts=(("easy", 2),),
        category_counts=(("entity_lookup", 2),),
    )
    return EvaluationRun(
        run_id=run_id,
        baseline=baseline,
        predictions=tuple(predictions),
        metrics=metrics,
        scientific_ready=False,
        blockers=("synthetic_backend",),
        seed=42,
        generated_at_utc="2026-09-26T12:00:00Z",
        input_sha256=input_sha,
    )


def _artifacts(
    tmp_path: Path, run_id: str = "run-1", baseline: str = "b1"
) -> tuple[Path, Path, Path, Path]:
    test_set, input_sha = _test_set(tmp_path / f"{run_id}-test.jsonl")
    predictions = tmp_path / f"{run_id}-predictions.jsonl"
    log = tmp_path / f"{run_id}-log.jsonl"
    report = tmp_path / f"{run_id}-report.json"
    publish_evaluation_run(
        _native_run(input_sha, run_id, baseline),
        predictions_path=predictions,
        log_path=log,
        report_path=report,
        protected_paths=(test_set,),
    )
    return test_set, predictions, log, report


def test_b12_maps_status_latency_tokens_hashes_and_provenance(tmp_path: Path) -> None:
    test_set, predictions, log, report = _artifacts(tmp_path)
    run = adapt_b12(B12AdaptRequest(test_set, predictions, log, report, synthetic=True))

    assert run.baseline_id == "b1"
    assert run.run_id == "run-1"
    assert run.seed == 42
    assert run.generated_at == datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert run.cases[0].prediction_status == "ok"
    assert run.cases[1].prediction_status == "no_output"
    assert run.cases[1].error_code == "empty"
    assert run.cases[0].raw_output_sha256 == hashlib.sha256(SQL.encode()).hexdigest()
    assert (run.cases[0].inference.latency_ms, run.cases[0].inference.input_tokens) == (10.0, 8)
    assert run.cases[0].inference.cost.measurement_status == "unmeasured"
    assert dict(run.provenance.fingerprints)["model_revision"] == "c" * 40
    assert run.provenance.synthetic is True
    assert run.cases[0].privacy.documentation_status == "undocumented"


def test_b2_retains_training_encoder_and_selected_example_provenance(tmp_path: Path) -> None:
    test_set, predictions, log, report = _artifacts(tmp_path, baseline="b2")
    run = adapt_b12(B12AdaptRequest(test_set, predictions, log, report, synthetic=True))

    fingerprints = dict(run.provenance.fingerprints)
    assert run.baseline_id == "b2"
    assert fingerprints["training"] == "f" * 64
    assert fingerprints["encoder_revision"] == "1" * 40
    assert len(fingerprints["selected_examples"]) == 64


def test_b12_rejects_valid_files_from_different_runs(tmp_path: Path) -> None:
    test_set, predictions, _, report = _artifacts(tmp_path, "run-1")
    _, _, other_log, _ = _artifacts(tmp_path, "run-2")

    with pytest.raises(EvaluationError, match="cross-file identity"):
        adapt_b12(B12AdaptRequest(test_set, predictions, other_log, report, synthetic=True))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", 7),
        ("input_sha256", "f" * 64),
        ("selected_examples_sha256", "f" * 64),
    ],
)
def test_b12_rejects_log_identity_mismatches(tmp_path: Path, field: str, value: object) -> None:
    test_set, predictions, log, report = _artifacts(tmp_path)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    rows[0][field] = value
    log.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    )

    with pytest.raises(EvaluationError, match="cross-file identity"):
        adapt_b12(B12AdaptRequest(test_set, predictions, log, report, synthetic=True))


def test_b12_rejects_model_revision_inconsistency_and_case_reordering(tmp_path: Path) -> None:
    test_set, predictions, log, report = _artifacts(tmp_path)
    rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    rows[1]["prediction"]["completion"]["model_revision"] = "f" * 40
    predictions.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    )
    with pytest.raises(EvaluationError, match="model revision"):
        adapt_b12(B12AdaptRequest(test_set, predictions, log, report, synthetic=True))

    publish_evaluation_run(
        _native_run(hashlib.sha256(test_set.read_bytes()).hexdigest()),
        predictions_path=predictions,
        log_path=log,
        report_path=report,
        protected_paths=(test_set,),
    )
    log_rows = [json.loads(line) for line in log.read_text().splitlines()]
    log.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in reversed(log_rows)
        )
    )
    with pytest.raises(EvaluationError, match="case order"):
        adapt_b12(B12AdaptRequest(test_set, predictions, log, report, synthetic=True))


def test_b12_rejects_config_and_catalog_inconsistency_between_cases(tmp_path: Path) -> None:
    test_set, predictions, log, report = _artifacts(tmp_path)
    rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    rows[1]["prediction"]["config_sha256"] = "9" * 64
    rows[1]["prediction"]["catalog_sha256"] = "8" * 64
    predictions.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    )

    with pytest.raises(EvaluationError, match="config fingerprint"):
        adapt_b12(B12AdaptRequest(test_set, predictions, log, report, synthetic=True))
