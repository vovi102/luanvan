# Stage A v2 Supported-Intent Revision Design

**Status:** Approved by the user on 2026-10-11.

**Extends:**

- `docs/superpowers/specs/2026-10-09-stage-a-v2-25-intents-design.md`
- `docs/superpowers/specs/2026-10-10-stage-a-v2-batch-verification-design.md`

## Context

The approved Stage A v2 live run failed closed at record `syn-v2-000834`.
Its template, `T_MIXER_TO_DEX_LARGE_FLOW`, returned no rows because the accepted
entity dictionary has no verified operational mixer endpoint. The template
already declared that limitation with `expect_non_empty=false`, and the SQL
catalog classifies its linked `CQ21` as `coverage_gap`. This conflicts with the
immutable Stage A v2 acceptance rule that every logical witness must be
non-empty.

Retrying the same query cannot create genuine evidence. Allowing an empty
result, changing acceptance metadata by hand, or lowering the validation gate
would invalidate the acceptance claim. The failed run therefore created no
accepted Stage A v2 artifacts and left Stage A v1 unchanged.

An initially considered replacement based on `CQ30` was also rejected before
specification. Direct inspection of the accepted curated dictionary found 71
owners and zero owners assigned to more than one category. A query requiring
multiple categories per owner would therefore reproduce the same empty-result
failure. CoinEx and SwissBorg each have only the `exchange` category in the
accepted dictionary; neither may be represented as a multi-category owner.

## Decision

Replace `T_MIXER_TO_DEX_LARGE_FLOW` with
`T_CATEGORY_OWNER_DISTRIBUTION`, a genuinely supported, non-empty analytical
intent linked to `CQ20`. The replacement summarizes and ranks accepted label
categories by distinct owner and account counts. It does not claim that any
owner spans multiple categories and does not link to `CQ30`.

Regenerate Stage A v2 as a new candidate revision under the existing v2
candidate paths. Do not create a v3 lifecycle. The superseded candidate remains
recoverable through Git history and its hashes remain in historical evidence.
Stage A v1 remains byte-for-byte immutable.

## Goals

1. Remove the known `CQ21` coverage-gap template from the 25-intent Stage A v2
   population.
2. Replace it with a deterministic query whose semantics and rows are supported
   by the accepted `entity_labels_v1` snapshot.
3. Preserve exactly 1,000 records, 25 template intents, difficulty totals of
   350 easy / 450 medium / 200 hard, and the existing 34-record allocation at
   the replaced position.
4. Preserve the existing genuine 45-block and 45-transaction-hash value pool,
   logical-to-physical evidence graph, cost caps, and fail-closed acceptance
   boundary.
5. Require a fresh exact BigQuery preflight and separate cost approval before
   another live acceptance attempt.

## Non-goals

- Adding or fabricating a mixer endpoint.
- Reclassifying `CQ21` or `CQ30` as data-backed for this candidate.
- Weakening the 100% non-empty rule, cache prohibition, exact-column checks, or
  evidence-graph validation.
- Manually changing lifecycle metadata or hashes.
- Modifying Stage A v1 or using its evidence to verify changed v2 SQL.
- Starting bilingual audit, canonical corpus publication, or B1/B2 training.

## Replacement Template Contract

The production template library removes `T_MIXER_TO_DEX_LARGE_FLOW` and adds
the following contract:

- **ID:** `T_CATEGORY_OWNER_DISTRIBUTION`
- **Name:** Category owner distribution
- **Category:** `transaction_aggregation`
- **Difficulty:** `hard`
- **Slots:** only `n`, an integer from 1 through 100
- **CQ link:** `CQ20`
- **Expected columns:** `category`, `owner_count`, `account_count`,
  `accounts_per_owner`, `owner_rank`
- **Schema elements:** `entity_labels_v1.category`,
  `entity_labels_v1.owner`, and `entity_labels_v1.address`
- **Validation:** `expect_non_empty=true`

The exact GoogleSQL shape is:

```sql
WITH category_stats AS (
  SELECT
    category,
    COUNT(DISTINCT owner) AS owner_count,
    COUNT(DISTINCT address) AS account_count
  FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`
  GROUP BY category
)
SELECT
  category,
  owner_count,
  account_count,
  SAFE_DIVIDE(account_count, owner_count) AS accounts_per_owner,
  DENSE_RANK() OVER (
    ORDER BY owner_count DESC, account_count DESC
  ) AS owner_rank
