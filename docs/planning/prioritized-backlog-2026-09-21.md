# Backlog ưu tiên — small-LLM NL2SQL

> **Canonical backlog:** dùng tài liệu này để chọn công việc tiếp theo. Các ticket
> chi tiết trong `docs/tasks/` là nguồn acceptance. Ticket còn mô tả SPARQL/Fuseki
> phải được migrate sang GoogleSQL trước khi triển khai.

## Phạm vi đã chốt

Dự án nghiên cứu NL2SQL trên BigQuery với bốn cấu hình B0–B3:

| ID | Cấu hình | Vai trò |
|---|---|---|
| B0 | Rule-based | Lower-bound deterministic |
| B1 | Small LLM zero-shot | Baseline mô hình gốc |
| B2 | Small LLM five-shot | Đo tác động của retrieval/examples |
| B3 | Small LLM fine-tuned | Hệ thống đề xuất |

Không dùng mô hình qua API. Contribution thực nghiệm là so sánh zero-shot,
few-shot và fine-tuned trong cùng phạm vi small LLM, đồng thời đo đóng góp của
schema/entity/class linking.

## Snapshot — cập nhật 2026-10-24 (Asia/Saigon)

| Nhóm | Trạng thái | Hành động |
|---|---|---|
| Phase 0–2 và T2-SQL-1/2/3 | Hoàn tất; T2.5 superseded | Đóng, không đầu tư thêm Plan A |
| T3.1–T3.2 | Hoàn tất | Giữ immutable làm nguồn Stage A |
| Stage A v2 | Accepted: 1.000 records, 25 intents, genuine live evidence | Giữ source/manifest immutable |
| T3.3 | Canonical published tại `2b652a3`: 8.000 records, 4.000 EN + 4.000 VI, 1.000 families; 7.208 train / 792 development | Hoàn tất; hai build byte-identical, validators pass; giữ failed audit + r1 |
| T3.4 | Superseded | Không sinh noise dataset riêng |
| T3.5 | English và Vietnamese finalized; VI có 100 user ACCEPT events, điểm 5/5/5/1 | Giữ snapshots immutable; VI reuse exact English live evidence, zero new BigQuery jobs |
| T4.1–T4.3 | Hoàn tất development evaluation | Giữ snapshot/hash immutable; không claim independent holdout |
| T5.1/B0 | Genuine English negative result hoàn tất (`0/100`) | Giữ làm English lower bound; không tự dùng làm Vietnamese control, không tune trên test set |
| T3.3 → B2 | Offline integration hoàn tất tại `9adf02c`; lossless train export 7.208 rows, exact fingerprint | Giữ development ngoài retrieval; bundle pinned source files cho Kaggle |
| T5.2/B1–B2 | Generation hoàn tất: 12/12 genuine native runs, B1/B2 × EN/VI × 3, N=100/run/language; B2 EN r03 dùng replacement02 | Giữ 14 attempted IDs gồm hai setup failures; không cần thêm generation. Native scientific blockers và latency gate fail giữ nguyên |
| B1/B2 Vietnamese consumer | Typed finalized paired consumer + CLI17/CLI25 EN/VI hoàn tất; toàn bộ VI r01/r02/r03 verified | Giữ nguồn/hash/paired lineage và exact reused English gold evidence; không coi là execution evidence mới |
| T5.4-A / offline adaptation | Framework hoàn tất; 12 canonical runs và 1.200 case traces đã xuất/validate, đối chiếu static hoàn tất tại `1f2f9da` | Giữ artifacts immutable; exact/structural match và agreement không thay execution accuracy |
| T5.4-B | Privacy/survey đã duyệt; 4 sidecars + 12 privacy-bound runs; đủ 143 SQL: 140 estimates, 3 compile errors; không live | Review errors/live feasibility → verified free allowance và giải quyết cap/calendar/protocol → duyệt live riêng → evidence/reports/comparison |
| T5.5 | Giữ B3 QLoRA là hướng chính cho RQ1; chưa chốt cấu hình/lịch | Chốt kế hoạch khả thi từ evidence B1/B2 và tài nguyên; scope-down vẫn giữ fine-tuning, bỏ B3 cần quyết định riêng của người dùng |
| Phase 6–7 | Ticket cũ còn SPARQL | Redesign sang NL2SQL trước khi implement |

## Thứ tự thực hiện

### P0 — Mở gate dữ liệu

1. **Stage A v2 + T3.3 — hoàn tất.** Stage A accepted với genuine live
   evidence; corpus canonical 8.000 records đã publish tại `2b652a3`, 7.208 train /
   792 development, không family cross split. Hai build byte-identical, staged
   và canonical validators pass. Không chạy lại historical absent-canonical gates.
2. **T3.3 → B2 data integration — hoàn tất offline (2026-10-16).** Export
   `data/dataset/processed/b2-training.jsonl` giữ nguyên 7.208 train lines, có
   manifest/hash riêng, bind canonical và accepted Stage A/catalogue/exclusion.
   B2 consume export bằng exact accepted-training fingerprint; không đổi semantics
   `style`, không thêm fixture acceptance flag. [Evidence](../research/b2-training-integration-2026-10-16.md).
3. **Vietnamese T3.5 — finalized (2026-10-16).** User xác nhận ACCEPT cả 100
   candidates với naturalness/SQL faithfulness/terminology/ambiguity = 5/5/5/1.
   Đã append 100 events vào log gốc; giữ candidate bytes/IDs/SQL. Final JSONL,
   manifest và exact reused English live evidence đã publish offline, validate pass,
   zero new BigQuery jobs. [Evidence](../research/t35-vi-finalization-2026-10-16.md).
   Review pack là snapshot chuẩn bị trước review; các ghi nhận 0 events trong
   evidence lịch sử giữ nguyên. Không review lại English hoặc tune trên benchmark.

### P1 — Baseline small LLM và quyết định scope

