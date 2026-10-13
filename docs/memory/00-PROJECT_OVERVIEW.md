# 00 — Project Overview

> **Đọc trước tiên.** Đây là tóm tắt canonical của dự án.

## Đề tài

**EN:** Small Language Models for Natural-Language-to-SQL Ethereum Analytics

**VN:** Mô hình ngôn ngữ nhỏ cho sinh truy vấn SQL từ ngôn ngữ tự nhiên trong
phân tích dữ liệu Ethereum

## One-liner

Người dùng hỏi bằng tiếng Anh hoặc tiếng Việt về dữ liệu Ethereum; hệ thống
link schema/entity/class, dùng small LLM sinh GoogleSQL an toàn, dry-run rồi
thực thi trên BigQuery và trả kết quả có provenance.

## Câu hỏi nghiên cứu

- **RQ1:** Small LLM fine-tuned bằng QLoRA trên Kaggle cải thiện execution
  accuracy bao nhiêu so với zero-shot và five-shot trên cùng benchmark NL2SQL?
- **RQ2:** Schema/entity/class linking và constrained generation đóng góp như
  thế nào vào accuracy, safety và latency của hệ thống?

## Đóng góp khoa học

1. **Dataset NL–GoogleSQL blockchain song ngữ** có provenance, leakage gate và
   benchmark human-reviewed tách khỏi training/tuning.
2. **Linking đặc thù blockchain** cho schema, alias, multi-address entities và
   typed class-resolution constraints.
3. **Đánh giá small LLM có kiểm soát:** B0 rule-based, B1 zero-shot, B2 five-shot
   và B3 fine-tuned; báo accuracy, latency, cost, reproducibility và failure modes.

## Phạm vi

- Ethereum mainnet và BigQuery public dataset.
- Target language: GoogleSQL trên analytical catalog đã quản lý.
- Small open-weight model chạy local/Kaggle; không inference qua API.
- Training corpus deterministic song ngữ; benchmark nằm ngoài training/tuning.
- Demo ưu tiên local; HF Spaces chỉ optional nếu giữ đúng model và resource guard.
- Không mở rộng sang chain khác, dữ liệu off-chain hoặc real-time.

## Baseline

| ID | Cấu hình |
|---|---|
| B0 | Rule-based deterministic lower bound |
| B1 | Small LLM zero-shot |
| B2 | Small LLM five-shot với retriever đã pin |
| B3 | Small LLM QLoRA fine-tuned |

## Plan A và Plan B

- **Plan A (dừng 2026-08-09):** NL2SPARQL trên KG/Fuseki; giữ artifact và negative
  performance finding để tái lập lịch sử.
- **Plan B (active):** NL2SQL trên BigQuery với small LLM.
- Entity dictionary, competency questions, dataset methodology và linking logic
  từ Plan A được tái sử dụng khi phù hợp.

## Tài nguyên

- Kaggle T4 GPU 30 giờ/tuần, Colab làm backup.
- BigQuery Ethereum public dataset với dry-run và byte/cost guard.
- Gradio cho local demo; không cần credential LLM bên ngoài.

## Đầu ra

- Luận văn thạc sĩ.
- Dataset NL–GoogleSQL song ngữ và benchmark có provenance.
- Source code pipeline tái lập được.
- Local demo; public showcase là optional.

## Quy tắc sống còn

1. Dataset trước, model sau.
2. Không dùng benchmark để train, tune prompt, linker hoặc hyperparameter.
3. Implementation pass không đồng nghĩa scientific result.
4. Negative result vẫn là kết quả hợp lệ.
5. Cập nhật decision log khi thay đổi scope hoặc acceptance.
