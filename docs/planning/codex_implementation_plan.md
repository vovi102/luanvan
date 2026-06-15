# Kế hoạch triển khai chi tiết cho Codex
## Dự án: NL2SPARQL cho Blockchain Knowledge Graph

> **Cách dùng tài liệu này:** Mỗi mục là một "ticket" độc lập có thể giao cho Codex. Mỗi ticket có: mục tiêu, input, output, file cần tạo, acceptance criteria. Codex nên thực hiện theo thứ tự, hoàn thành ticket trước rồi mới sang ticket sau. Khi gặp blocker, dừng lại báo cáo trước khi sang ticket khác.

---

## 0. Nguyên tắc tổng thể cho Codex

### 0.1. Quy ước code

- **Ngôn ngữ chính:** Python 3.11
- **Style:** PEP 8, formatter `ruff`, type hints bắt buộc cho public functions
- **Logging:** dùng `loguru`, không dùng `print()` trong code production
- **Config:** dùng `pydantic-settings` + file `.env` (không hardcode path/key)
- **Testing:** `pytest`, mỗi module có file test tương ứng, coverage tối thiểu 70%
- **Docstring:** Google style, bắt buộc cho public class/function
- **Git commit:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`)

### 0.2. Quy tắc làm việc

1. **Không được skip tests.** Test fail → dừng lại fix, không commit code đỏ.
2. **Không tự ý thay đổi scope.** Nếu thấy ticket không khả thi, ghi vào `docs/memory/05-DECISION_LOG.md` và hỏi trước.
3. **Mỗi ticket = 1 PR.** Branch theo dạng `feat/ticket-XX-short-name`.
4. **Document quyết định.** Sau mỗi ticket, append vào `docs/memory/05-DECISION_LOG.md`: ngày, ticket ID, quyết định kỹ thuật, lý do.
5. **Reproducibility là tối thượng.** Mọi script training/eval đều fix `seed=42`, log đầy đủ config.

### 0.3. Cấu trúc repo

```
nl2sparql-blockchain/
├── README.md
├── pyproject.toml              # Poetry/uv dependencies
├── .env.example
├── .gitignore
├── .github/workflows/ci.yml    # Lint + test
├── docs/
│   ├── memory/                 # Project context + decision log
│   ├── tasks/                  # Backlog theo phase
│   ├── planning/               # Kế hoạch triển khai chi tiết
│   ├── architecture/
│   ├── literature/
│   ├── thesis/
│   └── figures/
├── configs/
│   ├── default.yaml
│   ├── kg_build.yaml
│   ├── train_b3.yaml
│   └── eval.yaml
├── data/                       # gitignore content, giữ folder
│   ├── raw/                    # CSV từ BigQuery
│   ├── interim/                # TTL files
│   ├── processed/              # Dataset cuối
│   ├── kg/                     # TDB2 indexes, TTL lớn
│   ├── entities/               # Entity dictionary
│   └── samples/                # Sample nhỏ có thể commit
├── ontology/
│   ├── ethon_extended.ttl      # Ontology chính
│   ├── shapes.ttl              # SHACL shapes
│   └── examples.ttl            # Test instances
├── mappings/
│   ├── transactions.rml.ttl
│   ├── addresses.rml.ttl
│   └── tokens.rml.ttl
├── src/nl2sparql/
│   ├── __init__.py
│   ├── config.py
│   ├── kg/
│   │   ├── bigquery_extractor.py
│   │   ├── rml_runner.py
│   │   ├── fuseki_client.py
│   │   └── shacl_validator.py
│   ├── linking/
│   │   ├── entity_dictionary.py
│   │   ├── entity_linker.py
│   │   └── schema_linker.py
│   ├── dataset/
│   │   ├── templates.py
│   │   ├── synthesizer.py
│   │   ├── paraphraser.py
│   │   └── validator.py
│   ├── models/
│   │   ├── base.py
│   │   ├── rule_based.py        # B0
│   │   ├── llm_zero_shot.py     # B1, B4
│   │   ├── llm_few_shot.py      # B2, B5
│   │   ├── llm_finetuned.py     # B3
│   │   └── full_system.py       # System đề xuất
│   ├── decoding/
│   │   ├── constrained.py
│   │   └── grammar.py
│   ├── validation/
│   │   ├── sparql_parser.py
│   │   ├── ontology_validator.py
│   │   └── post_validator.py
│   ├── evaluation/
│   │   ├── metrics.py
│   │   ├── runner.py
│   │   └── analyzer.py
│   └── demo/
│       ├── app.py
│       └── examples.py
├── scripts/
│   ├── 01_extract_bigquery.py
│   ├── 02_build_ontology.py
│   ├── 03_run_rml.py
│   ├── 04_load_fuseki.py
│   ├── 05_validate_shacl.py
│   ├── 10_build_entity_dict.py
│   ├── 20_generate_dataset.py
│   ├── 30_train_b3.py
│   ├── 40_eval_all_baselines.py
│   └── 50_run_demo.py
├── notebooks/
│   ├── 01_kg_exploration.ipynb
│   ├── 02_dataset_analysis.ipynb
│   └── 03_results_analysis.ipynb
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── infrastructure/
    ├── docker/
    ├── kaggle/
    └── hf_spaces/
