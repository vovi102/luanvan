# 05 — Decision Log

> **Mục đích:** Ghi lại các quyết định kỹ thuật đáng nhớ. Sẽ được trích dẫn trong chương Methodology của luận văn.
> **Quy tắc:** Mỗi quyết định 1 entry. Cập nhật KHI ra quyết định, không phải sau cùng.
> **Format:** Reverse chronological (entry mới ở trên).

---

## Template entry

```markdown
### YYYY-MM-DD — <tóm tắt 1 dòng>

- **Context:** Tại sao cần quyết định này (vấn đề gặp phải, trade-off).
- **Options considered:** Liệt kê các lựa chọn đã cân nhắc.
- **Decision:** Chọn cái gì.
- **Rationale:** Lý do chọn (1-3 câu).
- **Consequences:** Tác động sau này (cái gì giờ dễ hơn, cái gì khó hơn).
- **Revisit:** Khi nào nên xem lại quyết định này (e.g. "sau Phase 5", "không cần").
- **Linked:** Task/file liên quan.
```

---

## Entries

### 2026-10-14 — Tách pair provenance và diagnostic evidence khỏi acceptance

- **Context:** Stage A v2 trước đây ghép độc lập hai address nên một witness
  `T_TX_BETWEEN_ACCOUNTS` rỗng. Pool mới chứng minh 40 quan hệ account-pair,
  nhưng diagnostic tiếp theo phát hiện một address giao dịch không đồng nghĩa là
  block beneficiary: `T_BLOCKS_BY_VALIDATOR` vẫn trả rỗng.
- **Options considered:** Coi pair evidence là đủ cho mọi account-bound intent;
  hạ non-empty gate; retry cùng candidate; hoặc giữ role/relationship provenance
  riêng và công bố diagnostic failure mà không promote acceptance.
- **Decision:** Generator consume nguyên tử 40 pair + date window; verifier batch
  thành bốn query 10-pair nhưng giữ 206 logical witnesses / 126 physical queries.
  Diagnostic chỉ được chạy khi billing disabled/unlinked và luôn có
  `acceptance_authorized=false`; failure report được giữ nguyên, không retry và
  không gọi accepted writer.
- **Rationale:** Một endpoint có transaction relationship không chứng minh nó có
  mọi semantic role khác. Tách evidence theo quan hệ/role ngăn provenance hợp lệ
  của intent này bị tái sử dụng sai cho intent khác, đồng thời giữ failure làm
  kết quả khoa học thay vì sửa threshold hậu nghiệm.
- **Consequences:** Pair-backed candidate hash là
  `bc82ef19884081f7017f138e6bfb6cf88851dcc4b209c990694828526edb5b7f`.
  Diagnostic `04c09aff49422274b1ad1b3a577f98a0c20e250d439a4675e8b684c57e30fb87`
  dừng tại `syn-v2-000637` sau 13 executions / 66 logical outcomes; ba accepted
  artifacts vẫn absent. Promotion cần beneficiary-specific evidence và audit
  các intent account-bound còn lại.
- **Revisit:** Sau khi có relationship-specific pools mới, candidate được
  regenerate và fresh preflight được user duyệt; không dùng report diagnostic
  hiện tại để authorize `--live`.
- **Linked:** `docs/evidence/stage-a-v2-account-pair-diagnostic.json`,
  `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`,
  `src/nl2sparql/dataset/stage_a/diagnostics.py`.

### 2026-10-13 — Thu gọn phạm vi mô hình còn B0–B3 small-LLM-only

- **Context:** Baseline mô hình bên ngoài làm tăng dependency, chi phí, privacy
  risk và khối lượng đánh giá nhưng không còn phục vụ hướng nghiên cứu đã chọn.
- **Options considered:** Giữ như optional/historical surface; chỉ bỏ khỏi
  critical path; hoặc xóa khỏi cây hiện tại và chốt ma trận B0–B3.
- **Decision:** Chỉ giữ B0 rule-based, B1 small LLM zero-shot, B2 small LLM
  five-shot và B3 small LLM fine-tuned. Xóa implementation, dependency, task,
  evaluator adapter và demo path dùng model bên ngoài.
- **Rationale:** Ma trận này tập trung trực tiếp vào tác động của prompting,
  retrieval, fine-tuning và linking trong cùng resource class, đồng thời giữ
  pipeline local/Kaggle tái lập được.
- **Consequences:** RQ/contribution đổi sang zero-shot vs five-shot vs fine-tuned;
  T5.5 quyết định phạm vi B3 từ genuine B1/B2 evidence; public demo không được
  thay model nghiên cứu bằng dịch vụ inference khác.
- **Revisit:** Không cần, trừ khi scope luận văn được GVHD phê duyệt lại.
- **Linked:** `docs/planning/prioritized-backlog-2026-09-21.md`,
  `docs/memory/00-PROJECT_OVERVIEW.md`, `docs/tasks/phase-5-baselines/05-pivot-decision.md`.

### 2026-10-10 — Stage A v2 tách candidate 25 intent khỏi live acceptance

- **Context:** Stage A v1 có genuine live evidence nhưng chỉ phủ 16/25 intent;
  T3.3 cần đủ 25 intent, trong khi chín intent mới chưa có evidence-backed block
  numbers/transaction hashes hoặc BigQuery run được cấp quyền.
- **Options considered:** Sửa/ghi đè v1; coi syntax-only values là live evidence;
  hạ gate của corpus song ngữ; hoặc tạo v2 candidate riêng và buộc promotion qua
  manifest/evidence gate.
- **Decision:** Giữ v1 immutable. V2 offline tạo deterministic 1.000 records trên
  25 intent với lifecycle `candidate`, không acceptance-eligible. Live promotion
  yêu cầu ít nhất 45 unique provenance-bearing block numbers và transaction
  hashes, genuine verifier results cho 1.000/1.000 records và zero cache hits.
  Audit/build/validation của corpus song ngữ hash-bind cả source lẫn accepted
  manifest; validate-only vẫn được phép kiểm tra candidate.
- **Rationale:** Tách ba trạng thái candidate → accepted → canonical cho phép
  kiểm thử coverage/reproducibility offline mà không biến dữ liệu cú pháp thành
  bằng chứng thực nghiệm.
- **Consequences:** Candidate data SHA-256 là
  `4746f68642913e0c40a0d19817cf0e4bf556f46d3ba1777a611f903e062e6561`;
  offline expansion đạt 8.000 rows. Không có credential/provider call, chi phí,
  accepted v2, audit decisions hay canonical bilingual artifact trong lần này.
  Catalog sửa một VI abbreviated pattern của `T_TX_BY_HASH` để loại collision
  normalized EN/VI thay vì hạ uniqueness gate. Vietnamese benchmark review vẫn
  pending và wording/review decisions không bị sửa.
- **Revisit:** Khi có evidence pools, BigQuery credential/quota và explicit cost
  authority; chạy `scripts/09_generate_stage_a_v2.py --live`, rồi mới audit và
  build canonical corpus.
- **Linked:** `docs/superpowers/specs/2026-10-09-stage-a-v2-25-intents-design.md`,
  `scripts/09_generate_stage_a_v2.py`, `src/nl2sparql/dataset/stage_a_v2.py`,
  `src/nl2sparql/dataset/bilingual/assembly.py`.

### 2026-10-07 — T3.3 dùng deterministic bilingual catalog

- **Context:** External generation không tạo được accepted Stage B/C trong ngân
  sách bằng 0. Training corpus cần provenance kiểm chứng được và phải giữ
  benchmark wording ngoài producer.
- **Options considered:** Tiếp tục chờ external generation hoặc thay bằng catalog
  hữu hạn do agent soạn và renderer deterministic offline.
