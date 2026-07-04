# T2.5 — SHACL Validation cho KG

## Mục tiêu

Viết SHACL shapes describe constraint cho KG, chạy validation, fix các vi phạm.

## Bối cảnh & lý do

Đảm bảo data quality của KG: mọi tx có from/to/value/timestamp; mọi địa chỉ có nhãn nếu được claim là exchange/mixer; range datatype đúng.

## Phụ thuộc

- T2.4 — KG đã load.

## Đầu vào

- Ontology `eth-kg-extension-v0.1.0.ttl`.
- KG dataset `eth-kg` ở Fuseki.

## Đầu ra

- File `src/nl2sparql/kg/validation/shapes.ttl` chứa SHACL shapes.
- File `src/nl2sparql/kg/validation/run_shacl.py` chạy validation.
- File `data/processed/full/shacl_report.ttl` chứa validation report.
- Bảng tóm tắt vi phạm trong `src/nl2sparql/kg/validation/violations_summary.md`.

## Acceptance criteria

- [ ] Shapes file parse được, viết theo SHACL Core.
- [ ] Validation chạy hoàn tất trên KG, không crash.
- [ ] ≤1% vi phạm critical (missing required property).
- [ ] Tất cả vi phạm được phân loại + có plan handle (fix data hoặc relax shape).

## Local automation scaffold

- [x] `src/nl2sparql/kg/validation/shapes.ttl` parse được và dùng SHACL Core.
- [x] `src/nl2sparql/kg/validation/run_shacl.py` validate RDF local, ghi report TTL, và ghi markdown summary.
- [x] Fixture conforming/nonconforming trong `tests/fixtures/shacl/` cover transaction, block, account, exchange account, token transfer, và token contract.
- [x] Unit tests verify conforming graph pass, violating graph fail, summary grouping, CLI return code, và CLI `--allow-nonconform`.
- [x] Full KG validation vẫn pending cho đến khi T2.4 live materialization + TDB2 load hoàn tất.

## Hướng dẫn triển khai

### 1. Define shapes

`shapes.ttl`:

```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix : <https://thesis.example.org/eth-kg/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# ---------- Transaction shape ----------
:TransactionShape a sh:NodeShape ;
    sh:targetClass :Transaction ;

    sh:property [
        sh:path :hasFrom ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:class :Account ;
        sh:message "Every transaction must have exactly one :hasFrom Account."
    ] ;

    sh:property [
        sh:path :hasTo ;
        sh:maxCount 1 ;
        sh:class :Account ;
        sh:message "Transaction can have at most one :hasTo (NULL allowed for contract creation)."
    ] ;

    sh:property [
        sh:path :hasValue ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:decimal ;
        sh:minInclusive 0 ;
    ] ;

    sh:property [
        sh:path :hasTimestamp ;
        sh:minCount 1 ;
        sh:datatype xsd:dateTime ;
    ] .

# ---------- Account shape ----------
:AccountShape a sh:NodeShape ;
    sh:targetClass :Account ;

    sh:property [
        sh:path :hasLabel ;
        sh:datatype xsd:string ;
    ] .

# ---------- Exchange must have label + owner ----------
:ExchangeAccountShape a sh:NodeShape ;
    sh:targetClass :ExchangeAccount ;

    sh:property [
        sh:path :hasLabel ;
        sh:minCount 1 ;
        sh:message "ExchangeAccount must have :hasLabel."
    ] ;

    sh:property [
        sh:path :hasOwner ;
        sh:minCount 1 ;
        sh:message "ExchangeAccount must have :hasOwner (e.g. 'Binance')."
    ] .

# ---------- Token transfer shape ----------
:TokenTransferShape a sh:NodeShape ;
    sh:targetClass :TokenTransfer ;

    sh:property [
        sh:path :inTransaction ;
        sh:minCount 1 ;
    ] ;
    sh:property [
        sh:path :transferredFromAccount ;
        sh:minCount 1 ;
    ] ;
    sh:property [
        sh:path :transferredAmount ;
        sh:minCount 1 ;
        sh:datatype xsd:decimal ;
    ] .
```

### 2. Run validation

```python
# src/nl2sparql/kg/validation/run_shacl.py
from pyshacl import validate
from rdflib import Graph

# Load data + shapes
data_g = Graph()
data_g.parse("data/processed/full/output.nt", format="nt")  # hoặc query Fuseki

shapes_g = Graph()
shapes_g.parse("src/nl2sparql/kg/validation/shapes.ttl", format="turtle")

# Validate (warning: full graph có thể tốn nhiều RAM)
conforms, results_graph, results_text = validate(
    data_g,
    shacl_graph=shapes_g,
    inference="rdfs",  # apply RDFS inferences
    advanced=True,
)

# Save report
results_graph.serialize("data/processed/full/shacl_report.ttl", format="turtle")

print(f"Conforms: {conforms}")
print(results_text[:5000])  # truncate
```

