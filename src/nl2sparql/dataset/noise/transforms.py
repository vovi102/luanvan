"""Pure, anchor-aware text transformations for T3.4."""

from __future__ import annotations

import json
import re
from pathlib import Path
from random import Random
from typing import Any

from nl2sparql.dataset.noise.contracts import NoiseType, NoiseValidationError

ABBREVIATIONS_PATH = Path(__file__).with_name("abbreviations.json")
WORD_RE = re.compile(r"[A-Za-z]{2,}")
TYPO_WORD_RE = re.compile(r"[A-Za-z]{5,}")
FRAGMENT_PATTERNS = (
    re.compile(
        r"^\s*(?:show me|show|please|could you|can you|would you|list|find)\s+",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:the|a|an)\s+", re.IGNORECASE),
    re.compile(r"\?\s*$"),
)


def load_abbreviations(path: Path = ABBREVIATIONS_PATH) -> dict[str, tuple[str, ...]]:
    """Load and validate the versioned structural abbreviation dictionary."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoiseValidationError(f"unable to load abbreviation dictionary: {path}") from exc
    if not isinstance(payload, dict):
        raise NoiseValidationError("abbreviation dictionary must be a JSON object")
    result: dict[str, tuple[str, ...]] = {}
    for key, raw_options in payload.items():
        if not isinstance(key, str) or not key or key != key.casefold():
            raise NoiseValidationError("abbreviation keys must be non-empty normalized strings")
        if not isinstance(raw_options, list) or not raw_options:
            raise NoiseValidationError(f"abbreviation options for {key!r} must be non-empty")
        if any(not isinstance(option, str) or not option.strip() for option in raw_options):
            raise NoiseValidationError(f"abbreviation options for {key!r} must be strings")
        options = tuple(option.strip() for option in raw_options)
        if len(set(options)) != len(options):
            raise NoiseValidationError(f"abbreviation options for {key!r} must be unique")
        result[key] = options
    return result


def protected_terms(record: dict[str, Any], entity_index: dict[str, dict[str, str]]) -> set[str]:
    """Return case-folded slot values and pinned entity labels that noise cannot edit."""
    terms = {
        str(value).strip().casefold()
        for value in record.get("slot_values", {}).values()
        if str(value).strip()
    }
    for entity in record.get("entities_used", []):
        value = str(entity.get("value", "")).strip().casefold()
        if not value:
            continue
        terms.add(value)
        known = entity_index.get(value)
        if known:
            terms.update(
                str(label).strip().casefold() for label in known.values() if str(label).strip()
            )
    return terms


def _protected_spans(question: str, terms: set[str]) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for term in sorted(terms, key=lambda value: (-len(value), value)):
        spans.extend(
            (match.start(), match.end())
            for match in re.finditer(re.escape(term), question, flags=re.IGNORECASE)
        )
    return tuple(spans)


def _overlaps(start: int, end: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(
        start < protected_end and protected_start < end for protected_start, protected_end in spans
    )


def _replace_span(question: str, start: int, end: int, replacement: str) -> str:
    return question[:start] + replacement + question[end:]


def _typo_candidates(question: str, spans: tuple[tuple[int, int], ...]) -> set[str]:
    candidates: set[str] = set()
    for match in TYPO_WORD_RE.finditer(question):
        if _overlaps(match.start(), match.end(), spans):
            continue
        word = match.group()
        for index in range(1, len(word) - 2):
            if word[index] == word[index + 1]:
                continue
            replacement = word[:index] + word[index + 1] + word[index] + word[index + 2 :]
            candidates.add(_replace_span(question, match.start(), match.end(), replacement))
    return candidates


def _abbreviation_candidates(
    question: str,
    abbreviations: dict[str, tuple[str, ...]],
    spans: tuple[tuple[int, int], ...],
) -> set[str]:
    candidates: list[tuple[int, int, str, tuple[str, ...]]] = []
    for phrase, options in abbreviations.items():
        pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(question):
            if not _overlaps(match.start(), match.end(), spans):
                candidates.append((match.start(), match.end(), phrase, options))
    if not candidates:
        return set()
    longest = max(len(phrase) for _, _, phrase, _ in candidates)
    return {
        _replace_span(question, start, end, option)
        for start, end, phrase, options in candidates
        if len(phrase) == longest
        for option in options
    }


def _fragment_candidates(question: str, spans: tuple[tuple[int, int], ...]) -> set[str]:
    candidates: list[tuple[int, int]] = []
    for pattern in FRAGMENT_PATTERNS:
        candidates.extend(
            (match.start(), match.end())
            for match in pattern.finditer(question)
            if not _overlaps(match.start(), match.end(), spans)
        )
    return {_replace_span(question, start, end, "").strip() for start, end in candidates}


def _mixed_case_candidates(question: str, spans: tuple[tuple[int, int], ...]) -> set[str]:
    candidates = [
        match
        for match in WORD_RE.finditer(question)
        if not _overlaps(match.start(), match.end(), spans)
    ]
    outputs: set[str] = set()
    for match in candidates:
        word = match.group()
        replacement = word.upper()
        if replacement == word:
            replacement = "".join(
                character.upper() if index % 2 == 0 else character.lower()
                for index, character in enumerate(word)
            )
        if replacement != word:
            outputs.add(_replace_span(question, match.start(), match.end(), replacement))
    return outputs


def noise_candidates(
    question: str,
    noise_type: NoiseType,
    abbreviations: dict[str, tuple[str, ...]],
    protected: set[str],
) -> set[str]:
    """Enumerate every text allowed by one declared noise operation."""
    spans = _protected_spans(question, protected)
    if noise_type is NoiseType.TYPO:
        return _typo_candidates(question, spans)
    if noise_type is NoiseType.ABBREV:
        return _abbreviation_candidates(question, abbreviations, spans)
    if noise_type is NoiseType.FRAGMENT:
        return _fragment_candidates(question, spans)
    if noise_type is NoiseType.MIXED_CASE:
        return _mixed_case_candidates(question, spans)
    raise NoiseValidationError(f"unsupported noise type: {noise_type}")


def transform_question(
    question: str,
    noise_type: NoiseType,
    abbreviations: dict[str, tuple[str, ...]],
    protected: set[str],
    rng: Random,
) -> str | None:
    """Apply one eligible noise operation while leaving protected spans untouched."""
    candidates = sorted(noise_candidates(question, noise_type, abbreviations, protected))
    return rng.choice(candidates) if candidates else None
