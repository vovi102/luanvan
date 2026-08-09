# T3.4 — Deterministic Noise Injection (Stage D)

## Mục tiêu

Tăng độ robust của NL2SQL model bằng cách giữ nguyên 3.000 câu Stage C và thêm
đúng 150 noisy variants có thể tái lập. Noise chỉ tác động câu tiếng Anh; gold
GoogleSQL, slot facts, entity context, Stage A proof và metadata LLM bất biến.

## Phụ thuộc

- T3.3 phải tạo và audit thành công
  `data/dataset/raw/synthetic-stage-c.jsonl` gồm đúng 3.000 records.
- Entity dictionary T2.2 dùng để bảo vệ owner/primary labels trong câu hỏi.

T3.3 hiện bị chặn bởi `OPENROUTER_API_KEY`, nên implementation và full-size
fixture verification của T3.4 đã hoàn tất nhưng final Stage D chưa thể sinh.

## Contract đã chốt

- Seed: `42`.
- Source: đúng 3.000 Stage C records đã qua validator T3.3.
- Output: đúng 3.150 records gồm 3.000 originals không đổi và 150 variants.
- Exact quotas: `typo=38`, `abbrev=38`, `fragment=37`, `mixed_case=37`.
- Mỗi Stage C record có nhiều nhất một noisy variant.
- `noise_type` chỉ nhận một trong bốn giá trị trên; không dùng compound label.
- Output byte-stable khi source bytes, dictionary và config không đổi.
- Mỗi final file atomic replace dưới process lock. Unique staging, durable
  backups và journal cho phép rollback lỗi bắt được và recovery sau interruption.

Candidate selection bắt đầu từ source IDs đã sort, dùng RNG seed dẫn xuất từ
SHA-256 của `42:<noise_type>`, rồi fill exact quota. Nếu một type không đủ valid
candidates, pipeline fail trước publication thay vì giảm quota hoặc đổi tỷ lệ.

## Biến đổi

- `typo`: swap đúng một cặp chữ cái kề nhau bên trong một từ dài ít nhất 5 ký tự.
- `abbrev`: thay đúng một structural phrase dài nhất theo
  `src/nl2sparql/dataset/noise/abbreviations.json`.
- `fragment`: bỏ đúng một request scaffold, article hoặc dấu hỏi cuối.
- `mixed_case`: đổi casing đúng một từ alphabetic.

Dictionary abbreviation cố ý không chứa Binance, Tornado Cash hoặc named entity
khác. Slot literals, date, number, address, token symbol và pinned owner/label
được chuyển thành protected spans; sau biến đổi, T3.3 anchor validator chạy lại.

## Schema noisy record

```json
{
  "id": "stage-c-0123-casual-noise-typo",
  "noise_parent_id": "stage-c-0123-casual",
  "nl_original": "Show transactions from Binance between 2026-06-01 and 2026-06-02?",
  "nl": "Show transacitons from Binance between 2026-06-01 and 2026-06-02?",
  "nl_normalized": "show transacitons from binance between 2026 06 01 and 2026 06 02",
  "noise_type": "typo",
  "noise_seed": 42,
  "noise_distance": 0.0164,
  "sql": "<exact source GoogleSQL>",
  "record_sha256": "<exact Stage A record hash>"
}
```

Ngoài `id`, `nl`, derived `nl_normalized` và năm metadata fields T3.4, mọi field
phải bằng source record. Validator recompute normalization/distance và không tin
metadata lưu sẵn.

## Automated quality gates

- 3.150 unique IDs và raw questions; đúng count/quota/single-source contract.
- `nl_original` bằng source `nl`; SQL và `record_sha256` không đổi.
- Tất cả numeric/date/token/entity anchors còn hợp lệ.
- Typo distance trong `(0, 0.10]`, abbrev `(0, 0.35]`, fragment `(0, 0.45]`.
- Mixed case phải khác raw text nhưng normalize đúng về source.
- Non-mixed normalized questions không collision với toàn corpus.
- Manifest lưu source/output/dictionary SHA-256, counts, quotas, stats, 150
  selected source IDs và 30 audit IDs deterministic.

Automated gates không thay manual decipherability review. Sau live generation,
review đúng 30 IDs trong manifest và yêu cầu ít nhất 27/30 vẫn hiểu được.

## Artifacts và lệnh chạy

- `data/dataset/raw/synthetic-stage-d.jsonl` — final 3.150 rows.
- `data/dataset/raw/noise-config.json` — hashes, config, stats, selection và audit.
- `notebooks/10_noise_injection.ipynb` — hiển thị summary và 30 audit rows.

```bash
# Generate + validate + locked, recoverable publication
uv run python scripts/11_inject_noise.py --mode generate

# Recompute all evidence against published files
uv run python scripts/11_inject_noise.py --mode validate-output
```

CLI hỗ trợ `--source`, `--output`, `--manifest`, `--abbreviations` để chạy trên
explicit paths; defaults luôn trỏ tới artifact paths chuẩn của repository.

## Acceptance criteria

- [x] Pure transforms deterministic và không sửa protected spans.
- [x] Full-size fixture tạo đúng 3.150 records và quotas 38/38/37/37.
- [x] Tests chứng minh one-source-one-variant, SQL/hash immutability, fresh
  normalization, distance/collision/anchor gates và insufficient-candidate fail.
- [x] Manifest evidence, 30 audit IDs, process lock, unique staging, rollback và
  interrupted-run recovery được test.
- [x] CLI generate→validate-output chạy end-to-end trên fixture 3.000 rows.
- [ ] Final Stage D có đúng 3.150 records từ accepted live Stage C artifact.
- [ ] Final source/output/dictionary hashes và validator evidence được ghi nhận.
- [ ] Manual review 30 noisy records đạt ít nhất 27/30 decipherable.

## Trạng thái — implementation complete, artifact credential-gated

Implementation hoàn tất ngày 2026-08-09. Default live command hiện exit 1 vì
`synthetic-stage-c.jsonl` chưa tồn tại; kiểm tra xác nhận không tạo
`synthetic-stage-d.jsonl` hoặc `noise-config.json` khi fail. Đây là downstream
gate trực tiếp từ T3.3, không phải lý do hạ acceptance hoặc sinh dữ liệu giả.

## Evidence

- Design:
  `docs/superpowers/specs/2026-08-09-t3-4-deterministic-noise-injection-design.md`.
- Plan:
  `docs/superpowers/plans/2026-08-09-t3-4-deterministic-noise-injection.md`.
- Focused verification: 35 tests pass cho transforms, allocator, artifacts và CLI.
- Notebook đã execute; output ghi package versions, credential gate và logic
  decipherability ratio khi audit hoàn tất.
- Default CLI gate: missing Stage C, exit `1`, Stage D/manifest absent.
