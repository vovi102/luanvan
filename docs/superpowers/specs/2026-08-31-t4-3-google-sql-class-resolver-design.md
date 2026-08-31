# T4.3 GoogleSQL Class Resolver Design

**Date:** 2026-08-31
**Status:** approved under the user's explicit self-approval delegation
**Scope:** migrate T4.3 from SPARQL fragment generation to deterministic,
typed GoogleSQL constraint planning over T4.1 schema links, T4.2 entity matches,
and the accepted analytical catalog.

## Context

Pivot #1 made read-only GoogleSQL over the BigQuery analytical catalog the
canonical runtime. The legacy T4.3 task still asks for ready-to-inject SPARQL
`VALUES`, `BIND`, and class triple patterns. That output would bypass the
catalog's relation, field, join, role, date, and coverage contracts.

T4.2 deliberately stops at recognition: it returns immutable `EntityMatch`
evidence without choosing a SQL predicate or join. T4.3 owns that next decision,
but it must not become a SQL generator. It resolves each recognized mention into
a typed constraint plan that T5.1 and later generators can render safely.

The implementation and all contract tests can run locally. No model download,
BigQuery credential, network call, or live query is required.

## Decision

Implement a deterministic resolver backed by a validated entity corpus and
analytical catalog. Its only public operation is:

```python
ClassResolver.resolve(
    question: str,
    matches: Sequence[EntityMatch],
    schema_links: LinkResult | None = None,
) -> ResolutionPlan
```

`ClassResolver` receives the validated catalog and `EntityCorpus` at
construction. Callers do not provide rule tables, field mappings, SQL syntax, or
dictionary lookups per call. The module therefore keeps a small interface while
hiding linguistic classification, target hydration, catalog validation,
direction inference, field selection, ambiguity policy, and coverage reporting.

Inputs and outputs are immutable. Results follow source-span order and preserve
T4.2 provenance. The resolver returns data only; it never renders or executes
SQL.

## Public contracts

`ResolutionPlan` contains:

- the original question fingerprint rather than persisted question text;
- an ordered tuple of `ResolvedEntity` values;
- the catalog fingerprint and the three dictionary fingerprints;
- aggregate status: `resolved`, `partial`, or `unresolved`;
- deterministic warnings for ambiguity, missing coverage, or unspecified
  direction.

Each `ResolvedEntity` contains:

- original `span`, half-open `span_offset`, `target_id`, and target fingerprint;
- `resolution_kind`: `instance`, `concept`, or `unresolved`;
- `direction`: `from`, `to`, `token`, or `unspecified`;
- zero or more typed `FieldCandidate` values;
- `operator`: `in` for instance addresses, `equals` for a concept class, or
  `none` when unresolved;
- immutable string values: canonical lowercase addresses or one catalog-backed
  concept-class value;
- required relation and join path when label lookup is needed;
- required address role when the catalog defines one;
- `coverage_status`: `supported`, `coverage_gap`, or `unresolved`;
- confidence, explanation, and source fingerprints.

`FieldCandidate` identifies a catalog relation and field. It is not a free-form
SQL expression. This allows a later renderer to quote identifiers and bind
parameters without trusting resolver-produced text.

Invalid contracts raise `ClassResolverError`, a typed `ValueError`. Valid but
ambiguous evidence is data, not an exception.

## Resolution rules

Rules are applied independently per non-overlapping mention, then checked for
cross-mention conflicts.

1. An `owner` or `address` target resolves to `instance` and uses its canonical
   address tuple with operator `in`. An owner target with no addresses is
   unresolved rather than converted into an owner-name predicate.
2. A `concept` target resolves to `concept`, requires `entity_labels_v1`, and
   constrains `concept_class` with operator `equals`.
3. An ambiguous match stays unresolved by default. A local class trigger
   (`any`, `all`, `every`, `major`, or an unambiguously plural generic mention)
   may select a concept alternative only when exactly one concept alternative
   exists and that target can be hydrated from the same fingerprint-bound
   corpus. The resolver never silently accepts T4.2's primary alternative.
4. Direction is inferred from bounded local context. Source cues include
   `from`, `sent by`, and `out of`; destination cues include `to`, `into`, and
   `received by`. Token cues apply only when the catalog/schema evidence supports
   a token-address field. Conflicting or absent cues produce `unspecified`.
5. Direction and optional T4.1 rankings select only fields that already exist in
   the validated catalog. Schema links narrow the candidate set; they never
   authorize a relation or field absent from the catalog.
6. Concept constraints use the catalog's `fact_address_to_entity` lookup and
   `entity_labels_v1.concept_class`. Instance constraints can bind a fact address
   directly. The plan records the join instead of emitting it.
