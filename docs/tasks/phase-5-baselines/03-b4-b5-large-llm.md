# T5.3 — B4 + B5: Large LLM Zero-Shot & Few-Shot (Llama 3 70B / Mistral Large)

## Mục tiêu

Triển khai 2 baselines dùng LLM lớn qua API (OpenRouter):
- **B4:** Llama 3 70B Instruct, zero-shot.
- **B5:** Llama 3 70B Instruct, few-shot 5 examples.

(Có thể dùng Mistral Large hoặc Qwen 2.5 72B làm alternative; chọn 1 nhất quán.)

## Bối cảnh & lý do

B4/B5 là **upper bound** trong bảng baseline. Nếu B3 (small fine-tuned) gần B4/B5 trên accuracy → finding quan trọng cho RQ1: small LLM fine-tuned đủ dùng.

API-based, không train, không host — kiểm tra capability "có sẵn" của LLM lớn.

## Phụ thuộc

- T5.2 — B1/B2 đã có (reuse SPARQL extraction logic).
- OpenRouter account + API key.
- T3.5 — Test set 100 câu.

## Đầu vào

- `OPENROUTER_API_KEY` (env var).
- Model identifier: `meta-llama/llama-3-70b-instruct` (hoặc Mistral / Qwen).
- Test set.

## Đầu ra

- Module `src/nl2sparql/models/large_llm.py`.
- Predictions `data/eval/predictions/b4_test.jsonl`, `b5_test.jsonl`.
- Cost log `data/eval/logs/openrouter_cost.csv`.

## Acceptance criteria

- [ ] B4/B5 chạy hoàn tất trên 100 test cases mà không exceed $20 cost.
- [ ] Latency log per query.
- [ ] Tất cả requests có retry logic (429/5xx).
- [ ] Tổng cost report cuối.
- [ ] Reproducibility: temperature=0, seed nếu API support.

## Hướng dẫn triển khai

### OpenRouter client

```python
import httpx, time
from typing import Optional

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

class OpenRouterClient:
    def __init__(self, api_key, model="meta-llama/llama-3-70b-instruct"):
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str, max_tokens=512, retries=3):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/<your-repo>",
            "X-Title": "NL2SPARQL-Thesis",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=60) as client:
                    resp = client.post(OPENROUTER_URL, headers=headers, json=body)
                    if resp.status_code == 429:
                        time.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPError as e:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)
```

### B4 / B5 code

Reuse prompt từ T5.2 (B1/B2). Chỉ đổi backend từ local model sang OpenRouter.

```python
class BaselineB4:
    def __init__(self, ontology_summary, client):
        self.ontology = ontology_summary
        self.client = client

    def predict(self, nl):
        system = B1_SYSTEM.format(ontology_summary=self.ontology)
        user = f"Question: {nl}\n\nSPARQL:"
        resp = self.client.complete(system, user)
        raw = resp["choices"][0]["message"]["content"]
        return extract_sparql(raw), {
            "tokens_in": resp["usage"]["prompt_tokens"],
            "tokens_out": resp["usage"]["completion_tokens"],
            "cost": estimate_cost(resp),
        }
```

### Cost tracking

OpenRouter pricing (varies, check current):
- Llama 3 70B: ~$0.7-0.9/M input + $0.8-1.0/M output.
- Mistral Large: ~$3/M input + $9/M output (đắt hơn).

```python
def estimate_cost(resp, prices):
    usage = resp["usage"]
    cost_in = (usage["prompt_tokens"] / 1_000_000) * prices["in"]
    cost_out = (usage["completion_tokens"] / 1_000_000) * prices["out"]
    return cost_in + cost_out
```

Cap tổng: nếu sum cost vượt $20 → abort, log unfinished cases.

### Concurrency

OpenRouter rate limits: thường 60 req/min cho free, 600 req/min cho paid. Dùng `asyncio.Semaphore(5)` để parallel mà không bị rate limit:

```python
import asyncio

async def run_async(test_set, client, semaphore):
    async def one(case):
        async with semaphore:
            sparql, meta = await client.complete_async(case["nl"])
            return {"id": case["id"], "predicted_sparql": sparql, **meta}
    sem = asyncio.Semaphore(5)
    return await asyncio.gather(*(one(c) for c in test_set))
```

### Variance check

Run 3 lần với cùng input (temperature=0). Compute:
- Exact match between runs (should be 100% if API deterministic).
- Nếu khác → log, có thể model server stochastic dù temp=0.

Đây là dimension "Reproducibility" trong evaluation framework (T5.4).

### Logging schema

```jsonl
{"id":"test-001","baseline":"b4","run":1,"raw":"...","sparql":"...","tokens_in":850,"tokens_out":120,"cost":0.0008,"latency_ms":2300,"timestamp":"..."}
```

### Privacy note

OpenRouter forwards prompts đến model providers. **Không gửi PII**. Test set chỉ chứa câu hỏi public Ethereum data → OK.

Document limitation này trong thesis privacy chapter (đối lập với local Llama 8B).

## Rủi ro & note

- **OpenRouter outage:** plan B = Together AI hoặc Replicate. Code abstraction để swap.
- **Cost overrun:** monitor mỗi 20 calls, hard stop $20.
- **Rate limit unexpected:** retry với backoff, log unfinished cases.
- **Model deprecation:** OpenRouter có thể đổi tên model. Pin specific version (e.g. `llama-3-70b-instruct:nitro` cho fast variant).
- **Different model results khác nhau:** chọn 1 (Llama 3 70B) làm chính, mention alternatives đã thử trong thesis.

## Estimated effort

1.5 ngày.

## Trạng thái

todo
