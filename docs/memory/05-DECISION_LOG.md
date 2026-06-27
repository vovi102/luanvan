# 05 — Decision Log

> **Mục đích:** Ghi lại các quyết định kỹ thuật đáng nhớ. Sẽ được trích dẫn trong chương Methodology của luận văn.
> **Quy tắc:** Mỗi quyết định 1 entry. Cập nhật KHI ra quyết định, không phải sau cùng.
> **Format:** Reverse chronological (entry mới ở trên).

---

## Template entry

```markdown
### YYYY-MM-DD — <tóm tắt 1 dòng>

- **Context:** Tại sao cần quyết định này (vấn đề gặp phải, trade-off).
- **Options considered:** Liệt kê các lựa chọn đã cân nhắc.
- **Decision:** Chọn cái gì.
- **Rationale:** Lý do chọn (1-3 câu).
- **Consequences:** Tác động sau này (cái gì giờ dễ hơn, cái gì khó hơn).
- **Revisit:** Khi nào nên xem lại quyết định này (e.g. "sau Phase 5", "không cần").
- **Linked:** Task/file liên quan.
```

---

## Entries

### 2026-06-28 — T2.2 dictionary dùng committed source snapshots

- **Context:** Public label sources for Ethereum addresses can change, rate-limit, or block automation. T2.2 still needs a stable input for Phase 4 entity linking and for thesis reproducibility.
- **Options considered:** Live scrape in CI; keep only final JSON artifacts; commit raw source snapshots plus final generated artifacts.
- **Decision:** Commit `data/entity_dictionary/raw/entities.csv`, curated coverage metadata, and final dictionary JSON artifacts. Live fetchers are optional acquisition tools and must not be required by CI.
- **Rationale:** A committed raw snapshot makes future refreshes auditable through git diffs while keeping tests deterministic and offline.
- **Consequences:** Automated acceptance can verify structure, count, coverage, sorting, normalization, and provenance locally. The 50-entry manual verification remains a separate evidence step and must stay pending until sampled rows are checked against external source pages.
- **Revisit:** When refreshing the dictionary after Phase 4 linker evaluation or when replacing source acquisition with a stable API/keyed provider.
- **Linked:** `docs/tasks/phase-2-kg/02-entity-dictionary.md`, `data/entity_dictionary/raw/entities.csv`, `src/nl2sparql/linking/dictionary/sources.md`.

### 2026-06-27 — Chốt ontology extension v0.1.0 cho Ethereum KG

- **Context:** EthOn cover tốt transaction/block/account nền tảng nhưng thiếu DeFi protocol classes, semantic labels cho địa chỉ, token-transfer model thân thiện với NL2SPARQL, và metadata giàu cho schema linker.
- **Options considered:** Sửa trực tiếp EthOn; tạo ontology local tối thiểu chỉ cho RML; tạo ontology extension versioned với class/property local và documentation contract.
- **Decision:** Tạo `eth-kg-extension-v0.1.0.ttl` trong namespace `https://thesis.example.org/eth-kg/`, subclass EthOn classes, không override EthOn predicates, và bắt buộc mỗi property có label/comment/synonyms/example/domain/range.
- **Rationale:** Extension local giữ EthOn nguyên vẹn nhưng cung cấp đúng abstraction cho thesis: exchange, mixer, DEX, lending, bridge, NFT marketplace, token transfer, metadata entity-labeling và meta-transaction. Documentation contract tạo input nhất quán cho schema linker ở Phase 4.
- **Consequences:** T2.2 có thể xây entity dictionary dựa trên account classes/identity properties; T2.4 có schema ổn định để mở rộng RML mapping; Phase 3 có competency questions làm seed cho query templates. Protégé reasoner validation vẫn cần manual GUI check ngoài CLI.
- **Revisit:** Khi hoàn thành T2.4 nếu mapping full cần đổi domain/range hoặc thêm protocol-specific event classes.
- **Linked:** `docs/tasks/phase-2-kg/01-ontology-extension.md`, `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`, `src/nl2sparql/kg/ontology/competency-questions.md`.

### 2026-06-21 — Giữ Morph-KGC cho RML pipeline sau pilot T1.3