7. Address-role requirements come from catalog semantics. They are never inferred
   from an ontology name alone and never substitute `operational`, `treasury`, or
   `token` roles for one another.
8. A representable concept with no accepted address coverage remains a concept
   constraint with `coverage_gap`; it is not reported as executable coverage.

When two mentions resolve to the same direction, both remain in source order and
the plan is `partial` with a deterministic conflict warning. T4.3 does not invent
boolean conjunction/disjunction intent.

## Catalog and provenance boundary

Construction validates the catalog with the existing SQL schema validator before
deriving an internal lookup of analytical relations, fields, joins, semantic
mappings, roles, and competency coverage. The resolver accepts a single catalog
snapshot and hashes the exact canonical bytes used to build that lookup.

The supplied `EntityCorpus` must agree with every owner/concept match target and
target fingerprint. Addresses and concept metadata are hydrated only from that
corpus. A T4.2 raw `address:<lowercase-address>` target is the sole exception: it
is self-authenticating when its target ID, one-item address tuple, empty semantic
claims, and SHA-256 of the target ID agree. Unknown owner/concept targets and all
stale or mismatched targets fail closed. Ambiguous alternatives are hydrated
through the corpus; their abbreviated T4.2 records are never treated as complete
metadata.

The output carries catalog and dictionary fingerprints so later baseline or
generator artifacts can prove which semantics produced a constraint plan.

## Error and safety behavior

- Reject empty, oversized, control-bearing, or tokenless questions.
- Reject spans that are out of bounds or do not equal the original question
  slice, unsorted/overlapping matches, duplicate target evidence, and malformed
  optional schema links.
- Reject stale entity target fingerprints, unknown catalog fields/relations,
  invalid join paths, noncanonical addresses, and unsupported operator/value
  combinations.
- Preserve ambiguity and coverage gaps explicitly; do not reinterpret them as
  successful resolution.
- Do not persist question text, initialize an encoder, access the network, query
  BigQuery, or produce executable SQL.

## Local evaluation and documentation

The numbered workflow exposes an offline `resolve` command for a supplied JSON
question/match payload and an `evaluate` command for a reviewed JSONL artifact.
Machine output is canonical JSON. `--help` and all validation paths remain free
of model initialization and external access.

The implementation includes at least 20 focused resolver cases and a validator
for an exactly 50-question manually annotated evaluation set. The evaluator
reports resolution-kind accuracy, direction accuracy, fully resolved plan
accuracy, coverage-gap counts, and provenance. Synthetic unit fixtures verify
metric arithmetic but do not satisfy the scientific accuracy gate.

The legacy `src/nl2sparql/linking/RESOLVER_RULES.md` deliverable becomes a
GoogleSQL rule reference describing typed constraints, ambiguity, role semantics,
and coverage behavior. The T4.3 task is rewritten and marked as migrated before
implementation is claimed complete.

## Testing

Test-first coverage crosses the public resolver interface:

- owner, known address, concept, empty-address owner, and ambiguous targets;
- `any`/`all`/`every` class triggers and proper-name instance behavior;
- source, destination, token, unspecified, and conflicting direction cues;
- schema-link narrowing and rejection of unknown catalog identities;
- exact catalog relation/field/join/role contracts;
- coverage gaps for concepts without accepted endpoints;
- stable ordering, same-direction conflicts, immutable values, and deterministic
  explanations;
- stale corpus fingerprints, bad spans, overlaps, invalid questions, and
  malformed payloads;
- 50-row ground-truth validation, metric math, canonical report provenance, CLI
  help, and offline execution;
- full pytest, Ruff lint/format, notebook JSON if a notebook is added, and
  `git diff --check`.

## Alternatives rejected

1. **Return SQL fragments from the resolver:** convenient for one caller, but it
   mixes semantic resolution with quoting, parameterization, aliasing, and query
   generation. That makes the module shallow and harder to reuse safely.
2. **Use an LLM to classify every mention:** handles broader language but adds
   nondeterminism, model availability, latency, and evaluation confounds to a
   rule set covered by current catalog semantics.
3. **Resolve from `EntityMatch` alone:** avoids a constructor dependency but
   cannot safely hydrate ambiguous alternatives or verify that target metadata is
   current. The fingerprint-bound corpus is the required provenance seam.
4. **Default every ambiguous match to instance:** mimics the legacy task but
   discards T4.2's explicit uncertainty and can produce silently wrong filters.

## Acceptance boundary

T4.3 implementation is locally complete when its migrated task, typed module,
rule documentation, offline workflow, focused tests, full repository tests, Ruff,
and diff checks pass. Scientific accuracy `>= 0.90` remains unchecked until an
independently reviewed 50-question annotation artifact exists and the production
evaluation passes. Local synthetic fixtures must not be cited as that evidence.
