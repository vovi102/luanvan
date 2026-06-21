# T1.1 — Pilot: Load EthOn Ontology vào Fuseki

## Mục tiêu

Parse bản EthOn ontology đã commit, load vào Fuseki, query 3 SPARQL test trên ontology để verify ontology + Fuseki kết hợp hoạt động.

## Bối cảnh & lý do

EthOn (Ethereum Ontology) là ontology nền cho KG. Trước khi extract dữ liệu BigQuery + RML mapping, cần verify ontology load được vào Fuseki và truy vấn được class/property hierarchy.

Đây là bước 1 trong 3 bước pilot của Phase 1, để verify khả thi của Plan A (xem `docs/tasks/phase-2-kg/06-pivot-decision.md`).

## Phụ thuộc

- T0.2 — Fuseki local đã chạy.

## Đầu vào

- Upstream canonical: https://github.com/ConsenSys/EthOn; raw source: https://raw.githubusercontent.com/ConsenSys/EthOn/master/EthOn.ttl.
- Complete ontology đã được commit tại `data/ontologies/EthOn.ttl`; luồng verify thông thường chỉ dùng file này và không phụ thuộc network.
- Fuseki dataset name `ethon-pilot` (in-memory).

## Đầu ra

- File `data/ontologies/EthOn.ttl` (cached).
- Dataset `ethon-pilot` ở Fuseki, contain ontology.
- File `src/nl2sparql/kg/validation/ethon_smoke.sparql` chứa 3 query test ontology.
- Notebook `notebooks/02_ethon_pilot.ipynb` chạy queries, in kết quả.

## Acceptance criteria

- [x] EthOn.ttl tải về và parse được không lỗi (`rdflib.Graph().parse()`).
- [x] Load vào Fuseki dataset `ethon-pilot`, count triples ≥ vài trăm.
- [x] 3 SPARQL queries chạy ra kết quả không rỗng.
- [x] Liệt kê được tất cả class (subclass of `owl:Class`) trong EthOn — ghi danh sách vào `src/nl2sparql/kg/ontology/ethon-classes.md`.
- [x] Liệt kê được tất cả property — ghi vào `src/nl2sparql/kg/ontology/ethon-properties.md`.

## Hướng dẫn triển khai

1. Dùng complete ontology đã commit tại `data/ontologies/EthOn.ttl`. URL canonical/raw ở phần **Đầu vào** chỉ dùng để truy xuất provenance hoặc khôi phục source khi cần, không phải dependency của verification.

2. Parse local bằng helper đã test (helper dùng `rdflib` với format Turtle):
   ```python
   from pathlib import Path

   from nl2sparql.kg.ontology.ethon_pilot import inspect_ethon, load_ethon

   graph = load_ethon(Path("data/ontologies/EthOn.ttl"))
   inventory = inspect_ethon(graph)
   print(f"Loaded {len(graph)} triples and {len(inventory.classes)} classes")
   ```
   Có thể dùng trực tiếp `rdflib.Graph().parse(..., format="turtle")` khi chỉ cần kiểm tra cú pháp.

3. Inventories deterministic được render bằng `render_class_inventory` và `render_property_inventory`, rồi commit tại `src/nl2sparql/kg/ontology/ethon-classes.md` và `src/nl2sparql/kg/ontology/ethon-properties.md`. Tests kiểm tra các artifact này khớp chính xác với ontology + source checksum. Notebook chỉ hiển thị và verify counts; notebook không ghi các file Markdown.

4. Chạy notebook `notebooks/02_ethon_pilot.ipynb` để thực hiện canonical Fuseki workflow qua `FusekiPilotClient`:
   - Dùng HTTP Basic authentication; local defaults là `admin`/`admin`, có thể override bằng `FUSEKI_ADMIN_USER` và `FUSEKI_ADMIN_PASSWORD`.
   - `prepare_dataset()` tạo in-memory dataset `ethon-pilot` nếu chưa tồn tại và luôn `DROP ALL`, nên mỗi lần chạy bắt đầu từ trạng thái sạch, idempotent.
   - `upload_turtle()` upload complete Turtle đã commit.
   - Load và chạy chính xác ba query đã lưu, sau đó assert kết quả không rỗng.

5. `src/nl2sparql/kg/validation/ethon_smoke.sparql` là source of truth cho ba query và variable names (`?class`/`?label`, `?property`/`?domain`/`?range`, `?subclass`/`?superclass`). Notebook load artifact này bằng `load_smoke_queries()` thay vì duplicate SPARQL inline.

6. Nhận xét trong `05-DECISION_LOG.md`:
   - EthOn cover được gì (Account, Transaction, Block, ...).
   - Thiếu gì (DEX, Lending, Mixer, Token? Có phải tự extension không?).

## Rủi ro & note

- **EthOn repo có thể không còn maintained** (last commit 2018-2019). Complete committed copy + checksum là source cho pilot. Chỉ trong tình huống phục hồi lịch sử khi cả upstream lẫn bản committed không còn dùng được mới tham khảo archive/paper hoặc dựng minimal skeleton; skeleton không phải normal pilot path và không thay thế acceptance trên complete ontology.
- **EthOn dùng OWL DL** — không cần reasoner cho thesis này, nhưng nếu cần: Fuseki có flag `--rdfs` cho RDFS inference đơn giản.
- **Namespace trong EthOn** là `http://ethon.consensys.net/`. Giữ nguyên khi import; extension của ta dùng namespace local riêng (xem `03-ONTOLOGY_REFERENCE.md`).

## Estimated effort

0.5 ngày.

## Kết quả

- Source SHA-256: `e73e19bf0d6bbb0e28b1497a73e4499ca78ee9c1e8c475fa31e7c821354ce71d`; kích thước file: 86,718 bytes.
- Ontology local: 1,423 triples, 40 classes, 48 object properties, 60 datatype properties và 29 quan hệ subclass.
- Fuseki dataset `ethon-pilot`: 1,423 triples; ba smoke query trả lần lượt 45, 48 và 29 dòng.

## Verification

```bash
docker compose \
  -f infrastructure/docker/docker-compose.fuseki.yml \
  up -d

docker compose \
  -f infrastructure/docker/docker-compose.fuseki.yml \
  ps

UV_CACHE_DIR=.uv-cache \
UV_PYTHON_INSTALL_DIR=.uv-python \
uv run pytest -q

UV_CACHE_DIR=.uv-cache \
UV_PYTHON_INSTALL_DIR=.uv-python \
uv run ruff check src tests scripts

JUPYTER_CONFIG_DIR=/tmp/t1-1-jupyter-config \
JUPYTER_DATA_DIR=/tmp/t1-1-jupyter-data \
JUPYTER_RUNTIME_DIR=/tmp/t1-1-jupyter-runtime \
UV_CACHE_DIR=.uv-cache \
UV_PYTHON_INSTALL_DIR=.uv-python \
uv run jupyter nbconvert \
  --to notebook \
  --execute notebooks/02_ethon_pilot.ipynb \
  --output /tmp/t1-1-ethon-pilot-verified.ipynb \
  --ExecutePreprocessor.timeout=120

curl --fail \
  --user admin:admin \
  --data-urlencode 'query=SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }' \
  -H 'Accept: application/sparql-results+json' \
  http://localhost:3030/ethon-pilot/query

git diff --check
git status --short --branch
```

## Trạng thái

`done — 2026-06-20`
