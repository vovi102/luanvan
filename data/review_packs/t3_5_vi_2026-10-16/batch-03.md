# Vietnamese review — batch 03 (21–30)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-024

**Câu Vietnamese:** Trung bình mỗi khối có bao nhiêu giao dịch trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-024`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["average_transactions_per_block"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.transaction_count"]`.

```sql
SELECT AVG(transaction_count) AS average_transactions_per_block FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `cecb50398a37146e633a8684a6e3c16b274aeb8a09a4bda130b5172e063b84fb`.

English case binding: `1c6287d60f44e6fca11e091aee23e53ea4b2de12f4a7472ecbd7beb039eb8175`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-025

**Câu Vietnamese:** Có bao nhiêu sự kiện chuyển token trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-025`; difficulty: `easy`; CQ: CQ15.

Categories: token_specific, time_range; entity kinds: concept_class.

Expected columns: `["token_transfer_count"]`; expected result size: `1`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS token_transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `298956160d6b396a1d36c2683545fb919032f95cb09d9784ef0747327f378d71`.

English case binding: `b1eb93bff8b0f0a6506a973a6d6ec4f335f1bc475d88e9541b113a67cd4ccb62`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-026

**Câu Vietnamese:** Có bao nhiêu lượt chuyển token có lượng chuẩn hóa hợp lệ trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-026`; difficulty: `easy`; CQ: CQ15.

Categories: simple_filter, token_specific; entity kinds: concept_class.

Expected columns: `["normalized_transfer_count"]`; expected result size: `1`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.normalized_amount"]`.

```sql
SELECT COUNTIF(normalized_amount IS NOT NULL) AS normalized_transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `955b347de0f253a5e5cfd2267b2403c51252ed7117c1b04ccd054dd0fe3cde96`.

English case binding: `6c17cc676775542faf0675b26b2985682ea0c65f5d0aa044c124021c60183dd2`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-028

**Câu Vietnamese:** Có bao nhiêu giao dịch trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026?

English ID: `t35-028`; difficulty: `easy`; CQ: CQ01.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `eff25f9e676149e3f2f6139d7657f0c3708e2fa637389a46a59e4e8bea393872`.

English case binding: `368b732c1dfc2ce05add81b8f38e984d50169c7825db68c1cd8de5685005da7b`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-029

**Câu Vietnamese:** Có bao nhiêu giao dịch thành công trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026?

English ID: `t35-029`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["successful_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS TRUE) AS successful_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `f69d7c8e26a89614cdf41707b4a642998088e28faaf091c133fb6b33d11454c5`.

English case binding: `b2ed7deae58a57a58cd3d7c6baa90a0686f48c064a3479a2710335d63bc00db1`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-030

**Câu Vietnamese:** Có bao nhiêu giao dịch thất bại trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026?

English ID: `t35-030`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["failed_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS FALSE) AS failed_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `5ce33af838b9c68130646493fcee067176caaf69df9e1655c99492721425421b`.

English case binding: `60774dc7d61691f0e88ce39f717588a649b86b58e679d6b78ee8e886e2f6e924`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-031

**Câu Vietnamese:** Tổng giá trị wei của các giao dịch trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026 là bao nhiêu?

English ID: `t35-031`; difficulty: `easy`; CQ: CQ02.

Categories: transaction_aggregation, time_range; entity kinds: address_only.

Expected columns: `["total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.value_wei"]`.

```sql
SELECT COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `3c5679e449908e84f89ccc7b081bdb836c4e41a03c75b1fca1ff4efcdb8d4132`.

English case binding: `d85db2e42e9eef1a80ad84daeb14645fabd0cd749fef7f53c6683a892f4b0e6c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-032

**Câu Vietnamese:** Có bao nhiêu khối Ethereum trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026?

English ID: `t35-032`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["block_count"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.block_number"]`.

```sql
SELECT COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `43ff4e188813c727cb9cea8623e8920986a05ef6c5af03c374f59a9f7e31f4bb`.

English case binding: `42271b52ceb58c0551e3b5b2a1d875fd62ce77ab360644d4d3751235bc6241b7`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-033

**Câu Vietnamese:** Trung bình mỗi khối có bao nhiêu giao dịch trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026?

English ID: `t35-033`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["average_transactions_per_block"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.transaction_count"]`.

```sql
SELECT AVG(transaction_count) AS average_transactions_per_block FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `10db493bc9793323c6ffd48ab8538a09caff76a5f2f1f36f7b246bf6d1a26441`.

English case binding: `6c140c679157650a19a7aa81631def79844b1dbc37487a1302abfbc5ef64636d`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-034

**Câu Vietnamese:** Có bao nhiêu sự kiện chuyển token trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026?

English ID: `t35-034`; difficulty: `easy`; CQ: CQ15.

Categories: token_specific, time_range; entity kinds: concept_class.

Expected columns: `["token_transfer_count"]`; expected result size: `1`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS token_transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-22', DATE '2026-07-01')
```

Candidate line SHA-256 (including newline): `e91576a304f2da8a2d8893a832dbdf796f36c058a654b8cc2b5d79658258f20b`.

English case binding: `3c96f4c8eafc985483f52496461f4adcd71db08e2bc8a15974610f1c4439301b`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