```

---

## PHASE 0 — Setup môi trường (Tuần 1)

### Ticket 0.1 — Khởi tạo repository

**Mục tiêu:** Repo có cấu trúc đầy đủ, CI chạy được.

**Việc cần làm:**
1. Tạo repo theo cấu trúc mục 0.3.
2. Setup `pyproject.toml` với các dependency cốt lõi:
   - Core: `python>=3.11`, `pydantic>=2`, `pydantic-settings`, `loguru`, `pyyaml`, `click`
   - KG: `rdflib>=7`, `SPARQLWrapper`, `pyshacl`
   - ML: `torch>=2.1`, `transformers>=4.40`, `peft>=0.10`, `datasets`, `accelerate`, `bitsandbytes`
   - NLP: `sentence-transformers>=2.7`, `rapidfuzz`
   - BigQuery: `google-cloud-bigquery`, `pyarrow`
   - Demo: `gradio>=4`
   - Dev: `ruff`, `pytest`, `pytest-cov`, `mypy`, `pre-commit`
3. Tạo `.env.example` với các biến: `FUSEKI_URL`, `FUSEKI_DATASET`, `BIGQUERY_PROJECT`, `OPENROUTER_API_KEY`, `HF_TOKEN`.
4. Setup `pre-commit` với `ruff` + `mypy`.
5. Tạo `.github/workflows/ci.yml`: lint + test trên Python 3.11.
6. Tạo `README.md` với phần Quickstart (placeholder).
7. Tạo `docs/memory/05-DECISION_LOG.md` với template.

**Acceptance criteria:**
- [ ] `git clone && uv sync && pytest` chạy OK (kể cả khi chưa có test thật, tạo 1 test placeholder).
- [ ] `pre-commit run --all-files` pass.
- [ ] CI workflow xanh khi push.

---

### Ticket 0.2 — Module config

**File:** `src/nl2sparql/config.py`

**Việc cần làm:**
- Class `Settings` (BaseSettings) với các nhóm: `KGSettings`, `LLMSettings`, `DataSettings`, `EvalSettings`.
- Hỗ trợ load từ YAML qua `configs/default.yaml`.
- Validation: path tồn tại, URL hợp lệ.
- Singleton `get_settings()` cached.

**Test:** `tests/unit/test_config.py` — load default config, override env, validation error khi sai path.

**Acceptance:**
- [ ] `from nl2sparql.config import get_settings; s = get_settings()` chạy không lỗi.
- [ ] Override qua biến môi trường hoạt động.

---

## PHASE 1 — Knowledge Graph Construction (Tuần 2-6)

> **⚠️ Đây là phase rủi ro nhất. Pivot Point #1 nằm ở cuối Ticket 1.5. Nếu fail → chuyển Plan B (NL2SQL).**

### Ticket 1.1 — Setup Fuseki local

**Mục tiêu:** Có Fuseki chạy local, accessible qua HTTP, có thể load/query TTL.

**File:** `infrastructure/docker-compose.fuseki.yml`

**Việc cần làm:**
1. Docker compose dùng image `stain/jena-fuseki:latest`.
2. Mount volume cho persistent dataset.
3. Expose port 3030.
4. Cấu hình admin password qua env.
5. Script `scripts/setup_fuseki.sh` để start và tạo dataset `ethereum_kg` (TDB2).
6. Tạo `src/nl2sparql/kg/fuseki_client.py`:
   - Class `FusekiClient` với methods: `upload_ttl(file_path)`, `query(sparql_str)`, `update(sparql_str)`, `clear_dataset()`, `count_triples()`.
   - Dùng `SPARQLWrapper`.
   - Retry logic với `tenacity`.
7. Smoke test: load file `examples.ttl` (5 triples), query `SELECT * WHERE { ?s ?p ?o }`.

**Acceptance:**
- [ ] `docker-compose up` xong, web UI Fuseki access được tại `localhost:3030`.
- [ ] `pytest tests/integration/test_fuseki.py` pass (test này cần Fuseki đang chạy, mark `@pytest.mark.integration`).
- [ ] Query test trả về đúng số triples.

---

### Ticket 1.2 — BigQuery data extractor

**File:** `src/nl2sparql/kg/bigquery_extractor.py` + `scripts/01_extract_bigquery.py`

**Mục tiêu:** Extract subset Ethereum data trong 1 tháng gần nhất (giới hạn để không quá 1TB free quota).

**Việc cần làm:**
1. Service account JSON qua env `GOOGLE_APPLICATION_CREDENTIALS`.
2. Extract 4 bảng (lưu dưới `data/raw/`):
   - `transactions.csv` — top 1M transactions có `value > 1 ETH` trong 30 ngày gần nhất, partition by date.
   - `token_transfers.csv` — top 500k transfers ERC-20 trong cùng khoảng.
   - `addresses_labeled.csv` — join với labels từ Etherscan/Dune (sẽ làm ở Ticket 1.6).
   - `blocks.csv` — block metadata (number, timestamp, miner) cho khoảng đó.
3. Mỗi function có param `dry_run=True` để in cost trước khi chạy thật.
4. Cache: nếu file đã tồn tại và không có flag `--force`, skip.
5. Log dung lượng query đã dùng (ước tính từ `query_job.total_bytes_processed`).

**Acceptance:**
- [ ] Chạy `python scripts/01_extract_bigquery.py --dry-run` in ra cost ước tính.
- [ ] Chạy thật → có 4 file CSV, tổng ~1-2 GB.
- [ ] Schema CSV được document trong `docs/data_schema.md`.

---

### Ticket 1.3 — Ontology design

**File:** `ontology/ethon_extended.ttl` + `docs/ontology_design.md`

**Mục tiêu:** Ontology 15-20 class, ~30 property, kế thừa EthOn.

**Việc cần làm:**
1. Download EthOn từ `https://github.com/ConsenSys/EthOn` làm base.
2. Định nghĩa namespace mới: `@prefix bckg: <https://example.org/blockchain-kg/> .`
3. Class hierarchy gợi ý:
   - `bckg:Transaction` (subClassOf `ethon:Tx`)
   - `bckg:Address`, `bckg:ContractAddress`, `bckg:EOA`
   - `bckg:Entity` (real-world entity), với subclass: `bckg:Exchange`, `bckg:Mixer`, `bckg:DEXProtocol`, `bckg:LendingProtocol`, `bckg:Bridge`, `bckg:NFTMarketplace`
   - `bckg:Token`, `bckg:ERC20Token`, `bckg:NFT`
   - `bckg:Block`
