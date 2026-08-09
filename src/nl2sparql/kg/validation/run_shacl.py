"""Run SHACL validation for local Ethereum KG RDF artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from pyshacl import validate
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data/processed/full/output.nt"
DEFAULT_SHAPES_PATH = PROJECT_ROOT / "src/nl2sparql/kg/validation/shapes.ttl"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data/processed/full/shacl_report.ttl"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "src/nl2sparql/kg/validation/violations_summary.md"
SH = Namespace("http://www.w3.org/ns/shacl#")


@dataclass(frozen=True)
class ShaclValidationResult:
    """Container for pySHACL validation output."""

    conforms: bool
    results_graph: Graph
    results_text: str
    report_path: Path


class ViolationSummary(NamedTuple):
    """Grouped SHACL validation result."""

    path: str
    message: str
    count: int


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


def _compact_term(value: object | None) -> str:
    if value is None:
        return "(none)"
    text = str(value)
    prefix = "https://thesis.example.org/eth-kg/"
    if text.startswith(prefix):
        return f":{text.removeprefix(prefix)}"
    return text


def summarize_validation_report(report_graph: Graph) -> list[ViolationSummary]:
    """Group SHACL validation results by result path and message."""
    counter: Counter[tuple[str, str]] = Counter()
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        path = _compact_term(report_graph.value(result, SH.resultPath))
        message = _compact_term(report_graph.value(result, SH.resultMessage))
        counter[(path, message)] += 1
    return [
        ViolationSummary(path=path, message=message, count=count)
        for (path, message), count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    ]


def write_violations_summary(
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    result: ShaclValidationResult | None = None,
    source_data_path: Path = DEFAULT_DATA_PATH,
    shapes_path: Path = DEFAULT_SHAPES_PATH,
) -> Path:
    """Write a markdown summary for a SHACL validation result."""
    if result is None:
        raise ValueError("result is required to write a SHACL summary")
    summaries = summarize_validation_report(result.results_graph)
    lines = [
        "# SHACL Validation Summary",
        "",
        f"Source data: `{source_data_path}`",
        f"Shapes: `{shapes_path}`",
        f"Report: `{result.report_path}`",
        f"Conforms: {str(result.conforms).lower()}",
        "",
        "## Validation Results",
        "",
    ]
    if not summaries:
        lines.append("No SHACL violations were reported.")
    else:
        lines.extend(
            [
                "| Path | Message | Count |",
                "|---|---|---:|",
            ]
        )
        lines.extend(
            f"| `{summary.path}` | {summary.message} | {summary.count} |" for summary in summaries
        )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for local SHACL validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--shapes", type=Path, default=DEFAULT_SHAPES_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--data-format", default=None)
    parser.add_argument("--inference", default="rdfs")
    parser.add_argument("--allow-nonconform", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run local SHACL validation and write report artifacts."""
    args = parse_args(argv)
    result = run_shacl_validation(
        data_path=args.data,
        shapes_path=args.shapes,
        report_path=args.report,
        data_format=args.data_format,
        inference=args.inference,
    )
    write_violations_summary(
        summary_path=args.summary,
        result=result,
        source_data_path=args.data,
        shapes_path=args.shapes,
    )
    print(f"Conforms: {result.conforms}")
    print(f"Report: {args.report}")
    print(f"Summary: {args.summary}")
    if result.conforms or args.allow_nonconform:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
