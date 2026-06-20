# T1.1 — Pilot: Load EthOn Ontology vào Fuseki

## Mục tiêu

Download EthOn ontology, load vào Fuseki, query 3 SPARQL test trên ontology để verify ontology + Fuseki kết hợp hoạt động.

## Bối cảnh & lý do

EthOn (Ethereum Ontology) là ontology nền cho KG. Trước khi extract dữ liệu BigQuery + RML mapping, cần verify ontology load được vào Fuseki và truy vấn được class/property hierarchy.

Đây là bước 1 trong 3 bước pilot của Phase 1, để verify khả thi của Plan A (xem `docs/tasks/phase-2-kg/06-pivot-decision.md`).

## Phụ thuộc

- T0.2 — Fuseki local đã chạy.

## Đầu vào

- EthOn TTL: download từ https://github.com/ConsenSysMesh/EthOn (file `EthOn.ttl`).
  - Nếu link chết: tham khảo paper EthOn để tìm mirror, hoặc tự kiến tạo skeleton từ paper.
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

1. Download EthOn.ttl. Nếu repo gốc khó access, có thể clone từ alternative mirror hoặc tự kiến tạo sub-set tối thiểu (Account, Transaction, Block, vài property cơ bản) dựa trên paper.

2. Parse local trước:
   ```python
   from rdflib import Graph
   g = Graph()
   g.parse("data/ontologies/EthOn.ttl", format="turtle")
   print(f"Loaded {len(g)} triples")
   ```

3. Upload vào Fuseki:
   ```bash
   curl -X POST -H "Content-Type: text/turtle" \
        --data-binary @data/ontologies/EthOn.ttl \
        http://localhost:3030/ethon-pilot/data
   ```

4. **Query 1: list classes**
   ```sparql
   PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?class ?label WHERE {
     ?class a owl:Class .
     OPTIONAL { ?class rdfs:label ?label }
   }
   ```

5. **Query 2: list object properties + domain/range**
   ```sparql
   PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?prop ?domain ?range WHERE {
     ?prop a owl:ObjectProperty .
     OPTIONAL { ?prop rdfs:domain ?domain }
     OPTIONAL { ?prop rdfs:range ?range }
   }
   ```

6. **Query 3: subclass hierarchy**
   ```sparql
   PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
   SELECT ?sub ?super WHERE {
     ?sub rdfs:subClassOf ?super .
     ?sub a owl:Class . ?super a owl:Class .
   }
   ```

7. Trong notebook, in kết quả pretty + save vào `ethon-classes.md` và `ethon-properties.md`.

8. Nhận xét trong `05-DECISION_LOG.md`:
   - EthOn cover được gì (Account, Transaction, Block, ...).
   - Thiếu gì (DEX, Lending, Mixer, Token? Có phải tự extension không?).

## Rủi ro & note

- **EthOn repo có thể không còn maintained** (last commit 2018-2019). Nếu link chết: clone từ Wayback Machine hoặc tự rebuild minimal.
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
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_ethon_pilot.py tests/unit/test_fuseki_pilot.py -q
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest -q
docker compose -f infrastructure/docker/docker-compose.fuseki.yml ps
JUPYTER_CONFIG_DIR=/tmp/t1-1-jupyter-config JUPYTER_DATA_DIR=/tmp/t1-1-jupyter-data JUPYTER_RUNTIME_DIR=/tmp/t1-1-jupyter-runtime UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run jupyter nbconvert --to notebook --execute notebooks/02_ethon_pilot.ipynb --output /tmp/t1-1-ethon-pilot-verified.ipynb --ExecutePreprocessor.timeout=120
curl --fail --user admin:admin --data-urlencode 'query=SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }' -H 'Accept: application/sparql-results+json' http://localhost:3030/ethon-pilot/query
```

## Trạng thái

`done — 2026-06-20`
