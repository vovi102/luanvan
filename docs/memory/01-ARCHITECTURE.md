# 01 — Architecture

## Pipeline xử lý câu hỏi (inference)

```
User question (English)
        │
        ▼
┌─────────────────────────┐
│  Schema Linker          │  sentence-transformers MiniLM
│                         │  + property documentation embeddings
│  → ranked properties    │  → Top-K properties được "kích hoạt"
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  Entity Linker          │  Hierarchical dictionary
│                         │  4-stage matching:
│  → entity URIs          │   A. Exact (case-insensitive)
│    + class hints        │   B. Fuzzy (Levenshtein ≥ 0.85)
└─────────────────────────┘   C. Embedding (cosine ≥ 0.75)
        │                     D. Fallback: clarify
        ▼
┌─────────────────────────┐
│  LLM Generator          │  Llama 3 8B Instruct, QLoRA fine-tuned
│                         │  Prompt: question + linked schema/entities
│  → SPARQL candidate     │  Constrained decoding (grammar-based)
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  Validator              │  1. Syntax check (rdflib)
│                         │  2. Schema check (predicates exist?)
│                         │  3. Dry-run on KG (timeout 5s)
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  Apache Jena Fuseki     │  SPARQL endpoint :3030
│                         │
│  → Result rows          │
└─────────────────────────┘
        │
        ▼
   User-facing output
   (table + provenance)
```

## Pipeline xây Knowledge Graph (one-shot)

```
BigQuery Ethereum public dataset
   - bigquery-public-data.crypto_ethereum.transactions
   - bigquery-public-data.crypto_ethereum.blocks
   - bigquery-public-data.crypto_ethereum.token_transfers
   - bigquery-public-data.crypto_ethereum.contracts
        │
        ▼  SQL extraction (1 tháng dữ liệu)
   CSV files (local, ~vài GB)
        │
        ▼  RML mapping (rules.ttl)
        │  Tool: Morph-KGC (ưu tiên) hoặc RMLMapper
   ethereum-kg.ttl (Turtle, ~5-10GB raw)
        │
        ▼  TDB2 indexing
   Apache Jena Fuseki (local, port 3030)
        │
        ▼
   SPARQL endpoint sẵn sàng
```

## Tách module — repo structure

```
src/nl2sparql/
├── kg/                       # Phase 1+2: KG construction
│   ├── bigquery_extractor.py
│   ├── rml_runner.py
│   ├── fuseki_client.py
│   └── shacl_validator.py
│
├── linking/                  # Phase 4: linkers
│   ├── schema_linker.py
│   ├── entity_linker.py
│   ├── class_resolver.py
│   └── entity_dictionary.py
│
├── dataset/                  # Phase 3: NL-SPARQL pipeline
│   ├── templates.py
│   ├── synthesizer.py
│   ├── paraphraser.py
│   ├── noise.py
│   └── validator.py
│
├── models/                   # Phase 5+6: baselines & main model
│   ├── rule_based.py
│   ├── llm_zero_shot.py
│   ├── llm_few_shot.py
│   ├── llm_finetuned.py
│   └── full_system.py
│
├── decoding/                 # Phase 6: constrained decoding
│   ├── constrained.py
│   ├── grammar.py
│   └── grammars/
│
├── validation/               # Phase 7: post-validation + recovery
│   ├── sparql_parser.py
│   ├── ontology_validator.py
│   └── post_validator.py
│
├── evaluation/               # Phase 5: evaluation framework
│   ├── metrics.py
│   ├── runner.py
│   └── analyzer.py
│
└── demo/                     # Phase 7: Gradio app
    ├── app.py
    └── examples.py

ontology/                     # Ontology TTL, SHACL shapes, examples
mappings/                     # RML mapping rules
scripts/                      # CLI orchestration scripts
data/                         # Không commit dữ liệu lớn
docs/                         # Memory, tasks, thesis, literature
notebooks/                    # Kaggle/Colab notebooks (mirror)
```

## Decision points đáng nhớ

- **TDB2 vs in-memory Fuseki:** dùng TDB2 (persistent, query nhanh hơn cho >1M triples).
- **Morph-KGC vs RMLMapper:** ưu tiên Morph-KGC (Python-friendly, dễ debug); fallback RMLMapper nếu Morph-KGC bug.
- **Llama 3 8B vs Mistral 7B:** ưu tiên Llama 3 8B Instruct (license rõ, ecosystem rộng); benchmark Mistral 7B nếu còn thời gian.
- **OpenRouter cho LLM lớn:** tránh lock vào 1 API; rotate giữa Llama 3 70B / Mistral Large / Qwen2 72B.

## Two-tier deployment

- **Tier 1 — Local notebook/Kaggle:** mô hình + Fuseki chạy local, không giới hạn.
- **Tier 2 — Hugging Face Spaces:** demo công khai, KG nhỏ (~10% dữ liệu), không có Fuseki Java; dùng rdflib in-memory.

Lý do: HF Spaces free tier không support Java/Fuseki bền vững. Tier 2 chỉ để showcase, không phải full system.