4. Properties chính (mỗi property phải có `rdfs:label`, `rdfs:comment` chi tiết, `:exampleUsage`, `rdfs:domain`, `rdfs:range`):
   - `bckg:hasFrom`, `bckg:hasTo`, `bckg:hasValue`, `bckg:hasGasUsed`, `bckg:hasTimestamp`, `bckg:inBlock`
   - `bckg:controlledBy` (Address → Entity)
   - `bckg:transferredToken`, `bckg:tokenAmount`
   - `bckg:hasLabel`, `bckg:hasAlias`
5. Documentation phong phú (quan trọng cho schema linker):
   ```turtle
  bckg:hasFrom rdfs:label "has from address" ;
    rdfs:comment "The sender address of an Ethereum transaction.
                  Use this for questions about who sent/initiated/originated
                   a transaction. Differs from :initiatedBy in meta-tx context." ;
     bckg:exampleUsage "?tx bckg:hasFrom ?addr ." ;
     bckg:naturalLanguageHints "sender, from, originator, initiator, sent by" ;
     rdfs:domain bckg:Transaction ;
     rdfs:range bckg:Address .
   ```
6. Validate ontology bằng Protégé (manual) + `rdflib` parse check.

**Acceptance:**
- [ ] File parse OK bằng `rdflib.Graph().parse("ontology/ethon_extended.ttl")`.
- [ ] Có ít nhất 15 class và 25 property.
- [ ] Mỗi property có ít nhất `rdfs:label`, `rdfs:comment`, `bckg:naturalLanguageHints`.
- [ ] Document `docs/ontology_design.md` giải thích các quyết định.

---

### Ticket 1.4 — SHACL shapes

**File:** `ontology/shapes.ttl` + `src/nl2sparql/kg/shacl_validator.py`

**Việc cần làm:**
1. Định nghĩa shapes constraint:
   - `Transaction` phải có `hasFrom`, `hasTo`, `hasValue`, `hasTimestamp`, `inBlock`.
   - `Address` phải match regex `^0x[a-fA-F0-9]{40}$`.
   - `hasValue` phải là `xsd:decimal`, `>= 0`.
   - `hasTimestamp` phải là `xsd:dateTime`.
2. `ShaclValidator.validate(graph_path) -> ValidationReport` dùng `pyshacl`.
3. Report bao gồm: số violations, sample 10 violation đầu, summary by shape.

**Acceptance:**
- [ ] Validate `examples.ttl` (cố tình có 2 lỗi) → detect đúng 2 violations.
- [ ] Test trong `tests/unit/test_shacl.py`.

---

### Ticket 1.5 — RML mapping

**File:** `mappings/*.rml.ttl` + `src/nl2sparql/kg/rml_runner.py` + `scripts/03_run_rml.py`

**Mục tiêu:** Convert CSV → TTL theo RML standard.

**Việc cần làm:**
1. Dùng **Morph-KGC** (Python-native, dễ hơn RMLMapper Java): `pip install morph-kgc`.
2. Viết RML mapping cho 3 nguồn:
   - `transactions.rml.ttl`: mỗi row → instance `bckg:Transaction` với hash là IRI.
   - `addresses.rml.ttl`: address → `bckg:Address` hoặc `bckg:ContractAddress`.
   - `tokens.rml.ttl`: token transfers.
3. `RMLRunner.run(mapping_file, output_ttl)` wrap `morph_kgc.materialize`.
4. Output từng batch 100k rows, merge cuối.
5. Script `03_run_rml.py` chạy toàn bộ với progress bar (tqdm).

**Acceptance:**
- [ ] Output TTL parse OK bằng rdflib.
- [ ] Số instance `bckg:Transaction` ≈ số dòng trong CSV.
- [ ] Sample 5 instance bằng SPARQL local check OK.

---

### 🚦 PIVOT POINT #1 — Cuối Ticket 1.5

**GO criteria (cần đủ 4):**
- [ ] Fuseki load TTL thành công, query test cho kết quả đúng.
- [ ] Ontology cover ≥80% trong 50 câu hỏi mẫu.
- [ ] Entity dictionary có ≥3000 entries (Ticket 1.6 dưới đây).
- [ ] Tổng thời gian từ Ticket 1.1 đến đây ≤ 5 tuần.

**NO-GO → chuyển Plan B (NL2SQL):**
- Bỏ qua Phase 1 từ Ticket 1.7 trở đi, dùng schema BigQuery trực tiếp.
- Giữ lại: Entity dictionary (1.6), data pipeline, evaluation framework.
- Phase 4 train trên cặp NL-SQL thay vì NL-SPARQL.

**Hành động:** Codex dừng, viết `docs/pivot_decision_phase1.md` với checklist GO/NO-GO, trình bạn quyết định.

---

### Ticket 1.6 — Entity dictionary builder