### 3. Phân loại vi phạm

Query report:
```sparql
PREFIX sh: <http://www.w3.org/ns/shacl#>
SELECT ?path ?message (COUNT(*) AS ?n) WHERE {
  ?result a sh:ValidationResult ;
          sh:resultPath ?path ;
          sh:resultMessage ?message .
} GROUP BY ?path ?message ORDER BY DESC(?n)
```

Phân vào 3 loại:

- **Critical (fix bằng mọi giá):** schema sai (datatype, range), missing required property cho >1% nodes.
- **Acceptable (relax shape):** edge case của data thật (e.g. NULL `to_address` cho contract creation → shape phải `maxCount 1` không phải `minCount 1`).
- **Long-tail (fix opportunistically):** ít nodes vi phạm, có thể bỏ qua + document trong limitations.

### 4. Fix loop

Cho mỗi critical violation:

- Trace ngược về RML mapping (T2.4) hoặc CSV gốc.
- Fix RML/CSV.
- Re-materialize.
- Re-validate.

Iterate cho đến khi conform hoặc còn vi phạm acceptable + documented.

### 5. Document

`violations_summary.md` ví dụ:

```markdown
# SHACL Validation Summary

Date: 2025-XX-XX. Total triples: 50,432,103. Total violations: 8,234 (0.0163%).

## Critical (fixed)
- 142 Transaction missing `:hasValue` → root cause: pandas drop NULL khi save CSV; fix: keep `0` value rows.
- 8 Block với `:hasTimestamp` sai datatype → root cause: epoch int chưa convert; fix RML: cast với `xsd:dateTime`.

## Acceptable (shape relaxed)
- 5,234 Transaction với `:hasTo` cardinality 0 → contract creation; shape đổi từ `minCount 1` thành `maxCount 1`.

## Long-tail (documented)
- 2,850 ExchangeAccount thiếu `:hasOwner` → entity dictionary có address nhưng không owner cụ thể; documented in thesis as known limitation.
```

## Rủi ro & note

- **pyshacl chậm với 50M triples** (vài giờ). Có thể:
  - Sample 10% data → validate → cảnh báo nếu vi phạm rate > X%.
  - Hoặc validate per-class (load chỉ Transaction subset).
  - Hoặc dùng TopBraid SHACL Java (faster).
- **inference="rdfs"** apply subClassOf inference. Có thể tắt nếu chậm.
- **Báo cáo ban đầu sẽ rất nhiều vi phạm** — đừng panic. Phần lớn là long-tail.

## Estimated effort

1-2 ngày (đa phần fix loop).

## Trạng thái

`scaffold done; full KG validation pending`

Local scaffold đã hoàn tất để kiểm tra SHACL shapes bằng fixture RDF nhỏ. Acceptance criteria phía trên vẫn pending cho full KG vì chưa chạy validation trên `data/processed/full/output.nt` hoặc Fuseki dataset `eth-kg`.

## Evidence — 2026-07-04 Scaffold

- Branch: `feat/t2-5-shacl-validation`.
- Design/spec:
  - `docs/superpowers/specs/2026-07-04-t2-5-shacl-validation-design.md`
  - `docs/superpowers/plans/2026-07-04-t2-5-shacl-validation.md`
- Implemented files:
  - `src/nl2sparql/kg/validation/shapes.ttl`
  - `src/nl2sparql/kg/validation/run_shacl.py`
  - `tests/unit/test_shacl_validation.py`
  - `tests/fixtures/shacl/conforming.ttl`
  - `tests/fixtures/shacl/violating.ttl`
- Focused local verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_shacl_validation.py -q
  ```
  Result: `7 passed`.
- CLI help smoke:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run python src/nl2sparql/kg/validation/run_shacl.py --help
  ```
  Result: exit `0`.

## Next live evidence step

Run only after T2.4 live materialization creates `data/processed/full/output.nt`:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run python src/nl2sparql/kg/validation/run_shacl.py \
    --data data/processed/full/output.nt \
    --shapes src/nl2sparql/kg/validation/shapes.ttl \
    --report data/processed/full/shacl_report.ttl \
    --summary src/nl2sparql/kg/validation/violations_summary.md \
    --allow-nonconform
```

After live validation, record triple count, validation wall time, conformance status, critical violation rate, and planned fixes here.
