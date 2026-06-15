# T5.2 — B1 + B2: Small LLM Zero-Shot & Few-Shot (Llama 3 8B)

## Mục tiêu

Triển khai 2 baselines:
- **B1:** Llama 3 8B Instruct, zero-shot (chỉ system prompt + ontology summary).
- **B2:** Llama 3 8B Instruct, few-shot (5 in-context examples từ training set).

KHÔNG dùng schema/entity linking ở B1/B2 — đó là "raw LLM" baselines để quantify đóng góp linking.

## Bối cảnh & lý do

B1/B2 đo capability "thuần" của LLM nhỏ. Khi so với B3 (fine-tuned) → quantify giá trị fine-tuning. Khi so với Full system (B3 + linking) → quantify giá trị linking (đáp RQ2).

## Phụ thuộc

- T2.1 — Ontology (cấp summary cho prompt).
- T3.5 — Test set 100 câu.
- T3 dataset (training pool, để rút ra few-shot examples cho B2).

## Đầu vào

- Test set `data/dataset/test/test-100.jsonl`.
- Ontology summary (auto-generated từ ontology, ~500 tokens).
- Training pool cho few-shot retrieval (B2).

## Đầu ra

- Module `src/nl2sparql/models/b1_zero_shot.py` và `src/nl2sparql/models/b2_few_shot.py`.
- Predictions `data/eval/predictions/b1_test.jsonl` và `b2_test.jsonl`.
- Inference logs `data/eval/logs/b1_*.log` (tokens, latency).

## Acceptance criteria

- [ ] B1 inference chạy stable trên Kaggle T4 (no OOM).
- [ ] B2 retrieval module dùng sentence-transformers chọn 5 examples gần nhất.
- [ ] Predictions có raw output + parsed SPARQL + extraction status.
- [ ] B1 latency <5s/query trên T4.
- [ ] B2 latency <8s/query (longer prompt).

## Hướng dẫn triển khai

### Common: model loading

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"

def load_llama():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        load_in_4bit=True,  # bitsandbytes nếu T4 không đủ VRAM
    )
    return model, tokenizer
```

### Ontology summary builder

Auto-generate compact summary trong ~500 tokens:

```
ONTOLOGY:

Classes:
- :Account — Ethereum address
- :Transaction — A transfer of value
- :ExchangeAccount — Exchange wallet (subclass of Account)
- :MixerAccount — Mixer service (subclass of Account)
- :DEXProtocol — Decentralized exchange (subclass of Account)
... (15-20 classes)

Properties:
- :hasFrom (Transaction → Account) — sender address
- :hasTo (Transaction → Account) — recipient address
- :hasValue (Transaction → xsd:decimal) — amount in Wei
- :hasTimestamp (Transaction → xsd:dateTime) — execution time
- :hasOwner (Account → xsd:string) — entity name (e.g. "Binance")
... (~30 properties)

PREFIXES:
PREFIX : <http://example.org/eth-kg#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
```

Build script `src/nl2sparql/models/ontology_summary.py` từ ontology TTL.

### B1 prompt template

```python
B1_SYSTEM = """You are an expert SPARQL query writer for Ethereum blockchain
knowledge graph analytics. Given a question in English, write the equivalent
SPARQL 1.1 query.

ONTOLOGY:
{ontology_summary}

Rules:
- Always include PREFIX declarations.
- Use full URIs from the ontology.
- For ETH amounts, values are stored in Wei (1 ETH = 1e18 Wei).
- Output ONLY the SPARQL query. No explanation, no markdown fences.
"""

B1_USER = "Question: {question}\n\nSPARQL:"
```

### B2 retrieval

```python
class FewShotRetriever:
    def __init__(self, train_pool, model_name="all-MiniLM-L6-v2"):
        self.encoder = SentenceTransformer(model_name)
        self.train = train_pool
        self.embeddings = self.encoder.encode(
            [r["nl"] for r in train_pool], normalize_embeddings=True
        )

    def retrieve(self, query, k=5):
        q_emb = self.encoder.encode(query, normalize_embeddings=True)
        scores = self.embeddings @ q_emb
        top_idx = np.argsort(-scores)[:k]
        return [self.train[i] for i in top_idx]
```

### B2 prompt template

```python
B2_SYSTEM = B1_SYSTEM  # same

B2_USER_TEMPLATE = """Here are some examples:

{examples}

Now answer this question.
Question: {question}

SPARQL:"""

def format_example(rec):
    return f"Question: {rec['nl']}\nSPARQL: {rec['sparql']}\n"
```

### Inference loop

```python
def run_baseline(test_set, prompt_fn, model, tokenizer):
    results = []
    for case in tqdm(test_set):
        prompt = prompt_fn(case)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,  # deterministic
                temperature=0.0,
                pad_token_id=tokenizer.eos_token_id,
            )
        raw = tokenizer.decode(output[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        sparql = extract_sparql(raw)
        results.append({
            "id": case["id"],
            "nl": case["nl"],
            "raw_output": raw,
            "predicted_sparql": sparql,
            "extraction_status": "ok" if sparql else "failed",
        })
    return results
```

### SPARQL extraction

```python
def extract_sparql(raw: str) -> Optional[str]:
    # Remove markdown fences
    raw = re.sub(r"```\w*\n?", "", raw)
    raw = re.sub(r"```", "", raw)
    # Trim to first SELECT/CONSTRUCT/ASK/DESCRIBE
    m = re.search(r"(PREFIX[\s\S]+?)(SELECT|CONSTRUCT|ASK|DESCRIBE)[\s\S]+", raw)
    if m:
        return raw[m.start():].strip()
    # Fallback: first occurrence of query keyword
    m = re.search(r"(SELECT|CONSTRUCT|ASK|DESCRIBE)[\s\S]+", raw)
    if m:
        return raw[m.start():].strip()
    return None
```

### Reproducibility

- Seed: `torch.manual_seed(42)`.
- Run 3 lần (B1, B2 nếu sample) → log variance.
- Document temperature, top_p, max_tokens trong file config.

## Rủi ro & note

- **Llama 3 8B base có thể hallucinate prefix sai:** prompt nhấn mạnh "use ontology only".
- **VRAM trên T4 (16GB):** load 4-bit quantize, batch size 1, output ~512 tokens.
- **Few-shot retrieval bias:** examples gần ≠ examples diverse. Có thể thử "diverse retrieval" (k-DPP) cho ablation.
- **Fairness compare:** B1 vs B2 chỉ khác prompt, KHÔNG khác model/seed.

## Estimated effort

2 ngày (1 ngày code + 1 ngày run + analyze).

## Trạng thái

todo