- **Context:** T1.3 cần chứng minh RML có thể chuyển dữ liệu BigQuery pilot thành RDF parse được và truy vấn được trước khi mở rộng sang Phase 2.
- **Options considered:** Morph-KGC trực tiếp trên CSV; tiền xử lý CSV trước Morph-KGC; chuyển sang RMLMapper hoặc RDFLib thuần.
- **Decision:** Giữ Morph-KGC 2.8.1 và mapping RML trực tiếp cho pipeline; pilot chỉ cover transactions và blocks.
- **Rationale:** Morph-KGC materialized 770 triples từ 100 transactions và 10 blocks, giữ datatype RDF, upload Fuseki thành công và cả ba query khớp CSV nguồn.
- **Consequences:** T2.4 có thể mở rộng mapping này cho token transfers và contracts. Dữ liệu CSV/TTL vẫn là artifact local bị ignore; mapping, runner, notebook và tests được version-control.
- **Revisit:** T2.4 nếu dữ liệu một tháng gây vấn đề về tốc độ, bộ nhớ hoặc NULL handling; khi đó benchmark RMLMapper.
- **Linked:** `docs/tasks/phase-1-pilot/03-rml-pilot.md`, `src/nl2sparql/kg/rml/pilot_mapping.ttl`, `notebooks/04_rml_pilot.ipynb`.

### 2026-06-20 — Commit EthOn 0.2 làm ontology nền cho pilot

- **Context:** T1.1 cần ontology tái lập để kiểm chứng Fuseki và làm namespace nền cho RML pilot T1.3.
- **Options considered:** Tải động mỗi lần; commit skeleton tối thiểu; commit toàn bộ ontology chính thức.
- **Decision:** Commit toàn bộ `EthOn.ttl`, giữ nguyên namespace `http://ethon.consensys.net/`, và chạy truy vấn không inference.
- **Rationale:** File chính thức nhỏ (86,718 bytes), loại bỏ phụ thuộc mạng và giữ đầy đủ source; SHA-256 là `e73e19bf0d6bbb0e28b1497a73e4499ca78ee9c1e8c475fa31e7c821354ce71d`.
- **Consequences:** T1.3 có thể tham chiếu trực tiếp EthOn; ontology đo được 1,423 triples, 40 classes, 48 object properties, 60 datatype properties và 29 quan hệ subclass. DEX, lending, mixer, token standards và dữ liệu hậu PoS vẫn cần extension ở Phase 2.
- **Revisit:** T2.1 khi thiết kế ontology extension.
- **Linked:** `docs/tasks/phase-1-pilot/01-load-ethon.md`, `data/ontologies/EthOn.ttl`.

### 2026-06-20 — Cố định và bảo toàn dữ liệu BigQuery pilot T1.2

- **Context:** T1.2 cần một lát dữ liệu nhỏ, tái lập được để kiểm tra BigQuery → CSV
  trước khi thiết kế RML mapping; các cột Ethereum NUMERIC có nguy cơ mất chính xác.
- **Options considered:** Lấy ngày mới nhất động; lấy mẫu ngẫu nhiên; cố định ngày và
  giới hạn dòng; serialize số qua float hoặc chuỗi thập phân.
- **Decision:** Cố định ngày `2024-01-15`, giới hạn 100/10/100/50 dòng cho
  transactions/blocks/token transfers/contracts, và serialize `Decimal` thành chuỗi.
- **Rationale:** Query có thể tái lập, dry-run chỉ quét `0.50 GiB`, còn biểu diễn chuỗi
  giữ nguyên giá trị wei trước bước RDF mapping.
- **Consequences:** CSV pilot chỉ lưu local dưới `data/raw/pilot/` và bị `.gitignore`;
  repo lưu SQL, extractor, notebook và mô tả edge cases. Sample ghi nhận 80 zero-value,
  19 large-integer và 93 typed transactions.
- **Revisit:** Phase 2 khi chốt slice extraction đầy đủ và schema literal trong RML.
- **Linked:** `docs/tasks/phase-1-pilot/02-bigquery-100rows.md`,
  `src/nl2sparql/kg/extraction/pilot_extract.py`.

### 2026-06-14 — Xác nhận BigQuery Ethereum smoke access và cost estimate

- **Context:** T0.3 cần chứng minh service account local query được BigQuery public Ethereum và estimate chi phí extraction 1 tháng.
- **Options considered:** Chỉ dựa vào estimate trong task doc; chạy query thật và dry-run bằng `google-cloud-bigquery`.
- **Decision:** Dùng service account local qua `GOOGLE_APPLICATION_CREDENTIALS`, chạy COUNT ngày `2024-01-01` và dry-run tháng `2024-01-01` đến `2024-01-31`.
- **Rationale:** Kết quả thật xác nhận IAM/API/credentials hoạt động, đồng thời dry-run không tốn query charge và cho số byte chính xác cho query extraction hiện tại.
- **Consequences:** T0.3 không còn blocked; tháng 2024-01 với 5 cột pilot estimate `6.04 GiB`, thấp hơn nhiều so với free tier 1 TiB/tháng.
- **Revisit:** Phase 2 khi chốt slice dữ liệu và danh sách cột extraction cuối.
- **Linked:** `docs/tasks/phase-0-setup/03-bigquery-access.md`, `scripts/01_bigquery_smoke.py`, `src/nl2sparql/kg/extraction/bigquery_smoke.py`.

