# T5.1 — B0 GoogleSQL Rule-Based Baseline

## Mục tiêu

Triển khai lower-bound B0 không dùng LLM: chọn một template GoogleSQL đã được
duyệt, fill slot có kiểu và trả query read-only an toàn; khi evidence không đủ
hoặc intent nhập nhằng, baseline trả `None` thay vì đoán.

## Quyết định kiến trúc

Sau Pivot #1, output canonical là GoogleSQL trên analytical catalog. B0 không tự
xây query từ fragment và không chèn text bắt được trực tiếp. Module
`src/nl2sparql/models/b0/` che template compilation, typed extraction,
T4.1–T4.3 evidence, structural scoring, rendering và SQL safety sau interface:

```python
BaselineB0.predict(nl: str) -> str | None
BaselineB0.predict_detailed(nl: str) -> B0Prediction | None
```

Seed-shaped full match được ưu tiên. Structural fallback dùng token F1 sau khi
mask typed/entity spans; tie trong ambiguity margin chỉ được phá khi T4.1 tạo
schema overlap duy nhất. Nếu vẫn hòa, B0 abstain. Entity/concept slot chỉ nhận
T4.3 plan `resolved`, không warning, coverage `supported` và đúng cardinality.

Mọi slot map đi qua T3.1 `render_template`; SQL cuối đi qua SQLGlot BigQuery
validator của T3.5 để enforce một read-only statement, explicit projections và
managed relations.

## Phụ thuộc

- T3.1 — 25 GoogleSQL templates và typed renderer.
- T3.5 — finalized three-pool test-set contract và SQL safety validator.
- T4.1 — relation/field ranking để phá structural tie duy nhất.
- T4.2 — entity recognition với source spans và fingerprints.
- T4.3 — catalog-backed instance/concept resolution và coverage policy.

## Đầu ra

- Public facade: `src/nl2sparql/models/b0_rule_based.py`.
- Deep module: `src/nl2sparql/models/b0/`.
- CLI: `scripts/16_b0_rule_baseline.py`.
- Predictions: `data/eval/predictions/b0_test.jsonl` khi có input hợp lệ.
- Report: `reports/b0_evaluation.json` khi có input hợp lệ.
- Notebook reader: `notebooks/13_b0_eval.ipynb`.
- Design/plan: `docs/superpowers/specs/2026-09-01-t5-1-google-sql-rule-baseline-design.md`
  và `docs/superpowers/plans/2026-09-01-t5-1-google-sql-rule-baseline.md`.

## Workflow local

```bash
PYTHONPATH=src python scripts/16_b0_rule_baseline.py predict \
  --question "How many transactions happened between 2026-06-15 and 2026-06-16?"

PYTHONPATH=src python scripts/16_b0_rule_baseline.py evaluate \
  --test-set data/eval/test-100.jsonl
```

`--help`, input preflight và missing-artifact paths không khởi tạo encoder. Lệnh
production chỉ load cache/model snapshot local; thiếu artifact trả structured
`blocked`. Predictions được publish trước, report cuối; report failure khôi phục
predictions đã được chấp nhận trước đó.

## Metrics và readiness

Evaluator tách các metric:

- coverage trên toàn bộ cases;
- exact SQL accuracy trên matched cases;
- structural SQLGlot accuracy trên matched cases;
- warm p50/p95 prediction latency;
- execution accuracy chỉ từ result semantics có live evidence.

Local readiness cần artifact đã review, không synthetic, coverage `>=0.40`,
structural accuracy `>=0.60` và warm p95 `<100 ms`. Scientific readiness còn cần
execution accuracy `>=0.60` trên finalized T3.5 benchmark. AST equality không
được dùng thay execution accuracy.

## Acceptance criteria

### Implementation local

- [x] API `BaselineB0.predict(nl: str) -> str | None`.
- [x] Compile và fingerprint exact 25-template snapshot.
- [x] Typed slot parsing, bounds/date-window validation và repeated-slot order.
- [x] T4.1 tie evidence; T4.2/T4.3 instance/concept evidence fail closed.
- [x] Render qua T3.1 và validate read-only managed GoogleSQL qua T3.5.
- [x] Offline evaluator tách coverage/text/structural/latency/execution metrics.
- [x] Synthetic fixture không thể tạo readiness giả.
- [x] Canonical atomic artifacts, report-last publication và rollback.
- [x] Lazy numbered CLI và notebook report reader.
- [ ] Final focused/full test, Ruff, CLI, notebook và diff evidence được ghi sau
  whole-branch review.

### Pending reviewed/live evidence

- [ ] Finalized T3.5 test set khoảng 100 câu đã review độc lập có mặt local.
- [ ] Coverage `>=0.40` trên artifact đó.
- [ ] Structural accuracy `>=0.60` trên matched cases.
- [ ] Warm p95 `<100 ms` trên artifact đó.
- [ ] Execution accuracy `>=0.60` với valid warehouse result evidence.

## Trạng thái

`implementation in progress — final local verification pending; reviewed/live evidence pending`
