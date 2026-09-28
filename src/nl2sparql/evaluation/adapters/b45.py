"""Adapter from native verified B4/B5 artifacts to canonical predictions."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from nl2sparql.evaluation.adapters.common import (
    load_authoritative_test_set,
    require_distinct_files,
    sha256_file,
)
from nl2sparql.evaluation.artifacts import canonical_json
from nl2sparql.evaluation.contracts import (
    ArtifactRef,
    CanonicalPredictionRun,
    CostEvidence,
    EvaluationError,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    RunProvenance,
)
from nl2sparql.models.b45 import LargeLLMError, load_large_run_artifacts


@dataclass(frozen=True)
class B45AdaptRequest:
    """Native B4/B5 report/journal pair and authoritative test snapshot."""

    test_set_path: Path
    report_path: Path
    request_log_path: Path
    synthetic: bool = False


def _prediction_status(outcome: object) -> tuple[str, str | None]:
    status = outcome.status
    prediction = outcome.prediction
    if status == "completed":
        return "ok", None
    if status == "extraction_failed" and prediction is not None:
        native = prediction.extraction_status
        mapped = {
            "empty": "no_output",
            "prose": "no_output",
            "invalid_sql": "invalid_sql",
            "unsafe_sql": "unsafe_sql",
        }.get(native)
        if mapped is None:
            raise EvaluationError("unsupported B4/B5 extraction status")
        return mapped, native
    if status in {"request_failed", "budget_blocked", "cost_unresolved"}:
        return "generation_error", status
    raise EvaluationError("unsupported B4/B5 outcome status")


def adapt_b45(request: B45AdaptRequest) -> CanonicalPredictionRun:
    """Load through the native hash-chain verifier, then convert without loss."""
    require_distinct_files(request.test_set_path, request.report_path, request.request_log_path)
    authoritative = load_authoritative_test_set(request.test_set_path, synthetic=request.synthetic)
    try:
        native = load_large_run_artifacts(request.report_path, request.request_log_path)
    except LargeLLMError as exc:
        raise EvaluationError(f"invalid native B4/B5 artifacts: {exc}") from exc
    if native.input_sha256 != authoritative.sha256:
        raise EvaluationError("B4/B5 test-set hash does not match authoritative input")
    expected_order = tuple(case.case_id for case in authoritative.cases)
    if tuple(outcome.case_id for outcome in native.outcomes) != expected_order:
        raise EvaluationError("B4/B5 outcome order does not match authoritative test set")

    privacy = PrivacyEvidence(
        documentation_status="documented" if native.privacy_sha256 else "undocumented",
        data_egress="provider",
        provider=native.provider_slug,
        policy_sha256=native.provider_policy_sha256,
        review_sha256=native.privacy_sha256,
    )
    by_id = {case.case_id: case for case in authoritative.cases}
    cases: list[PredictionCase] = []
    for outcome in native.outcomes:
        gold = by_id[outcome.case_id]
        if (
            outcome.gold_sql != gold.gold_sql
            or outcome.difficulty != gold.difficulty
            or outcome.categories != gold.categories
            or outcome.question_sha256 != hashlib.sha256(gold.question.encode()).hexdigest()
        ):
            raise EvaluationError("B4/B5 duplicated authoritative metadata mismatch")
        status, error_code = _prediction_status(outcome)
        prediction = outcome.prediction
        if prediction is not None:
            completion = prediction.completion
            raw_sha = hashlib.sha256(prediction.raw_output.encode()).hexdigest()
            cost = CostEvidence(
                "observed",
                completion.charged_cost_usd,
                "USD",
                f"provider:{completion.provider_slug}",
            )
            latency = prediction.latency_ms
            input_tokens = completion.input_tokens
            output_tokens = completion.output_tokens
            predicted_sql = prediction.sql if status == "ok" else None
        else:
            raw_sha = None
            predicted_sql = None
            latency = None
            input_tokens = None
            output_tokens = None
            cost = (
                CostEvidence("observed", Decimal("0"), "USD", "budget_guard")
                if outcome.status == "budget_blocked"
                else CostEvidence("unmeasured", None, None, None)
            )
        cases.append(
            PredictionCase(
                case_id=gold.case_id,
                question=gold.question,
                gold_sql=gold.gold_sql,
                difficulty=gold.difficulty,
                categories=gold.categories,
                prediction_status=status,
                predicted_sql=predicted_sql,
                raw_output_sha256=raw_sha,
                error_code=error_code or outcome.safe_error_code,
                inference=InferenceEvidence(latency, input_tokens, output_tokens, cost),
                privacy=privacy,
            )
        )

    fingerprints: dict[str, str] = {
        "catalog": native.catalog_sha256,
        "config": native.config_sha256,
        "model_id": hashlib.sha256(native.model_id.encode()).hexdigest(),
        "provider": native.provider_slug,
        "summary": native.summary_sha256,
    }
    for key in (
        "training_sha256",
        "model_metadata_sha256",
        "provider_policy_sha256",
        "privacy_sha256",
        "prompt_set_sha256",
    ):
        value = getattr(native, key)
        if value is not None:
            fingerprints[key.removesuffix("_sha256")] = value
    retrieval = tuple(
        (outcome.case_id, outcome.retrieval_sha256)
        for outcome in native.outcomes
        if outcome.retrieval_sha256 is not None
    )
    if retrieval:
        fingerprints["retrieval_set"] = hashlib.sha256(canonical_json(retrieval)).hexdigest()
    if native.attempts:
        fingerprints["attempt_set"] = hashlib.sha256(
            canonical_json(tuple(asdict(attempt) for attempt in native.attempts))
        ).hexdigest()
    generated_at = datetime.fromisoformat(native.generated_at_utc.replace("Z", "+00:00"))
    refs = [
        ArtifactRef("report", "application/json", sha256_file(request.report_path), 1),
        ArtifactRef("request_log", "application/jsonl", sha256_file(request.request_log_path), 1),
        ArtifactRef("test_set", "application/jsonl", authoritative.sha256, 1),
    ]
    if authoritative.manifest_sha256 is not None:
        refs.append(
            ArtifactRef("test_set_manifest", "application/json", authoritative.manifest_sha256, 1)
        )
    synthetic_backend = any(
        outcome.prediction is not None and outcome.prediction.completion.synthetic_backend
        for outcome in native.outcomes
    )
    return CanonicalPredictionRun(
        baseline_id=native.baseline,
        run_id=native.run_id,
        seed=native.seed,
        generated_at=generated_at,
        test_set_sha256=authoritative.sha256,
        test_case_count=len(cases),
        provenance=RunProvenance(
            reviewed=authoritative.reviewed,
            live_verified=authoritative.live_verified,
            synthetic=request.synthetic or synthetic_backend,
            fingerprints=tuple(sorted(fingerprints.items())),
        ),
        source_artifacts=tuple(sorted(refs, key=lambda ref: ref.role)),
        adapter_id="b45-native-v1",
        adapter_schema_version=1,
        cases=tuple(cases),
    )
