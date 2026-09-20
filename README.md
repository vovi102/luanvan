# NL2SQL Blockchain KG

> **Trang thai:** Pivot #1 da chuyen target active sang NL2SQL tren BigQuery (2026-08-09).
>
> **De tai ban dau:** Natural-language blockchain analytics trên Knowledge Graph
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

## T5.3 B4/B5 GoogleSQL large-LLM

T5.3 dùng model `meta-llama/llama-3.3-70b-instruct`: B4 zero-shot và B5
few-shot đúng năm examples do B2 retriever chọn. Hai baseline dùng chung
catalog/prompt/extraction GoogleSQL của B1/B2. Provider được pin và không
fallback; hard budget là USD 20 tối đa theo reservation trước request. Xem
chi tiết acceptance và artifact tại
`docs/tasks/phase-5-baselines/03-b4-b5-large-llm.md`.

Lệnh preflight offline sau đây chỉ kiểm tra catalog/config local, không đọc API
key, không khởi tạo client và không mở network:

```bash
uv run python scripts/generate_b45_local_verification.py
uv run python scripts/18_large_llm_baselines.py validate \
  --baseline b4 \
  --provider deepinfra \
  --max-cost-usd 20
```

Lệnh generator chạy lại focused/full pytest, Ruff check/format, CLI help và
offline validate rồi mới ghi manifest canonical
`docs/evidence/t5-3-local-verification.json`. Manifest ràng buộc SHA-256 của
module B45, workflow/wrapper, B45 tests và cấu hình Python; thay đổi bất kỳ đầu
vào nào làm `local_implementation_ready=false` cho đến khi toàn bộ gate được
chạy lại thành công. Generator không gọi OpenRouter.

`validate` cũng kiểm tra sidecar privacy cục bộ nếu có; khi sidecar chưa có,
JSON kết quả giữ blocker `privacy_review_missing` để nhắc gate bên ngoài mà
không chặn preflight offline. Sidecar mặc định là
`<test-set>.privacy.json`; có thể chọn bằng `--privacy-review`.

Ví dụ live dưới đây chỉ là thao tác thủ công có chủ đích; nó **không bao giờ
được chạy tự động**. Cần tự cấp key, metadata fingerprint đã chấp nhận và
đồng ý phát sinh chi phí trước khi thêm `--allow-network`:

```bash
export OPENROUTER_API_KEY
uv run python scripts/18_large_llm_baselines.py predict \
  --baseline b4 \
  --question "List known Ethereum addresses" \
  --provider deepinfra \
  --max-cost-usd 20 \
  --accepted-model-metadata-sha256 <64-lowercase-hex-sha256> \
  --allow-network
```

`predict` không publish artifact. Evaluation dùng `evaluate --run-id ...`
với `--test-set`, `--predictions`, `--request-log`, `--cost-log`, `--report`
và `--resume`; `summarize` nhận đúng ba cặp `--report`/`--request-log` và vẫn
offline. Live `predict` và `evaluate` bắt buộc truyền tường minh
`--max-cost-usd` (không có mặc định USD 20), và live `evaluate` bắt buộc
`--accepted-privacy-review-sha256` khớp chính xác sidecar với snapshot test.
Mỗi lần retry giữ liability reservation riêng; failure/cancellation được ghi
vào checkpoint để resume không bỏ mất chi phí chưa rõ. Không có lệnh README
nào tự chạy live inference.

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
│   ├── validation/             # Legacy graph validation va recovery
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
