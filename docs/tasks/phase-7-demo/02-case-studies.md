# T7.2 — Case Studies (3 Personas)

## Mục tiêu

Xây dựng 3 case studies cụ thể, end-to-end, demonstrate giá trị thực tế của hệ thống cho 3 user personas (xem `00-PROJECT_OVERVIEW.md`).

## Bối cảnh & lý do

Thesis chap "Application & Case Studies" cần ví dụ "câu chuyện hoàn chỉnh" — không chỉ "câu hỏi → SPARQL → kết quả" mà là **bối cảnh → mục đích → loạt câu hỏi → insight rút ra**.

3 personas:
1. **Investigative journalist** — điều tra rút tiền sau hack.
2. **AML compliance officer (cá nhân)** — screen ví trước khi giao dịch.
3. **Interdisciplinary researcher** — phân tích DEX usage patterns.

## Phụ thuộc

- T7.1 — Validator + recovery (để demo run thông).
- T6.1 — B3 model.
- T2.4 — Full KG có data 1 tháng.

## Đầu vào

- Case study scenarios (build manual).
- Model + KG.

## Đầu ra

- File `docs/case_studies/01_journalist.md`.
- File `docs/case_studies/02_compliance.md`.
- File `docs/case_studies/03_researcher.md`.
- Notebook `notebooks/16_case_studies.ipynb` chạy reproducible.
- Screenshots cho thesis (placed in `docs/thesis/figures/`).

## Acceptance criteria

- [ ] Mỗi case study có ≥5 câu hỏi liên quan, chạy được trên KG.
- [ ] Mỗi case study có 1-2 "insight" từ kết quả truy vấn (không chỉ technical demo).
- [ ] Screenshots clear, có annotation.
- [ ] Document 1500-2500 từ mỗi case study (vừa đủ cho 1 chapter section).

## Hướng dẫn triển khai

### Case Study 1: Investigative Journalist

**Bối cảnh giả định:**
> Ngày 2024-XX-YY, dApp ABC bị hack mất Z ETH. Hacker rút từ contract về địa chỉ 0xHACK1. Nhà báo Mai muốn truy vết dòng tiền: hacker đã làm gì với số ETH này?

**Loạt câu hỏi (~6-8):**
1. "What is the total ETH that 0xHACK1 received in the day after the hack?" (verify scale)
2. "Show all outgoing transactions from 0xHACK1 worth more than 10 ETH in the next 7 days." (find distribution)
3. "Did 0xHACK1 send funds to any known mixer (e.g. Tornado Cash)?" (laundering signal)
4. "List the top 5 addresses receiving funds from 0xHACK1 in that period." (downstream)
5. "Were any of those receiving addresses connected to centralized exchanges?" (off-ramp)
6. "How many hops did the funds go through before reaching exchange addresses?" (depth)
7. "What was the time pattern of these transfers (hourly distribution)?" (automation evidence)
8. "Compare wallet behavior of 0xHACK1 with known mixer users — is the pattern similar?"

**Insight phải rút ra:**
- "Hacker dùng pattern X (e.g. split → mixer → exchange) typical for laundering."
- "Y% funds đi qua Tornado Cash trong 24h đầu."
- "Final on-ramp tới exchange Z — recovery actionable."

**Format document:**
```markdown
## Case Study 1: Tracing Stolen Funds

### Background
[Paragraph 1: scenario description]

### Investigation flow
[Numbered Q&A, mỗi câu có:
- NL question
- Generated SPARQL (collapsed code block)
- Result table snippet
- Brief interpretation
]

### Insights
[Bullet list of 3-5 findings]

### System performance
- Total queries: 8
- Recovery triggered: 1 (Q4 needed retry)
- Total time: ~30s
- All on local Fuseki, no data left device.
```

### Case Study 2: AML Compliance (cá nhân)

**Bối cảnh giả định:**
> Hân là freelance developer chuẩn bị nhận thanh toán 50K USD bằng USDC từ khách hàng ở address 0xCLIENT. Trước khi cho address vào ví, Hân muốn screening xem có rủi ro AML không.

**Loạt câu hỏi (~5-7):**
1. "Has 0xCLIENT received any funds directly from a sanctioned address in the last 30 days?"
2. "What categories of counterparties has 0xCLIENT interacted with most?"
3. "Find any transaction from 0xCLIENT to a known mixer."
4. "Top 10 senders to 0xCLIENT — are any flagged?"
5. "What's the typical transaction size pattern of 0xCLIENT?" (legitimate business vs suspicious)
6. "When was 0xCLIENT most active? Recent or historical?"

**Insight:**
- "0xCLIENT interactions are 95% with verified DeFi protocols — likely legit."
- HOẶC "0xCLIENT received 12 ETH from Tornado Cash 5 days ago — high risk, do NOT engage."

### Case Study 3: Interdisciplinary Researcher

**Bối cảnh giả định:**
> TS. Long từ khoa Kinh tế nghiên cứu hành vi user trên DEXes. Câu hỏi: "Pattern usage của Uniswap V3 khác Sushiswap thế nào trong tháng X?"

**Loạt câu hỏi (~6-8):**
1. "How many unique users did Uniswap V3 have in January 2024?"
2. "What was the median trade size on Uniswap vs Sushiswap?"
3. "Distribution of trade sizes — log-scaled histogram."
4. "Repeat user rate (users with ≥5 trades in the month)?"
5. "Time-of-day distribution of trades — when most active?"
6. "Cross-protocol users — how many used both Uniswap and Sushiswap?"
7. "Average gas fee per trade — protocol comparison."
8. "Which token pairs were most traded?"

**Insight:**
- "Uniswap V3 has higher repeat-user ratio → 'sticky' UX."
- "Sushiswap users tend to make smaller trades → retail."
- Researcher có thể export kết quả → import vào R/Python phân tích sâu.

**Note:** case study này highlight **non-technical user benefit** — TS. Long không cần học SPARQL.

### Implementation tips

- Setup KG có data thực, real addresses (anonymize nếu cần publish).
- Pre-run notebook để có reproducible kết quả.
- Screenshot bằng tool nhất quán (e.g., Carbon cho code, native screenshot cho UI).
- Bao gồm cả **lỗi và recovery** trong case study (real-world honesty).

### Anonymization

Nếu publish thesis online + screenshot có địa chỉ thật:
- Ngon nhất: dùng địa chỉ public đã có trong news (e.g., known hacks). Đổi format hash bớt: 0xa1b2...c3d4.
- Nếu không nhạy cảm (top exchanges, public protocols), không cần anonymize.

## Rủi ro & note

- **KG không có scenario data:** chọn ngày trong KG có sẵn event tương tự, hoặc scope bối cảnh xuống.
- **Hệ thống fail trên scenario:** debug, hoặc đổi câu hỏi sang easier — case studies phải SHOW SUCCESS, không show failure.
- **Câu chuyện quá fictional:** dùng inspiration từ real events (Lazarus Group, Ronin hack) nhưng anonymize nếu cần.

## Estimated effort

2-3 ngày.

## Trạng thái

todo
