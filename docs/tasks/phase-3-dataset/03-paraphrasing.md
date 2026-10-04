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
- Stage B: `gemini-3.5-flash`, temperature `0`.
- Stage C: `gemini-3.5-flash-lite`, temperature `0.7`.
- Cả hai stage pin `thinkingLevel=minimal` và `maxOutputTokens=1024`; response
  có `finishReason` khác `STOP` bị từ chối trước checkpoint.
- Provider: Gemini Developer API trực tiếp, non-streaming, JSON Schema qua
  `responseMimeType=application/json` và `responseJsonSchema`.
- Concurrency mặc định 10; tối đa 3 attempts cho 429, 5xx và timeout.
- Chỉ chạy bằng project Gemini Free Tier không gắn billing; bắt buộc operator
  attestation `GEMINI_FREE_TIER_CONFIRMED=1`, cost cap là `$0.00` và không
  fallback sang paid provider/model. Gemini response không cung cấp authoritative
  per-request USD cost, nên `$0.00` là recorded contract value, không phải billing
  evidence độc lập.
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
- `cost_log.csv`: một dòng cho mỗi generation ID, ghi `$0.00` theo Free Tier
  contract và không chứa key hoặc prompt.
- `paraphrase-config.json`: source/output hashes, pinned models, counts, quality,
  provider/billing tier, recorded cost và deterministic audit IDs (seed 42).
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
export GEMINI_API_KEY='<configured outside the repository>'
export GEMINI_FREE_TIER_CONFIRMED=1
uv run python scripts/10_paraphrase_stage_a.py --mode all
```

Có thể dùng `--mode stage-b` hoặc `--mode stage-c` để resume riêng từng stage.
Không commit API key. Notebook `notebooks/09_paraphrase.ipynb` dùng cho preflight,
quality summary và audit IDs.

## Acceptance criteria

- [x] Source Stage A đúng 1.000 records và pinned SHA-256.
- [x] Strict Stage B/C response, prompt, fact-anchor và diversity validators.
- [x] Async runner có retry, concurrency bound, checkpoint/resume và zero-cost
  hard cap.
- [x] Final artifact writers atomic; manifest và audit sample IDs deterministic.
- [x] Offline unit/integration tests và validate-only không khởi tạo API client.
- [ ] Stage B live: 1.000/1.000 records; manual faithfulness audit 50 records đạt
  ít nhất 95%.
- [ ] Stage C live: 3.000 unique records; mean distance >30%; audit 100 parents
  đạt ít nhất 90% natural và 95% faithful.
- [ ] Stage B + C chạy bằng operator-attested Free Tier project và tổng recorded
  cost bằng `$0.00`; báo cáo rõ không có authoritative billing evidence.

## Trạng thái — external credential gate

OpenRouter contract ngày 2026-08-09 đã được thay thế ngày 2026-10-04 bằng hai
model Gemini Free Tier gọi trực tiếp. Implementation và offline validation đã
hoàn tất; môi trường vẫn cần `GEMINI_API_KEY` thuộc project Free Tier không gắn
billing để chạy 2.000 live calls và đặt `GEMINI_FREE_TIER_CONFIRMED=1`. Quota
thực tế lấy từ Google AI Studio; khi hết quota, rerun cùng lệnh để resume từ
checkpoint. Free Tier có thể dùng prompt và response để cải thiện sản phẩm
Google, nên limitation này phải được công bố.

Chi tiết thiết kế và execution plan:

- `docs/superpowers/specs/2026-08-09-t3-3-sql-paraphrasing-design.md`
- `docs/superpowers/plans/2026-08-09-t3-3-sql-paraphrasing.md`
