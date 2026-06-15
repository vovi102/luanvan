from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELATED_WORK_DIR = ROOT / "docs" / "related-work"


def test_related_work_bib_has_at_least_thirty_entries() -> None:
    text = (RELATED_WORK_DIR / "papers.bib").read_text(encoding="utf-8")

    assert text.count("@") >= 30
    assert text.count("url =") >= 30


def test_related_work_notes_cover_required_groups_and_gaps() -> None:
    text = (RELATED_WORK_DIR / "notes.md").read_text(encoding="utf-8")

    for group in ["Nhóm A", "Nhóm B", "Nhóm C", "Nhóm D", "Nhóm E", "Nhóm F"]:
        assert group in text

    assert text.count("### [") >= 30
    assert text.count("\n1. **") >= 1
    assert text.count("\n5. **") >= 1


def test_comparison_table_has_at_least_ten_papers() -> None:
    text = (RELATED_WORK_DIR / "comparison-table.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("|") and "http" in line]

    assert len(rows) >= 10
    assert "Schema linking" in text
    assert "Code available" in text
