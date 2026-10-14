# Audit hard-intent coverage của Stage A v2 — 2026-10-14

Trạng thái: audit hoàn tất; phương án bên dưới **chờ user duyệt**. Chưa thay
template, catalogue, candidate, benchmark hoặc acceptance gate.

## Kết luận

Đề xuất giữ `T_TOKEN_AFTER_NATIVE_FUNDING`, bổ sung điều kiện funding thực sự
thành công và có native value dương. Thay ba intents
`T_EXCHANGE_TO_DEX_FLOW`, `T_CROSS_EXCHANGE_FLOW` và
`T_BRIDGE_OUTFLOW_AFTER_EXCHANGE` bằng ba câu hỏi phân tích đã có probe
non-empty. Giữ 1.000 records, 25 training intents, seed 42, phân bố
350/450/200 và gate 100% non-empty.

Cờ `expect_non_empty=false` chỉ mô tả policy của example, không chứng minh
một intent không có dữ liệu. Audit dựa trên SQL và kết quả thật, thay vì dùng
cờ này làm lý do loại cả bốn intents.

## Phạm vi và nguồn

- Window catalogue: `[2026-05-31, 2026-07-01)`, tối đa 31 ngày. Probe coverage
  gồm toàn tháng 6 và ngày biên 31/5; không tìm window ngoài phạm vi này.
- Snapshot labels live:
  `entity_labels_snapshot_cdc7856df81f`, khớp SHA-256 dictionary local
  `cdc7856df81f2cce61290ef27a8872477f1b77da998a6aa88ca0ed75cc19617e`.
  Có 30 treasury / ExchangeAccount, 3 operational / DEXProtocol và
  5 operational / BridgeProtocol. Không thay vai trò token thành operational.
- Template library raw SHA-256:
  `85c60de3f5d8d62855c2770fabdb99f09e22fb62c9c104f90d573829763dedda`.
  Catalogue raw SHA-256:
  `db8393aa7258d1331387eff9825e22ca729daf93234419f00d7dd538196cb3dd`.
- Candidate được audit:
  `563025953b52b9465dc8fe2d879cebffa8a9e1ba86ea138b2de686f01c5235ee`.
  Bằng chứng cũ của Stage A v1 và các diagnostic thất bại được giữ nguyên.
- Không dùng câu hỏi/gold SQL của benchmark để chọn replacement. Các candidates
  xuất phát từ analytical relations, giới hạn labels và các phép đo mô tả.

Evidence machine-readable:

- [Label audit](../evidence/stage-a-v2-hard-intent-label-audit.json):
  SHA-256 `553e587bd41eac2a51e0c6b3c86e44f1ffd9b83ea29adbb436429f46e2a99a24`.
- [Coverage và candidate probes](../evidence/stage-a-v2-hard-intent-coverage-audit.json):
  SHA-256 `8b9114a6a7cb756eb180ae2633673a8ab0ce6f98fc92ee2040766f2fdc9d4934`.
  File lưu exact SQL, query SHA, job IDs, rows, byte metrics và cache state.

## Kết quả từng intent

| Intent hiện tại | Bằng chứng | Kết luận |
|---|---|---|
| `T_EXCHANGE_TO_DEX_FLOW` | Count đúng các predicates treasury/exchange → operational/DEX bằng 0 trong cả 31 ngày; diagnostic mới cũng trả rỗng | Không có window cứu được trong phạm vi hiện tại; đề xuất thay |
| `T_CROSS_EXCHANGE_FLOW` | Count treasury → treasury, khác owner, bằng 0 trong cả 31 ngày | Đề xuất thay; không nới role hoặc đổi thành token flow dưới cùng tên |
| `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE` | Count của chính bước deposit treasury → operational/bridge bằng 0 trong cả 31 ngày | CTE deposits rỗng khiến temporal INNER JOIN chắc chắn rỗng; không cần quét token toàn tháng |
| `T_TOKEN_AFTER_NATIVE_FUNDING` | V1 có live witness `syn-000800`, SQL khớp library hiện tại; probe mới có row ngay cả khi thêm `value_wei > 0`, receipt của funding bằng 1 | Giữ intent, làm chặt nghĩa funding và sửa CQ mapping |

Đây là absence trong **accepted labels + window hiện tại**. Không suy ra các
quan hệ này không tồn tại trên Ethereum, hoặc schema không hỗ trợ chúng.
Catalogue `supported` cũng không đồng nghĩa dataset có non-empty witness.

Native coverage job:
`446543da-92ad-461a-8459-174fee21f846`; boundary-day job:
`92b5fc25-43a9-469f-bf98-e1d8d898c01c`. Vì cả hai predicates-window probes
trả zero cho ba patterns trên mọi ngày, chọn subwindow hoặc tăng
`duration_minutes` không tạo được missing deposit/direct-flow rows.

### Giữ native funding → token transfer

