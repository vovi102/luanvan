# T3.5 — Benchmark agent-authored, human-reviewed (GoogleSQL)

## Mục tiêu và provenance

Tạo benchmark cuối gồm 100 cặp NL–GoogleSQL để đánh giá generalization trên
BigQuery analytical catalog. Profile active là
`agent_authored_human_reviewed_v1`: Codex soạn 120 ứng viên, user review toàn bộ
và chọn 100 câu. Vì cùng một agent soạn NL và SQL và chỉ có một human reviewer,
artifact không được claim independent authorship, independent review,
inter-rater agreement hoặc Cohen's kappa.

Thiết kế three-pool tháng 8 (`three_pool_v1`) vẫn được giữ trong code, spec và
test như một đường lịch sử/optional. Nó không còn là acceptance path active và
không được dùng để mô tả provenance của benchmark mới.

## Artifact active

Draft review nằm tại
`data/review_drafts/t3_5_candidate_set_2026-09-27/`:

- `candidates.jsonl`: 120 dòng immutable, ID `t35-001..t35-120`, quota đề xuất
  36 easy / 60 medium / 24 hard;
- `review_events.csv`: append-only human decisions; hiện chỉ có header;
- `final_selection.csv`: lựa chọn 100 câu; hiện chỉ có header;
- `REVIEW_GUIDE.md`: quy tắc score, revise/accept và handoff;
- `manifest.json`, `validation-report.json`: evidence `draft_ready`, hash-bound
  với candidate source, catalog và leakage corpora.

Final output chỉ được publish tại `data/dataset/test/test-100.jsonl` sau khi đủ
review, selection và live evidence. File final này chưa tồn tại ở trạng thái
`draft_ready`.

## Workflow

```bash
# Offline; không khởi tạo credential hoặc BigQuery client
.venv/bin/python scripts/12_test_set_workflow.py reviewed validate-candidates \
  --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27

.venv/bin/python scripts/12_test_set_workflow.py reviewed validate-review \
  --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27

# Chỉ chạy sau khi user duyệt và cho phép live access rõ ràng
.venv/bin/python scripts/12_test_set_workflow.py reviewed verify-live \
  --allow-bigquery --project <gcp-project> \
  --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27

.venv/bin/python scripts/12_test_set_workflow.py reviewed finalize \
  --draft-root data/review_drafts/t3_5_candidate_set_2026-09-27
```

Live policy cố định là 20 GiB/query, 64 GiB aggregate, location `US`, query cache
tắt, dry-run toàn batch trước execution. Finalizer yêu cầu evidence hiện hành cho
đúng 100 selected rows và publish JSONL/manifest immutable.

## Acceptance status

### Hoàn tất

- [x] Contract/profile strict, review state machine và exact final schemas.
- [x] Offline SQL/catalog/CQ/leakage validation và guarded CLI.
- [x] Immutable live-evidence/finalization contract và downstream B0–B5 support.
- [x] 120 candidate rows đạt `draft_ready`, đúng quota 36/60/24 và coverage.
- [x] Draft manifest/report pin candidate, catalog, leakage và repository commit.
- [x] Review/selection source tách riêng; tooling không tự tạo human decision.

### Còn pending — human/live gates

- [ ] User review đủ 120 candidates với một reviewer ID ổn định; mọi `REVISE`
  phải có event `ACCEPT` sau đó và score acceptance tối thiểu 4/5.
- [ ] User chọn đúng 100 accepted rows với quota 30 easy / 50 medium / 20 hard,
  ít nhất sáu categories và đủ ba entity kinds.
- [ ] Codex chạy lại offline `validate-review` và xử lý lỗi deterministic cùng user.
- [ ] User cho phép explicit live BigQuery run; 100 SQL có current bounded evidence.
- [ ] `finalize` publish immutable `test-100.jsonl` và manifest. Chỉ lúc đó mới
  mở genuine B0–B5 accuracy evaluation.

## Chống leakage

Candidate/final questions và mọi biến thể bị cấm dùng cho training, fine-tuning,
few-shot retrieval corpus, prompt/linker tuning, hyperparameter search hoặc sửa hệ
thống dựa trên lỗi trước khi primary evaluation được khóa. Downstream chỉ consume
final snapshot theo hash manifest.

## Historical three-pool path

Spec/plan tháng 8 và các top-level CLI `scaffold`, `validate`, `verify-live`,
`finalize` tiếp tục tái lập `three_pool_v1`; không bị rewrite. Chúng yêu cầu ba
vai độc lập và có thể tính kappa khi có cộng tác viên thật. Profile active dùng
subgroup `reviewed` và tuyệt đối không thừa kế các claim đó.

Linked:

- Active spec: `docs/superpowers/specs/2026-09-27-t3-5-agent-reviewed-benchmark-design.md`
- Active plan: `docs/superpowers/plans/2026-09-27-t3-5-agent-reviewed-benchmark.md`
- Historical spec: `docs/superpowers/specs/2026-08-15-t3-5-google-sql-test-set-design.md`
- Code: `src/nl2sparql/dataset/testset/`, `scripts/12_test_set_workflow.py`
