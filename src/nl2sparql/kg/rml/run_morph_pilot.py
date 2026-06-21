"""Run the T1.3 Morph-KGC pilot deterministically."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import morph_kgc
from rdflib import Graph

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "src/nl2sparql/kg/rml/pilot_mapping.ttl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/processed/pilot/output.ttl"
MINIMUM_PILOT_TRIPLES = 500


class PilotMaterializationError(RuntimeError):
    """Report invalid pilot inputs or output."""


def required_input_paths(root: Path = PROJECT_ROOT) -> tuple[Path, Path]:
    """Return the transaction and block CSV paths required by T1.3."""
    pilot_dir = root / "data/raw/pilot"
    return (
        pilot_dir / "transactions_pilot.csv",
        pilot_dir / "blocks_pilot.csv",
    )


def validate_required_files(mapping_path: Path, input_paths: Sequence[Path]) -> None:
    """Fail once with every missing mapping or input path."""
    missing = [path for path in (mapping_path, *input_paths) if not path.is_file()]
    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise PilotMaterializationError(f"Missing RML pilot files:\n{rendered}")


def build_morph_config(mapping_path: Path) -> str:
    """Build the in-memory Morph-KGC configuration."""
    return f"[DataSource1]\nmappings: {mapping_path.resolve()}\n"


def materialize_pilot(
    mapping_path: Path,
    output_path: Path,
    minimum_triples: int = MINIMUM_PILOT_TRIPLES,
) -> Graph:
    """Materialize, serialize, reparse, and validate a pilot graph."""
    graph = morph_kgc.materialize(build_morph_config(mapping_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_path, format="turtle")

    parsed = Graph().parse(output_path, format="turtle")
    if len(parsed) < minimum_triples:
        raise PilotMaterializationError(
            f"Morph-KGC produced {len(parsed)} triples; minimum is {minimum_triples}"
        )
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the pilot runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--minimum-triples", type=int, default=MINIMUM_PILOT_TRIPLES)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete local pilot and print its artifact summary."""
    args = parse_args(argv)
    inputs = required_input_paths(args.root.resolve())
    validate_required_files(args.mapping.resolve(), inputs)
    graph = materialize_pilot(
        args.mapping.resolve(),
        args.output.resolve(),
        minimum_triples=args.minimum_triples,
    )
    print(f"Morph-KGC pilot triples: {len(graph)}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
