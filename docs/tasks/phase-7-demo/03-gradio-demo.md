# T7.3 — Local Gradio Demo (Tier 1: Full System)

## Mục tiêu

Xây dựng Gradio web app local với full backend (Fuseki + B3 + linkers + validator). User type câu hỏi → thấy SPARQL + kết quả + trace pipeline.

## Bối cảnh & lý do

Demo là DELIVERABLE chính cho thesis defense. Phải:
- Chạy được trong defense (laptop GVHD/họp đồng chấm).
- Show pipeline transparency (không black box).
- Handle errors gracefully.

Tier 1 = local full system. Tier 2 = HF Spaces showcase (T7.4).

## Phụ thuộc

- T7.1 — Validator + recovery.
- T6.1 — B3 model.
- T2.4 — Full KG trên Fuseki.

## Đầu vào

- Pipeline modules đầy đủ.
- Model checkpoint.
- Fuseki running locally.

## Đầu ra

- App `src/nl2sparql/demo/app.py`.
- Config `src/nl2sparql/demo/config.yaml`.
- Run script `run_demo.sh`.
- README `src/nl2sparql/demo/README.md` (cách chạy + screenshots).
- Recording demo video MP4 ~3 phút (cho thesis appendix).

## Acceptance criteria

- [ ] App khởi động <30s từ cold start.
- [ ] Latency tổng query <8s (typical).
- [ ] UI có 4 panels: Input, Pipeline trace (linking + SPARQL), Result table, Logs.
- [ ] Responsive: không freeze khi query long.
- [ ] Có 5-10 example queries pre-filled.
- [ ] Demo không crash trên 30 runs liên tiếp (stress test).

## Hướng dẫn triển khai

### Architecture

```
[Gradio UI]
  │
  ├─ Input box (NL question)
  ├─ Submit button
  ├─ Loading spinner
  │
  ├─ [Trace Panel]
  │    ├─ Schema linker output (top-K props)
  │    ├─ Entity linker output (matched entities)
  │    ├─ Generated SPARQL (syntax highlighted)
  │    └─ Validator status (green/red)
  │
  ├─ [Result Panel]
  │    └─ DataFrame display
  │
  └─ [Logs Panel]
       └─ Latency breakdown, recovery info
```

### Gradio code skeleton

```python
import gradio as gr
from src.system.pipeline import Pipeline

pipeline = Pipeline.from_config("src/nl2sparql/demo/config.yaml")

def query_handler(nl_question):
    if not nl_question.strip():
        return "", "", None, "Please enter a question."

    trace = {}
    t_start = time.time()

    # Step 1: linking
    schema = pipeline.schema_linker.link(nl_question, top_k=10)
    entities = pipeline.entity_linker.link(nl_question)
    trace["linking_ms"] = (time.time() - t_start) * 1000

    # Step 2: generate SPARQL
    t_gen = time.time()
    sparql, val = pipeline.predict_with_recovery(nl_question)
    trace["generate_ms"] = (time.time() - t_gen) * 1000

    # Step 3: execute
    t_exec = time.time()
    if sparql:
        try:
            result_df = pipeline.execute(sparql, timeout=15)
        except Exception as e:
            return _format_trace(schema, entities, sparql, val), "", None, f"Execution error: {e}"
        trace["execute_ms"] = (time.time() - t_exec) * 1000
    else:
        return _format_trace(schema, entities, None, val), "", None, "Could not generate valid SPARQL after retry."

    trace_md = format_trace_markdown(schema, entities, sparql, val, trace)
    log_text = format_log(trace, val)
    return trace_md, sparql, result_df, log_text


with gr.Blocks(title="NL2SPARQL Blockchain Demo", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# NL2SPARQL — Blockchain Knowledge Graph Demo")
    gr.Markdown("Ask questions in English about Ethereum data. See the SPARQL query and pipeline trace.")

    with gr.Row():
        with gr.Column(scale=2):
            nl_input = gr.Textbox(
                label="Question",
                placeholder="e.g. Top 10 transactions from Binance to Tornado Cash last week",
                lines=2,
            )
            submit_btn = gr.Button("Run", variant="primary")

            gr.Examples(
                examples=[
                    "Top 10 transactions by value yesterday",
                    "Transactions from Binance to any mixer last month",
                    "How many transactions did Uniswap V3 process?",
                    "Find addresses that sent more than 1000 ETH to a known exchange",
                    "Hourly distribution of transactions on 2024-01-15",
                ],
                inputs=nl_input,
            )

        with gr.Column(scale=3):
            trace_md = gr.Markdown(label="Pipeline trace")
            sparql_out = gr.Code(label="Generated SPARQL", language="sql")
            result_table = gr.DataFrame(label="Result")
            log_box = gr.Textbox(label="Log", lines=4)

    submit_btn.click(
        query_handler,
        inputs=[nl_input],
        outputs=[trace_md, sparql_out, result_table, log_box],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
```

