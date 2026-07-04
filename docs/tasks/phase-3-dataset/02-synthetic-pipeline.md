# T3.2 — Synthetic Generation Pipeline (Bước A)

## Mục tiêu

Sinh ~1000 cặp `(SPARQL, NL_seed)` từ templates + entity sampling từ KG. Mỗi cặp đảm bảo SPARQL chạy thực và trả kết quả non-empty trên Fuseki.

## Bối cảnh & lý do

Đây là bước A trong pipeline sinh dataset 4-bước (A→B→C→D). Output của bước này là input cho paraphrasing (T3.3).

Chất lượng "execute và non-empty" rất quan trọng: nếu sinh template + entity ngẫu nhiên ra trả 0 kết quả, training data sẽ teach model sinh query "rỗng" — phải reject và regenerate.

## Phụ thuộc

- T3.1 — `templates.json` đã có ≥25 templates verified.
- T2.2 — Entity dictionary (`entities.json`).
- T2.4 — Full KG đã load vào Fuseki.

## Đầu vào

- `src/nl2sparql/dataset/templates/templates.json`.
- `src/nl2sparql/linking/dictionary/entities.json`.
- Fuseki endpoint full KG.

## Đầu ra

- File `data/dataset/raw/synthetic-stage-a.jsonl` — ~1000-1200 records (sinh dư để loss khi reject).
- Notebook `notebooks/08_generate_synthetic.ipynb`.
- Script `src/nl2sparql/dataset/generate.py` — CLI có thể chạy lại reproducible.
- Report `data/dataset/raw/stats.md` — phân bố templates, difficulty, entities.

## Acceptance criteria

- [ ] ≥1000 records không trùng SPARQL.
- [ ] 100% records có SPARQL chạy thành công trên Fuseki, kết quả non-empty.
- [ ] Phân bố template: không template nào chiếm >10% dataset.
- [ ] Phân bố entity: không entity nào chiếm >5% (tránh model nhớ địa chỉ cụ thể).
- [ ] Stratified theo difficulty: ~30% Easy, ~45% Medium, ~25% Hard.
- [ ] Có seed cố định (42), reproducible.

## Local automation scaffold

- [x] `src/nl2sparql/dataset/generate.py` load templates, render deterministic Stage A records, write JSONL, write stats, and expose CLI.
- [x] Unit tests verify deterministic generation, record schema, unique SPARQL strings, template frequency cap, JSONL writing, and stats writing.
- [x] `notebooks/08_generate_synthetic.ipynb` is an unexecuted notebook scaffold for local generation.
- [x] Scaffold records use `verification_mode = "offline_render_only"`.
- [x] Live Fuseki execution and non-empty filtering remain pending until full KG is loaded.

## Hướng dẫn triển khai

### Schema record output

```json
{
  "id": "syn-000123",
  "template_id": "T_TX_TOP_N_BY_VALUE",
  "difficulty": "medium",
  "slot_values": {
    "n": 10,
    "start_date": "2024-01-15",
    "end_date": "2024-01-20"
  },
  "entities_used": [
    {"slot": null, "type": "time_filter", "value": "2024-01-15"}
  ],
  "sparql": "SELECT ?tx ?value WHERE { ... } ORDER BY DESC(?value) LIMIT 10",
  "nl_seed": "Top 10 transactions by value between 2024-01-15 and 2024-01-20",
  "result_preview": [
    {"tx": "0xabc...", "value": "1234.5"}
  ],
  "result_count": 10,
  "execution_time_ms": 234,
  "verified_at": "2026-04-15T10:30:00Z"
}
```

### Pipeline logic

```python
def generate_one(template, entity_pool):
    # 1. Sample slot values
    slot_values = {}
    for slot_name, slot_def in template["slots"].items():
        slot_values[slot_name] = sample_slot(slot_def, entity_pool)

    # 2. Fill template
    sparql = fill_sparql(template["sparql_template"], slot_values)
    nl_seed = fill_nl(template["nl_seed"], slot_values)

    # 3. Execute on Fuseki (with timeout 10s)
    try:
        result = run_sparql(sparql, timeout=10)
    except TimeoutError:
        return None  # reject

    # 4. Check non-empty
    if len(result) == 0:
        return None  # reject

    # 5. Build record
    return build_record(...)

def main():
    target = 1000
    accepted = []
    attempts = 0
    while len(accepted) < target and attempts < target * 5:
        template = sample_template_stratified(templates)
        rec = generate_one(template, entity_pool)
        if rec:
            accepted.append(rec)
        attempts += 1
```

### Sampling slot

- `entity_address` slot → sample từ `entities.json` weighted theo confidence.
- `entity_owner` slot → sample owner (e.g. "Binance") từ unique owners list.
- `concept_class` slot → sample từ {Exchange, DEXProtocol, MixerAccount, ...}.
- `decimal_eth` slot → sample log-uniform [0.01, 10000].
- `integer` (top-N) → sample {5, 10, 20, 50, 100}.
- `date` → sample uniform trong dataset time range.
- `duration` → {"1 hour", "1 day", "1 week", "last month"}.

### Stratified template sampling

- Tính tần suất template theo difficulty target.
- Mỗi vòng `random.choices(templates, weights=...)` để tránh chỉ pick easy.

### Reject conditions

1. SPARQL timeout >10s (skip, không retry cùng entity).
2. Result empty.
3. SPARQL parse error (báo bug template).
4. Result quá lớn (>1000 rows) → có thể OK nhưng đánh dấu để paraphrasing không expand kết quả.

### Reproducibility

- `random.seed(42)`.
- Lưu `generation_config.json` với seed, template hash, dictionary version.

## Rủi ro & note

- **Templates thiếu data:** một số template (e.g. "transactions to mixer") có thể không có nhiều entity match → distribution skew. Giải pháp: log reject rate per template, nếu template nào reject >50% → quay lại sửa template.
- **Sinh quá nhiều variant của 1 template:** dùng cap 10% để tránh.
- **Slow generation:** parallel execution Fuseki với `concurrent.futures` (5-10 workers).

## Estimated effort

2 ngày.

## Trạng thái

`scaffold done; Fuseki execution pending`

Local offline rendering scaffold is complete. Full acceptance remains pending because `data/processed/full/output.nt` and Fuseki `eth-kg` live verification are not available yet.

## Evidence — 2026-07-04 Scaffold

- Branch: `feat/t3-2-synthetic-pipeline-scaffold`.
- Design/spec:
  - `docs/superpowers/specs/2026-07-04-t3-2-synthetic-pipeline-scaffold-design.md`
  - `docs/superpowers/plans/2026-07-04-t3-2-synthetic-pipeline-scaffold.md`
- Implemented files:
  - `src/nl2sparql/dataset/generate.py`
  - `tests/unit/test_synthetic_generate.py`
  - `notebooks/08_generate_synthetic.ipynb`
- Focused local verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_synthetic_generate.py -q
  ```
  Result: `3 passed`.

## Next live evidence step

After the full KG is loaded in Fuseki, extend `generate.py` with query execution/rejection, run target count 1000, and record duplicate rate, reject rate, template distribution, entity distribution, and non-empty verification results here.
