# T2.4 — Full RML Mapping + Load KG vào Fuseki

## Mục tiêu

Mở rộng RML mapping pilot để cover toàn bộ dữ liệu CSV; chạy Morph-KGC; load output TTL vào Fuseki TDB2 (persistent storage).

## Bối cảnh & lý do

Đây là bước đưa dữ liệu raw thành KG queryable. Persistent TDB2 thay in-memory để KG không mất khi restart Fuseki + query nhanh hơn cho ≥1M triples.

## Phụ thuộc

- T1.3 — RML pilot đã chạy.
- T2.1 — Ontology extension đã chốt.
- T2.2 — Entity dictionary (cần để inject `:hasLabel`, `:hasOwner`, `a :ExchangeAccount` vào KG).
- T2.3 — CSV full extraction.

## Đầu vào

- 4 CSV trong `data/raw/full/`.
- Ontology `eth-kg-extension-v0.1.0.ttl`.
- Dictionary `entities.json`.

## Đầu ra

- File `src/nl2sparql/kg/rml/full_mapping.ttl` — RML rules đầy đủ.
- File `src/nl2sparql/kg/rml/run_morph_full.py` — chạy Morph-KGC.
- File `data/processed/full/output.nt` (output, có thể chia nhiều file nếu lớn).
- Fuseki TDB2 dataset `eth-kg` với data đã load.
- Notebook `notebooks/06_kg_load.ipynb` — verify queries.

## Acceptance criteria

- [ ] Morph-KGC chạy hoàn tất, không crash.
- [ ] Triple count ≥ 50M (5M tx × ~10 triple/tx).
- [ ] Fuseki TDB2 có thể query, response time < 2s cho query đơn giản (count, simple filter).
- [ ] 10 SPARQL competency queries từ T2.1 chạy được trên KG, trả kết quả hợp lý.
- [ ] Memory footprint TDB2 ≤ 30GB (cho persistent indexes).

## Local automation scaffold

- [x] `src/nl2sparql/kg/rml/full_mapping.ttl` có 5 TriplesMap cho transactions, blocks, token transfers, contracts, và entity labels.
- [x] `src/nl2sparql/kg/rml/run_morph_full.py` có helper validate inputs, prepare `entities.csv`, build Morph-KGC config, materialize output N-Triples, validate output, và CLI guardrails.
- [x] Unit tests materialize fixture CSV nhỏ qua Morph-KGC và assert ontology-aligned predicates từ T2.1.
- [x] CLI `--prepare-only` chạy được để tạo `data/raw/full/entities.csv` từ dictionary JSON.
- [x] Full live materialization bị chặn nếu thiếu `--force` hoặc `--fixture-mode`.
- [x] Full live materialization dùng chunked mode mặc định để tránh giữ toàn bộ RDFLib graph trong RAM.

## Hướng dẫn triển khai

### Phần 1 — Mở rộng RML mapping

`full_mapping.ttl` thêm các phần (so với pilot):

1. **Token transfers:**
   ```turtle
   <#TokenTransferMap> a rr:TriplesMap ;
       rml:logicalSource [
           rml:source "data/raw/full/token_transfers.csv" ;
           rml:referenceFormulation ql:CSV
       ] ;
       rr:subjectMap [
           rr:template "https://thesis.example.org/eth-kg/transfer/{transaction_hash}-{log_index}" ;
           rr:class :TokenTransfer
       ] ;
       rr:predicateObjectMap [
           rr:predicate :inTransaction ;
           rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/tx/{transaction_hash}" ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :transferredFromAccount ;
           rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/addr/{from_address}" ]
       ] ;
       # ... (to, amount, token contract)
   ```

2. **Inject labels từ entity dictionary:**

   Convert `entities.json` → `entities.csv` rồi map:

   ```turtle
   <#AccountLabelMap> a rr:TriplesMap ;
       rml:logicalSource [
           rml:source "data/raw/full/entities.csv" ;
           rml:referenceFormulation ql:CSV
       ] ;
       rr:subjectMap [
           rr:template "https://thesis.example.org/eth-kg/addr/{address}" ;
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasLabel ;
           rr:objectMap [ rml:reference "primary_label" ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasOwner ;
           rr:objectMap [ rml:reference "owner" ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasCategory ;
           rr:objectMap [ rml:reference "category" ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate rdf:type ;
           rr:objectMap [
               rr:template "https://thesis.example.org/eth-kg/{concept_class}" ;
               rr:termType rr:IRI
           ]
       ] .
   ```

   Note: subject map dùng cùng template `addr/{address}` → triple được merge với từ TransactionMap.

3. **Handle NULL `to_address`** (contract creation):

   Morph-KGC không tự skip NULL; cần SQL view trong logical source:
   ```turtle
   rml:logicalSource [
       rml:source "data/raw/full/transactions.csv" ;
       rml:referenceFormulation ql:CSV ;
       rml:iterator "$.[?(@.to_address != null)]"  # Nếu Morph-KGC support
   ]
   ```
   Hoặc đơn giản: pre-process CSV bằng pandas, drop rows NULL `to_address` (lưu thành CSV riêng cho contract-creation tx).

4. **Total mappings dự kiến:** 8-10 TriplesMap:
   - TransactionMap
   - BlockMap
   - TokenTransferMap
   - ContractMap
   - AccountLabelMap (từ dictionary)
   - ConceptClassMap (assign rdf:type cho địa chỉ thuộc concept)
   - (optional) MinerRewardMap

### Phần 2 — Chạy Morph-KGC

