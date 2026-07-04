"""Run SHACL validation for local Ethereum KG RDF artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyshacl import validate
from rdflib import Graph

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data/processed/full/output.nt"
DEFAULT_SHAPES_PATH = PROJECT_ROOT / "src/nl2sparql/kg/validation/shapes.ttl"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data/processed/full/shacl_report.ttl"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "src/nl2sparql/kg/validation/violations_summary.md"


@dataclass(frozen=True)
class ShaclValidationResult:
    """Container for pySHACL validation output."""

    conforms: bool
    results_graph: Graph
    results_text: str
    report_path: Path


def infer_rdf_format(path: Path) -> str:
    """Infer an RDFLib parser format from a local file suffix."""
    suffix = path.suffix.lower()
    if suffix in {".ttl", ".turtle"}:
        return "turtle"
    if suffix in {".nt", ".ntriples"}:
        return "nt"
    if suffix in {".rdf", ".xml"}:
        return "xml"
    raise ValueError(f"Cannot infer RDF format from suffix: {path}")


def parse_rdf_graph(path: Path, rdf_format: str | None = None) -> Graph:
    """Load an RDF graph from a local file."""
    graph = Graph()
    graph.parse(path, format=rdf_format or infer_rdf_format(path))
    return graph


def run_shacl_validation(
    data_path: Path = DEFAULT_DATA_PATH,
    shapes_path: Path = DEFAULT_SHAPES_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    data_format: str | None = None,
    inference: str = "rdfs",
) -> ShaclValidationResult:
    """Validate a local RDF graph with SHACL shapes and write report TTL."""
    data_graph = parse_rdf_graph(data_path, data_format)
    shapes_graph = parse_rdf_graph(shapes_path, "turtle")
    conforms, results_graph, results_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference=inference,
        advanced=False,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results_graph.serialize(destination=report_path, format="turtle")
    return ShaclValidationResult(
        conforms=bool(conforms),
        results_graph=results_graph,
        results_text=str(results_text),
        report_path=report_path,
    )
