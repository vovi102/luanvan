# T4.3 — GoogleSQL Class Resolver (Typed Constraint Planning)

## Mục tiêu

Chuyển evidence từ T4.2 và ranking tùy chọn từ T4.1 thành constraint plan có
kiểu, bind vào analytical catalog và dictionary provenance. Resolver không sinh
SPARQL, không render SQL và không gọi BigQuery.

## Migration sau Pivot #1

Task cũ yêu cầu `VALUES`, `BIND` và RDF class triple. Contract đó đã bị
supersede bởi Plan B GoogleSQL. Runtime canonical dùng:

- field identity dạng `relation.field` đã tồn tại trong catalog;
- operator typed `in`, `equals`, hoặc `none`;
- `fact_address_to_entity` và `entity_labels_v1` cho concept lookup;
- role `operational`, `treasury`, `token` đúng catalog policy;
- explicit `coverage_gap` thay vì claim endpoint không có trong dictionary.

## Phụ thuộc

- T4.1 — `SchemaLinker` rank analytical relations và fields.
- T4.2 — `EntityLinker` trả immutable `EntityMatch` evidence.
- T2-SQL-1/2 — validated catalog và label-enriched analytical layer.

## Interface

```python
ClassResolver(catalog_path, entity_corpus).resolve(
    question,
    matches,
    schema_links=None,
) -> ResolutionPlan
```

`ResolutionPlan` chứa ordered `ResolvedEntity`, catalog/dictionary/question
fingerprints, aggregate status và warnings. Mỗi entity ghi resolution kind,
direction, candidate fields, typed operator/values, required relation/join/role,
coverage status, confidence và explanation. Output không chứa executable query.

## Resolution policy

1. Owner hoặc raw address hợp lệ resolve thành instance address membership.
2. Concept resolve qua `entity_labels_v1.concept_class` và
   `fact_address_to_entity`.
3. Ambiguous match mặc định unresolved. `any`, `all`, `every`, `major` hoặc
   plural generic chỉ chọn khi có đúng một concept alternative trong corpus.
4. Cue local xác định `from`, `to`; T4.1 token field có thể xác định `token`.
   Cue xung đột hoặc thiếu evidence giữ `unspecified`.
5. T4.1 chỉ thu hẹp candidate catalog; unknown relation/field fail closed.
6. Concept coverage được kiểm tra từ owner targets có cùng concept class và
   accepted address roles. Không có endpoint thì `coverage_gap`.
7. Hai mention dùng cùng direction được giữ nguyên và phát conflict warning;
   resolver không tự phát minh boolean intent.

Chi tiết vận hành nằm tại `src/nl2sparql/linking/RESOLVER_RULES.md`.

## Offline workflow

```bash
uv run python scripts/15_class_resolver.py resolve --input path/to/payload.json
uv run python scripts/15_class_resolver.py evaluate \
  --ground-truth data/eval/class_resolver_groundtruth.jsonl \
  --report reports/class_resolver_evaluation.json
```

`resolve` in canonical JSON ra stdout. `evaluate` yêu cầu đúng 50 câu reviewed,
bind exact JSONL bytes và provenance, rồi publish report atomically. Import và
`--help` không build model/corpus hay gọi external service.

## Acceptance criteria

- [x] GoogleSQL-native immutable typed contracts và stable resolver facade.
- [x] Owner, raw address, concept, ambiguity, direction, schema narrowing,
  role, coverage và conflict behavior có focused tests.
- [x] Catalog/dictionary/span/fingerprint evidence fail closed.
- [x] Exactly-50 JSONL validator và deterministic evaluation metrics.
- [x] Offline numbered CLI, canonical JSON và safe atomic report publication.
- [x] Local focused/full pytest, Ruff lint/format và diff checks pass.
- [ ] Fully resolved plan accuracy >=90% trên đúng 50 câu independently
  reviewed. Artifact `data/eval/class_resolver_groundtruth.jsonl` chưa tồn tại;
  fixtures synthetic không thay thế scientific evidence.

## Trạng thái

Implementation checkpoint complete locally. Scientific acceptance còn pending
independent 50-row artifact và production `evaluate` run. Task không yêu cầu
credential, network, model download hoặc BigQuery execution để hoàn tất phần
implementation local.

## Evidence triển khai cục bộ — 2026-08-31

- Focused T4.3 suite: `66 passed`.
- Full repository suite: `813 passed`, `342 warnings` từ dependencies/legacy RML
  paths đã biết; không có failure.
- `ruff check .`: pass.
- `ruff format --check .`: `151 files already formatted`.
- Numbered `scripts/15_class_resolver.py --help`: pass với `resolve` và `evaluate`.
- `git diff --check`: pass.
- Không có model initialization, network access, BigQuery credential hoặc live
  query trong verification.