- **Decision:** Dùng đúng 200 patterns (25 intent × English/Vietnamese × bốn
  styles), render tám record cho mỗi Stage A family, provider/model null, API
  calls `0`, recorded cost `$0.00`. Enforce hash-only held-out exclusions,
  family-aware splits, diversity, audit 100/ngôn ngữ và atomic publication.
- **Rationale:** Luồng này byte-reproducible, không có credential/quota/privacy
  dependency và cho phép kiểm tra trực tiếp mỗi pattern/provenance claim.
- **Consequences:** Stage B/C và Stage D bị loại khỏi active scope. Catalog và
  benchmark đều có shared agent authorship nên không claim
  independent authorship. Pinned Stage A chỉ phủ 16/25 intent; canonical artifact
  phải fail closed cho đến khi có accepted 25-intent source hoặc gate được duyệt
  lại. Vietnamese 100-candidate benchmark vẫn chờ user review.
- **Revisit:** Chỉ khi accepted source/gate thay đổi bằng quyết định governance;
  không tự tạo chín intent còn thiếu.
- **Linked:** `docs/superpowers/specs/2026-10-07-deterministic-bilingual-training-design.md`,
  `src/nl2sparql/dataset/bilingual/`, `scripts/20_build_bilingual_training.py`,
  `scripts/21_validate_bilingual_training.py`.

### 2026-10-03 — Giữ T5.1 B0 genuine run như negative result, không tune trên T3.5

- **Context:** B0 được thiết kế trước khi T3.5 final tồn tại. Genuine run trên
  snapshot 100 câu cho `0/100` output; coverage, structural và execution accuracy
  đều `0.0`, inference p95 `259.65 ms`. 100 gold SQL vẫn execute thành công.
- **Options considered:** Hạ threshold; bổ sung parser/template sau khi xem test
  set; thay T3.5 bằng câu gần seed; hoặc giữ nguyên result và chuyển sang baseline
  học máy.
- **Decision:** Giữ B0 và T3.5 immutable cho phép đo này, công bố negative result,
  không tối ưu template/parser/linker bằng câu hỏi T3.5.
- **Rationale:** Sửa B0 dựa trên test set sẽ gây leakage và biến lower-bound thành
  hệ thống đã tune trên benchmark. Causal attribution cho `no_output` chưa có
  diagnostic artifact hash-bound, nên quyết định chỉ dựa trên nguyên tắc giữ phép
  đo genuine immutable, không tuyên bố một parser patch cụ thể là root cause.
- **Consequences:** T5.1 genuine evaluation hoàn tất nhưng acceptance thresholds
  không đạt. T5.4 report ghi `no_output=100%`; B1/B2/B3 phải chứng minh khả
  năng generalize thay vì dùng B0 làm target cần cứu. BigQuery run dùng
  `559,594,602,496` billed bytes, estimated cost `$3.180927`.
- **Revisit:** Chỉ xây rule-based v2 trên một development set tách biệt nếu luận
  văn cần thí nghiệm mới; không dùng T3.5 để chọn rule hoặc threshold.
- **Linked:** `docs/tasks/phase-5-baselines/01-b0-rule-based.md`,
  `data/eval/canonical/b0-run-01.json`, `reports/evaluation/b0-run-01.json`.

### 2026-09-28 — T3.5 active dùng agent-authored, single-human-reviewed provenance

- **Context:** Thiết kế tháng 8 yêu cầu ba pool độc lập, nhiều cộng tác viên và
  kappa, nhưng không có đủ human authors/reviewers để tạo evidence đó. Tiếp tục
  gọi dữ liệu do Codex soạn là three-pool sẽ thổi phồng provenance và chặn toàn
  bộ baseline/fine-tuning downstream.
- **Options considered:** Chờ vô thời hạn đủ cộng tác viên; tự điền ba vai giả;
  bỏ benchmark; hoặc tạo profile mới ghi đúng Codex là author và user là một
  human reviewer, giữ three-pool như đường lịch sử.
- **Decision:** Chọn profile exact `agent_authored_human_reviewed_v1`. Codex tạo
  120 NL–GoogleSQL candidates; user review tất cả và chọn 100 theo quota 30/50/20.
  Artifact bắt buộc công bố các limitation: không independent authorship,
  independent review, inter-rater agreement hay kappa claim.
- **Rationale:** Profile mới tạo được benchmark có audit trail trung thực và
  vẫn giữ human quality gate, thay vì giả evidence hoặc đánh đồng với thiết kế
  cộng tác viên không thực hiện được.
- **Consequences:** Draft đã `draft_ready` tại
  `data/review_drafts/t3_5_candidate_set_2026-09-27/`; review/selection hiện chỉ
  có header. Cấm dùng candidate/final questions và variants cho training,
  fine-tuning, few-shot retrieval, prompt/linker/hyperparameter tuning. Genuine
  B0–B3 accuracy chỉ mở sau user review, explicit live BigQuery verification và
  immutable finalization.
- **Revisit:** Chỉ nâng provenance nếu sau này có authors/reviewers độc lập thật;
  không backfill claim three-pool cho snapshot hiện tại.
- **Linked:** `docs/tasks/phase-3-dataset/05-test-set-3pool.md`,
  `docs/superpowers/specs/2026-09-27-t3-5-agent-reviewed-benchmark-design.md`,
  `data/review_drafts/t3_5_candidate_set_2026-09-27/`.

### 2026-09-01 — T5.2 tách local baseline logic khỏi Kaggle Llama inference

- **Context:** T5.2 legacy prompt SPARQL bằng ontology và giả định Llama 3 8B
  chạy trên Kaggle T4, trong khi Pivot #1 yêu cầu GoogleSQL và workstation chỉ có
  GTX 1650 4 GiB. Chạy model nhỏ khác hoặc fake completion local sẽ làm sai
  baseline khoa học.
- **Options considered:** Giữ SPARQL task; tải/chạy hoặc train Llama 8B local;
  dùng model nhỏ thay thế; viết notebook Kaggle monolithic; hoặc tách deterministic
  baseline module khỏi generation adapter.
- **Decision:** B1/B2 dùng cùng catalog-only GoogleSQL prompt/config, B2 thêm đúng
  năm nearest training examples. Generation và encoder là injected internal seams;
  real Transformers/SentenceTransformers load lazy sau explicit opt-in. Local
  adapters kiểm chứng behavior nhưng mang synthetic marker và không thể mở
  readiness. Production evaluation reuse finalized T3.5 evidence contract.
- **Rationale:** Interface nhỏ giữ prompt/retrieval/extraction/artifact behavior
  test được local mà không giả lập kết quả nghiên cứu. Whole-output SQL validation
  và complete fingerprints ngăn prose/unsafe output hoặc stale cache trở thành
  prediction hợp lệ.
- **Consequences:** Code, CLI, cache và evaluator hoàn thành local mà không tải hay
  train Llama. Scientific acceptance vẫn cần finalized T3.5/training artifacts,
  pinned model snapshots và genuine Kaggle T4 latency/OOM evidence.
- **Revisit:** Khi external artifacts có mặt và trước khi chạy B1/B2 Kaggle; pin
  exact Hugging Face revisions rồi giữ nguyên prompt/config cho cả hai baseline.
- **Linked:** `docs/tasks/phase-5-baselines/02-b1-b2-small-llm.md`,
  `src/nl2sparql/models/b12/`, `scripts/17_small_llm_baselines.py`.

### 2026-09-01 — T5.1 B0 chọn validated GoogleSQL template và fail closed

- **Context:** B0 legacy match regex rồi fill SPARQL/free-form entity text, trái
  Pivot #1 và các typed catalog/linker contracts đã hoàn thành ở T3.1/T4.1–T4.3.
- **Options considered:** Giữ regex/Jaccard và chọn first; generate SQL trực tiếp
  từ resolver fields; gọi LLM cho fallback; hoặc chọn template deterministic,
  typed rendering và abstain khi tie/evidence không đủ.
