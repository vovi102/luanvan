from __future__ import annotations

import pytest

from nl2sparql.models.b12.extraction import extract_google_sql

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("", "empty"),
        (" \n\t", "empty"),
        ("Here is SQL: " + SAFE_SQL, "prose"),
        ("SELECT FROM", "invalid_sql"),
        ("DELETE FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`", "unsafe_sql"),
        (SAFE_SQL + "; " + SAFE_SQL, "unsafe_sql"),
        ("```sql\n" + SAFE_SQL + "\n``` trailing", "prose"),
        ("SELECT * FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`", "unsafe_sql"),
        ("SELECT address FROM `other-project.dataset.table`", "unsafe_sql"),
    ],
)
def test_extraction_fails_closed(raw: str, status: str) -> None:
    assert extract_google_sql(raw) == (None, status)


def test_complete_outer_fence_is_accepted() -> None:
    assert extract_google_sql(f"```sql\r\n{SAFE_SQL}\r\n```") == (SAFE_SQL, "ok")


def test_plain_safe_query_is_accepted_without_canonical_rewrite() -> None:
    raw = "  " + SAFE_SQL + "\n"

    assert extract_google_sql(raw) == (SAFE_SQL, "ok")
