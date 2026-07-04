# T3.1 — Query Template Library (~25-30 templates)

## Mục tiêu

Thiết kế ~25-30 SPARQL query templates phủ 80% use case blockchain analytics, mỗi template có metadata (slots, difficulty, category) để generation pipeline (T3.2) dùng được.

## Bối cảnh & lý do

Templates là xương sống của synthetic data pipeline. Chất lượng và đa dạng templates quyết định chất lượng dataset training.

**Lưu ý cho coverage:** templates phải đủ đa dạng để cover các pattern thực tế, không phải chỉ "filter by value" lặp đi lặp lại.

## Phụ thuộc

- T2.1 — Ontology đã chốt.
- T2.2 — Entity dictionary có (cho entity slots).

## Đầu vào

- Ontology `eth-kg-extension-v0.1.0.ttl`.
- Competency questions từ T2.1.
- Entity dictionary.

## Đầu ra

- File `src/nl2sparql/dataset/templates/templates.json` chứa ~25-30 templates.
- File `src/nl2sparql/dataset/templates/README.md` document format + cách dùng.
- Notebook `notebooks/07_template_validate.ipynb` — chạy mỗi template với entity sample → query Fuseki → verify ra kết quả.

## Acceptance criteria

- [ ] ≥25 templates.
- [ ] Mỗi template có ≥1 example fill-in chạy thành công trên Fuseki.
- [ ] Phân bố difficulty: ≥30% Easy, ≥40% Medium, ≥20% Hard.
- [ ] Phân bố category: cover ≥6 categories (xem dưới).
- [ ] Document format chi tiết.

## Local automation scaffold

- [x] `src/nl2sparql/dataset/templates/templates.json` có 25 SPARQL templates.
- [x] Template schema có `slots`, `sparql_template`, `nl_seed`, `expected_columns`, `ontology_elements`, và `example_fill`.
- [x] Phân bố difficulty đạt yêu cầu: 8 easy, 11 medium, 6 hard.
- [x] Category coverage đạt yêu cầu: cover 10 categories.
- [x] `src/nl2sparql/dataset/templates/README.md` document schema, slot types, và Fuseki validation workflow.
- [x] `notebooks/07_template_validate.ipynb` là notebook unexecuted để render templates và chuẩn bị Fuseki validation.
- [x] Unit tests verify count, uniqueness, distribution, placeholder consistency, expected SELECT columns, README, và notebook contract.
- [x] Live Fuseki execution vẫn pending cho đến khi full KG từ T2.4 được load.

## Hướng dẫn triển khai

### Format template

```json
{
  "id": "T_TX_TOP_N_BY_VALUE",
  "name": "Top N transactions by value in time range",
  "category": "transaction_aggregation",
  "difficulty": "medium",
  "slots": {
    "n": {"type": "integer", "default_range": [5, 100]},
    "start_date": {"type": "date", "default_range": ["2024-01-01", "2024-12-31"]},
    "end_date": {"type": "date", "default_range": ["2024-01-01", "2024-12-31"], "constraint": "after start_date"}
  },
  "sparql_template": "PREFIX : <https://thesis.example.org/eth-kg/>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\nSELECT ?tx ?value WHERE {\n  ?tx a :Transaction ;\n      :hasValue ?value ;\n      :hasTimestamp ?ts .\n  FILTER(?ts >= \"{start_date}T00:00:00Z\"^^xsd:dateTime)\n  FILTER(?ts < \"{end_date}T00:00:00Z\"^^xsd:dateTime)\n} ORDER BY DESC(?value) LIMIT {n}",
  "nl_seed": "What are the top {n} transactions by ETH amount between {start_date} and {end_date}?",
  "expected_columns": ["tx", "value"],
  "ontology_elements": [":Transaction", ":hasValue", ":hasTimestamp"]
}
```

### Categories

1. **`simple_filter`** — đơn giản, 1 ràng buộc (e.g. "transactions over 1000 ETH").
2. **`time_range`** — filter theo thời gian.
3. **`entity_lookup`** — query về 1 entity cụ thể (e.g. "all txs from Binance").
4. **`transaction_aggregation`** — count/sum/avg trên transactions.
5. **`top_k`** — ORDER BY + LIMIT.
6. **`multi_hop`** — join 2+ entity (e.g. "DEX that received ETH from a mixer").
7. **`class_level`** — query bằng class chứ không instance (e.g. "any major DEX").
8. **`token_specific`** — về ERC20/ERC721 tokens.
9. **`comparison`** — between 2 entities (e.g. "compare Binance vs Coinbase tx volume").
10. **`temporal_pattern`** — time-based grouping (e.g. "tx by hour of day").

### 25 templates đề xuất (đảm bảo cover):

**Easy (~10 templates):**
1. `T_COUNT_TX_IN_RANGE` — count tx trong khoảng thời gian.
2. `T_LIST_TX_FROM_ENTITY` — list tx từ 1 entity (Binance).
3. `T_LIST_TX_TO_ENTITY` — list tx đến 1 entity.
4. `T_FILTER_BY_VALUE` — tx > X ETH.
5. `T_LIST_TX_BY_CATEGORY` — tx liên quan tới class (e.g. exchange).
6. `T_TOKEN_TRANSFERS_OF_TOKEN` — list transfers của 1 token.
7. `T_BLOCK_BY_NUMBER` — block info by number.
8. `T_TX_BY_HASH` — info of 1 transaction.
9. `T_ACCOUNT_BALANCE_LIKE` — top recipients of an entity.
10. `T_GAS_USED_IN_RANGE` — total gas used in time range.

