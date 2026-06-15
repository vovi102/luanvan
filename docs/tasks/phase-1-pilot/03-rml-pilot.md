# T1.3 — Pilot: RML Mapping với 100 rows

## Mục tiêu

Viết RML rules mapping CSV pilot → TTL, chạy Morph-KGC, load TTL vào Fuseki, query thành công.

## Bối cảnh & lý do

Đây là bước pilot 3 — gấp khúc khó nhất của Plan A. Nếu RML mapping chạy được với 100 rows, có cơ sở tin Plan A khả thi cho 1 tháng dữ liệu (Phase 2).

**Nếu task này tốn >1 tuần → trigger Pivot Point #1 (xem `phase-2-kg/06-pivot-decision.md`).**

## Phụ thuộc

- T1.1 — EthOn loaded (để biết namespace/property).
- T1.2 — CSV pilot tồn tại.

## Đầu vào

- 4 file CSV trong `data/raw/pilot/`.
- EthOn ontology cho namespace tham chiếu.

## Đầu ra

- File `src/nl2sparql/kg/rml/pilot_mapping.ttl` chứa RML rules.
- File `src/nl2sparql/kg/rml/run_morph_pilot.py` chạy Morph-KGC.
- File `data/processed/pilot/output.ttl` (output TTL).
- Notebook `notebooks/04_rml_pilot.ipynb` upload TTL vào Fuseki + chạy 3 query test.

## Acceptance criteria

- [ ] Morph-KGC chạy không crash.
- [ ] Output TTL parse được bằng `rdflib`.
- [ ] Triple count ≥ 5 × 100 = 500 (vì mỗi tx tạo nhiều triple: type, from, to, value, timestamp, ...).
- [ ] Upload vào Fuseki dataset `pilot-kg`.
- [ ] 3 SPARQL queries chạy được, trả kết quả khớp với expected số rows.

## Hướng dẫn triển khai

1. **RML mapping `pilot_mapping.ttl`:**

   ```turtle
   @prefix rr: <http://www.w3.org/ns/r2rml#> .
   @prefix rml: <http://semweb.mmlab.be/ns/rml#> .
   @prefix ql: <http://semweb.mmlab.be/ns/ql#> .
   @prefix : <https://thesis.example.org/eth-kg/> .
   @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

   # ---------- Mapping cho transactions ----------
   <#TransactionMap> a rr:TriplesMap ;
       rml:logicalSource [
           rml:source "data/raw/pilot/transactions_pilot.csv" ;
           rml:referenceFormulation ql:CSV
       ] ;
       rr:subjectMap [
           rr:template "https://thesis.example.org/eth-kg/tx/{hash}" ;
           rr:class :Transaction
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasFromAddress ;
           rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/addr/{from_address}" ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasToAddress ;
           rr:objectMap [ rr:template "https://thesis.example.org/eth-kg/addr/{to_address}" ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasValue ;
           rr:objectMap [ rml:reference "value" ; rr:datatype xsd:decimal ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasTimestamp ;
           rr:objectMap [ rml:reference "block_timestamp" ; rr:datatype xsd:dateTime ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasGasUsed ;
           rr:objectMap [ rml:reference "gas" ; rr:datatype xsd:integer ]
       ] .

   # ---------- Mapping cho blocks ----------
   <#BlockMap> a rr:TriplesMap ;
       rml:logicalSource [
           rml:source "data/raw/pilot/blocks_pilot.csv" ;
           rml:referenceFormulation ql:CSV
       ] ;
       rr:subjectMap [
           rr:template "https://thesis.example.org/eth-kg/block/{number}" ;
           rr:class :Block
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasBlockNumber ;
           rr:objectMap [ rml:reference "number" ; rr:datatype xsd:integer ]
       ] ;
       rr:predicateObjectMap [
           rr:predicate :hasTimestamp ;
           rr:objectMap [ rml:reference "timestamp" ; rr:datatype xsd:dateTime ]
       ] .

   # NOTE: Mapping cho token_transfers, contracts — viết tương tự, để pilot không cần tất cả.
   ```

2. **Run script `run_morph_pilot.py`:**
   ```python
   import morph_kgc

   config = """
   [DataSource1]
   mappings: src/nl2sparql/kg/rml/pilot_mapping.ttl
   """
   g = morph_kgc.materialize(config)
   g.serialize(destination="data/processed/pilot/output.ttl", format="turtle")
   print(f"Triples: {len(g)}")
   ```

3. **Upload Fuseki:**
   ```bash
   # Tạo dataset pilot-kg
   curl -X POST "http://localhost:3030/$/datasets?dbName=pilot-kg&dbType=mem"

   # Upload data
   curl -X POST -H "Content-Type: text/turtle" \
        --data-binary @data/processed/pilot/output.ttl \
        http://localhost:3030/pilot-kg/data
   ```

4. **3 queries test trong notebook:**

   ```sparql
   # Query 1: Đếm transactions
   PREFIX : <https://thesis.example.org/eth-kg/>
   SELECT (COUNT(?tx) AS ?n) WHERE { ?tx a :Transaction }
   # Expected: 100
   ```

   ```sparql
   # Query 2: List transactions with value > 1 ETH
   PREFIX : <https://thesis.example.org/eth-kg/>
   PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
   SELECT ?tx ?value WHERE {
     ?tx a :Transaction ; :hasValue ?value .
     FILTER(?value > 1000000000000000000)
   }
   ```

   ```sparql
   # Query 3: Group by from_address
   PREFIX : <https://thesis.example.org/eth-kg/>
   SELECT ?from (COUNT(?tx) AS ?n_tx) WHERE {
     ?tx :hasFromAddress ?from .
   } GROUP BY ?from ORDER BY DESC(?n_tx) LIMIT 10
   ```

5. **Note kết quả vào `05-DECISION_LOG.md`:**
   - Số triples thực tế ra bao nhiêu.
   - Có gì bất ngờ (NULL handling, datatype mismatch, ...).
   - **Quyết định:** dùng Morph-KGC hay chuyển RMLMapper.

## Rủi ro & note

- **NULL `to_address` trong CSV** → RML mapping mặc định sẽ tạo URI `addr/None`, không hợp lệ. Cần thêm `rr:objectMap` với `rr:termType rr:IRI` + lọc NULL bằng `rml:logicalSource` query (Morph-KGC hỗ trợ SQL views).
  - Workaround đơn giản nhất: xóa rows NULL trong CSV trước khi map. Pilot OK; production cần handle proper.
- **Datatype `xsd:decimal` cho `value`:** Morph-KGC sẽ giữ chính xác. RDF không có "wei vs ETH"; lưu raw wei (xem `03-ONTOLOGY_REFERENCE.md`).
- **CSV BigQuery có quote escaping** đặc biệt với cột chứa NULL. Test parse bằng pandas trước khi feed vào Morph-KGC.
- **Morph-KGC bug** đôi khi với `xsd:dateTime` format. Fallback: convert timestamp sang ISO format trong CSV trước.

## Estimated effort

1-2 ngày. **Nếu vượt 1 tuần → cảnh báo Pivot Point #1.**

## Trạng thái

`todo`
