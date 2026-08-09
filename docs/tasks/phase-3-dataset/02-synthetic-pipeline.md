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
- [ ] Live preflight pass trong 20/96 GiB gates.
- [ ] 100% final records có non-empty witness; zero cache hits.
- [ ] Final artifacts/stats/config được tạo và hash-verified.
- [ ] Full pytest, Ruff, format, `git diff --check` pass; worktree clean.

## Trạng thái

`implementation green locally — live witness run pending`

## Chạy lại

Offline deterministic candidates:

```bash
uv run python scripts/09_generate_stage_a.py
```

Live witness verification:

```bash
uv run python scripts/09_generate_stage_a.py --live
```

## Historical scaffold

Scaffold SPARQL ngày 2026-07-04 được giữ trong git history và hai design/plan
files có nhãn superseded. Evidence `3 passed` khi đó chỉ chứng minh offline
rendering, không còn là acceptance contract hiện hành.
