# Stage A v2 CQ35 correction — 2026-10-15

Status: correction implemented and reviewed; the user subsequently approved
final-live and the local accepted V2 publication succeeded. See the
[acceptance report](stage-a-v2-final-live-acceptance-2026-10-15.md) for the new
run and post-publication checks. The diagnostic/preflight details below describe
the earlier approval handoff, not the current lifecycle.

The [final independent review](../superpowers/reviews/2026-10-15-stage-a-v2-cq35.md)
found no Critical, Important or Minor issues. Its offline checks independently
reproduced candidate/evidence bindings; scope limitations and all implementation
rulings are recorded there. This review predates the separately approved
final-live run and its small latency-summation fix recorded in the acceptance report.

Implements the user-approved [coverage/CQ proposal](stage-a-v2-large-class-coverage-audit-2026-10-14.md)
and [native plan](../superpowers/plans/2026-10-15-stage-a-v2-cq35-correction.md).

## Contract and frozen inputs

`T_LARGE_TX_TO_CLASS` now uses BridgeProtocol, inclusive 1 ETH in NUMERIC wei,
and `[2026-06-15, 2026-06-16)` as its example fill, mapped only to CQ35. SQL,
six projected columns, medium difficulty, 41 allocation positions and n=1..41
are unchanged. The other 24 template objects are unchanged. This is recipient
label-class membership and transaction value, not successful fund receipt,
decoded bridge activity, exchange funding, subsequent outflow or CQ26 coverage.
No receipt or address-role predicate was silently added.

Training validation explicitly selects `ethereum_analytics_stage_a_v2_1_2.json`,
version 1.2.0 with exact CQ01–CQ35. The first 34 definitions are unchanged;
unknown versions and mismatched exact ID sets are rejected. CQ35 has no sender
class/address-role restriction and does not assert successful movement.

Frozen catalogue SHA-256:

- Default 1.0.0, unchanged: `db8393aa7258d1331387eff9825e22ca729daf93234419f00d7dd538196cb3dd`.
- Training 1.1.0, unchanged: `2c800d4c1af74f24aed73bcb7881f1cd514ab068fecdb301d6c478fd3ce34fa0`.
- Training 1.2.0, new: `37101b56dbb7fb0ad135b73f2aafdf66e44a9a2c00ab0963ad45569969f057f5`.

Eight bilingual class patterns now describe native transaction value, avoiding
“transfers moved”/“chuyển” implications. No other pattern entries changed;
the catalogue remains 200 patterns (25 × 2 × 4). No canonical 8,000 records
were published.

The pre-CQ35 template library is archived byte-for-byte in
`tests/fixtures/dataset/stage-a-v2-pre-cq35-templates.json`, SHA-256
`11a03a487e53248fe9549504e8f5054b4760b3d074343a5d4c59291782c0a8b9`.
It reconstructs the immutable failed diagnostic's original candidate fingerprint
`c20be57c884baf0c8b4dac3d6f7f81031becc7df030842963413d29c6dfc7c59`.
Tests validate that historical report against old inputs and reject pairing it
with new CQ35 inputs; the report itself is not rewritten. V1, evidence pools,
historical catalogues, benchmark wording/gold and model results remain unchanged.

## Measured candidate regeneration

Two generation runs produced identical bytes. Exactly 41 records changed,
`syn-v2-000759` through `syn-v2-000799`. Actual planner output remains 206 logical
witness groups / 126 physical queries; 1,000 records, 25 intents, seed 42 and
difficulty 350/450/200 remain.

- Candidate JSONL: `5a4e0299d8f36bc3d77bc47ed7aa6ae0c10846846924b9fcd002c04c98c06cd6`.
- Candidate manifest: `edc924b6e9718a1edb0a0d10485104b0b7612a1b02eb1236636d8d9979486d03`.
- Candidate stats (unchanged): `c64bb37333bb1590dd4e01e8446a062885b590ad6095326d80a567a0a9a53187`.
- Active template library: `6f4393d9a118942a82c976f04c37ec1c51a3056a662ffd915d6db637c41ae8f9`.
- Bilingual catalogue: `00d5dc083bd22aeeee4a8515c0cda0fb0f18cc972584f0e0f57681954cbf6cfe`.
- Evidence pools (unchanged): `a6b827732320c18a274323fe4f5a5d60ea07d380065c6c1c4707b905a081fbca`.

Local verification so far: four new behavior tests failed before correction and
passed afterward; 172 focused schema/template/CQ35/bilingual/diagnostic/artifact
tests passed. Offline template and bilingual catalogue validation passed.
The full suite passed with 1,467 tests and 342 upstream warnings in 301.20s.

## Diagnostic and acceptance boundary

A one-shot diagnostic used complete initial and per-query immediate dry-runs,
20 GiB/query and 96 GiB aggregate caps. Billing must be disabled and unlinked;
query cache and SDK request/job/result retries were disabled in the injected
client, not claimed as production SDK defaults. Any first failure is retained
and stops provider work without retry.

The [diagnostic report](../evidence/stage-a-v2-cq35-diagnostic-2026-10-15.json)
passed and was validated offline against the exact new candidate. Its SHA-256
is `11f177d4c9158ca37ddeaa49c33451fa9c14860a8f608f7b2611cc705158955c`.
It records **126/126 physical executions and 206/206 logical witnesses**,
zero cache hits, initial and immediate estimates 82,852,652,009 bytes, processed
80,089,662,489 bytes and billed 80,594,599,936 bytes. No failure or retry occurred.
The corrected class intent's witness job is
`1089feae-5922-4842-b7cf-bfcd32a2a519` (one non-empty row, unchanged projection).
The candidate remains offline/unverified data; these are diagnostic proofs,
not automatically promoted accepted record verification fields.

The [post-diagnostic preflight](../evidence/stage-a-v2-cq35-preflight-2026-10-15.json)
is explicitly dry-only and `acceptance_authorized=false`, observed at
2026-10-15 20:24 Asia/Saigon (13:24 UTC). SHA-256:
`cc169d87de18a6963494cc7956bd08abd32b6717f5360594f33f768768559d7e`.
It binds the exact candidate, template-library and 1.2.0 catalogue fingerprints:

- 206 logical groups / 126 physical queries.
- Aggregate estimate **82,852,652,009 bytes (77.162545 GiB)**, under
  **103,079,215,104 bytes (96 GiB)**.
- Largest query: funding, **15,392,481,552 bytes (14.335366 GiB)**, under
  **21,474,836,480 bytes (20 GiB)**.
- Billing disabled/unlinked; cache and SDK retries disabled in the wrapper.
- A read-only post-diagnostic metadata observation confirms the live label view
  still points to `entity_labels_snapshot_cdc7856df81f`, matching the unchanged
  local dictionary hash prefix. This is not a fresh full data-column hash check.

Neither diagnostic nor preflight published accepted artifacts. At that handoff,
all three accepted-v2 paths remained absent and final-live required separate
approval. That approval and subsequent successful execution/publication are
recorded in the acceptance report above. No merge, push or PR is authorized.
