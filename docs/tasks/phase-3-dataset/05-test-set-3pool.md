# T3.5 — Test Set 100 cặp (3-Pool Cross-Validation)

## Mục tiêu

Xây dựng test set ~100 cặp `(NL, SPARQL)` chất lượng cao, viết bởi nhiều người độc lập theo quy trình 3-pool để tránh bias từ template/synthetic.

## Bối cảnh & lý do

**Đây là tài sản quan trọng nhất của luận văn.** Test set độc lập với template và synthetic data → đo được generalization thực sự, không phải overfit trên template.

3-pool design:
- **Pool A (3-5 người):** viết câu hỏi tiếng Anh KHÔNG nhìn ontology → đảm bảo NL "tự nhiên" như user thật.
- **Pool B (bạn + 1 người):** viết SPARQL gold dựa vào câu hỏi từ Pool A.
- **Pool C (1 người độc lập):** review từng cặp, chấm điểm chất lượng.

## Phụ thuộc

- T2.1 — Ontology stable.
- T2.2 — Entity dictionary có entries phổ biến (Binance, Uniswap, Tornado Cash, etc.).
- T2.4 — Full KG đã load để verify SPARQL execute được.

## Đầu vào

- 3-5 collaborators cho Pool A (recruit từ classmate / lab / cộng đồng nghiên cứu).
- 1 collaborator cho Pool B (peer reviewer).
- 1 collaborator cho Pool C (independent reviewer, không tham gia A/B).

## Đầu ra

- File `data/dataset/test/test-100.jsonl` — 100 cặp final.
- File `data/dataset/test/raw_pool_a.csv` — câu hỏi raw từ Pool A (~150 câu, sẽ filter còn 100).
- File `data/dataset/test/sparql_pool_b.csv` — SPARQL từ Pool B.
- File `data/dataset/test/review_pool_c.csv` — review notes.
- Document `data/dataset/test/PROCESS.md` — mô tả quy trình tuyển dụng + brief + payment (nếu có).
- Document `data/dataset/test/CONSENT.md` — consent form (đặc biệt nếu publish).

## Acceptance criteria

- [ ] ≥100 cặp final pass review (target 110-120 raw → filter 100).
- [ ] Phân bố difficulty: ~30 Easy / ~50 Medium / ~20 Hard.
- [ ] 100% SPARQL execute thành công, kết quả non-empty (hoặc explicit "expected empty").
- [ ] Pool A coverage: ≥3 người, mỗi người ≥20 câu.
- [ ] Pool C reject rate <30% (nếu cao hơn → chất lượng Pool A/B kém).
- [ ] Inter-annotator agreement (Pool C trên subset 30 câu): Cohen's kappa ≥0.7.

## Hướng dẫn triển khai

### Brief cho Pool A (template)

```
Bạn sẽ viết câu hỏi tiếng Anh về dữ liệu Ethereum mà một
[journalist / compliance officer / researcher] thực sự sẽ hỏi.

Bối cảnh: Tưởng tượng bạn đang điều tra dòng tiền trên Ethereum
trong tháng [X-Y]. Bạn quan tâm các dạng câu hỏi:
- Tìm giao dịch đặc biệt (số tiền lớn, từ/đến địa chỉ cụ thể)
- Phân tích pattern (top senders, hourly distribution)
- Truy vết dòng tiền (mixer, exchanges, DEX)

Yêu cầu:
- Viết 30-40 câu hỏi tiếng Anh tự nhiên.
- ĐỪNG đọc ontology hoặc database schema trước khi viết.
- Dùng tên thực thể (Binance, Tornado Cash, Uniswap) — chúng tôi cung cấp danh sách.
- Đa dạng độ phức tạp.

KHÔNG cần viết SPARQL.
```

Cấp danh sách entity rút gọn (top-30 named entities) để Pool A dùng.

### Brief cho Pool B

```
Bạn nhận ~150 câu hỏi tiếng Anh. Với MỖI câu:
1. Viết SPARQL "đúng nhất" theo ontology (file kèm).
2. Chạy thử trên Fuseki.
3. Note kết quả (rỗng / có kết quả / lỗi).
4. Nếu câu mơ hồ → flag "ambiguous" và viết 2 SPARQL khác nhau.
5. Nếu câu vượt scope ontology → flag "out_of_scope".

Format: CSV với cột (id, nl, sparql, status, notes).
```

### Brief cho Pool C (Independent Reviewer)

```
Bạn nhận pairs (NL, SPARQL). Với MỖI pair, chấm:
- Quality NL (1-5): tự nhiên, rõ ràng?
- Faithfulness (1-5): SPARQL có trả lời chính xác câu hỏi NL?
- Difficulty (Easy/Medium/Hard): theo cảm quan của bạn.
- Decision: ACCEPT / REVISE / REJECT.

Nếu REVISE: viết note chỉnh.
Nếu REJECT: lý do.
```

### Quy trình orchestration

```
Week 1: Recruit + brief (chọn channel: Discord, FB groups, university listserv).
Week 2: Pool A viết câu hỏi → ~150 raw câu.
Week 3: Pool B viết SPARQL → ~150 cặp.
Week 4: Pool C review → reject ~20-30%, revise ~20%.
Week 4 (cuối): Bạn final filter → 100 cặp tốt nhất.
```

### Stratification cho 100 final

Cố ý chọn để cover:
- 6+ category templates (filter, aggregation, top-k, multi-hop, ...).
- 3+ entity types (named entity, address-only, concept-class).
- Time ranges đa dạng.

### Schema record final

```json
{
  "id": "test-001",
  "source": "pool_a_user_03",
  "nl": "Find all transactions from Binance to Tornado Cash worth more than 100 ETH last month",
  "sparql": "SELECT ?tx ?value WHERE { ... }",
  "difficulty": "medium",
  "categories": ["filter", "entity_lookup", "time_range"],
  "ontology_elements": [":hasFrom", ":hasTo", ":hasValue", ":Transaction"],
  "expected_result_size": 17,
  "ambiguity_flag": false,
  "pool_b_writer": "anon_b1",
  "pool_c_score": {"quality": 5, "faithfulness": 5},
  "verified_executable": true,
  "verified_at": "2026-04-30T14:00:00Z"
}
```

### Payment & ethics

- Nếu trả tiền thí nghiệm viên: minimum wage địa phương × estimated time.
- Consent form rõ ràng: data sẽ public hay không, anonymize username.
- Nếu trường có IRB → submit (thường thesis ML không cần nhưng check).

## Rủi ro & note

- **Pool A khó tuyển:** plan B = bạn tự viết với personas khác nhau, tách thành 3 batches cách nhau ≥3 ngày.
- **Pool A viết câu vượt scope:** brief rõ ràng + cấp danh sách entity.
- **Pool B disagree với Pool A intent:** flag "ambiguous", tạo 2 versions, Pool C chọn.
- **Inter-annotator agreement thấp:** review brief Pool C, làm calibration trên 10 câu trước khi review hết.
- **Tốn thời gian:** start sớm (ngay sau T2.4), parallel với T3.2-T3.4.

## Estimated effort

3-4 tuần wall-clock (gồm chờ collaborator), ~1 tuần effort thật.

## Trạng thái

todo
