"""Plumbing only: finalized artifacts, no benchmark-dependent accuracy assertions."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from nl2sparql.models.b12 import (
    BaselineB1,
    Completion,
    GenerationConfig,
    SmallLLMError,
    compile_catalog_summary,
    evaluate_baseline,
    load_evaluation_cases,
)

ROOT = Path(__file__).resolve().parents[2]
VI = ROOT / "data/dataset/test/test-100-vi.jsonl"
EN = ROOT / "data/dataset/test/test-100.jsonl"


def test_finalized_vi_retains_typed_pair_and_exact_source_binding():
    cases = load_evaluation_cases(VI, language="vi")
    original = [json.loads(line) for line in VI.read_text().splitlines()]
    assert len(cases) == 100
    for case, row in zip(cases, original, strict=True):
        assert case.case_id == row["id"]
        assert case.question == row["question"]
        assert case.gold_sql == row["sql"]
        assert case.language == "vi"
        assert json.loads(json.dumps(asdict(case.paired_source.case))) == row
        assert case.paired_source.evidence_mode == "exact_reused_english_live_evidence"
        assert case.reviewed and case.live_verified and not case.synthetic
        assert case._trusted_source
    assert dict(cases[0].paired_source.source_sha256s)["data/dataset/test/test-100-vi.jsonl"] == (
        "0abf44dca4b9111f4fe10930fca5d7c56961b7ef79a0ac0fe50f8b16cb1ba5eb"
    )


@pytest.mark.parametrize("path,language", [(EN, "vi"), (VI, "en"), (VI, "fr")])
def test_wrong_language_fails_closed(path, language):
    with pytest.raises(SmallLLMError):
        load_evaluation_cases(path, language=language)


class PlumbingBackend:
    """Fixed safe output unrelated to gold; always synthetic."""

    def generate(self, messages, config):
        return Completion(
            raw_text="SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`",
            model_id=config.model_id,
            model_revision=config.model_revision,
            input_tokens=1,
            output_tokens=1,
        )


def baseline():
    return BaselineB1(
        compile_catalog_summary(ROOT / "src/nl2sparql/sql/catalog/ethereum_analytics.json"),
        GenerationConfig("a" * 40),
        PlumbingBackend(),
    )


def test_mixed_language_and_snapshot_rejected_before_generation():
    vi = load_evaluation_cases(VI, language="vi")
    en = load_evaluation_cases(EN)
    with pytest.raises(SmallLLMError, match="language|snapshot"):
        evaluate_baseline((en[0], vi[0]), baseline(), run_id="mixed")
    with pytest.raises(SmallLLMError, match="snapshot"):
        evaluate_baseline(
            (vi[0], replace(vi[1], input_sha256="0" * 64)), baseline(), run_id="mixed-hash"
        )


def test_vi_native_and_canonical_roundtrip_is_synthetic(tmp_path):
    from nl2sparql.evaluation.adapters.b12 import B12AdaptRequest, adapt_b12
    from scripts.small_llm_baselines_workflow import publish_evaluation_run

    cases = load_evaluation_cases(VI, language="vi")
    run = evaluate_baseline(
        cases, baseline(), run_id="plumbing-vi", reviewed=True, live_verified=True
    )
    assert run.language == "vi"
    assert run.metrics.total == 100
    assert not run.scientific_ready and "synthetic_backend" in run.blockers
    paths = [tmp_path / name for name in ("pred.jsonl", "log.jsonl", "report.json")]
    publish_evaluation_run(run, predictions_path=paths[0], log_path=paths[1], report_path=paths[2])
    prediction = json.loads(paths[0].read_text().splitlines()[0])
    log = json.loads(paths[1].read_text().splitlines()[0])
    report = json.loads(paths[2].read_text())
    assert prediction["language"] == log["language"] == report["language"] == "vi"
    assert prediction["paired_source"] == log["paired_source"]
    canonical = adapt_b12(B12AdaptRequest(VI, *paths, language="vi"))
    assert canonical.test_case_count == 100 and canonical.provenance.synthetic
    assert canonical.cases[0].case_id == cases[0].case_id
    # A source/pair substitution cannot survive the adapter, even with unchanged SQL.
    rows = paths[0].read_text().splitlines()
    prediction["paired_source"]["case"]["english_id"] = "wrong-source"
    rows[0] = json.dumps(prediction)
    paths[0].write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match="paired|lineage|source"):
        adapt_b12(B12AdaptRequest(VI, *paths, language="vi"))


def test_language_plans_are_isolated_and_three_processes_per_baseline(tmp_path):
    from nl2sparql.kaggle.runner import plan_runs

    config = json.loads((ROOT / "configs/kaggle-b12-run.template.json").read_bytes())
    config.update(
        campaign_id="plumbing",
        model_revision="a" * 40,
        encoder_revision="b" * 40,
        hf_home="/nonexistent",
        run_timeout_seconds=60,
    )
    en = plan_runs(ROOT, config, tmp_path)
    config["language"] = "vi"
    vi = plan_runs(ROOT, config, tmp_path)
    assert len(en) == len(vi) == 6
    assert set(r["folder"] for r in en).isdisjoint(r["folder"] for r in vi)
    for run in vi:
        argv = run["argv"]
        assert argv[argv.index("--language") + 1] == "vi"
        assert argv[argv.index("--test-set") + 1] == str(VI)
        assert run["language"] == "vi"
        assert "-vi-r" in run["run_id"]
        assert argv[argv.index("--cache") + 1] != en[0]["argv"][en[0]["argv"].index("--cache") + 1]


@pytest.mark.parametrize(
    "target",
    [
        "data/dataset/test/test-100-vi.jsonl",
        "data/dataset/test/manifest-vi.json",
        "data/dataset/test/live-evidence-vi.json",
        "data/dataset/test/live-evidence.json",
        "data/dataset/test/test-100.jsonl",
        "data/review_drafts/t3_5_vi_candidate_set_2026-10-07/candidates.jsonl",
        "data/review_drafts/t3_5_vi_candidate_set_2026-10-07/review_events.jsonl",
        "data/review_drafts/t3_5_candidate_set_2026-09-27/final_selection.csv",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_modified_or_missing_paired_authority_rejected(tmp_path, target, mutation):
    from nl2sparql.models.b12.paired_snapshot import SOURCE_SHA256S

    for name in SOURCE_SHA256S:
        copy = tmp_path / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes((ROOT / name).read_bytes())
    copy = tmp_path / target
    if mutation == "missing":
        copy.unlink()
    else:
        copy.write_bytes(copy.read_bytes() + b" ")
    with pytest.raises(SmallLLMError, match="provenance|fingerprint|source"):
        load_evaluation_cases(
            tmp_path / "data/dataset/test/test-100-vi.jsonl", language="vi", source_root=tmp_path
        )


def test_caller_flags_and_paired_dataclass_do_not_create_trust():
    case = load_evaluation_cases(VI, language="vi")[0]
    fabricated = replace(case)  # init=False trust marker deliberately resets.
    run = evaluate_baseline(
        (fabricated,), baseline(), run_id="manual", reviewed=True, live_verified=True
    )
    assert not run.scientific_ready
    assert "trusted_test_set_provenance_missing" in run.blockers


def test_native_publication_refuses_cross_language_overwrite(tmp_path):
    from scripts.small_llm_baselines_workflow import publish_evaluation_run

    run = evaluate_baseline(load_evaluation_cases(VI, language="vi"), baseline(), run_id="same")
    prediction = tmp_path / "pred.jsonl"
    prediction.write_text('{"run_id":"same","language":"en"}\n')
    before = prediction.read_bytes()
    with pytest.raises(SmallLLMError, match="language"):
        publish_evaluation_run(
            run,
            predictions_path=prediction,
            log_path=tmp_path / "log",
            report_path=tmp_path / "report",
        )
    assert prediction.read_bytes() == before
    assert not (tmp_path / "log").exists()


def test_cli17_vi_opt_in_and_protected_sources_precede_load(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import scripts.small_llm_baselines_workflow as workflow

    def forbidden(*a, **k):
        raise AssertionError("real loader forbidden")

    monkeypatch.setattr(workflow, "load_real_backend", forbidden)
    monkeypatch.setattr(workflow, "load_sentence_encoder", forbidden)
    argv = [
        "evaluate",
        "--baseline",
        "b1",
        "--language",
        "vi",
        "--test-set",
        str(VI),
        "--model-revision",
        "a" * 40,
        "--run-id",
        "offline",
        "--predictions",
        str(tmp_path / "p"),
        "--log",
        str(tmp_path / "l"),
        "--report",
        str(tmp_path / "r"),
    ]
    result = CliRunner().invoke(workflow.cli, argv)
    assert result.exit_code == 2 and "opt-in" in result.output
    index = argv.index("--predictions") + 1
    argv[index] = str(ROOT / "data/dataset/test/live-evidence-vi.json")
    result = CliRunner().invoke(workflow.cli, [*argv, "--real-inference"])
    assert result.exit_code == 2 and "alias" in result.output


def test_vi_report_carries_reused_evidence_source_binding(tmp_path):
    from scripts.small_llm_baselines_workflow import publish_evaluation_run

    cases = load_evaluation_cases(VI, language="vi")
    run = evaluate_baseline(cases, baseline(), run_id="report-vi")
    report = tmp_path / "report.json"
    publish_evaluation_run(
        run, predictions_path=tmp_path / "p", log_path=tmp_path / "l", report_path=report
    )
    value = json.loads(report.read_bytes())
    assert value["paired_source_sha256s"] == json.loads(
        json.dumps(cases[0].paired_source.source_sha256s)
    )
    assert value["gold_evidence_mode"] == "exact_reused_english_live_evidence"


def test_native_output_cannot_be_reused_by_other_baseline(tmp_path):
    from scripts.small_llm_baselines_workflow import publish_evaluation_run

    run = evaluate_baseline(load_evaluation_cases(VI, language="vi"), baseline(), run_id="same")
    report = tmp_path / "report"
    report.write_text('{"run_id":"same","language":"vi","baseline":"b2"}\n')
    with pytest.raises(SmallLLMError, match="baseline"):
        publish_evaluation_run(
            run, predictions_path=tmp_path / "p", log_path=tmp_path / "l", report_path=report
        )


def test_invalid_cli17_run_id_fails_before_model_load(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import scripts.small_llm_baselines_workflow as workflow

    def forbidden(*a, **k):
        raise AssertionError("model loader reached before run identity validation")

    monkeypatch.setattr(workflow, "load_real_backend", forbidden)
    result = CliRunner().invoke(
        workflow.cli,
        [
            "evaluate",
            "--baseline",
            "b1",
            "--language",
            "vi",
            "--test-set",
            str(VI),
            "--model-revision",
            "a" * 40,
            "--run-id",
            "../escape",
            "--real-inference",
            "--predictions",
            str(tmp_path / "p"),
            "--log",
            str(tmp_path / "l"),
            "--report",
            str(tmp_path / "r"),
        ],
    )
    assert result.exit_code == 2 and "run ID" in result.output
