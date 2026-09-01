from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl2sparql.models.b12 import SmallLLMError, compile_catalog_summary
from nl2sparql.sql.schema import CATALOG_PATH


def test_summary_covers_every_managed_relation_and_field() -> None:
    result = compile_catalog_summary(CATALOG_PATH)
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    for relation_id, relation in catalog["analytical_relations"].items():
        assert f"Relation {relation_id}" in result.text
        for field_name in relation["fields"]:
            assert f"  - {field_name}:" in result.text
    assert result.catalog_sha256 == hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
    assert result.summary_sha256 == hashlib.sha256(result.text.encode("utf-8")).hexdigest()


def test_summary_includes_join_and_bounded_query_rules() -> None:
    result = compile_catalog_summary(CATALOG_PATH)

    assert "Join transaction_to_block" in result.text
    assert "half-open [start_date, end_date)" in result.text
    assert "Use explicit projections" in result.text
    assert "managed relations only" in result.text


def test_summary_fails_instead_of_truncating_catalog() -> None:
    with pytest.raises(SmallLLMError, match="summary exceeds"):
        compile_catalog_summary(CATALOG_PATH, max_chars=100)


def test_summary_validates_the_exact_bytes_that_it_fingerprints(tmp_path: Path) -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog["dialect"] = "legacy_sql"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(SmallLLMError, match="catalog"):
        compile_catalog_summary(path)


@pytest.mark.parametrize("max_chars", [0, -1, True])
def test_summary_requires_positive_character_budget(max_chars: object) -> None:
    with pytest.raises(SmallLLMError, match="max_chars"):
        compile_catalog_summary(CATALOG_PATH, max_chars=max_chars)  # type: ignore[arg-type]