- **Decision:** `BaselineB0.predict()` trả một managed read-only GoogleSQL hoặc
  `None`. Seed match đứng trước token-F1 structural fallback; T4.1 chỉ phá tie có
  unique schema overlap, T4.2/T4.3 chỉ cấp scalar instance/concept slot khi plan
  resolved và coverage supported. T3.1 renderer và T3.5 SQL safety là authority
  cuối. Evaluation tách structural khỏi execution accuracy.
- **Rationale:** Interface nhỏ giữ matching/rendering phức tạp ở một deep module,
  bảo toàn provenance và tránh tăng coverage bằng silent guesses. Prediction vẫn
  chạy local, deterministic và không gắn network/billing vào inference.
- **Consequences:** Synthetic tests kiểm chứng metric math nhưng không thể tạo
  readiness; finalized T3.5/live result evidence vẫn là gate ngoài local.
  Publication ghi predictions trước, report cuối và rollback khi report lỗi.
- **Revisit:** Sau khi finalized T3.5 benchmark có mặt; xem lại structural
  threshold/ambiguity margin bằng error analysis nhưng không tune trên test set.
- **Linked:** `docs/tasks/phase-5-baselines/01-b0-rule-based.md`,
  `src/nl2sparql/models/b0/`, `scripts/16_b0_rule_baseline.py`.

### 2026-08-31 — T4.3 resolve entity evidence thành typed GoogleSQL constraint plan

- **Context:** T4.3 legacy sinh SPARQL `VALUES`/class triple, trong khi T4.2 Plan
  B chỉ trả recognition evidence và analytical catalog mới sở hữu relation,
  field, join, role và coverage semantics.
- **Options considered:** Giữ SPARQL fragments; render GoogleSQL predicate ngay
  trong resolver; dùng LLM để classify từng mention; hoặc trả deterministic
  typed constraint plan.
- **Decision:** `ClassResolver.resolve()` trả immutable `ResolutionPlan` với
  resolution kind, direction, catalog field candidates, typed operator/values,
  required label relation/join/role, coverage status và full fingerprints. SQL
  rendering nằm downstream. Ambiguity fail closed trừ một concept alternative có
  explicit class trigger; raw T4.2 address target vẫn được self-authenticate.
- **Rationale:** Một interface nhỏ che linguistic, corpus và catalog policy giữ
  module sâu, test offline và ngăn free-form SQL vượt qua catalog validation.
- **Consequences:** T5.1/T6.1 nhận plan machine-readable thay vì fragment. Missing
  mixer/NFT coverage và unspecified/conflicting direction hiện rõ, không bị biến
  thành query success giả. Exactly-50 evaluator có provenance nhưng scientific
  >=0.90 vẫn pending independent artifact.
- **Revisit:** Sau khi T5.1 renderer dùng interface và 50-row evaluation được
  review độc lập; khi đó kiểm tra candidate-field granularity và ambiguity rules.
- **Linked:** `docs/tasks/phase-4-linking/03-class-resolver.md`,
  `src/nl2sparql/linking/resolver/`, `scripts/15_class_resolver.py`.

### 2026-08-29 — T4.2 tách recognition entity khỏi GoogleSQL resolution và publish index fail-closed

- **Context:** T4.2 legacy từng trộn nhận diện entity với SPARQL triple/filter,
  pickle cache và fallback `unknown`. Sau Pivot #1, analytical catalog
  GoogleSQL là runtime canonical; quyết định predicate, join và SQL filter phụ
  thuộc context schema nên không thuộc entity recognition.
- **Options considered:** Resolve trực tiếp thành SQL/VALUES trong T4.2; quét
  dictionary ở mọi query không có artifact; persist pickle/trie; hoặc tách
  linker typed nhận diện evidence và cache chỉ embedding matrix có provenance.
- **Decision:** `EntityLinker.link()` chỉ trả owner/concept/address evidence,
  original spans, ambiguity alternatives và target fingerprints. T4.3 sở hữu
  GoogleSQL predicate/join/filter resolution. Exact/fuzzy indexes được rebuild
  deterministic từ dictionary; chỉ matrix MiniLM float32 được cache trong NPZ
  content-addressed, `allow_pickle=False`, process lock và manifest-last. Strict
  load bind dictionary/model/document hashes, matrix digest/shape/normalization,
  fuzzy/embedding thresholds và ambiguity margin; reject path/alias tampering
  hoặc effective-policy mismatch, không implicit rebuild/download.
- **Rationale:** Seam này giữ module sâu, tránh mặc định hóa SQL semantics trước
  schema resolution, và cho deterministic unit tests bằng fake encoder. Cache
  immutable/auditable giúp real production retrieval fail closed khi dictionary,
  model hoặc artifact stale/tampered thay vì tạo result khó truy nguyên.
- **Consequences:** Local build ngày 2026-08-29 tạo 5,107 targets, matrix 384-d,
  manifest file SHA-256
  `0575e2222b0d1aebff0bee80cdd338c6dc8a80be38f6094f19cf9bbc05979a31` và
  matrix SHA-256
  `ee33c9fededf9be1091bca69e64c7f4075ba1d0f9948652a412c39f14c4dfa53`.
  Recognition output không chứa SQL; consumer phải resolve qua T4.3. Model
  snapshot remains outside the repository, while only validated production index
  artifacts are versioned.
- **Revisit:** Khi có đúng 100 rows independently reviewed, chạy real evaluation
  để kiểm tra named-entity Top-1 >=0.85 và warm p95 <200 ms; khi T4.3 ổn định,
  review seam có cần thêm typed resolution request hay không.
- **Linked:** `docs/tasks/phase-4-linking/02-entity-linker.md`,
  `src/nl2sparql/linking/entity/`, `scripts/14_entity_linker.py`.

### 2026-08-15 — T4.1 rank GoogleSQL relation/field bằng hybrid linker fail-closed

- **Context:** Task T4.1 cũ rank ontology property/class để inject SPARQL, trái với
  Pivot #1 và analytical catalog GoogleSQL đang active. Đồng thời chưa có file 50
  câu manual ground truth được review độc lập, nên template fixtures không thể
  đóng acceptance khoa học.
- **Options considered:** Giữ linker SPARQL legacy; embedding-only trên tên field;
  fine-tune bi-encoder trước evaluation; hoặc hybrid lexical + MiniLM trên catalog
  documents có cache fingerprinted.
- **Decision:** Rank riêng 6 analytical relations và 62 `relation.field` elements
  bằng `0.65 * semantic + 0.35 * lexical`, stable tie-break, typed immutable
  results và explicit `sentence-transformers/all-MiniLM-L6-v2` encoder. Cache dùng
  manifest JSON + immutable content-addressed NPZ `allow_pickle=False`, bind
  catalog/model/exact current document hashes/weights/order/digest, switch
  manifest cuối, giữ prior generations và không implicit rebuild/fake vector.
- **Rationale:** Lexical evidence giữ directional blockchain roles; MiniLM xử lý
  paraphrase. Separate pools tránh so score relation với field, còn explicit
  cache lifecycle làm CI deterministic với fake encoder nhưng production evidence
  vẫn fail closed khi thiếu model/network.
- **Consequences:** Real model rebuild schema v2 ngày 2026-08-15 đã tạo index
  384-d cho 6 relations/62 fields; strict second load mất 2.686 ms. Manifest file
  SHA-256 là
  `7105c53158c8cd553ace796d5c84d7cdb93d2618a60fb5ca08291943de402c3b`, NPZ
  SHA-256 là
  `17b123ba8a2baf42d2c5235e7a63019d29b682dea7366affecb63b6cba987324`.
  và manifest body SHA-256 là
  `962f74fd498bc5eb8a45a0111aefa479135a3c153eb3b125c05ad653471cfda9`.
  Model snapshot nằm trong Hugging Face cache ngoài repo. Evaluator nay emit
  fixed field Recall@5/@10 và full-pool field MRR. File
  `data/eval/schema_link_groundtruth.jsonl` chưa tồn tại, nên Recall@10, warm
  p50/p95 và hash-bound evaluation report vẫn pending; template fixtures không
  được gọi là independent annotation.
