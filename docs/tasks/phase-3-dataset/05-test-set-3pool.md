# T3.5 — Benchmark agent-authored, human-reviewed (GoogleSQL)

## Trạng thái hiện tại — 2026-10-16

**English đã finalized**: 100 câu tại `data/dataset/test/test-100.jsonl`,
manifest và genuine live evidence cùng thư mục. 120 English candidates đã có
120 human ACCEPT events; final selection là 30 easy / 50 medium / 20 hard.
Không mở lại vòng review 120 English candidates. B0 genuine evaluation đã hoàn
tất, 0/100; giữ negative finding, không tune trên benchmark.

**Vietnamese đã finalized**: user xác nhận ACCEPT toàn bộ 100 paired candidates
và điểm chung **5/5/5/1** (naturalness/SQL faithfulness/terminology/ambiguity).
Đã append 100 events, round 1, `reviewer_role=user`; không sửa candidate gốc.
`test-100-vi.jsonl`, `manifest-vi.json`, `live-evidence-vi.json` đã publish bằng
CLI hiện có. `validate-final` pass; live evidence reuse exact English SQL/result
contracts, giữ original job IDs/timestamp, zero new BigQuery jobs. Đây là user
bulk confirmation trong chat, không phải 100 nhận xét riêng được agent chấm.

[Finalization evidence](../../research/t35-vi-finalization-2026-10-16.md).
[Review pack 10 × 10](../../../data/review_packs/t3_5_vi_2026-10-16/README.md) giữ
nguyên như snapshot chuẩn bị trước review, lúc đó có 0 human events; không dùng
các số liệu lịch sử đó làm trạng thái pending hiện tại.

## Mục tiêu và provenance

English profile `agent_authored_human_reviewed_v1`: agent soạn NL/SQL, một human
reviewer quyết định. Vietnamese được agent soạn từ gold SQL, semantic metadata
và catalog context, không dịch English surface text; cần cùng quy trình review
Vietnamese thật. Không claim independent authorship/review, inter-rater agreement
hoặc Cohen's kappa. Thiết kế `three_pool_v1` là đường lịch sử/optional, không phải
acceptance active.

## Artifacts

| Phần | Đường dẫn | Trạng thái |
| --- | --- | --- |
| English original draft | `data/review_drafts/t3_5_candidate_set_2026-09-27/` | 120 reviewed; selection 100, giữ audit |
| English final | `data/dataset/test/test-100.jsonl` + `manifest.json` + `live-evidence.json` | Finalized, exact output SHA-256 `5d342a5c063ea2d4b5fb7cd62ab15fabb82d2164e5eca5cb248843797989ff0d` |
| Vietnamese source/review | `data/review_drafts/t3_5_vi_candidate_set_2026-10-07/` | 100 immutable candidates; 100 user ACCEPT events |
| Vietnamese final | `data/dataset/test/test-100-vi.jsonl` + `manifest-vi.json` + `live-evidence-vi.json` | Finalized; exact reused English live evidence, no new jobs |
| Vietnamese review aids | `data/review_packs/t3_5_vi_2026-10-16/` | 10 batches of 10, bound to candidate file SHA-256 `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96` |

## Workflow Vietnamese

1. User đọc batch, cung cấp decision `ACCEPT`/`REVISE`/`REJECT` và bốn điểm thật
   theo REVIEW_GUIDE. Naturalness, SQL faithfulness, terminology ≥4; ambiguity ≤2
   cho ACCEPT. REVISE cần `revised_question` rồi round kế tiếp; tất cả 100 pair
   cần final ACCEPT, không có event sau ACCEPT. Không tự tạo human decisions.
2. Đối chiếu pack/candidate binding; append đúng event user vào log gốc. Không
   sửa candidate nguồn, SQL hoặc tự chọn replacement cho REJECT.
3. Chạy offline draft validation; kiểm tra schema/round/score khi nhận events.
   CLI hiện chưa có lệnh validation từng batch riêng; `apply-review` là finalizer,
   không dùng nó để giả vờ đã accept một batch.
4. Sau đủ 100 ACCEPT, áp dụng review và kiểm tra/publish exact paired evidence
   theo existing workflow. SQL/metadata khớp English có thể reuse evidence theo
   policy; chỉ gọi bounded BigQuery nếu cần và có authorization riêng.

```bash
PYTHONPATH=src python scripts/22_vietnamese_testset_workflow.py validate-draft \
  --candidates data/review_drafts/t3_5_vi_candidate_set_2026-10-07/candidates.jsonl
```

Tên lệnh finalization hiện là `apply-review`, không phải `finalize` như guide
ngày 2026-10-07 ghi. Khi đã đủ human events, phải truyền explicit
`--candidates` và `--review-events` tới đúng draft 2026-10-07 vì default CLI
vẫn là draft 2026-10-04. Không chạy author-draft/review lại English.

## Acceptance

- [x] English review/selection/live evidence/finalization hoàn tất.
- [x] Strict contracts, SQL/catalog/CQ/leakage gates, downstream support.
- [x] Vietnamese 100 candidates hợp lệ, snapshot/English binding.
- [x] Vietnamese review pack offline, training adapter khóa tại `9adf02c` trước
  khi mở nội dung benchmark để chuẩn bị pack.
- [x] User ACCEPT đủ 100 Vietnamese pairs, điểm chung 5/5/5/1 được xác nhận rõ; không REVISE/REJECT.
- [x] Apply review, validate exact final paired/live-evidence binding và khóa
  immutable Vietnamese snapshot. Gate đóng bằng user events + final artifacts, không bằng pack.

## Chống leakage và thứ tự thực hiện

Candidate/final questions và gold SQL không được dùng cho training, fine-tuning,
few-shot retrieval corpus, prompt/linker tuning, hyperparameter search hoặc sửa
hệ thống dựa trên lỗi trước khi primary evaluation được khóa. B2 chỉ consume
7.208 train records từ T3.3 qua export đã hash-bind; 792 development records
không vào retrieval. Giữ canonical, accepted Stage A/catalogue/exclusion index.

Data integration + Vietnamese review/finalization (đều hoàn tất) → B1/B2 genuine →
T5.4 comparison → T5.5 quyết định B3. Không thay model hoặc thresholds, không
mở lại Stage D noise hoặc hosted LLM baselines.

## Lịch sử và tài liệu

English live policy tại finalization là 24 GiB/query, 600 GiB aggregate, US,
cache off, dry-run batch trước execution; evidence pin exact selected SQL.
Không rerun live để cập nhật trạng thái docs. Failed training audit ban đầu,
audit r1 và các historical benchmark paths giữ nguyên.

- Active English spec: `docs/superpowers/specs/2026-09-27-t3-5-agent-reviewed-benchmark-design.md`
- Historical spec: `docs/superpowers/specs/2026-08-15-t3-5-google-sql-test-set-design.md`
- Code: `src/nl2sparql/dataset/testset/`, `scripts/12_test_set_workflow.py`,
  `scripts/22_vietnamese_testset_workflow.py`