4. **B1/B2 genuine generation — hoàn tất (2026-10-23).** Đủ ba compatible
   runs cho mỗi (baseline, language), tổng 12 runs, N=100/run/language.
   B2 EN r03 dùng replacement02; hai setup failures giữ riêng, tổng 14 attempted
   IDs. Native outputs/runtime/source hashes đã verified; không lên lịch thêm
   replicate hoặc retry. Extraction OK/run: B1 EN/VI 0/100, B2 EN 31/100,
   B2 VI 12/100; không phải execution accuracy. Native scientific blockers và
   latency gate fail giữ nguyên.
   [Ma trận và per-run evidence](../research/kaggle-b12-generation-matrix-2026-10-23.md).
5. **T5.4 comparison vòng 1 — đang mở.** Framework và offline adaptation đã
   hoàn tất: 12 canonical runs, 1.200 case traces, static SQL checks và
   exact/structural match riêng từng run. Scientific completion chưa đạt.
   [Offline evidence và handoff](../research/t54-offline-2026-10-24.md).
   - [Giai đoạn A sau duyệt](../research/t54-phase-a-2026-10-24.md): privacy
     đã ghi nhận, 4 sidecars và 12 privacy-bound runs mới hợp lệ. Billing vẫn
     tắt; paid spend 0 USD. Đủ 143 SQL đã khảo sát: 140 estimates và ba compile
     errors, giữ nguyên SQL/lỗi. Một prediction vượt cap 24 GiB. Daily limits đã
     đọc được, monthly free balance chưa biết; chưa có quyền live.
     [Kết quả đầy đủ](../research/t54-phase-a-final-2026-10-24.md).
   - Sau khi đủ estimates/quota và được duyệt live gold/predicted scope riêng
     theo cấu hình cuối: chạy nối tiếp với reservation ledger, giữ genuine
     execution evidence và sealed journals; không tự retry hoặc tăng cap.
   - Tạo bốn reports B1/B2 × EN/VI, primary r01 và r02/r03 làm replicates;
     compare B1–B2 riêng từng language, N=100. Báo execution accuracy,
     exact/structural match, answer metrics, latency, cost, reproducibility,
     breakdowns và failure analysis. Kiểm tra đơn vị resampling trước khi công
     bố CI reproducibility; ba replicates không phải ba mẫu câu hỏi độc lập.
   - Chỉ thêm B0 English nếu snapshot/policy/evidence tương thích đã được kiểm
     tra; không suy ra Vietnamese B0. Execution/answer metrics hiện vẫn null.
6. **T5.5 — chốt cấu hình/kế hoạch B3 QLoRA khả thi sau T5.4-B.** Giữ
   fine-tuning làm hướng chính để trả lời RQ1. Dùng genuine B1/B2 metrics, linker
   deltas và bằng chứng calendar/GPU/memory để chọn full B3 hoặc scope-down vẫn
   train QLoRA; chỉ giảm sweep/phần không thiết yếu khi có bằng chứng thiếu tài
   nguyên. B1/B2 yếu hoặc quota BigQuery không tự chứng minh nên bỏ B3. Bỏ
   fine-tuning cần quyết định riêng của người dùng. Ghi kế hoạch tại
   `docs/pivot-decision-2.md`, đồng bộ Phase 6–7 và RQ/contribution claims.
   Có thể rà tài nguyên/chuẩn bị offline trong lúc chờ; chưa mở training B3.

### P2 — Hệ thống đề xuất

7. **T6.1-SQL — B3 QLoRA** theo cấu hình/kế hoạch T5.5; target là GoogleSQL từ
   accepted deterministic bilingual artifact. Fine-tuning vẫn là mục tiêu chính.
8. **T6.2-SQL — Constrained generation.** Grammar/safety target GoogleSQL; đo
   syntax/safety rate, execution accuracy và latency overhead.
9. **T6.3-SQL — Ablation.** Ưu tiên `no_schema`, `no_entity`, `no_class` và
   `no_constraint`; báo CI 95% và paired significance trên cùng test snapshot.
10. **T5.4 comparison cuối.** Tổng hợp B0–B3 và failure analysis từ genuine
    evidence; không tự thay B3 bằng B2 + linkers + validator. Mọi thay đổi bỏ
    fine-tuning cần quyết định riêng và cập nhật RQ/contribution claims.

### P3 — Demo và luận văn

11. **T7.1-SQL — Validator/recovery.** SQLGlot, managed-relation allowlist,
    BigQuery dry-run, byte cap, tối đa một retry và đầy đủ provenance.
12. **T7.3-SQL — Local Gradio demo.** Chạy small model; hiển thị linking trace,
    GoogleSQL, dry-run estimate, result, latency và failure trace.
13. **T7.2-SQL — Case studies.** Chạy trên analytical layer và ghi rõ giới hạn
    label coverage, không suy diễn AML attribution vượt evidence.
14. **T7.4-SQL — HF Spaces optional.** Chỉ deploy nếu small model chạy được trong
    resource budget hoặc có demo tĩnh trung thực; không thay model bằng API.
15. **T7.5 — Thesis/slides/rehearsal.** Khóa figures sau ablation và case studies.

## Luồng song song

- **Lane A — Evidence:** Stage A/T3.3/data integration và Vietnamese review/
  finalization đã xong; giữ các snapshots/hash immutable.
- **Lane B — Evaluation:** generation B1/B2 và T5.4 offline đã xong; privacy
  đã duyệt và đủ 143 SQL đã khảo sát, giữ ba compile errors. Chờ quota/cap/
  calendar/protocol cho phương án free-only; live T5.4-B vẫn chưa duyệt. Giữ latency/native scientific blockers; chưa mở
  thêm GPU generation hoặc B3 training.
- **Lane C — Writing:** cập nhật RQ/contributions sang small-LLM-only, viết Plan A
  negative finding, methodology và kết quả generation/static đã có evidence;
  execution/answer metrics chưa chạy giữ null, chưa kết luận B3.

