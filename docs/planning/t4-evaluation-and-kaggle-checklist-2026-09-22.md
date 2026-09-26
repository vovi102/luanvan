# Checklist thực hiện T4 và Kaggle — 2026-09-22

## Phân vai và nguyên tắc bằng chứng

| Hạng mục | Người thực hiện | Kết quả được phép kết luận |
|---|---|---|
| T3.5: soạn câu hỏi và GoogleSQL gold | Codex | Bộ **agent-authored** để bạn review; không gọi là benchmark 3-pool độc lập. |
| T3.5: duyệt chất lượng, độ khó, SQL/BigQuery evidence | Bạn | Bộ test có human-review; ghi rõ giới hạn về tính độc lập. |
| T4.1–T4.3: gán gold label | Bạn | Ground truth được human-reviewed, tách biệt với train/T3.5. |
| T4.1–T4.3: format validation, chạy evaluator, report | Codex | Metrics/reproducibility report, sau khi bạn chấp nhận nhãn. |
| B1/B2 Kaggle: chuẩn bị tài khoản, notebook và quyền model | Bạn | Môi trường compute sẵn sàng và evidence provenance. |
| B1/B2 Kaggle: code notebook/evaluator và phân tích artifact | Codex | Run có thể tái lập; không tự dùng credential của bạn. |

Không dùng cùng một câu hỏi cho T3.5, T4 ground truth hoặc dữ liệu train/validation.
Không ghi API key/Hugging Face token, BigQuery credential hay dữ liệu định danh vào Git,
Kaggle Dataset công khai hoặc notebook output.

## Completion record — 2026-09-26

T4.1–T4.3 đã được human-review và promote từ bộ nháp agent-authored vào
`data/eval/`. Cả ba evaluator trả `status=ready` trên ground-truth snapshot đã
khóa hash:

| Component | Rows | Kết quả chính | Latency | Status |
|---|---:|---|---|---|
| T4.1 Schema Linker | 50 | Field Recall@10 `0.808`; relation Recall@5 `0.9636` | p95 `26.52 ms` | ready |
| T4.2 Entity Linker | 100 | Top-1/F1 `1.0/1.0` | warm p95 `119.71 ms` | ready |
| T4.3 Class Resolver | 50 | plan/direction/kind accuracy `1.0/1.0/1.0`; 5 coverage gaps | n/a | ready |

Giới hạn provenance vẫn áp dụng: câu và nhãn ban đầu do agent soạn, sau đó được
human-review bằng 162 quyết định `ACCEPT` và 38 quyết định `REVISE`; không claim
independent authorship hoặc inter-rater agreement. Bộ T4 đã được dùng để chẩn
đoán và cải thiện linker ngày 2026-09-26, nên các chỉ số trên là **post-tuning
development acceptance**, không phải ước lượng generalization trên holdout độc
lập. Snapshot được khóa từ đây; benchmark cuối vẫn là T3.5/BigQuery và không được
tune theo T4.

## A. T3.5 — workflow do Codex soạn, bạn duyệt

1. Codex tạo 120 ứng viên `question + GoogleSQL + expected_columns`, phủ difficulty
   mục tiêu 30 Easy / 50 Medium / 20 Hard sau khi loại bớt 20 ứng viên.
2. Codex kiểm tra SQL read-only, allowlist catalog, projection rõ ràng và không trùng
   với training/fixture theo normalized question.
3. Bạn review 120 ứng viên theo ba quyết định: `ACCEPT`, `REVISE`, `REJECT`; với mỗi
   `REVISE/REJECT`, ghi lý do ngắn (mơ hồ, SQL sai, không tự nhiên, ngoài catalog,
   duplicate, hay difficulty sai).
4. Codex sửa/loại theo quyết định của bạn, chốt đúng 100 bản ghi và chạy validator.
5. Khi BigQuery credential sẵn sàng, Codex chạy dry-run rồi live verification; bạn
   duyệt các trường hợp empty result hoặc tranh cãi trước khi `finalize`.

**Giới hạn phải ghi trong luận văn/report:** tác giả câu hỏi và gold SQL là agent;
bạn là human reviewer. Đây không phải thiết kế 3-pool độc lập hoặc inter-rater
reliability. Không báo Cohen's kappa hoặc claim “independently authored”.

## B. T4 — checklist cho bạn đánh giá

### B0. Chuẩn bị chung (làm một lần)

- [ ] Xác nhận chỉ đánh giá câu tiếng Anh, mục tiêu là GoogleSQL analytical catalog.
- [ ] Cam kết không tái sử dụng câu từ `data/dataset/final/`, Stage A–D, fixture,
  hoặc T3.5; Codex sẽ kiểm tra duplicate khi nhận file.
- [ ] Dùng mã reviewer ổn định, ví dụ `reviewer-01`; không ghi họ tên/email trong
  JSONL hay Git.
