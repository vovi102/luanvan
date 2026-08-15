# T4.1 — GoogleSQL Schema Linker (Relation + Field Ranking)

## Mục tiêu

Xây dựng `SchemaLinker` nhận một câu hỏi NL tiếng Anh và trả về hai ranking độc
lập cho các analytical relation và `relation.field` trong catalog GoogleSQL Plan
B. Kết quả này là schema context cho SQL generator và là treatment để đo đóng
góp của schema linking trong RQ2.

Task này không còn rank ontology class/property hoặc inject SPARQL/Fuseki
context. Plan A đã dừng tại Pivot Point #1; ontology chỉ còn là semantic source
đã được map vào catalog Plan B.

## Phụ thuộc và input canonical

- Catalog: `src/nl2sparql/sql/catalog/ethereum_analytics.json`.
- Loader/validator: `nl2sparql.sql.schema.load_catalog`.
- Synonym lexicon được review và version-control:
  `src/nl2sparql/linking/schema/synonyms.json`.
- Production encoder: `sentence-transformers/all-MiniLM-L6-v2`.
- Ground truth khoa học, khi có:
  `data/eval/schema_link_groundtruth.jsonl`, đúng 50 rows được review độc lập.

Committed Stage A/template provenance chỉ được dùng làm fixture/diagnostic. Nó
không thay thế manual ground truth và không được dùng để đóng acceptance recall.

## Contract triển khai

Public API:

```python
SchemaLinker.link(question: str, top_k: int = 10) -> LinkResult

LinkResult.relations: tuple[SchemaMatch, ...]
LinkResult.fields: tuple[SchemaMatch, ...]
```

Mỗi `SchemaMatch` chứa `element_id`, `kind`, total score, lexical score, semantic
score và document fingerprint. Hai pool relation/field được rank riêng, score
giảm dần và tie-break ổn định theo element ID.

Retrieval mặc định:

```text
0.65 * semantic_score + 0.35 * lexical_score
```

- Documents chỉ dùng evidence đã commit từ catalog và synonym lexicon.
- Vector document/câu hỏi được L2-normalize; semantic score là cosine similarity.
- Input rỗng, control character, sai type hoặc `top_k` ngoài range fail closed.
- Unit tests inject fake encoder deterministic, không tải model/network.
- Production CLI không fallback sang vector giả khi model/cache không sẵn sàng.

## Cache và workflow

Cache production không dùng pickle:

- `src/nl2sparql/linking/cache/schema-index.json`: manifest canonical, bind model,
  catalog SHA-256, document version, weights, element order/dimension và NPZ hash.
- `src/nl2sparql/linking/cache/schema-index.npz`: relation/field matrices float32,
  load bằng `allow_pickle=False`.
- `src/nl2sparql/linking/cache/schema-index.lock`: process-lock sidecar do explicit
  build tạo; không chứa model/vector data.

`scripts/13_schema_linker.py` cung cấp:

- `build-index`: explicit model load và atomic cache publication.
- `query`: strict-load cache rồi rank relation/field.
- `evaluate`: chỉ chạy với đúng ground truth 50 rows, warm-up trước đo, xuất report
  aggregate có hashes/model/git provenance.

Missing model/network/ground truth trả structured `blocked`; invalid
catalog/cache/ground truth trả `failed`. Không command nào tự sinh manual labels
hoặc silently rebuild cache stale.

## Artifacts triển khai

- `src/nl2sparql/linking/schema/contracts.py`
- `src/nl2sparql/linking/schema/documents.py`
- `src/nl2sparql/linking/schema/index.py`
- `src/nl2sparql/linking/schema/linker.py`
- `src/nl2sparql/linking/schema/evaluate.py`
- `src/nl2sparql/linking/schema/synonyms.json`
- `src/nl2sparql/linking/schema_linker.py`
- `scripts/schema_linker_workflow.py`
- `scripts/13_schema_linker.py`
- `tests/unit/test_schema_documents.py`
- `tests/unit/test_schema_index.py`
- `tests/unit/test_schema_linker.py`
- `tests/unit/test_schema_linker_evaluate.py`
- `notebooks/11_schema_linker_eval.ipynb`