> **Quan trọng:** Có thể chạy song song với 1.1-1.5, không phụ thuộc Fuseki. Nên start sớm.

**File:** `src/nl2sparql/linking/entity_dictionary.py` + `scripts/10_build_entity_dict.py`

**Mục tiêu:** Có ≥5000 entries (entity_name → list of addresses + class).

**Schema entry:**
```python
{
  "canonical_name": "Binance",
  "aliases": ["binance", "binance exchange", "BNB exchange"],
  "entity_class": "Exchange",
  "addresses": ["0x28C6c06298d514Db089934071355E5743bf21d60", ...],
  "confidence": "high",
  "source": "etherscan_label_cloud"
}
```

**Việc cần làm:**
1. **Source 1 — Etherscan Label Cloud:** scrape (có rate limit) hoặc dùng public dataset ETH labels trên Kaggle.
2. **Source 2 — Dune Analytics:** queries public về `labels.all` (cần Dune API free tier).
3. **Source 3 — OFAC SDN list** (sanctioned addresses) cho compliance use case.
4. **Source 4 — DefiLlama protocol addresses.**
5. **Source 5 — Manual curation** top 100 entities (Binance, Coinbase, Tornado Cash, Uniswap, Aave, ...).
6. Class `EntityDictionary`:
   - `load(path)`, `save(path)` (JSON + Parquet).
   - `lookup_by_name(name) -> List[Entry]`
   - `lookup_by_address(addr) -> Optional[Entry]`
   - `lookup_by_class(class_name) -> List[Entry]`
   - `add_entry(entry)`, `merge(other_dict)`.
7. Validate sample 50 entries bằng manual review (script tạo file `data/entities/sample_for_review.csv`).

**Acceptance:**
- [ ] File `data/entities/dictionary.parquet` có ≥3000 entries.
- [ ] Top 100 entity được manual verify, log trong `data/entities/manual_verified.csv`.
- [ ] Test unit cho lookup methods.

---

### Ticket 1.7 — Load KG vào Fuseki & test

**Script:** `scripts/04_load_fuseki.py` + `scripts/05_validate_shacl.py`

**Việc cần làm:**
1. Pipeline: ontology + RML output + entity links → upload vào Fuseki dataset.
2. Build entity links: cho mỗi address trong CSV, lookup entity dictionary, generate triples `?addr bckg:controlledBy ?entity`.
3. Validate toàn bộ KG bằng SHACL → report.
4. Performance test: 5 query mẫu (đơn giản → phức tạp), đo latency. Yêu cầu < 2s/query đơn giản, < 5s/query phức tạp.
5. Tạo notebook `notebooks/01_kg_exploration.ipynb` với 10 SPARQL example queries.

**Acceptance:**
- [ ] KG có ≥1M triples.
- [ ] SHACL validation: violations < 1% (chấp nhận noise nhỏ).
- [ ] 5 query mẫu đều chạy < 5s.
- [ ] Notebook chạy end-to-end OK.

---

## PHASE 2 — Linking Components (Tuần 7-10)

### Ticket 2.1 — Schema linker

**File:** `src/nl2sparql/linking/schema_linker.py`

**Mục tiêu:** Cho câu hỏi NL → trả về top-K (class, property) liên quan.

**Approach:**
1. **Indexing pha offline:**
   - Parse ontology, với mỗi class/property tạo "document":
     ```
     "{label}. {comment}. Examples: {examples}. Hints: {nlHints}"
     ```
   - Encode bằng `sentence-transformers/all-mpnet-base-v2`.
   - Lưu embeddings vào file `data/processed/ontology_embeddings.npz`.
2. **Inference:**
   - Encode question.
   - Cosine similarity → top-K classes + top-K properties.
   - Hybrid: kết hợp với BM25 (rapid hit cho keyword exact match).
3. Class `SchemaLinker`:
   - `__init__(ontology_path, model_name)`
   - `index() -> None` (build embeddings)
   - `link(question: str, top_k: int = 5) -> SchemaLinkResult`
4. `SchemaLinkResult` chứa: `classes: List[(uri, score)]`, `properties: List[(uri, score)]`.

**Acceptance:**
- [ ] Test trên 20 câu hỏi mẫu (`tests/fixtures/schema_link_test.json`), top-3 recall ≥ 70%.
- [ ] Indexing < 30s, inference < 100ms/query.

---

### Ticket 2.2 — Entity linker (4-stage)

**File:** `src/nl2sparql/linking/entity_linker.py`

**Việc cần làm:**
1. Class `EntityLinker(dictionary: EntityDictionary, embedder)`.
2. Method `link(text: str) -> List[EntityMention]`:
   - **Bước 1:** NER với `spaCy` model `en_core_web_lg` để extract candidate spans (ORG, PERSON, MONEY...).
   - **Bước 2 (Stage A — Exact match):** lower-case match span vs `canonical_name` + `aliases`. Score = 1.0.
   - **Bước 3 (Stage B — Fuzzy):** với spans chưa match, dùng `rapidfuzz.process.extract` với `ratio >= 0.85`. Score = ratio/100.
   - **Bước 4 (Stage C — Embedding):** encode span và canonical_names, cosine sim ≥ 0.75.
   - **Bước 5 (Stage D — Fallback):** không match → flag `unknown=True`, kèm clarification suggestion.
3. `EntityMention`: `{span, start, end, candidates: [(entity_id, score, stage)], chosen: Optional[entity_id]}`.
4. Disambiguation: nếu nhiều candidate cùng score, ưu tiên theo `confidence` của entry và class context (nếu schema linker đã chỉ ra "exchange" thì ưu tiên Exchange).