WIP limit: một task implementation lớn và một external-evidence task đang active.

## Loại khỏi scope

- Mọi hosted/remote LLM baseline và dependency provider.
- Full T2.5 pySHACL, tối ưu Fuseki/KG, RML/ontology extension không phục vụ luận văn.
- Stage D noise injection riêng; deterministic bilingual styles là nguồn training.
- Deploy thay model nghiên cứu bằng một model ngoài phạm vi.
- Fixture/synthetic backend dùng để tick scientific acceptance.

## Definition of done

- **Implementation complete:** test, lint, CLI/help và artifact integrity pass.
- **Scientific complete:** input độc lập được review, genuine run hoàn tất, report
  hash-bound có metrics/latency/cost/privacy/reproducibility và không còn blocker.
- **Superseded/out of scope:** không xuất hiện trong active backlog hoặc acceptance;
  lịch sử thay đổi được truy xuất qua Git.

## Công việc kế tiếp

**Ưu tiên hiện tại: chốt tính khả thi live free-only của T5.4-B.** Privacy đã
duyệt, bốn sidecars và 12 privacy-bound runs mới hợp lệ. Đã khảo sát đủ 143 SQL:
140 estimates, ba compile errors và một prediction vượt cap. Không sửa SQL
hoặc chạy live; chưa có monthly free balance hoặc calendar khả thi.

1. Review [kết quả/diagnosis](../research/t54-phase-a-final-2026-10-24.md) và
   [live feasibility](t54-phase-b-feasibility-2026-10-24.md). Known scan components
   khoảng 6,968 TiB; chỉ reuse gold theo số học vẫn trên 1 TiB. Không tự đổi
   protocol, sửa evaluator, tăng cap hoặc lặp dry-runs đã hết scope.
2. Xác minh số dư miễn phí tháng và chốt calendar/expiry cùng cách xử lý live
   guards. Nếu cần đổi protocol/reuse/materialize phải có đề xuất riêng; quota
   API daily limits không phải số dư miễn phí tháng.
3. Chốt reservation/expiry/data drift và xin duyệt live riêng; genuine sealed
   evidence → reports/comparison riêng EN/VI → failure analysis → T5.5 B3 QLoRA.

### Trình tự lúc chuẩn bị gói — đã có checkpoint mới ở trên

1. Reviewer duyệt [privacy policy](t54-bigquery-privacy-policy-2026-10-24.md)
   và [scope 143 dry-runs](t54-bigquery-approval-2026-10-24.md). Bốn worksheets
   có provider/policy hash nhưng chưa ký. Giai đoạn này không có live query.
2. Sau duyệt: dry-run exact SQL để lấy current scan estimates, kiểm tra compile/
   quyền và ghi errors nguyên trạng. Project `nl2sparql-thesis`, dataset US và
   billing tắt đã kiểm chứng qua metadata; chưa xác minh hết public view dependencies.
3. Đối chiếu quota miễn phí hiện tại. Sandbox có 1 TiB/tháng; historical usage
   không phải số dư quota. Giữ billing tắt, paid spend 0 USD; không có phương án
   tự nâng cấp trả phí. 9 TiB/60 USD cũ đã được archive, không còn active.
4. Khi đủ quota cho complete run, chốt free-byte reservation và xin duyệt live
   riêng với canonical đã bind privacy/hash mới. CLI19 chỉ guard theo run,
   chưa có monthly free-tier ledger tự động. Protocol vẫn tối đa 1.200 gold +
   129 predicted live queries, không reuse gold cross-run; có thể cần chia đợt,
   phải kiểm tra source expiry/data drift trước khi chốt lịch.
5. Genuine evidence + sealed journals → bốn reports → comparison B1–B2 riêng
   EN/VI và failure analysis → T5.5 chốt cấu hình/kế hoạch B3 QLoRA khả thi.

Nguồn hiện tại: [ma trận generation](../research/kaggle-b12-generation-matrix-2026-10-23.md),
[T5.4 offline và execution handoff](../research/t54-offline-2026-10-24.md),
[gói duyệt free-only](t54-bigquery-approval-2026-10-24.md),
[proposal lúc chuẩn bị](../../configs/t54/b12-bigquery-review-proposal.json),
[privacy worksheets gốc](../../configs/t54/privacy-review-drafts.json) và
[checkpoint survey đầy đủ](../research/t54-phase-a-final-2026-10-24.md).
Đồng bộ backlog không cấp quyền BigQuery hoặc thay đổi scientific readiness.

[Rà local mới ngày 2026-10-24](../research/t54-local-review-2026-10-24.md):
hash/mapping và tái tạo offline khớp; reservation 768 GiB/run còn vướng lịch
miễn phí và source expiry. Đây là checkpoint trước phê duyệt; trạng thái mới
nằm tại kết quả giai đoạn A ở trên.

## Historical local-preparation checkpoint — 2026-10-17

> Toàn bộ checkpoint từ đây là lịch sử tại thời điểm ghi, giữ để truy xuất
> quyết định và failures. Trạng thái hiện tại nằm ở Snapshot và Công việc kế tiếp
> phía trên; không dùng chỉ dẫn pending/launch cũ làm gate hiện tại.

[Setup handoff](kaggle-environment-cache-2026-10-17.md): exact model/encoder
revisions pinned from anonymous public metadata; genuine MiniLM cache bytes
verified locally, no encoder/model load. Separate CPU setup notebook, locked
runtime requirements and portable cache/setup artifacts prepared. User has not
yet requested Llama access. Existing Kaggle notebook supplied by user; its actual
contents/runtime/quota remain unverified. No upload/session execution or genuine
inference occurred. Environment/cache on Kaggle is still pending, followed by
non-test GPU smoke, genuine B1/B2, T5.4 and T5.5. No baseline or benchmark change.

### 2026-10-17 — genuine Kaggle cache checkpoint

