"""Run the T2.4 full Morph-KGC mapping scaffold."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "src/nl2sparql/kg/rml/full_mapping.ttl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/processed/full/output.nt"
DEFAULT_DICTIONARY_PATH = PROJECT_ROOT / "src/nl2sparql/linking/dictionary/entities.json"
DEFAULT_ENTITIES_CSV_PATH = PROJECT_ROOT / "data/raw/full/entities.csv"
MINIMUM_FULL_TRIPLES = 1_000
ENTITY_CSV_FIELDS = (
    "address",
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "aliases",
)


class FullMaterializationError(RuntimeError):
    """Report invalid full RML inputs or outputs."""


def required_full_input_paths(root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return the CSV paths required by T2.4 full materialization."""
    full_dir = root / "data/raw/full"
    return (
        full_dir / "transactions.csv",
        full_dir / "blocks.csv",
        full_dir / "token_transfers.csv",
        full_dir / "contracts.csv",
        full_dir / "entities.csv",
    )


def validate_required_files(mapping_path: Path, input_paths: Sequence[Path]) -> None:
    """Fail once with every missing mapping or input path."""
    missing = [path for path in (mapping_path, *input_paths) if not path.is_file()]
    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise FullMaterializationError(f"Missing RML full files:\n{rendered}")


def prepare_entities_csv(
    dictionary_path: Path = DEFAULT_DICTIONARY_PATH,
    output_path: Path = DEFAULT_ENTITIES_CSV_PATH,
) -> int:
    """Convert dictionary JSON to a flat CSV source for Morph-KGC."""
    entities: list[dict[str, Any]] = json.loads(dictionary_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENTITY_CSV_FIELDS)
        writer.writeheader()
        for entity in entities:
            aliases = entity.get("aliases") or []
            writer.writerow(
                {
                    "address": str(entity.get("address_lower") or entity["address"]).lower(),
                    "primary_label": entity.get("primary_label", ""),
                    "owner": entity.get("owner", ""),
                    "category": entity.get("category", ""),
                    "concept_class": entity.get("concept_class", "Account"),
                    "aliases": "|".join(str(alias) for alias in aliases),
                }
            )
    return len(entities)


def build_morph_config(
    mapping_path: Path,
    output_format: str = "N-TRIPLES",
    number_of_processes: int = 4,
) -> str:
    """Build the in-memory Morph-KGC configuration for the full mapping."""
    return (
        "[CONFIGURATION]\n"
        f"output_format: {output_format}\n"
        f"number_of_processes: {number_of_processes}\n\n"
        "[DataSource1]\n"
        f"mappings: {mapping_path.resolve()}\n"
    )
