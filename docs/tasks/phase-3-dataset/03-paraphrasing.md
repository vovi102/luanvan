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

Implementation offline hoàn tất. Stage A v2 đã được accept bằng genuine BigQuery
evidence ngày 2026-10-15; canonical publication còn chờ audit 100 EN + 100 VI và
các build/validation gates. Chưa tạo corpus 8.000 records trong lượt final-live.

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

## Tài liệu

- Spec: `docs/superpowers/specs/2026-10-07-deterministic-bilingual-training-design.md`
- Plan: `docs/superpowers/plans/2026-10-07-deterministic-bilingual-training.md`
