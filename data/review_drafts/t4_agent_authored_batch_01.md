# T4 agent-authored draft pack 01

**Status:** `SUPERSEDED DRAFT — not ground truth, not for training, not for publication`

**Author:** Codex (2026-09-22)

**Superseded by:** `t4_candidate_set_2026-09-24/`. No row from this initial
15-question pack was directly promoted to `data/eval/`; it is retained only as
an audit artifact.

**Purpose:** First review batch for T4.1/T4.2/T4.3. It has exactly 15 questions:
5 per component. It is intentionally separate from `data/eval/`, T3.5, and all
Stage A–D training artifacts. All labels below are proposed labels, not accepted
scientific evidence. Do not promote any row until a human reviewer records an
`ACCEPT`, `REVISE`, or `REJECT` decision.

## How to review

For every row, add one decision and a short note:

| Decision | Meaning |
|---|---|
| `ACCEPT` | The question is natural and the proposed semantic label is minimal and correct. |
| `REVISE` | Keep the question, but state the exact corrected label or wording. |
| `REJECT` | Remove it; state whether it is ambiguous, out of catalog, duplicate, or unnatural. |

Do not alter target IDs/field IDs by guessing. They are taken from the current
catalog and dictionary snapshots stated in the individual sections.

---

## T4.1 — Schema Linker (5 proposed cases)

Catalog source: `src/nl2sparql/sql/catalog/ethereum_analytics.json`.
`gold_fields` means fields materially needed to interpret, filter, group, or
return the requested answer. It is not a full GoogleSQL implementation.

| ID | Natural-language question | Proposed `gold_relations` | Proposed `gold_fields` | Review focus |
|---|---|---|---|---|
| schema-a01 | How many transactions occurred on each day in June 2026? | `transaction_facts` | `transaction_facts.block_timestamp`, `transaction_facts.transaction_hash` | Time bucketing plus transaction count. |
| schema-a02 | Which recipient addresses received the most successful transactions in June 2026? | `transaction_facts` | `transaction_facts.to_address`, `transaction_facts.is_success`, `transaction_facts.transaction_hash`, `transaction_facts.block_timestamp` | Recipient direction, success filter, ranking and time window. |
| schema-a03 | Which token symbols had the most token transfers in June 2026? | `token_transfer_facts` | `token_transfer_facts.token_symbol`, `token_transfer_facts.transaction_hash`, `token_transfer_facts.log_index`, `token_transfer_facts.block_timestamp` | Token aggregation. `transaction_hash` + `log_index` identify a transfer. |
| schema-a04 | Which blocks had the highest transaction counts in June 2026? | `block_facts` | `block_facts.block_number`, `block_facts.transaction_count`, `block_facts.block_timestamp` | Block ranking and time filter. |
| schema-a05 | List the owner and category for every entity label classified as an exchange. | `entity_labels_v1` | `entity_labels_v1.owner`, `entity_labels_v1.category`, `entity_labels_v1.concept_class` | Entity-label lookup and class filter. |

### T4.1 decision log

| ID | Decision (`ACCEPT` / `REVISE` / `REJECT`) | Reviewer note |
|---|---|---|
| schema-a01 |  |  |
| schema-a02 |  |  |
| schema-a03 |  |  |
| schema-a04 |  |  |
| schema-a05 |  |  |

---

## T4.2 — Entity Linker (5 proposed cases)

Dictionary source: current `EntityCorpus` derived from the committed reviewed
dictionary. `target_id` is the exact canonical owner target. `span` is copied
exactly from the question; its offsets will be generated mechanically only after
review approval.

| ID | Natural-language question | Proposed mention | Proposed target ID | Why it is included |
|---|---|---|---|---|
| entity-a01 | Show transfers sent from Binance in June 2026. | `Binance` | `owner:Binance` | Exact owner mention; sender context. |
| entity-a02 | Which token transfers were received by OKX in June 2026? | `OKX` | `owner:OKX` | Exact owner mention; recipient context. |
| entity-a03 | Did Uniswap V3 receive token transfers in June 2026? | `Uniswap V3` | `owner:Uniswap%20V3` | Multi-token owner phrase. |
| entity-a04 | Show transactions sent to Aave V3 in June 2026. | `Aave V3` | `owner:Aave%20V3` | Multi-token owner phrase. |
| entity-a05 | How many token transfers originated from Curve DEX in June 2026? | `Curve DEX` | `owner:Curve%20DEX` | Multi-token owner phrase; sender context. |

### T4.2 decision log

| ID | Decision (`ACCEPT` / `REVISE` / `REJECT`) | Correct mention/target if revised | Reviewer note |
|---|---|---|---|
| entity-a01 |  |  |  |
| entity-a02 |  |  |  |
| entity-a03 |  |  |  |
| entity-a04 |  |  |  |
| entity-a05 |  |  |  |

---

## T4.3 — Class Resolver (5 proposed cases)

This section evaluates typed entity constraints, not SQL. The expected semantic
decision specifies the intended `resolution_kind`, `direction`, and coverage
outcome. Codex will turn accepted rows into the stricter JSONL contract after
generating current target fingerprints and linker-compatible evidence.

| ID | Natural-language question | Entity/concept | Proposed target | Expected semantic decision | Review focus |
|---|---|---|---|---|---|
| resolver-a01 | Retrieve Binance-originating transactions in June 2026. | `Binance` | `owner:Binance` | `instance`, `from`, `supported` | Owner resolves to Binance's accepted treasury address in a sender constraint. |
| resolver-a02 | Show transactions sent to OKX in June 2026. | `OKX` | `owner:OKX` | `instance`, `to`, `supported` | Owner resolves to OKX's accepted treasury address in a recipient constraint. |
| resolver-a03 | Show token transfers from exchanges in June 2026. | `exchanges` | `concept:exchange` | `concept`, `from`, `supported` | Generic exchange concept, not a single owner. |
| resolver-a04 | Show token transfers to decentralized exchanges in June 2026. | `decentralized exchanges` | `concept:dex` | `concept`, `to`, `supported` | Generic DEX concept in recipient direction. |
| resolver-a05 | Find transactions from mixers to exchanges in June 2026. | `mixers`; `exchanges` | `concept:mixer`; `concept:exchange` | mixer: `concept`, `from`, `coverage_gap`; exchange: `concept`, `to`, `supported` | Must preserve the mixer coverage gap; never invent an endpoint. |

### T4.3 decision log

| ID | Decision (`ACCEPT` / `REVISE` / `REJECT`) | Correct semantic decision if revised | Reviewer note |
|---|---|---|---|
| resolver-a01 |  |  |  |
| resolver-a02 |  |  |  |
| resolver-a03 |  |  |  |
| resolver-a04 |  |  |  |
| resolver-a05 |  |  |  |

## Promotion rule

After human review, Codex may create canonical JSONL only for rows marked
`ACCEPT` or corrected through `REVISE`. Rejected rows are retained here as review
history and are never used as training, evaluation, or fixture data. The first
full agent-authored T4 sets will be reported as human-reviewed but **not
independently authored**.