**Acceptance:**
- [ ] Test 30 câu hỏi (`tests/fixtures/entity_link_test.json`) với:
  - Exact: "Binance" → đúng addresses.
  - Alias: "TC", "tornado.cash" → Tornado Cash.
  - Fuzzy: "Binanc" (typo) → Binance.
  - Class: "any major DEX" → flag class-level.
- [ ] Precision@1 ≥ 80%, Recall ≥ 75%.

---

### Ticket 2.3 — Class-level resolver

**File:** mở rộng `entity_linker.py`.

**Việc cần làm:**
1. Detect class-level mentions: "exchanges", "mixers", "any DEX", "all lending protocols".
2. Maintain mapping: `{"exchange": bckg:Exchange, "mixer": bckg:Mixer, ...}` + plural/synonym handling.
3. Trả về class URI thay vì instance addresses, để LLM generator biết dùng `?addr a bckg:Exchange` thay vì `VALUES`.

**Acceptance:**
- [ ] Test 15 class-level questions, recall ≥ 85%.

---

## PHASE 3 — Dataset Generation (Tuần 9-13, song song Phase 2 cuối)

### Ticket 3.1 — SPARQL templates

**File:** `src/nl2sparql/dataset/templates.py`

**Mục tiêu:** 25-30 templates phủ 80% use case.

**Cấu trúc template:**
```python
@dataclass
class Template:
    id: str
    difficulty: Literal["easy", "medium", "hard"]
    sparql_template: str  # với placeholders {entity_from}, {time_start}, ...
    slots: List[SlotSpec]
    nl_seeds: List[str]   # 3-5 câu hỏi NL trang trọng tương ứng
    competency_question: str
```

**Template categories cần có:**
1. **Easy (5-7 templates):** Single-hop lookup. Ví dụ: count tx của 1 address, balance check, latest tx.
2. **Medium (10-12 templates):** 2-hop, filter, aggregation. Ví dụ: "transfers from X to Y in time range", "top 10 receivers from X".
3. **Hard (8-10 templates):** Multi-hop, subquery, class-level, negation. Ví dụ: "addresses interacted with Tornado Cash but not before 2023", "DEXes with > 1B volume".

**Acceptance:**
- [ ] ≥25 templates, mỗi template có ≥3 NL seeds.
- [ ] Mỗi template được test execute trên Fuseki cho ra ≥1 result với entity thật.
- [ ] File `tests/fixtures/templates_smoke.json` documenting tất cả templates.

---

### Ticket 3.2 — Synthetic data pipeline

**File:** `src/nl2sparql/dataset/synthesizer.py` + `scripts/20_generate_dataset.py`

**Quy trình 5 bước (theo design doc):**

#### Bước A: Sinh SPARQL từ template
- Random fill slots với entity từ KG (sample address có `bckg:controlledBy`).
- Đảm bảo query thực sự return ≥1 result (filter ra "dead" queries).

#### Bước B: SPARQL → Formal NL
- Dùng OpenRouter API (Llama 3 70B free tier) với prompt:
  ```
  Convert this SPARQL query to a formal English question.
  Use entity names from this mapping: {entity_map}.
  SPARQL: {sparql}
  ```
- Output: 1 câu hỏi trang trọng.

#### Bước C: Paraphrase → Casual NL
- Mỗi formal question → 3 casual versions với prompt khác nhau:
  - "Make this question sound more casual."
  - "Rewrite in a more conversational tone."
  - "How would a journalist phrase this?"
- Tạo 3 paraphrase per query.

#### Bước D: Add noise (10% sample)
- Typo (random char swap), abbreviation, incomplete sentence, lowercase, punctuation strip.
- Implement với `nlpaug` hoặc custom function.

#### Bước E: Validation sample 5%
- Random 50 cặp → script tạo CSV `data/processed/manual_review_sample.csv`.
- Manual review (bạn làm), upload lại với cột `correct: bool`, `notes`.

**Output structure:**
```jsonl
{
  "id": "syn_00001",
  "nl_question": "How much ETH did Binance send to Coinbase last week?",
  "sparql": "SELECT (SUM(?v) AS ?total) WHERE { ... }",
  "template_id": "T_aggregation_002",
  "difficulty": "medium",
  "entities": ["binance", "coinbase"],
  "noise_added": false,
  "split": "train"
}
```

**Acceptance:**
- [ ] ~1000 cặp train, ~100 validation, distribution Easy:Medium:Hard ≈ 30:50:20.
- [ ] Manual sample 50 cặp có ≥85% correct.
- [ ] Mỗi câu hỏi có ít nhất 1 paraphrase.

---

### Ticket 3.3 — Manual test set (gold)

**File:** `data/processed/test_gold.jsonl` + `scripts/21_test_set_workflow.py`

**Mục tiêu:** 100 cặp test set chất lượng cao, được viết bởi nhiều người độc lập.

**Workflow:**
1. **Pool A** — 3-5 người (cố thể là bạn + bạn bè/đồng nghiệp): viết 100 câu hỏi tiếng Anh **không nhìn ontology**, chỉ biết "system này dùng cho phân tích Ethereum". Output: `data/processed/pool_A_questions.csv`.
2. **Pool B** — bạn + 1 người khác: viết SPARQL gold cho 100 câu hỏi, làm độc lập. Output: 2 file SPARQL.
3. **Pool C** — 1 người review độc lập: với mỗi câu hỏi, có 2 SPARQL. Reviewer chọn cái đúng hoặc viết version 3. Resolution conflict.
4. Final: mỗi câu hỏi có 1 SPARQL gold đã được consensus.
5. Script tự động: validate execute trên Fuseki, đo answer cardinality, gán difficulty (theo số triple pattern + filter + aggregation).