### 2026-06-14 — Nhóm related work theo vai trò trong luận văn

- **Context:** Literature review cần phục vụ cả chương Related Work lẫn thiết kế hệ thống, không chỉ là danh sách citation.
- **Options considered:** Liệt kê paper theo năm; nhóm theo kỹ thuật; nhóm theo contribution/risk của đề tài.
- **Decision:** Chia thành 6 nhóm: NL2SPARQL classic, KGQA+LLM, Text-to-SQL, Blockchain KG, Entity/Schema Linking, Synthetic Data Generation.
- **Rationale:** Cách nhóm này map trực tiếp tới 3 đóng góp khoa học, Plan B, và các module triển khai như linker, dataset generation, constrained decoding.
- **Consequences:** Dễ viết thesis theo luận điểm, nhưng cần chuẩn hóa BibTeX metadata lần nữa trước bản nộp cuối.
- **Revisit:** Phase 7 khi viết chương Related Work và chuẩn hóa citation theo template trường.
- **Linked:** `docs/related-work/papers.bib`, `docs/related-work/notes.md`, `docs/related-work/comparison-table.md`.

### 2026-06-14 — Bắt buộc dry-run và filter ngày cho BigQuery Ethereum

- **Context:** BigQuery public Ethereum là nguồn dữ liệu chính nhưng query không giới hạn thời gian có thể quét toàn bảng và tiêu tốn quota/cost.
- **Options considered:** Cho phép exploratory SQL tự do; chỉ document cảnh báo; encode query helper có filter `block_timestamp` và dry-run config.
- **Decision:** Mọi query extraction/smoke phải có filter ngày; estimate chi phí dùng `QueryJobConfig(dry_run=True, use_query_cache=False)`.
- **Rationale:** Kiểm soát quota 1TB/tháng, tránh lỗi thao tác khi chạy pipeline extract, và tạo bằng chứng cost estimate cho methodology.
- **Consequences:** Script BigQuery smoke yêu cầu credentials thật trước khi chạy; helper test offline chỉ kiểm tra query safety và config.
- **Revisit:** Phase 2 khi chốt kích thước slice dữ liệu 1 tháng và danh sách cột extraction cuối.
- **Linked:** `src/nl2sparql/kg/extraction/bigquery_smoke.py`, `scripts/01_bigquery_smoke.py`, `src/nl2sparql/kg/extraction/bq_schema.md`.

### 2026-06-14 — Chạy Fuseki local bằng Docker Compose

- **Context:** Host hiện tại không có Java, trong khi Apache Jena Fuseki cần JVM. Cài Java trực tiếp làm môi trường local khó tái lập hơn.
- **Options considered:** Cài Java 17+ trên host; build image Fuseki từ `eclipse-temurin` và tải tarball Apache; dùng image Docker Hub `stain/jena-fuseki:latest`.
- **Decision:** Dùng Docker Compose với image `stain/jena-fuseki:latest`, dataset in-memory `/test`, port `3030`, admin password local cố định `admin`.
- **Rationale:** Docker giữ Java/Fuseki trong container, tránh yêu cầu Java host; Docker Hub pull thành công trong khi `archive.apache.org` timeout từ môi trường này.
- **Consequences:** Lệnh setup Fuseki chuẩn là `src/nl2sparql/kg/scripts/start_fuseki.sh` hoặc `docker compose -f infrastructure/docker/docker-compose.fuseki.yml up -d`; upload smoke data cần Basic Auth `admin:admin`.
- **Revisit:** Phase 2 khi chuyển từ in-memory `/test` sang TDB2 persistent dataset.
- **Linked:** `docs/tasks/phase-0-setup/02-fuseki-local.md`, `docs/setup-fuseki.md`, `infrastructure/docker/docker-compose.fuseki.yml`.

### 2026-06-14 — Dùng `uv` làm trình quản lý môi trường Python