## Acceptance criteria

### Implementation evidence

- [x] API typed trả hai ranking độc lập cho relation và field Plan B.
- [x] Catalog documents deterministic cho 6 relations và 62 fields; unknown
  references, duplicate IDs và synonym malformed fail closed.
- [x] Hybrid lexical/MiniLM retrieval dùng weights `0.35/0.65`, stable tie-break và
  directional role terms như sender/from so với recipient/to.
- [x] Cache JSON/NPZ fingerprinted, atomic, không pickle; loader validate catalog,
  model, document version, element order/count, dimensions, normalization và
  payload digest.
- [x] Real production index đã build bằng
  `sentence-transformers/all-MiniLM-L6-v2`, không fake vector.
- [x] Validated cache load lần hai dưới 1 giây: 2.806 ms ngày 2026-08-15, 384
  dimensions, 6 relation rows và 62 field rows.
- [x] Tests cover invalid input, stale/tampered cache, atomic replacement, role
  ambiguity, synonym ranking, metric math, exact-50 ground-truth validation và
  CLI structured status.
- [x] Notebook là thin consumer của production evaluator và là JSON hợp lệ.

### Scientific/external acceptance còn pending

- [ ] Có đúng 50 câu manual ground truth được independently reviewed tại
  `data/eval/schema_link_groundtruth.jsonl`.
- [ ] Field Recall@10 ≥ 0.80 trên file 50 câu đã accept.
- [ ] Warm inference p50 < 100 ms trên cùng evaluation run; ghi kèm p95.
- [ ] Commit hash-bound evaluation report với ground-truth/cache/model/git hashes.

Không tick bốn box trên từ template-derived fixtures hoặc unit fake encoder.
Ngày 2026-08-15 file ground truth accepted chưa tồn tại, vì vậy `evaluate` không
được chạy và không có scientific metrics/report để công bố.

## Evidence production index (2026-08-15)

- Model snapshot được tải vào cache ngoài repo:
  `/home/khoavd/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/`
  (khoảng 88 MiB; snapshot `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`).
- Catalog SHA-256:
  `db8393aa7258d1331387eff9825e22ca729daf93234419f00d7dd538196cb3dd`.
- Manifest file SHA-256:
  `d3168a6d25830dea1dd2696281a816cae693a08c87fa6903b60bb8b2b8a9a8a0`.
- Manifest body SHA-256:
  `0aa2a44211f1268ee329b52918540445d1d63c3d9615e24814c8394e22f375f7`.
- NPZ SHA-256:
  `17b123ba8a2baf42d2c5235e7a63019d29b682dea7366affecb63b6cba987324`.

## Verification

Fresh repository verification ngày 2026-08-15:

- `UV_CACHE_DIR=.uv-cache uv run pytest -q`: exit 0, 502 passed, 342 warnings.
- `UV_CACHE_DIR=.uv-cache uv run ruff check .`: exit 0, all checks passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff format --check .`: exit 0, 120 files đã
  formatted.
- `UV_CACHE_DIR=.uv-cache uv run python -m json.tool
  notebooks/11_schema_linker_eval.ipynb`: exit 0.
- `git diff --check`: exit 0, không có output.
- `git status --short --branch`: exit 0; chỉ có Task 5 docs/evidence/cache artifact
  trước commit, branch ahead 8.
- Formal focused review: **Approved**, không có Critical/Important/Minor finding.
  Reviewer independently xác nhận NPZ có đúng hai float32 matrices shapes
  `(6, 384)` và `(62, 384)`, unit-normalized, khớp manifest/catalog hashes,
  element order, model ID, document version và score weights.

Không dùng kết quả của unit fixture để suy ra scientific Recall@10 hoặc
production query latency.

## Trạng thái — implementation complete, manual evaluation gate pending

Implementation và real production index đã sẵn sàng. Scientific acceptance vẫn
pending cho đến khi có independent 50-row manual ground truth và real evaluation
đạt recall/latency gates.
