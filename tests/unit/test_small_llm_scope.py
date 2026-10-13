"""Regression checks for the small-LLM-only project scope."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_retired_large_model_surfaces_are_removed() -> None:
    removed_paths = (
        "src/nl2sparql/models/b45",
        "src/nl2sparql/models/b4_zero_shot.py",
        "src/nl2sparql/models/b5_few_shot.py",
        "src/nl2sparql/evaluation/adapters/b45.py",
        "scripts/18_large_llm_baselines.py",
        "scripts/generate_b45_local_verification.py",
        "scripts/large_llm_baselines_workflow.py",
        "docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md",
    )

    leftovers = [path for path in removed_paths if (ROOT / path).exists()]

    assert leftovers == []


def test_remote_llm_provider_surfaces_are_removed() -> None:
    removed_paths = (
        "src/nl2sparql/dataset/paraphrase/gemini.py",
        "scripts/10_paraphrase_stage_a.py",
        "docs/research/t5-3-alternatives-2026-09-20.md",
        "docs/evidence/t5-3-local-verification.json",
    )
    leftovers = [path for path in removed_paths if (ROOT / path).exists()]
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert leftovers == []
    assert '"open' + "ai>=" not in pyproject.lower()


def test_canonical_project_docs_describe_only_b0_through_b3() -> None:
    canonical_docs = (
        "README.md",
        "docs/planning/prioritized-backlog-2026-09-21.md",
        "docs/memory/00-PROJECT_OVERVIEW.md",
        "docs/memory/01-ARCHITECTURE.md",
        "docs/memory/02-TECH_STACK.md",
        "docs/tasks/phase-5-baselines/04-evaluation-framework.md",
        "docs/tasks/phase-5-baselines/05-pivot-decision.md",
    )
    retired_tokens = ("B" + "4", "B" + "5", "Open" + "Router", "large-" + "LLM")

    violations: list[str] = []
    for relative_path in canonical_docs:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for token in retired_tokens:
            if token.lower() in text.lower():
                violations.append(f"{relative_path}: {token}")

    assert violations == []