**Acceptance:**
- [ ] 100 cặp NL-SPARQL, mỗi cặp được ≥2 người validate.
- [ ] Difficulty distribution: 30 Easy, 50 Medium, 20 Hard.
- [ ] Tất cả SPARQL execute trên Fuseki không syntax error.

---

### Ticket 3.4 — Dataset validator

**File:** `src/nl2sparql/dataset/validator.py`

**Việc cần làm:**
1. Validate SPARQL syntax bằng `rdflib.plugins.sparql.parser`.
2. Validate execute được trên Fuseki.
3. Detect potential issues: query trả về quá nhiều/ít rows, undefined variables, unused prefixes.
4. Generate report `data/processed/dataset_report.md` với stats: distribution by template, by difficulty, by length.

**Acceptance:**
- [ ] Report tự động generate.
- [ ] 100% queries trong train/test pass syntax check.

---

## PHASE 4 — Baselines (Tuần 14-17)

### Ticket 4.1 — Evaluation framework (LÀM TRƯỚC TIÊN!)

**File:** `src/nl2sparql/evaluation/`

> **Lý do làm trước:** Mọi baseline đều cần evaluator chung. Build framework trước để test apples-to-apples.

**Modules:**

#### `metrics.py`
- `exact_match(pred_sparql, gold_sparql) -> bool` (sau normalize).
- `execution_accuracy(pred, gold, fuseki) -> bool` (so sánh result set, set-based, không order-sensitive nếu không có ORDER BY).
- `answer_f1(pred, gold)` cho aggregation queries (so sánh số/list).
- `syntax_valid(sparql) -> bool`.
- `query_complexity(sparql) -> dict` (số triple pattern, filter, aggregation, subquery).

#### `runner.py`
- Class `EvalRunner(model, dataset, fuseki_client)`.
- `run() -> EvalReport`: chạy model trên toàn dataset, log từng prediction, tính metrics.
- Hỗ trợ `repeat=5` cho variance analysis.
- Output: `results/{model_name}_{timestamp}.json` với raw predictions + metrics.

#### `analyzer.py`
- `compare_models(reports: List[EvalReport])` → bảng so sánh.
- `failure_analysis(report)` → phân loại lỗi: syntax / semantic / hallucination / logic / timeout.
- Generate plots: confusion by difficulty, latency distribution, error type breakdown.

**Acceptance:**
- [ ] Mock model (random) chạy được qua evaluator end-to-end.
- [ ] Test trên 10 câu hỏi gold sample.

---

### Ticket 4.2 — B0: Rule-based baseline

**File:** `src/nl2sparql/models/rule_based.py`

**Approach:**
1. Pattern match câu hỏi vs templates trong `templates.py`.
2. Dùng regex/keyword để fill slots.
3. Entity linking dùng module Phase 2.

**Acceptance:**
- [ ] Coverage ≥ 30% câu hỏi (chấp nhận thấp, đây là lower bound).
- [ ] Eval report generated.

---

### Ticket 4.3 — B1, B4: Zero-shot LLM

**File:** `src/nl2sparql/models/llm_zero_shot.py`

**Việc cần làm:**
1. Class `ZeroShotLLM(model_name, backend)`. Backend: `local_hf`, `openrouter`, `kaggle_api`.
2. Prompt template:
   ```
  You are a SPARQL expert. Convert this English question to SPARQL.

  Available ontology classes: {classes_summary}
  Available properties: {properties_summary}

  Question: {question}

  SPARQL:
   ```
3. B1: `meta-llama/Meta-Llama-3-8B-Instruct` local hoặc Kaggle.
4. B4: `meta-llama/Meta-Llama-3-70B-Instruct` qua OpenRouter.
5. Extract SPARQL từ response (regex, strip markdown fence).

**Acceptance:**
- [ ] Cả B1 và B4 chạy end-to-end trên test set.
- [ ] Latency và cost được log.

---

### Ticket 4.4 — B2, B5: Few-shot LLM

**File:** `src/nl2sparql/models/llm_few_shot.py`

**Việc cần làm:**
1. Kế thừa `ZeroShotLLM`.
2. Select 5 examples từ train set:
   - **Approach 1:** Random fixed (dễ implement, reproducible).
   - **Approach 2:** Similarity-based retrieval (encode question, top-5 nearest từ train).
   - Implement cả 2, mặc định Approach 2.
3. Prompt template insert examples trước question chính.

**Acceptance:**
- [ ] B2 và B5 chạy OK, cải thiện so với zero-shot trên ≥3% F1.

---

### Ticket 4.5 — B3: Fine-tuned LLM với QLoRA

**File:** `src/nl2sparql/models/llm_finetuned.py` + `infrastructure/kaggle/train_b3.ipynb` + `scripts/30_train_b3.py`

**Việc cần làm:**
1. Notebook Kaggle dùng GPU T4 (×2 nếu được).
2. Setup QLoRA 4-bit:
   - Model: `meta-llama/Meta-Llama-3-8B-Instruct`.
   - bnb config: `load_in_4bit=True`, `bnb_4bit_quant_type="nf4"`, `bnb_4bit_compute_dtype=torch.bfloat16`.
   - LoRA config: `r=16`, `alpha=32`, target modules: `["q_proj", "k_proj", "v_proj", "o_proj"]`, dropout 0.05.
