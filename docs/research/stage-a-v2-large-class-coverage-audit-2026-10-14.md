# Stage A v2 large native-to-class coverage audit — 2026-10-14

Status: user-authorized audit completed. The correction below is a proposal,
not implemented. No templates, catalogue versions, candidates, pools, historical
evidence, benchmark/model artifacts or acceptance gates were changed.

## Conclusion and proposed correction

Keep `T_LARGE_TX_TO_CLASS` as the general native-transaction recipient-class
threshold question. Recommend `concept_class=BridgeProtocol` instead of
`DEXProtocol`, keeping inclusive threshold **1 ETH**, date window
`[2026-06-15, 2026-06-16)`, the existing SQL, six projected columns, medium
difficulty and 41 allocated records. Do not lower the threshold to zero merely
to satisfy non-empty acceptance.

Remove incorrect CQ21/CQ25 annotations. Define explicit GoogleSQL training
CQ35 for the parameterized native-value-to-recipient-label-class question in a
new **1.2.0** catalogue revision. Preserve default 1.0.0 and training 1.1.0
snapshots/bytes, old question meanings and version-specific exact-ID guards;
select and pin the new revision explicitly rather than appending CQ35 under
1.1.0. See the independently sourced
[CQ audit](stage-a-v2-large-class-cq-audit-2026-10-14.md).

This is a class-fill and CQ-annotation correction, not a new intent or revival
of retired bridge-flow coverage. It does not ask for exchange funding, a bridge
deposit event, subsequent outflow, causality or an asset actually bridged.
Selecting BridgeProtocol without those predicates does **not** cover CQ26.

## Reproduction and scope

The retained failed diagnostic identifies witness `syn-v2-000759`:
`DEXProtocol`, `value_wei=1000000000000000000`, `n=1`, June 15–16.
Job `fb114172-bdb9-4521-8407-9448604c4ef3` executed SQL without provider errors
but returned zero rows. An offline replay called the actual verifier's
`_logical_results` with that exact planned query, expected columns and captured
empty result; it reproduced `requires a non-empty result` in about one second.
The failed live query was not executed again.

The falsifiable audit hypotheses were: DEX positive native value scarcity;
the 1 ETH threshold removing all matches; a June-15-only coverage gap; or another
accepted recipient class having meaningful native-value coverage. A single
daily class/role aggregation compared zero, positive, >=0.01, >=0.1, >=1 and
>=10 ETH in the bounded catalogue interval `[2026-05-31, 2026-07-01)`.
This remains the same external native transaction-value source, not token
transfer quantities or internal traces.

Machine-readable primary observations, exact SQL, digests, rows, jobs, column
schemas and byte metrics:
[coverage evidence](../evidence/stage-a-v2-large-class-coverage-audit.json),
SHA-256 `a47bfb2b448fa6928eee85ddf53d64e60de886f30334c291665e0e772fd628b4`.

Live view metadata still selects `entity_labels_snapshot_cdc7856df81f`, matching
the prefix of unchanged local dictionary SHA-256
`cdc7856df81f2cce61290ef27a8872477f1b77da998a6aa88ca0ed75cc19617e`.
The view query and etag are captured in this audit. This is a metadata/prefix
binding; the full `dictionary_sha256` data column was observed by the prior
[label audit](../evidence/stage-a-v2-hard-intent-label-audit.json), not freshly
re-read here. Do not overstate the new observation as a full-column hash check.

## Coverage results

| Recipient class | >=1 ETH on June 15 | >=1 ETH over 31 days | Days with >=1 ETH | Interpretation |
|---|---:|---:|---:|---|
| DEXProtocol | 0 | 0 | 0/31 | Changing window alone cannot retain the 1 ETH threshold |
| BridgeProtocol | 9 | 258 | 31/31 | Same-day, same-threshold alternative with protocol-class diversity |
| ExchangeAccount | 160 | 3,942 | 31/31 | Valid fallback, but further concentrates an already treasury-heavy training population |

The protocol-diversity preference is a design judgment, not an empirical model
performance result. Both alternatives have exact production-query witnesses.

