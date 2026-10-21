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

## Snapshot

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
| T5.2/B1–B2 | T4 smoke COMPLETE; genuine B1/B2 × EN/VI r01 COMPLETE, N=100 each, artifact/runtime verified | 7/12 native processes complete; 5 unstarted. B2 EN r02: 31 ok / 60 prose / 8 unsafe / 1 invalid, P95 51.300s. B1 VI r02: 100 unsafe, P95 29.532s. B1 EN r02: 99 unsafe / 1 invalid, P95 48.809s. B2 VI: 12 ok / 88 prose, P95 73.590s. B2 EN: 31 ok / 60 prose / 8 unsafe / 1 invalid, P95 52.987s. B1 EN: 99 unsafe / 1 invalid, P95 49.107s; VI: 100 unsafe, P95 30.376s. Scientific gates remain blocked |
| B1/B2 Vietnamese consumer | Typed finalized paired consumer + CLI17/CLI25 EN/VI implemented offline | Giữ nguồn/hash/lineage và exact reused evidence; B1/B2 VI r01 verified, r02/r03 pending |
| T5.4 | Framework hoàn tất; comparison chưa đủ input | Ingest B1–B3 genuine runs và làm failure analysis |
| T5.5 | Chưa quyết định scope fine-tuning | Quyết định full B3, scope-down B3 hoặc full-system không fine-tune từ số liệu B1/B2 |
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

4. **B1/B2 genuine run.** [Runner/bundle EN/VI](kaggle-b12-runbook-2026-10-16.md)
   đã chuẩn bị offline: input allowlist/hash, deterministic archive, data/runtime
   preflight, notebook với execution mặc định tắt. Model/encoder đã pin và cache
   Kaggle version 5 đã xác minh; full Python 3.11.15 environment đã cài thành công
   ở phiên riêng. Non-test T4 smoke v2 đã COMPLETE, 10/10 genuine processes,
   không OOM. Giữ negative observations: median generation B1 20,95s/B2 20,01s
   vượt target, B1 5 unsafe_sql; không tune theo output. Notebook benchmark 16 và
   [campaign offline](kaggle-b12-benchmark-campaign-2026-10-18.md) đã chuẩn bị;
   chốt campaign/caps/budget và quota mới trước khi cho phép 12 genuine processes.
   B1 EN và VI r01 đã COMPLETE (mỗi ngôn ngữ 100/100 genuine); 10 process
   còn lại chưa khởi chạy. Giữ native outputs/blockers nguyên trạng.
   Ba compatible process runs cho mỗi (baseline, language): EN+VI tổng 12 processes.
   VI đã có typed paired consumer và source-bound native/T5.4 artifacts; metric N=100
   riêng mỗi language, không pooling. [Offline handoff](../research/b12-bilingual-consumer-2026-10-16.md).
5. **T5.4 comparison vòng 1.** So sánh B0/B1/B2, báo execution accuracy,
   exact/structural match, answer metrics, latency, cost, reproducibility và
   failure modes với CI/bootstrap đã chốt.
6. **T5.5 decision.** Chọn full B3, scope-down B3 hoặc bỏ fine-tuning. Quyết định
   dựa trên B1/B2 genuine metrics và linker deltas, không dựa trên fixture.

### P2 — Hệ thống đề xuất

7. **T6.1-SQL — B3 QLoRA** nếu T5.5 chọn fine-tuning; target là GoogleSQL từ
   accepted deterministic bilingual artifact.
8. **T6.2-SQL — Constrained generation.** Grammar/safety target GoogleSQL; đo
   syntax/safety rate, execution accuracy và latency overhead.
9. **T6.3-SQL — Ablation.** Ưu tiên `no_schema`, `no_entity`, `no_class` và
   `no_constraint`; báo CI 95% và paired significance trên cùng test snapshot.
10. **T5.4 comparison cuối.** Tổng hợp B0–B3 và failure analysis; nếu bỏ
    fine-tuning thì thay B3 bằng full-system B2 + linkers + validator và ghi rõ
    B3 không được thực hiện.

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
- **Lane B — Model:** cache/runtime và T4 compatibility smoke đã xác minh;
  genuine benchmark B1/B2 còn pending. Giữ quan sát latency/unsafe_sql và
  kiểm tra lại quota, campaign/timeout trước khi chạy.
- **Lane C — Writing:** cập nhật RQ/contributions sang small-LLM-only, viết Plan A
  negative finding và methodology; không điền metrics chưa chạy.

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

Runner/input bundle EN/VI và cache Llama/MiniLM đã sẵn sàng. Private Kaggle
notebook `aohkvd/nl2sql-environment-cache`, version 5, đã COMPLETE: 24 files,
16.161.347.681 bytes, đúng hash qua hai lượt kiểm tra. Full environment đã cài
thành công riêng; cache output không chứa runtime đầy đủ.

T4 smoke version 2 đã COMPLETE ngày 2026-10-18: 10/10 genuine native
processes trên Tesla T4 ×2, không OOM; original BF16/4-bit settings giữ nguyên.
Median generation B1 20,95s/B2 20,01s vượt target hiện tại. B1 5 unsafe_sql;
B2 5 extraction ok không phải accuracy. Smoke dùng năm câu train, không phải test.

Tiếp theo chốt campaign, caps và quota hiện tại cho ba processes mỗi
(baseline, language), tổng 12 genuine benchmark processes, N=100 riêng EN/VI.
Chưa chạy benchmark hay BigQuery mới. Sau đó T5.4 comparison → T5.5 quyết định B3.
[Smoke result và evidence](../research/kaggle-t4-smoke-2026-10-17.md).

## Historical local-preparation checkpoint — 2026-10-17

> Checkpoint lịch sử trước khi user được cấp quyền; trạng thái hiện tại nằm ở
> checkpoint genuine cache bên dưới. Không dùng đoạn này làm gate hiện tại.

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
