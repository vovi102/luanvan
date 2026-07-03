"""Run the T2.4 full Morph-KGC mapping scaffold."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import morph_kgc
from rdflib import Graph

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


def materialize_full(
    mapping_path: Path,
    output_path: Path,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
) -> Graph:
    """Materialize, serialize, reparse, and validate the full mapping."""
    graph = morph_kgc.materialize(build_morph_config(mapping_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_path, format="nt")
    validate_full_output(output_path, minimum_triples=minimum_triples)
    return Graph().parse(output_path, format="nt")


def validate_full_output(
    output_path: Path,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
) -> int:
    """Parse an existing full output artifact and validate triple count."""
    if not output_path.is_file():
        raise FullMaterializationError(f"Missing full RML output: {output_path}")
    graph = Graph().parse(output_path, format="nt")
    if len(graph) < minimum_triples:
        raise FullMaterializationError(
            f"Morph-KGC produced {len(graph)} triples; minimum is {minimum_triples}"
        )
    return len(graph)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the full RML runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY_PATH)
    parser.add_argument("--entities-csv", type=Path, default=DEFAULT_ENTITIES_CSV_PATH)
    parser.add_argument("--minimum-triples", type=int, default=MINIMUM_FULL_TRIPLES)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run preparation or guarded full materialization."""
    args = parse_args(argv)
    if args.prepare_only:
        count = prepare_entities_csv(args.dictionary.resolve(), args.entities_csv.resolve())
        print(f"Prepared {count} entity rows: {args.entities_csv.resolve()}")
        return 0
    if not args.force and not args.fixture_mode:
        print("Refusing full materialization without --force or --fixture-mode.")
        return 2
    prepare_entities_csv(args.dictionary.resolve(), args.entities_csv.resolve())
    inputs = required_full_input_paths(args.root.resolve())
    validate_required_files(args.mapping.resolve(), inputs)
    graph = materialize_full(
        args.mapping.resolve(),
        args.output.resolve(),
        minimum_triples=args.minimum_triples,
    )
    print(f"Morph-KGC full triples: {len(graph)}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