Private `aohkvd/nl2sql-environment-cache` version 5 completed on CPU. All 24
pinned Llama/MiniLM files (16.16 GB) passed content hashes twice and are saved in
private output. The full Python 3.11.15 environment installed successfully in
separate runs; provision it separately from the mounted read-only cache for
smoke. GPU smoke and genuine B1/B2 inference have not run.
[Handoff and preserved failures](../research/kaggle-cache-acquisition-2026-10-17.md);
[machine evidence](../evidence/kaggle-cache-acquisition-2026-10-17.json).

### 2026-10-17 — T4 smoke submitted

Private `aohkvd/nl2sql-b12-t4-smoke-20261017-r01` version 1 was submitted
with the verified cache mounted read-only, unchanged pinned environment and
research configuration. The latest saved checkpoint is `QUEUED`: actual T4,
model loading, OOM/latency and inference are not yet verified. Five fixed
train-only questions are planned for both B1/B2; 300s per process, 1,800s
smoke and 2,700s session caps. Continue monitoring this run before launching
any genuine benchmark campaign. [Smoke handoff](../research/kaggle-t4-smoke-2026-10-17.md).

### 2026-10-18 — smoke archive guard corrected

Version 1 genuinely failed before installation/model load: its notebook expected
181 archive members instead of 181 payload files plus the bundle manifest (182).
Version 2 changes only this count. Local regression reproduced the original error,
then passed real extraction and native EN/VI data preflight with the unchanged
accepted bundle. Version 2 is `RUNNING` at the latest checkpoint; model load,
OOM/latency and genuine benchmark acceptance remain open.

### 2026-10-18 — genuine non-test T4 smoke completed

Version 2 COMPLETE; 10/10 genuine CLI17 processes, Tesla T4 ×2, original
BF16/4-bit, no OOM. Generation medians: B1 20.95s, B2 20.01s. B1 extraction:
5 unsafe_sql; B2: 5 ok, without correctness evaluation. Compatibility smoke
passed; latency acceptance and 12 benchmark processes remain open. Post-run
quota snapshot: 29.76h GPU remaining; recheck before use. No new BigQuery job.

### 2026-10-18 — benchmark campaign prepared offline

[Campaign and operational controls](kaggle-b12-benchmark-campaign-2026-10-18.md):
notebook 16 is disabled by default, reuses smoke-v2 setup and cache v5 read-only,
and schedules one full 100-case native process per selected session. Full matrix:
B1/B2 × EN/VI × 3 = 12 processes; N=100 per language. Proposed 90m/process,
120m/session, 24 GPU-session-hours plus 3h contingency; fresh quota, charge unit,
IDs and execution authorization remain unresolved. First genuine process remains
full N=100; only runtime/artifact completeness guides continuation. No upload,
GPU inference, new Kaggle session or BigQuery job in this preparation turn.
T5.4 canonical adaptation/privacy/cost and separate BigQuery budget remain pending.
B0 0/100 is English only; no Vietnamese control is inferred.

### 2026-10-18 — first full B1 EN process authorized and submitted

User authorized only B1 EN r01, all 100 cases, 90m native / 120m session after
fresh quota check (29.76275h available, no reserved quota, pay-to-scale off).
Private notebook v1 is RUNNING; actual inference/hardware/completeness are not yet
verified. No remaining campaign process is authorized by this launch. Preserve
all results; no tuning/retry based on SQL validity or accuracy.
[Live-run checkpoint](../research/kaggle-b12-benchmark-first-run-2026-10-18.md).

### 2026-10-18 — first full B1 EN process complete and verified

Private v1 COMPLETE; 100/100 genuine completions, N=100 EN, Tesla T4 ×2,
original BF16/4-bit, Python 3.11.15 / torch 2.5.1+cu124. All 22 saved files
retained; 21 driver-manifest entries plus report/source/identity checks pass.
Native 47.00m; driver 56.11m; platform observed COMPLETE about 65m after submit.
B1 extraction: 99 unsafe_sql, 1 invalid_sql, zero ok; no repair/retry. P50
25.457s / P95 49.107s fails unchanged latency gate. Native review/live aggregate
flags also remain blocked; audit confirms all loader cases carry trusted human/live
authority. No flags/reports/semantics were changed.

Settled quota remaining 28.82212h, observed account delta 0.94063h. Exactly one
process executed; remaining 11 have not started. Runtime/artifact completeness
review passes; scientific completion, T5.4 canonical/privacy/cost and separate
BigQuery work remain pending.
[Result and audit](../research/kaggle-b12-benchmark-first-run-2026-10-18.md).

### 2026-10-18 — next scheduled B1 VI r01 submitted after continuation

User said continue after EN r01 completion. EN result/evidence committed at
`3b93dd1`; its runtime/artifact review passes. Fresh quota 28.82212h, no reserved
quota, pay-to-scale off. At the submission checkpoint, private B1 VI r01 v1 was RUNNING from 21:52, full N=100,
same 90m native / 120m session caps and unchanged research/flags. Prior EN
attempt carried in cumulative ledger. This is a single-process continuation;
whole remaining-campaign budget is not inferred. No new BigQuery execution or
Vietnamese B0 control is implied.
[VI checkpoint](../research/kaggle-b12-benchmark-b1-vi-r01-2026-10-18.md).

### 2026-10-19 — B1 VI r01 saved outputs verified

Existing private v1 is COMPLETE. All 22 saved files retained; 21 driver-manifest
hashes plus native report self-digest pass. Verified all 100 genuine completions,
original Vietnamese questions/typed paired lineage, pinned model/environment,
T4 ×2 hardware, cache/data gates, single-session run and cumulative EN/VI ledger.
Native process 37.17m, driver 46.11m. VI N=100: 100 unsafe_sql, 0 extraction ok,
P50 20.461s, P95 30.376s. Scientific gates remain blocked; no SQL execution
accuracy, new BigQuery, repair, retry or research change is claimed.
Quota remaining on return 28.046782h; observed account delta 0.775337h.
Campaign 2/12 native processes complete, EN and VI denominators separate;
10 unstarted, next planned B2 EN r01. No new session launched during resumption.
[Verified VI result](../research/kaggle-b12-benchmark-b1-vi-r01-2026-10-18.md).

