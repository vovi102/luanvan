# Stage A v2 25-Intent Design

**Status:** Approved in the user brief on 2026-10-09.

**Extends:** `2026-08-09-t3-2-witness-grounded-stage-a-design.md` and
`2026-10-07-deterministic-bilingual-training-design.md`.

## Decision

Create Stage A v2 as a new, deterministic 1,000-record artifact covering all
25 production intents. Preserve every Stage A v1 file and its live evidence as
historical evidence. A v2 candidate and an accepted v2 artifact have separate
paths and manifests; candidate generation never implies acceptance.

Stage A v2 is accepted only after every record is backed by the existing
bounded, cache-free BigQuery witness contract. Offline generation may produce a
candidate and all mechanical validation evidence, but a missing live report,
empty witness, credential/quota failure, or unapproved cost leaves the artifact
in `candidate` state and blocks canonical bilingual publication.

## Artifact Boundaries

- Stage A v1 remains byte-for-byte unchanged at
  `data/dataset/raw/synthetic-stage-a.jsonl`, with its existing config and stats.
- The offline v2 candidate uses dedicated `*-v2-candidate.*` paths.
- The accepted v2 snapshot uses dedicated `*-v2.*` paths and is written only by
  the live workflow after all witnesses pass.
- Each v2 manifest binds the template library, value inputs, allocation,
  artifact bytes, lifecycle state, and superseded v1 hash.
- Downstream audit and canonical bilingual build require an accepted v2
  manifest whose artifact hash matches the supplied Stage A bytes.

No file in the v1 artifact set is rewritten, renamed, or used as a v2 output.

## Deterministic Allocation

The allocation retains the scientific difficulty totals `350/450/200`, covers
all 25 production templates, totals exactly 1,000, and keeps every template at
or below 10%. Counts within a difficulty are as even as the entity-frequency
constraint permits. Address-bearing templates are capped so the four pinned
address values remain at or below 50 appearances each; all other entities must
also remain at or below 5%.

The generator retains seed 42, unique IDs, SQL strings, and record hashes. It
renders every row from the unchanged production template, slot schema,
expected columns, schema elements, CQ links, entities, semantic anchors, and
template digest. Candidate-only values are explicitly marked in their input
provenance and can never satisfy the live acceptance gate.

## Evidence and Acceptance

The current witness verifier remains the source of truth: preflight every
unique witness, enforce per-query and aggregate byte caps, re-dry-run before
execution, disable cache, require exact columns and non-empty results, then
propagate only the existing limit-monotonic proof. V2 uses the same semantics
through an explicit validator seam; v1 behavior stays unchanged.

Acceptance requires:

1. exactly 1,000 records and 25 represented production intents;
2. exact allocation, `350/450/200` difficulty totals, template/entity caps,
   unique IDs/SQL/hashes, and seed 42;
3. a passing live witness report for every v2 record, zero cache hits, and a
   non-empty result under the existing cost caps;
4. one accepted manifest bound to the exact artifact bytes; and
5. no claim that v1 evidence verifies changed v2 SQL or slot values.

The workflow must not read credentials or instantiate a BigQuery client unless
the operator explicitly selects the live command. This implementation run is
authorized for offline work only, so it must stop at the external live gate.

## Bilingual Continuation

After acceptance, the existing deterministic catalog expands v2 into exactly
8,000 clean rows: 4,000 English and 4,000 Vietnamese, eight variants per
semantic family. Audit samples remain deterministic at 100 records per
language with exactly 25 intents by four styles. Audit events are append-only,
use strict booleans, bind the post-split record digest, and retain truthful
`agent-reviewed` provenance.

Canonical publication requires both language thresholds, the existing
hash-only exclusion index, group-aware splitting, diversity/leakage/provenance
validation, and two byte-identical builds at separate output paths. A candidate
Stage A may exercise validation and sampling in temporary paths but may not be
published or documented as canonical training data.

The Vietnamese benchmark candidate decisions remain untouched and pending user
review. Benchmark raw wording is not an input to generation, audit authorship,
or training; only the exclusion-index CLI may read it.

## Testing and Documentation

All behavior changes follow RED → GREEN → refactor. Tests cover v1
immutability, exact v2 allocation and coverage, deterministic candidate bytes,
entity/template caps, strict lifecycle manifests, live-verifier adaptation,
offline import/credential isolation, accepted-source enforcement in bilingual
CLIs, audit digest binding, and reproducible publication.

Task docs, architecture, decision log, backlog, and the SDD ledger record exact
candidate paths/hashes and the unresolved live gate. They may record v2 as
accepted and the bilingual artifact as canonical only after real live and audit
evidence exists.

