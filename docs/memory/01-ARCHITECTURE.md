# 01 — Architecture

## Active inference pipeline

```text
Question (English/Vietnamese)
        │
        ├─ Schema linker → tables, fields, join paths
        ├─ Entity linker → aliases, addresses, entity evidence
        └─ Class resolver → typed constraints and coverage
        │
        ▼
Small LLM generator (B1/B2/B3)
        │  question + analytical catalog + linking context
        ▼
GoogleSQL candidate
        │
        ├─ SQLGlot parse/canonicalize
        ├─ read-only and managed-relation allowlist
        ├─ BigQuery dry-run
        └─ per-query and aggregate byte/cost caps
        ▼
BigQuery execution → result + provenance + latency/failure trace
```

B1 không có examples; B2 thêm đúng năm examples do retriever đã pin chọn; B3
dùng cùng contract đầu vào/đầu ra sau QLoRA. B0 là lower-bound deterministic và
đi qua cùng validator/evaluator. Không có remote-model fallback.

## Training-data pipeline

```text
Accepted Stage A (SQL/slots/provenance immutable)
        +
Finite bilingual catalog (25 intents × 2 languages × 4 styles)
        │  deterministic rendering; no model/network/API
        ▼
8 variants per semantic family
        │  semantic checks + diversity gate
        ▼
Hash-only held-out exclusion
        │  exact + normalized n-gram leakage checks
        ▼
Family-aware train/development split
        │  audit 100 records/language
        ▼
Atomic canonical artifact + manifest
```

Stage A v2 hiện là candidate 25/25 intent; publication fail closed cho đến khi
có genuine BigQuery verification cho 1.000/1.000 records với zero cache hits.
Benchmark English đã finalized; Vietnamese draft vẫn chờ user review. Producer
chỉ nhận exclusion hashes, không nhận raw benchmark wording.

## Module boundaries

```text
src/nl2sparql/
├── sql/            # analytical catalog, GoogleSQL rendering/canonicalization
├── linking/        # schema, entity and class resolution
├── dataset/        # Stage A, deterministic bilingual corpus, leakage/audit
├── models/
│   ├── b0/         # rule-based baseline
│   └── b12/        # small-LLM zero/five-shot contracts and adapters
├── evaluation/     # canonical predictions, execution evidence, reports
├── validation/     # SQL safety, dry-run and recovery
└── demo/           # Gradio orchestration
```

Phase 6 bổ sung B3/fine-tuning và constrained generation sau quyết định T5.5.
Plan A modules KG/RML/Fuseki được giữ riêng để tái lập negative result, không nằm
trên active inference path.

## Deployment

- **Primary:** local/Kaggle với đúng small model đã pin.
- **Optional showcase:** HF Spaces chỉ khi đủ tài nguyên để giữ đúng model hoặc
  trình bày demo tĩnh trung thực. Không thay bằng model qua API.
