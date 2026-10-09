# T3.3 — Deterministic bilingual GoogleSQL training data

> **Supersession (2026-10-07):** Luồng Gemini Stage B/C bên dưới chỉ còn là
> historical pilot chưa chạy live. Nó đã bị thay thế bởi catalog hữu hạn do agent
> soạn và renderer deterministic offline; không cần API key, provider hay model.

## Mục tiêu hiện hành

Mở rộng Stage A đã accept thành corpus song ngữ sạch bằng đúng 200 pattern:
25 intent × `en|vi` × `formal|conversational|abbreviated|alternative`. Mỗi
semantic family sinh tám record, giữ nguyên GoogleSQL, slots, entity annotations,
schema elements và source hashes. Provenance bắt buộc là `author_type=agent`,
`producer_type=deterministic_template_renderer`,
`review_type=agent-reviewed`, provider/model null, API calls `0`, recorded cost
`$0.00`.

Implementation hiện có:

- Catalog: `src/nl2sparql/dataset/bilingual/templates.json` (200 entries,
  25 intent, exact language/style coverage).
- CLIs: `scripts/20_build_bilingual_training.py` và
  `scripts/21_validate_bilingual_training.py`.
- Exclusion index: `data/dataset/processed/bilingual-training-exclusion-index.json`,
  100 English + 100 Vietnamese source records, 12-token n-grams, index SHA-256
  `ef5bec4c0d949d657ca6c0c321ae5e62e06f77e7bc5bdf2c6d94cc550a6239fa`;
  artifact chỉ chứa counts và irreversible hashes.
- Gates: immutable semantic fields; diversity trung bình theo family/language
  phải `>0.30`; exclusion index chỉ chứa hash; split theo semantic family; audit
  deterministic 100 câu/ngôn ngữ phủ 25 intent × 4 styles; ngưỡng ≥95 faithful
  và ≥90 natural; publication ba file có lock/journal/recovery.

Stage A đã ghim có 1.000 rows nhưng chỉ đại diện 16/25 intent. Vì vậy validation
và expansion 8.000 rows chạy được, còn audit/canonical publication cố ý fail
closed. Không được tái sinh chín intent còn thiếu hoặc gọi LLM để lấp chỗ trống;
task chỉ tiếp tục khi có một Stage A 25-intent đã được accept hoặc quyết định
governance mới thay đổi gate. Bộ 100 Vietnamese benchmark candidates riêng vẫn
chờ user review; chưa có final Vietnamese benchmark.

## Acceptance criteria hiện hành

- [x] Catalog đúng 200 entries và strict contract/digest.
- [x] Renderer tạo đúng 8.000 records, 4.000 mỗi ngôn ngữ, tám mỗi family.
- [x] Exclusion, leakage, split, audit, manifest và atomic publication gates.
- [x] CLI offline, secret-safe, zero request/cost, fail-closed.
- [ ] Accepted Stage A phủ đủ 25 intent.
- [ ] Agent audit 100 English + 100 Vietnamese đạt ngưỡng.
- [ ] Canonical artifact/manifest/audit được build hai lần byte-identical và
  validate độc lập.

## Historical Gemini pilot (superseded, incomplete)

### Mục tiêu lịch sử

Chuyển 1.000 câu `nl_seed` đã được live-verify ở Stage A thành tiếng Anh tự
nhiên mà không thay đổi ý nghĩa truy vấn:

- **Stage B:** một câu hỏi formal cho mỗi GoogleSQL record.
- **Stage C:** ba biến thể `casual`, `abbreviated`, `alternative` cho mỗi câu
  formal.

Hai stage dùng model khác nhau để giảm single-model bias. SQL và provenance
Stage A là immutable; LLM chỉ sinh câu hỏi.

### Contract lịch sử

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

### Artifacts lịch sử

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

### Cách chạy lịch sử

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

### Acceptance criteria lịch sử

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

### Trạng thái lịch sử

OpenRouter contract ngày 2026-08-09 từng được thay thế ngày 2026-10-04 bằng hai
model Gemini Free Tier gọi trực tiếp, nhưng không có live Stage B/C artifact nào
được tạo. Quyết định deterministic ngày 2026-10-07 thay thế cả hai phương án;
không tiếp tục xin credential hay thực hiện 2.000 live calls cho training data.

Chi tiết thiết kế và execution plan:

- `docs/superpowers/specs/2026-08-09-t3-3-sql-paraphrasing-design.md`
- `docs/superpowers/plans/2026-08-09-t3-3-sql-paraphrasing.md`
