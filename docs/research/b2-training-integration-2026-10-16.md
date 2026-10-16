# T3.3 → B2 offline integration, 2026-10-16

The canonical publication at `2b652a3` is immutable. The derived artifact
`data/dataset/processed/b2-training.jsonl` selects its original `split=train`
lines, preserving order, bytes, IDs, questions, SQL, styles, record digests,
slots and semantic-family/source provenance. It has 7,208 records (3,604 EN +
3,604 VI), 901 families; 792 development records / 99 families are excluded.
There is no `style` → `text_variant` rename and no invented fixture/acceptance
field. The adjacent `b2-training.manifest.json` records the recipe, source
file hashes and output hash. It is explanatory provenance, not an acceptance
switch consumed by B2.

Accepted-training SHA-256 (the export, **not** the 8,000-row source):
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`.

`FewShotRetriever.from_snapshot` shares `validate_training_snapshot` with the
new data-only CLI. Canonical schema detection triggers byte-for-byte comparison
with the train projection of the exact accepted publication. The adapter pins
all seven source files: canonical corpus/manifest/audit, Stage A data/manifest,
active catalogue and digest-only exclusion index. Any change fails closed;
a future publication needs explicit new evidence and binding updates. No sidecar
can bless arbitrary content. Legacy inputs still require `synthetic_fixture=false`
and their complete bilingual metadata. IDs, normalized question uniqueness,
managed read-only SQL safety, held-out hashes/IDs and accepted fingerprint checks
remain active. Cache identity, prompt and prediction fingerprints use the exact
export digest; selected IDs/language/family remain unchanged.

Reproduce from the repository root, using the existing Python environment:

```bash
PYTHONPATH=src python scripts/22_b2_training.py export \
  --accepted-training-sha256 b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835
PYTHONPATH=src python scripts/22_b2_training.py validate \
  --accepted-training-sha256 b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835
```

The export command refuses to replace different existing bytes. Repeated export
is deterministic and resumable. B2's existing CLI must receive explicit
`--training data/dataset/processed/b2-training.jsonl` and the exact
`--accepted-training-sha256` above. Keep all pinned files in the offline Kaggle
repository bundle. Real runs additionally need genuine encoder/model snapshots,
pinned revisions and a genuine embedding cache; those remain external work.
The data-only CLI needs none of these. CLI17's cache validation continues to
require a real cache; data validation is not evidence of embeddings or inference.

The test-only synthetic cache is temporary and never published as real encoder
or scientific evidence. The training acceptance boolean describes input data;
it does not establish model/backend genuineness or scientific readiness.

## Separation from benchmark review

Training code, tests and binding evidence are committed before opening Vietnamese
benchmark content to prepare the pack. After that boundary, benchmark wording or
gold SQL must not change training, retrieval, linker, prompt or accuracy tests.
The current source retains the original failed audit and the subsequent r1 audit;
same-agent review is never presented as human or independent review.

## Verification

See `docs/evidence/b2-training-2026-10-16/` for fresh export, validate, canonical
CLI21 and test logs. The regression first failed on the old loader's missing
`synthetic_fixture` check before implementation. Negative tests reject modified
questions/SQL/IDs/family/style/digest/provenance, development rows, reordered or
partial exports, changed source binding, missing acceptance, the full-corpus
fingerprint and legacy rows missing fixture provenance.

The guarded export/validate runs observed zero connection, credential,
model/provider import or subprocess attempts. SDK imports are allowed because
existing package imports eagerly load BigQuery library definitions; no client is
created. Two initial runner failures are preserved: an overly broad SDK import
block, then a Popen typing incompatibility. They are not passing runs. The final
runner guards Python APIs, not the OS, and denies benchmark content reads during
training work. Current CLI21 `validate-artifact` is used; historical assertions
that canonical artifacts do not exist are not rerun.
