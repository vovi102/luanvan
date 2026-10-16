# T5.2 — B1/B2 GoogleSQL Small-LLM Baselines (Llama 3 8B)

## Mục tiêu

Triển khai hai raw-model baselines sau Pivot #1:

- **B1:** Llama 3 8B Instruct zero-shot, chỉ nhận câu hỏi và analytical catalog
  summary.
- **B2:** cùng model/config với B1, thêm đúng năm ví dụ gần nhất từ training pool.

B1/B2 sinh một read-only GoogleSQL query hoặc fail closed. Hai baseline không
dùng schema linker, entity linker hay class resolver; khác biệt này được giữ để
định lượng đóng góp linking ở các thí nghiệm sau.

T5.2 chỉ inference, **không train model**. Workstation local GTX 1650 4 GiB không
được dùng để thay thế evidence Kaggle T4 và task không tải Llama 3 8B ở local.

## Quyết định kiến trúc

Deep module `src/nl2sparql/models/b12/` che catalog compilation, prompt,
retrieval, backend generation, extraction, provenance và evaluation sau hai
interface:

```python
BaselineB1.predict(question: str) -> str | None
BaselineB1.predict_detailed(question: str) -> SmallLLMPrediction

BaselineB2.predict(question: str, *, target_id: str | None = None) -> str | None
BaselineB2.predict_detailed(
    question: str,
    *,
    target_id: str | None = None,
) -> SmallLLMPrediction
```

Generation backend và text encoder là internal seams. Test dùng adapter
deterministic; production dùng Transformers/SentenceTransformers được import
lazy sau input/artifact preflight. Synthetic adapter luôn được đánh dấu và không
thể tạo scientific readiness; chỉ production loader có thể phát genuine
backend provenance.

## Phụ thuộc và artifact boundary

- T2-SQL-1 analytical catalog là prompt schema authority.
- T3.5 finalized test set cung cấp exact reviewed/live GoogleSQL evidence.
- T3 training artifact cung cấp B2 examples và phải tách khỏi test set.
- T3.5 SQL safety validator enforce một read-only statement, explicit
  projections và managed relations.
- Model/encoder revision phải là pinned lowercase 40-hex revision.

English T3.5 đã finalized với human review/live evidence. Stage A v2 accepted và
T3.3 canonical published tại `2b652a3`; offline data integration T3.3 → B2 đã
hoàn tất tại `9adf02c`. Vietnamese đã finalized với 100 user ACCEPT events (5/5/5/1) và exact
reused English live evidence; không có new BigQuery jobs. Chưa có genuine B1/B2 Kaggle runs; không dùng fixture để đóng gate.

## Module và output

- `src/nl2sparql/models/b12/contracts.py`: immutable config/completion/prediction.
- `catalog_summary.py`: validate, summarize và fingerprint exact catalog bytes.
- `prompts.py`: một system prompt chung; chỉ B2 có examples block.
- `retrieval.py`: cosine top-5 deterministic, leakage exclusion và atomic cache.
- `extraction.py`: whole-output GoogleSQL extraction fail closed.
- `baseline.py`: public B1/B2 orchestration và generation-only latency.
- `transformers_backend.py`: lazy 4-bit Kaggle adapter, không có import-time Torch.
- `evaluate.py`: operational metrics và trusted T3.5 provenance gate.
- Compatibility deliverables: `b1_zero_shot.py`, `b2_few_shot.py`.
- CLI: `scripts/17_small_llm_baselines.py`.

Khi external artifacts/model có mặt, workflow publish atomically:

- `data/eval/predictions/b1_test.jsonl`, `b2_test.jsonl`;
- `data/eval/logs/b1_run.jsonl`, `b2_run.jsonl`;
- `reports/b1_inference.json`, `b2_inference.json`.

Mỗi prediction giữ run ID, seed, UTC timestamp, input SHA-256, raw output, parsed
GoogleSQL, extraction status, model/config/catalog/summary/prompt/training
fingerprints, token counts, latency, B2 selected-example identities và digest
của exact selected-example content. Log và report giữ cùng run provenance.

## Prompt, retrieval và extraction contract

B1/B2 dùng model `meta-llama/Meta-Llama-3-8B-Instruct`, seed 42, greedy decoding,
`do_sample=False`, `max_new_tokens=512`, batch size một. Temperature không được
truyền trong greedy mode. Production load 4-bit bằng `BitsAndBytesConfig` và chỉ
sau explicit `--real-inference`.

B2 đọc exact UTF-8 JSONL training bytes, yêu cầu unique ID/câu hỏi, `split=train`
và safe GoogleSQL. Legacy schema vẫn yêu cầu `synthetic_fixture=false` và đầy đủ
`text_variant` metadata. Với canonical T3.3, adapter kiểm tra exact accepted
publication/source hashes và byte equality với train-only projection; giữ `style`,
không rename semantics hoặc thêm fixture flag. Export chứa nguyên dòng canonical,
7.208 records / 901 families (3.604 EN + 3.604 VI); không có 792 development records.

Artifact tiêu thụ là `data/dataset/processed/b2-training.jsonl`, kèm recipe/hash
manifest `b2-training.manifest.json`; accepted-training fingerprint phải là
`b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835`, **không phải**
hash corpus canonical 8.000 rows. Khi bundle cho Kaggle phải kèm bảy pinned
source files được liệt kê trong manifest; adapter từ chối source đã đổi.
CLI17 cần explicit `--training data/dataset/processed/b2-training.jsonl` và
`--accepted-training-sha256` trên; default legacy path không được hiểu là export.

[Integration report](../../research/b2-training-integration-2026-10-16.md).
Training adapter/test được khóa trước khi đọc benchmark VI để chuẩn bị review pack.

