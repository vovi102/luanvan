# T2.4 RML Full Mapping Scaffold Design

## Goal

Build a reproducible scaffold for T2.4 that extends the RML pilot to the full extraction schema, prepares Morph-KGC inputs, and proves the mapping on small fixture CSVs. This scope does not attempt the full 50M+ triple materialization or TDB2 load; those remain explicit evidence steps after the scaffold is stable.

## Scope

Included:

- Create `src/nl2sparql/kg/rml/full_mapping.ttl` for the full CSV layout.
- Create `src/nl2sparql/kg/rml/run_morph_full.py` with input validation, dictionary-to-CSV preparation, Morph-KGC config generation, materialization, output validation, and CLI guardrails.
- Add fixture CSVs under `tests/fixtures/rml/full/` and unit tests that materialize a small graph.
- Update T2.4 documentation to distinguish scaffold completion from live KG-load evidence.

Excluded from this scaffold:

- Running Morph-KGC over `data/raw/full/`.
- Building or loading a Fuseki TDB2 dataset.
- Benchmarking 10 competency queries on the full KG.

## Mapping Contract

The mapping uses the T2.1 namespace `https://thesis.example.org/eth-kg/` and the property names documented in `docs/memory/03-ONTOLOGY_REFERENCE.md`.

TriplesMaps:

- `TransactionMap` reads `transactions.csv` and emits `:Transaction` resources at `:tx/{hash}` with `:hasFrom`, `:hasTo`, `:hasValue`, `:hasGasUsed`, `:hasGasPrice`, `:hasReceiptStatus`, `:hasBlockNumber`, `:hasTimestamp`, and `:includedInBlock`.
- `BlockMap` reads `blocks.csv` and emits `:Block` resources at `:block/{number}` with block number, timestamp, miner, gas used, gas limit, and transaction count.
- `TokenTransferMap` reads `token_transfers.csv` and emits `:TokenTransfer` resources at `:transfer/{transaction_hash}-{log_index}` with transaction, from/to account, token contract, transferred amount, and timestamp.
- `ContractMap` reads `contracts.csv` and emits `:ContractAccount` resources for contract addresses. Token contracts are additionally typed through dictionary labels or token-transfer references.
- `AccountLabelMap` reads a prepared `entities.csv` generated from `src/nl2sparql/linking/dictionary/entities.json`, emits `:Account`, `:hasLabel`, `:hasOwner`, `:hasCategory`, `:hasAlias`, and the class in `concept_class`.

RML should omit triples when a source field is empty. Fixture tests will include a contract-creation transaction with an empty `to_address` and assert no `addr/` IRI is produced.

## Runner Design

`run_morph_full.py` mirrors the pilot runner but keeps full-run risk explicit.

Public functions:

- `required_full_input_paths(root: Path) -> tuple[Path, ...]`: returns the four full CSV paths.
- `validate_required_files(mapping_path: Path, input_paths: Sequence[Path]) -> None`: reports all missing paths at once.
- `prepare_entities_csv(dictionary_path: Path, output_path: Path) -> int`: converts dictionary JSON to Morph-KGC friendly CSV columns `address`, `primary_label`, `owner`, `category`, `concept_class`, and pipe-separated `aliases`.
- `build_morph_config(mapping_path: Path, output_format: str = "N-TRIPLES", number_of_processes: int = 4) -> str`: returns a deterministic Morph-KGC config string.
- `materialize_full(mapping_path: Path, output_path: Path, minimum_triples: int) -> Graph`: materializes, serializes, reparses, and checks the minimum triple count.
- `validate_full_output(output_path: Path, minimum_triples: int) -> int`: parses existing output and returns triple count.

CLI behavior:

- Defaults to `data/raw/full/*.csv`, `data/raw/full/entities.csv`, `src/nl2sparql/kg/rml/full_mapping.ttl`, and `data/processed/full/output.nt`.
- `--prepare-only` creates `entities.csv` and exits.
- Full materialization requires `--force` unless `--fixture-mode` is passed. This prevents accidental multi-hour local runs.
- Output format defaults to N-Triples for large line-based loading.

## Testing

Unit tests cover:

- Required full input path resolution.
- Missing-file error reporting.
- Dictionary JSON to `entities.csv` preparation, including lowercase address preference and alias joining.
- Morph-KGC config shape.
- Production full mapping parses as Turtle and declares all expected sources and TriplesMaps.
- Fixture materialization emits transaction, block, token-transfer, contract, and label triples with ontology-aligned predicates.
- Empty `to_address` does not produce an empty account IRI.

The tests use small fixture CSVs and do not depend on BigQuery credentials, full extraction artifacts, Docker, Fuseki, or network access.

## Documentation

The T2.4 task file will keep live acceptance checkboxes pending. A new local scaffold evidence section records:

- Implemented files.
- Focused test command and result.
- Explanation that live Morph-KGC, TDB2 load, 50M+ triple count, and query benchmarks are not claimed by scaffold tests.

## Risks

Morph-KGC behavior for empty CSV values is verified by fixture tests before relying on it for full output. If the fixture shows invalid empty IRIs, the implementation will add a preprocessing step that writes null-safe CSVs before materialization.

Full-run scale remains the main operational risk. The scaffold uses explicit `--force`, N-Triples output, and a separate live evidence step so a normal test or CLI smoke cannot accidentally create huge artifacts.
