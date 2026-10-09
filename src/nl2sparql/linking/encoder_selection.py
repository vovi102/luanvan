"""Development-only multilingual encoder evaluation and frozen selection evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

FINAL_BENCHMARK_SHA256S = frozenset(
    {"5d342a5c063ea2d4b5fb7cd62ab15fabb82d2164e5eca5cb248843797989ff0d"}
)
SELECTION_RULE = "vi_metric,english_metric,latency_ms,model_id"


class EncoderSelectionError(ValueError):
    """Raised when encoder evidence is invalid, leaked, or not selectable."""


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _digest(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise EncoderSelectionError(f"{label} must be a lower-case SHA-256")
    if value in FINAL_BENCHMARK_SHA256S:
        raise EncoderSelectionError(f"{label} is a held-out benchmark hash")
    return value


def _development_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    lowered = tuple(part.casefold() for part in path.parts)
    joined = "/".join(lowered)
    if "data/dataset/test" in joined or any(part.startswith("t3_5") for part in lowered):
        raise EncoderSelectionError(f"{label} points to a held-out benchmark")
    if not value or path.is_absolute() or ".." in path.parts:
        raise EncoderSelectionError(f"{label} must be a repository-relative development path")
    return value


@dataclass(frozen=True, slots=True)
class DevelopmentSets:
    """Hash-bound English, Vietnamese, and unaccented development inputs."""

    english_path: str
    english_sha256: str
    vietnamese_path: str
    vietnamese_sha256: str
    unaccented_path: str
    unaccented_sha256: str

    def __post_init__(self) -> None:
        for label in ("english", "vietnamese", "unaccented"):
            _development_path(getattr(self, f"{label}_path"), f"{label}_path")
            _digest(getattr(self, f"{label}_sha256"), f"{label}_sha256")


@dataclass(frozen=True, slots=True)
class EncoderCandidate:
    """Pinned candidate and measured development-only metrics."""

    model_id: str
    revision: str
    artifact_sha256: str
    license: str
    dimension: int
    normalization: str
    english_metric: float
    vietnamese_metric: float
    unaccented_metric: float
    schema_recall_at_5_en: float
    schema_recall_at_5_vi: float
    schema_recall_at_10_en: float
    schema_recall_at_10_vi: float
    schema_mrr_en: float
    schema_mrr_vi: float
    entity_top1_en: float
    entity_top1_vi: float
    entity_f1_en: float
    entity_f1_vi: float
    latency_ms: float
    memory_mb: float
    cache_size_bytes: int
    english_baseline: float

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.license.strip():
            raise EncoderSelectionError("candidate model and license must be explicit")
        if len(self.revision) != 40 or any(c not in "0123456789abcdef" for c in self.revision):
            raise EncoderSelectionError("candidate revision must be pinned to 40 lower-case hex")
        if len(self.artifact_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.artifact_sha256
        ):
            raise EncoderSelectionError("candidate artifact must have a lower-case SHA-256")
        if (
            not isinstance(self.dimension, int)
            or isinstance(self.dimension, bool)
            or self.dimension <= 0
        ):
            raise EncoderSelectionError("candidate dimension must be positive")
        if self.normalization != "l2":
            raise EncoderSelectionError("candidate normalization must be l2")
        metrics = (
            self.english_metric,
            self.vietnamese_metric,
            self.unaccented_metric,
            self.schema_recall_at_5_en,
            self.schema_recall_at_5_vi,
            self.schema_recall_at_10_en,
            self.schema_recall_at_10_vi,
            self.schema_mrr_en,
            self.schema_mrr_vi,
            self.entity_top1_en,
            self.entity_top1_vi,
            self.entity_f1_en,
            self.entity_f1_vi,
            self.english_baseline,
        )
        if any(
            not isinstance(value, float)
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in metrics
        ):
            raise EncoderSelectionError("candidate metrics must be finite floats in [0, 1]")
        if (
            not isinstance(self.latency_ms, float)
            or not math.isfinite(self.latency_ms)
            or self.latency_ms <= 0
        ):
            raise EncoderSelectionError("candidate latency must be a positive finite float")
        if (
            not isinstance(self.memory_mb, float)
            or not math.isfinite(self.memory_mb)
            or self.memory_mb <= 0
        ):
            raise EncoderSelectionError("candidate memory must be a positive finite float")
        if (
            not isinstance(self.cache_size_bytes, int)
            or isinstance(self.cache_size_bytes, bool)
            or self.cache_size_bytes <= 0
        ):
            raise EncoderSelectionError("candidate cache size must be a positive integer")


@dataclass(frozen=True, slots=True)
class EncoderScore:
    """Canonical development score for one pinned encoder."""

    model_id: str
    revision: str
    artifact_sha256: str
    license: str
    dimension: int
    normalization: str
    english_metric: float
    vietnamese_metric: float
    unaccented_metric: float
    schema_recall_at_5_en: float
    schema_recall_at_5_vi: float
    schema_recall_at_10_en: float
    schema_recall_at_10_vi: float
    schema_mrr_en: float
    schema_mrr_vi: float
    entity_top1_en: float
    entity_top1_vi: float
    entity_f1_en: float
    entity_f1_vi: float
    latency_ms: float
    memory_mb: float
    cache_size_bytes: int
    english_baseline: float
    development_sha256s: tuple[str, str, str]
    report_sha256: str

    def recompute_sha256(self) -> str:
        """Recompute the score digest without trusting the stored value."""
        body = asdict(self)
        body.pop("report_sha256")
        return _canonical_sha256(body)


def evaluate_encoder_candidate(
    candidate: EncoderCandidate,
    development_sets: DevelopmentSets,
) -> EncoderScore:
    """Bind one candidate's measured metrics to development-only input hashes."""
    body = {
        **asdict(candidate),
        "development_sha256s": (
            development_sets.english_sha256,
            development_sets.vietnamese_sha256,
            development_sets.unaccented_sha256,
        ),
    }
    return EncoderScore(**body, report_sha256=_canonical_sha256(body))