- **Revisit:** Khi có đúng 50 rows được independently reviewed; chạy real
  `evaluate`, kiểm tra field Recall@10 ≥0.80 và warm p50 <100 ms, rồi ghi report
  hashes/metrics vào task và decision log.
- **Linked:** `docs/tasks/phase-4-linking/01-schema-linker.md`,
  `docs/superpowers/specs/2026-08-15-t4-1-google-sql-schema-linker-design.md`,
  `src/nl2sparql/linking/schema/`, `scripts/13_schema_linker.py`.

### 2026-08-15 — T3.5 migrate three-pool benchmark sang GoogleSQL và fail closed khi thiếu evidence

- **Context:** T3.5 cũ yêu cầu NL–SPARQL, Fuseki và chỉ mô tả một Pool C reviewer,
  trái với Plan B NL2SQL và không đủ để tính Cohen's kappa trên subset double-review.
- **Options considered:** Giữ SPARQL/Fuseki; chỉ commit CSV/brief tĩnh; dựng survey
  platform; hoặc tạo module/CLI GoogleSQL có validator offline và BigQuery adapter.
- **Decision:** Dùng module sâu `src/nl2sparql/dataset/testset/` với contracts,
  bundle/review/kappa/quota validation, SQL safety, hash-bound live evidence và
  explicit lead selection. CLI có scaffold/validate/verify-live/finalize; chỉ
  `verify-live` được tạo evidence và finalizer không tự chọn record.
- **Rationale:** Một interface tập trung giữ schema/review/cost rules nhất quán,
  test được không cần credentials, và không biến dữ liệu giả thành benchmark. Hai
  reviewer trên 30 IDs là điều kiện cần để đo kappa thay vì percent agreement.
- **Consequences:** Sau final review remediation, offline implementation có 68
  focused tests và 558 tests toàn repository. SQLGlot BigQuery AST kiểm tra mọi
  direct relation/table function cả offline/live; role identities tách biệt,
  kappa degenerate/changing-pair bị chặn; normalized selection annotations được
  kiểm tra với catalog và propagate. Result preview bị giới hạn, hai vòng
  preflight đều chặn aggregate trước execution, ordered expected columns được
  kiểm tra live, report có full-SHA/dirty provenance/hash, và finalizer kiểm tra
  selection/evidence/policy fail closed. Raw collaborator files, consent,
  BigQuery execution, 100 final rows và kappa thật vẫn pending. Thiếu credential/
  submission trả structured `blocked` và không publish artifact.
- **Revisit:** Khi có đủ Pool A/B/C và BigQuery credentials; sau đó ghi evidence
  hashes, reject rate, kappa và final selection vào task.
- **Linked:** `docs/tasks/phase-3-dataset/05-test-set-3pool.md`,
  `docs/superpowers/specs/2026-08-15-t3-5-google-sql-test-set-design.md`,
  `src/nl2sparql/dataset/testset/`.

### 2026-08-09 — T3.4 dùng exact deterministic quotas và bảo vệ semantic anchors

- **Context:** Task noise cũ dùng Bernoulli 5%, cho phép compound labels và gọi
  gold query là SPARQL. Cách này không đảm bảo count/type distribution, khó tái
  lập, và có thể làm hỏng entity/date/number anchors.
- **Options considered:** Random 5% theo từng record; sinh nhiều candidates rồi
  filter; hoặc deterministic single-operation allocation với exact quotas.
- **Decision:** Giữ 3.000 Stage C originals và thêm đúng 150 variants bằng seed
  42: 38 typo, 38 abbrev, 37 fragment, 37 mixed case. Mỗi source tối đa một
  variant; chỉ structural phrases được abbreviation; mọi slot/entity anchor được
  bảo vệ và validate lại. SQL, Stage A hash và generation metadata bất biến.
- **Rationale:** Exact quotas và SHA-derived RNG làm dataset byte-stable và audit
  được. Single-operation labels giúp ablation rõ nghĩa; protected spans giảm
  semantic drift trong khi vẫn tạo lỗi surface realistic.
- **Consequences:** Pipeline full-size fixture, exact validators, manifest,
  process lock, unique staging và journaled recovery đã sẵn sàng. Vì POSIX không
  thể atomic rename hai sibling paths như một unit, mỗi file atomic riêng và
  manifest hash làm split pair fail closed. `nl_normalized` phải recompute vì nó
  là derived field của noisy `nl`. Final artifact và audit 30 rows vẫn chờ T3.3
  live output; automated gates không thay tiêu chí ít nhất 27/30 decipherable.
- **Revisit:** Sau manual audit; nếu một type thường khó hiểu, chỉnh dictionary
  hoặc transform nhưng giữ count/quota contract và tăng schema version.
- **Linked:** `docs/tasks/phase-3-dataset/04-noise-injection.md`,
  `src/nl2sparql/dataset/noise/`, `scripts/11_inject_noise.py`.

### 2026-08-09 — T3.2 dùng limit-monotonic live witnesses thay vì 1.000 scans

- **Context:** T3.2 cũ sinh SPARQL offline. Nếu execute độc lập 1.000 GoogleSQL
  records, enriched token templates sẽ lặp nhiều scan 13–14 GB và có thể vượt
  BigQuery Sandbox quota. Đồng thời live month probes chỉ tìm thấy hai hard
  templates non-empty, nên target hard 25% xung đột cap 10%/template.
- **Options considered:** Execute đủ 1.000 queries; giữ offline-only; chấp nhận
  zero rows; hoặc group các query chỉ khác `LIMIT n` và execute witness nhỏ
  nhất để dùng tính đơn điệu non-empty.
- **Decision:** Sinh deterministic 1.000 SQL records với allocation 350 easy /
  450 medium / 200 hard. Chỉ dùng 16 live templates. Execute 81 witnesses;
  singleton dùng `live_exact`, còn cùng semantics với `n` lớn hơn dùng
  `live_limit_monotonic`. Gate 20 GiB/witness, 96 GiB tổng, cache off.
- **Rationale:** Nếu query `LIMIT 1` trả row thì cùng query với limit lớn hơn
  chắc chắn non-empty; proof không claim exact cardinality. 20% hard là maximum
  honest share từ hai live hard templates dưới cap 100 records/template.
- **Consequences:** 1.000/1.000 records có proof, 81 exact + 919 monotonic, 0
  cache hits. Run xử lý 61.855.311.688 và billed 61.918.412.800 bytes. Artifact
  1.559.692 bytes có SHA-256
  `a42e76e363e48a495d46432cb3fad649206934a39e0b3e0110617fc5564b6709`.
  T3.3 phải consume field `sql` và giữ record hash/proof metadata.
- **Revisit:** Khi operational/mixer/bridge coverage tăng đủ ít nhất ba hard
  templates non-empty; khi đó có thể khôi phục hard share 25% mà không phá cap.
- **Linked:** `docs/tasks/phase-3-dataset/02-synthetic-pipeline.md`,
  `src/nl2sparql/dataset/generate.py`,
  `src/nl2sparql/dataset/stage_a/verify.py`,
  `data/dataset/raw/generation-config.json`.

### 2026-08-09 — T3.1 dùng contract-v2 GoogleSQL và live cap 20/64 GiB

- **Context:** Phase 3 vẫn có 25 SPARQL/Fuseki templates từ trước Pivot #1.
  Proposal live gate 5 GiB/query và 30 GiB/library fail closed ở query token đầu
  tiên vì enriched token TVF quét thêm contract dimension lịch sử.
