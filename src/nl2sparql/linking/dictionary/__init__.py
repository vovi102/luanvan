"""Entity dictionary artifacts and validation helpers for Ethereum KG linking."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ENTITIES_PATH = PACKAGE_DIR / "entities.json"
CONCEPTS_PATH = PACKAGE_DIR / "concepts.json"
ALIASES_PATH = PACKAGE_DIR / "aliases.json"
SOURCES_PATH = PACKAGE_DIR / "sources.md"

__all__ = [
    "PACKAGE_DIR",
    "ENTITIES_PATH",
    "CONCEPTS_PATH",
    "ALIASES_PATH",
    "SOURCES_PATH",
]
