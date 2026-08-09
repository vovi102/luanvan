import json
from pathlib import Path

import pytest

from nl2sparql.linking.dictionary import (
    CONCEPTS_PATH,
    ENTITIES_PATH,
    SOURCES_PATH,
)
from nl2sparql.linking.dictionary.schema import DictionaryValidationError
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts, validate_artifacts


def test_validate_artifacts_reports_missing_files(tmp_path):
    artifacts = DictionaryArtifacts(
        entities_path=tmp_path / "entities.json",
        concepts_path=tmp_path / "concepts.json",
        aliases_path=tmp_path / "aliases.json",
        sources_path=tmp_path / "sources.md",
    )

    with pytest.raises(DictionaryValidationError, match="Missing dictionary artifact"):
        validate_artifacts(artifacts, min_entities=1, min_aliases=1)


def test_committed_dictionary_artifacts_meet_t2_2_thresholds():
    report = validate_artifacts(min_entities=3000, min_aliases=1000)

    assert report["entity_count"] >= 3000
    assert 8 <= report["concept_count"] <= 12
    assert report["alias_count"] >= 1000


def test_committed_dictionary_covers_required_exchange_and_defi_owners():
    entities = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
    concepts = json.loads(CONCEPTS_PATH.read_text(encoding="utf-8"))
    coverage = json.loads(
        Path("data/entity_dictionary/curated/coverage.json").read_text(encoding="utf-8")
    )
    owners = {entry["owner"] for entry in entities}

    required_exchanges = set(coverage["top_exchanges"])
    required_defi = set(coverage["top_defi_protocols"])

    assert len(required_exchanges) == 30
    assert len(required_defi) == 50
    assert required_exchanges <= owners
    assert required_defi <= owners
    assert set(concepts["exchange"]["instances"]) >= required_exchanges
    assert SOURCES_PATH.exists()


def test_sources_document_failed_manual_verification_boundary():
    text = SOURCES_PATH.read_text(encoding="utf-8")

    assert "Retrieved date: 2026-06-28" in text
    assert "Manual verification: failed on 2026-08-09" in text
    assert "entity-dictionary-manual-sample-2026-08-09.md" in text
    assert "rebuilt" in text
    assert "chain-aware" in text
    assert "Automated acceptance criteria" in text
    assert "live scraping is not required" in text
