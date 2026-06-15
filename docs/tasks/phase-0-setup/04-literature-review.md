# T0.4 — Literature Review Note

## Mục tiêu

Tổng hợp ~30 paper liên quan thành note có cấu trúc, làm nền cho chương Related Work + định hướng các quyết định kỹ thuật.

## Bối cảnh & lý do

Chương Related Work của thesis cần cite cẩn thận. Quan trọng hơn: **biết những gì đã được làm tránh lặp lại** + tìm ý tưởng cho Schema/Entity linking.

Đây không phải "pure coding task" nhưng có deliverable rõ. Coding agent có thể giúp:
- Crawl bibtex từ DBLP/Google Scholar.
- Tổng hợp abstract.
- Tạo bảng so sánh.

## Phụ thuộc

- (không có)

## Đầu vào

- Tham khảo 5 cụm từ khóa search:
  1. "Natural language to SPARQL", "NL2SPARQL", "KGQA"
  2. "Knowledge graph question answering"
  3. "Text-to-SQL" (cho bài học chuyển sang Plan B nếu cần)
  4. "Blockchain knowledge graph"
  5. "Entity linking knowledge graph"

## Đầu ra

- File `docs/related-work/papers.bib` chứa BibTeX.
- File `docs/related-work/notes.md` chứa note theo nhóm:
  - **Nhóm A:** NL2SPARQL classic (LC-QuAD, QALD, ...).
  - **Nhóm B:** KGQA + LLM (recent 2022-2024).
  - **Nhóm C:** Text-to-SQL (Spider, BIRD, ...).
  - **Nhóm D:** Blockchain KG (BLONDiE, ethon, etc.).
  - **Nhóm E:** Entity linking + schema linking.
  - **Nhóm F:** Synthetic data generation cho semantic parsing.
- File `docs/related-work/comparison-table.md` so sánh ~10 paper gần nhất theo các chiều: dataset size, KG, model, accuracy, schema linking, has-code.

## Acceptance criteria

- [ ] ≥30 entries trong `papers.bib`, đầy đủ DOI/URL.
- [ ] Mỗi paper có ≥2-3 câu summary trong `notes.md`.
- [ ] Có ≥2 paper đại diện ở mỗi nhóm A-F.
- [ ] Comparison table với ≥10 hàng.
- [ ] Note ra ≥5 "gap" mà thesis này có thể lấp.

## Hướng dẫn triển khai

1. **Search starting points:**
   - DBLP search: "NL2SPARQL", "KGQA LLM", "blockchain knowledge graph".
   - Google Scholar profile của: TS. Trịnh Tuấn Đạt; Frank van Harmelen; Diego Calvanese (KG); Tao Yu (Spider/text-to-SQL).
   - ACL Anthology (`aclanthology.org`) cho NLP papers.
   - ISWC/ESWC proceedings cho semantic web papers.

2. **Tools để tự động:**
   ```python
   # scholarly: đọc Google Scholar (rate-limited)
   pip install scholarly arxiv

   # Hoặc dùng Semantic Scholar API:
   # https://api.semanticscholar.org/
   ```

3. **Ưu tiên đọc kỹ (đọc full paper, không chỉ abstract):**
   - **LC-QuAD 2.0** (ESWC 2019) — benchmark chính cho NL2SPARQL.
   - **QALD-9-plus** — benchmark đa ngôn ngữ.
   - **SPARQL-LLaMA** hoặc các paper LLM fine-tuned cho SPARQL gần nhất.
   - **DIN-SQL / C3-SQL / DAIL-SQL** — text-to-SQL state-of-the-art (LLM-based).
   - **BLONDiE** hoặc paper blockchain KG bất kỳ.
   - **Trinh et al. iiWAS 2015 + WI 2017** — papers của GVHD (xem `00-PROJECT_OVERVIEW.md`).

4. **Cấu trúc note cho mỗi paper:**
   ```markdown
   ### [Year] Author et al. — Title

   - **Venue:** ...
   - **Problem:** 1 câu.
   - **Approach:** 2-3 câu.
   - **Dataset/KG:** ...
   - **Result:** F1/EM/Acc cụ thể.
   - **Code:** link nếu có.
   - **Relevance to us:** 1-2 câu — paper này cho ta học được gì / paper này thiếu gì so với đề tài ta.
   ```

5. **Comparison table gồm cột:**
   - Paper (1st author + year)
   - KG/Schema
   - Dataset size (train/test)
   - Model (size)
   - Accuracy metric + value
   - Has schema linking (Y/N)
   - Domain (general/biomedical/blockchain/...)
   - Code available (Y/N + link)

6. **Section "Gaps identified":** 3-5 gap mà thesis sẽ giải quyết. Ví dụ:
   - "Không có benchmark NL2SPARQL chuyên cho blockchain (gap → Đóng góp 1)."
   - "Schema linking trong KGQA không xử lý multi-address-one-entity (gap → Đóng góp 2.1)."
   - "Trade-off small vs large LLM cho domain-specific KGQA chưa được phân tích định lượng (gap → Đóng góp 3)."

## Rủi ro & note

- **Cẩn thận paper "có vẻ giống nhưng thực ra khác"** — đọc abstract kỹ trước khi thêm vào nhóm.
- **Không paraphrase quá tay** — note để dùng cho thesis, cần verify lại khi cite.
- **Workflow đề xuất:** dùng Zotero hoặc Mendeley để quản lý PDF + bibtex auto-export.
- **Đừng quá perfectionism:** 30 paper với note ngắn > 10 paper với note quá dài. Có thể bổ sung ở Phase 7.

## Estimated effort

3-5 ngày (rải rác, không liên tục).

## Trạng thái

`done — 2026-06-14`

Đã hoàn thành:

- `docs/related-work/papers.bib` với 32 entries, mỗi entry có URL/DOI.
- `docs/related-work/notes.md` theo 6 nhóm A-F, mỗi paper có note ngắn và relevance.
- `docs/related-work/comparison-table.md` với hơn 10 paper/chủ đề so sánh.
- `tests/unit/test_related_work_docs.py` kiểm tra số lượng BibTeX, nhóm note, gaps và table rows.

Verification:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run pytest tests/unit/test_related_work_docs.py -q
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run ruff check tests/unit/test_related_work_docs.py
```

Kết quả: 3 tests pass, ruff pass.

Note:

- Đây là working literature review cho Phase 0. Khi viết thesis cuối, cần mở lại PDF/venue pages để chuẩn hóa authors, venue, pages, DOI theo style guide của trường.
