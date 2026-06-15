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
