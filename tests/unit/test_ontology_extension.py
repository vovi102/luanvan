from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = ROOT / "src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl"
ETHKG = Namespace("https://thesis.example.org/eth-kg/")


@pytest.fixture(scope="module")
def ontology_graph() -> Graph:
    graph = Graph()
    graph.parse(ONTOLOGY_PATH, format="turtle")
    return graph


def _local_terms(graph: Graph, rdf_type) -> set:
    return {
        subject
        for subject in graph.subjects(RDF.type, rdf_type)
        if str(subject).startswith(str(ETHKG))
    }


def _sentence_count(text: str) -> int:
    return len(re.findall(r"[.!?](?:\s|$)", text))


def test_extension_turtle_exists_and_parses(ontology_graph: Graph) -> None:
    assert ONTOLOGY_PATH.exists()
    assert len(ontology_graph) > 0


def test_extension_declares_required_number_of_terms(ontology_graph: Graph) -> None:
    classes = _local_terms(ontology_graph, OWL.Class)
    object_properties = _local_terms(ontology_graph, OWL.ObjectProperty)
    datatype_properties = _local_terms(ontology_graph, OWL.DatatypeProperty)
    assert len(classes) >= 15
    assert len(object_properties | datatype_properties) >= 25


def test_all_local_properties_have_schema_linker_metadata(ontology_graph: Graph) -> None:
    properties = _local_terms(ontology_graph, OWL.ObjectProperty) | _local_terms(
        ontology_graph, OWL.DatatypeProperty
    )
    assert properties

    for prop in sorted(properties, key=str):
        labels = list(ontology_graph.objects(prop, RDFS.label))
        comments = list(ontology_graph.objects(prop, RDFS.comment))
        synonyms = list(ontology_graph.objects(prop, ETHKG.synonyms))
        examples = list(ontology_graph.objects(prop, ETHKG.exampleUsage))
        domains = list(ontology_graph.objects(prop, RDFS.domain))
        ranges = list(ontology_graph.objects(prop, RDFS.range))

        assert labels, f"{prop} missing rdfs:label"
        assert comments, f"{prop} missing rdfs:comment"
        assert synonyms, f"{prop} missing :synonyms"
        assert examples, f"{prop} missing :exampleUsage"
        assert domains, f"{prop} missing rdfs:domain"
        assert ranges, f"{prop} missing rdfs:range"

        comment_text = str(comments[0])
        assert _sentence_count(comment_text) >= 2, f"{prop} comment has fewer than 2 sentences"

        synonym_terms = [term.strip() for term in str(synonyms[0]).split(",") if term.strip()]
        assert len(synonym_terms) >= 3, f"{prop} has fewer than 3 synonyms"
        assert isinstance(examples[0], Literal)
        assert "?" in str(examples[0]), f"{prop} example does not look like a SPARQL fragment"