- **Options considered:** Giữ dual SQL/SPARQL contract; bỏ live execution; nâng
  tùy ý riêng query lỗi; materialize token dimension; hoặc đo đủ distribution
  rồi chốt một gate chung có headroom.
- **Decision:** Migrate atomically sang 25 GoogleSQL contract-v2 templates, giữ
  stable IDs và 8/11/6 distribution. Chốt live cap 20 GiB/template và 64
  GiB/library sau diagnostic dry-run đủ 25 cases; execution luôn full-preflight,
  immediate re-dry-run, cache off, schema và non-empty policy fail closed.
- **Rationale:** 21 queries chỉ 0–0,33 GiB; bốn token queries 12,80–13,38 GiB do
  shared dimension, tổng 56,53 GiB. Gate 20/64 bao workload thật với headroom
  nhưng vẫn thấp hơn general cap 50 GiB/query và không che cost.
- **Consequences:** Dry-run và execute đều pass 25/25; 60.698.067.264 processed,
  60.749.250.560 billed, 0 cache hits, max wall 18,41s. 16 cases non-empty; 9
  empty cases đều explicit policy/gap. T3.2 phải dùng `sql_template`, typed slots,
  schema/CQ metadata và bounded date windows.
- **Revisit:** Sau Phase 5 evaluation; nếu typical token templates tiến sát 20
  GiB hoặc latency 30s, cân nhắc materialized token/contract enrichment.
- **Linked:** `docs/tasks/phase-3-dataset/01-query-templates.md`,
  `src/nl2sparql/dataset/templates/validate.py`,
  `scripts/08_validate_sql_templates.py`.

### 2026-08-09 — Phase 3 dùng bounded full-fact SQL với explicit latency evidence

- **Context:** T2-SQL-3 cần gate Plan B bằng live results. Run đầu phát hiện
  counts T2.3 là dictionary+1% filtered KG subset, không phải full public facts.
  Corrected full-month benchmark sau đó pass correctness nhưng labeled token
  stress case mất 45,79s, vượt descriptive target 30s.
- **Options considered:** Giữ filtered counts làm oracle; tự chấp nhận observed
  values; independent raw count; retry/cache để latency đẹp hơn; materialize
  full-month facts; hoặc giữ public facts và bắt buộc bounded windows.
- **Decision:** Pin independent raw oracles 65.621.456 transactions, 222.310
  blocks, 125.320.919 transfers. Giữ logical/TVF layer, không retry/cache hoặc
  materialize từ một stress run. Phase 3+ phải sinh date-bounded query với
  window hẹp nhất hợp lý và log dry-run bytes/latency.
- **Rationale:** Independent source count tránh population mismatch; 6/6
  correctness và 66,17 GB total chứng minh layer đúng/bounded. Một full-month
  exact-distinct+precision audit là upper-bound workload, không đủ evidence để
  đổi architecture nhưng latency miss phải còn visible.
- **Consequences:** Phase 2 SQL đủ điều kiện mở Phase 3. Interactive/evaluation
  token queries không được mặc định quét trọn 31 ngày; validator/cost display
  là contract bắt buộc. Filtered KG counts vẫn dùng đúng scope cho Plan A.
- **Revisit:** Sau Phase 5 execution evaluation; nếu typical bounded queries
  vẫn >30s, cân nhắc materialized aggregates hoặc giảm maximum window.
- **Linked:** `docs/tasks/phase-2-sql/03-smoke-benchmark.md`,
  `docs/sql-benchmark.md`, `src/nl2sparql/sql/benchmark.py`.

### 2026-08-09 — T2-SQL-2 dùng immutable label snapshots và explicit Sandbox TTL

- **Context:** Plan B cần stable entity labels và canonical BigQuery routines.
  Live apply đồng thời phát hiện project `nl2sparql-thesis` chưa bật billing nên
  BigQuery Sandbox tự áp default expiration 60 ngày dù create request gửi
  `None`.
- **Options considered:** Mutable label table; version column trong một table;
  immutable digest snapshots sau stable view; coi Sandbox TTL như durable; hoặc
  fail mọi deployment cho tới khi bật billing.
- **Decision:** Dùng immutable `entity_labels_snapshot_<sha12>` sau stable
  `entity_labels_v1`, 2 logical views và 6 bounded TVFs. Durable mode fail
  closed trên mọi TTL. Flag explicit `--allow-sandbox-expiration` chỉ accept
  đúng `5.184.000.000 ms`, read-back server policy/expiry và in deadline.
- **Rationale:** Snapshot + stable view giữ audit/rollback và ngăn version join
  duplication. Explicit Sandbox mode cho phép tiếp tục research trên hạ tầng
  hiện có mà không che giấu retention constraint hoặc tự ý thay đổi billing.
- **Consequences:** 5.135 unique labels và toàn bộ routines đang live; 6/6 source
  schemas pass, representative dry-run cao nhất 30.551.889.008 bytes dưới cap
  50 GiB. Snapshot/view hiện expire 2026-10-08; phải bật billing hoặc redeploy
  trước đó. Legacy `nl2sparql_kg.labeled_addresses` được giữ nguyên.
- **Revisit:** Trước 2026-10-01 hoặc ngay khi project bật billing; redeploy ở
  durable mode và xác nhận dataset/snapshot/view không còn expiration.
- **Linked:** `docs/tasks/phase-2-sql/02-label-enriched-layer.md`,
  `src/nl2sparql/sql/label_layer.py`,
  `scripts/06_deploy_sql_label_layer.py`.

### 2026-08-09 — Plan B dùng hybrid GoogleSQL catalog và date-bounded TVFs

- **Context:** Pivot #1 chuyển execution target sang BigQuery, nhưng raw public
  tables không tự cung cấp canonical joins, role-aware entity semantics hoặc
  bắt buộc date/cost guards. Logical views cũng không nhận query parameters.
- **Options considered:** Prompt query trực tiếp public tables; materialize full
  monthly snapshot; hoặc hybrid layer dùng public facts, managed label
  dimension và parameterized TVFs.
- **Decision:** Chọn hybrid. T2-SQL-1 commit machine-readable catalog gồm 6
  sources, 6 relations, 6 joins, 41 semantic mappings và CQ01-CQ30. Fact
  windows dùng half-open `[start_date, end_date)`, tối đa 31 ngày, dry-run và
  cap 50 GiB/query. T2-SQL-2 sẽ tạo `entity_labels_v1` và TVFs.
- **Rationale:** Cách này giữ partition pruning và dữ liệu public cập nhật mà
  vẫn cho downstream một interface nhỏ, testable và fail closed. CQ mapping
  buộc gaps/unsupported semantics phải hiện rõ thay vì model tự suy diễn.
- **Consequences:** 25 CQs supported; CQ21/CQ23/CQ27/CQ28 thiếu operational
  label coverage; CQ24 không hỗ trợ vì public substrate không decode distinct
  meta-transaction initiator/executor. CQ17 chỉ dùng block beneficiary, không
  claim validator identity. CQ18 bổ sung canonical transaction→contract join.
- **Revisit:** Sau T2-SQL-3 nếu representative query vượt 50 GiB hoặc latency
  gate yêu cầu materialized intermediate; không nới role/semantic safety để
  làm benchmark pass.
- **Linked:** `docs/tasks/phase-2-sql/01-analytical-schema.md`,
  `src/nl2sparql/sql/catalog/ethereum_analytics.json`,
  `docs/research/bigquery-analytical-layer-options-2026-08-09.md`.

### 2026-08-09 — T2.2 dùng role-aware hybrid snapshots và fail closed

- **Context:** Seed-42 audit chứng minh extraction theo chuỗi giống EVM address
  làm mất chain context. Protocol token, operational contract và exchange
  treasury cũng không thể dùng thay thế nhau trong downstream queries.
