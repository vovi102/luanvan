# T3.3 — Paraphrasing GoogleSQL hai giai đoạn

## Mục tiêu

Chuyển 1.000 câu `nl_seed` đã được live-verify ở Stage A thành tiếng Anh tự
nhiên mà không thay đổi ý nghĩa truy vấn:

- **Stage B:** một câu hỏi formal cho mỗi GoogleSQL record.
- **Stage C:** ba biến thể `casual`, `abbreviated`, `alternative` cho mỗi câu
  formal.

Hai stage dùng model khác nhau để giảm single-model bias. SQL và provenance
Stage A là immutable; LLM chỉ sinh câu hỏi.

## Contract đã chốt

- Source: `data/dataset/raw/synthetic-stage-a.jsonl`, đúng 1.000 records, SHA-256
  `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`.
- Stage B: `openai/gpt-4.1-mini`, temperature `0`.
- Stage C: `google/gemini-2.5-flash`, temperature `0.7`.
- Gateway: OpenRouter non-streaming, strict JSON Schema và
  `provider.require_parameters=true`.
- Concurrency mặc định 10; tối đa 3 attempts cho 429, 5xx và timeout.
- Tổng chi phí thực tế từ `usage.cost` không vượt `$30`; thiếu cost thì fail
  closed.
- Checkpoint theo source hash, prompt hash, stage và model; resume không gọi lại
  record đã được chấp nhận và vẫn cộng chi phí lịch sử.

Prompt truyền GoogleSQL, `nl_seed`, canonical `slot_values` và entity context.
Response phải lặp lại chính xác danh sách `name=value`; validator kiểm tra thêm
date, numeric, token và entity/address anchors trước khi ghi checkpoint.

## Artifacts

- `synthetic-stage-b.jsonl`: đúng 1.000 records, thêm `nl_formal` và metadata
  generation Stage B.
- `synthetic-stage-c.jsonl`: đúng 3.000 child records, có `parent_id`, `version`,
  `nl`, `nl_normalized`, nguyên SQL/provenance và metadata Stage C.
- `cost_log.csv`: một dòng cho mỗi generation ID, không chứa key hoặc prompt.
- `paraphrase-config.json`: source/output hashes, pinned models, counts, quality,
  actual cost và deterministic audit IDs (seed 42).
- `.stage-b.checkpoint.jsonl` và `.stage-c.checkpoint.jsonl`: partial state để
  resume; không phải final artifact.

Final JSONL chỉ được atomic replace sau khi toàn stage qua validation. Stage C
yêu cầu 3.000 câu normalized khác nhau và dataset-wide mean normalized
Levenshtein distance lớn hơn `0.30`.

## Cách chạy

Offline preflight không cần credential:

```bash
uv run python scripts/10_paraphrase_stage_a.py --mode validate-only
```

Live run sau khi cấu hình key:

```bash
export OPENROUTER_API_KEY='<configured outside the repository>'
uv run python scripts/10_paraphrase_stage_a.py --mode all
```

Có thể dùng `--mode stage-b` hoặc `--mode stage-c` để resume riêng từng stage.
Không commit API key. Notebook `notebooks/09_paraphrase.ipynb` dùng cho preflight,
quality summary và audit IDs.

## Acceptance criteria

- [x] Source Stage A đúng 1.000 records và pinned SHA-256.
- [x] Strict Stage B/C response, prompt, fact-anchor và diversity validators.
- [x] Async runner có retry, concurrency bound, checkpoint/resume và actual-cost
  hard cap.
- [x] Final artifact writers atomic; manifest và audit sample IDs deterministic.
- [x] Offline unit/integration tests và validate-only không khởi tạo API client.
- [ ] Stage B live: 1.000/1.000 records; manual faithfulness audit 50 records đạt
  ít nhất 95%.
- [ ] Stage C live: 3.000 unique records; mean distance >30%; audit 100 parents
  đạt ít nhất 90% natural và 95% faithful.
- [ ] Tổng actual OpenRouter cost của Stage B + C không vượt `$30`.

## Trạng thái — external credential gate

Implementation và offline validation đã hoàn tất ngày 2026-08-09. Môi trường
hiện không có `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, file
`.env`, hoặc Ollama runtime. Vì vậy 2.000 live calls, final Stage B/C artifacts
và manual audits chưa thể thực hiện trung thực. Task dừng ở checkpoint có thể
resume; các acceptance live ở trên không được hạ thấp hoặc đánh dấu hoàn tất.

Chi tiết thiết kế và execution plan:

- `docs/superpowers/specs/2026-08-09-t3-3-sql-paraphrasing-design.md`
- `docs/superpowers/plans/2026-08-09-t3-3-sql-paraphrasing.md`
