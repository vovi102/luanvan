# Supported-intent revision final review — 2026-10-14

Fresh read-only reviewer: `final_supported_intents_review`, gpt-6-astra.
Reviewed whole branch `5ff21e1..fbeea42` in passes, focusing the approved
`9f9ba3a..fbeea42` implementation. No provider calls, writes, additional
reviewers or full-suite reruns by the reviewer.

## Findings and single fix pass

No Critical or Minor findings. Two Important findings were independently
reproduced and entered the implementer's one fix pass:

1. Failed diagnostic validation returned before checking candidate/billing/
   partial observations/totals. Reproduced with the actual report against `[]`
   and corrupted fields. Eleven regression cases failed before correction;
   three further row/column corruption cases also failed before correction.
   Validator now binds the exact candidate, requires stage-appropriate billing,
   validates retained query digests/membership/dependencies, non-empty execution
   IDs/rows, logical edges/columns/row totals and byte/count totals. Failure at
   billing guard may have no provider observations; incomplete coverage remains
   permitted only for failed reports. This does not convert failure to success.
2. Accepted manifest required nonempty initial/immediate dry-run job IDs,
   unlike observed unpersisted BigQuery dry runs. Three regression cases failed
   before correction and passed afterward. Empty string dry-run IDs are now
   valid, but absent/non-string fields and empty execution IDs are rejected;
   query identity, location, estimates, coverage and non-empty result gates stay
   intact. Tests construct manifests only in memory, never publish acceptance.

Focused fix verification: 66 tests pass; Ruff and diff checks pass. Full suite
after the fix pass: **1,462 passed**, 342 upstream warnings, 330.32 seconds.
Diagnostic bytes are not
rewritten or executions repeated; the same failed report validates under the
strengthened provenance checks.

## Executor rulings on declined-to-judge items

- Live acceptance: remains blocked by unchanged `T_LARGE_TX_TO_CLASS`; the user
  receives a failed diagnostic, not an acceptance claim. Wrong ruling would
  misrepresent population coverage; no accepted artifacts exist.
- Other 21 templates / nonempty gate: keep unchanged per approved scope; propose
  a separate coverage audit, not silent replacement or relaxed acceptance.
- Production retry defaults: unchanged; the actual diagnostic uses explicitly
  disabled request/job/result retries. Do not claim default CLI retry safety.
- Historical benchmark/ontology wording: preserved; training CQ31–CQ34 are
  explicitly selected, versioned extensions, not reinterpreted old IDs.
- Empirical hard difficulty/representativeness: no new model evaluation claim;
  only the approved compositional rubric and training population are changed.
- Earlier account-pair, beneficiary and category-owner design choices: retain
  approved dependency contracts; final review checked integration rather than
  redesigning them. The two shared evidence defects above were not deferred.
- Coordinated forgery of serialized accepted evidence: offline checks establish
  internal provenance consistency, not cryptographic provider attestation.
  No exhaustive anti-forgery guarantee or accepted publication is claimed;
  independent provider audit would need separate authorized work.

No second reviewer is dispatched after fixes: regression tests and the final
full suite are the fix-pass gate. No merge, push, PR or live promotion is authorized.
