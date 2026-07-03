"""Run the T2.4 full Morph-KGC mapping scaffold."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "src/nl2sparql/kg/rml/full_mapping.ttl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/processed/full/output.nt"
DEFAULT_DICTIONARY_PATH = PROJECT_ROOT / "src/nl2sparql/linking/dictionary/entities.json"
DEFAULT_ENTITIES_CSV_PATH = PROJECT_ROOT / "data/raw/full/entities.csv"
MINIMUM_FULL_TRIPLES = 1_000


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