```python
import morph_kgc
import time

config = """
[CONFIGURATION]
output_format: N-TRIPLES
number_of_processes: 4

[DataSource1]
mappings: src/nl2sparql/kg/rml/full_mapping.ttl
"""

t0 = time.time()
g = morph_kgc.materialize(config)
print(f"Materialized {len(g)} triples in {time.time()-t0:.1f}s")

# Save
g.serialize(destination="data/processed/full/output.nt", format="nt")
```

**Lưu ý:**
- 5M tx → 50M+ triples → file `.nt` có thể vài chục GB. Dùng N-Triples (line-based) thay Turtle để load streaming.
- `number_of_processes: 4` parallelize per source.

### Phần 3 — Load vào Fuseki TDB2

1. **Stop Fuseki nếu đang chạy.**

2. **Build TDB2 offline (nhanh hơn loading qua HTTP):**
   ```bash
   cd apache-jena-fuseki-4.10.0
   ./tdb2.tdbloader --loc=data/eth-kg-tdb2 \
       data/processed/full/output.nt \
       data/ontologies/EthOn.ttl \
       src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl
   ```

   Loader sẽ in progress (rows/sec). 50M triples ~30-60 phút trên SSD tốt.

3. **Configure Fuseki dùng TDB2:**

   Tạo `config.ttl`:
   ```turtle
   @prefix : <#> .
   @prefix fuseki: <http://jena.apache.org/fuseki#> .
   @prefix tdb2: <http://jena.apache.org/2016/tdb#> .

   :service a fuseki:Service ;
       fuseki:name "eth-kg" ;
       fuseki:dataset :dataset ;
       fuseki:endpoint [ fuseki:operation fuseki:query ;
                         fuseki:name "sparql" ] ;
       fuseki:endpoint [ fuseki:operation fuseki:update ;
                         fuseki:name "update" ] .

   :dataset a tdb2:DatasetTDB2 ;
       tdb2:location "/path/to/data/eth-kg-tdb2" .
   ```

4. **Start Fuseki:**
   ```bash
   ./fuseki-server --config=config.ttl
   ```

### Phần 4 — Verify queries

10 competency queries từ T2.1, ví dụ:

```sparql
# Q1: Top exchanges by inbound tx
PREFIX : <https://thesis.example.org/eth-kg/>
SELECT ?owner (COUNT(?tx) AS ?n) WHERE {
  ?tx :hasTo ?to .
  ?to a :ExchangeAccount ; :hasOwner ?owner .
} GROUP BY ?owner ORDER BY DESC(?n) LIMIT 10
```

Đo response time mỗi query, log vào `docs/kg-benchmark.md`.

## Rủi ro & note

- **Triple count "phình":** mỗi tx tạo ~10 triple. Track total để không vượt 100M (Fuseki TDB2 vẫn ổn nhưng query chậm dần).
- **Disk space TDB2:** indexes ~3-5x raw triple size. 50M triples → ~30GB.
- **Memory:** mặc định Fuseki -Xmx 4GB. Cho 50M triples nên `-Xmx 8G` hoặc 16G.
- **Concurrent write:** Morph-KGC chạy → đừng đụng vào CSV files.
- **Index time:** lần đầu load chậm; sau đó query nhanh.
- **Nếu Morph-KGC quá chậm/crash:** fallback RMLMapper Java (slower nhưng stable hơn cho large data):
  ```bash
  java -jar rmlmapper.jar -m full_mapping.ttl -s nt -o output.nt
  ```

## Estimated effort

3-5 ngày (đa phần là chờ Morph-KGC + tdb2.tdbloader).

## Trạng thái

`scaffold done; live materialization pending`

Local scaffold đã hoàn tất để kiểm tra mapping bằng fixture nhỏ. Các acceptance criteria ở trên vẫn pending vì chưa chạy Morph-KGC trên `data/raw/full/`, chưa build Fuseki TDB2, chưa đo 50M+ triple count, và chưa benchmark competency queries trên KG thật.

## Evidence — 2026-07-04 Scaffold

- Branch: `feat/t2-4-rml-full-mapping`.
- Design/spec:
  - `docs/superpowers/specs/2026-07-04-t2-4-rml-full-mapping-design.md`
  - `docs/superpowers/plans/2026-07-04-t2-4-rml-full-mapping.md`
- Implemented files:
  - `src/nl2sparql/kg/rml/full_mapping.ttl`
  - `src/nl2sparql/kg/rml/run_morph_full.py`
  - `tests/unit/test_rml_full.py`
  - `tests/fixtures/rml/full/`
- Focused local verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_rml_full.py -q
  ```
  Result: `9 passed, 51 warnings`.
- CLI help smoke:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run python src/nl2sparql/kg/rml/run_morph_full.py --help
  ```
  Result: exit `0`.

## Next live evidence step

Run only when enough disk/time is available:

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run python src/nl2sparql/kg/rml/run_morph_full.py --prepare-only

UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
uv run python src/nl2sparql/kg/rml/run_morph_full.py --force --chunk-rows 100000
```

After live materialization, record output size, triple count, wall time, TDB2 load command, Fuseki query benchmark, and TDB2 disk footprint here.

## Evidence — 2026-07-04 Chunked runner update

- Root cause: original `--force` path called `morph_kgc.materialize()` once for all full CSV files, keeping the full RDFLib graph in memory until final serialization.
- Fix: `--force` now uses `materialize_full_chunked()` by default. Each chunk writes bounded temporary CSV slices, materializes one chunk, appends chunk N-Triples to `data/processed/full/output.nt`, and releases the chunk graph.
- Controls:
  - `--chunk-rows`: source rows per chunk, default `100000`.
  - `--number-of-processes`: Morph-KGC process count per chunk, default `1`.
  - `--single-shot`: explicit opt-in to the old all-at-once materialization path.
- Focused verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_rml_full.py -q
  ```
  Result: `10 passed`.
