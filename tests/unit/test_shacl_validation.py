"""Tests for the T2.5 SHACL validation scaffold."""

from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

ROOT = Path(__file__).resolve().parents[2]
SHAPES_PATH = ROOT / "src/nl2sparql/kg/validation/shapes.ttl"
SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("https://thesis.example.org/eth-kg/")


def test_shapes_parse_and_declare_core_node_shapes() -> None:
    graph = Graph().parse(SHAPES_PATH, format="turtle")

    node_shapes = set(graph.subjects(RDF.type, SH.NodeShape))

    assert len(node_shapes) >= 6
    assert EX.TransactionShape in node_shapes
    assert EX.BlockShape in node_shapes
    assert EX.AccountShape in node_shapes
    assert EX.ExchangeAccountShape in node_shapes
    assert EX.TokenTransferShape in node_shapes
    assert EX.TokenContractShape in node_shapes


def test_shapes_cover_ontology_predicates_used_by_full_mapping() -> None:
    text = SHAPES_PATH.read_text(encoding="utf-8")

    for predicate in (
        ":hasFrom",
        ":hasTo",
        ":hasValue",
        ":emittedInTransaction",
        ":transferredAmount",
        ":hasLabel",
        ":hasOwner",
    ):
        assert predicate in text
