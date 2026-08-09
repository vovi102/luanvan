# 00 — Project Overview

> **Đọc trước tiên.** File này là tóm tắt cao nhất. Nếu chỉ đọc 1 file memory, đọc file này.

## Đề tài

**EN:** Natural Language to SPARQL Translation for Blockchain Knowledge Graph Analytics
**VN:** Sinh truy vấn SPARQL từ ngôn ngữ tự nhiên cho phân tích dữ liệu blockchain dựa trên Knowledge Graph

## One-liner

Người dùng (nhà báo điều tra, AML compliance, nhà nghiên cứu) hỏi tiếng Anh thông thường về dữ liệu Ethereum → hệ thống sinh SPARQL → chạy trên KG Fuseki → trả kết quả thực.

## Câu hỏi minh họa

> "List transactions larger than 1000 ETH from Binance to Tornado Cash last month"

Hệ thống cần:
- Map "Binance" → ~30 địa chỉ ví Binance (multi-address-one-entity).
- Map "Tornado Cash" / "tornado.cash" / "TC" → set địa chỉ TC (alias).
- Map "from"/"to" → property `:hasFrom`/`:hasTo` (chứ không phải `:initiatedBy`).
- Map "last month" → time filter chính xác.
- Sinh SPARQL hợp lệ chạy được.

## Câu hỏi nghiên cứu

- **RQ1:** LLM nhỏ (≤8B) fine-tuned trên Kaggle có đạt accuracy đủ dùng cho NL2SPARQL trên KG blockchain không?
- **RQ2:** Schema/Entity linking đặc thù blockchain đóng góp như thế nào (định lượng) so với baseline LLM thuần?

## Ba đóng góp khoa học

1. **Bộ dữ liệu NL-SPARQL chuyên blockchain** — ~1000 cặp training (synthetic pipeline) + ~100 cặp test (3-pool independent writers). Là benchmark có giá trị citation độc lập.
2. **Schema/Entity Linking đặc thù blockchain** — xử lý 4 đặc thù: multi-address-one-entity, alias, class-level resolution, property nhập nhằng.
3. **Phân tích trade-off LLM nhỏ vs lớn** — 6 baselines × 6 chiều đo (accuracy, latency, cost, privacy, reproducibility, failure mode).

## Phạm vi

- **Blockchain:** Ethereum mainnet (chỉ).
- **Dữ liệu:** 1 tháng gần nhất tại thời điểm thu thập.
- **Ontology:** 15-20 class, ~30 property (kế thừa EthOn + extension cho DeFi).
- **Entity dictionary:** ~5000 entries.
- **Query templates:** ~25-30 patterns phủ 80% use case.
- **Loại trừ:** chains khác, dữ liệu off-chain (giá, tin tức), real-time.

## Plan A vs Plan B

- **Plan A (đã thử, dừng 2026-08-09):** NL2SPARQL trên KG Apache Jena Fuseki.
- **Plan B (đang active):** NL2SQL trên BigQuery Ethereum public dataset.
- **Common ground (làm trước):** entity dictionary, dataset pipeline, test set, schema/entity linking logic, evaluation framework, literature review.
- **Pivot Point #1 — đã quyết định:** pivot Plan B vì query đơn giản trên full KG
  vượt NO-GO 5 giây; xem `docs/pivot-decision-1.md`.
- **Pivot Point #2 — giữa tháng 4 (last resort):** scope down/pivot nếu B1 baseline F1 < 20%.

## Tài nguyên

- **Compute:** Kaggle T4 GPU 30h/tuần + Colab backup + OpenRouter free tier cho LLM lớn.
- **Data:** BigQuery Ethereum public dataset (1TB free/tháng).
- **Triple store:** Apache Jena Fuseki local (port 3030).
- **Demo:** Gradio + Hugging Face Spaces (two-tier).

## Đầu ra dự kiến

- Quyển luận văn thạc sĩ.
- Bộ dữ liệu NL-SPARQL công khai trên GitHub.
- Mã nguồn pipeline đầy đủ trên GitHub.
- Demo trên HF Spaces.
- Bài báo workshop (NLIWoD/Text2KG @ ISWC, hoặc SoICT/RIVF/KSE).

## Quy tắc sống còn (đọc khi bị stuck)

1. **Dataset trước, mô hình sau.** Đừng touch fine-tuning trước khi có dataset chất lượng.
2. **Scope down sớm khi có dấu hiệu trễ.** 80% scope đúng hạn > 100% trễ 3 tháng.
3. **Báo cáo tiêu cực vẫn là kết quả.** Fine-tuned model thua zero-shot vẫn là finding.
4. **Document quyết định.** Cập nhật `05-DECISION_LOG.md` mỗi tuần.
5. **Tôn trọng Pivot Point.** Cuối tháng 2 nếu còn argue về pivot — câu trả lời là pivot.

## Người dùng mục tiêu (để giữ định hướng UX)

- **Nhà báo điều tra:** "ai đã chuyển tiền cho địa chỉ X trước/sau sự kiện Y?"
- **Cán bộ AML compliance:** "có giao dịch nào từ ví bị cấm vận đến exchange Z không?"
- **Nhà nghiên cứu liên ngành (kinh tế, xã hội học):** "phân bố giao dịch DEX theo giờ trong ngày?"

Đây không phải tool cho dev/quant — họ tự viết SPARQL/SQL được.
