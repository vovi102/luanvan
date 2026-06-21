# T0.1 — Repo và Development Environment

## Mục tiêu

Khởi tạo repo Git, cấu hình môi trường Python bằng `uv`, đảm bảo có thể chạy `python -c "import torch; print(torch.__version__)"` thành công.

## Bối cảnh & lý do

Cần nền tảng repo trước khi làm bất kỳ task nào khác. Convention được mô tả ở `docs/memory/04-CONVENTIONS.md`.

## Phụ thuộc

- (không có)

## Đầu vào

- Tham khảo `docs/memory/04-CONVENTIONS.md` cho repo structure + .gitignore.
- Tham khảo `docs/memory/02-TECH_STACK.md` cho danh sách dependency.

## Đầu ra

- Repo Git public trên GitHub (link cập nhật vào `docs/memory/05-DECISION_LOG.md`).
- File `pyproject.toml` + `uv.lock` đã pin/resolved dependency chính.
- File `README.md` ở root với 1 đoạn giới thiệu + setup instructions.
- Cấu trúc thư mục theo `docs/memory/01-ARCHITECTURE.md`.
- Có thể chạy được:
  ```bash
  python -c "import torch, transformers, peft, rdflib, sentence_transformers"
  ```

## Acceptance criteria

- [x] `git clone <repo>` thành công.
- [x] `UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv sync` chạy hết không lỗi.
- [x] Smoke test ở trên (import) chạy được.
- [x] `uv run ruff check src tests` không báo lỗi.
- [x] `uv run pytest -q` chạy được.

## Hướng dẫn triển khai

1. Tạo repo trên GitHub. Tên gợi ý: `nl2sparql-blockchain-kg`.
2. License MIT (cho phép cite + reuse). Update DECISION_LOG.
3. Tạo cấu trúc thư mục:
   ```bash
   mkdir -p src/nl2sparql/{kg,linking,dataset,models,decoding,validation,evaluation,demo}
   mkdir -p configs ontology mappings scripts notebooks
   mkdir -p infrastructure/{docker,kaggle,hf_spaces}
   mkdir -p data/{raw,interim,processed,kg,entities,samples}
   mkdir -p docs/{memory,tasks,planning,architecture,literature,thesis,figures}
   mkdir -p tests/{unit,integration,fixtures}
   touch src/nl2sparql/__init__.py
   ```
4. Viết `pyproject.toml` cho `uv` (pin version range chính) và commit `uv.lock`.
5. Viết `.gitignore` theo `docs/memory/04-CONVENTIONS.md`.
6. Viết `README.md` rất ngắn (1 đoạn + setup instructions). Sẽ mở rộng sau.
7. Tạo `__init__.py` rỗng cho `src/nl2sparql/` và các subpackage.
8. Tạo file `tests/test_smoke.py`:
   ```python
   def test_imports():
       import torch  # noqa
       import transformers  # noqa
       import rdflib  # noqa
       import sentence_transformers  # noqa
   ```
9. Commit ban đầu: `chore: initial repo scaffold`.

## Rủi ro & note

- **bitsandbytes** chỉ chạy trên CUDA. Trên Mac/local CPU sẽ lỗi import → đó là OK, sẽ chạy trên Kaggle.
  - Để smoke test chạy được local: import bitsandbytes có thể bỏ qua bằng `try/except`.
- **morph-kgc** có thể conflict với `pandas` version cũ. Pin `pandas>=2.2` giải quyết.
- Dùng `uv sync` thay vì `pip install` để tái lập môi trường nhanh và nhất quán.

## Estimated effort

0.5 ngày.

## Trạng thái

`done — 2026-06-14`

Verification:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv sync
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest -q
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src tests
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run python -c "import torch, transformers, peft, rdflib, sentence_transformers; print(torch.__version__)"
```

Kết quả: `pytest` 2 passed, `ruff` all checks passed, full import smoke trả `torch==2.5.1+cu124`.