### 2026-10-19 — B2 EN r01 submitted after explicit continuation

User said “OKe tiếp tục triển khai đi” after verified VI results. Submitted only
next scheduled B2 EN r01, N=100, private v1 at 19:08:56 Asia/Saigon, unchanged
90m native / 120m session caps. Fresh quota 28.046782h, 0 reserved, pay-to-scale
off; private cache v5 and both previous sessions COMPLETE. Remote source/private
GPU metadata verified; platform RUNNING at 19:09:28, actual inference/runtime
still unverified. Training-only 7,208-row retrieval, model/settings/flags and
scientific gates unchanged. Cumulative prior ledger contains EN and VI B1 r01.
No automatic retries, BigQuery, canonical adaptation or whole-campaign approval.
Two processes verified complete, one submitted/running, nine unstarted.
[B2 EN checkpoint](../research/kaggle-b12-benchmark-b2-en-r01-2026-10-19.md).

### 2026-10-19 — B2 EN r01 COMPLETE and independently verified

Existing private v1 COMPLETE. All 25 saved files retained, 24 native manifest
hashes/report self-digest pass, 100 genuine completions verified. Train-only
retrieval cache 7,208 × 384 and all 500 selected training examples verified.
B2 EN N=100: 31 extraction ok, 60 prose, 8 unsafe_sql, 1 invalid_sql;
P50 33.696s, P95 52.987s. Native wall 61.70m, driver 68.31m. Native scientific
blockers unchanged; this is not SQL execution accuracy. No BigQuery, adaptation,
repair/retry or new session launched. Quota remaining 26.902697h. Campaign 3/12
native processes complete, nine unstarted; next planned B2 VI r01.
[Verified B2 EN result](../research/kaggle-b12-benchmark-b2-en-r01-2026-10-19.md).

### 2026-10-19 — B2 VI r01 explicitly authorized and submitted

User said “oke khởi chạy đi” for B2 VI r01. Private v1 submitted at 22:13:49
Asia/Saigon; platform QUEUED at 22:14:06. Full N=100, unchanged 90m native /
120m session caps and research settings. Quota 26.902697h, no reserved quota,
pay-to-scale off; private cache v5 and three prior sessions COMPLETE. Remote
cells/private GPU/source metadata verified; actual inference/runtime/hardware
remain unverified. Prior ledger matches B1 EN, B1 VI, B2 EN r01. Three native
processes verified complete, fourth submitted, eight unstarted. No new BigQuery,
retry or whole-campaign authorization inferred.
[B2 VI checkpoint](../research/kaggle-b12-benchmark-b2-vi-r01-2026-10-19.md).

### 2026-10-20 — B2 VI r01 COMPLETE and independently verified

Existing private v1 COMPLETE; all 25 saved files retained, 24 native manifest
entries and report self-digest pass. Verified 100 genuine VI completions,
original question/paired lineage and reused English evidence, train-only
7,208 × 384 retrieval cache and 500 selected examples, T4 ×2 runtime and exact
four-attempt ledger. VI N=100: 12 extraction ok, 88 prose; P50 30.977s,
P95 73.590s. Native wall 62.47m, driver 66.49m. Scientific blockers unchanged;
no execution accuracy, new BigQuery, adaptation, SQL repair/retry or new session.
Quota remaining 25.789862h. Campaign 4/12 complete (all r01); eight unstarted,
next B1 EN r02. EN/VI denominators remain separate.
[Verified B2 VI result](../research/kaggle-b12-benchmark-b2-vi-r01-2026-10-19.md).

### 2026-10-20 — B1 EN r02 explicitly authorized and submitted

User said “oke khởi chạy đi” for next scheduled B1 EN r02. Private v1 submitted
at 19:58:01 Asia/Saigon; RUNNING at 19:58:17. N=100, same 90m native / 120m
session caps; unchanged model/seed/greedy/prompts/flags and scientific gates.
This is the planned r02 replicate, not a repair or replacement of r01.
Quota before launch 25.789862h, 0 reserved, pay-to-scale off; four prior sessions
and cache v5 COMPLETE. Exact prior four-attempt ledger carried. Remote source
and private GPU metadata match; actual native inference/hardware still unverified.
Four verified processes, fifth running, seven unstarted. No new BigQuery,
adaptation, tuning or full-campaign budget inferred.
[B1 EN r02 checkpoint](../research/kaggle-b12-benchmark-b1-en-r02-2026-10-20.md).

### 2026-10-20 — B1 EN r02 COMPLETE and independently verified

Existing private v1 COMPLETE. All 22 saved files retained, 21 native manifest
hashes and report self-digest pass. Verified 100 genuine EN completions,
zero-shot B1/source authority, unchanged settings, actual T4 ×2 runtime and
exact five-attempt ledger. N=100: 99 unsafe_sql, 1 invalid_sql, 0 extraction ok;
P50 25.522s, P95 48.809s. Native wall 47.95m, driver 52.62m. Native blockers
unchanged; no execution accuracy, BigQuery, adaptation, repair/retry or new
session. Quota remaining 24.906806h. Campaign 5/12 complete, seven unstarted;
next B1 VI r02 not launched. r01/r02 preserved separately.
[Verified B1 EN r02](../research/kaggle-b12-benchmark-b1-en-r02-2026-10-20.md).

### 2026-10-20 — B1 VI r02 authorized and submitted