- [ ] Đọc catalog: `src/nl2sparql/sql/catalog/ethereum_analytics.json` và dictionary
  reviewed: `data/entity_dictionary/curated/reviewed_ethereum_entities.csv`.
- [ ] Chấm theo ý nghĩa của câu hỏi, không theo output của linker; nếu câu mơ hồ thì
  ghi câu khác thay vì cố chọn nhãn.
- [ ] Lưu bản nháp ngoài các path canonical; chỉ đưa bản đã duyệt vào `data/eval/`.

### B1. T4.1 Schema Linker — 50 câu

Mục tiêu: mỗi câu có quan hệ và field thực sự cần để trả lời. Không cần GoogleSQL
hoàn chỉnh.

- [ ] Soạn/chọn đúng 50 câu độc nhất, đa dạng filter, aggregation, top-k, time range,
  transfer direction, token, label/category và relation join.
- [ ] Với mỗi câu, liệt kê tối thiểu một `gold_relations` và một `gold_fields` từ
  catalog. Relation chứa mỗi field phải xuất hiện trong `gold_relations`.
- [ ] Kiểm tra element ID đúng chính tả và không thêm field chỉ “có thể hữu ích”.
- [ ] Lưu một JSON object mỗi dòng vào `data/eval/schema_link_groundtruth.jsonl`:

```json
{"id":"schema-001","nl":"Which tokens had the most transfers in June 2026?","gold_relations":["token_transfer_facts"],"gold_fields":["token_transfer_facts.token_address","token_transfer_facts.block_timestamp"]}
```

- [ ] Gửi file cho Codex để validate exact-50, rebuild/strict-load index nếu cần và
  chạy `scripts/13_schema_linker.py evaluate`.
- [ ] Review report: Field Recall@10 phải >= 0.80; kiểm tra p50/p95 warm latency và
  các error case trước khi chấp nhận report.

### B2. T4.2 Entity Linker — 100 câu

Mục tiêu: đo nhận diện owner/entity, không đánh giá SQL. Mỗi câu bắt buộc có ít nhất
một named owner trong dictionary.

- [ ] Soạn/chọn đúng 100 câu độc nhất, mỗi câu có ít nhất một owner có trong
  dictionary (ví dụ target ID `owner:Binance`, nếu ID đó còn tồn tại trong file
  dictionary hiện tại).
- [ ] Với từng mention, copy chính xác substring của `question`; `span_offset` là
  offset ký tự `[start, end]` kiểu Python, end-exclusive. Không tự chuẩn hoá hoặc
  sửa case trong `span`.
- [ ] Nếu một câu có nhiều entity, gán tất cả mention; tránh câu không có entity và
  tránh alias mơ hồ nếu không có gold target duy nhất.
- [ ] Lưu mỗi dòng theo schema:

```json
{"id":"entity-001","question":"Show transfers from Binance.","mentions":[{"span":"Binance","span_offset":[20,27],"target_id":"owner:Binance"}]}
```

- [ ] Gửi `data/eval/entity_link_groundtruth.jsonl` cho Codex validate và chạy
  `scripts/14_entity_linker.py evaluate`.
- [ ] Review Top-1 >= 0.85, warm p95 < 200 ms, candidate/error cases và hash trong
  report. Nếu dictionary cập nhật sau khi chấm, phải chấm lại target IDs bị ảnh hưởng.

### B3. T4.3 Class Resolver — 50 câu

Đây là nhãn khó nhất vì input là typed entity evidence và output là constraint plan.
Bạn chỉ cần quyết định semantics; Codex sẽ tạo nháp `matches` theo dictionary/linker
để bạn kiểm tra trước khi file được chốt.

- [ ] Chọn đúng 50 câu độc nhất có owner, concept hoặc raw address; gồm directional
  `from/to`, concept class, coverage gap và ít nhất một case mơ hồ/fail-closed.
- [ ] Với từng entity mention, xác nhận `target_id`, `resolution_kind`, `direction`
  (`from`, `to`, hoặc `unspecified`) và `coverage_status` thay vì tự suy ra SQL.
- [ ] Với case concept, chấp nhận `coverage_gap` nếu dictionary không có endpoint;
  không ép resolver gán address không có evidence.
- [ ] Gửi danh sách câu + quyết định semantics cho Codex tạo JSONL canonical
  `data/eval/class_resolver_groundtruth.jsonl`; sau đó review diff bản nháp.
- [ ] Sau khi bạn chấp nhận bản nháp, Codex chạy `scripts/15_class_resolver.py
  evaluate`; bạn review fully-resolved plan accuracy (mục tiêu >= 0.90) và các
  unresolved/coverage-gap cases.

## C. Kaggle — checklist chuẩn bị cho B1/B2 và tùy chọn B3

