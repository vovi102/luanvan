# T2.2 Entity Dictionary v0 Design

## Context

T2.2 builds the first production-quality entity dictionary for the NL2SPARQL over Ethereum KG project. The dictionary must support Phase 4 entity linking by mapping natural-language entity mentions such as "Binance", "Tornado Cash", or "Uniswap" to one or more Ethereum addresses and to a concept-level class.

The task target is intentionally data-heavy: at least 3000 labeled Ethereum address entries, at least 1000 alias mappings, and 8-12 concept categories. The implementation must be reproducible enough for thesis evaluation and CI. Tests must not depend on live network scraping.

## Goals

- Produce a committed, deterministic dictionary snapshot under `src/nl2sparql/linking/dictionary/`.
- Validate the snapshot with automated tests before accepting it.
- Preserve provenance for every entry so manual review and future refreshes are possible.
- Cover multi-address entities, especially centralized exchanges and major DeFi protocols.
- Generate enough normalized aliases for Phase 4 entity-linker development without embedding ambiguous aliases that would make linking brittle.

## Non-goals

- Build the Phase 4 entity linker itself.
- Guarantee real-time freshness of labels.
- Depend on live Etherscan, Dune, Arkham, or DeFiLlama calls in unit tests.
- Claim manual verification for entries that were not manually checked.
- Scrape sites aggressively or bypass rate limits.

## Recommended approach

Use a reproducible snapshot pipeline:

1. Store raw or curated source snapshots in a controlled local format.
2. Normalize, merge, deduplicate, and validate those inputs with scripts.
3. Commit deterministic output JSON files.
4. Keep live scraping optional and separate from validation.

This is better than runtime scraping because CI remains stable, thesis artifacts are reproducible, and future refreshes can be audited by comparing snapshot diffs.

## Alternatives considered

### Live scraper as the source of truth

The pipeline could scrape Etherscan and DeFiLlama every time the dictionary is generated. This maximizes freshness but makes tests flaky, introduces external-rate-limit failures, and creates non-reproducible thesis artifacts.

### Fully hand-curated dictionary

A manually maintained JSON file would be easy to inspect but too slow and error-prone for 3000+ entries. It also makes refreshes difficult.

### Hybrid snapshot pipeline

The selected approach uses committed snapshots plus deterministic build scripts. Live fetchers can be added as optional tools, but the accepted dictionary is the committed output. This preserves reproducibility while still allowing future refreshes.

## Data model

### `entities.json`

`entities.json` is a list of instance-level address records. Each record must contain:

- `address`: EIP-55 display address when available.
- `address_lower`: lowercase address used for matching and deduplication.
- `primary_label`: source-facing label, for example `Binance: Hot Wallet 14`.
- `owner`: normalized entity owner, for example `Binance`.
- `category`: normalized concept key such as `exchange`, `mixer`, `dex`, or `lending`.
- `concept_class`: ontology class local name, for example `ExchangeAccount`.
- `aliases`: entry-level aliases that can directly refer to this address or owner.
- `sources`: list of provenance records.
- `confidence`: `high`, `medium`, or `low`.
- `verified_date`: ISO date for the snapshot or verification event.

Each provenance record should include at least:

- `name`: source name such as `etherscan`, `defillama`, `curated_seed`, or `public_snapshot`.
- `url`: source URL when available.
- `retrieved_date`: ISO date.
- `note`: short explanation of what was used from the source.

### `concepts.json`

`concepts.json` maps concept keys to class-level metadata:

- `ontology_class`: ontology URI from the T2.1 extension.
- `aliases`: terms that imply the concept.
- `instances`: normalized owners covered by the concept.
- `description`: short human-readable definition.

Expected v0 concepts:

- `exchange`
- `mixer`
- `dex`
- `lending`
- `nft_marketplace`
- `bridge`
- `stablecoin`
- `staking`
- `mev`
- `token_contract`

The implementation may keep 8-12 concepts, but each concept must be linked to an ontology class or explicitly documented as a dictionary-only grouping if the ontology has no class yet.

### `aliases.json`

`aliases.json` maps normalized mention strings to normalized owner names:

```json
{
  "binance": "Binance",
  "binance hot wallet": "Binance",
  "tornado": "Tornado Cash",
  "uniswap v3": "Uniswap V3"
}
```

