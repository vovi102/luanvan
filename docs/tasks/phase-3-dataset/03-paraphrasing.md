# T3.3 — Paraphrasing 2 giai đoạn (Bước B + C)

## Mục tiêu

Biến `nl_seed` (câu hỏi "robotic" sinh từ template) thành câu hỏi tiếng Anh tự nhiên qua 2 stage:
- **Stage B:** SPARQL → câu hỏi "trang trọng" (chuẩn ngữ pháp).
- **Stage C:** Paraphrase thành 3 phiên bản đa dạng (đời thường / casual / abbreviated).

## Bối cảnh & lý do

`nl_seed` từ template thường cứng và lặp lại pattern, model sẽ overfit. Paraphrasing tạo đa dạng linguistic diversity quan trọng cho generalization.

Dùng 2 LLM khác nhau ở stage B và C để tránh bias một model. Stage B cần "faithful" (không đổi nghĩa), stage C cần "diverse".

## Phụ thuộc

- T3.2 — `synthetic-stage-a.jsonl` đã có ~1000 records.
- Quyết định paraphrase model (xem T0/decision log).

## Đầu vào

- `data/dataset/raw/synthetic-stage-a.jsonl`.
- LLM API access:
  - Stage B preferred: GPT-4o-mini hoặc Llama 3 70B qua OpenRouter (faithful translator).
  - Stage C preferred: Claude 3.5 Haiku hoặc Mistral Large qua OpenRouter (diverse paraphraser).
  - Lý do dùng 2 model khác: tránh single-model bias trong dataset.

## Đầu ra

- File `data/dataset/raw/synthetic-stage-b.jsonl` — thêm field `nl_formal`.
- File `data/dataset/raw/synthetic-stage-c.jsonl` — expand mỗi record thành 3 records với `nl_casual_v1/v2/v3`.
- File `data/dataset/raw/cost_log.csv` — log chi phí API.
- Notebook `notebooks/09_paraphrase.ipynb`.

## Acceptance criteria

- [ ] Stage B: 100% records có `nl_formal`, faithfulness check ≥95% (sample 50 manual).
- [ ] Stage C: ~3000 records (1000 × 3 versions), không trùng lặp.
- [ ] Edit-distance giữa 3 versions của cùng record: trung bình >30% (tức là thực sự khác nhau).
- [ ] Cost API tổng ≤ $30 USD.
- [ ] Quality sample 100 records: ≥90% đọc tự nhiên, ≥95% giữ nguyên ý nghĩa SPARQL.

## Hướng dẫn triển khai

### Stage B — Formal translation

```python
SYSTEM_PROMPT_B = """You are a precise SPARQL-to-English translator.
Given a SPARQL query and an entity context, write ONE clear, grammatically
correct English question that the SPARQL would answer.
Rules:
- Preserve all filters, time ranges, top-N, and entities EXACTLY.
- Use formal English (no slang).
- Single sentence preferred. Max 30 words.
- Do not add information not in SPARQL.
- Use entity owner names ("Binance") instead of addresses when given.
"""

USER_PROMPT_B_TEMPLATE = """SPARQL:
{sparql}

Entity context:
{entity_dict}

NL seed (for reference):
{nl_seed}

Write the English question:"""
```

Lưu output → `nl_formal`.

### Stage C — Diverse paraphrase

```python
SYSTEM_PROMPT_C = """You are a paraphrasing assistant. Given a formal English
question, write THREE different paraphrases:
1. CASUAL: how a regular person might ask (informal, contractions OK).
2. ABBREVIATED: shortened, telegram-style, may use abbreviations.
3. ALTERNATIVE: different sentence structure but same meaning.

Rules:
- Preserve meaning EXACTLY (numbers, entities, time ranges).
- Each paraphrase must be linguistically different (not just word swap).
- Output as JSON: {"casual": "...", "abbreviated": "...", "alternative": "..."}
"""
```

### Faithfulness verification

Sample 50 records, manual check:
- Có giữ nguyên entity names? (e.g. không bỏ "Binance")
- Có giữ nguyên numeric thresholds?
- Có giữ nguyên time ranges?
- Reject record nếu có drift nghĩa.

### Cost control

- Stage B: ~1000 calls × ~500 tokens/call = ~500K tokens.
- Stage C: ~1000 calls × ~800 tokens/call = ~800K tokens.
- Llama 3 70B trên OpenRouter ~$0.5-0.9/M tokens → tổng ~$1-2.
- Claude Haiku ~$0.25/M input + $1.25/M output → tổng ~$2-3.
- Buffer cho retry → cap $30.

### Output schema sau Stage C

```json
{
  "id": "syn-000123-v1",
  "parent_id": "syn-000123",
  "version": "casual",
  "sparql": "...",
  "nl": "what's the top 10 biggest transfers from Jan 15 to Jan 20",
  "nl_formal": "List the top 10 transactions by value between 2024-01-15 and 2024-01-20",
  ...
}
```

### Batching

- Async parallel với `aiohttp` hoặc `asyncio` + semaphore (10 concurrent).
- Retry với exponential backoff cho 429/5xx.
- Save partial results mỗi 50 records (nếu crash không mất hết).

## Rủi ro & note

- **LLM hallucinate entity:** stage B có thể đổi "Binance" thành "Coinbase". Mitigation: prompt nhấn mạnh, check post-hoc bằng regex match entity names.
- **Stage C "paraphrase" giống stage B:** prompt rõ ràng + check edit distance threshold.
- **Cost overrun:** monitor cost mỗi 100 calls, hard stop tại $30.
- **Rate limit:** OpenRouter free tier có thể rate limit, dùng paid tier nếu bị throttle.

## Estimated effort

2 ngày (1 ngày code + 1 ngày run + verify).

## Trạng thái

todo
