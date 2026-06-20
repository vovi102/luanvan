import hashlib
from pathlib import Path

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.plugins.parsers.notation3 import BadSyntax
from rdflib.plugins.sparql import prepareQuery

from nl2sparql.kg.ontology.ethon_pilot import (
    QUERY_SEPARATOR,
    EthonInventory,
    inspect_ethon,
    load_ethon,
    load_smoke_queries,
    render_class_inventory,
    render_property_inventory,
)

ROOT = Path(__file__).resolve().parents[2]
ETHON_PATH = ROOT / "data" / "ontologies" / "EthOn.ttl"
ETHON_METADATA_PATH = ROOT / "data" / "ontologies" / "EthOn.sha256"
ETHON_SMOKE_PATH = ROOT / "src" / "nl2sparql" / "kg" / "validation" / "ethon_smoke.sparql"
ETHON_SOURCE = "https://raw.githubusercontent.com/ConsenSys/EthOn/master/EthOn.ttl"
ETHON_SHA256 = "e73e19bf0d6bbb0e28b1497a73e4499ca78ee9c1e8c475fa31e7c821354ce71d"
ETHON_NAMESPACE = "http://ethon.consensys.net/"


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


def test_inspect_ethon_finds_explicit_core_terms() -> None:
    inventory = inspect_ethon(load_ethon(ETHON_PATH))

    assert {f"{ETHON_NAMESPACE}{name}" for name in ("Account", "Block", "Tx")} <= set(
        inventory.classes
    )
    assert f"{ETHON_NAMESPACE}containsTx" in inventory.object_properties
    assert f"{ETHON_NAMESPACE}address" in inventory.datatype_properties
    assert (
        f"{ETHON_NAMESPACE}Block",
        f"{ETHON_NAMESPACE}StateTransition",
    ) in inventory.subclass_relations


@pytest.mark.parametrize("property_type", [OWL.ObjectProperty, OWL.DatatypeProperty])
def test_inspect_ethon_accepts_graph_with_one_property_category(property_type: URIRef) -> None:
    graph = Graph()
    graph.add((URIRef("https://example.test/Class"), RDF.type, OWL.Class))
    graph.add((URIRef("https://example.test/property"), RDF.type, property_type))

    inventory = inspect_ethon(graph)

    assert inventory.classes == ("https://example.test/Class",)
    assert inventory.object_properties + inventory.datatype_properties == (
        "https://example.test/property",
    )


def test_inspect_ethon_rejects_graph_without_properties() -> None:
    graph = Graph()
    graph.add((URIRef("https://example.test/Class"), RDF.type, OWL.Class))

    with pytest.raises(ValueError, match="properties"):
        inspect_ethon(graph)


def test_inspect_ethon_filters_blank_node_terms_and_subclass_endpoints() -> None:
    graph = Graph()
    class_iri = URIRef("https://example.test/Class")
    parent_iri = URIRef("https://example.test/Parent")
    object_property_iri = URIRef("https://example.test/objectProperty")
    datatype_property_iri = URIRef("https://example.test/datatypeProperty")
    blank_node = BNode()
    for term in (class_iri, parent_iri, blank_node):
        graph.add((term, RDF.type, OWL.Class))
    graph.add((object_property_iri, RDF.type, OWL.ObjectProperty))
    graph.add((datatype_property_iri, RDF.type, OWL.DatatypeProperty))
    graph.add((blank_node, RDF.type, OWL.ObjectProperty))
    graph.add((blank_node, RDF.type, OWL.DatatypeProperty))
    graph.add((class_iri, RDFS.subClassOf, parent_iri))
    graph.add((blank_node, RDFS.subClassOf, parent_iri))
    graph.add((class_iri, RDFS.subClassOf, blank_node))

    inventory = inspect_ethon(graph)

    assert inventory.classes == (str(class_iri), str(parent_iri))
    assert inventory.object_properties == (str(object_property_iri),)
    assert inventory.datatype_properties == (str(datatype_property_iri),)
    assert inventory.subclass_relations == ((str(class_iri), str(parent_iri)),)


