import hashlib
from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[2]
ETHON_PATH = ROOT / "data" / "ontologies" / "EthOn.ttl"
ETHON_METADATA_PATH = ROOT / "data" / "ontologies" / "EthOn.sha256"
ETHON_SOURCE = "https://raw.githubusercontent.com/ConsenSys/EthOn/master/EthOn.ttl"
ETHON_SHA256 = "e73e19bf0d6bbb0e28b1497a73e4499ca78ee9c1e8c475fa31e7c821354ce71d"


def test_committed_ethon_parses_and_has_expected_scale() -> None:
    graph = Graph()
    graph.parse(ETHON_PATH, format="turtle")

    assert len(graph) >= 1000


def test_ethon_source_metadata_is_committed() -> None:
    metadata = ETHON_METADATA_PATH.read_text(encoding="utf-8")
    expected_lines = [f"source={ETHON_SOURCE}", f"sha256={ETHON_SHA256}"]

    assert hashlib.sha256(ETHON_PATH.read_bytes()).hexdigest() == ETHON_SHA256
    assert ETHON_PATH.stat().st_size == 86718
    assert metadata.splitlines() == expected_lines
    assert metadata == "\n".join(expected_lines) + "\n"