Positive-funding probe job `6b75de22-a455-48d1-a19f-4f8528c84473` trả:

- Funding hash:
  `0x71342b32a8d423f7bc2962bbb064d447fa222394f3acbead14781f961f8458f8`.
- Funded address: `0x2f9a818f6034d91e0cdc89c0088b481d8d9ba742`.
- Native value: `4587720000000` wei, dương.
- Transfer hash:
  `0xf10b2ae500159f0b926cb8f0c003083dd51655b4150393b016ba57d0c6485b30`;
  log index 426; token JASMY.
- Receipt lookup job `732cbc89-e35a-41a9-ad89-193e5ce72dad` xác nhận cùng
  funding hash/address/value, `receipt_status=1`.

Đề xuất thêm `value_wei > 0 AND receipt_status = 1` vào funding CTE. Giữ
window `[2026-06-15, 2026-06-16)`, duration 60 phút và sáu output columns
cũ; column funding value thêm trong probe chỉ phục vụ audit.

Giữ nghĩa thời gian đúng SQL: token timestamp không trước funding timestamp
và nhỏ hơn funding timestamp + 60 phút. Không claim causality, ownership của
funded address hoặc thứ tự transaction trong cùng một block.
Witness feasibility này không thay thế fresh verification của SQL production
đã sửa.

## Ba replacements đề xuất

Exact SQL prototypes nằm trong evidence JSON, với tên probe bên dưới. Khi
implement, chỉ parameterize date bounds và `LIMIT {n}`; không thêm comment,
joins hoặc predicates vô nghĩa để tạo diversity/difficulty.

| Retire | Replacement | Records | Khác biệt về câu hỏi |
|---|---|---:|---|
| `T_EXCHANGE_TO_DEX_FLOW` | `T_OWNER_NET_NATIVE_FLOW` | 34 | So sánh native value vào/ra và net flow trên các treasury addresses có labels theo owner |
| `T_CROSS_EXCHANGE_FLOW` | `T_TREASURY_NATIVE_COUNTERPARTY_CONCENTRATION` | 33 | Đo mức tập trung transaction counts vào recipient addresses, thay vì hỏi direct flow giữa hai exchange owners |
| `T_BRIDGE_OUTFLOW_AFTER_EXCHANGE` | `T_TREASURY_TOKEN_COUNTERPARTY_DIVERSITY` | 33 | Xếp hạng treasury owners theo số recipient addresses và token contracts khác nhau |

1. **Net native flow.** Probe `owner_net_native_flow`, job
   `919fc676-2b1a-4425-acf9-7da37103c952`, trả Gemini / Bitfinex / Gate.io.
   Hai hướng successful positive-value transactions được UNION ALL, aggregate
   theo owner, tính incoming − outgoing bằng NUMERIC wei rồi rank theo trị
   tuyệt đối. Đây không phải balance change: không bao gồm gas, internal
   transfers hoặc các addresses của owner chưa được label.
   Category đề xuất: `comparison`.
2. **Native recipient concentration.** Probe
   `treasury_native_counterparty_concentration`, job
   `752c9133-e4a6-407a-a7bc-2467291ba1d5`, trả Deribit / Bitfinex / Bitrue.
   Pair counts → recipient shares bằng window SUM → sum of squared shares →
   owner ranking. Chỉ dùng successful positive-value transactions, owner có
   ít nhất 10 transactions. HHI nằm trong [0,1]; không suy diễn AML hoặc actor
   identity từ concentration. Khác `T_REPEATED_PAIR_FLOW`: đơn vị kết quả là
   owner-level distribution, không phải một cặp address.
   Category đề xuất: `transaction_aggregation`.
3. **Token recipient/token diversity.** Probe
   `treasury_token_counterparty_diversity`, job
   `dcf4f0ae-ebd8-4633-bd13-e9ec28e0dfeb`, trả Gate.io / Indodax / Poloniex.
   Gate.io có 4.085 transfer events, 441 token contracts và 1.363 recipients.
   Aggregate distinct counts và window ranking; không cộng lượng của các token
   khác nhau hoặc dùng symbol để đồng nhất contract.
   Khác `T_TOKEN_VOLUME_BY_SYMBOL` và `T_TX_GROUPED_BY_OWNER`: đo diversity
   theo owner, không đo token volume hoặc chỉ tổng transaction count.
   Category đề xuất: `token_specific`.

Đề xuất label hard theo compositional SQL rubric: bidirectional normalization,
multi-stage aggregation/window distribution hoặc multi-metric distinct ranking.
Đây chưa phải empirical difficulty đã đo bằng B1/B2/B3; cần duyệt rubric, không
gán hard chỉ để đủ quota.

Mỗi replacement chỉ biến thiên `n=1..34` hoặc `n=1..33` trong cùng window
ngày 15/6. Dự kiến mỗi intent vẫn là một limit-monotonic group, giữ topology
206 logical / 126 physical. Số đếm phải được derive và test từ actual
regeneration; không chỉnh manifest để ép khớp.

