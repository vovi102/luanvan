# 02 — Tech Stack

> **Quy tắc:** chỉ thay stack khi có lý do mạnh + cập nhật `05-DECISION_LOG.md`. Đừng tự ý đổi vì thấy thư viện mới hơn.

## Knowledge Graph

| Mục | Lựa chọn | Phiên bản | Lý do |
|---|---|---|---|
| Triple store | Apache Jena Fuseki | 4.10+ | Mature, free, hỗ trợ TDB2 persistent, SPARQL 1.1 đầy đủ |
| Storage backend | TDB2 | (built-in) | Persistent, query nhanh cho ≥1M triples |
| RDF mapping | Morph-KGC | latest pip | Python-native, dễ debug; chuẩn RML |
| Fallback mapping | RMLMapper | jar | Java reference impl của RML |
| Ontology editor | Protégé | 5.6+ | De-facto, GUI tốt cho design + check consistency |
| Validation | SHACL (pyshacl) | latest pip | W3C standard, phát hiện vi phạm constraint |
| Library Python | rdflib | 7.x | In-memory KG cho HF Spaces tier; query offline |

**Versions cụ thể được pin trong `requirements.txt` sau Phase 0.**

## ML / Fine-tuning

| Mục | Lựa chọn | Lý do |
|---|---|---|
| LLM nhỏ chính | meta-llama/Meta-Llama-3-8B-Instruct | License rõ, ecosystem rộng |
| LLM nhỏ phụ | mistralai/Mistral-7B-Instruct-v0.3 | So sánh, robust baseline |
| LLM lớn (qua API) | Llama 3 70B / Mistral Large / Qwen2 72B | Qua OpenRouter free tier, không lock vendor |
| Framework | PyTorch | 2.3+ |
| Trainer | transformers + peft + trl + bitsandbytes | QLoRA 4-bit |
| Tokenizer | tokenizers | (đi kèm transformers) |
| Embedding | sentence-transformers | MiniLM-L6-v2 (fast, 384d) cho linking |
| Constrained decoding | outlines hoặc lm-format-enforcer | Grammar-based để giảm syntax errors |

**QLoRA hyperparam mặc định** (điều chỉnh sau ablation Phase 6):
- 4-bit nf4 quantization, double quant
- LoRA r=16, alpha=32, dropout=0.05
- Target modules: `q_proj, k_proj, v_proj, o_proj`
- Learning rate 2e-4, cosine scheduler
- Batch size 4, grad accumulation 4 → effective 16
- Epochs 3 (early stop trên val loss)

## Compute

| Mục | Tài nguyên | Hạn mức |
|---|---|---|
| Kaggle | T4 ×2 hoặc P100 | 30h/tuần GPU |
| Colab (backup) | T4 free / A100 paid | hạn mức biến động |
| OpenRouter | LLM 70B+ | free tier, rate limit |
| Local | CPU + Fuseki | RAM ≥16GB cho TDB2 |

## Data sources

| Mục | Nguồn | Free tier |
|---|---|---|
| Ethereum on-chain | BigQuery `bigquery-public-data.crypto_ethereum` | 1TB query/tháng |
| Entity labels | Etherscan public, Dune Analytics, Arkham (manual scrape) | Sample chứ không bulk |
| Existing ontology | EthOn (ethon.consensys.net), schema.org | Open |

## Demo / Deploy

| Mục | Lựa chọn | Lý do |
|---|---|---|
| UI | Gradio | 1 file, chạy được trên HF Spaces |
| Hosting | HF Spaces (free CPU) | Free, public, dễ share |
| Local serving | uvicorn + Gradio | Khi cần full system với Fuseki |

## Anti-stack — KHÔNG dùng

- **Neo4j / property graph DB:** vì thesis về KG/SPARQL, không phải Cypher.
- **Sông pha graph + embedding (RDF2Vec, etc.):** không nằm trong scope thesis này.
- **LangChain/LlamaIndex agent framework:** lock-in nặng, đánh đổi reproducibility, đa phần black-box.
  - Có thể dùng `langchain-text-splitters` đơn lẻ. Không dùng `LangChain agents`.
- **OpenAI API trực tiếp:** chi phí không bền vững cho thesis dài; OpenRouter có free tier rotate.
- **Fancy frontend (Next.js, React):** không cần. Gradio đủ.
- **Docker compose phức tạp:** cố gắng giữ "git clone + pip install + run" càng đơn giản càng tốt.

## Tooling phụ

| Mục | Lựa chọn |
|---|---|
| Lint Python | ruff |
| Format | ruff format (hoặc black) |
| Type check | (optional) pyright/mypy nhẹ |
| Test | pytest |
| Notebook | Jupyter (Kaggle/Colab native) |
| Tracking experiment | wandb (free tier) hoặc local CSV log |
| Version | git + GitHub (public repo) |

## Ngôn ngữ

- **Code, identifiers, comments trong code:** English.
- **Documentation, task files, memory:** Vietnamese (kèm thuật ngữ EN khi cần).
- **Thesis:** Vietnamese (hoặc song ngữ tùy yêu cầu trường).
- **Bài báo:** English.