def test_rendered_inventories_are_deterministic_and_end_with_one_newline() -> None:
    inventory = EthonInventory(
        classes=(
            f"{ETHON_NAMESPACE}BlockConcept",
            f"{ETHON_NAMESPACE}AccountConcept",
        ),
        object_properties=(
            f"{ETHON_NAMESPACE}to",
            f"{ETHON_NAMESPACE}containsTx",
        ),
        datatype_properties=(
            f"{ETHON_NAMESPACE}blockHash",
            f"{ETHON_NAMESPACE}address",
        ),
        subclass_relations=(),
    )
    checksum = hashlib.sha256(ETHON_PATH.read_bytes()).hexdigest()

    class_markdown = render_class_inventory(inventory, checksum)
    property_markdown = render_property_inventory(inventory, checksum)

    assert class_markdown.startswith("# EthOn Classes\n")
    assert f"Source SHA-256: `{checksum}`" in class_markdown.splitlines()
    assert "Total classes: 2" in class_markdown
    assert class_markdown.index("AccountConcept") < class_markdown.index("BlockConcept")
    assert class_markdown.endswith("\n") and not class_markdown.endswith("\n\n")
    assert property_markdown.startswith("# EthOn Properties\n")
    assert f"Source SHA-256: `{checksum}`" in property_markdown.splitlines()
    assert "Object properties: 2" in property_markdown
    assert "Datatype properties: 2" in property_markdown
    assert "## Object properties" in property_markdown
    assert "## Datatype properties" in property_markdown
    assert property_markdown.index("containsTx") < property_markdown.index("to`")
    assert property_markdown.index("address") < property_markdown.index("blockHash")
    assert property_markdown.endswith("\n") and not property_markdown.endswith("\n\n")


@pytest.mark.parametrize(
    ("object_properties", "datatype_properties"),
    [
        (("https://example.test/objectProperty",), ()),
        ((), ("https://example.test/datatypeProperty",)),
    ],
)
def test_render_property_inventory_has_one_final_newline_for_single_category(
    object_properties: tuple[str, ...],
    datatype_properties: tuple[str, ...],
) -> None:
    inventory = EthonInventory(
        classes=("https://example.test/Class",),
        object_properties=object_properties,
        datatype_properties=datatype_properties,
        subclass_relations=(),
    )

    markdown = render_property_inventory(inventory, "checksum")

    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")


def test_render_class_inventory_matches_exact_markdown_with_fragment_local_name() -> None:
    inventory = EthonInventory(
        classes=("https://example.test/vocabulary#Widget",),
        object_properties=(),
        datatype_properties=(),
        subclass_relations=(),
    )

    markdown = render_class_inventory(inventory, "abc123")

    assert markdown == (
        "# EthOn Classes\n"
        "\n"
        "Source SHA-256: `abc123`\n"
        "\n"
        "Total classes: 1\n"
        "\n"
        "- `Widget` — <https://example.test/vocabulary#Widget>\n"
    )


def test_render_class_inventory_has_one_final_newline_when_empty() -> None:
    inventory = EthonInventory(
        classes=(),
        object_properties=("https://example.test/objectProperty",),
        datatype_properties=(),
        subclass_relations=(),
    )

    markdown = render_class_inventory(inventory, "checksum")

    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")


def test_load_ethon_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="EthOn ontology not found"):
        load_ethon(tmp_path / "missing.ttl")


def test_load_ethon_rejects_empty_file(tmp_path: Path) -> None:
    empty_path = tmp_path / "empty.ttl"
    empty_path.touch()

    with pytest.raises(ValueError, match="empty"):
        load_ethon(empty_path)


def test_load_ethon_rejects_parsed_graph_without_statements(tmp_path: Path) -> None:
    empty_graph_path = tmp_path / "prefix-only.ttl"
    empty_graph_path.write_text("@prefix example: <https://example.test/> .\n", encoding="utf-8")

    with pytest.raises(ValueError, match="parsed to an empty graph"):
        load_ethon(empty_graph_path)


def test_load_ethon_propagates_malformed_turtle_parse_error(tmp_path: Path) -> None:
    malformed_path = tmp_path / "malformed.ttl"
    malformed_path.write_text("@prefix broken syntax", encoding="utf-8")

    with pytest.raises(BadSyntax):
        load_ethon(malformed_path)


