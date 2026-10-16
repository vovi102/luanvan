# Canonical bilingual training corpus — 2026-10-15

Status: canonical clean corpus published locally after the user approved the
offline build/validation step following `a62c076`. Two builds are byte-identical;
both staged triples and the canonical triple pass CLI 21 artifact validation.
No model training, evaluation, noise generation, BigQuery call, merge, push or PR.

The evidence retains its 2026-10-15 logical run identifier. Final verification
and handoff continued on 2026-10-16 (Asia/Saigon).

## Published artifacts

| Artifact | Bytes | File SHA-256 |
| --- | ---: | --- |
| [Corpus](../../data/dataset/processed/bilingual-training.jsonl) | 16,754,825 | `72285871518a14c0a30e09ee31e58bbb06bfb25089465555625ad9fd929f7f55` |
| [Manifest](../../data/dataset/processed/bilingual-training-manifest.json) | 3,098 | `a4db0c4afde877ac93ac1420c68434774ca73c2f3cc1b9b90697491c56547e28` |
| [Audit](../../data/dataset/processed/bilingual-training-audit.jsonl) | 89,741 | `3d10f0d0e1f3db9e46367e7b924cc8e1232ef33f29361bf26d463dad2a76df62` |

The corpus has 8,000 records: 4,000 English and 4,000 Vietnamese, 25 intents,
1,000 semantic families and eight language/style combinations per family.
Each of the four styles has 2,000 records. Seed-42 grouped splitting yields
7,208 train records (901 families) and 792 development records (99 families),
not a forced 7,200/800 allocation. No family crosses the split.

Every rendered row retains the accepted source's SQL verbatim, exact slot
values, source-record digest and template digest. Slot values are serialized
as sorted key/value pairs, whereas Stage A stores a dictionary. An additional
ad-hoc check initially compared those unlike containers directly and failed;
checking the documented exact sorted-pair representation passes all 8,000
rows. This was a diagnostic assumption error, not a corpus or renderer change.

## Reproducibility and publication

CLI 20 uses `--audit` as both an input and a transactional output, and requires
the output, manifest and audit to share a directory. Two separate ignored
staging directories therefore received byte-exact copies of the approved r1
audit. The immutable dated audit evidence was never used as an output path.

Both CLI 20 builds exited 0 with 8,000 records. Separate CLI 21 invocations
recomputed source/catalogue equality, record integrity, SQL/slot preservation,
split assignment, diversity, leakage and audit gates; both exited 0. All three
payloads, not only their reported hashes, were compared byte-for-byte.

Only then did the existing `assembly.publish_artifacts` publish the exact
validated payloads to the previously absent canonical paths. Post-publication
bytes match both staged triples; a further full CLI 21 invocation against the
canonical paths exited 0 with `status=valid`. No journal, backup or temporary
publication file remains. The persistent publisher lock is retained; a narrow
`.gitignore` rule excludes only `data/dataset/processed/.bilingual-publish-*.lock`.
No production code, test, renderer, catalogue, schema or SQL changed in this step.

The manifest's `manifest_body_sha256` is
`c56ed82aff8419e606157a8700802182a85e1f4ddb50f1d115bb28da5cc7888a`;
this is distinct from the complete manifest file hash above.

## Quality and scope

- All 2,000 family/language groups pass diversity: minimum mean pairwise
  normalized Levenshtein distance 0.3197242273, mean 0.5635130373, maximum
  0.7137188209; no failing group.
- Digest-only exclusion checks cover all 8,000 records with zero full-text or
  12-gram matches. No held-out benchmark question wording was read in this step.
- The canonical audit is an exact copy of the approved r1 event log: 100 EN
  and 100 VI reviewed rows, each language 100 faithful and 100 natural.
- Accepted Stage A data/manifest, active catalogue, exclusion index and dated
  audit evidence retain their pinned hashes. Initial failed-audit evidence is
  preserved, not relabeled.
- Each build/validation process ran under the archived Python offline guard:
  zero observed credential reads, socket connection attempts, provider imports
  and subprocess attempts. This is Python-level instrumentation, not an OS
  sandbox. All records declare zero API requests, operational cost 0.0, and
  null provider/model; operational cost is not a provider billing statement.

The finite controlled-language corpus is agent-authored and the r1 audit is
same-agent review, **not human or independent review** and not 8,000 individually
reviewed rows. Digest exclusion does not establish semantic benchmark
independence. These results do not establish generalization, empirical task
difficulty, population naturalness or solver quality. The separate human
benchmark-review requirement remains unchanged.

## Verification evidence

Fresh bilingual tests: **94 passed** across three completed invocations:
workflow 8 in 214.56s, assembly 34 in 32.40s, and the other bilingual files
52 in 204.35s. Ruff check and format check (12 files) pass. An earlier extra
test invocation was interrupted at session transition without a final result;
it is not counted as passing evidence. The completed runs cover all six
`test_bilingual_*.py` files. This operation did not rerun the
full repository suite; the 1,485-test result in the r1 report belongs to that
earlier frozen revision, not this build operation.

Machine-readable bindings, exact CLI command templates, checks and log links:
[canonical build evidence](../evidence/bilingual-training-canonical-build-2026-10-15.json).
The [archived offline runner](../evidence/bilingual-training-canonical-offline-runner-2026-10-15.txt)
can be invoked with `.venv/bin/python <runner> <CLI script> <arguments>` from
the repository root. Staged builds require a directory containing an exact
copy of the approved r1 audit; canonical publication used the existing publisher,
not a new CLI or modified historical evidence.

Prior scope and audit: [catalogue correction / r1](bilingual-training-audit-correction-r1-2026-10-15.md).
Further training/evaluation or noisy-corpus work is outside this approved step.
