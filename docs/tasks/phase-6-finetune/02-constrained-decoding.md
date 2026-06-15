# T6.2 — Constrained Decoding (Grammar-Based SPARQL Generation)

## Mục tiêu

Áp dụng constrained decoding (grammar-based) lên LLM generation để **đảm bảo output luôn là SPARQL syntactically valid**. Loại bỏ failure mode "syntax error" hoàn toàn.

## Bối cảnh & lý do

Phân tích failure mode (T5.4) sẽ show: 5-15% predictions là syntax error. Constrained decoding giải quyết được 100% lỗi này by design.

Library options:
- **Outlines** (preferred) — Lark grammar.
- **lm-format-enforcer** — token mask based.
- **guidance** (Microsoft) — alternative.

Áp dụng cho B1, B2, B3 (B4/B5 không vì OpenRouter API không support custom grammar).

## Phụ thuộc

- T6.1 — B3 model checkpoint (chính).
- T5.2 — B1/B2 inference code (apply lên đó cho fairness compare).

## Đầu vào

- LLM (Llama 3 8B local hoặc adapter).
- SPARQL grammar (W3C SPARQL 1.1 BNF, simplified).
- Test set.

## Đầu ra

- Module `src/nl2sparql/models/constrained_decoder.py`.
- File grammar `src/nl2sparql/decoding/grammars/sparql.lark`.
- Predictions với constrained decoding `data/eval/predictions/<baseline>_constrained_test.jsonl`.
- Comparison report `docs/eval/constrained_vs_free.md`.

## Acceptance criteria

- [ ] Grammar parse 100% gold SPARQL trong dataset (nếu fail, grammar incomplete).
- [ ] Constrained inference: 0% syntax errors trên test set.
- [ ] Latency overhead <2x so với free decoding.
- [ ] So sánh accuracy: constrained có cải thiện total Exec Acc ≥3% (hoặc ngang, không xấu hơn).

## Hướng dẫn triển khai

### Outlines setup

```python
from outlines import models, generate

model = models.transformers(
    "meta-llama/Meta-Llama-3-8B-Instruct",
    device="cuda",
    model_kwargs={"quantization_config": bnb_config},
)

# Or for B3 with LoRA: load PeftModel, then wrap.
```

### SPARQL grammar (simplified, đủ cho dataset)

File `src/nl2sparql/decoding/grammars/sparql.lark`:

```lark
?query: prologue (select_query | construct_query | ask_query)

prologue: prefix_decl*
prefix_decl: "PREFIX" CNAME ":" "<" URI ">"

select_query: "SELECT" select_modifier? select_vars where_clause solution_modifier?
select_modifier: "DISTINCT" | "REDUCED"
select_vars: VAR+ | "*"

where_clause: "WHERE"? "{" group_pattern "}"

group_pattern: triple_pattern (("." | ";")? triple_pattern)* "."?
             | filter_clause
             | optional_clause
             | bind_clause
             | values_clause
             | union_clause

triple_pattern: term term term
term: VAR | iri_ref | literal | prefixed_name
prefixed_name: CNAME ":" CNAME?

filter_clause: "FILTER" "(" expr ")"
expr: arith_expr | bool_expr | function_call
arith_expr: term op term
op: ">" | "<" | ">=" | "<=" | "=" | "!="
bool_expr: expr ("&&" | "||") expr

optional_clause: "OPTIONAL" "{" group_pattern "}"
union_clause: group_pattern "UNION" group_pattern
bind_clause: "BIND" "(" expr "AS" VAR ")"
values_clause: "VALUES" VAR "{" iri_ref+ "}"

solution_modifier: order_clause? limit_clause? offset_clause?
order_clause: "ORDER" "BY" (("ASC" | "DESC") "(" VAR ")" | VAR)+
limit_clause: "LIMIT" INT
offset_clause: "OFFSET" INT

VAR: /\?[a-zA-Z_][a-zA-Z0-9_]*/
URI: /[^>]+/
INT: /\d+/
literal: STRING | NUMBER | BOOLEAN | DATETIME
STRING: /"[^"]*"/
NUMBER: /-?\d+(\.\d+)?/
...
```

Test grammar:
```python
from lark import Lark
parser = Lark.open("src/nl2sparql/decoding/grammars/sparql.lark", start="query")
for rec in train_dataset:
    parser.parse(rec["sparql"])  # should not raise
```

Iterate grammar đến khi 100% gold parse được.

### Generate với grammar

```python
from outlines import generate

generator = generate.cfg(model, grammar)

def predict_constrained(nl, ontology_summary):
    prompt = build_prompt(nl, ontology_summary)
    result = generator(prompt, max_tokens=512)
    return result
```

### Fallback strategy

Nếu grammar fails on edge case (rare):
- Catch exception → fallback to free decoding.
- Log để fix grammar later.

### Latency optimization

Constrained decoding có overhead. Tips:
- Cache grammar compilation.
- Batch generate nếu possible (Outlines supports).
- Sử dụng KV cache aggressively.

### Comparison framework

So sánh từng baseline với và không constrained:

| Baseline | Free SyntaxErr | Free ExecAcc | Constr SyntaxErr | Constr ExecAcc |
|---|---|---|---|---|
| B1 | 12% | 32% | 0% | 35% |
| B2 | 8% | 45% | 0% | 47% |
| B3 | 5% | 60% | 0% | 62% |
| Full | 3% | 75% | 0% | 78% |

(Numbers placeholder.)

### When constrained doesn't help

Nếu output đã ít syntax error (B3 fine-tuned ~5%), gain marginal.
Nhưng B1/B2 có gain to lớn.
Document finding này trong thesis.

## Rủi ro & note

- **Grammar incomplete:** một số gold SPARQL có syntax phức tạp (property paths, subqueries). Start với basic, add features iteratively.
- **Outlines + Llama 3 chat template:** có thể conflict. Thử `outlines.generate.text` mode đầu, sau đó cfg mode.
- **OOM với grammar:** grammar tăng VRAM ~10%. Giảm batch size nếu cần.
- **Property path support:** SPARQL `?x rdf:type/rdfs:subClassOf* :Class` rất hữu ích nhưng grammar phức tạp. Defer if needed.

## Estimated effort

2 ngày.

## Trạng thái

todo