- **Options considered:** Parse/execute mọi adapter JavaScript; curate thủ công
  toàn bộ dictionary; hoặc hybrid snapshot với automated chain-aware tokens và
  reviewed pinned CEX/protocol evidence.
- **Decision:** Chọn hybrid fail-closed. Tất cả rows bắt buộc `chain_id=1`, role
  `operational|token|treasury`, immutable revision và row locator. CoinGecko
  `chainId=1` cung cấp bulk tokens; reviewed rows có precedence; ambiguous hoặc
  non-Ethereum evidence bị loại.
- **Rationale:** Cách này giữ được scale 5.135 records và CI offline nhưng không
  thực thi upstream code hay suy diễn chain/role từ address shape.
- **Consequences:** Independent seed-20260809 audit pass 50/50. Chỉ 14 rows được
  phép dùng cho flow analysis; token/treasury rows vẫn hữu ích cho linking và
  attribution nhưng không được giả làm operational endpoints.
- **Revisit:** Khi Phase 4/Plan B evaluation cần tăng operational coverage; mỗi
  row mới vẫn phải qua cùng provenance contract và independent audit.
- **Linked:** `docs/superpowers/specs/2026-08-09-t2-2-chain-aware-remediation-design.md`,
  `data/entity_dictionary/curated/reviewed_ethereum_entities.csv`,
  `docs/research/entity-dictionary-manual-sample-remediated-2026-08-09.md`.

### 2026-08-09 — T2.2 phải rebuild DefiLlama rows theo chain context

- **Context:** Manual audit seed 42 trên 50 dictionary rows chỉ pass 43. Hai CEX
  addresses thuộc BSC/Arbitrum; bốn protocol addresses thuộc Base, Polygon,
  Arbitrum, Mantle hoặc zkSync; một row là prefix bị cắt từ Aptos resource.
- **Options considered:** Tick acceptance dựa trên 86% sample pass; xóa riêng 7
  rows; hoặc rebuild toàn bộ DefiLlama-derived rows bằng parser chain-aware.
- **Decision:** Không tick T2.2 manual acceptance và không vá riêng sample.
  Rebuild toàn bộ DefiLlama rows, chỉ nhận explicit Ethereum chain context và
  pin row-level provenance trước khi audit lại.
- **Rationale:** Lỗi đến từ acquisition method nên 7 sampled rows không phải
  outlier độc lập. Vá sample sẽ che population risk và làm entity linker học
  attribution sai chain.
- **Consequences:** Dictionary hiện tại vẫn dùng được để phát triển structural
  tests nhưng không được coi là production-quality Ethereum dictionary. T2-SQL
  label views và Phase 3 entity sampling phải chờ artifact remediated.
- **Revisit:** Sau khi regenerate artifacts và independent sample 50 pass.
- **Linked:** `docs/tasks/phase-2-kg/02-entity-dictionary.md`,
  `docs/research/entity-dictionary-manual-sample-2026-08-09.md`,
  `src/nl2sparql/linking/dictionary/sources.md`.

### 2026-08-09 — Pivot từ NL2SPARQL sang NL2SQL tại Pivot Point #1

- **Context:** Full KG 73,9M triples load được vào TDB2 nhưng benchmark chính
  thức cho Q1 count và Q2 filter không LIMIT mất lần lượt 34,55s và 38,01s.
  Dictionary có 4.520 entries nhưng manual sample sau đó fail 7/50.
- **Options considered:** Tiếp tục Plan A và tối ưu/cache Fuseki; thu nhỏ KG;
  hoặc tuân thủ NO-GO gate và pivot Plan B trên BigQuery.
- **Decision:** Pivot sang NL2SQL. Giữ full KG như negative-result artifact,
  dừng T2.5 full validation và không đầu tư thêm vào optimization Plan A.
- **Rationale:** T2.6 quy định bất kỳ một NO-GO trigger nào cũng buộc pivot;
  query đơn giản >5s đã kích hoạt trigger #3. Cache/pre-aggregation hoặc thu nhỏ
  KG sẽ thay đổi workload thay vì làm evidence hiện tại pass.
- **Consequences:** Bổ sung Phase 2 SQL schema/views/smoke tasks; migrate target
  của Phase 3–7 từ SPARQL sang Standard SQL. Dictionary, extraction, dataset
  protocol, linker/evaluation methodology và model training vẫn tái sử dụng.
- **Revisit:** Không đảo lại Plan A trong implementation; chỉ thảo luận KG như
  negative finding/limitation khi viết luận văn.
- **Linked:** `docs/pivot-decision-1.md`, `docs/plan-b-adjustments.md`,
  `docs/tasks/phase-2-kg/06-pivot-decision.md`, `docs/kg-benchmark.md`.

### 2026-08-09 — Materialize full KG bằng chunk 50k có checkpoint xác thực

- **Context:** Live Morph-KGC với chunk 100k tạo 2.43M triples rồi bị kernel kill
  (exit 137) khi RDFLib serialize trên máy 7.4 GiB RAM. Run nhiều giờ cũng cần
  tiếp tục an toàn sau interruption.
- **Options considered:** Single-shot; chunk 100k không resume; chunk 50k với
  reuse mọi `output.nt`; chunk 50k với manifest và completion marker.
- **Decision:** Mặc định 50k rows/chunk, chỉ reuse chunk có completion marker,
  và bắt buộc manifest SHA-256 của mapping/input/chunk size khớp khi `--resume`.
- **Rationale:** 50k giữ peak memory dưới giới hạn host và hoàn tất 89/89 chunk;
  manifest ngăn trộn output từ input hoặc cấu hình khác, marker ngăn tin partial
  file sau crash.
- **Consequences:** Full output đạt 73,906,181 triples và TDB2 chỉ 10.88 GB.
  Selective queries đạt <2s nhưng aggregate counts mất 15.12-69.68s, nên T2.6
  phải xem đây là NO-GO evidence thay vì coi T2.4 pass hoàn toàn.
- **Revisit:** Nếu tiếp tục Plan A sau Pivot #1, benchmark pre-aggregation hoặc
  cached dataset statistics mà không thay thế metric exact-match cốt lõi.
- **Linked:** `src/nl2sparql/kg/rml/run_morph_full.py`,
  `docs/tasks/phase-2-kg/04-rml-full-mapping.md`, `docs/kg-benchmark.md`.

### 2026-06-28 — T2.2 dictionary dùng committed source snapshots

- **Context:** Public label sources for Ethereum addresses can change, rate-limit, or block automation. T2.2 still needs a stable input for Phase 4 entity linking and for thesis reproducibility.
- **Options considered:** Live scrape in CI; keep only final JSON artifacts; commit raw source snapshots plus final generated artifacts.
- **Decision:** Commit `data/entity_dictionary/raw/entities.csv`, curated coverage metadata, and final dictionary JSON artifacts. Live fetchers are optional acquisition tools and must not be required by CI.
- **Rationale:** A committed raw snapshot makes future refreshes auditable through git diffs while keeping tests deterministic and offline.
- **Consequences:** Automated acceptance can verify structure, count, coverage, sorting, normalization, and provenance locally. The 50-entry manual verification remains a separate evidence step and must stay pending until sampled rows are checked against external source pages.
- **Revisit:** When refreshing the dictionary after Phase 4 linker evaluation or when replacing source acquisition with a stable API/keyed provider.
- **Linked:** `docs/tasks/phase-2-kg/02-entity-dictionary.md`, `data/entity_dictionary/raw/entities.csv`, `src/nl2sparql/linking/dictionary/sources.md`.

### 2026-06-27 — Chốt ontology extension v0.1.0 cho Ethereum KG

