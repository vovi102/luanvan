"""Run the T2.4 full Morph-KGC mapping scaffold."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import morph_kgc
from rdflib import Graph

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "src/nl2sparql/kg/rml/full_mapping.ttl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/processed/full/output.nt"
DEFAULT_DICTIONARY_PATH = PROJECT_ROOT / "src/nl2sparql/linking/dictionary/entities.json"
DEFAULT_ENTITIES_CSV_PATH = PROJECT_ROOT / "data/raw/full/entities.csv"
MINIMUM_FULL_TRIPLES = 1_000
DEFAULT_CHUNK_ROWS = 50_000
FULL_SOURCE_FILENAMES = (
    "transactions.csv",
    "blocks.csv",
    "token_transfers.csv",
    "contracts.csv",
    "entities.csv",
)
ENTITY_CSV_FIELDS = (
    "address",
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "aliases",
)


class FullMaterializationError(RuntimeError):
    """Report invalid full RML inputs or outputs."""


def required_full_input_paths(root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return the CSV paths required by T2.4 full materialization."""
    full_dir = root / "data/raw/full"
    return tuple(full_dir / filename for filename in FULL_SOURCE_FILENAMES)


def validate_required_files(mapping_path: Path, input_paths: Sequence[Path]) -> None:
    """Fail once with every missing mapping or input path."""
    missing = [path for path in (mapping_path, *input_paths) if not path.is_file()]
    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise FullMaterializationError(f"Missing RML full files:\n{rendered}")


def prepare_entities_csv(
    dictionary_path: Path = DEFAULT_DICTIONARY_PATH,
    output_path: Path = DEFAULT_ENTITIES_CSV_PATH,
) -> int:
    """Convert dictionary JSON to a flat CSV source for Morph-KGC."""
    entities: list[dict[str, Any]] = json.loads(dictionary_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENTITY_CSV_FIELDS)
        writer.writeheader()
        for entity in entities:
            aliases = entity.get("aliases") or []
            writer.writerow(
                {
                    "address": str(entity.get("address_lower") or entity["address"]).lower(),
                    "primary_label": entity.get("primary_label", ""),
                    "owner": entity.get("owner", ""),
                    "category": entity.get("category", ""),
                    "concept_class": entity.get("concept_class", "Account"),
                    "aliases": "|".join(str(alias) for alias in aliases),
                }
            )
    return len(entities)


def build_morph_config(
    mapping_path: Path,
    output_format: str = "N-TRIPLES",
    number_of_processes: int = 4,
) -> str:
    """Build the in-memory Morph-KGC configuration for the full mapping."""
    return (
        "[CONFIGURATION]\n"
        f"output_format: {output_format}\n"
        f"number_of_processes: {number_of_processes}\n\n"
        "[DataSource1]\n"
        f"mappings: {mapping_path.resolve()}\n"
    )


def _csv_data_row_count(csv_path: Path) -> int:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def _write_csv_chunk(source_path: Path, output_path: Path, start: int, limit: int) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with (
        source_path.open(newline="", encoding="utf-8") as source,
        output_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as output,
    ):
        reader = csv.reader(source)
        writer = csv.writer(output)
        header = next(reader)
        writer.writerow(header)
        for index, row in enumerate(reader):
            if index < start:
                continue
            if index >= start + limit:
                break
            writer.writerow(row)
            written += 1
    return written


def _mapping_for_chunk(
    mapping_path: Path, chunk_sources: dict[str, Path], output_path: Path
) -> Path:
    mapping_text = mapping_path.read_text(encoding="utf-8")
    for filename, source_path in chunk_sources.items():
        mapping_text = mapping_text.replace(
            f"data/raw/full/{filename}",
            source_path.as_posix(),
        )
    output_path.write_text(mapping_text, encoding="utf-8")
    return output_path


def _materialize_mapping_to_nt(
    mapping_path: Path,
    output_path: Path,
    number_of_processes: int,
) -> int:
    graph = morph_kgc.materialize(
        build_morph_config(mapping_path, number_of_processes=number_of_processes)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_path, format="nt")
    return len(graph)