User said “tiếp” after verified B1 EN r02 and next B1 VI r02 was named.
Private v1 submitted at 21:03:51 Asia/Saigon; QUEUED at 21:04:08. N=100,
unchanged 90m native / 120m session caps and research settings. Quota before
launch 24.906806h, 0 reserved, pay-to-scale off; five prior sessions and cache
v5 COMPLETE. Exact five prior IDs carried; remote source/private GPU metadata
verified, actual native inference/hardware still unverified. Five processes
complete, sixth submitted, six unstarted. No tuning/repair, new BigQuery,
adaptation or full-campaign budget inferred.
[B1 VI r02 checkpoint](../research/kaggle-b12-benchmark-b1-vi-r02-2026-10-20.md).

### 2026-10-20 — B1 VI r02 COMPLETE and verified; next process authorized

User requested result check and launching the next single process. B1 VI r02
v1 COMPLETE: 22 saved files retained, 21 native manifest hashes/report digest
pass; all 100 genuine VI completions, original paired lineage/reused English
evidence, zero-shot settings, T4 ×2 runtime and six-attempt ledger verified.
N=100: 100 unsafe_sql, 0 extraction ok; P95 29.532s. Native 35.86m, driver
44.37m. Quota remaining 24.161284h. Scientific blockers unchanged, no execution
accuracy/BigQuery/adaptation/repair claimed. Campaign 6/12 complete at review;
next B2 EN r02 explicitly authorized, subject to fresh launch preflight.
[Verified B1 VI r02](../research/kaggle-b12-benchmark-b1-vi-r02-2026-10-20.md).

### 2026-10-20 — B2 EN r02 submitted after authorized result review

After B1 VI r02 artifact/runtime review passed at `2a24069`, launched the next
single process explicitly requested by the user. B2 EN r02 private v1 submitted
at 23:08:04 Asia/Saigon; RUNNING at 23:08:19. N=100, unchanged 90m native /
120m session caps, model/retrieval/flags/thresholds. Quota before launch
24.161284h, 0 reserved, pay-to-scale off; six prior notebooks and cache v5
COMPLETE. Exact six prior IDs carried. Remote source/private GPU metadata
verified; actual native inference/hardware still unverified. Six complete,
seventh running, five unstarted. No new BigQuery, tuning, repair/retry or
whole-campaign budget inferred.
[B2 EN r02 checkpoint](../research/kaggle-b12-benchmark-b2-en-r02-2026-10-20.md).

### 2026-10-21 — B2 EN r02 COMPLETE; next B2 VI r02 authorized

Private v1 COMPLETE, 25 saved files/24 native manifest hashes/report digest
verified. All 100 genuine EN completions, original source authority, 7,208-row
cache and 500 training selections, T4 ×2 runtime and seven-attempt ledger pass.
N=100: 31 extraction ok, 60 prose, 8 unsafe_sql, 1 invalid_sql; P95 51.300s.
Native 59.18m, driver 63.73m; quota remaining 23.094586h. Scientific blockers
unchanged; no execution accuracy, new BigQuery, adaptation or repair claimed.
Campaign 7/12 complete at review; user explicitly requested next B2 VI r02,
subject to fresh launch preflight. No full-campaign budget inferred.
[Verified B2 EN r02](../research/kaggle-b12-benchmark-b2-en-r02-2026-10-20.md).

### 2026-10-21 — B2 VI r02 authorized and submitted

After B2 EN r02 completeness review passed at `50e1a70`, launched explicitly
requested next B2 VI r02 private v1. Submitted at 19:10:52 Asia/Saigon;
RUNNING at 19:11:08. N=100, unchanged 90m native / 120m session caps and all
research settings. Quota before launch 23.094586h, 0 reserved, pay-to-scale off;
seven prior sessions and cache v5 COMPLETE. Exact seven prior IDs carried.
Remote source/private GPU metadata verified; actual inference/hardware still
unverified. Seven complete, eighth running, four unstarted. No new BigQuery,
tuning, repair/retry, adaptation or full-campaign budget inferred.
[B2 VI r02 checkpoint](../research/kaggle-b12-benchmark-b2-vi-r02-2026-10-21.md).

### 2026-10-21 — B2 VI r02 COMPLETE; next B1 EN r03 authorized

Private v1 COMPLETE; 25 saved files/24 native manifest hashes/report digest
verified. All 100 genuine VI completions, original paired lineage/reused English
evidence, 7,208-row cache and 500 training selections, T4 ×2 runtime and exact
eight-attempt ledger pass. N=100: 12 extraction ok, 88 prose; P95 72.962s.
Native 61.93m, driver 66.60m. Quota remaining 21.979519h. Scientific blockers
unchanged; no execution accuracy, new BigQuery, repair/adaptation claimed.
Campaign 8/12 complete at review, all r01/r02 combinations; user authorized
next B1 EN r03 after fresh launch preflight, no full-campaign budget inferred.
[Verified B2 VI r02](../research/kaggle-b12-benchmark-b2-vi-r02-2026-10-21.md).

### 2026-10-21 — B1 EN r03 authorized and submitted

After B2 VI r02 review passed at `b8147e6`, launched explicitly requested next
scheduled B1 EN r03 private v1, N=100. Submitted 20:33:40 Asia/Saigon;
QUEUED 20:33:58. Unchanged 90m native / 120m session caps and research settings.
Quota before launch 21.979519h, 0 reserved, pay-to-scale off; eight prior
sessions and cache v5 COMPLETE. Exact eight prior IDs carried. Remote
source/private GPU metadata match; actual inference/hardware unverified.
Eight complete, ninth submitted, three unstarted. No BigQuery, tuning,
repair/retry, adaptation or whole-campaign budget inferred.
[B1 EN r03 checkpoint](../research/kaggle-b12-benchmark-b1-en-r03-2026-10-21.md).

### 2026-10-21 — B1 EN r03 COMPLETE; next B1 VI r03 authorized