3. Format dataset thành chat template với system prompt + user (question) + assistant (sparql).
4. Train args: epochs=3, lr=2e-4, batch=4, grad_accum=4, warmup=100, eval every 200 steps.
5. Save adapter mỗi epoch + best by eval loss.
6. Push checkpoint lên HF Hub (private).
7. Inference: load base + adapter, generate với constraint (xem 5.1).

**Lưu ý Kaggle 30h/tuần:**
- Một full training ~ 4-6h.
- Nên save checkpoint thường xuyên để có thể resume nếu session timeout (Kaggle limit 12h/session).

**Acceptance:**
- [ ] Training loss giảm ổn định, eval loss không overfit.
- [ ] Checkpoint upload HF Hub thành công.
- [ ] Inference local load adapter + base hoạt động.

---

### Ticket 4.6 — Run all baselines + report

**Script:** `scripts/40_eval_all_baselines.py`

**Việc cần làm:**
1. Chạy lần lượt B0 → B5 trên test set.
2. Mỗi baseline chạy 5 lần (variance analysis cho LLM).
3. Generate `results/baseline_comparison.md` với bảng:

| Model | EM | ExecAcc | F1_Easy | F1_Med | F1_Hard | Latency(s) | Cost($/1k) |
|---|---|---|---|---|---|---|---|

4. Failure mode analysis cho mỗi baseline.

### 🚦 PIVOT POINT #2 — Sau Ticket 4.6

**NO-GO triggers:**
- B1 baseline F1 < 20%.
- Kế hoạch trễ ≥ 3 tuần.

**Hành động nếu NO-GO:** Scope down — bỏ B4/B5 large model, focus vào fine-tuning B3 với dataset đã có.

---

## PHASE 5 — Full System (Tuần 18-21)

### Ticket 5.1 — Constrained decoding

**File:** `src/nl2sparql/decoding/constrained.py` + `decoding/grammar.py`

**Mục tiêu:** Đảm bảo output luôn là SPARQL syntactically valid.

**Approach:**
1. Định nghĩa SPARQL grammar (subset đủ cho use case) trong `grammar.py`.
2. Dùng library `outlines` hoặc `lm-format-enforcer`:
   ```python
   from outlines import generate, models
   from outlines.fsm.guide import RegexGuide
   ```
3. Constrain các tokens:
   - Keywords (SELECT, WHERE, FILTER...): chỉ generate khi đúng vị trí.
   - Variables: format `?[a-z_]+`.
   - URIs: chỉ trong tập properties/classes của ontology + entities có trong context.
4. Fallback: nếu constraint quá chặt làm chậm, dùng post-validation thay thế.

**Acceptance:**
- [ ] Test 50 generation, syntax valid 100% (so với baseline ~85%).
- [ ] Latency tăng < 2x.

---

### Ticket 5.2 — Post-validation

**File:** `src/nl2sparql/validation/post_validator.py`

**Việc cần làm:**
1. Pipeline validation sau khi LLM generate:
   - **Check 1:** Syntax (rdflib parse).
   - **Check 2:** All URIs exist trong ontology hoặc entity dict.
   - **Check 3:** Domain/range của properties hợp lệ.
   - **Check 4:** Execute thử trên Fuseki với timeout 5s.
2. Nếu fail → các strategy:
   - Auto-fix common issues (sai prefix, thiếu `.` cuối triple).
   - Retry với prompt thêm error hint.
   - Fallback: trả về error message thân thiện cho user.
3. `PostValidator.validate(sparql) -> ValidationResult` với `is_valid`, `errors`, `fixed_sparql`.

**Acceptance:**
- [ ] Auto-fix tăng valid rate ≥ 5%.
- [ ] Test với 30 SPARQL có lỗi (fixture).

---

### Ticket 5.3 — Full system integration

**File:** `src/nl2sparql/models/full_system.py`

**Pipeline:**
```
Question
  ↓
[Schema Linker] → top-K classes + properties
  ↓
[Entity Linker] → entity mentions với candidate addresses
  ↓
[Prompt Builder] → enrich prompt với linked context
  ↓
[Fine-tuned LLM (B3)] → generate SPARQL với constrained decoding
  ↓
[Post-Validator] → validate + auto-fix
  ↓
[Fuseki Executor] → run query → results
```

**Class `FullSystem`:**
- `predict(question: str) -> Prediction`
- Trace từng bước cho debugging (return cả intermediate outputs).

**Acceptance:**
- [ ] End-to-end test trên 100 test gold.
- [ ] Cải thiện ≥ 8% F1 so với B3 alone.

---

### Ticket 5.4 — Ablation studies

**Script:** `scripts/41_ablation.py`

**Configurations:**
| ID | Config |
|---|---|
| Full | B3 + Schema + Entity + Constrained + Post-validate |
| -Schema | Bỏ schema linker |
| -Entity | Bỏ entity linker (LLM tự xử lý) |
| -Constrained | Bỏ constrained decoding |
| -PostVal | Bỏ post-validation |

**Acceptance:**
- [ ] Bảng ablation rõ ràng, mỗi component có contribution measurable.
- [ ] Plot bar chart so sánh.

---

## PHASE 6 — Demo & Documentation (Tuần 22-26)

### Ticket 6.1 — Gradio demo

**File:** `src/nl2sparql/demo/app.py`

**UI components:**
1. Input text box cho câu hỏi.
2. Button "Generate SPARQL".
3. Display panels:
   - SPARQL được generate (highlighted).
   - Linked entities (table).
   - Schema linking results (table).
   - Result từ Fuseki (table).
   - Trace mode toggle (show intermediate).
