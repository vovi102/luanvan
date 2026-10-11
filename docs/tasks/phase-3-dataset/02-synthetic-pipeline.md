# T3.2 — Witness-Grounded GoogleSQL Generation (Stage A)

## Mục tiêu

Sinh đúng 1.000 cặp `(GoogleSQL, nl_seed)` deterministic từ T3.1 contract v2,
sau đó dùng bounded BigQuery witnesses để chứng minh 100% records non-empty mà
không lặp lại cùng một scan cho mọi biến thể `LIMIT`.

## Bối cảnh

Scaffold tháng 7 dùng `sparql_template`, Fuseki, RDF IRI và window 2024 nên đã
superseded sau Pivot #1. T3.1 hiện có 25 typed GoogleSQL templates, nhưng chín
example thuộc sentinel/coverage gap có thể trả rỗng và không được đưa vào
training Stage A.

Live probe toàn tháng xác nhận chỉ hai hard templates có dữ liệu:
`T_TOKEN_AFTER_NATIVE_FUNDING` và `T_REPEATED_PAIR_FLOW`. Với cap 10% mỗi
template, hard share tối đa trung thực là 20%; target cũ khoảng 25% không thể đạt
nếu vẫn bắt buộc non-empty.

## Phụ thuộc

- T3.1 — 25 GoogleSQL templates, typed renderer và live 20/64 GiB gate.
- T2.2 — role-aware entity dictionary.
- T2-SQL-2 — managed views/TVFs trên BigQuery.
- T2-SQL-3 — bounded-window correctness/cost evidence.

## Đầu ra

- `data/dataset/raw/synthetic-stage-a.jsonl` — 1.000 verified SQL records.
- `data/dataset/raw/generation-config.json` — seed, allocations, input/artifact
  hashes và live witness metrics.
- `data/dataset/raw/stats.md` — difficulty/template/entity/proof/cost stats.
- `src/nl2sparql/dataset/generate.py` — network-free candidate generator.
- `src/nl2sparql/dataset/stage_a/verify.py` — BigQuery witness verifier.
- `scripts/09_generate_stage_a.py` — offline/live atomic artifact CLI.
- `notebooks/08_generate_synthetic.ipynb` — unexecuted workflow.

## Record contract

Mỗi record lưu stable ID, template/category/difficulty, typed slot values,
`entities_used`, canonical `sql`, `nl_seed`, schema/CQ links, template/record
SHA-256, seed, witness group và verification object. Candidate identity không
phụ thuộc live latency/timestamp.

Witness group chỉ được bỏ slot `n`. Query có `LIMIT 1` được execute exact; nếu
có row thì mọi record cùng semantics với `n >= 1` được đánh dấu
`live_limit_monotonic`. Query không có `n` là singleton `live_exact`. Không
record nào claim exact result count từ propagated proof.

## Distribution contract

- easy: 350 records trên 6 live templates;
- medium: 450 records trên 8 live templates;
- hard: 200 records trên 2 live hard templates;
- mỗi template tối đa 100 records;
- mỗi typed entity value tối đa 50 records;
- 1.000 SQL strings và record hashes phải unique bằng slot variation thật,
  không dùng comment/tautology để giả diversity.

## Validation và cost safety

- Offline: exact allocation/schema/hash/render checks, typed pool provenance,
  unique SQL/IDs, template/entity caps và seed 42.
- Live: dry-run toàn bộ witness set trước mọi execution, tối đa 20 GiB/witness
  và 96 GiB tổng.
- Mỗi witness được re-dry-run ngay trước execution; query cache disabled; result
  columns phải exact; zero row/cache hit/schema drift đều fail closed.
- `T_COUNT_TX_IN_RANGE` chỉ pass khi `transaction_count > 0`, không chỉ vì
  aggregate query trả một row.
- Final JSONL/config/stats chỉ được replace sau khi toàn bộ verification pass.