### Trace formatting

```python
def format_trace_markdown(schema, entities, sparql, val, trace):
    md = "## Pipeline Trace\n\n"
    md += "### 1. Schema Linker (top-5 properties)\n\n"
    for uri, score in schema["properties"][:5]:
        md += f"- `{uri}` ({score:.2f})\n"

    md += "\n### 2. Entity Linker\n\n"
    for ent in entities:
        md += f"- **{ent.span}** → {ent.matched_to} ({ent.stage}, conf={ent.confidence:.2f})\n"

    md += f"\n### 3. Validator\n\n"
    if val.valid:
        md += "Valid\n"
    else:
        md += "Errors:\n"
        for e in val.errors:
            md += f"- {e.type}: {e.message}\n"

    md += f"\n### 4. Latency\n\n"
    md += f"- Linking: {trace.get('linking_ms', 0):.0f} ms\n"
    md += f"- Generation: {trace.get('generate_ms', 0):.0f} ms\n"
    md += f"- Execution: {trace.get('execute_ms', 0):.0f} ms\n"
    return md
```

### Streaming (optional, nicer UX)

Gradio supports `gr.update()` streaming. Update trace panel as each stage completes:

```python
def query_streaming(nl):
    yield "Linking...", "", None, ""
    schema = pipeline.schema_linker.link(nl)
    yield format_partial(schema), "", None, "Linking done"

    yield format_partial(schema), "Generating...", None, "Generating..."
    sparql, val = pipeline.predict(nl)
    yield format_partial(schema, sparql=sparql), sparql, None, "Generated"

    yield format_partial(...), sparql, "Executing...", "Running query"
    df = pipeline.execute(sparql)
    yield format_full(...), sparql, df, "Done"
```

### Configuration

`src/nl2sparql/demo/config.yaml`:

```yaml
fuseki_endpoint: http://localhost:3030/eth-kg/sparql
model:
  base: meta-llama/Meta-Llama-3-8B-Instruct
  adapter: models/b3-llama3-8b-qlora
  quantization: 4bit
linking:
  schema_top_k: 10
  entity_threshold: 0.75
inference:
  max_new_tokens: 512
  timeout_seconds: 15
recovery:
  max_retries: 1
demo:
  port: 7860
  share: false
  examples_path: src/nl2sparql/demo/examples.json
```

### Run script

```bash
#!/bin/bash
# run_demo.sh

# Check Fuseki running
if ! curl -s http://localhost:3030/$/ping > /dev/null; then
    echo "Starting Fuseki..."
    ./apache-jena-fuseki/fuseki-server --config=fuseki-config.ttl &
    sleep 5
fi

python -m src.demo.app
```

### Stress test

```python
# tests/stress_demo.py
import requests
queries = [...]  # 30 queries from test set
for i, q in enumerate(queries):
    resp = requests.post("http://localhost:7860/run/predict", json={"data": [q]})
    assert resp.status_code == 200
    print(f"{i}: OK")
```

### Recording demo video

- Tool: OBS Studio (free) hoặc Loom.
- Length: 2-3 phút.
- Script:
  1. Intro 15s — what is the demo.
  2. 3 questions: easy, medium, hard.
  3. Show 1 error + recovery.
  4. Outro 10s — link to repo.

## Rủi ro & note

- **Cold start latency:** model load ~30s đầu. Mitigate: warm load on app start, show progress bar.
- **Concurrent requests:** Gradio default single-threaded. Defense thường 1 user — OK. Nếu cần parallel, add `concurrency_count=2`.
- **VRAM crash mid-demo:** preload model + first dummy inference khi start app.
- **Fuseki down:** check loop, restart, log clearly.

## Estimated effort

2-3 ngày.

## Trạng thái

todo
