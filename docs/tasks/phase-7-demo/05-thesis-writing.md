# T7.5 — Thesis Writing + Slides + Defense

## Mục tiêu

Viết thesis tiếng Việt ~80-120 trang, slides ~25-30, rehearsal defense 2-3 lần.

## Bối cảnh & lý do

Hệ thống code tốt mà thesis viết tệ vẫn fail. Quy ước trường (KHTN ĐHQGHN ITech): thesis tiếng Việt, abstract Anh+Việt, slides VN.

## Phụ thuộc

- T7.1, T7.2, T7.3 — system + case studies + demo.
- T6.3 — ablation results.
- T5.4 — evaluation results.

## Đầu vào

- Tất cả results, plots, tables.
- Notebook `notebooks/*` — nguồn figure.
- Template trường (LaTeX hoặc Word).

## Đầu ra

- File `docs/thesis/main.tex` (LaTeX) hoặc `main.docx`.
- File `docs/thesis/figures/` — tất cả hình.
- File `docs/thesis/refs.bib` — đầy đủ references.
- File `docs/thesis/slides.pptx` (~25-30 slides).
- File `docs/thesis/abstract_vi.md` + `abstract_en.md`.
- Recording rehearsal MP4.

## Acceptance criteria

- [ ] Thesis ≥80 trang, không quá 120.
- [ ] Có ≥30 references, ≥10 papers gần đây (2023-2025).
- [ ] Có ≥3 contribution claims rõ ràng, mỗi claim mapping section nào support.
- [ ] Slides ≤30 slides, mỗi slide ≤5 bullets.
- [ ] Rehearsal: nói trong 18-22 phút, không over time.
- [ ] GVHD review ít nhất 2 vòng trước nộp.

## Hướng dẫn triển khai

### Cấu trúc thesis (suggested 8 chapters)

```
Chương 1: Mở đầu (~8 trang)
  1.1 Bối cảnh và động lực
  1.2 Mục tiêu và phạm vi
  1.3 Câu hỏi nghiên cứu (RQ1, RQ2)
  1.4 Đóng góp
  1.5 Cấu trúc luận văn

Chương 2: Cơ sở lý thuyết (~12 trang)
  2.1 Knowledge Graph và RDF/SPARQL
  2.2 Ethereum blockchain — kiến trúc dữ liệu
  2.3 Large Language Models cho code generation
  2.4 NL2X paradigm: NL2SQL, NL2SPARQL
  2.5 Tham số hiệu quả (PEFT/LoRA, quantization)

Chương 3: Khảo sát công trình liên quan (~10 trang)
  3.1 NL2SPARQL classic (LC-QuAD, QALD)
  3.2 LLM-based KGQA
  3.3 Text-to-SQL recent works
  3.4 Blockchain knowledge graphs
  3.5 Khoảng trống nghiên cứu

Chương 4: Phương pháp đề xuất (~15 trang)
  4.1 Tổng quan kiến trúc
  4.2 Construct knowledge graph
  4.3 Schema linker
  4.4 Entity linker (4-stage cascading)
  4.5 Class resolver
  4.6 LLM Generator (B3 với QLoRA)
  4.7 Constrained decoding
  4.8 Validator + recovery

Chương 5: Dataset NL-SPARQL Blockchain (~10 trang)
  5.1 Pipeline 4-bước
  5.2 Templates
  5.3 Synthetic generation
  5.4 Paraphrasing
  5.5 Test set 3-pool
  5.6 Thống kê dataset

Chương 6: Đánh giá thực nghiệm (~15 trang)
  6.1 Setup
  6.2 6 baselines so sánh
  6.3 Metrics 6 chiều
  6.4 Kết quả chính
  6.5 Ablation study
  6.6 Failure mode analysis
  6.7 Trả lời RQ1, RQ2

Chương 7: Ứng dụng và case studies (~8 trang)
  7.1 Persona 1: Investigative journalist
  7.2 Persona 2: AML compliance
  7.3 Persona 3: Researcher
  7.4 Demo system

Chương 8: Kết luận và hướng phát triển (~5 trang)
  8.1 Tổng kết đóng góp
  8.2 Hạn chế
  8.3 Hướng phát triển

Tài liệu tham khảo
Phụ lục A: Ontology đầy đủ
Phụ lục B: Templates đầy đủ
Phụ lục C: Cài đặt và reproducibility
```

### Writing guidelines