DEX operational labels have 673 transactions over the interval: 666 value-zero
and seven positive. Six positive rows are on June 18, with max value
100,000,000 wei; one is on June 29, with value 100,000,000,000,000 wei
(0.0001 ETH). There are **zero >=0.01 ETH** matches. Two DEX token-role labels
have 71,790 transactions, all value-zero. Thus neither another allowed day nor
even a 0.01 ETH threshold salvages meaningful large-native DEX coverage in
this snapshot. These are transaction `value_wei` observations; no receipt-success
claim is made for the seven tiny positive DEX values.

On June 15, all nine BridgeProtocol >=1 ETH rows are receipt-successful and
associated with operational labels; the same is true for all 160 eligible
ExchangeAccount rows, whose labels are treasury. Successful counts were measured
separately from the unchanged production predicate. Production SQL itself has
no receipt-success or address-role filter. A general label-class question must
not imply successful funds received or a decoded protocol operation.

### Exact production witnesses

Only the `concept_class` fill changed; date bounds, threshold, `n=1`, SQL shape
and expected six columns stayed the same as the active template.

- BridgeProtocol: job `f97212be-ccc2-4ada-8974-755e5749a4c2`, one row,
  transaction `0xf4bddec3911167595ed563a3acaf44fcf570b9f5039806891a6e616475c9f424`,
  recipient `0x604dd02d620633ae427888d41bfd15e38483736e`, label owner Aster Bridge,
  native value `36110000000000000000` wei (36.11 ETH).
- ExchangeAccount: job `0b9211d2-2c1e-41cf-8629-5b568b685546`, one row,
  transaction `0x05a6d680dc120fdc5a934ae751d00bbb7417843b8a3085b7188cb9858e98af2a`,
  recipient `0x77134cbc06cb00b66f4c7e623d5fdbf6777635ec`, label owner Bitfinex,
  native value `40000000000000000000000` wei (40,000 ETH).

Point witnesses demonstrate feasibility only. They do not complete the 126-query
diagnostic, produce accepted records or establish n requested rows always exist.

## Contract implications

CQ21 requires mixer-to-DEX native flow; CQ25 asks token-volume aggregation into
DEX. This template has neither sender-class restriction nor token aggregation.
CQ02 describes only its native-threshold facet, not exact general class-filter
equivalence. Prefer CQ35 over replacing two false annotations with an ambiguous
facet-only coverage claim. Catalogue `supported` means schema expressibility,
not measured non-empty population coverage.

The proposed CQ35 should describe: native transaction rows whose recipient
accepted label class equals a parameter and native `value_wei` is at least a
NUMERIC parameter, within half-open date bounds, ordered by native wei descending.
All sender classes and label roles remain permitted; no receipt-success,
decoded bridge operation, token units or balances are inferred. Preserve NUMERIC
wei and the inclusive threshold.

Review the eight existing bilingual patterns for neutral transaction-value
language. In particular, English “transfers ... moved” and Vietnamese “chuyển”
can imply successful asset movement even though SQL does not filter receipt
success. Prefer “transactions with native value ...” for those variants rather
than silently adding a new successful-transfer predicate. This proposal does
not rewrite patterns during the audit.

An in-memory parameter-only counterfactual (no artifact writes and no endorsement
of the old CQ21/CQ25 metadata) changed exactly 41 records,
`syn-v2-000759` through `syn-v2-000799`, with `n=1..41`. Actual planner output
remained 206 logical / 126 physical queries. The proposed corrected catalogue
and CQ35 metadata still require implementation and fresh verification. Target
remains 1,000 records, 25 intents, seed 42, difficulty 350/450/200; no rebalance.

## Bounds, cost and publication boundary

Four executions occurred once each: label-role counts, daily class/value coverage,
and two production witnesses. Each had initial plus immediate dry-run, query cache
disabled and SDK request/job/result retries disabled. Billing was confirmed
disabled and unlinked. Per-query caps: 64 MiB, 16 GiB, 1 GiB, 1 GiB; aggregate
cap **24 GiB**. Observed aggregate estimates: 9,783,123,650 bytes; processed:
9,742,808,678; billed: 9,753,853,952; cache hits: zero. Read-only view metadata
retrieval is not counted as a query execution.

No initial failed SQL was repeated; no full diagnostic or acceptance run was
performed. Historical failed reports and all current training inputs remain
unchanged. All three accepted-v2 paths remain absent; no canonical bilingual
publication, merge, push or PR. Next step is approval of this concrete correction,
then local implementation/regeneration, a bounded full diagnostic and a separately
approved post-diagnostic final-live preflight if all witnesses pass.