## Acceptance criteria

- [x] Plan B design/plan được duyệt và commit trước implementation.
- [x] Candidate generator dùng `sql`, không còn SPARQL/Fuseki runtime contract.
- [x] Exact 1.000 records, seed 42 byte-stable, 1.000 unique SQL/hashes.
- [x] Distribution 350/450/200; template cap 100; entity cap 50.
- [x] Fake-client tests cover witness planning, full preflight, caps, schema,
  non-empty/count/cache và proof propagation.
- [x] CLI offline không tạo BigQuery client; live outputs chỉ ghi sau success.
- [x] Live preflight pass trong 20/96 GiB gates.
- [x] 100% final records có non-empty witness; zero cache hits.
- [x] Final artifacts/stats/config được tạo và hash-verified.
- [x] Full pytest, Ruff, format, `git diff --check` pass; worktree clean.

## Trạng thái

`done — 2026-08-09; 1.000 GoogleSQL records live-witness verified`

### Stage A v2 — candidate 25 intent (2026-10-10)

Stage A v1 ở trên vẫn là historical accepted artifact và không bị sửa. Một v2
candidate riêng đã được tạo để giải quyết coverage 16/25 intent:

- `synthetic-stage-a-v2-candidate.jsonl`: 1.000 records, đủ 25 intent,
  difficulty 350/450/200, seed 42; SHA-256
  `4746f68642913e0c40a0d19817cf0e4bf556f46d3ba1777a611f903e062e6561`.
- `generation-config-v2-candidate.json`: lifecycle `candidate`,
  `acceptance_eligible=false`, verification `offline_candidates`; SHA-256
  `fd5bdd9797e0e6af0ee184e9dcc4cc787a7526e3f3d05d0bdf73f8955c814a4d`.
- `stats-v2-candidate.md`: SHA-256
  `3b0f445fd12da9712f71e05a9075fd165ed32fd4cd658e1953abaa3c95e23a55`.

Các giá trị `block_number` và `transaction_hash` trong candidate vẫn chỉ là giá
trị deterministic/syntax-only; candidate không supersede acceptance của v1 và
không được dùng để publish/audit corpus canonical. Pool promotion riêng hiện có
45 block numbers và 45 transaction hashes unique với BigQuery provenance,
SHA-256 `1bdbd40f5e5a31616ee537fe01a101642609c7afb07d52cd36e19af170334fc8`.
Live promotion vẫn phải chạy toàn bộ witness gate rồi mới được ghi ba artifact
accepted riêng (`synthetic-stage-a-v2.jsonl`, `generation-config-v2.json`,
`stats-v2.md`).

Candidate identity canonicalize thứ tự template, slot và value-pool entry. Vì
vậy đảo thứ tự input không đổi bytes; hash ở trên thay thế hash candidate ban đầu
sau whole-branch review. Acceptance gate còn kiểm tra evidence trên từng record
và quan hệ đầy đủ giữa record, witness group, preflight và execution; chỉ sửa
metadata manifest không thể mở audit/build gate.

## Chạy lại

Offline deterministic candidates:

```bash
uv run python scripts/09_generate_stage_a.py
```

Stage A v2 offline candidate:

```bash
uv run python scripts/09_generate_stage_a_v2.py
```

Stage A v2 live promotion (chỉ sau khi các evidence pool và quyền chạy đã sẵn
sàng):

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --live \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

Stage A v2 dry-run-only approval boundary:

```bash
uv run python scripts/09_generate_stage_a_v2.py \
  --preflight \
  --value-pools data/dataset/raw/stage-a-v2-evidence-pools.json
```

## Stage A v2 batched preflight — 2026-10-10

- Giữ nguyên 170 logical witnesses nhưng gom 45 `T_TX_BY_HASH` lookups vào một
  physical query; measured plan có 126 physical queries.