Alias keys must be lowercase, trimmed, and deterministic. Ambiguous short aliases are excluded unless the dictionary can resolve them reliably in context. For v0, aliases such as `eth`, `usdc`, and `uni` should be treated cautiously because they can refer to token symbols, protocols, or generic concepts.

### `sources.md`

`sources.md` documents:

- each data source;
- retrieval or snapshot date;
- rate-limit or access notes;
- known quality limitations;
- manual verification method and sample result;
- which acceptance criteria are automated and which are manual.

## Pipeline components

### Raw input area

The implementation should provide a stable place for input snapshots, for example:

- `data/entity_dictionary/raw/`
- `data/entity_dictionary/curated/`

Raw snapshots may be CSV, JSON, or Markdown-backed curated lists. They should be small enough to commit for T2.2 v0, or documented as intentionally external if size becomes excessive.

### Builder

Add a builder module or script that:

1. loads source rows;
2. normalizes addresses, owners, categories, and aliases;
3. merges duplicate addresses;
4. deduplicates aliases;
5. sorts outputs deterministically;
6. writes the three JSON outputs and source documentation inputs.

The builder should be rerunnable and should avoid hidden state. If live fetchers are added, they should write snapshots first rather than updating final JSON directly.

### Validator

Automated validation should check:

- `entities.json` has at least 3000 entries;
- all addresses match Ethereum address shape;
- `address_lower` is lowercase and unique;
- required fields are present;
- categories are known and have matching concepts;
- confidence values are valid;
- every entry has at least one source;
- `concepts.json` has 8-12 concepts;
- `aliases.json` has at least 1000 mappings;
- alias keys are normalized;
- alias targets exist in entity owners or concept instances;
- top-30 exchange coverage and top-50 DeFi protocol coverage are represented by owner/concept metadata.

Manual validation remains required for the 50-entry source check. The task file should not mark that checkbox done until the sample evidence is recorded.

## Testing strategy

Tests should be added before implementation and should target observable behavior:

- schema validation for all dictionary files;
- count thresholds for entries, aliases, and concepts;
- deduplication and normalization behavior in the builder;
- deterministic output ordering;
- coverage of required exchange and DeFi owners;
- `sources.md` contains retrieval dates and manual verification notes.

Tests must run offline against committed fixtures and outputs. Network access is not required for CI.

## Error handling

The builder should fail fast on:

- malformed Ethereum addresses;
- unknown categories;
- duplicate `address_lower` records that cannot be merged safely;
- alias collisions that map one alias to multiple owners;
- missing provenance.

Collisions that are intentionally unresolved should be written to a review report rather than silently accepted.

## Documentation impact

Update or add:

- `src/nl2sparql/linking/dictionary/sources.md`
- `docs/tasks/phase-2-kg/02-entity-dictionary.md`
- optionally `docs/memory/03-ONTOLOGY_REFERENCE.md` if concept-to-class mapping reveals ontology naming gaps
- optionally `docs/memory/05-DECISION_LOG.md` for the snapshot-vs-live-scraping decision

## Acceptance mapping

- `entities.json` ≥3000 entries: automated.
- Required entry format: automated.
- Sample 50 manual verification: manual evidence in `sources.md`.
- Top-30 exchange + top-50 DeFi protocol coverage: automated where curated coverage lists exist; manual notes for borderline owners.
- `concepts.json` 8-12 concepts: automated.
- `aliases.json` ≥1000 mappings: automated.

## Risks

- Public labels can be stale or inconsistent across sources.
- Some labels are service-level rather than owner-level.
- Etherscan or other sites can change HTML and break live fetchers.
- DeFi protocols may expose contracts across multiple chains; T2.2 should keep Ethereum-mainnet addresses only unless explicitly documented.
- Large generated JSON files can become noisy in diffs; deterministic sorting is required.

## Open decisions resolved for v0

- The accepted artifact is a committed JSON snapshot, not live scrape output.
- Live scraping is optional tooling, not part of required unit tests.
- Manual verification is documented separately and remains unchecked until evidence exists.
- Ambiguous aliases are excluded from v0 unless there is clear contextual disambiguation.
