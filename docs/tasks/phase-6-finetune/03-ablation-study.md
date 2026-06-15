# T6.3 — Ablation Study

## Mục tiêu

Chạy 4-5 ablation configs để quantify đóng góp của từng component (schema linker, entity linker, constrained decoding, LoRA hyperparameters). Đây là **bằng chứng định lượng** cho RQ2.

## Bối cảnh & lý do

Ablation là "must-have" cho thesis ML. Mỗi component có thể đẹp về mặt design nhưng không cải thiện accuracy → bóc tách bằng ablation.

5 configs cốt lõi:
1. **Full system** (B3 + schema linker + entity linker + class resolver + constrained decoding).
2. **No schema linker** (cấp full ontology trong prompt thay vì top-K).
3. **No entity linker** (LLM tự xử lý "Binance" trong prompt).
4. **No constrained decoding** (free decoding).
5. **LoRA r=8 vs r=16 vs r=32** (hyperparameter ablation).

## Phụ thuộc

- T6.1 — B3 checkpoint.
- T6.2 — Constrained decoding.
- T4.1-4.3 — Linking modules.
- T5.4 — Evaluation framework.

## Đầu vào

- B3 model + LoRA adapters từ T6.1.
- Test set 100 câu.
- Linking modules.

## Đầu ra

- Predictions cho mỗi config: `data/eval/predictions/ablation_<config>_test.jsonl`.
- Ablation report `docs/eval/ablation.md` với bảng + insights.
- LaTeX table source cho thesis chapter.

## Acceptance criteria

- [ ] 5+ configs run hoàn tất trên test set.
- [ ] Bảng so sánh có CI (95%) cho mỗi config.
- [ ] Statistical significance test (paired bootstrap) giữa Full vs ablation.
- [ ] Mỗi config có note rõ "what changed" để reproducible.

## Hướng dẫn triển khai

### Config matrix

| Config ID | Schema linker | Entity linker | Class resolver | Constrained dec. | LoRA r |
|---|---|---|---|---|---|
| `full` | ✓ | ✓ | ✓ | ✓ | 16 |
| `no_schema` | ✗ (full ontology) | ✓ | ✓ | ✓ | 16 |
| `no_entity` | ✓ | ✗ (raw mention) | ✗ | ✓ | 16 |
| `no_constr` | ✓ | ✓ | ✓ | ✗ | 16 |
| `r8` | ✓ | ✓ | ✓ | ✓ | 8 |
| `r32` | ✓ | ✓ | ✓ | ✓ | 32 |

(Có thể thêm `no_class_resolver` nếu thời gian.)

### Hyperparameter ablation (r=8, r=32)

Cần re-train cho mỗi r. Nếu thời gian gấp:
- Train r=8 và r=32 với epochs giảm (1-2 thay 3) — chấp nhận less converged.
- Hoặc skip r ablation, chỉ giữ component ablation.

### Run script template

```python
def run_ablation(config_name, test_set, model, linkers, decoder):
    predictions = []
    for case in test_set:
        # Step 1: linking (toggle on/off based on config)
        if config_name != "no_schema":
            schema_results = linkers["schema"].link(case["nl"], top_k=10)
        else:
            schema_results = ALL_PROPS  # full ontology

        if config_name != "no_entity":
            entity_results = linkers["entity"].link(case["nl"])
        else:
            entity_results = []

        # Step 2: build prompt
        prompt = build_prompt(case["nl"], schema_results, entity_results, config_name)

        # Step 3: generate
        if config_name != "no_constr":
            sparql = decoder.generate_constrained(prompt)
        else:
            sparql = decoder.generate_free(prompt)

        predictions.append({
            "id": case["id"],
            "config": config_name,
            "predicted_sparql": sparql,
        })
    return predictions
```

### Ablation analysis

```python
def compare_configs(predictions_by_config, gold):
    table = {}
    for cfg, preds in predictions_by_config.items():
        ea = exec_acc(preds, gold)
        em = exact_match(preds, gold)
        f1 = answer_f1(preds, gold)
        ci = bootstrap_ci([1 if e else 0 for e in eval_each(preds, gold)])
        table[cfg] = {"ea": ea, "em": em, "f1": f1, "ci": ci}
    return table
```

### Statistical significance

Paired bootstrap (cùng test cases):

```python
def paired_bootstrap(scores_a, scores_b, n=10000):
    """H0: scores_a == scores_b. Return p-value."""
    diffs = np.array(scores_a) - np.array(scores_b)
    observed = np.mean(diffs)
    centered = diffs - observed
    boots = [np.mean(np.random.choice(centered, len(diffs), replace=True))
             for _ in range(n)]
    p = np.mean(np.abs(boots) >= np.abs(observed))
    return observed, p
```

Ablation chỉ "có ý nghĩa" nếu p < 0.05.

### Report template

```markdown
# Ablation Study

## Setup

- Base model: Llama 3 8B Instruct + QLoRA adapter (B3).
- Test set: 100 cases (T3.5).
- Each config run with seed=42, temperature=0.

## Results

| Config | Exact Match | Exec Acc | Answer F1 | 95% CI | Δ vs Full |
|---|---|---|---|---|---|
| Full | 50% | 78% | 0.81 | [73, 83] | — |
| no_schema | 38% | 65% | 0.69 | [60, 70] | -13 (p<0.001) |
| no_entity | 41% | 68% | 0.72 | [63, 73] | -10 (p<0.01) |
| no_constr | 47% | 75% | 0.78 | [70, 80] | -3 (p=0.08, n.s.) |
| r=8 | 46% | 73% | 0.76 | [68, 78] | -5 (p=0.03) |
| r=32 | 51% | 79% | 0.82 | [74, 84] | +1 (p=0.4, n.s.) |

(Numbers placeholder.)

## Findings

1. **Schema linker đóng góp lớn nhất** (-13% nếu remove). Confirms RQ2.
2. **Entity linker quan trọng** cho long-tail entities (-10%).
3. **Constrained decoding giảm syntax error xuống 0** nhưng accuracy delta nhỏ — có nghĩa B3 fine-tuned đã ít syntax error.
4. **r=16 đủ**, r=32 không cải thiện đáng kể (Occam's razor: chọn r=16).
```

### Compute budget

- Mỗi config inference 100 cases: ~10 phút trên T4 với B3.
- 6 configs × 10 min = 1 giờ inference.
- Re-train r=8, r=32: 2 × 5h = 10h. Nếu Kaggle quota tight → skip r ablation.

## Rủi ro & note

- **Compute không đủ:** prioritize component ablation (no_schema, no_entity, no_constr) > hyperparameter (r) ablation.
- **Variance giữa runs:** với temp=0 nên deterministic, nhưng nondeterminism từ CUDA có thể nhỏ. Run 1 lần đủ.
- **Edge case ablation:** "no_entity but with class resolver" → khó vì class resolver dependent on entity linker. Skip combo này.
- **Không có Full vượt B3 base:** hiếm nhưng có thể. Document thành "limitation" chap.

## Estimated effort

2-3 ngày (1 ngày code + 1 ngày run + 1 ngày analyze).

## Trạng thái

todo
