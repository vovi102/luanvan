# T0.2 — Apache Jena Fuseki Local Setup

## Mục tiêu

Cài Apache Jena Fuseki local, chạy được trên port 3030, query SPARQL test thành công.

## Bối cảnh & lý do

Fuseki là triple store + SPARQL endpoint chính (Plan A). Cần verify cài được trước khi đầu tư công sức cho RML. Đây là **first sanity check** cho tính khả thi của Plan A.

## Phụ thuộc

- (không bắt buộc) T0.1 — Repo setup. Có thể làm song song.

## Đầu vào

- Docker + Docker Compose v2 đã cài sẵn trên máy.
- Tham khảo `docs/memory/02-TECH_STACK.md` (Fuseki version 4.10+).

## Đầu ra

- Fuseki chạy bằng Docker Compose.
- File script `src/nl2sparql/kg/scripts/start_fuseki.sh` để start server.
- File `src/nl2sparql/kg/validation/smoke_queries.sparql` chứa 3 query test.
- Notebook `notebooks/00_fuseki_smoke.ipynb` demo: dùng `SPARQLWrapper` query Fuseki, cho ra kết quả.

## Acceptance criteria

- [x] Truy cập `http://localhost:3030/` thấy admin UI.
- [x] Tạo dataset name `test` (in-memory hoặc TDB2).
- [x] Upload file `src/nl2sparql/kg/validation/sample.ttl` (10-20 triples tự viết, ví dụ về địa chỉ + transaction giả) thành công.
- [x] Chạy 3 SPARQL queries qua `SPARQLWrapper` cho ra kết quả không rỗng.
- [x] Document quy trình start/stop Fuseki trong `docs/setup-fuseki.md`.

## Hướng dẫn triển khai

1. Download Fuseki:
   ```bash
   wget https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-4.10.0.tar.gz
   tar xzf apache-jena-fuseki-4.10.0.tar.gz
   ```

2. Khởi động ở chế độ developer:
   ```bash
   cd apache-jena-fuseki-4.10.0
   ./fuseki-server --update --mem /test
   ```

   Cờ `--mem /test` tạo dataset in-memory tên `test`. Đủ cho smoke; sẽ chuyển sang TDB2 ở Phase 2.

3. Tạo `src/nl2sparql/kg/validation/sample.ttl`:
   ```turtle
   @prefix : <https://thesis.example.org/eth-kg/> .
   @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

   :addr_alice a :Account ;
       :hasLabel "Alice" .

   :addr_bob a :Account ;
       :hasLabel "Bob" .

   :tx_001 a :Transaction ;
       :hasFrom :addr_alice ;
       :hasTo :addr_bob ;
       :hasValue "1000000000000000000"^^xsd:decimal ;
       :hasTimestamp "2024-01-01T00:00:00Z"^^xsd:dateTime .
   ```

4. Upload qua admin UI hoặc curl:
   ```bash
   curl -X POST -H "Content-Type: text/turtle" \
        --data-binary @src/nl2sparql/kg/validation/sample.ttl \
        http://localhost:3030/test/data
   ```

5. Tạo `src/nl2sparql/kg/validation/smoke_queries.sparql`:
   ```sparql
   # Query 1: count all transactions
   PREFIX : <https://thesis.example.org/eth-kg/>
   SELECT (COUNT(?tx) AS ?n) WHERE { ?tx a :Transaction }

   # Query 2: list transactions with from/to labels
   PREFIX : <https://thesis.example.org/eth-kg/>
   SELECT ?tx ?fromLabel ?toLabel ?value WHERE {
     ?tx a :Transaction ;
         :hasFrom ?from ; :hasTo ?to ; :hasValue ?value .
     ?from :hasLabel ?fromLabel .
     ?to :hasLabel ?toLabel .
   }

   # Query 3: filter by value
   PREFIX : <https://thesis.example.org/eth-kg/>
   PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
   SELECT ?tx WHERE {
     ?tx a :Transaction ;
         :hasValue ?v .
     FILTER(?v >= 1000000000000000000)
   }
   ```

6. Notebook `notebooks/00_fuseki_smoke.ipynb`:
   ```python
   from SPARQLWrapper import SPARQLWrapper, JSON
   sw = SPARQLWrapper("http://localhost:3030/test/sparql")
   sw.setReturnFormat(JSON)
   sw.setQuery("SELECT (COUNT(*) AS ?n) WHERE {?s ?p ?o}")
   print(sw.query().convert())
   ```

7. Document trong `docs/setup-fuseki.md` các bước này.

## Rủi ro & note

- **Java version:** Fuseki 4.10 cần Java 17+. Java 11 sẽ lỗi runtime.
- **Port conflict:** mặc định 3030. Đổi `--port 3031` nếu conflict.
- **In-memory mất data khi restart:** chấp nhận ở smoke. Phase 2 chuyển TDB2.
- **CORS:** nếu sau này demo gọi từ browser local, cần thêm flag CORS. Chưa cần lúc này.

## Estimated effort

0.5 ngày.

## Trạng thái

`done — 2026-06-14`

Đã hoàn thành:

- `src/nl2sparql/kg/scripts/start_fuseki.sh`
- `infrastructure/docker/docker-compose.fuseki.yml`
- `src/nl2sparql/kg/validation/sample.ttl`
- `src/nl2sparql/kg/validation/smoke_queries.sparql`
- `notebooks/00_fuseki_smoke.ipynb`
- `docs/setup-fuseki.md`
- Unit tests kiểm tra TTL parse, smoke query file và script executable.

Verification đã pass:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest -q
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check src tests
docker compose -f infrastructure/docker/docker-compose.fuseki.yml up -d
curl -sS -X POST -H "Content-Type: text/turtle" -u admin:admin \
  --data-binary @src/nl2sparql/kg/validation/sample.ttl \
  http://localhost:3030/test/data
```

Kết quả: container `nl2sparql-fuseki` healthy, Fuseki 5.1.0 chạy trên Java 21 trong container, dataset `/test` tạo thành công, upload `sample.ttl` HTTP 200, 3 smoke queries qua `SPARQLWrapper` trả lần lượt 1/2/2 rows.