- **Mỗi claim → có dữ liệu/reference back:** "Theo Trinh et al. [12], chiến lược fine-tune nhỏ..."
- **Section ≥1 figure/table:** không section toàn text.
- **Methodology trước Results:** đừng trộn.
- **Abstract viết cuối cùng:** sau khi xong tất cả chapters.
- **Limitations section honest:** "Mini KG only Jan 2024 → seasonality bias, ablation r ablation skipped due to compute, etc."
- **Personal voice:** nhất quán "chúng tôi" (academic plural), không lẫn "tôi".

### Figure budget

Phải có ít nhất:
- Architecture diagram (Chương 4).
- Pipeline data flow (Chương 5).
- Bảng so sánh 6 baselines × 6 dimensions (Chương 6).
- Ablation chart (Chương 6).
- Failure mode pie chart (Chương 6).
- 3 case study screenshots (Chương 7).
- Demo screenshot (Chương 7).

Tổng ~10-15 figures + ~5-8 tables.

### Slide structure (~25-30 slides, ~20 phút)

```
1. Title + tên + GVHD (15s)
2. Bối cảnh: blockchain analytics needs (1 min)
3. Vấn đề: tại sao NL → SPARQL khó (1 min)
4. RQ1, RQ2 (30s)
5. Contributions (1 min)
6-8. Related work (2 min)
9. Approach overview (architecture) (1 min)
10. KG construction pipeline (1 min)
11-13. Schema/Entity/Class linker (3 min)
14. LLM Generator + QLoRA (1 min)
15. Constrained decoding (1 min)
16. Dataset pipeline (1 min)
17. Test set 3-pool (1 min)
18. Setup eval (30s)
19. Bảng results main (2 min)
20. Ablation (1.5 min)
21. Failure modes (1 min)
22. Trả lời RQ1, RQ2 (1 min)
23-24. Case study highlights (1.5 min)
25. Demo (live or video, 2 min)
26. Limitations (1 min)
27. Future work (30s)
28. Q&A invitation (15s)
29. Backup slides (FAQ): privacy, compute, dataset stats, ...
```

### Defense Q&A prep

Anticipated questions (chuẩn bị câu trả lời):

1. **"Tại sao chọn SPARQL không phải SQL?"**
   → Plan A vs Plan B, lý do KG model phù hợp graph traversal queries.

2. **"Làm sao đảm bảo dataset không bias từ template?"**
   → Test set 3-pool independent.

3. **"Tại sao Llama 3 8B chứ không phải 7B / Mistral?"**
   → Decision log có ablation thử.

4. **"Lazy: làm sao biết model không memorize test set?"**
   → Test set hoàn toàn independent từ training pool, không có leakage.

5. **"Schema linker đóng góp 13% F1 — rất nhỏ?"**
   → Nói rõ "nhỏ về absolute, lớn về relative %".

6. **"Có thể scale lên 1 năm data không?"**
   → Future work, dependencies (compute, KG size).

7. **"Privacy claim — local LLM thực tế cần GPU đắt?"**
   → Đúng — nhưng không gửi data ra ngoài, GPU một lần đầu tư < cost phí API liên tục.

8. **"Tại sao không dùng Neo4j Cypher?"**
   → SPARQL standard W3C, ontology + reasoning capabilities; tradeoff documented.

### Rehearsal

- 1st rehearsal: solo, time check.
- 2nd rehearsal: trước GVHD or labmate, feedback.
- 3rd rehearsal: full dress (laptop, demo, slides). Thời gian.
- Edit slides nếu over time.

### Submission checklist

- [ ] Final PDF thesis.
- [ ] Final PPTX slides.
- [ ] Source code GitHub repo public (hoặc release tag if private).
- [ ] HF Spaces demo accessible.
- [ ] Demo video MP4.
- [ ] Forms trường đúng template.
- [ ] Plagiarism check passed (Turnitin if required).
- [ ] GVHD signature.

### Publication consideration

- Workshop paper (2-page extended abstract): submit trước defense.
- Suggest: ISWC 2026 workshop, ESWC, or domain-specific (ICAIF, FC).
- Dataset có thể publish trên Kaggle/HF Datasets (independent contribution).

## Rủi ro & note

- **Viết thesis luôn lâu hơn dự tính 2x:** start writing sớm, từ Phase 4 đã có thể viết Chương 1-2.
- **GVHD review có thể yêu cầu re-experiments:** chừa buffer 1 tuần cho việc này.
- **Plagiarism risk:** dùng **paraphrase** tools cẩn thận, cite mọi reference, đặc biệt copy-paste từ paper.
- **PowerPoint vs LaTeX Beamer:** PPTX đơn giản hơn cho live demo embed. LaTeX Beamer đẹp hơn nhưng tốn thời gian.

## Estimated effort

3-4 tuần wall-clock (gồm review GVHD).

## Trạng thái

todo
