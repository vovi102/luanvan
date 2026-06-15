# T7.4 — HuggingFace Spaces Deploy (Tier 2: Showcase)

## Mục tiêu

Deploy phiên bản showcase trên HuggingFace Spaces (free CPU tier) — accessible online cho hội đồng + reviewer + cộng đồng.

## Bối cảnh & lý do

HF Spaces free = không Java, không GPU, ~16GB RAM. KHÔNG chạy được Fuseki + Llama 8B. Nên Tier 2 là **simplified version**:
- Mini KG (~10% data, ~5M triples) load qua **rdflib in-memory** (không Fuseki).
- Inference qua **OpenRouter API** (Llama 70B), không local model.
- Hoặc: chỉ demo template-based / cached responses cho tốc độ.

Tier 2 phục vụ "công bố thesis", Tier 1 (T7.3) phục vụ defense.

## Phụ thuộc

- T7.3 — Local demo working (cùng codebase, simplified).
- HuggingFace account.
- Mini KG đã được lọc.

## Đầu vào

- 10% sample của full KG (saved as TTL/N3 ~10-50MB).
- OpenRouter API key (ép vào secrets HF).
- Codebase từ T7.3.

## Đầu ra

- Repo HF Spaces `huggingface.co/spaces/<user>/nl2sparql-eth-demo`.
- File `app.py`, `requirements.txt`, `README.md` cho HF.
- File `mini_kg.ttl` (commit vào Space hoặc HF dataset).
- Documentation `docs/deployment/hf_spaces.md`.

## Acceptance criteria

- [ ] Space chạy thành công, accessible URL.
- [ ] Latency <15s/query (chấp nhận chậm hơn local vì OpenRouter).
- [ ] 10 example queries pre-filled, all run thành công.
- [ ] Build time <10 phút (HF tier free hard limit).
- [ ] README rõ giới hạn (mini KG 10%, ~X-Y date range).

## Hướng dẫn triển khai

### Mini KG creation

Lấy 10% transactions stratified:

```python
# Take 10% transactions, plus all related accounts/labels
import rdflib
g_full = rdflib.Graph()
g_full.parse("data/eth-kg/output.nt", format="nt")

# Sample tx
tx_uris = list(g_full.subjects(predicate=RDF.type, object=ETH.Transaction))
sampled_tx = random.sample(tx_uris, len(tx_uris) // 10)

g_mini = rdflib.Graph()
for tx in sampled_tx:
    for s, p, o in g_full.triples((tx, None, None)):
        g_mini.add((s, p, o))
    # Also include the related accounts
    for from_acc in g_full.objects(tx, ETH.hasFrom):
        for s, p, o in g_full.triples((from_acc, None, None)):
            g_mini.add((s, p, o))
    for to_acc in g_full.objects(tx, ETH.hasTo):
        for s, p, o in g_full.triples((to_acc, None, None)):
            g_mini.add((s, p, o))

# Add all class hierarchy + entity labels
for s, p, o in g_full.triples((None, ETH.hasOwner, None)):
    g_mini.add((s, p, o))

g_mini.serialize("data/mini_kg.ttl", format="turtle")
```

Target ~10-30MB compressed.

### App.py for HF Spaces

