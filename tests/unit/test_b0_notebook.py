from __future__ import annotations

import json
from pathlib import Path


def test_b0_notebook_reads_the_published_workflow_artifact() -> None:
    notebook = json.loads(Path("notebooks/13_b0_eval.ipynb").read_text(encoding="utf-8"))

    source = "\n".join(line for cell in notebook["cells"] for line in cell.get("source", []))
    assert notebook["nbformat"] == 4
    assert "reports/b0_evaluation.json" in source
    assert "BaselineB0(" not in source
    assert "BigQuery" not in source
    assert all(
        cell.get("outputs", []) == [] for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
