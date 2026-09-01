"""Fail-closed whole-output GoogleSQL extraction."""

from __future__ import annotations

import re

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.models.b12.contracts import ExtractionStatus, SmallLLMError

_FENCE_RE = re.compile(
    r"\A```(?:sql|googlesql)?[ \t]*\n(?P<body>[\s\S]*?)\n```[ \t]*\Z",
    flags=re.IGNORECASE,
)
_LEADING_KEYWORD_RE = re.compile(r"\A([A-Za-z]+)\b")
_UNSAFE_KEYWORDS = frozenset(
    {
        "ALTER",
        "CALL",
        "CREATE",
        "DELETE",
        "DROP",
        "EXECUTE",
        "INSERT",
        "MERGE",
        "TRUNCATE",
        "UPDATE",
    }
)


def extract_google_sql(raw: str) -> tuple[str | None, ExtractionStatus]:
    """Accept a complete safe query or classify why the whole response failed."""
    if not isinstance(raw, str):
        raise SmallLLMError("raw model output must be a string")
    candidate = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not candidate:
        return None, "empty"

    fence = _FENCE_RE.fullmatch(candidate)
    if fence is not None:
        candidate = fence.group("body").strip()
        if not candidate:
            return None, "empty"
    elif "```" in candidate:
        return None, "prose"

    keyword_match = _LEADING_KEYWORD_RE.match(candidate)
    if keyword_match is None:
        return None, "prose"
    keyword = keyword_match.group(1).upper()
    if keyword in _UNSAFE_KEYWORDS:
        return None, "unsafe_sql"
    if keyword not in {"SELECT", "WITH"}:
        return None, "prose"

    try:
        validate_sql_text(candidate)
    except TestSetError as exc:
        status: ExtractionStatus = (
            "invalid_sql" if str(exc).startswith("invalid GoogleSQL:") else "unsafe_sql"
        )
        return None, status
    return candidate, "ok"