```python
import os
import gradio as gr
import rdflib
import openai  # for OpenRouter

OPENROUTER_KEY = os.environ["OPENROUTER_API_KEY"]
client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
)

# Load mini KG once at startup
print("Loading mini KG...")
G = rdflib.Graph()
G.parse("mini_kg.ttl", format="turtle")
print(f"Loaded {len(G)} triples")

ONTOLOGY_SUMMARY = open("ontology_summary.txt").read()

def generate_sparql(nl):
    """Use OpenRouter Llama 70B."""
    resp = client.chat.completions.create(
        model="meta-llama/llama-3-70b-instruct",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(ontology=ONTOLOGY_SUMMARY)},
            {"role": "user", "content": f"Question: {nl}\n\nSPARQL:"},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw = resp.choices[0].message.content
    return extract_sparql(raw)

def execute_sparql(sparql, timeout=10):
    try:
        results = G.query(sparql)
        rows = [{str(k): str(v) for k, v in row.asdict().items()} for row in results]
        return rows
    except Exception as e:
        return [{"error": str(e)}]

def query_handler(nl):
    if not nl:
        return "", "", None
    sparql = generate_sparql(nl)
    if not sparql:
        return "Could not generate SPARQL", "", None
    results = execute_sparql(sparql)
    df = pd.DataFrame(results) if results else None
    return f"```sparql\n{sparql}\n```", sparql, df

with gr.Blocks() as demo:
    gr.Markdown("# NL2SPARQL Blockchain Demo (Showcase)")
    gr.Markdown("""
    **Note:** This is a simplified showcase running on HuggingFace Spaces (free CPU tier).
    - Mini KG: ~10% sample of full Ethereum data (Jan 2024).
    - Uses Llama 3 70B via OpenRouter (small fine-tuned model in local Tier 1 demo).
    - Limited query types — see examples below.

    Full system + thesis: [GitHub repo](...)
    """)

    nl_input = gr.Textbox(label="Question", lines=2)
    btn = gr.Button("Run")
    sparql_md = gr.Markdown()
    result = gr.DataFrame()

    btn.click(query_handler, inputs=[nl_input], outputs=[sparql_md, gr.State(), result])

    gr.Examples(
        examples=[...],  # curated to work on mini KG
        inputs=nl_input,
    )

if __name__ == "__main__":
    demo.launch()
```

### requirements.txt

```
gradio==4.40.0
rdflib==7.0.0
openai==1.40.0
pandas==2.2.0
sentence-transformers==2.7.0  # for entity linker if used
```

KHÔNG include: torch, transformers (tránh build time long, model size lớn).

### Repo structure

```
hf_space/
├── app.py
├── requirements.txt
├── README.md           # HF README (markdown shown on Space page)
├── mini_kg.ttl         # 10-30MB
├── ontology_summary.txt
├── examples.json       # curated examples
└── .gitattributes      # large file via LFS if needed
```

### README.md (HF Space)

```markdown
---
title: NL2SPARQL Blockchain Demo
emoji: 🔍
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.40.0
app_file: app.py
pinned: false
license: mit
---

# NL2SPARQL Blockchain — Showcase Demo

This is the Tier 2 showcase demo for my master's thesis on Natural Language to SPARQL translation for blockchain analytics.

## Limitations of this demo

- **Mini KG (10% sample):** ~5M triples covering Jan 2024 Ethereum mainnet.
- **Uses external LLM API:** Llama 3 70B via OpenRouter (NOT the small fine-tuned model from the thesis).
- **No constrained decoding, no entity linker:** simplified for showcase.

## Full system

Full implementation with QLoRA fine-tuned Llama 3 8B + Fuseki backend:
[GitHub repo link]

## Thesis

[Link to thesis PDF]
```

### Secrets management

HF Spaces UI → Settings → Variables and secrets:
- `OPENROUTER_API_KEY` (secret).

KHÔNG hardcode key trong app.py hoặc commit lên repo.

### Cost monitoring

OpenRouter sẽ tính cost mỗi query. Nếu Space được public + có traffic:
- Set spending limit trên OpenRouter dashboard ($10 budget cap).
- Monitor traffic; nếu spike, có thể disable share temporarily.

### Build optimization

- Mini KG file: dùng `git lfs` nếu >10MB.
- Avoid heavy deps trong requirements.
- Cache rdflib parse: HF Spaces có persistent /data, nhưng free tier reset on rebuild.

### Alternative: cached responses

Nếu OpenRouter cost concern hoặc latency:
- Pre-compute responses cho 50 example queries.
- Demo mode = "lookup cache" + "API fallback".
- User type → fuzzy match cache → instant response. Cache miss → API.

Document mode trong README.

## Rủi ro & note

- **HF free tier sleep after 48h idle:** acceptable, restart on visit.
- **OpenRouter rate limit:** không nghiêm trọng cho demo low traffic.
- **Mini KG quality:** một số example queries có thể trả empty trên mini KG. Curate examples kỹ.
- **Privacy reverse:** Tier 2 send data đến OpenRouter — note trong README rõ ràng (đối lập với Tier 1 fully local).

## Estimated effort

1-2 ngày.

## Trạng thái

todo
