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

Implementation offline hoàn tất. Canonical publication đang chờ Stage A v2
được accept bằng genuine BigQuery evidence và audit decisions hoàn chỉnh.

## Tài liệu

- Spec: `docs/superpowers/specs/2026-10-07-deterministic-bilingual-training-design.md`
- Plan: `docs/superpowers/plans/2026-10-07-deterministic-bilingual-training.md`