def _completed_chunk_triples(chunk_dir: Path) -> int | None:
    output_path = chunk_dir / "output.nt"
    completion_path = chunk_dir / "complete.json"
    if not output_path.is_file() or not completion_path.is_file():
        return None
    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        triple_count = int(completion["triple_count"])
        output_size = int(completion["output_size"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if triple_count < 1 or output_path.stat().st_size != output_size:
        return None
    return triple_count


def _commit_completed_chunk(chunk_dir: Path, triple_count: int) -> None:
    output_path = chunk_dir / "output.nt"
    completion_path = chunk_dir / "complete.json"
    completion_path.write_text(
        json.dumps(
            {"output_size": output_path.stat().st_size, "triple_count": triple_count},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _run_manifest(
    mapping_path: Path, input_paths: Sequence[Path], chunk_rows: int
) -> dict[str, Any]:
    return {
        "version": 1,
        "chunk_rows": chunk_rows,
        "mapping_sha256": _file_sha256(mapping_path),
        "inputs": {
            path.name: {"size": path.stat().st_size, "sha256": _file_sha256(path)}
            for path in input_paths
        },
    }


def materialize_full(
    mapping_path: Path,
    output_path: Path,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
) -> Graph:
    """Materialize, serialize, reparse, and validate the full mapping."""
    graph = morph_kgc.materialize(build_morph_config(mapping_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_path, format="nt")
    validate_full_output(output_path, minimum_triples=minimum_triples)
    return Graph().parse(output_path, format="nt")


def materialize_full_chunked(
    mapping_path: Path,
    input_dir: Path,
    output_path: Path,
    work_dir: Path | None = None,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
    number_of_processes: int = 1,
    resume: bool = False,
) -> int:
    """Materialize full CSV inputs with bounded, resumable N-Triples chunks."""
    if chunk_rows < 1:
        raise ValueError("chunk_rows must be >= 1")
    input_paths = tuple(input_dir / filename for filename in FULL_SOURCE_FILENAMES)
    validate_required_files(mapping_path, input_paths)

    row_counts = {
        filename: _csv_data_row_count(input_dir / filename) for filename in FULL_SOURCE_FILENAMES
    }
    total_chunks = max(
        1,
        max(math.ceil(count / chunk_rows) for count in row_counts.values()),
    )
    chunk_root = work_dir or output_path.parent / "chunks"
    expected_manifest = _run_manifest(mapping_path, input_paths, chunk_rows)
    manifest_path = chunk_root / "manifest.json"
    if resume:
        if not manifest_path.is_file():
            raise FullMaterializationError(
                f"Resume manifest is missing: {manifest_path}. Start a new run without --resume."
            )
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest != expected_manifest:
            raise FullMaterializationError(
                "Resume manifest does not match the mapping, inputs, or chunk size. "
                "Start a new run without --resume."
            )
    if chunk_root.exists() and not resume:
        shutil.rmtree(chunk_root)
    chunk_root.mkdir(parents=True, exist_ok=True)
    if not resume:
        manifest_path.write_text(
            json.dumps(expected_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    total_triples = 0
    for chunk_index in range(total_chunks):
        start = chunk_index * chunk_rows
        chunk_dir = chunk_root / f"chunk-{chunk_index:05d}"
        chunk_output = chunk_dir / "output.nt"
        completed_triples = _completed_chunk_triples(chunk_dir) if resume else None
        if completed_triples is not None:
            chunk_triples = completed_triples
        else:
            (chunk_dir / "complete.json").unlink(missing_ok=True)
            chunk_sources: dict[str, Path] = {}
            for filename in FULL_SOURCE_FILENAMES:
                chunk_source = chunk_dir / filename
                _write_csv_chunk(
                    input_dir / filename,
                    chunk_source,
                    start=start,
                    limit=chunk_rows,
                )
                chunk_sources[filename] = chunk_source

            chunk_mapping = _mapping_for_chunk(
                mapping_path,
                chunk_sources,
                chunk_dir / "full_mapping.ttl",
            )
            chunk_triples = _materialize_mapping_to_nt(
                chunk_mapping,
                chunk_output,
                number_of_processes=number_of_processes,
            )
            _commit_completed_chunk(chunk_dir, chunk_triples)
        total_triples += chunk_triples
        print(
            f"Chunk {chunk_index + 1}/{total_chunks}: "
            f"{chunk_triples} triples; total={total_triples}"
        )

    if total_triples < minimum_triples:
        raise FullMaterializationError(
            f"Morph-KGC produced {total_triples} triples; minimum is {minimum_triples}"
        )
    with output_path.open("wb") as final_handle:
        for chunk_index in range(total_chunks):
            chunk_output = chunk_root / f"chunk-{chunk_index:05d}" / "output.nt"
            with chunk_output.open("rb") as chunk_handle:
                shutil.copyfileobj(chunk_handle, final_handle)
    return total_triples


def validate_full_output(
    output_path: Path,
    minimum_triples: int = MINIMUM_FULL_TRIPLES,
) -> int:
    """Parse an existing full output artifact and validate triple count."""
    if not output_path.is_file():
        raise FullMaterializationError(f"Missing full RML output: {output_path}")
    graph = Graph().parse(output_path, format="nt")
    if len(graph) < minimum_triples:
        raise FullMaterializationError(
            f"Morph-KGC produced {len(graph)} triples; minimum is {minimum_triples}"
        )
    return len(graph)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the full RML runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY_PATH)
    parser.add_argument("--entities-csv", type=Path, default=DEFAULT_ENTITIES_CSV_PATH)
    parser.add_argument("--minimum-triples", type=int, default=MINIMUM_FULL_TRIPLES)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS)
    parser.add_argument("--number-of-processes", type=int, default=1)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--single-shot", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run preparation or guarded full materialization."""
    args = parse_args(argv)
    if args.prepare_only:
        count = prepare_entities_csv(args.dictionary.resolve(), args.entities_csv.resolve())
        print(f"Prepared {count} entity rows: {args.entities_csv.resolve()}")
        return 0
    if not args.force and not args.fixture_mode:
        print("Refusing full materialization without --force or --fixture-mode.")
        return 2
    prepare_entities_csv(args.dictionary.resolve(), args.entities_csv.resolve())
    root = args.root.resolve()
    inputs = required_full_input_paths(root)
    validate_required_files(args.mapping.resolve(), inputs)
    if args.single_shot:
        graph = materialize_full(
            args.mapping.resolve(),
            args.output.resolve(),
            minimum_triples=args.minimum_triples,
        )
        triple_count = len(graph)
    else:
        triple_count = materialize_full_chunked(
            mapping_path=args.mapping.resolve(),
            input_dir=root / "data/raw/full",
            output_path=args.output.resolve(),
            work_dir=args.work_dir.resolve() if args.work_dir else None,
            chunk_rows=args.chunk_rows,
            minimum_triples=args.minimum_triples,
            number_of_processes=args.number_of_processes,
            resume=args.resume,
        )
    print(f"Morph-KGC full triples: {triple_count}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
