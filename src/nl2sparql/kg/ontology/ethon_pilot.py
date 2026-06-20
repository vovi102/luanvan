"""Deterministic helpers for inspecting the committed EthOn ontology."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS


@dataclass(frozen=True)
class EthonInventory:
    """Explicitly declared EthOn terms and subclass relationships.

    Attributes:
        classes: IRIs explicitly declared as OWL classes.
        object_properties: IRIs explicitly declared as OWL object properties.
        datatype_properties: IRIs explicitly declared as OWL datatype properties.
        subclass_relations: Explicit child-parent subclass IRI pairs.
    """

    classes: tuple[str, ...]
    object_properties: tuple[str, ...]
    datatype_properties: tuple[str, ...]
    subclass_relations: tuple[tuple[str, str], ...]


def load_ethon(path: Path) -> Graph:
    """Load an EthOn Turtle document into an RDF graph.

    Args:
        path: Path to the local Turtle document.

    Returns:
        The parsed RDF graph.

    Raises:
        FileNotFoundError: If the ontology path does not exist.
        ValueError: If the document is empty or parses to an empty graph.
    """
    if not path.exists():
        raise FileNotFoundError(f"EthOn ontology not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"EthOn ontology is empty: {path}")

    graph = Graph()
    graph.parse(path, format="turtle")
    if not graph:
        raise ValueError(f"EthOn ontology parsed to an empty graph: {path}")
    return graph


def inspect_ethon(graph: Graph) -> EthonInventory:
    """Build a deterministic inventory from explicit EthOn declarations.

    Args:
        graph: Parsed RDF graph to inspect without applying inference.

    Returns:
        A sorted inventory of classes, properties, and subclass pairs.

    Raises:
        ValueError: If required explicit class or property declarations are absent.
    """
    classes = _typed_uri_subjects(graph, OWL.Class)
    object_properties = _typed_uri_subjects(graph, OWL.ObjectProperty)
    datatype_properties = _typed_uri_subjects(graph, OWL.DatatypeProperty)

    if not classes:
        raise ValueError("EthOn graph has no explicitly declared classes")
    if not object_properties and not datatype_properties:
        raise ValueError("EthOn graph has no explicitly declared object or datatype properties")

    subclass_relations = tuple(
        sorted(
            (str(child), str(parent))
            for child, parent in graph.subject_objects(RDFS.subClassOf)
            if isinstance(child, URIRef) and isinstance(parent, URIRef)
        )
    )
    return EthonInventory(
        classes=classes,
        object_properties=object_properties,
        datatype_properties=datatype_properties,
        subclass_relations=subclass_relations,
    )


def render_class_inventory(inventory: EthonInventory, checksum: str) -> str:
    """Render a deterministic Markdown inventory of EthOn classes.

    Args:
        inventory: Inventory whose class IRIs should be rendered.
        checksum: SHA-256 checksum of the source ontology.

    Returns:
        Markdown ending in exactly one newline.
    """
    classes = sorted(inventory.classes)
    lines = [
        "# EthOn Classes",
        "",
        f"Source SHA-256: `{checksum}`",
        "",
        f"Total classes: {len(classes)}",
        "",
        *(_term_entry(iri) for iri in classes),
    ]
    return "\n".join(lines) + "\n"


def render_property_inventory(inventory: EthonInventory, checksum: str) -> str:
    """Render deterministic Markdown inventories of EthOn properties.

    Args:
        inventory: Inventory whose property IRIs should be rendered.
        checksum: SHA-256 checksum of the source ontology.

    Returns:
        Markdown ending in exactly one newline.
    """
    object_properties = sorted(inventory.object_properties)
    datatype_properties = sorted(inventory.datatype_properties)
    lines = [
        "# EthOn Properties",
        "",
        f"Source SHA-256: `{checksum}`",
        "",
        f"Object properties: {len(object_properties)}",
        f"Datatype properties: {len(datatype_properties)}",
        "",
        "## Object properties",
        "",
        *(_term_entry(iri) for iri in object_properties),
        "",
        "## Datatype properties",
        "",
        *(_term_entry(iri) for iri in datatype_properties),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _typed_uri_subjects(graph: Graph, rdf_type: URIRef) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(subject)
            for subject in graph.subjects(RDF.type, rdf_type)
            if isinstance(subject, URIRef)
        )
    )


def _term_entry(iri: str) -> str:
    return f"- `{_local_name(iri)}` — <{iri}>"


def _local_name(iri: str) -> str:
    base, fragment = urldefrag(iri)
    if fragment:
        return fragment
    path = urlparse(base).path.rstrip("/")
    return path.rsplit("/", maxsplit=1)[-1] or iri