### C1. Tài khoản, quota và notebook

- [ ] Đăng nhập/xác minh tài khoản Kaggle; kiểm tra Accelerator quota còn đủ trong
  profile/Notebook settings. Quota thay đổi theo thời điểm, nên chụp màn hình hoặc
  ghi ngày + số giờ còn lại vào experiment log.
- [ ] Tạo **private** Python Notebook, đặt tên có run ID, ví dụ
  `nl2sql-b1-b2-2026-09-22-r01`; không bật public cho tới khi đã rà soát data.
- [ ] Trong Settings, chọn GPU; chạy cell smoke và lưu output hardware:

```python
import platform, torch
print(platform.platform())
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO_GPU")
```

- [ ] Dùng `Save Version` / `Save & Run All` cho mỗi run chính thức; ghi URL/version
  của notebook vào experiment log. Kaggle hiện công bố session CPU/GPU tối đa 12h và
  `/kaggle/working` auto-saved 20 GB, nên checkpoint phải nằm ở đó rồi export ra.
- [ ] Chủ động stop interactive session không dùng để tiết kiệm quota; không dùng
  batch commit như checkpoint giữa chừng.

### C2. Model và data input (chỉ khi artifact đã ready)

- [ ] Chỉ bắt đầu B1/B2 scientific run khi có: Stage D training artifact đã accept,
  T3.5 test-100 đã human-review + live-verified, và split/hash manifest đã chốt.
- [ ] Tạo Kaggle Dataset **private** cho input immutable: train/validation/test,
  catalog, dictionary/synonym và manifest SHA-256. Không upload `.env`, service
  account JSON, raw collaborator metadata hoặc report có secret.
- [ ] Chấp nhận license của model gốc trên Hugging Face/Kaggle nếu model yêu cầu;
  chuẩn bị token đọc-only riêng trong Kaggle Secrets, không viết token vào cell,
  output hay commit.
- [ ] Pin chính xác `model_id`, revision/commit SHA, tokenizer revision, dataset
  version, Python/Torch/Transformers/PEFT/BitsAndBytes versions trước run. Với
  internet chỉ cần để tải dependency/model ban đầu; sau khi cache hoặc dùng model
  dataset, tắt internet cho rerun tái lập nếu notebook không cần network.

### C3. Kế hoạch chạy và artifact phải giữ

- [ ] Chạy smoke B1/B2 trên 5 câu không thuộc test; xác nhận model load, 4-bit
  inference, SQL validator và artifact writer hoạt động, không OOM.
- [ ] Chốt run config trước full run: baseline (B1/B2), seed, max input/new tokens,
  batch size, quantization, model revision và deadline/timeout.
- [ ] Chạy full evaluation đúng một test snapshot; không chỉnh prompt/hyperparameter
  sau khi xem prediction test. Mọi thay đổi tạo run ID mới.
- [ ] Lưu/đưa lại cho Codex: notebook URL + version, `nvidia-smi`, package freeze,
  input file hashes, model revision, config JSON, predictions, metrics/report,
  stdout/stderr, OOM/timeout notes và elapsed time.
- [ ] Download output từ `/kaggle/working` và giữ immutable copy trong artifact store
  hoặc Kaggle Dataset private. Không dùng screenshot thay cho JSON/CSV/log gốc.

### C4. Quy tắc dừng và tiếp tục

- [ ] Nếu OOM: lưu log, giảm batch size và tăng gradient accumulation (B3 training)
  hoặc giảm batch inference; không thay test set hay silently đổi model.
- [ ] Nếu session/quota hết: export checkpoint + manifest; resume bằng run ID mới và
  ghi rõ parent run. Không gộp metrics hai môi trường khác nhau thành một run.
- [ ] Nếu model/token download bị chặn: giữ lỗi và model ID; báo Codex để chọn
  snapshot hợp lệ hoặc cập nhật notebook, không thay model ngầm.

## D. Handoff theo thứ tự

1. Bạn hoàn thành B0 (T4 preparation) và C1 (Kaggle account + GPU smoke).
2. Gửi Codex: reviewer ID, xác nhận no-overlap, output GPU smoke, và notebook URL
   hoặc Kaggle handle (không gửi secret).
3. Codex bắt đầu soạn T3.5 120 ứng viên và tạo nháp input T4.3; bạn review theo
   checklist B1–B3.
4. Khi T3.5/T4 artifact đã accepted, bạn upload data Kaggle C2; Codex chuẩn bị/run
   B1/B2 notebook theo C3.

## E. Bắt đầu trong 30 phút — không cần tự viết JSONL

### T4: việc bạn làm trong vòng đầu tiên