- Exact BigQuery dry-run estimate: `101.534.116.450` bytes (`94,561015 GiB`),
  thấp hơn aggregate cap 96 GiB `1.545.098.654` bytes (`1,438985 GiB`).
- Query lớn nhất là `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE`, `15.851.661.328` bytes
  (`14,763010 GiB`), thấp hơn per-query cap 20 GiB.
- Gross on-demand estimate là khoảng `$0.577155` theo mức `$6.25/TiB`; chi phí
  thực tế còn phụ thuộc monthly free tier và billed bytes. Dry-run không execute
  query và không tạo accepted output.
- Local verification: `1.639 passed`, Ruff format/check và `git diff --check`
  pass; v1 và v2 candidate hashes giữ nguyên; cả ba accepted v2 output vẫn absent.
- Live execution và accepted artifacts vẫn pending explicit approval. Không bắt
  đầu bilingual audit, canonical build hoặc B1/B2 training ở trạng thái này.

## Stage A v2 live attempt — 2026-10-11

- User đã duyệt measured live run. Repeated preflight pass, nhưng execution dừng
  fail-closed tại witness `syn-v2-000834` của
  `T_MIXER_TO_DEX_LARGE_FLOW`: kết quả rỗng.
- Root cause là coverage contract đã biết, không phải transient provider error:
  template ghi `expect_non_empty=false` với scope note “no accepted operational
  mixer endpoint”, và analytical catalog đánh dấu `CQ21` là `coverage_gap` vì
  dictionary chưa có verified operational mixer endpoint. Điều này mâu thuẫn với
  Stage A v2 acceptance gate yêu cầu 100% records `non_empty=true`.
- Hai physical executions đã hoàn tất trước khi dừng: processed `779.483.182`
  bytes, billed `780.140.544` bytes, cache hits `0`; gross on-demand equivalent
  khoảng `$0.004435` ở `$6.25/TiB`, trước monthly free tier.
- Publication boundary hoạt động đúng: `synthetic-stage-a-v2.jsonl`,
  `generation-config-v2.json` và `stats-v2.md` đều không được tạo. Không retry,
  không sửa metadata, không hạ threshold và không bắt đầu audit/build/training.
- Promotion hiện cần một quyết định redesign: bổ sung genuine verified mixer
  coverage và chứng minh bounded flow thật, hoặc thay intent coverage-gap bằng
  một intent được support rồi tạo/hash/audit lại candidate. Cho phép empty proof
  không đáp ứng acceptance contract hiện hành.

Live witness verification:

```bash
uv run python scripts/09_generate_stage_a.py --live
```

## Live evidence — 2026-08-09

- Full preflight: 81 witness groups, estimate 61.855.311.688 bytes (57,61
  GiB), dưới total cap 96 GiB; max individual 14.368.179.853 bytes, dưới cap 20
  GiB.
- Execution: 81/81 witnesses pass, cache hit 0; processed 61.855.311.688 bytes,
  billed 61.918.412.800 bytes, total wall 196.993,36 ms. Max wall 20.107,53 ms
  tại witness `syn-000800` của `T_TOKEN_AFTER_NATIVE_FUNDING`.
- Proof propagation: 81 `live_exact` + 919 `live_limit_monotonic` = 1.000
  records có `non_empty=true`.
- Artifact audit: 1.000 unique IDs/SQL/record hashes; difficulty 350/450/200;
  max template 100; max entity 30; 16 included và 9 excluded templates.
- Final JSONL size 1.559.692 bytes; SHA-256
  `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`,
  khớp `generation-config.json`.
- Repository verification sau migration: 336 passed, 342 upstream warnings;
  Ruff check/format và `git diff --check` pass.

## Historical scaffold

Scaffold SPARQL ngày 2026-07-04 được giữ trong git history và hai design/plan
files có nhãn superseded. Evidence `3 passed` khi đó chỉ chứng minh offline
rendering, không còn là acceptance contract hiện hành.