## CQ contract và tác động cần duyệt

Các câu hỏi mới không còn là exchange→DEX, exchange→lending hoặc bridge deposit
flow. Không được giữ CQ13/CQ22/CQ26 trên replacements để claim coverage cũ.
Một mismatch hiện có cũng cần sửa: ontology CQ29 hỏi token received **rồi**
native sent to exchange; `T_TOKEN_AFTER_NATIVE_FUNDING` hỏi chiều và thứ tự
khác. CQ annotation này không thể giữ chỉ vì hai query dùng cùng relations.

Phương án metadata rõ nghĩa đề xuất:

- CQ31: successful positive native funding từ accepted treasury, theo sau bởi
  token transfer từ funded address trong khoảng timestamp đã định nghĩa.
- CQ32: incoming/outgoing/net native value trên accepted treasury addresses theo
  owner.
- CQ33: concentration của native recipient transaction-count distribution theo
  accepted treasury owner.
- CQ34: distinct token-contract/recipient diversity của treasury token transfers
  theo owner.

Đây là **proposed GoogleSQL CQ extensions**, chưa có trong catalogue hiện hành.
Catalogue và validator hiện pin đúng CQ01–CQ30. Nếu duyệt, cần một revision
explicit cho CQ31–CQ34, pin/hash revision mới và giữ catalogue snapshots dùng
bởi historical evidence. Không đổi nghĩa các IDs cũ hoặc âm thầm bỏ exact-ID
guard. Bản ontology SPARQL lịch sử không tự động trở thành catalogue active mới.

Các bước implementation sau approval:

1. Viết/chốt spec và plan cho đúng three replacements + funding correction +
   CQ revision; kiểm tra không trùng existing questions.
2. Cập nhật template library/validator, catalogue version/CQ definitions và
   tests; giữ record contract, v1 bytes và các failed reports.
3. Giữ 100 replacement records và 33 funding records ở các allocation positions
   hiện tại; regenerate candidate và tính hashes từ bytes thật.
4. Thay đúng 24 bilingual patterns của ba retired intents; rà tám patterns của
   funding intent cho đúng positive/successful/temporal semantics. Catalog vẫn
   25 intents × 2 languages × 4 styles. Không publish canonical 8.000 records.
5. Chạy local verification và bounded diagnostic cho candidate mới. Probe
   audit chỉ chứng minh feasibility, không authorize accepted publication.
6. Sau diagnostic thành công, fresh preflight và user approval riêng cho
   `--live`.

B0–B3 và hướng so sánh zero-shot/five-shot/fine-tuned giữ nguyên. Phần thay đổi
khoa học là population các training intents và CQ coverage được công bố.
Benchmark wording/gold SQL không được sửa để khớp replacements; nếu catalogue
revision làm đổi provenance hash, xử lý bằng versioned inputs và compatibility
validation, không rewrite historical measurements.

## Cost, capture và giới hạn evidence

Project được kiểm tra billing disabled/unlinked trước executions; query cache,
SDK request/job/result retries đều tắt. Label count query có cap 64 MiB.
Bảy coverage/candidate executions có individual caps 1/2/16/20 GiB và aggregate
preflight cap 48 GiB:

- Estimated bytes: 38.395.363.189 (35,758468498 GiB).
- Processed: 37.670.503.883; billed: 37.672.189.952; cache hits: 0.
- Bao gồm label query: processed 37.670.956.007, billed 37.682.675.712 bytes.

Helper đầu tiên đọc schema từ QueryJob thay vì result iterator và lỗi sau
native execution; kết quả được recover từ cùng completed job, không execute
lại. Một prototype concentration bị reject ở dry-run vì aggregate alias trong
HAVING; sửa alias pair-level rồi mới execute. SQL reject/job ID được giữ trong
evidence. Output capture của một helper bị truncate; metadata/results của bốn
completed jobs được đọc lại, hai missing per-query estimates được confirm bằng
dry-run sau execution và đánh dấu riêng. Tổng estimates confirmation khớp
original preflight total. Không trình bày các confirmation đó như initial
dry-run observations.

Đây là development coverage audit, không phải benchmark/model evaluation hay
accepted Stage A report. Các probes không xác nhận mọi possible date/threshold,
không thay complete 206-witness diagnostic và không mở bilingual acceptance.

Nguồn local liên quan:

- `docs/tasks/phase-3-dataset/01-query-templates.md`.
- `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`.
- `docs/superpowers/specs/2026-08-09-t3-2-witness-grounded-stage-a-design.md`.
- `data/dataset/raw/synthetic-stage-a.jsonl` (historical exact funding witness).
- `src/nl2sparql/kg/ontology/competency-questions.md` và current SQL catalogue.
