"""Full BigQuery extraction helpers for the Ethereum KG dataset."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DICTIONARY_PATH = Path("src/nl2sparql/linking/dictionary/entities.json")
DEFAULT_OUTPUT_DIR = Path("data/raw/full")


def compute_full_extract_date_range(today: date | None = None) -> tuple[date, date]:
    """Return the lagged 30-day extraction window.

    The public BigQuery Ethereum dataset can lag behind chain head. Using a
    two-day lag avoids extracting dates that may still be incomplete.
    """
    reference_date = today or date.today()
    end_date = reference_date - timedelta(days=2)
    start_date = end_date - timedelta(days=30)
    return start_date, end_date


def load_dictionary_addresses(dictionary_path: Path = DEFAULT_DICTIONARY_PATH) -> list[str]:
    """Load unique lower-case Ethereum addresses from the entity dictionary."""
    raw_entities: list[dict[str, Any]] = json.loads(dictionary_path.read_text(encoding="utf-8"))
    addresses = {
        str(entity["address"]).lower()
        for entity in raw_entities
        if entity.get("address")
    }
    return sorted(addresses)