- **Context:** T0.1 ban đầu mô tả setup qua `requirements.txt`/`pip`, nhưng project cần môi trường tái lập nhanh cho stack lớn gồm KG, ML, demo và dev tools.
- **Options considered:** Giữ `requirements.txt` + `pip`; dùng Poetry; dùng `uv` với `pyproject.toml` và `uv.lock`.
- **Decision:** Dùng `uv` làm workflow chính, với `pyproject.toml`, `.python-version` 3.11 và `uv.lock`.
- **Rationale:** `uv` tự quản lý Python 3.11, resolve/install nhanh, lock dependency rõ hơn, phù hợp stack nhiều package nặng như `torch`, `transformers`, `bitsandbytes`.
- **Consequences:** Lệnh setup chuẩn là `uv sync`; các task cũ nhắc `pip install -r requirements.txt` cần được hiểu là legacy và cập nhật dần khi chạm tới.
- **Revisit:** Sau Phase 0 nếu cần publish package hoặc tách dependency group cho Kaggle/HF Spaces.
- **Linked:** `pyproject.toml`, `.python-version`, `uv.lock`, `docs/tasks/phase-0-setup/01-repo-and-env.md`.

### 2026-06-14 — Chuẩn hóa cấu trúc repo theo package `src/nl2sparql`

- **Context:** Repo ban đầu chỉ có `memory/`, `tasks/` và kế hoạch triển khai ở root; tài liệu và source code chưa được tách rành mạch.
- **Options considered:** Giữ `memory/`/`tasks/` ở root; gom toàn bộ tài liệu vào `docs/`; hoặc dùng cấu trúc `.claude/` như bản nháp README cũ.
- **Decision:** Chuyển tài liệu vận hành vào `docs/memory/`, backlog vào `docs/tasks/`, kế hoạch vào `docs/planning/`, và đặt source code trong package `src/nl2sparql/`.
- **Rationale:** Root repo gọn hơn, package boundary rõ hơn cho Python import/test/deploy, đồng thời tách được source code, dữ liệu, tài liệu, hạ tầng và notebook.
- **Consequences:** Các task cũ cần dùng đường dẫn `docs/...` và `src/nl2sparql/...`; mọi module mới nên import qua `nl2sparql.*`.
- **Revisit:** Sau khi hoàn thành Phase 0 nếu tooling packaging yêu cầu đổi tên package.
- **Linked:** `README.md`, `docs/memory/01-ARCHITECTURE.md`, `docs/memory/04-CONVENTIONS.md`.

### 2025-XX-XX — Khởi tạo decision log

- **Context:** Bắt đầu dự án, cần file để track decisions.
- **Decision:** Tạo file này, format reverse-chronological.
- **Rationale:** Theo "quy tắc sống còn #4" trong `00-PROJECT_OVERVIEW.md`.
- **Consequences:** Mọi quyết định phải ghi ở đây — overhead nhỏ, lợi ích lớn khi viết thesis.
- **Revisit:** Không cần.
- **Linked:** Tất cả memory files.

---

## Quyết định chờ ghi (placeholders — điền khi đến)

- [ ] Phase 0: Chốt repo URL, license, .gitignore policy.
- [ ] Phase 0: Chốt OpenRouter free tier model rotation strategy.
- [ ] Phase 1: Chốt Plan A khả thi sau pilot (Pivot Point #1 chuẩn bị).
- [ ] Phase 2: Chốt namespace ontology cuối cùng.
- [ ] Phase 2: Chốt mức độ extension EthOn (số class/property thêm).
- [ ] Phase 2: Chốt kích thước slice BigQuery (1 tháng → bao nhiêu transactions thực tế).
- [ ] Phase 2: **Pivot Point #1** — Plan A tiếp tục hay Plan B.
- [ ] Phase 3: Chốt số templates cuối cùng (mục tiêu 25-30).
- [ ] Phase 3: Chốt LLM dùng cho paraphrase (Llama 3 70B qua OpenRouter? Mistral Large?).
- [ ] Phase 3: Chốt mức noise injection (% items, loại noise nào).
- [ ] Phase 4: Chốt embedding model cuối (MiniLM-L6 hay multilingual?).
- [ ] Phase 4: Chốt fuzzy threshold sau hyperparam search.
- [ ] Phase 5: Chốt format prompt cho B1/B2 (system prompt + few-shot template).
- [ ] Phase 5: **Pivot Point #2** — scope down nếu cần.
- [ ] Phase 6: Chốt QLoRA hyperparam sau ablation.
- [ ] Phase 6: Chốt constrained decoding lib (outlines vs lm-format-enforcer).
- [ ] Phase 7: Chốt 3 case studies cuối cùng.

---

## Cách dùng entries này khi viết thesis

Trong chương Methodology (hoặc Implementation), mỗi quyết định kỹ thuật phải có justification. File này là nguồn chính:

1. Tìm decisions có `Linked` đến chương đang viết.
2. Paraphrase Context + Rationale → 1 đoạn Methodology.
3. Trade-off và Consequences → vào phần "Discussion" hoặc "Limitations".
