from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from nl2sparql.linking.dictionary.schema import (
    normalize_address,
    normalize_alias,
    validate_address_role,
    validate_chain_id,
    validate_confidence,
    validate_source_locator,
    validate_source_revision,
)


def _read_rows(raw_path: Path) -> list[dict[str, str]]:
    with raw_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _split_aliases(value: str) -> list[str]:
    return sorted({normalize_alias(part) for part in value.split("|") if part.strip()})


def build_dictionary(raw_path: Path, concepts_path: Path) -> dict[str, Any]:
    concepts = json.loads(concepts_path.read_text(encoding="utf-8"))
    entities: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    ambiguous_aliases: set[str] = set()
    seen_addresses: set[str] = set()

    for concept in concepts.values():
        concept["instances"] = []

    for row in _read_rows(raw_path):
        address_lower = normalize_address(row["address"])
        if address_lower in seen_addresses:
            raise ValueError(f"Duplicate address in raw snapshot: {address_lower}")
        seen_addresses.add(address_lower)
        if row["category"] not in concepts:
            raise ValueError(f"Unknown category: {row['category']}")
        confidence = validate_confidence(row["confidence"])
        entry_aliases = _split_aliases(row["aliases"])
        entry_aliases.append(normalize_alias(row["owner"]))
        entry_aliases = sorted(set(entry_aliases))
        for alias in entry_aliases:
            if alias in ambiguous_aliases:
                continue
            existing = aliases.get(alias)
            if existing is not None and existing != row["owner"]:
                aliases.pop(alias)
                ambiguous_aliases.add(alias)
                continue
            aliases[alias] = row["owner"]
        concepts[row["category"]]["instances"].append(row["owner"])
        entities.append(
            {
                "address": row["address"],
                "address_lower": address_lower,
                "primary_label": row["primary_label"],
                "owner": row["owner"],
                "category": row["category"],
                "concept_class": row["concept_class"],
                "aliases": entry_aliases,
                "chain_id": validate_chain_id(row["chain_id"]),
                "address_role": validate_address_role(row["address_role"]),
                "sources": [
                    {
                        "name": row["source_name"],
                        "url": row["source_url"],
                        "revision": validate_source_revision(row["source_revision"]),
                        "locator": validate_source_locator(row["source_locator"]),
                        "retrieved_date": row["retrieved_date"],
                        "note": (f"{row['address_role'].title()} evidence for {row['owner']}"),
                    }
                ],
                "confidence": confidence,
                "verified_date": row["retrieved_date"],
            }
        )

    for concept in concepts.values():
        concept["instances"] = sorted(set(concept["instances"]))

    return {
        "entities": sorted(
            entities,
            key=lambda entry: (
                entry["category"],
                entry["owner"],
                entry["address_lower"],
            ),
        ),
        "concepts": dict(sorted(concepts.items())),
        "aliases": dict(sorted(aliases.items())),
    }


def write_dictionary(built: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, filename in (
        ("entities", "entities.json"),
        ("concepts", "concepts.json"),
        ("aliases", "aliases.json"),
    ):
        (output_dir / filename).write_text(
            json.dumps(built[key], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build T2.2 entity dictionary artifacts from raw snapshots."
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data/entity_dictionary/raw/entities.csv"),
    )
    parser.add_argument(
        "--concepts",
        type=Path,
        default=Path("data/entity_dictionary/curated/concepts.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/nl2sparql/linking/dictionary"),
    )
    args = parser.parse_args()
    write_dictionary(build_dictionary(args.raw, args.concepts), args.output_dir)


if __name__ == "__main__":
    main()
