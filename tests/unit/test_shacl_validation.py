"""Tests for the T2.5 SHACL validation scaffold."""

from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

from nl2sparql.kg.validation.run_shacl import parse_rdf_graph, run_shacl_validation

ROOT = Path(__file__).resolve().parents[2]
SHAPES_PATH = ROOT / "src/nl2sparql/kg/validation/shapes.ttl"
FIXTURE_DIR = ROOT / "tests/fixtures/shacl"
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


def test_parse_rdf_graph_loads_fixture_turtle() -> None:
    graph = parse_rdf_graph(FIXTURE_DIR / "conforming.ttl")

    assert len(graph) > 0
    assert (EX["tx/0xtx1"], RDF.type, EX.Transaction) in graph


def test_run_shacl_validation_conforming_fixture_writes_report(tmp_path: Path) -> None:
    report_path = tmp_path / "shacl_report.ttl"

    result = run_shacl_validation(
        data_path=FIXTURE_DIR / "conforming.ttl",
        shapes_path=SHAPES_PATH,
        report_path=report_path,
    )

    assert result.conforms is True
    assert result.results_text.startswith("Validation Report")
    assert report_path.is_file()