Embedding được L2-normalize; ranking
dùng descending cosine score rồi stable record ID. Target ID và NFKC/casefold
question trùng test case bị loại trước khi chọn đúng năm examples. Cache bind
training SHA-256, encoder/revision, ordered IDs, shape/dtype và matrix digest.
B2 scientific readiness còn yêu cầu `--accepted-training-sha256` khớp exact
training snapshot; thiếu hoặc sai fingerprint đều fail closed.

Extractor chỉ unwrap một complete outer SQL fence rồi validate toàn response.
Nó không tìm `SELECT` nằm giữa prose và không cắt bỏ statement/content phía sau.
Status gồm `ok`, `empty`, `prose`, `invalid_sql`, `unsafe_sql`; chỉ `ok` trả SQL.

## Workflow local

```bash
uv run python scripts/17_small_llm_baselines.py --help
uv run python scripts/17_small_llm_baselines.py validate --baseline b1

# Chỉ chạy khi pinned model snapshot và external artifacts đã có:
uv run python scripts/17_small_llm_baselines.py predict \
  --baseline b1 \
  --question "List known Ethereum addresses" \
  --model-revision <40-hex-revision> \
  --real-inference
```

`--help`, invalid question, missing file, output-alias và T3.5 validation không
khởi tạo model. B2 cache-only `validate` cũng không load encoder. Predictions và
logs được publish trước, report cuối; failure rollback toàn bộ prior outputs.

## Acceptance criteria

### Implementation local

- [x] B1/B2 public interface và task-named compatibility imports.
- [x] Compact deterministic catalog summary bind exact source/summary SHA-256.
- [x] B1/B2 prompt parity; B2 thêm đúng năm examples, không dùng T4 linkers.
- [x] Training snapshot validation, leakage exclusion, deterministic cosine
  ranking và provenance-bound atomic embedding cache.
- [x] Whole-output extraction qua T3.5 managed read-only GoogleSQL validator.
- [x] Raw output, extraction status, token/latency và complete fingerprints.
- [x] Lazy Transformers 4-bit adapter; import/help/preflight không load ML stack.
- [x] Evaluator giữ difficulty/category/status metrics và không suy execution
  accuracy từ text/AST.
- [x] Synthetic backend/test set và manual evidence flags không thể tạo readiness.
- [x] Canonical atomic predictions/log/report, protected-path checks và rollback.
- [x] Numbered `validate`, `predict`, `evaluate` CLI với explicit real opt-in.

### Local checkpoint — 2026-09-01

- Baseline trước implementation: `869 passed, 342 warnings in 44.64s` qua
  `uv run python -m pytest -q`.
- Focused B1/B2 suite sau review fixes: `78 passed in 5.94s`.
- Focused Ruff lint/format, CLI help, B1 catalog validation và `git diff --check`
  pass tại checkpoint.
- Full repository suite sau review fixes: `947 passed, 342 warnings in 39.76s`;
  Ruff check pass và 193 files đã đúng format.
- Whole-branch Standards và Spec re-review tại `82b3e79` đều không còn
  Critical/Important finding và kết luận `ready to merge`.
- Các kết quả local này không phải Kaggle/scientific acceptance.

### Data integration checkpoint — 2026-10-16

- [x] Accepted Stage A v2 + canonical T3.3 đã hoàn tất; failed audit lịch sử giữ nguyên.
- [x] Task T3.3 → B2: lossless train export, exact consumed hash, deterministic
  rebuild và strict provenance/fixture/SQL/leakage gates.
- [x] Fresh 42 focused tests pass, bao gồm regression fail-before-fix và actual
  B2 cache/data path offline không model/encoder. Cache trong test là synthetic,
  không publish hoặc dùng làm scientific evidence.
- [x] Guarded export/data preflight và current canonical CLI21 validate-artifact pass.
- [x] English benchmark finalized; không review lại 120 candidates.
- [x] Fresh full suite sau integration: 1.505 passed, 342 warnings, 563,75s;
  không dùng lại historical 1.485-test evidence. Log và handoff tại
  `docs/research/offline-data-handoff-2026-10-16.md`.

### Pending external/scientific acceptance

- [x] Vietnamese review/finalization 100 pairs và exact live-evidence binding hoàn
  tất offline sau user confirmation; [finalization report](../../research/t35-vi-finalization-2026-10-16.md).
  Review pack/historical 0-event evidence giữ nguyên ở trạng thái lúc tạo.
- [ ] Pinned genuine encoder snapshot/revision và cache, cùng accepted train export.
- [ ] Pinned Llama 3 8B snapshot chạy đủ B1/B2 trên Kaggle T4, không OOM.
- [ ] B1 latency `<5 s/query` trên Kaggle T4.
- [ ] B2 latency `<8 s/query` trên Kaggle T4.
- [ ] Genuine prediction/log/report artifacts được publish từ các input trên.

## Trạng thái

`implementation + offline data integration + English/Vietnamese benchmark finalization complete — genuine model/encoder/Kaggle gates pending`

Thứ tự: data integration + Vietnamese review/finalization (đã xong) → B1/B2 genuine → T5.4 comparison
(B0 genuine 0/100 đã có) → T5.5 quyết định B3. Không hosted LLM baselines,
Stage D noise generation hoặc thay model/acceptance thresholds.

Linked:

- Spec: `docs/superpowers/specs/2026-09-01-t5-2-google-sql-small-llm-design.md`.
- Plan: `docs/superpowers/plans/2026-09-01-t5-2-google-sql-small-llm.md`.
- Code: `src/nl2sparql/models/b12/`, `scripts/17_small_llm_baselines.py`.
