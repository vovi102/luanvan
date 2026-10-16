# Vietnamese review — batch 02 (11–20)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-012

**Câu Vietnamese:** Có bao nhiêu giao dịch thất bại trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026?

English ID: `t35-012`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["failed_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS FALSE) AS failed_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `fed45d244dcdd66f5b512292a923c0eb45bd1beccaf83824467fafed78d94671`.

English case binding: `2d2ae92c3073c678e3e69553f00e43d2155d3a37a2c13a28a39bf680bc769256`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-013

**Câu Vietnamese:** Tổng giá trị wei của các giao dịch trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026 là bao nhiêu?

English ID: `t35-013`; difficulty: `easy`; CQ: CQ02.

Categories: transaction_aggregation, time_range; entity kinds: address_only.

Expected columns: `["total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.value_wei"]`.

```sql
SELECT COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `595cbaafb1fde421951f2f80f0aca91b40b7ffed38d9419809d950d735e61d3d`.

English case binding: `796426da200b4430f4185be03a4e3a0127855987f45dd41ad325355bd08fb312`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-014

**Câu Vietnamese:** Có bao nhiêu khối Ethereum trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026?

English ID: `t35-014`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["block_count"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.block_number"]`.

```sql
SELECT COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `a0f786a29e500c64c222141ff48228155c0534f23e0fe6bcdf03a7ffe2cf9fb8`.

English case binding: `990c95536b0040e509fc9a921db25ce250be1008d571f5c81cf4b2cd85e7f8dc`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-015

**Câu Vietnamese:** Trung bình mỗi khối có bao nhiêu giao dịch trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026?

English ID: `t35-015`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["average_transactions_per_block"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.transaction_count"]`.

```sql
SELECT AVG(transaction_count) AS average_transactions_per_block FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `5853c87c15f25d968d679502899070bfa59ae5bf659546eaee46d1e54c7222ba`.

English case binding: `c29b451081da7b43b6319d84ab909b1864d50e8aa3434138bd0aea68698761c1`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-016

**Câu Vietnamese:** Có bao nhiêu sự kiện chuyển token trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026?

English ID: `t35-016`; difficulty: `easy`; CQ: CQ15.

Categories: token_specific, time_range; entity kinds: concept_class.

Expected columns: `["token_transfer_count"]`; expected result size: `1`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS token_transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `6f49baa18aca5603a7c5c59817a4dc4a0dce9168a62807ab5f2d2ce7b0fbe5a0`.

English case binding: `5a6bd183e02e23cabf5e1343e91e358bdfbb051416710d916715a0398e1b82cf`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-019

**Câu Vietnamese:** Có bao nhiêu giao dịch trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-019`; difficulty: `easy`; CQ: CQ01.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `0fc1529831ced280523a990b5800bade7ef9ab2ae1cccf511c515237d2a2878d`.

English case binding: `5c436d4641d316ae080eaa1245296ba0491411310cd7cb1fae3fa8fdfb1fb46c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-020

**Câu Vietnamese:** Có bao nhiêu giao dịch thành công trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-020`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["successful_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS TRUE) AS successful_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `20b7e8be1c161c5f345f5e08588b21e0bd32477d7b8b53cce8f5ebd5aca117de`.

English case binding: `18fabd756c8cef8a9580e07001674dec59860b2075ffe48c27577acfa9ad6e2f`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-021

**Câu Vietnamese:** Có bao nhiêu giao dịch thất bại trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-021`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["failed_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS FALSE) AS failed_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `81aa612995e9677f39d21c7ffc97eca3dbc9f3c9e4bbfc54847b178f99c965b2`.

English case binding: `6874131ce3ba003901cef0060d5399648935e671af3c036f0358b5af7dd4acef`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-022

**Câu Vietnamese:** Tổng giá trị wei của các giao dịch trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026 là bao nhiêu?

English ID: `t35-022`; difficulty: `easy`; CQ: CQ02.

Categories: transaction_aggregation, time_range; entity kinds: address_only.

Expected columns: `["total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.value_wei"]`.

```sql
SELECT COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `899b8ad6542eb76fa46c8291af49f56da2b9b981e12fc539569be3cf525a0786`.

English case binding: `9c0f1c44e01e802dc046ffbefc70d18f386992184539d02fcfbc52ae63c426d5`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-023

**Câu Vietnamese:** Có bao nhiêu khối Ethereum trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026?

English ID: `t35-023`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["block_count"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.block_number"]`.

```sql
SELECT COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-15', DATE '2026-06-22')
```

Candidate line SHA-256 (including newline): `bd3503a70b61579e1db62340958f73005cdd405d6898518406bddc5a3b6077de`.

English case binding: `194525f1c6e4883a3499aff6305215ff9a941089e259f187c940178d8d13a756`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
