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
- T3.5 — finalized `agent_authored_human_reviewed_v1` test-set contract và SQL
  safety validator.
- T4.1 — relation/field ranking để phá structural tie duy nhất.
- T4.2 — entity recognition với source spans và fingerprints.
- T4.3 — catalog-backed instance/concept resolution và coverage policy.

## Đầu ra

- Public facade: `src/nl2sparql/models/b0_rule_based.py`.
- Deep module: `src/nl2sparql/models/b0/`.
- CLI: `scripts/16_b0_rule_baseline.py`.
- Native predictions/report: `data/eval/b0/predictions.jsonl` và
  `data/eval/b0/report.json`.
- Canonical run/evidence/report: `data/eval/canonical/b0-run-01.json`,
  `data/eval/evidence/b0-exec-01.{json,jsonl}` và
  `reports/evaluation/b0-run-01.json`.
- Notebook reader: `notebooks/13_b0_eval.ipynb`.
- Design/plan: `docs/superpowers/specs/2026-09-01-t5-1-google-sql-rule-baseline-design.md`
  và `docs/superpowers/plans/2026-09-01-t5-1-google-sql-rule-baseline.md`.

## Workflow local

```bash
PYTHONPATH=src python scripts/16_b0_rule_baseline.py predict \
  --question "How many transactions happened between 2026-06-15 and 2026-06-16?"

PYTHONPATH=src python scripts/16_b0_rule_baseline.py evaluate \
  --test-set data/dataset/test/test-100.jsonl \
  --predictions data/eval/b0/predictions.jsonl \
  --report data/eval/b0/report.json
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
- [x] Final focused/full test, Ruff, CLI, notebook và diff evidence đã được kiểm
  tra sau whole-branch review.

### Bằng chứng local — 2026-09-01

- Review checkpoint: `a7b8b9a240c028f15a28c4df1588bf89b03e2fc0`.
- Focused B0 suite: `50 passed in 2.66s`.
- Full repository suite: `869 passed, 342 warnings in 44.18s`.
- `ruff check .`: pass; `ruff format --check .`: 169 files already formatted.
- Numbered CLI `--help`: pass; production `predict` dùng model/cache local trả
  `ready`, GoogleSQL hợp lệ và đủ template/policy/catalog/dictionary fingerprints.
- Notebook JSON, executed-cell contract, `git diff --check`: pass.
- Standards/spec whole-branch review: không còn finding Critical/Important; helper
  path-alias dùng chung được giữ lại như design debt ngoài phạm vi T5.1.
- Các metric coverage/accuracy/latency bên dưới chưa được tuyên bố vì chưa có
  finalized T3.5 reviewed artifact phù hợp.

### Genuine evaluation — 2026-10-03

- [x] Finalized T3.5 gồm 100 câu agent-authored, single-human-reviewed và
  live-verified có mặt local; test-set SHA-256
  `5d342a5c063ea2d4b5fb7cd62ab15fabb82d2164e5eca5cb248843797989ff0d`.
- [ ] Coverage `>=0.40`: **không đạt**, `0/100 = 0.0`.
- [ ] Structural accuracy `>=0.60` trên matched cases: **không đạt**, report
  full-denominator là `0/100 = 0.0`; không có matched case để công bố
  matched-only accuracy.
- [ ] Warm p95 `<100 ms`: **không đạt**, canonical p95 `259.65499335 ms`.
- [ ] Execution accuracy `>=0.60`: **không đạt**, `0/100 = 0.0` với 100 gold
  executions `ok` và 100 predictions `skipped_no_output`.

Genuine run được giữ nguyên như negative result; không chỉnh template, parser,
threshold hoặc linker sau khi xem T3.5 để tránh tune trên test set. Source review
gợi ý mismatch giữa 25 seed templates/typed slot extractor và query shapes/cách
diễn đạt tự nhiên của T3.5, nhưng đây chỉ là hypothesis chẩn đoán, không phải
causal claim được artifact bên dưới chứng minh.

Artifacts:

- Native: `data/eval/b0/predictions.jsonl`, `data/eval/b0/report.json`.
- Canonical run: `data/eval/canonical/b0-run-01.json`.
- Live evidence/journal: `data/eval/evidence/b0-exec-01.json` và
  `data/eval/evidence/b0-exec-01.jsonl`.
- Canonical report: `reports/evaluation/b0-run-01.json`, artifact SHA-256
  `d58a3320f4d5b9c7ee4e0ad07fd4bbc03d91ec7eaac30444470f64eb15c00ac4`.
- BigQuery: `559,594,602,496` billed bytes, estimated on-demand cost
  `$3.1809270381927490234375`; guard `24 GiB/query`, `600 GiB` aggregate và
  `$3.67`.
- T5.4 report có implementation blockers rỗng nhưng scientific blockers còn
  `incomplete_reproducibility`, `missing_genuine_baseline_runs` và
  `missing_privacy_evidence`; các blocker này không được che giấu bằng fixture.

## Trạng thái

`genuine evaluation complete — B0 acceptance thresholds not met`