- **Context:** EthOn cover tốt transaction/block/account nền tảng nhưng thiếu DeFi protocol classes, semantic labels cho địa chỉ, token-transfer model thân thiện với NL2SPARQL, và metadata giàu cho schema linker.
- **Options considered:** Sửa trực tiếp EthOn; tạo ontology local tối thiểu chỉ cho RML; tạo ontology extension versioned với class/property local và documentation contract.
- **Decision:** Tạo `eth-kg-extension-v0.1.0.ttl` trong namespace `https://thesis.example.org/eth-kg/`, subclass EthOn classes, không override EthOn predicates, và bắt buộc mỗi property có label/comment/synonyms/example/domain/range.
- **Rationale:** Extension local giữ EthOn nguyên vẹn nhưng cung cấp đúng abstraction cho thesis: exchange, mixer, DEX, lending, bridge, NFT marketplace, token transfer, metadata entity-labeling và meta-transaction. Documentation contract tạo input nhất quán cho schema linker ở Phase 4.
- **Consequences:** T2.2 có thể xây entity dictionary dựa trên account classes/identity properties; T2.4 có schema ổn định để mở rộng RML mapping; Phase 3 có competency questions làm seed cho query templates. Protégé reasoner validation vẫn cần manual GUI check ngoài CLI.
- **Revisit:** Khi hoàn thành T2.4 nếu mapping full cần đổi domain/range hoặc thêm protocol-specific event classes.
- **Linked:** `docs/tasks/phase-2-kg/01-ontology-extension.md`, `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`, `src/nl2sparql/kg/ontology/competency-questions.md`.

### 2026-06-21 — Giữ Morph-KGC cho RML pipeline sau pilot T1.3

- **Context:** T1.3 cần chứng minh RML có thể chuyển dữ liệu BigQuery pilot thành RDF parse được và truy vấn được trước khi mở rộng sang Phase 2.
- **Options considered:** Morph-KGC trực tiếp trên CSV; tiền xử lý CSV trước Morph-KGC; chuyển sang RMLMapper hoặc RDFLib thuần.
- **Decision:** Giữ Morph-KGC 2.8.1 và mapping RML trực tiếp cho pipeline; pilot chỉ cover transactions và blocks.
- **Rationale:** Morph-KGC materialized 770 triples từ 100 transactions và 10 blocks, giữ datatype RDF, upload Fuseki thành công và cả ba query khớp CSV nguồn.
- **Consequences:** T2.4 có thể mở rộng mapping này cho token transfers và contracts. Dữ liệu CSV/TTL vẫn là artifact local bị ignore; mapping, runner, notebook và tests được version-control.
- **Revisit:** T2.4 nếu dữ liệu một tháng gây vấn đề về tốc độ, bộ nhớ hoặc NULL handling; khi đó benchmark RMLMapper.
- **Linked:** `docs/tasks/phase-1-pilot/03-rml-pilot.md`, `src/nl2sparql/kg/rml/pilot_mapping.ttl`, `notebooks/04_rml_pilot.ipynb`.

### 2026-06-20 — Commit EthOn 0.2 làm ontology nền cho pilot

- **Context:** T1.1 cần ontology tái lập để kiểm chứng Fuseki và làm namespace nền cho RML pilot T1.3.
- **Options considered:** Tải động mỗi lần; commit skeleton tối thiểu; commit toàn bộ ontology chính thức.
- **Decision:** Commit toàn bộ `EthOn.ttl`, giữ nguyên namespace `http://ethon.consensys.net/`, và chạy truy vấn không inference.
- **Rationale:** File chính thức nhỏ (86,718 bytes), loại bỏ phụ thuộc mạng và giữ đầy đủ source; SHA-256 là `e73e19bf0d6bbb0e28b1497a73e4499ca78ee9c1e8c475fa31e7c821354ce71d`.
- **Consequences:** T1.3 có thể tham chiếu trực tiếp EthOn; ontology đo được 1,423 triples, 40 classes, 48 object properties, 60 datatype properties và 29 quan hệ subclass. DEX, lending, mixer, token standards và dữ liệu hậu PoS vẫn cần extension ở Phase 2.
- **Revisit:** T2.1 khi thiết kế ontology extension.
- **Linked:** `docs/tasks/phase-1-pilot/01-load-ethon.md`, `data/ontologies/EthOn.ttl`.

### 2026-06-20 — Cố định và bảo toàn dữ liệu BigQuery pilot T1.2

- **Context:** T1.2 cần một lát dữ liệu nhỏ, tái lập được để kiểm tra BigQuery → CSV
  trước khi thiết kế RML mapping; các cột Ethereum NUMERIC có nguy cơ mất chính xác.
- **Options considered:** Lấy ngày mới nhất động; lấy mẫu ngẫu nhiên; cố định ngày và
  giới hạn dòng; serialize số qua float hoặc chuỗi thập phân.
- **Decision:** Cố định ngày `2024-01-15`, giới hạn 100/10/100/50 dòng cho
  transactions/blocks/token transfers/contracts, và serialize `Decimal` thành chuỗi.
- **Rationale:** Query có thể tái lập, dry-run chỉ quét `0.50 GiB`, còn biểu diễn chuỗi
  giữ nguyên giá trị wei trước bước RDF mapping.
- **Consequences:** CSV pilot chỉ lưu local dưới `data/raw/pilot/` và bị `.gitignore`;
  repo lưu SQL, extractor, notebook và mô tả edge cases. Sample ghi nhận 80 zero-value,
  19 large-integer và 93 typed transactions.
- **Revisit:** Phase 2 khi chốt slice extraction đầy đủ và schema literal trong RML.
- **Linked:** `docs/tasks/phase-1-pilot/02-bigquery-100rows.md`,
  `src/nl2sparql/kg/extraction/pilot_extract.py`.

### 2026-06-14 — Xác nhận BigQuery Ethereum smoke access và cost estimate

- **Context:** T0.3 cần chứng minh service account local query được BigQuery public Ethereum và estimate chi phí extraction 1 tháng.
- **Options considered:** Chỉ dựa vào estimate trong task doc; chạy query thật và dry-run bằng `google-cloud-bigquery`.
- **Decision:** Dùng service account local qua `GOOGLE_APPLICATION_CREDENTIALS`, chạy COUNT ngày `2024-01-01` và dry-run tháng `2024-01-01` đến `2024-01-31`.
- **Rationale:** Kết quả thật xác nhận IAM/API/credentials hoạt động, đồng thời dry-run không tốn query charge và cho số byte chính xác cho query extraction hiện tại.
- **Consequences:** T0.3 không còn blocked; tháng 2024-01 với 5 cột pilot estimate `6.04 GiB`, thấp hơn nhiều so với free tier 1 TiB/tháng.
- **Revisit:** Phase 2 khi chốt slice dữ liệu và danh sách cột extraction cuối.
- **Linked:** `docs/tasks/phase-0-setup/03-bigquery-access.md`, `scripts/01_bigquery_smoke.py`, `src/nl2sparql/kg/extraction/bigquery_smoke.py`.

### 2026-06-14 — Nhóm related work theo vai trò trong luận văn

- **Context:** Literature review cần phục vụ cả chương Related Work lẫn thiết kế hệ thống, không chỉ là danh sách citation.
- **Options considered:** Liệt kê paper theo năm; nhóm theo kỹ thuật; nhóm theo contribution/risk của đề tài.
- **Decision:** Chia thành 6 nhóm: NL2SPARQL classic, KGQA+LLM, Text-to-SQL, Blockchain KG, Entity/Schema Linking, Synthetic Data Generation.
- **Rationale:** Cách nhóm này map trực tiếp tới 3 đóng góp khoa học, Plan B, và các module triển khai như linker, dataset generation, constrained decoding.
- **Consequences:** Dễ viết thesis theo luận điểm, nhưng cần chuẩn hóa BibTeX metadata lần nữa trước bản nộp cuối.
- **Revisit:** Phase 7 khi viết chương Related Work và chuẩn hóa citation theo template trường.
- **Linked:** `docs/related-work/papers.bib`, `docs/related-work/notes.md`, `docs/related-work/comparison-table.md`.

