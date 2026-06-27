from __future__ import annotations

import argparse
import csv
from pathlib import Path

FIELDS = [
    "address",
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "aliases",
    "source_name",
    "source_url",
    "retrieved_date",
    "confidence",
]


def write_rows(rows: list[dict[str, str]], output: Path) -> None:
    """Write reviewed Ethereum label rows to the raw T2.2 snapshot CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Write reviewed Ethereum label rows to the T2.2 raw snapshot CSV. "
            "This command intentionally does not fabricate or live-scrape labels."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/entity_dictionary/raw/entities.csv"),
    )
    parser.parse_args()
    raise SystemExit(
        "This fetcher is intentionally fail-fast. Add explicitly reviewed rows "
        "from source snapshots, then call write_rows(rows, output)."
    )


if __name__ == "__main__":
    main()