def test_load_smoke_queries_returns_exactly_three_stripped_queries(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.sparql"
    query_path.write_text(
        f"\nSELECT * WHERE {{}}\n{QUERY_SEPARATOR}\n\nASK {{}}\n"
        f"{QUERY_SEPARATOR}\nCONSTRUCT {{}} WHERE {{}}\n",
        encoding="utf-8",
    )

    assert load_smoke_queries(query_path) == (
        "SELECT * WHERE {}",
        "ASK {}",
        "CONSTRUCT {} WHERE {}",
    )


def test_load_smoke_queries_accepts_indented_crlf_separator_lines(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.sparql"
    query_path.write_bytes(
        (
            " SELECT * WHERE {} \r\n"
            f"\t{QUERY_SEPARATOR}  \r\n"
            " ASK {} \r\n"
            f"  {QUERY_SEPARATOR}\t\r\n"
            " CONSTRUCT {} WHERE {} \r\n"
        ).encode()
    )

    assert load_smoke_queries(query_path) == (
        "SELECT * WHERE {}",
        "ASK {}",
        "CONSTRUCT {} WHERE {}",
    )


def test_load_smoke_queries_does_not_split_embedded_marker_text(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.sparql"
    query_path.write_text(
        f'SELECT ("{QUERY_SEPARATOR}" AS ?text) WHERE {{}}\n'
        f"# larger comment containing {QUERY_SEPARATOR} text\n"
        f"{QUERY_SEPARATOR}\n"
        "ASK {}\n"
        f"{QUERY_SEPARATOR}\n"
        "CONSTRUCT {} WHERE {}\n",
        encoding="utf-8",
    )

    queries = load_smoke_queries(query_path)

    assert len(queries) == 3
    assert f'"{QUERY_SEPARATOR}"' in queries[0]
    assert f"containing {QUERY_SEPARATOR} text" in queries[0]


def test_load_smoke_queries_rejects_extra_consecutive_separator(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.sparql"
    query_path.write_text(
        f"SELECT * WHERE {{}}\n{QUERY_SEPARATOR}\n{QUERY_SEPARATOR}\n"
        f"ASK {{}}\n{QUERY_SEPARATOR}\nCONSTRUCT {{}} WHERE {{}}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"expected 3.*actual 3.*slot count 4"):
        load_smoke_queries(query_path)


def test_load_smoke_queries_rejects_empty_middle_slot(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.sparql"
    query_path.write_text(
        f"SELECT * WHERE {{}}\n{QUERY_SEPARATOR}\n{QUERY_SEPARATOR}\nASK {{}}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"expected 3.*actual 2.*slot count 3"):
        load_smoke_queries(query_path)


@pytest.mark.parametrize("query_count", [0, 1, 2, 4])
def test_load_smoke_queries_rejects_wrong_query_count(tmp_path: Path, query_count: int) -> None:
    query_path = tmp_path / "queries.sparql"
    query_path.write_text(
        f"\n{QUERY_SEPARATOR}\n".join(f"SELECT {index} WHERE {{}}" for index in range(query_count)),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=rf"expected 3.*actual {query_count}",
    ):
        load_smoke_queries(query_path)


def test_load_smoke_queries_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="EthOn smoke query file not found"):
        load_smoke_queries(tmp_path / "missing.sparql")


def test_committed_ethon_smoke_artifact_has_three_distinct_query_contracts() -> None:
    content = ETHON_SMOKE_PATH.read_text(encoding="utf-8")
    queries = load_smoke_queries(ETHON_SMOKE_PATH)
    owl_prefix = "PREFIX owl: <http://www.w3.org/2002/07/owl#>"
    rdfs_prefix = "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>"

    assert content.count(QUERY_SEPARATOR) == 2
    assert content.count(owl_prefix) == 3
    assert content.count(rdfs_prefix) == 3
    assert [query.count("SELECT") for query in queries] == [1, 1, 1]
    assert "SELECT ?class ?label" in queries[0]
    assert "?class a owl:Class" in queries[0]
    assert "OPTIONAL" in queries[0] and "rdfs:label" in queries[0]
    assert "SELECT ?property ?domain ?range" in queries[1]
    assert "?property a owl:ObjectProperty" in queries[1]
    assert "rdfs:domain" in queries[1] and "rdfs:range" in queries[1]
    assert "SELECT ?subclass ?superclass" in queries[2]
    assert "?subclass rdfs:subClassOf ?superclass" in queries[2]
    assert "?subclass a owl:Class" in queries[2]
    assert "?superclass a owl:Class" in queries[2]
    assert [
        "ORDER BY ?class ?label",
        "ORDER BY ?property ?domain ?range",
        "ORDER BY ?subclass ?superclass",
    ] == [
        next(line for line in query.splitlines() if line.startswith("ORDER BY"))
        for query in queries
    ]


def test_committed_ethon_smoke_queries_parse_and_return_explicit_results() -> None:
    graph = load_ethon(ETHON_PATH)

    for query in load_smoke_queries(ETHON_SMOKE_PATH):
        prepared_query = prepareQuery(query)

        assert list(graph.query(prepared_query))
