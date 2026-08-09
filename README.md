# NL2SPARQL Blockchain KG

> **Trang thai:** Pivot #1 da chuyen target active sang NL2SQL tren BigQuery (2026-08-09).
>
> **De tai ban dau:** NL2SPARQL cho Blockchain Knowledge Graph Analytics
>
> **Thoi luong:** 6.5 thang  
> **Dau ra active:** luan van thac si, dataset NL-SQL, source code pipeline, demo Gradio/HF Spaces

## Muc tieu

Nguoi dung hoi bang tieng Anh ve du lieu Ethereum; he thong thuc hien
schema/entity linking, sinh Standard SQL co guard chi phi, chay tren BigQuery va
tra ket qua co provenance. Full KG/Fuseki duoc giu nhu artifact va negative
finding cua Plan A.

## Setup nhanh

Project dung `uv` de quan ly Python environment va dependency.

```bash
uv sync
uv run pytest -q
uv run ruff check src tests
uv run python -c "import nl2sparql; print(nl2sparql.__name__)"
```

Neu can tach cache/Python managed vao trong repo khi chay local:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv sync
```

Du lieu lon va artifact train/KG khong commit vao git. Xem `.gitignore` va `docs/memory/04-CONVENTIONS.md`.

## Cau truc thu muc

```text
.
├── README.md
├── configs/                    # YAML config cho KG build, train, eval, demo
├── data/                       # Du lieu local, khong commit file lon
│   ├── raw/                    # CSV extract tu BigQuery
│   ├── interim/                # Artifact trung gian
│   ├── processed/              # Dataset/output da xu ly
│   ├── kg/                     # TDB2 indexes, TTL lon
│   ├── entities/               # Entity dictionary artifacts
│   └── samples/                # Mau nho co the commit
├── docs/
│   ├── memory/                 # Context lau dai cho agent/project
│   ├── tasks/                  # Backlog theo phase
│   ├── planning/               # Ke hoach trien khai chi tiet
│   ├── architecture/           # Diagram va note kien truc
│   ├── literature/             # Paper notes
│   ├── thesis/                 # Ban thao luan van
│   └── figures/                # Hinh ve, bang bieu
├── infrastructure/
│   ├── docker/                 # Docker/Fuseki compose
│   ├── kaggle/                 # Notebook/config train tren Kaggle
│   └── hf_spaces/              # Asset deploy Hugging Face Spaces
├── mappings/                   # RML mapping rules
├── notebooks/                  # Notebook prototype; logic on dinh dua ve src/
├── ontology/                   # Ontology TTL, SHACL shapes, examples
├── scripts/                    # CLI orchestration scripts
├── src/nl2sparql/              # Python package chinh
│   ├── kg/                     # BigQuery extract, RML, Fuseki, SHACL
│   ├── linking/                # Schema/entity/class linkers
│   ├── dataset/                # Template, synthetic, paraphrase, noise
│   ├── models/                 # Baselines, fine-tuned model, full system
│   ├── decoding/               # Grammar/constrained decoding
│   ├── validation/             # SPARQL validation va recovery
│   ├── evaluation/             # Metrics, runner, analysis
│   └── demo/                   # Gradio app
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

## Tai lieu dieu huong

Doc theo thu tu:

1. `docs/memory/00-PROJECT_OVERVIEW.md` - muc tieu, scope, research questions.
2. `docs/memory/01-ARCHITECTURE.md` - pipeline va module boundaries.
3. `docs/memory/02-TECH_STACK.md` - stack cong nghe duoc chon.
4. `docs/memory/04-CONVENTIONS.md` - quy uoc code, data, commit.
5. `docs/tasks/` - backlog trien khai theo phase.

## Quy trinh lam task

Truoc khi bat dau task:

1. Doc `docs/memory/00-PROJECT_OVERVIEW.md` va `docs/memory/04-CONVENTIONS.md`.
2. Doc task file trong `docs/tasks/` va cac phu thuoc cua no.
3. Kiem tra `docs/memory/05-DECISION_LOG.md`.
4. Neu cham ontology/schema, doc `docs/memory/03-ONTOLOGY_REFERENCE.md`.

Sau khi hoan thanh task:

1. Cap nhat `## Trang thai` trong task file.
2. Ghi decision quan trong vao `docs/memory/05-DECISION_LOG.md`.
3. Neu doi ontology/schema, cap nhat `docs/memory/03-ONTOLOGY_REFERENCE.md`.

## Pivot points

- **Pivot #1 (2026-08-09):** da chuyen sang Plan B NL2SQL sau khi full-KG
  benchmark kich hoat NO-GO latency. Xem `docs/pivot-decision-1.md` va
  `docs/plan-b-adjustments.md`.
- **Pivot #2:** sau Phase 5, scope down neu baseline qua yeu hoac timeline khong con an toan. Xem `docs/tasks/phase-5-baselines/05-pivot-decision.md`.
