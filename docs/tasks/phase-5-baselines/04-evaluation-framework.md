# T5.4 — Evaluation Framework (6 dimensions)

## Mục tiêu

Xây dựng evaluation framework đo 6 chiều: Accuracy, Latency, Cost, Privacy, Reproducibility, Failure Mode. Khung này dùng cho TẤT CẢ baselines + Full system.

## Bối cảnh & lý do

Evaluation framework là sản phẩm khoa học độc lập, có thể publish riêng. Nó cũng là cốt lõi RQ1 (RQ1 trả lời được khi compare 6 dimensions, không chỉ accuracy).

## Phụ thuộc

- T3.5 — Test set 100 câu (gold).
- Predictions từ T5.1-T5.3 (B0, B1, B2, B4, B5).
- Sau này: T6.1 (B3), T7.1 (Full system).

## Đầu vào

- `data/dataset/test/test-100.jsonl` (gold).
- Predictions per baseline (jsonl).
- Inference logs (latency, tokens, cost).

## Đầu ra

- Module `src/nl2sparql/evaluation/`:
  - `metrics.py` — accuracy metrics.
  - `executor.py` — chạy SPARQL trên Fuseki và compare results.
  - `failure_classifier.py` — phân loại lỗi.
  - `report.py` — generate Markdown + LaTeX tables.
- `data/eval/results/<baseline>_metrics.json`.
- `docs/eval/baseline_comparison.md` — bảng so sánh.

## Acceptance criteria

- [ ] Tất cả 6 dimensions implement và compute được.
- [ ] Per-baseline report chạy `python -m src.evaluation.report --baseline b1` < 60s.
- [ ] Stratified breakdown theo difficulty (Easy/Medium/Hard) và category.
- [ ] Report có CI (95%) cho accuracy metrics (bootstrap 1000).

## Hướng dẫn triển khai

### Dimension 1: Accuracy

3 metrics:

**(a) Exact Match (EM)** — chuỗi SPARQL giống hệt sau normalize.

```python
def normalize_sparql(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = s.lower()  # case-insensitive (SPARQL keywords)
    return s

def exact_match(pred, gold):
    return normalize_sparql(pred) == normalize_sparql(gold)
```

**(b) Execution Accuracy (ExecAcc)** — chạy cả 2 SPARQL trên Fuseki, compare result sets.

```python
def execution_accuracy(pred_sparql, gold_sparql, endpoint):
    try:
        pred_result = run_query(pred_sparql, endpoint, timeout=30)
    except Exception:
        return False
    try:
        gold_result = run_query(gold_sparql, endpoint, timeout=30)
    except Exception:
        # Should not happen on gold
        return False
    return canonicalize(pred_result) == canonicalize(gold_result)

def canonicalize(result):
    """Sort rows, remove ORDER-dependent diffs unless query has ORDER BY."""
    # Hash each row, sort by hash, return tuple.
    rows = [tuple(sorted(row.items())) for row in result]
    return frozenset(rows)
```

**(c) Answer F1** — F1 trên set rows (cho queries không SELECT trả lại đúng số row).

```python
def answer_f1(pred_rows, gold_rows):
    pred_set = canonicalize_rows(pred_rows)
    gold_set = canonicalize_rows(gold_rows)
    if not pred_set and not gold_set:
        return 1.0
    if not pred_set or not gold_set:
        return 0.0
    tp = len(pred_set & gold_set)
    p = tp / len(pred_set)
    r = tp / len(gold_set)
    return 2*p*r/(p+r) if (p+r) > 0 else 0.0
```

### Dimension 2: Latency

Đã đo trong inference logs. Report:
- Median, P50, P95, P99.
- Stratified by difficulty (Hard có thể slower).

### Dimension 3: Cost

- B0/B1/B2/B3: cost = 0 (local). (Có thể đo electricity nếu rigorous nhưng skip.)
- B4/B5: cost từ OpenRouter logs.
- Report: cost per 1k queries.

```python
def cost_per_1k(predictions):
    total_cost = sum(p["cost"] for p in predictions)
    n = len(predictions)
    return total_cost / n * 1000
```

### Dimension 4: Privacy (qualitative)

Không phải metric số. Tạo bảng đánh giá:

| Baseline | Data leaves device? | PII risk | Use cases viable |
|---|---|---|---|
| B0 | No | None | All (forensic, AML, internal) |
| B1/B2/B3/Full | No | None | All |
| B4/B5 (API) | Yes (to provider) | High | Research only |

Document trong thesis chapter.

### Dimension 5: Reproducibility

Run baseline 3 lần (với same input, temp=0). Compute:

```python
def reproducibility_score(runs):
    # runs: List[List[str]] — list of predictions over runs
    n = len(runs)
    matches = 0
    total = 0
    for i in range(n):
        for j in range(i+1, n):
            for p1, p2 in zip(runs[i], runs[j]):
                if normalize_sparql(p1) == normalize_sparql(p2):
                    matches += 1
                total += 1
    return matches / total
```

API-based baselines có thể có variance dù temp=0 (server-side stochasticity).

### Dimension 6: Failure mode classification

Phân loại lỗi cho mỗi prediction sai:

```python
class FailureType(Enum):
    SYNTAX = "syntax_error"           # SPARQL không parse
    HALLUCINATION = "hallucination"   # dùng prefix/property không tồn tại
    SCHEMA = "wrong_schema"           # property sai (e.g. :hasFrom vs :initiatedBy)
    LOGIC = "logic_error"             # đúng schema nhưng sai logic (filter sai, join sai)
    SEMANTIC = "semantic_drift"       # query khác hoàn toàn ý câu hỏi
    EMPTY = "no_output"               # model không generate được

def classify_failure(pred, gold, ontology, endpoint):
    if not pred:
        return FailureType.EMPTY
    try:
        ast = parse_sparql(pred)
    except SPARQLSyntaxError:
        return FailureType.SYNTAX
    used_uris = extract_uris(ast)
    if any(u not in ontology.uris for u in used_uris):
        return FailureType.HALLUCINATION
    # Run pred. Compare structure with gold.
    if execution_accuracy(pred, gold, endpoint):
        return None  # success
    # Compare property usage
    if used_props(ast) != used_props(parse_sparql(gold)):
        return FailureType.SCHEMA
    # Compare filter clauses
    if filters(ast) != filters(parse_sparql(gold)):
        return FailureType.LOGIC
    return FailureType.SEMANTIC
```

### Stratified report

Per difficulty (Easy/Medium/Hard) + per category:

```
| Baseline | All EM | All ExecAcc | Easy ExecAcc | Med ExecAcc | Hard ExecAcc |
|----------|--------|-------------|--------------|-------------|--------------|
| B0       | 28%    | 35%         | 70%          | 30%         | 5%           |
| B1       | 15%    | 32%         | 60%          | 35%         | 10%          |
| B2       | 22%    | 45%         | 72%          | 50%         | 18%          |
| B4       | 35%    | 65%         | 85%          | 70%         | 35%          |
| B5       | 40%    | 70%         | 88%          | 75%         | 40%          |
| B3 (FT)  | 38%    | 60%         | 82%          | 65%         | 30%          |
| Full     | 50%    | 78%         | 92%          | 82%         | 55%          |
```

(Numbers placeholder — actual sẽ fill sau.)

### Bootstrap CI

```python
def bootstrap_ci(scores, n=1000, alpha=0.05):
    boots = [np.mean(np.random.choice(scores, len(scores), replace=True))
             for _ in range(n)]
    lo = np.percentile(boots, 100*alpha/2)
    hi = np.percentile(boots, 100*(1-alpha/2))
    return lo, hi
```

### CLI

```bash
python -m src.evaluation.report \
  --predictions data/eval/predictions/b1_test.jsonl \
  --gold data/dataset/test/test-100.jsonl \
  --baseline b1 \
  --output data/eval/results/b1_metrics.json
```

## Rủi ro & note

- **Result canonicalization:** SPARQL result order phụ thuộc ORDER BY. Nếu không có ORDER BY → set comparison; nếu có → list comparison. Detect tự động từ AST.
- **Timeout queries:** một số gold queries cũng slow → tăng timeout 60s. Mark "timeout" → không count vào denominator.
- **Floating point trong values:** "1.0" vs "1.00" — round to 6 decimals khi compare.
- **DataType mismatch:** SPARQL trả `xsd:integer` vs `xsd:decimal` — normalize datatype trong canonicalize.

## Estimated effort

3 ngày (framework lớn).

## Trạng thái

todo