FROM category_stats
ORDER BY owner_rank, category
LIMIT {n}
```

This is a hard analytical intent because it combines a grouped relation,
distinct aggregations, a derived concentration measure, and a window ranking.
It is distinct from `T_ACCOUNTS_BY_CATEGORY`, which groups by category and
address role and returns only account counts. The replacement asks how ownership
is distributed across categories and ranks those category summaries.

The natural-language seed asks for the top `n` label categories ranked by
distinct owners, including account count and accounts per owner. The scope note
states that the result summarizes the accepted label dictionary and makes no
cross-category-owner claim.

## Deterministic Generation and Allocation

`V2_TEMPLATE_ALLOCATION` replaces the old template key with the new key at the
same allocation of 34 records. Every other template count and its ordering stay
unchanged. The replacement records vary only by `n`, using values 1 through 34.
The rendered SQL remains unique even though the current dictionary has fewer
than 34 categories.

Witness identity excludes `n`, so all 34 records form one limit-monotonic
logical witness group. The existing verifier selects the minimum-limit record,
`n=1`, as the witness: a non-empty result at limit 1 proves only the shared
non-empty obligation for every larger limit, not a row-count guarantee.
Replacing one one-group template with another therefore preserves the current
expected plan at 170 logical witness groups and 126 physical queries. Tests
must derive and assert these counts rather than force them through metadata.

Offline regeneration overwrites only the v2 candidate artifacts:

- `data/dataset/raw/synthetic-stage-a-v2-candidate.jsonl`
- `data/dataset/raw/generation-config-v2-candidate.json`
- `data/dataset/raw/stats-v2-candidate.md`

The regenerated data, manifest, stats, template-library, and record hashes are
expected to change and must be calculated from actual serialized bytes. The
candidate lifecycle remains `candidate`; regeneration alone cannot produce or
unlock accepted artifacts.

## Bilingual Catalog Migration

Remove the eight English/Vietnamese patterns associated with the retired
template and add exactly eight patterns for
`T_CATEGORY_OWNER_DISTRIBUTION`: four styles in English and the same four styles
in Vietnamese. Each pattern must express category-level owner distribution,
account totals, and ranking without implying that an owner belongs to multiple
categories.

The bilingual contract tests must continue to enforce 25 templates, two
languages, four styles, unique normalized patterns, valid placeholders, and
exact template references. Regenerating the Stage A candidate may update
candidate-bound fixtures, but it does not authorize a bilingual audit or a
canonical 8,000-record publication.

## Evidence and Acceptance Flow

The genuine evidence-pool file and its acquisition provenance remain unchanged.
The replacement template needs no external value-pool entry because its only
slot is `n`. Existing block-number and transaction-hash entries retain exactly
the `{value, source, evidence}` structure and remain necessary for their own
templates.

The revised workflow is:

1. Regenerate the deterministic offline v2 candidate and its truthful hashes.
2. Run focused and full local validation, including a second candidate build to
   prove byte determinism.
3. Run `scripts/09_generate_stage_a_v2.py --preflight` with the genuine evidence
   pool and report exact estimated bytes, logical witness count, physical query
   count, per-query and aggregate caps, maximum query, and estimated gross cost
   when available.
4. Stop for explicit approval of that measured live execution cost.
5. After approval, run the existing `--live` command, which repeats complete
   preflight and immediate per-query dry-runs before executing cache-disabled
   queries.
6. Publish the three accepted v2 outputs atomically only if all 1,000 records
   have non-empty genuine evidence, the complete evidence graph validates,
   every cache flag is false, and preflight/execution provenance is consistent.

The existing caps remain 20 GiB per physical query and 96 GiB across the exact
initial physical preflight. No query may execute when either cap fails or when
the measured cost has not been approved.

## Failure Handling

Every stage remains fail-closed. In particular:

- an empty replacement result blocks publication;
- any mismatch in the expected replacement columns blocks publication;
- a changed logical or physical count must be explained by the generated plan,
  not hidden by editing expected metadata;
- preflight cap overflow stops before execution;
- cache hits, SQL-digest drift, group-membership drift, or incomplete evidence
  edges reject the live run; and
- a failure leaves all accepted-v2 outputs absent and Stage A v1 unchanged.

No failed live job may be described as acceptance evidence. Execution metadata
from a failed run remains operational evidence only.

## Testing and Verification

Implementation follows RED, GREEN, REFACTOR. Tests cover:

- retirement of the mixer template and addition of the exact replacement
  contract;
- truthful CQ20 linkage and absence of CQ21/CQ30 claims on the replacement;
- exact 34-record replacement allocation, 1,000 total records, 25 templates,
  and 350/450/200 difficulty totals;
- unique IDs, SQL, hashes, deterministic bytes, and the one-group
  limit-monotonic witness behavior;
- 170 logical witnesses and 126 physical queries for the regenerated candidate;
- exact result columns and non-empty validation for the replacement query;
- eight replacement bilingual patterns and removal of all retired-template
  references;
- candidate lifecycle enforcement, v1 byte preservation, evidence-pool
  preservation, and absence of accepted outputs before live success; and
- preflight/live fail-closed behavior with fake BigQuery jobs before any real
  provider call.

Repository verification includes the full test suite, Ruff formatting and
checks, JSON parsing, candidate hash reporting, deterministic double-build,
immutable v1 hash checks, and `git diff --check`.

## Post-Acceptance Boundary

If and only if the live workflow produces valid accepted artifacts, verify the
accepted data, manifest, and stats hashes; exactly 1,000 records; all 25
templates; 350/450/200 difficulty totals; complete evidence; zero cache hits;
and lifecycle `accepted`.

Only then may the project begin the manual 100-English plus 100-Vietnamese
audit. Only after that audit passes may it build the canonical bilingual
8,000-record corpus twice and compare bytes for determinism. Vietnamese
benchmark review may be prepared independently, but no agent action may be
represented as human approval. B1/B2 training remains blocked until acceptance
and bilingual audit are complete.
