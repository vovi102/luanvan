from datetime import date
import json
from pathlib import Path

from nl2sparql.kg.extraction.full_extract import (
    compute_full_extract_date_range,
    load_dictionary_addresses,
)


def test_load_dictionary_addresses_deduplicates_and_lowercases(tmp_path: Path) -> None:
    dictionary_path = tmp_path / "entities.json"
    dictionary_path.write_text(
        json.dumps(
            [
                {"address": "0xABCDEF0000000000000000000000000000000000"},
                {"address": "0xabcdef0000000000000000000000000000000000"},
                {"address": "0x1234500000000000000000000000000000000000"},
            ]
        ),
        encoding="utf-8",
    )

    addresses = load_dictionary_addresses(dictionary_path)

    assert addresses == [
        "0x1234500000000000000000000000000000000000",
        "0xabcdef0000000000000000000000000000000000",
    ]


def test_compute_full_extract_date_range_uses_lagged_30_day_window() -> None:
    start_date, end_date = compute_full_extract_date_range(today=date(2026, 6, 28))

    assert start_date.isoformat() == "2026-05-27"
    assert end_date.isoformat() == "2026-06-26"
