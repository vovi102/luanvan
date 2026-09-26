import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nl2sparql.evaluation.artifacts import (
    HashChainJournal,
    canonical_json,
    load_and_verify_artifact,
    load_prediction_run,
    load_privacy_review,
    publish_immutable,
    serialize_prediction_run,
    serialize_privacy_review,
    verify_sealed_journal,
)
from nl2sparql.evaluation.contracts import (
    ArtifactRef,
    CanonicalPredictionRun,
    CostEvidence,
    EvaluationError,
    InferenceEvidence,
    PredictionCase,
    PrivacyEvidence,
    PrivacyReview,
    RunProvenance,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _review() -> PrivacyReview:
    return PrivacyReview(
        baseline_id="b4",
        test_set_sha256=SHA_A,
        data_egress="provider",
        provider="gemini",
        policy_sha256=SHA_B,
        reviewer_id="reviewer-01",
        reviewed_at=NOW,
        synthetic=False,
    )


def _run() -> CanonicalPredictionRun:
    return CanonicalPredictionRun(
        baseline_id="b0",
        run_id="run-001",
        seed=42,
        generated_at=NOW,
        test_set_sha256=SHA_A,
        test_case_count=1,
        provenance=RunProvenance(True, True, False, (("catalog", SHA_B),)),
        source_artifacts=(ArtifactRef("prediction", "application/jsonl", SHA_B, 1),),
        adapter_id="b0-v1",
        adapter_schema_version=1,
        cases=(
            PredictionCase(
                case_id="q-001",
                question="Count transfers.",
                gold_sql="SELECT COUNT(*) FROM `p.d.transfers`",
                difficulty="easy",
                categories=("aggregation",),
                prediction_status="ok",
                predicted_sql="SELECT COUNT(*) FROM `p.d.transfers`",
                raw_output_sha256=SHA_A,
                error_code=None,
                inference=InferenceEvidence(
                    1.5,
                    3,
                    4,
                    CostEvidence("observed", Decimal("0.0100"), "USD", "meter"),
                ),
                privacy=PrivacyEvidence("documented", "none", None, SHA_A, SHA_B),
            ),
        ),
    )


def test_canonical_json_orders_keys_uses_decimal_strings_and_newline() -> None:
    payload = canonical_json({"z": Decimal("1.2300"), "a": [2, 1]})
    assert payload == b'{"a":[2,1],"z":"1.2300"}\n'


def test_privacy_review_round_trip_and_generic_dispatch(tmp_path: Path) -> None:
    path = tmp_path / "privacy.json"
    payload = serialize_privacy_review(_review())
    path.write_bytes(payload)

    assert load_privacy_review(path) == _review()
    assert load_and_verify_artifact(path) == _review()


def test_prediction_run_round_trip_preserves_order_and_exact_decimal(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    payload = serialize_prediction_run(_run())
    path.write_bytes(payload)

    loaded = load_prediction_run(path)
    assert loaded == _run()
    assert loaded.cases[0].inference.cost.amount == Decimal("0.0100")


def test_loader_rejects_unknown_fields_version_tampering_and_noncanonical_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "privacy.json"
    document = json.loads(serialize_privacy_review(_review()))

    document["extra"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(EvaluationError, match="field set"):
        load_privacy_review(path)

    document.pop("extra")
    document["schema_version"] = 2
    path.write_bytes(canonical_json(document))
    with pytest.raises(EvaluationError, match="schema version"):
        load_privacy_review(path)

    document["schema_version"] = 1
    document["body"]["provider"] = "changed"
    path.write_bytes(canonical_json(document))
    with pytest.raises(EvaluationError, match="self-hash"):
        load_privacy_review(path)

    canonical = serialize_privacy_review(_review())
    path.write_bytes(canonical.replace(b'"body":', b'"body" : '))
    with pytest.raises(EvaluationError, match="canonical"):
        load_privacy_review(path)


def test_publish_is_idempotent_but_refuses_different_content(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    publish_immutable(path, b"one\n")
    publish_immutable(path, b"one\n")
    assert path.read_bytes() == b"one\n"

    with pytest.raises(EvaluationError, match="different content"):
        publish_immutable(path, b"two\n")


def test_publish_rejects_protected_symlink_and_hardlink_aliases(tmp_path: Path) -> None:
    protected = tmp_path / "input.json"
    protected.write_bytes(b"source\n")

    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(protected)
    with pytest.raises(EvaluationError, match="alias"):
        publish_immutable(symlink, b"new\n", protected_paths=(protected,))

    hardlink = tmp_path / "hardlink.json"
    os.link(protected, hardlink)
    with pytest.raises(EvaluationError, match="alias"):
        publish_immutable(hardlink, b"new\n", protected_paths=(protected,))


def test_hash_chain_requires_untampered_terminal_seal(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    journal = HashChainJournal(path)
    journal.append("header", {"run": SHA_A})

    with pytest.raises(EvaluationError, match="unsealed"):
        verify_sealed_journal(path)

    terminal = journal.seal({"case_count": 1})
    assert verify_sealed_journal(path) == terminal

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("header", "changed")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(EvaluationError, match="digest"):
        verify_sealed_journal(path)
