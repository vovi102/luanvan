from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[2]
ETHON_PATH = ROOT / "data" / "ontologies" / "EthOn.ttl"
ETHON_METADATA_PATH = ROOT / "data" / "ontologies" / "EthOn.sha256"


def test_committed_ethon_parses_and_has_expected_scale() -> None:
    graph = Graph()
    graph.parse(ETHON_PATH, format="turtle")

    assert len(graph) >= 1000


def test_ethon_source_metadata_is_committed() -> None:
    metadata = ETHON_METADATA_PATH.read_text(encoding="utf-8")

    assert "sha256=" in metadata
    assert "source=https://raw.githubusercontent.com/ConsenSys/EthOn" in metadata