Private v1 COMPLETE; all 22 saved files/21 native manifest hashes/report digest
pass. Verified all 100 genuine EN completions/source authority, zero-shot
settings, T4 ×2 runtime and exact nine-attempt ledger. N=100: 99 unsafe_sql,
1 invalid_sql, 0 extraction ok; P95 45.922s. Native 43.47m, driver 47.41m.
Quota remaining 21.184038h. Scientific blockers retained; no execution accuracy,
new BigQuery, repair/adaptation. Campaign 9/12 complete at review; user explicitly
authorized next B1 VI r03 after fresh launch preflight.
[Verified B1 EN r03](../research/kaggle-b12-benchmark-b1-en-r03-2026-10-21.md).

### 2026-10-21 — B1 VI r03 authorized and submitted

After B1 EN r03 review passed at `6c19205`, launched next explicitly requested
B1 VI r03 private v1, N=100. Submitted 22:17:02 Asia/Saigon; QUEUED 22:17:20.
Unchanged 90m native / 120m session caps and research settings. Quota before
launch 21.184038h, 0 reserved, pay-to-scale off; nine prior sessions and cache
v5 COMPLETE. Exact nine prior IDs carried. Remote source/private GPU metadata
match; actual inference/hardware unverified. Nine complete, tenth submitted,
two unstarted. No BigQuery, tuning, repair/retry, adaptation or whole-campaign
budget inferred.
[B1 VI r03 checkpoint](../research/kaggle-b12-benchmark-b1-vi-r03-2026-10-21.md).

### 2026-10-21 — B1 VI r03 COMPLETE; next B2 EN r03 authorized

Private v1 COMPLETE; all 22 saved files/21 native manifest hashes/report digest
pass. Verified all 100 genuine VI completions/full paired lineage/reused English
evidence, zero-shot settings, T4 ×2 runtime and exact ten-attempt ledger.
100 unsafe_sql, 0 extraction ok; P95 31.101s, native 36.38m, driver 49.50m.
Quota remaining 20.353947h. Scientific blockers retained; no execution accuracy,
new BigQuery/repair/adaptation. Campaign 10/12 complete at review, all B1 runs
verified. User authorized next B2 EN r03 after fresh launch preflight.
[Verified B1 VI r03](../research/kaggle-b12-benchmark-b1-vi-r03-2026-10-21.md).

### 2026-10-21 — B2 EN r03 authorized and submitted

After B1 VI r03 review passed at `84b0f2a`, launched next explicitly requested
B2 EN r03 private v1, N=100. Submitted 23:26:48 Asia/Saigon; QUEUED 23:27:06.
Unchanged 90m native / 120m session caps and research settings. Quota before
launch 20.353947h, 0 reserved, pay-to-scale off; ten prior sessions and cache v5
COMPLETE. Exact ten prior IDs carried. Remote source/private GPU metadata match;
actual inference/hardware unverified. Ten complete, eleventh submitted, final
B2 VI r03 unstarted. No BigQuery, tuning, repair/retry, adaptation or
whole-campaign budget inferred.
[B2 EN r03 checkpoint](../research/kaggle-b12-benchmark-b2-en-r03-2026-10-21.md).

### 2026-10-22 — B2 EN r03 setup timeout; failure retained, continuation pending

Private v1 ERROR; all seven saved files/6 native manifest hashes verified.
Cumulative setup cap 1,200s exhausted while verifying mounted cache; full
locked install completed, then verification timed out after remaining 615.233s.
No mismatch/success receipt; underlying slowness unknown, corruption not proven.
Native runner never started: zero generated cases and no native ledger/report.
Scratch removed. This is not a completed/0%-accuracy EN replicate.
Quota remaining 20.015843h; observed account delta 0.338104h.
Campaign 10 complete native processes, one setup failure, final VI slot unstarted.
Failure-stop/completeness protocol prevents automatic continuation. Prepared
unchanged B2 VI r03 proposal with all opt-ins/receipt flag false and conservative
eleven-ID audit; asked user to approve explicit continuation preserving EN failure
without retry, or stop for setup diagnosis. No new session submitted or cap changed.
[Failure audit and proposal](../research/kaggle-b12-benchmark-b2-en-r03-2026-10-21.md).

### 2026-10-22 — user stops continuation to address setup

User selected setup repair first; disabled final-VI proposal not approved.
Offline comparison of ten successes/one failure confirms setup watchdog expiry:
failed package prep 7m46s vs prior 56.01s–3m49s, leaving 615.233s for cache
verification. Underlying cache slowness/corruption not established. No new
remote session or runtime change. Bounded candidate: 27m setup + unchanged
91m maximum worker + 2m cleanup = original 120m session cap, native cap 90m;
add persistent per-stage elapsed/budget/timeout telemetry. Requires short-design
approval before implementation; no fix or remote validation claimed.
[Diagnosis](../research/kaggle-b12-setup-diagnosis-2026-10-22.md).

### 2026-10-22 — approved setup repair implemented offline

User approved 20m→27m setup allowance and per-stage timing. Operational driver,
embedded disabled notebook 16 and campaign config/docs updated. Native 90m and
session 120m unchanged: setup 27m + worker max91m + cleanup2m =120m. Original
cache-byte/hash checks, accepted bundle/setup pins and research functions
unchanged; old failed session and IDs preserved. TDD: three new regressions
failed before implementation, then passed; focused19 passed, full1,593 passed
with342 warnings in788.72s. Lint/format/notebook/static checks pass.
No new Kaggle/inference/BigQuery session; real mounted-cache validation pending.
Campaign remains10 complete, one setup failure, final VI unstarted. No EN
replacement or final VI continuation authorized by this offline repair.
[Repair handoff](../research/kaggle-b12-setup-repair-2026-10-22.md).

### 2026-10-22 — real setup validation passed; final B2 VI r03 launched

