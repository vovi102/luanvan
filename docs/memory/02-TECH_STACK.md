# 02 — Tech Stack

> Chỉ thay stack khi có lý do được ghi vào decision log. Version thực tế được
> khai báo trong `pyproject.toml` và khóa bằng `uv.lock`.

## Active NL2SQL stack

| Mục | Lựa chọn | Vai trò |
|---|---|---|
| Query engine | BigQuery Ethereum public dataset | Genuine execution và answer evidence |
| SQL dialect | GoogleSQL | Target duy nhất của active system |
| SQL parser | SQLGlot | Parse, canonicalize và safety validation |
| Small LLM chính | Llama 3 8B Instruct, exact revision phải pin trước genuine run | B1/B2 và nền cho B3 |
| Small LLM phụ | Mistral 7B Instruct, optional | Robustness check nếu timeline cho phép |
| Fine-tuning | PyTorch, Transformers, PEFT, TRL, bitsandbytes | QLoRA B3 trên Kaggle |
| Embedding | sentence-transformers MiniLM | Schema/entity retrieval; multilingual revision chốt bằng dev evidence |
| UI | Gradio | Local defense demo |
| Package manager | uv | Environment và lockfile tái lập |
| Quality | pytest + Ruff | Test, lint và format |

Không dùng remote LLM inference. B0–B3 phải chạy bằng code/model đã pin trên
local hoặc Kaggle; không có provider fallback.

## QLoRA defaults

- 4-bit NF4, double quantization.
- LoRA `r=16`, `alpha=32`, `dropout=0.05`.
- Target modules: `q_proj`, `k_proj`, `v_proj`, `o_proj`.
- Learning rate `2e-4`, cosine scheduler.
- Batch size 4, gradient accumulation 4, tối đa 3 epochs với early stopping.

Defaults chỉ là điểm bắt đầu; config scientific phải được pin và báo đúng theo
artifact thực tế.

## Compute và data

| Mục | Tài nguyên | Guard |
|---|---|---|
| Training/inference | Kaggle T4, Colab backup | Pin model/tokenizer; ghi OOM và latency thật |
| Development | Local CPU/GPU | Không dùng fake completion làm scientific evidence |
| BigQuery | `bigquery-public-data.crypto_ethereum` | Date bounds, dry-run, byte/cost caps |
| Labels | Source snapshots đã verify | Hash, chain provenance và audit trail |

## Demo/deployment

- Local Gradio là đường defense chính và dùng đúng small model nghiên cứu.
- HF Spaces là optional; chỉ interactive nếu resource probe đủ chạy đúng model.
- Nếu resource không đủ, dùng static sealed case studies và ghi rõ không live.
- Không cấp BigQuery write access và không bỏ parse/allowlist/dry-run guards.

## Plan A historical stack

Apache Jena Fuseki/TDB2, Morph-KGC, RML, RDFLib, EthOn và pySHACL chỉ còn phục
vụ tái lập Plan A và negative performance finding. Chúng không nằm trên active
NL2SQL inference path và không quyết định architecture của demo mới.

## Anti-stack

- Remote LLM API hoặc model fallback ngoài ma trận B0–B3.
- Agent framework nặng như LangChain/LlamaIndex cho core pipeline.
- Frontend riêng khi Gradio đã đủ cho defense.
- BigQuery query không có date, dry-run và byte/cost guard.
- Fixture/synthetic execution được trình bày như scientific result.
