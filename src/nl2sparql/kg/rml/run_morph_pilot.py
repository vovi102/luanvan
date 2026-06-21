"""Run the T1.3 Morph-KGC pilot deterministically."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

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
