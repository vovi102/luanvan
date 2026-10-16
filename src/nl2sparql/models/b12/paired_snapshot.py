"""Typed authority for the immutable user-finalized Vietnamese T3.5 snapshot.

Pins authenticate the accepted publication, not caller-supplied trusted flags.
Evidence is exact reused English execution; this loader never executes SQL.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from nl2sparql.dataset.testset.live import reuse_paired_live_evidence
from nl2sparql.dataset.testset.paired import (
    EnglishPairCase,
    PairedCandidate,
    PairedFinalCase,
    PairedReviewDecision,
    build_paired_manifest,
    finalize_paired_cases,
)
from nl2sparql.dataset.testset.reviewed_artifacts import read_reviewed_live_evidence
from nl2sparql.dataset.testset.reviewed_contracts import load_reviewed_selections
from nl2sparql.models.b0.evaluate import load_b0_cases
from nl2sparql.models.b12.contracts import SmallLLMError

ROOT = Path(__file__).resolve().parents[4]
ENGLISH = "data/dataset/test/test-100.jsonl"
VIETNAMESE = "data/dataset/test/test-100-vi.jsonl"
DRAFT = "data/review_drafts/t3_5_vi_candidate_set_2026-10-07"
SELECTION = "data/review_drafts/t3_5_candidate_set_2026-09-27/final_selection.csv"
SOURCE_SHA256S = {
    "data/dataset/test/live-evidence-vi.json": (
        "b0e506b04dd61ab15258d4d85b17f74889bbcfb2e56150c73b0f8e64be9e347c"
    ),
    "data/dataset/test/live-evidence.json": (
        "21cfee8601c7670f23581bb0c6755f306ca41aab2029dd6b50a6d65fab25f969"
    ),
    "data/dataset/test/manifest-vi.json": (
        "3331cb18cd175ce80addef793514f683414917b17640e80e9451d1258cb88672"
    ),
    "data/dataset/test/manifest.json": (
        "719d41ff065a5b720c64b18de5c2f6ae2988d054000158e5a43d045ddf461f17"
    ),
    "data/dataset/test/test-100-vi.jsonl": (
        "0abf44dca4b9111f4fe10930fca5d7c56961b7ef79a0ac0fe50f8b16cb1ba5eb"
    ),
    "data/dataset/test/test-100.jsonl": (
        "5d342a5c063ea2d4b5fb7cd62ab15fabb82d2164e5eca5cb248843797989ff0d"
    ),
    "data/review_drafts/t3_5_candidate_set_2026-09-27/candidates.jsonl": (
        "39b69d3dbfc49edfe33314c272bbefc8fab1f63ab3eba546a8c3fa9536212b50"
    ),
    "data/review_drafts/t3_5_candidate_set_2026-09-27/final_selection.csv": (
        "adaeab8bbedaebf8f027c493e829a21d6aec27c29a0fa30afb74bc7029c29a00"
    ),
    "data/review_drafts/t3_5_candidate_set_2026-09-27/review_events.csv": (
        "5e065c404cb50c4524c11e45a2eb3cf60ead5d5b64846e85d5518084f5b7fb77"
    ),
    "data/review_drafts/t3_5_vi_candidate_set_2026-10-07/candidates.jsonl": (
        "ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96"
    ),
    "data/review_drafts/t3_5_vi_candidate_set_2026-10-07/review_events.jsonl": (
        "9adec603f6313c6b31e214d0330f940d8cc25c1529824fbebab598d8e9f511da"
    ),
}


@dataclass(frozen=True)
class PairedCaseSource:
    """Original typed row plus exact file authority and honest evidence mode."""

    case: PairedFinalCase
    source_sha256s: tuple[tuple[str, str], ...]
    evidence_mode: str = "exact_reused_english_live_evidence"


def source_paths(root: Path = ROOT) -> tuple[Path, ...]:
    return tuple(root / name for name in SOURCE_SHA256S)


def _rows(payload: bytes) -> tuple[dict, ...]:
    rows = tuple(json.loads(line) for line in payload.decode("utf-8").splitlines())
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise SmallLLMError("paired snapshot requires JSONL objects")
    return rows


def load_paired_sources(path: Path, *, root: Path = ROOT) -> tuple[PairedCaseSource, ...]:
    """Reconstruct human finalization and exact historical evidence, fail closed."""
    try:
        payloads = {}
        for name, digest in SOURCE_SHA256S.items():
            payload = (root / name).read_bytes()
            if hashlib.sha256(payload).hexdigest() != digest:
                raise SmallLLMError(f"paired source fingerprint mismatch: {name}")
            payloads[name] = payload
        if path.read_bytes() != payloads[VIETNAMESE]:
            raise SmallLLMError("Vietnamese snapshot differs from accepted source bytes")
        english = load_b0_cases(root / ENGLISH, synthetic=False)
        evidence = read_reviewed_live_evidence(root / "data/dataset/test/live-evidence.json")
        selections = {row.question_id: row for row in load_reviewed_selections(root / SELECTION)}
        executions = {row.question_id: row for row in evidence.execution.records}
        source = tuple(
            EnglishPairCase(
                id=case.case_id,
                question=case.question,
                sql=case.gold_sql,
                expected_columns=executions[case.case_id].columns,
                expected_result_size=raw["expected_result_size"],
                difficulty=case.difficulty,
                categories=tuple(raw["categories"]),
                entity_kinds=selections[case.case_id].entity_kinds,
                schema_elements=tuple(raw["schema_elements"]),
                cq_ids=tuple(raw["cq_ids"]),
            )
            for case, raw in zip(english.cases, _rows(payloads[ENGLISH]), strict=True)
        )
        finalized = finalize_paired_cases(
            source,
            tuple(
                PairedCandidate.from_mapping(row)
                for row in _rows(payloads[f"{DRAFT}/candidates.jsonl"])
            ),
            tuple(
                PairedReviewDecision.from_mapping(row)
                for row in _rows(payloads[f"{DRAFT}/review_events.jsonl"])
            ),
        )
        expected = json.loads(json.dumps([asdict(case) for case in finalized]))
        if list(_rows(payloads[VIETNAMESE])) != expected:
            raise SmallLLMError("paired final snapshot differs from human-reviewed lineage")
        manifest = build_paired_manifest(finalized, english_benchmark_sha256=english.input_sha256)
        if json.loads(payloads["data/dataset/test/manifest-vi.json"]) != asdict(manifest):
            raise SmallLLMError("paired manifest source binding mismatch")
        reused = reuse_paired_live_evidence(
            source, finalized, evidence.execution, policy=evidence.policy
        )
        if json.loads(payloads["data/dataset/test/live-evidence-vi.json"]) != json.loads(
            json.dumps(asdict(reused))
        ):
            raise SmallLLMError("paired exact reused English evidence mismatch")
        if any((root / name).read_bytes() != payload for name, payload in payloads.items()):
            raise SmallLLMError("paired source changed during validation")
        if path.read_bytes() != payloads[VIETNAMESE]:
            raise SmallLLMError("paired snapshot changed during validation")
        binding = tuple(sorted(SOURCE_SHA256S.items()))
        return tuple(PairedCaseSource(case, binding) for case in finalized)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise SmallLLMError(f"invalid finalized Vietnamese provenance: {exc}") from exc
