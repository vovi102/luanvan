# T6.1 — B3: QLoRA Fine-Tune Llama 3 8B Instruct

## Mục tiêu

Fine-tune Llama 3 8B Instruct với QLoRA (4-bit) trên ~1000 cặp NL-SPARQL, lưu LoRA checkpoint reusable cho ablation.

## Bối cảnh & lý do

B3 là baseline trung tâm trả lời RQ1 ("LLM nhỏ fine-tuned đủ dùng?"). QLoRA chọn vì:
- Fit Kaggle T4 (16GB VRAM).
- LoRA adapter nhẹ (~50MB), dễ ablate (swap r, target modules).
- Chuẩn industry hiện tại.

## Phụ thuộc

- T3 hoàn tất — `data/dataset/raw/synthetic-stage-d.jsonl` (~3000 records sau augment).
- T2 hoàn tất — Fuseki KG để có thể chạy validation queries trong eval.
- Kaggle T4 quota ≥10h.

## Đầu vào

- Train pool ~3000 records (split 90/10 → train/val).
- Test set 100 (separate, NOT touched).
- Llama 3 8B Instruct base.

## Đầu ra

- Checkpoint `models/b3-llama3-8b-qlora/` (chỉ LoRA weights).
- Training log `models/b3-llama3-8b-qlora/training.log`.
- W&B run (optional, free).
- Notebook `notebooks/14_b3_train.ipynb` reproducible.
- Predictions `data/eval/predictions/b3_test.jsonl`.

## Acceptance criteria

- [ ] Training hoàn tất 3 epochs trên Kaggle T4 trong <8h.
- [ ] Validation loss giảm monotonically (không overfit nặng).
- [ ] Inference với LoRA chạy stable.
- [ ] Predictions trên test set 100 hoàn tất.
- [ ] Checkpoint reproducible: cùng seed → same loss curve (within noise).

## Hướng dẫn triển khai

### Data formatting

Llama 3 chat template:

```python
def format_example(rec):
    system = "You are an expert SPARQL query writer for Ethereum blockchain analytics. Output only the SPARQL query."
    user = f"Question: {rec['nl']}"
    assistant = rec["sparql"]
    return f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system}<|eot_id|><|start_header_id|>user<|end_header_id|>

{user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

{assistant}<|eot_id|>"""
```

### Train/val split

Stratified 90/10 by template_id (đảm bảo val có distribution giống train):

```python
from sklearn.model_selection import train_test_split

train_data, val_data = train_test_split(
    records,
    test_size=0.1,
    stratify=[r["template_id"] for r in records],
    random_state=42
)
```

### QLoRA config

```python
from transformers import (
    AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3-8B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",
)
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Should print ~0.5% trainable
```

### Training config

```python
training_args = SFTConfig(
    output_dir="models/b3-llama3-8b-qlora",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,  # effective batch 16
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    bf16=True,
    optim="paged_adamw_8bit",
    logging_steps=10,
    save_strategy="epoch",
    eval_strategy="epoch",
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    seed=42,
    report_to="wandb",
)

trainer = SFTTrainer(
    model=model,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    args=training_args,
    tokenizer=tokenizer,
    max_seq_length=1024,
    dataset_text_field="text",
)
trainer.train()
```

### Memory budget T4 16GB

- Llama 3 8B 4-bit: ~5GB.
- Activations: ~2-3GB (batch 4, seq 1024).
- Optimizer states LoRA: ~200MB.
- Headroom: 7-8GB. OK.

Nếu OOM:
- Giảm `per_device_train_batch_size` xuống 2.
- Tăng `gradient_accumulation_steps` lên 8.
- `max_seq_length` 768 thay 1024.

### Inference

```python
from peft import PeftModel

base = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3-8B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",
)
model = PeftModel.from_pretrained(base, "models/b3-llama3-8b-qlora")
model.eval()

# Use same prompt format as B1 (from T5.2)
def predict_b3(nl, ontology_summary):
    prompt = format_chat(system=B1_SYSTEM.format(ontology_summary=ontology_summary), user=f"Question: {nl}")
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=512, do_sample=False, temperature=0.0)
    raw = tokenizer.decode(output[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return extract_sparql(raw)
```

### Hyperparameter for ablation

Default ở đây là baseline B3. T6.3 (ablation) sẽ vary:
- `r` ∈ {8, 16, 32}.
- `target_modules` ∈ {qv_only, qkvo, qkvo_gate}.
- `lr` ∈ {1e-4, 2e-4, 5e-4}.

Lưu config mỗi run vào `config.json` cạnh checkpoint.

### Reproducibility

```python
import random, numpy as np, torch
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
torch.cuda.manual_seed_all(42)
```

Lưu `requirements.txt` snapshot trong checkpoint dir.

### W&B logging (optional)

Free tier OK cho thesis. Track:
- train_loss, eval_loss curves.
- Learning rate schedule.
- Sample generations every 100 steps (qualitative check).

## Rủi ro & note

- **Overfit nặng (eval_loss tăng từ epoch 2):** giảm epochs xuống 2; tăng dropout 0.1.
- **Kaggle 9-hour limit per session:** nếu run >8h, save checkpoint mỗi epoch để resume.
- **Loss flatlines từ đầu:** check tokenizer chat template (nhiều bug nổi tiếng), check learning rate (có thể quá thấp).
- **Save quá nhiều disk:** Kaggle free tier 20GB, mỗi epoch checkpoint ~50MB OK nhưng skip optimizer state nếu cần (`save_safetensors=True` không có optim state).

## Estimated effort

3-4 ngày (1 ngày setup + 2 ngày train/iterate + 1 ngày eval).

## Trạng thái

todo
