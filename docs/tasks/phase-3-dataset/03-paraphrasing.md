# T3.3 — Deterministic bilingual training corpus

> External paraphrasing is out of scope. The active producer is deterministic
> and performs no model, network, credential or provider call.

## Mục tiêu

Tạo corpus NL–GoogleSQL song ngữ từ accepted Stage A và finite catalog gồm 25
intent × hai ngôn ngữ × bốn styles. Mỗi semantic family render tám records; đầu
ra mục tiêu là 8.000 records có provenance và byte reproducibility.

## Gates

- Stage A source phải có lifecycle `accepted`, đủ 1.000/1.000 live-verified
  records, zero cache hits và manifest hash hợp lệ.
- Held-out English/Vietnamese benchmark chỉ đi vào producer dưới dạng hash.
- Split theo semantic family; không để variants cùng family rơi vào train/dev khác nhau.
- Diversity, SQL identity, slot preservation và leakage checks fail closed.
- Audit 100 records mỗi ngôn ngữ, phủ 25 intent × bốn styles.
- Publication atomic; chạy build/validate hai lần phải cho bytes giống nhau.

## Workflow

```bash
uv run python scripts/20_build_bilingual_training.py --help
uv run python scripts/21_validate_bilingual_training.py --help
```

## Trạng thái

Implementation và canonical clean publication hoàn tất trong lượt build
2026-10-15; kiểm tra cuối và bàn giao tiếp tục ngày 2026-10-16.
Stage A v2 đã được accept bằng genuine BigQuery evidence; sau correction/audit
r1, user duyệt build offline. Corpus canonical có 8.000 records (4.000 EN +
4.000 VI), 1.000 families, 25 intents; train/development = 7.208/792.
Hai build byte-identical; cả hai staging triples và canonical đều pass CLI 21.
Các mục audit bên dưới ghi lịch sử từng thời điểm, không phải trạng thái chờ hiện tại.

Evidence: `docs/research/stage-a-v2-final-live-acceptance-2026-10-15.md`.

### Agent audit — 2026-10-15

Đã đọc và chấm đủ 100 EN + 100 VI, seed 42, phủ 25 intents × 4 styles mỗi
ngôn ngữ. EN: faithful 67/100, natural 96/100; VI: faithful 73/100, natural
93/100. Cả hai **fail faithfulness gate 95/100**, dù naturalness đạt 90/100.
Giữ đủ 200 quyết định agent-reviewed, không coi là human/independent review.

Hai lần lấy mẫu byte-identical; binding ID/hash/provenance pass. Validator từ
chối publication ở đúng faithfulness threshold. Không sửa catalog/SQL, không
gọi provider, không publish canonical 8.000 records. Accepted Stage A V2 không
đổi. Cần task sửa wording/top-k/date boundary rồi fresh audit trước publication.

Report: `docs/research/bilingual-training-agent-audit-2026-10-15.md`.

### Catalogue correction + re-audit r1 — 2026-10-15

User đã duyệt sửa wording và audit lại. Chỉ đổi 200 patterns/content digests,
giữ renderer, schema, SQL và accepted Stage A V2. Catalog cũ được archive nguyên
bytes; sample/200 quyết định fail ban đầu giữ nguyên.

Audit r1: 100 EN + 100 VI, seed 42 và cách chọn mẫu không đổi. Mỗi ngôn ngữ
100/100 faithful, 100/100 natural, vượt gate 95/90. Binding/provenance pass;
quyết định cũ bị từ chối khi ghép với digest mới. Đây là cùng agent tự review,
không phải human/independent review; không suy ra chất lượng ngoài mẫu.

36 focused tests pass; full suite 1.485 passed, 342 upstream warnings, 510,32s.
Ruff/format/diff pass. Chưa publish corpus canonical 8.000 hoặc manifest,
không gọi provider.

Report: `docs/research/bilingual-training-audit-correction-r1-2026-10-15.md`.

### Canonical clean build — 2026-10-15

Đã publish ba artifacts corpus/manifest/audit bằng publisher giao dịch sẵn có,
giữ nguyên accepted source, SQL/slots, catalog và audit r1. Không family nào
cross train/dev; diversity và digest-only leakage gates pass. Hai build và ba
lượt validate-artifact chạy offline, zero observed credential/network/provider/
subprocess attempts. Không đọc benchmark wording, không train/evaluate model.
Audit vẫn là same-agent review, không phải human/independent review.

Fresh verification: 94 bilingual tests pass (8 workflow + 34 assembly + 52
remaining); Ruff/format/diff pass. Không coi lượt test bị ngắt trước đó là pass;
không claim đã chạy lại full repository suite trong lượt build này.

Report: `docs/research/bilingual-training-canonical-build-2026-10-15.md`.

### Downstream B2 integration — 2026-10-16

Hoàn tất offline tại `9adf02c`: lossless train-only export
`data/dataset/processed/b2-training.jsonl`, 7.208 records / 901 families, hash riêng
bind canonical publication `2b652a3`. Không đổi canonical, SQL, ID, family/slot
provenance, không rename `style` thành `text_variant`, không thêm acceptance flag.
B2 xác minh exact canonical train projection và exact consumed fingerprint trước
cache/encoder. 792 development records tuyệt đối không vào retrieval. Training
adapter/test đã khóa trước khi mở benchmark VI để soạn review pack.

Report: `docs/research/b2-training-integration-2026-10-16.md`.
Genuine encoder/Kaggle inference vẫn pending; integration không phải model evidence.

## Tài liệu

- Spec: `docs/superpowers/specs/2026-10-07-deterministic-bilingual-training-design.md`
- Plan: `docs/superpowers/plans/2026-10-07-deterministic-bilingual-training.md`
