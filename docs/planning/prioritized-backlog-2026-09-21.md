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
| T5.1/B0 | Genuine negative result hoàn tất (`0/100`) | Giữ làm lower bound, không tune trên test set |
| T3.3 → B2 | Offline integration hoàn tất tại `9adf02c`; lossless train export 7.208 rows, exact fingerprint | Giữ development ngoài retrieval; bundle pinned source files cho Kaggle |
| T5.2/B1–B2 | Typed runner/cache hoàn tất; T4 smoke v2 COMPLETE, 10 genuine non-test processes, không OOM | 12 genuine benchmark processes còn pending; smoke latency vượt target, B1 5 unsafe_sql |
| B1/B2 Vietnamese consumer | Typed finalized paired consumer + CLI17/CLI25 EN/VI implemented offline | Giữ nguồn/hash/lineage và exact reused evidence; genuine runs vẫn pending |
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
   vượt target, B1 5 unsafe_sql; không tune theo output. Chốt campaign/wall-time
   cap và quota mới trước 12 genuine benchmark processes; publish native artifacts.
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