4. Example questions dropdown.
5. Settings: model selector (B0-B5 + Full), temperature.

**Acceptance:**
- [ ] Chạy local OK với `python -m nl2sparql.demo.app`.
- [ ] Có ít nhất 10 example questions hoạt động.

---

### Ticket 6.2 — HuggingFace Spaces deploy

**Two-tier strategy:**
- **Tier 1 (HF Spaces public):** Demo lite — không có Fuseki backend, chỉ generate SPARQL, không execute. Dùng adapter B3 từ HF Hub. CPU/T4 small.
- **Tier 2 (Local full):** Full pipeline với Fuseki + execute → docs hướng dẫn user clone và chạy.

**File:** `infrastructure/hf_spaces/` với `app.py` (entry), `requirements.txt`, `README.md`.

**Acceptance:**
- [ ] Space deploy thành công.
- [ ] URL public hoạt động.

---

### Ticket 6.3 — Case studies

**Notebook:** `notebooks/04_case_studies.ipynb`

**3 use cases:**
1. **Forensics:** truy vết flow từ một hack (vd: Ronin bridge hack).
2. **AML compliance:** identify high-risk addresses (interaction với mixers).
3. **Research:** phân tích DEX volume trends.

Mỗi case: 5-10 câu hỏi end-to-end, screenshots, narrative.

**Acceptance:**
- [ ] Notebook chạy reproducible.
- [ ] Output có thể paste vào chương 5 luận văn.

---

### Ticket 6.4 — Documentation

**Files:**
- `docs/architecture.md` — kiến trúc tổng thể (mermaid diagrams).
- `docs/api_reference.md` — API public của các module chính.
- `docs/dataset_card.md` — HuggingFace dataset card cho NL-SPARQL dataset.
- `docs/model_card.md` — model card cho B3 fine-tuned.
- `docs/reproducibility.md` — hướng dẫn reproduce kết quả.
- `README.md` — overview, quickstart, citation.

**Acceptance:**
- [ ] Mỗi file ≥ 500 từ, không lorem ipsum.
- [ ] README có badge CI, link demo, citation BibTeX.

---

### Ticket 6.5 — Public release artifacts

**Việc cần làm:**
1. Push dataset lên HuggingFace Hub: `huggingface.co/datasets/{username}/nl-sparql-blockchain`.
2. Push model adapter B3: `huggingface.co/{username}/llama3-8b-nl2sparql-eth-lora`.
3. Tag GitHub release `v1.0` với changelog.
4. Add citation file `CITATION.cff`.

**Acceptance:**
- [ ] Dataset có README có Croissant metadata.
- [ ] Model có inference example trong card.

---

## TỔNG KẾT — Acceptance trên toàn dự án

Khi hoàn thành tất cả tickets, bạn phải có:

- [ ] Repo public GitHub với code + docs đầy đủ.
- [ ] Dataset NL-SPARQL ~1100 cặp trên HF.
- [ ] Model B3 fine-tuned trên HF.
- [ ] Demo Gradio trên HF Spaces.
- [ ] Eval report so sánh 6 baselines + Full system.
- [ ] 3 case studies notebooks.
- [ ] Decision log đầy đủ (≥ 30 entries trong 6.5 tháng).
- [ ] Draft luận văn chương Methodology + Experiments dùng được output từ repo.

---

## Phụ lục A — Dependencies giữa các tickets

```
0.1 → 0.2 → [tất cả các phase sau]

Phase 1 path:
1.1 → 1.2 → 1.5 → 1.7
       ↘  1.3 → 1.4 ↗
1.6 (parallel với 1.1-1.5, không depend)

Phase 2 path:
1.3 → 2.1
1.6 → 2.2 → 2.3

Phase 3 path:
1.7 + 2.1 + 2.2 → 3.1 → 3.2 → 3.4
              ↘ 3.3 (parallel)

Phase 4 path:
3.4 → 4.1 → [4.2, 4.3, 4.4, 4.5] → 4.6

Phase 5 path:
4.5 → 5.1, 5.2 → 5.3 → 5.4

Phase 6 path:
5.3 → 6.1 → 6.2
5.4 → 6.3
[all] → 6.4 → 6.5
```

## Phụ lục B — Quy tắc cho Codex khi gặp blocker

1. **Sau 2h bị stuck một ticket** → ghi vào `docs/memory/05-DECISION_LOG.md`, đề xuất 2 options, dừng chờ feedback.
2. **Test fail nhưng nghĩ là test sai** → KHÔNG sửa test trước. Document lý do trước, hỏi rồi mới sửa.
3. **Phụ thuộc external service down** (BigQuery, OpenRouter): retry tối đa 3 lần với exponential backoff, sau đó fallback nếu có hoặc skip + flag.
4. **Out of memory trên Kaggle** → giảm batch size, tăng grad_accum giữ effective batch, KHÔNG giảm sequence length dưới 512.
5. **Hết quota BigQuery** → KHÔNG re-extract. Dùng cache. Nếu thật cần data mới, hỏi trước.

## Phụ lục C — Checklist trước khi đóng mỗi PR

- [ ] Tests viết và pass.
- [ ] Type hints đầy đủ cho public API.
- [ ] Docstring cho public class/function.
- [ ] Update `docs/memory/05-DECISION_LOG.md` nếu có quyết định kỹ thuật.
- [ ] Update README hoặc docs liên quan.
- [ ] Không hardcode path/key.
- [ ] Run `ruff check` và `ruff format` clean.
- [ ] Commit message theo Conventional Commits.
