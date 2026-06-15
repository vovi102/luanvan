# 04 — Conventions

## Repo structure (xem chi tiết ở `01-ARCHITECTURE.md`)

Top level:

```
.
├── README.md
├── configs/                 # YAML config cho KG build, train, eval, demo
├── data/                    # Dữ liệu local, KHÔNG commit file lớn
│   ├── raw/                 # CSV từ BigQuery
│   ├── interim/             # Artifact trung gian
│   ├── processed/           # Dataset/output đã xử lý
│   ├── kg/                  # TDB2 indexes, TTL lớn
│   ├── entities/            # Entity dictionary artifacts
│   └── samples/             # Sample nhỏ có thể commit
├── docs/
│   ├── memory/              # Context lâu dài, đọc trước mỗi session
│   ├── tasks/               # Backlog theo phase
│   ├── planning/            # Kế hoạch triển khai chi tiết
│   ├── architecture/        # Diagram và note kiến trúc
│   ├── literature/          # Paper notes
│   ├── thesis/              # Bản thảo luận văn
│   └── figures/             # Hình vẽ, bảng biểu
├── infrastructure/          # Docker, Kaggle, HF Spaces
├── mappings/                # RML mapping rules
├── notebooks/               # Notebook prototype
├── ontology/                # Ontology TTL, SHACL shapes, examples
├── scripts/                 # CLI orchestration scripts
├── src/nl2sparql/           # Python package chính
└── tests/                   # pytest
```

## .gitignore quan trọng

```
data/raw/         # CSV từ BigQuery
data/interim/      # Artifact trung gian lớn
data/processed/   # File .ttl size lớn
data/kg/          # TDB2 indexes
artifacts/
*.ckpt
*.bin
checkpoints/
wandb/
__pycache__/
.ipynb_checkpoints/
.env
.venv/
```

## Python style

- **Format:** `ruff format` (line length 100).
- **Lint:** `ruff check`. Fix tất cả lỗi trước khi commit.
- **Imports:** stdlib → 3rd party → local, mỗi nhóm cách 1 dòng. Ruff tự sort.
- **Docstrings:** Google style, có cho mọi function public.
- **Type hints:** dùng cho function signature public. Không bắt buộc cho biến cục bộ.
- **f-string:** ưu tiên hơn `.format()` hay `%`.

Ví dụ:

```python
def link_entity(
    mention: str,
    candidates: list[Entity],
    threshold: float = 0.85,
) -> list[Entity]:
    """Link a surface mention to candidate entities.

    Args:
        mention: Surface form from the question, e.g. "Binance".
        candidates: Pool of entities to consider.
        threshold: Minimum fuzzy ratio for stage B match.

    Returns:
        Ranked list of candidate entities, best first.
    """
    ...
```

## Naming

- **File Python:** `snake_case.py`.
- **Module:** `snake_case`; package chính là `nl2sparql`.
- **Class:** `PascalCase`.
- **Function/var:** `snake_case`.
- **Constant:** `UPPER_SNAKE_CASE`.
- **Notebook:** `NN_descriptive_name.ipynb` (NN là 2 chữ số thứ tự).

## Git commits

Format Conventional Commits:

```
<type>(<scope>): <subject>

<body — optional>
<footer — optional>
```

Types: `feat | fix | docs | refactor | test | chore | exp | data`.
- `exp` = experiment (training run).
- `data` = dataset thay đổi.

Scopes ưa dùng: `kg | linking | dataset | b0 | b1 | b3 | eval | demo | thesis`.

Ví dụ:
```
feat(linking): add 4-stage entity matcher
fix(rml): handle null `to_address` in contract creation tx
exp(b3): qlora r=16 lr=2e-4 → val_loss 0.42
data(test): add 20 hard test items from pool A
```

## Branch policy

Đơn giản — 1 người làm:

- `main` — luôn chạy được.
- `wip/<short-name>` — feature đang làm, có thể commit broken.
- Merge bằng squash để main sạch.

## Notebook convention

- Notebook = workspace prototype, KHÔNG phải nơi chứa source thật.
- Sau khi notebook xong → refactor logic ra `src/nl2sparql/`, notebook gọi `from nl2sparql.x import y`.
- Notebook commit ở trạng thái **đã chạy hết**, có output. Nếu output quá lớn → strip-output trước commit.

## Test convention

- File unit test: `tests/unit/test_<module>.py`.
- File integration test: `tests/integration/test_<workflow>.py`.
- Hàm: `test_<behavior>()`.
- Không cần coverage cao. Tập trung vào:
  - Linker (test các trường hợp alias, fuzzy, embedding).
  - Validator (test syntax/schema check).
  - Critical SPARQL templates (chạy được trên KG mock).
- Chạy bằng `pytest -q`.

## Documentation các quyết định trong code

Khi gặp lựa chọn không hiển nhiên, để comment kiểu:

```python
# DECISION: dùng Levenshtein ratio thay vì Jaro-Winkler vì
# entity blockchain hay có pattern "0x..." khiến J-W bị lệch.
# Xem 05-DECISION_LOG.md ngày 2025-XX-XX.
```

## File size + binary

- **KHÔNG commit:** file `.ttl` >50MB, `.csv` >50MB, `.ckpt`, `.bin`, dataset raw.
- **Commit:** sample nhỏ (top 100 dòng) cho người khác sanity-check.
- File lớn → upload lên HF Hub hoặc Kaggle Dataset, ghi link trong README.

## Reproducibility

- Pin random seed: `torch.manual_seed(42)`, `np.random.seed(42)`, `random.seed(42)`.
- Mỗi experiment → ghi config (yaml/json) và git commit hash.
- Notebook lưu lại version Python + pip freeze ở cell đầu.

## Comment ngôn ngữ

- Comment **trong code**: English (để PR/share dễ).
- Docstring: English.
- Markdown task/memory: Vietnamese.
- Exception: comment giải thích quirk đặc thù tiếng Việt — viết tiếng Việt được, nhưng hiếm khi cần.