1. Tạo một file text/Google Sheet riêng với 5 câu tiếng Anh cho mỗi nhóm dưới đây.
   Mỗi hàng chỉ cần có `question` và `ý nghĩa bạn muốn đo`; chưa cần ID, JSON,
   offset hay target fingerprint.
2. Gửi 15 câu đó cho Codex. Codex sẽ trả **review pack** gồm candidate relation/
   field (T4.1), entity mention + target (T4.2), hoặc resolution/direction (T4.3).
3. Với từng hàng review pack, bạn chọn một trong ba giá trị:
   `ACCEPT` (đúng), `REVISE: <nội dung đúng>` (sửa nhãn), hoặc `REJECT: <lý do>`
   (câu mơ hồ/ngoài phạm vi).
4. Khi 15 câu đầu pass cách chấm, lặp lại theo batch 10–20 câu đến đủ 50/100/50.
   Codex mới tạo JSONL canonical; bạn review diff cuối trước khi evaluate.

Gợi ý 5 câu khởi đầu cho từng nhóm:

| Nhóm | Câu bạn có thể viết | Bạn cần quyết định |
|---|---|---|
| T4.1 | “Which tokens had the most transfers in June 2026?” | Quan hệ và field nào thật sự cần để trả lời. |
| T4.1 | “How many successful transactions were there each day?” | Cần transaction facts, timestamp và success flag; không thêm field dư. |
| T4.2 | “Show transfers from Binance.” | `Binance` map đúng owner nào; mention bắt đầu/kết thúc ở đâu. |
| T4.2 | “Which addresses sent funds to Uniswap?” | Entity `Uniswap` có phải đúng target dictionary không. |
| T4.3 | “Show transfers from Binance to an exchange.” | `Binance` là direction `from`; concept exchange là concept/coverage gì. |

### Kaggle: thao tác click-by-click cho lần setup đầu

1. Mở [Kaggle Notebooks](https://www.kaggle.com/code), chọn **New Notebook**;
   chọn Python và đặt tên `nl2sql-b1-b2-YYYY-MM-DD-r01`.
2. Mở panel **Settings** ở cạnh phải, chọn **Accelerator → GPU**. Ghi tên GPU hiển
   thị và GPU-hours còn lại. Nếu bị queue, không đổi thiết kế; thử lại sau và ghi
   time/queue vào log.
3. Chạy cell smoke sau, rồi lưu nguyên output vào notebook:

```python
import platform
import subprocess
import sys
import torch

print("python:", sys.version)
print("platform:", platform.platform())
print("torch:", torch.__version__)
print("cuda_available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
print(subprocess.run(["nvidia-smi"], text=True, capture_output=True).stdout)
```

4. Chọn **Save Version → Quick Save** để giữ setup; gửi Codex URL/version. Chưa
   cần upload dataset, model hay token ở bước này.
5. Khi Codex báo input T3.5/Stage D đã chốt, tạo Kaggle Dataset ở chế độ **private**,
   upload đúng bundle do Codex chuẩn bị, rồi Add Data dataset đó vào notebook.
6. Chỉ khi model download bị gated, thêm token đọc-only vào **Add-ons → Secrets**;
   trong code chỉ đọc tên secret, ví dụ `UserSecretsClient().get_secret("HF_TOKEN")`.
   Không dán token vào cell.
7. Trước full run, chọn **Save Version → Save & Run All**. Sau run, download toàn bộ
   report/prediction/config từ `/kaggle/working` và gửi Codex URL + files/log; không
   chỉ gửi screenshot.

### Lệnh Codex sẽ chạy sau khi bạn duyệt artifact

```bash
# T4.1 — cần exactly 50 reviewed rows
UV_CACHE_DIR=.uv-cache uv run python scripts/13_schema_linker.py evaluate

# T4.2 — cần exactly 100 reviewed rows
UV_CACHE_DIR=.uv-cache uv run python scripts/14_entity_linker.py evaluate \
  --ground-truth data/eval/entity_link_groundtruth.jsonl \
  --report reports/entity_linker_evaluation.json

# T4.3 — cần exactly 50 reviewed rows
UV_CACHE_DIR=.uv-cache uv run python scripts/15_class_resolver.py evaluate \
  --ground-truth data/eval/class_resolver_groundtruth.jsonl \
  --report reports/class_resolver_evaluation.json
```

## Nguồn tham khảo Kaggle

- [Kaggle Notebooks documentation](https://www.kaggle.com/docs/notebooks): GPU bật
  tại Settings, notebook versions, `Save & Run All`, giới hạn session và storage.
- [Kaggle Efficient GPU Usage](https://www.kaggle.com/docs/efficient-gpu-usage):
  quota GPU theo tuần, theo dõi usage và dừng session không dùng.
- [Kaggle API documentation](https://www.kaggle.com/docs/api): API token cho CLI/
  automated workflows nếu về sau cần push/pull notebook hoặc dataset.
