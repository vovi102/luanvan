# T2.2 Chain-Aware Entity Dictionary Remediation Design

## Context

The committed T2.2 dictionary passes structural tests but failed the independent
manual source audit on 2026-08-09. Seven of fifty sampled rows were not Ethereum
mainnet entities: six belonged to another EVM chain and one was a truncated
prefix of an Aptos resource address. The root cause is loss of chain context
during DefiLlama source extraction.

This remediation replaces inference from address-shaped strings with an
explicit, fail-closed Ethereum provenance contract. It preserves the useful
CoinGecko token population while rebuilding exchange and protocol coverage from
chain-aware evidence.

## Goals

- Guarantee that every committed record represents Ethereum mainnet
  (`chain_id = 1`).
- Distinguish the semantic role of each address as `operational`, `token`, or
  `treasury`.
- Make every source claim traceable to an immutable source snapshot or pinned
  upstream commit and a row-level locator.
- Retain at least 3,000 entities, 1,000 aliases, 8-12 concepts, top-30 exchange
  owner coverage, and top-50 DeFi protocol owner coverage.
- Prevent the seven audited failure modes from recurring.
- Keep generation and CI validation deterministic and offline.

## Non-goals

- Prove legal ownership or private-key control beyond the cited source claim.
- Parse arbitrary JavaScript or execute upstream DefiLlama adapters.
- Treat a protocol token contract as an operational endpoint.
- Refresh labels automatically during tests.
- Add support for non-Ethereum chains in T2.2.

## Approaches considered

### Full JavaScript adapter parsing

Parsing every DefiLlama adapter could retain the largest address population,
but adapters contain imports, generated configuration, helper calls, and
chain-specific conventions. Static parsing would be brittle, while executing
untrusted upstream code is outside the safety boundary.

### Fully hand-curated top-80 dictionary

Curating all exchange and protocol rows by hand offers high immediate accuracy,
but does not scale to the 3,000-entry token population and makes refreshes
needlessly expensive.

### Hybrid fail-closed snapshot pipeline — selected

CoinGecko token-list entries are ingested automatically only when their source
record declares `chainId = 1`; they receive role `token`. Exchange treasury and
protocol operational records are accepted only from reviewed source rows whose
evidence locator names an explicit Ethereum section in a pinned source. Protocol
token records may also come from a chain-aware source and remain role `token`.
Ambiguous records are omitted rather than guessed.

## Architecture

The pipeline has three boundaries:

1. **Source snapshots.** A committed CoinGecko JSON snapshot supplies the bulk
   token population. A compact reviewed CSV supplies exchange and protocol rows
   with pinned provenance.
2. **Snapshot compiler.** `scripts/03_fetch_entity_labels.py` reads both inputs,
   accepts only CoinGecko `chainId=1` records, validates reviewed rows, merges
   them by `(chain_id, address_lower)`, and writes the canonical raw CSV.
3. **Artifact builder and validator.** The existing builder projects canonical
   rows into `entities.json`, `concepts.json`, and `aliases.json`. Offline
   validation enforces the complete chain, role, provenance, coverage, and count
   contract.

No build step accesses the network. Updating a source is an explicit acquisition
and review operation whose downloaded snapshot or pinned commit changes in the
same reviewable diff as the regenerated artifacts.

## Data contract

The canonical raw CSV retains its existing columns and adds:

- `chain_id`: decimal CAIP/EIP-155 chain identifier; T2.2 accepts only `1`.
- `address_role`: one of `operational`, `token`, or `treasury`.
- `source_revision`: immutable commit SHA or `sha256:<digest>` for a committed
  source snapshot.
- `source_locator`: JSON pointer, file-and-line span, or other row-level locator
  inside that revision.

Each final entity repeats `chain_id` and `address_role`. Its single source record
contains `name`, `url`, `revision`, `locator`, `retrieved_date`, and `note`.

Role semantics are strict:

- `operational`: a contract/account used in protocol execution or flow analysis.
- `token`: a token contract; it is not assumed to be a protocol endpoint.
- `treasury`: a centralized-exchange reserve, custody, or treasury account.

The same address cannot appear twice, even with different roles. A role or owner
conflict therefore fails compilation and requires an explicit source decision.

## Source policy

- **CoinGecko:** accept an entry only when `chainId` is integer `1`, its address
  is an exact 42-character Ethereum address field, and name/symbol are non-empty.
  The committed JSON file is identified by SHA-256; its JSON array index is the
  source locator.
- **DefiLlama CEX:** accept a reviewed literal only when the pinned adapter path
  and locator identify an explicit Ethereum owner/treasury section. Assign
  `treasury`.
- **Protocols:** assign `operational` only when a pinned adapter or first-party
  document identifies an Ethereum deployment. Assign `token` when the evidence
  identifies an Ethereum token. Generic top-level protocol metadata never
  implies `operational`.
- URLs containing mutable `/main/` references may be retained for navigation,
  but `source_revision` must pin the evidence independently. A reviewed row
  without a revision and locator is invalid.

## Validation and error handling

Compilation and artifact validation fail on:

- a chain identifier other than integer `1`;
- an unknown address role;
- an address that is not exactly `0x` plus 40 hexadecimal characters;
- an address-shaped prefix embedded in a longer identifier;
- a missing or mutable-only source revision;
- an empty source locator;
- duplicate `(chain_id, address_lower)` rows;
- conflicting owner, category, or role metadata;
- unknown concepts or invalid confidence values;
- missing top-30 exchange or top-50 protocol owner coverage.

The global alias map continues to omit ambiguous aliases while retaining the
underlying entity rows.

## Coverage semantics

Owner coverage and operational coverage are separate measurements:

- An owner is covered when at least one verified Ethereum record exists for it.
- A protocol has operational coverage only when at least one record has role
  `operational`.
- Flow-query consumers must filter to `operational` records.
- Token-query consumers must filter to `token` records.
- Attribution queries may use `treasury` records.

The v0 acceptance threshold requires owner coverage for all listed owners.
Operational coverage is reported, not fabricated, and becomes an explicit input
to downstream sampling.

## Testing strategy

Tests are offline and test-first:

- schema tests cover chain, role, revision, and locator validation;
- compiler tests accept only CoinGecko mainnet rows and reject embedded/truncated
  addresses, non-Ethereum rows, duplicates, and incomplete provenance;
- builder tests verify propagation of chain, role, and provenance fields;
- artifact tests require 100% Ethereum chain IDs, valid roles, immutable
  provenance, deterministic ordering, minimum counts, and required owner
  coverage;
- regression fixtures encode SwissBorg, Bitget, Kelp, BlackRock BUIDL, Curve,
  Spiko, and Avalon failure modes.

After automated checks pass, an independent 50-row sample uses a new fixed seed
and is verified against sources. Acceptance requires zero critical chain/address
errors and at most one minor metadata error.

## Acceptance criteria

- At least 3,000 entities and 1,000 aliases.
- Between 8 and 12 concepts.
- Every entity has `chain_id = 1`, a valid role, and immutable row-level
  provenance.
- All top-30 exchange and top-50 protocol owners have at least one verified
  Ethereum record.
- All regression, focused, and full test suites pass.
- The new 50-row audit has zero critical errors and no more than one minor
  metadata error.
- The task record, source notes, and decision log describe the rebuilt snapshot
  and do not claim broader operational coverage than the data contains.

