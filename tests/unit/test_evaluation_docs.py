from pathlib import Path

TASK = Path("docs/tasks/phase-5-baselines/04-evaluation-framework.md")
README = Path("README.md")


def test_t54_task_documents_current_nl2sql_contract_and_boundary() -> None:
    text = TASK.read_text(encoding="utf-8")
    lowered = text.casefold()

    for required in (
        "t5.4-a",
        "t5.4-b",
        "googlesql",
        "bigquery",
        "--allow-bigquery",
        "10,000",
        "seed 42",
        "full denominator",
        "implementation_status",
        "scientific_status",
    ):
        assert required in lowered
    assert "sparql trên fuseki" not in lowered
    assert "cost = 0 (local)" not in lowered
    assert "numbers placeholder" not in lowered


def test_readme_exposes_safe_offline_commands_and_live_warning() -> None:
    text = README.read_text(encoding="utf-8")

    assert "scripts/19_nl2sql_evaluation.py --help" in text
    assert "scripts/19_nl2sql_evaluation.py validate" in text
    assert "--allow-bigquery" in text
    assert "không" in text.casefold() or "khong" in text.casefold()
    assert "T5.4-B" in text