Setup-only private v1 COMPLETE:15 saved files/14 manifest entries verified,
24 pinned cache files/data/package/runtime/timing gates pass, zero inference
and no benchmark ID reserved. Setup13.27m, driver13.56m, cache11.71m; actual
hardware not probed. Successful session fit old20m too; no guarantee original
transient slowdown cured. Evidence commit `b94a0f8`.
User explicitly authorized continuation after validation and renewed execution.
Final B2 VI r03 private v1 N=100 submitted22:37:51 Asia/Saigon, RUNNING22:38:09.
Fresh quota19.783096h, 0 reserved/pay-to-scale off; repaired setup27m,
native90m/session120m. Eleven IDs carried conservatively including failed EN;
review flag acknowledges explicit failure exception, not a successful EN receipt.
Remote source/private GPU metadata match; native hardware/completeness pending.
Campaign10 complete native processes +1 failed setup +final VI running. If final
VI completes:11 native successes/1 setup failure, not12 complete replicates.
No EN retry/replacement, tuning, new BigQuery or scientific completion claim.
[Final VI checkpoint](../research/kaggle-b12-benchmark-b2-vi-r03-2026-10-22.md).

### 2026-10-23 — final VI verified;11 native successes/1 setup failure

B2 VI r03 private v1 COMPLETE:26 saved files/25 native manifest hashes/report
digest pass.100 genuine VI cases/full paired source,7,208-row cache/500 train
selections, T4×2 runtime/timing/cleanup and12 attempted IDs verified. N=100:
12 extraction ok,88 prose; P95 68.346s; native57.77m, driver79.56m. Setup21.16m
exceeded old20m but passed new27m. Quota remaining18.451761h. No new BigQuery,
SQL repair/tuning/adaptation or execution accuracy. Scientific blockers remain.
Independent registry:11 native successes, EN/VI kept separate, B1 EN3/VI3,
B2 EN2/VI3; one failed EN setup. All12 original slots attempted; none unstarted.
User requests next process, but previous scope excluded EN retry. Disabled new-ID
B2 EN replacement proposal prepared, not implemented/submitted; explicit scope
exception and bounded identity support/tests required before any new run.
[Final VI](../research/kaggle-b12-benchmark-b2-vi-r03-2026-10-22.md).

### 2026-10-23 — generation matrix hoàn tất với replacement02

B2 EN r03 replacement02 COMPLETE, đủ 100 genuine cases; 31 extraction OK,
60 prose, 8 unsafe, 1 invalid; P95 50,256s. Toàn bộ 12 generation roles đã đủ:
B1 EN3/VI3, B2 EN3/VI3, N=100/run/language. Tổng 14 attempted IDs gồm hai setup
failures giữ riêng, không có accuracy denominator cho failure trước inference.
Không cần thêm generation; scientific blockers và latency gate fail giữ nguyên.
[Ma trận verified](../research/kaggle-b12-generation-matrix-2026-10-23.md).

### 2026-10-24 — T5.4 offline hoàn tất; gate tiếp theo là execution review

Tại `1f2f9da`, đã xuất/validate 12 canonical runs và 1.200 case traces, giữ
source hashes và paired VI lineage. Mỗi replicate: B1 EN/VI exact/structural 0/100;
B2 EN exact 2/100, structural 6/100; B2 VI exact 0/100, structural 1/100.
Agreement raw output/canonical observation là 100/100 trong từng nhóm ba runs;
không pooling languages/replicates và chưa công bố CI reproducibility.
Execution accuracy/answer metrics vẫn null, inference cost unmeasured.
Privacy worksheets chưa ký, proposal BigQuery disabled; chưa có T5.4-B execution,
reports/comparisons hoặc quyết định B3. Backlog đã đồng bộ để ưu tiên gói duyệt
BigQuery, giữ nguyên mọi native artifact và historical checkpoint.
[Handoff và kiểm chứng](../research/t54-offline-2026-10-24.md).

### 2026-10-24 — gói duyệt BigQuery chuyển sang free-only

Theo yêu cầu người dùng, thay đề xuất trả phí bằng sandbox giữ billing tắt và
paid spend 0 USD. Metadata xác minh project/dataset US, direct objects và usage
history; chưa query/dry-run. Pin nguồn pricing/sandbox và scope 143 unique SQL
cho bước dry-run miễn phí, giữ đủ 1.329 logical references. Bốn privacy
worksheets đã điền provider/policy hash, reviewer/time vẫn chờ quyết định thật.
Số dư quota chưa biết; full protocol có thể vượt một tháng miễn phí, không tự
reuse gold, bật billing hoặc thay protocol. Đề xuất 60 USD cũ lưu lịch sử.
[Gói duyệt và điều kiện live riêng](t54-bigquery-approval-2026-10-24.md).

### 2026-10-24 — T5.5 giữ B3 QLoRA làm mục tiêu chính

Người dùng xác nhận giữ fine-tuning để trả lời RQ1. Đồng bộ snapshot, thứ tự
thực hiện và ticket T5.5: full B3 hoặc scope-down có genuine QLoRA; giảm sweep/
phần không thiết yếu khi có bằng chứng thiếu tài nguyên. B1/B2 yếu và quota
BigQuery không tự chứng minh nên bỏ B3. Việc bỏ B3 là thay đổi scope cần người
dùng quyết định riêng. Cách diễn đạt cũ liệt kê bỏ fine-tuning ngang hàng được
giữ trong lịch sử Git; chưa có quyết định bỏ B3 hoặc quyền mở training mới.

## T5.4 shared protocol — cập nhật 2026-10-24

Đã duyệt hai thay đổi: cô lập prediction SQL lỗi/vượt 24 GiB thành failure và dùng
chung execution evidence cho exact SQL trong một campaign. Giữ N=100, EN/VI riêng,
12 generation runs và B3 QLoRA. Implementation/offline scope xem
[checkpoint shared protocol](../research/t54-shared-protocol-2026-10-24.md).
Live vẫn chờ verified free allowance/reservation và final config/hash approval;
không dùng forecast ~752,10 GiB làm quota balance hoặc claim scientific complete.