@dataclass(frozen=True, slots=True)
class EncoderSelection:
    """Deterministic ranking and selected multilingual encoder evidence."""

    winner_model_id: str
    winner_revision: str
    ranked_model_ids: tuple[str, ...]
    rejected_model_ids: tuple[str, ...]
    english_regression_limit: float
    selection_rule: str
    score_sha256s: tuple[str, ...]
    report_sha256: str

    def recompute_sha256(self) -> str:
        """Recompute the selection digest without trusting the stored value."""
        body = asdict(self)
        body.pop("report_sha256")
        return _canonical_sha256(body)


def select_encoder(
    candidates: tuple[EncoderScore, ...],
    *,
    english_regression_limit: float = 0.02,
) -> EncoderSelection:
    """Select by Vietnamese, English, latency, and model ID after regression gating."""
    if (
        not isinstance(english_regression_limit, float)
        or not 0.0 <= english_regression_limit <= 1.0
    ):
        raise EncoderSelectionError("English regression limit must be a float in [0, 1]")
    if not candidates or len({score.model_id for score in candidates}) != len(candidates):
        raise EncoderSelectionError("encoder scores must be non-empty with unique model IDs")
    for score in candidates:
        if score.report_sha256 != score.recompute_sha256():
            raise EncoderSelectionError("encoder score digest mismatch")
    eligible = tuple(
        score
        for score in candidates
        if score.english_baseline - score.english_metric <= english_regression_limit + 1e-12
    )
    rejected = tuple(sorted(set(candidates) - set(eligible), key=lambda score: score.model_id))
    if not eligible:
        raise EncoderSelectionError("all candidates exceed the English regression limit")
    ranked = tuple(
        sorted(
            eligible,
            key=lambda score: (
                -score.vietnamese_metric,
                -score.english_metric,
                score.latency_ms,
                score.model_id,
            ),
        )
    )
    body = {
        "winner_model_id": ranked[0].model_id,
        "winner_revision": ranked[0].revision,
        "ranked_model_ids": tuple(score.model_id for score in ranked),
        "rejected_model_ids": tuple(score.model_id for score in rejected),
        "english_regression_limit": english_regression_limit,
        "selection_rule": SELECTION_RULE,
        "score_sha256s": tuple(score.report_sha256 for score in (*ranked, *rejected)),
    }
    return EncoderSelection(**body, report_sha256=_canonical_sha256(body))