### 2026-06-14 — Bắt buộc dry-run và filter ngày cho BigQuery Ethereum

- **Context:** BigQuery public Ethereum là nguồn dữ liệu chính nhưng query không giới hạn thời gian có thể quét toàn bảng và tiêu tốn quota/cost.
- **Options considered:** Cho phép exploratory SQL tự do; chỉ document cảnh báo; encode query helper có filter `block_timestamp` và dry-run config.
- **Decision:** Mọi query extraction/smoke phải có filter ngày; estimate chi phí dùng `QueryJobConfig(dry_run=True, use_query_cache=False)`.
- **Rationale:** Kiểm soát quota 1TB/tháng, tránh lỗi thao tác khi chạy pipeline extract, và tạo bằng chứng cost estimate cho methodology.
- **Consequences:** Script BigQuery smoke yêu cầu credentials thật trước khi chạy; helper test offline chỉ kiểm tra query safety và config.
- **Revisit:** Phase 2 khi chốt kích thước slice dữ liệu 1 tháng và danh sách cột extraction cuối.
- **Linked:** `src/nl2sparql/kg/extraction/bigquery_smoke.py`, `scripts/01_bigquery_smoke.py`, `src/nl2sparql/kg/extraction/bq_schema.md`.

### 2026-06-14 — Chạy Fuseki local bằng Docker Compose

- **Context:** Host hiện tại không có Java, trong khi Apache Jena Fuseki cần JVM. Cài Java trực tiếp làm môi trường local khó tái lập hơn.
- **Options considered:** Cài Java 17+ trên host; build image Fuseki từ `eclipse-temurin` và tải tarball Apache; dùng image Docker Hub `stain/jena-fuseki:latest`.
- **Decision:** Dùng Docker Compose với image `stain/jena-fuseki:latest`, dataset in-memory `/test`, port `3030`, admin password local cố định `admin`.
- **Rationale:** Docker giữ Java/Fuseki trong container, tránh yêu cầu Java host; Docker Hub pull thành công trong khi `archive.apache.org` timeout từ môi trường này.
- **Consequences:** Lệnh setup Fuseki chuẩn là `src/nl2sparql/kg/scripts/start_fuseki.sh` hoặc `docker compose -f infrastructure/docker/docker-compose.fuseki.yml up -d`; upload smoke data cần Basic Auth `admin:admin`.
- **Revisit:** Phase 2 khi chuyển từ in-memory `/test` sang TDB2 persistent dataset.
- **Linked:** `docs/tasks/phase-0-setup/02-fuseki-local.md`, `docs/setup-fuseki.md`, `infrastructure/docker/docker-compose.fuseki.yml`.

### 2026-06-14 — Dùng `uv` làm trình quản lý môi trường Python

- **Context:** T0.1 ban đầu mô tả setup qua `requirements.txt`/`pip`, nhưng project cần môi trường tái lập nhanh cho stack lớn gồm KG, ML, demo và dev tools.
- **Options considered:** Giữ `requirements.txt` + `pip`; dùng Poetry; dùng `uv` với `pyproject.toml` và `uv.lock`.
- **Decision:** Dùng `uv` làm workflow chính, với `pyproject.toml`, `.python-version` 3.11 và `uv.lock`.
- **Rationale:** `uv` tự quản lý Python 3.11, resolve/install nhanh, lock dependency rõ hơn, phù hợp stack nhiều package nặng như `torch`, `transformers`, `bitsandbytes`.
- **Consequences:** Lệnh setup chuẩn là `uv sync`; các task cũ nhắc `pip install -r requirements.txt` cần được hiểu là legacy và cập nhật dần khi chạm tới.
- **Revisit:** Sau Phase 0 nếu cần publish package hoặc tách dependency group cho Kaggle/HF Spaces.
- **Linked:** `pyproject.toml`, `.python-version`, `uv.lock`, `docs/tasks/phase-0-setup/01-repo-and-env.md`.

### 2026-06-14 — Chuẩn hóa cấu trúc repo theo package `src/nl2sparql`

- **Context:** Repo ban đầu chỉ có `memory/`, `tasks/` và kế hoạch triển khai ở root; tài liệu và source code chưa được tách rành mạch.
- **Options considered:** Giữ `memory/`/`tasks/` ở root; gom toàn bộ tài liệu vào `docs/`; hoặc dùng cấu trúc `.claude/` như bản nháp README cũ.
- **Decision:** Chuyển tài liệu vận hành vào `docs/memory/`, backlog vào `docs/tasks/`, kế hoạch vào `docs/planning/`, và đặt source code trong package `src/nl2sparql/`.
- **Rationale:** Root repo gọn hơn, package boundary rõ hơn cho Python import/test/deploy, đồng thời tách được source code, dữ liệu, tài liệu, hạ tầng và notebook.
- **Consequences:** Các task cũ cần dùng đường dẫn `docs/...` và `src/nl2sparql/...`; mọi module mới nên import qua `nl2sparql.*`.
- **Revisit:** Sau khi hoàn thành Phase 0 nếu tooling packaging yêu cầu đổi tên package.
- **Linked:** `README.md`, `docs/memory/01-ARCHITECTURE.md`, `docs/memory/04-CONVENTIONS.md`.

### 2025-XX-XX — Khởi tạo decision log

- **Context:** Bắt đầu dự án, cần file để track decisions.
- **Decision:** Tạo file này, format reverse-chronological.
- **Rationale:** Theo "quy tắc sống còn #4" trong `00-PROJECT_OVERVIEW.md`.
- **Consequences:** Mọi quyết định phải ghi ở đây — overhead nhỏ, lợi ích lớn khi viết thesis.
- **Revisit:** Không cần.
- **Linked:** Tất cả memory files.

---

## Quyết định chờ ghi (placeholders — điền khi đến)

- [ ] Phase 0: Chốt repo URL, license, .gitignore policy.
- [x] Phase 0: Không dùng remote LLM provider trên critical path.
- [ ] Phase 1: Chốt Plan A khả thi sau pilot (Pivot Point #1 chuẩn bị).
- [ ] Phase 2: Chốt namespace ontology cuối cùng.
- [ ] Phase 2: Chốt mức độ extension EthOn (số class/property thêm).
- [ ] Phase 2: Chốt kích thước slice BigQuery (1 tháng → bao nhiêu transactions thực tế).
- [x] Phase 2: **Pivot Point #1** — pivot Plan B (2026-08-09).
- [ ] Phase 3: Chốt số templates cuối cùng (mục tiêu 25-30).
- [x] Phase 3: Chốt deterministic bilingual catalog, không dùng model generation.
- [ ] Phase 3: Chốt mức noise injection (% items, loại noise nào).
- [ ] Phase 4: Chốt embedding model cuối (MiniLM-L6 hay multilingual?).
- [ ] Phase 4: Chốt fuzzy threshold sau hyperparam search.
- [ ] Phase 5: Chốt format prompt cho B1/B2 (system prompt + few-shot template).
- [ ] Phase 5: **Pivot Point #2** — scope down nếu cần.
- [ ] Phase 6: Chốt QLoRA hyperparam sau ablation.
- [ ] Phase 6: Chốt constrained decoding lib (outlines vs lm-format-enforcer).
- [ ] Phase 7: Chốt 3 case studies cuối cùng.

---

## Cách dùng entries này khi viết thesis

Trong chương Methodology (hoặc Implementation), mỗi quyết định kỹ thuật phải có justification. File này là nguồn chính:

1. Tìm decisions có `Linked` đến chương đang viết.
2. Paraphrase Context + Rationale → 1 đoạn Methodology.
3. Trade-off và Consequences → vào phần "Discussion" hoặc "Limitations".