**Medium (~10 templates):**
11. `T_TX_BETWEEN_TWO_ENTITIES` — tx từ A đến B.
12. `T_TOP_N_TX_BY_VALUE` — top N theo value.
13. `T_TOP_N_SENDERS_TO_ENTITY` — top N senders to Binance.
14. `T_TX_GROUPED_BY_OWNER` — tx grouped by exchange owner.
15. `T_TX_GROUPED_BY_HOUR` — tx by hour of day.
16. `T_LARGE_TX_TO_MIXER` — tx >X to any mixer.
17. `T_TX_FROM_DEX_TO_EOA` — tx từ DEX class đến EOA.
18. `T_TOKEN_VOLUME_IN_RANGE` — total token transferred in range.
19. `T_NEW_CONTRACTS_DEPLOYED` — contracts created in time range.
20. `T_ENTITIES_BY_CATEGORY_COUNT` — count by category.

**Hard (~5-7 templates):**
21. `T_DEX_TO_MIXER_FLOW` — multi-hop: DEX → EOA → Mixer.
22. `T_REPEATED_TX_PATTERN` — tx repeated pattern (round-trip detection).
23. `T_HIGH_VOLUME_NEW_ACCOUNT` — new account (within last week) with high tx volume.
24. `T_CROSS_EXCHANGE_FLOW` — flow between 2 exchanges.
25. `T_MIXER_USERS_AFTER_RECEIVING` — addresses that used mixer after receiving from exchange.
26. `T_TIME_DECAY_FILTER` — tx within X minutes of a specific event (block).

### Cách build template

1. Bắt đầu từ competency questions (T2.1) đã có.
2. Mỗi competency question → template tương ứng:
   - Identify slots (numbers, names, dates).
   - Replace bằng `{slot_name}`.
   - Fix SPARQL syntax.
3. Verify chạy được trên Fuseki với 1 example fill-in:
   ```python
   import json
   from SPARQLWrapper import SPARQLWrapper, JSON

   templates = json.load(open("src/nl2sparql/dataset/templates/templates.json"))
   sw = SPARQLWrapper("http://localhost:3030/eth-kg/sparql")
   sw.setReturnFormat(JSON)

   for t in templates:
       # fill slots với default
       slots = {k: v.get("default_range", [None])[0] for k, v in t["slots"].items()}
       q = t["sparql_template"].format(**slots)
       sw.setQuery(q)
       try:
           results = sw.query().convert()
           print(f"✅ {t['id']}: {len(results['results']['bindings'])} rows")
       except Exception as e:
           print(f"❌ {t['id']}: {e}")
   ```

### Slot type system

```json
{
  "n": {"type": "integer", "default_range": [5, 100]},
  "value_threshold_eth": {"type": "decimal_eth", "default_range": [1, 1000]},
  "address": {"type": "ethereum_address"},
  "entity_owner": {"type": "entity_owner"},  // pull from entity dict
  "entity_concept": {"type": "concept_class"},  // exchange, mixer, DEX, ...
  "token_symbol": {"type": "token_symbol"},  // USDT, WETH, ...
  "start_date": {"type": "date"},
  "end_date": {"type": "date"},
  "duration": {"type": "duration"}  // last week, last 30 days
}
```

Pipeline T3.2 sẽ sample slot values theo type — tránh sinh slot values invalid.

## Rủi ro & note

- **Đừng template quá rigid.** SPARQL có nhiều cách viết tương đương. Ở Phase 3, sẽ paraphrase câu hỏi nhưng KHÔNG paraphrase SPARQL — giữ canonical form để dataset consistent.
- **Test mỗi template với 3-5 fill-in khác nhau** để kiểm tra robustness.
- **Hard templates có thể trả về 0 rows** với một số fill-in (data thật không có pattern). Đó là OK; tag những fill-in đó để T3.2 prefer fill-in cho ra kết quả.
- **Slot interaction:** end_date phải > start_date. Express trong constraint dạng `"after start_date"` để T3.2 enforce.

## Estimated effort

3-5 ngày (đa phần là design + verify).

## Trạng thái

`scaffold done; Fuseki execution pending`

Local template library đã hoàn tất và được kiểm tra offline. Acceptance criterion "Mỗi template có ≥1 example fill-in chạy thành công trên Fuseki" vẫn pending vì full KG live chưa được load.

## Evidence — 2026-07-04 Scaffold

- Branch: `feat/t3-1-query-template-library`.
- Design/spec:
  - `docs/superpowers/specs/2026-07-04-t3-1-query-template-library-design.md`
  - `docs/superpowers/plans/2026-07-04-t3-1-query-template-library.md`
- Implemented files:
  - `src/nl2sparql/dataset/templates/templates.json`
  - `src/nl2sparql/dataset/templates/README.md`
  - `notebooks/07_template_validate.ipynb`
  - `tests/unit/test_query_templates.py`
- Focused local verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_query_templates.py -q
  ```
  Result: `6 passed`.

## Next live evidence step

After T2.4 full KG load, open `notebooks/07_template_validate.ipynb` or port the same logic into a script, execute all 25 rendered `example_fill` queries against Fuseki, and record execution status plus any zero-row but valid queries here.
