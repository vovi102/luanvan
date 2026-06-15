# T7.1 — Validator + Error Recovery

## Mục tiêu

Module `Validator` chạy 3 check trên SPARQL output trước khi submit lên Fuseki:
1. **Syntax check** — parse bằng rdflib.
2. **Schema check** — predicates/classes có tồn tại trong ontology không.
3. **Dry-run** — chạy với `LIMIT 1` + timeout 5s để verify endpoint không reject.

Nếu fail → trigger error recovery (re-prompt LLM với error hint, retry tối đa 1 lần).

## Bối cảnh & lý do

Validator + recovery là phần "production-ready" của hệ thống. Demo dùng được phải có cơ chế "không crash" khi LLM generate bad output.

Cũng là phần thứ 2 của **đóng góp 2 (linking + validation)**.

## Phụ thuộc

- T2.1 — Ontology (để check predicate/class).
- T6.1+T6.2 — Pipeline B3 + constrained decoding.
- Fuseki running.

## Đầu vào

- SPARQL string từ LLM.
- Ontology (loaded once).
- Fuseki endpoint URL.

## Đầu ra

- Module `src/nl2sparql/validation/validator.py`.
- Module `src/nl2sparql/validation/recovery.py`.
- Tests `tests/test_validator.py` ≥15 cases.
- Notebook `notebooks/15_validator_demo.ipynb`.

## Acceptance criteria

- [ ] API: `Validator.validate(sparql) -> ValidationResult` với detailed error.
- [ ] Recovery: `Pipeline.predict_with_recovery(nl) -> SparqlResult` retry tối đa 1 lần.
- [ ] Test: 5 cases mỗi loại lỗi (syntax, schema, dry-run timeout).
- [ ] Latency overhead validator <300ms (parse + schema check).
- [ ] Recovery success rate ≥40% trên cases có lỗi.

## Hướng dẫn triển khai

### ValidationResult schema

```python
@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError]
    warnings: list[str]
    parsed_ast: Optional[Any]  # rdflib parsed query

@dataclass
class ValidationError:
    type: Literal["syntax", "unknown_predicate", "unknown_class", "domain_mismatch", "dry_run_timeout", "dry_run_error"]
    message: str
    location: Optional[str]  # offset hoặc node trong AST
    suggestion: Optional[str]  # gợi ý cho LLM
```

### Stage 1: Syntax check

```python
from rdflib.plugins.sparql import prepareQuery

def check_syntax(sparql):
    try:
        ast = prepareQuery(sparql)
        return None, ast
    except Exception as e:
        return ValidationError(
            type="syntax",
            message=str(e),
            suggestion="Fix SPARQL syntax. Check braces, dots, prefix declarations."
        ), None
```

### Stage 2: Schema check

Extract URIs từ AST, kiểm tra trong ontology:

```python
def check_schema(ast, ontology):
    errors = []
    used_uris = extract_uris_from_ast(ast)

    for uri in used_uris:
        if is_predicate_position(uri, ast):
            if uri not in ontology.properties:
                # Find similar via Levenshtein
                similar = find_closest_property(uri, ontology, top_k=3)
                errors.append(ValidationError(
                    type="unknown_predicate",
                    message=f"Predicate {uri} not in ontology",
                    suggestion=f"Did you mean: {', '.join(similar)}?"
                ))
        elif is_class_position(uri, ast):
            if uri not in ontology.classes:
                similar = find_closest_class(uri, ontology, top_k=3)
                errors.append(ValidationError(
                    type="unknown_class",
                    message=f"Class {uri} not in ontology",
                    suggestion=f"Did you mean: {', '.join(similar)}?"
                ))

    # Optional: check domain/range
    for triple in extract_triples(ast):
        s, p, o = triple
        if p in ontology.properties:
            domain = ontology.properties[p].get("domain")
            range_ = ontology.properties[p].get("range")
            # Domain/range check (limited — only if subj has explicit type triple)
            ...

    return errors
```

### Stage 3: Dry-run

```python
def check_dry_run(sparql, endpoint, timeout=5):
    # Inject LIMIT 1 if not present (safe for SELECT only)
    sparql_dry = inject_limit_1(sparql)
    try:
        result = run_sparql(sparql_dry, endpoint, timeout=timeout)
        return None  # OK
    except TimeoutError:
        return ValidationError(
            type="dry_run_timeout",
            message=f"Query exceeded {timeout}s on dry-run",
            suggestion="Query may be too expensive. Add filters to narrow scope."
        )
    except Exception as e:
        return ValidationError(
            type="dry_run_error",
            message=str(e),
            suggestion="Check syntax and schema again."
        )
```

`inject_limit_1` carefully:
- SELECT: append `LIMIT 1` nếu không có.
- ASK: skip (already returns 1 boolean).
- CONSTRUCT/DESCRIBE: skip dry-run (or use `LIMIT 1` trong WHERE).

### Recovery loop

```python
def predict_with_recovery(nl, max_retries=1):
    sparql = pipeline.predict(nl)
    val = validator.validate(sparql)

    if val.valid:
        return run_sparql(sparql, endpoint), val

    if max_retries == 0:
        # Return error response with explanation
        return None, val

    # Retry with error hint in prompt
    error_hints = "\n".join([
        f"Previous attempt error: {e.message}. Suggestion: {e.suggestion}"
        for e in val.errors
    ])
    retry_prompt = build_retry_prompt(nl, sparql, error_hints)
    sparql_retry = pipeline.predict_raw(retry_prompt)
    val_retry = validator.validate(sparql_retry)

    if val_retry.valid:
        return run_sparql(sparql_retry, endpoint), val_retry

    return None, val_retry
```

### Retry prompt template

```python
RETRY_PROMPT = """The previous SPARQL had errors:
{error_hints}

Previous SPARQL:
{previous_sparql}

Please fix the errors and provide a corrected SPARQL query.

Question: {nl}

Corrected SPARQL:"""
```

### Test cases

Mỗi loại lỗi cần test:

```python
# Syntax error
"SELECT ?x WHERE { ?x :hasFrom ?y" → missing brace

# Unknown predicate
"SELECT ?x WHERE { ?x :nonexistent ?y }" → :nonexistent not in ontology

# Unknown class
"SELECT ?x WHERE { ?x a :NotAClass }" → :NotAClass not in ontology

# Dry-run timeout (deliberately bad query)
"SELECT * WHERE { ?a ?b ?c . ?c ?d ?e . ?e ?f ?g . ?g ?h ?i }" → cartesian product

# OK case
"SELECT ?tx WHERE { ?tx a :Transaction } LIMIT 10" → valid
```

### Recovery effectiveness measurement

Trên test set:
- Đếm số queries cần recovery.
- Tỉ lệ recovery thành công.
- Average final accuracy comparison.

Báo cáo trong thesis như "engineering contribution".

## Rủi ro & note

- **Schema check false positive:** SPARQL có thể dùng property ngoài ontology như `rdf:type`, `rdfs:subClassOf` — cần whitelist standard prefixes (rdf, rdfs, xsd, owl).
- **Dry-run quá strict:** một số valid queries chậm hơn 5s. Tăng lên 10s nếu trên KG full.
- **Retry không converge:** LLM có thể repeat lỗi. Cap retries=1.
- **`prepareQuery` chấp nhận một số non-standard syntax:** test trên multiple parsers (rdflib + Fuseki) để đồng nhất.

## Estimated effort

2 ngày.

## Trạng thái

todo
