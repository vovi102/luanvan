# Vietnamese review — batch 01 (1–10)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-001

**Câu Vietnamese:** Có bao nhiêu giao dịch trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-001`; difficulty: `easy`; CQ: CQ01.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `7e3f5abc7f6003582cd17ef622645974af265d1c96df4ed2e79c80c23f4b053f`.

English case binding: `1b63ae92ff540dfad7eeb3d8ab7da5417f5fae357089e227127bf626565526f2`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-002

**Câu Vietnamese:** Có bao nhiêu giao dịch thành công trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-002`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["successful_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS TRUE) AS successful_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `f22678be2288a638aa163e8b66138fd4074ee46488f66757d7128500d95afcd4`.

English case binding: `f738734b00a569fdc311cda1cc779b91ac6bb3ed2952435a521a262a21ae726e`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-003

**Câu Vietnamese:** Có bao nhiêu giao dịch thất bại trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-003`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["failed_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS FALSE) AS failed_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `8a1e7c6943e925530d5819fec9b4459afde339fdd38bf3b2e332c7cf646c0108`.

English case binding: `0e21e7998c2c6cf51e107d6ebcb45aa1bc7653be1ac1fe0fb86029e1986d4809`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-004

**Câu Vietnamese:** Tổng giá trị wei của các giao dịch trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026 là bao nhiêu?

English ID: `t35-004`; difficulty: `easy`; CQ: CQ02.

Categories: transaction_aggregation, time_range; entity kinds: address_only.

Expected columns: `["total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.value_wei"]`.

```sql
SELECT COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `32363e02fe8caed6c62cdfb0c80ef4a12632ad93e63b74b1583a6df7b657e529`.

English case binding: `a67dc5baa049c0fc2b603128cf8ce7c04115f5ad63463c590514b60679e9c3ec`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-005

**Câu Vietnamese:** Có bao nhiêu khối Ethereum trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-005`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["block_count"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.block_number"]`.

```sql
SELECT COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `6f3f51f3a534cc2c3731a6a78fa1d0df09ea312157112b4aff37fceb666ce02f`.

English case binding: `ef8d0eb7ca23f53132d6f4be397f2f32f39f2ac517b620acbd19e82705489b89`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-006

**Câu Vietnamese:** Trung bình mỗi khối có bao nhiêu giao dịch trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-006`; difficulty: `easy`; CQ: CQ09.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["average_transactions_per_block"]`; expected result size: `1`.

Schema elements: `["block_facts", "block_facts.transaction_count"]`.

```sql
SELECT AVG(transaction_count) AS average_transactions_per_block FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `0fc0fffc9b107614f451ca4e42711212de55a643508cce192214927b97e97536`.

English case binding: `38d5c4962503cf8567920f127ab09b2cff2895f1df6e5830e2443eda44c497cc`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-007

**Câu Vietnamese:** Có bao nhiêu sự kiện chuyển token trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-007`; difficulty: `easy`; CQ: CQ15.

Categories: token_specific, time_range; entity kinds: concept_class.

Expected columns: `["token_transfer_count"]`; expected result size: `1`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS token_transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `29c41047196d45c5f7fb1735f97b0d31dce0812a22c2dea89c82e8c79812d90c`.

English case binding: `fc0610427d04621b7a8011c0ee63da43ee6439106e502da84bbc1a1d8ee4adb1`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-008

**Câu Vietnamese:** Có bao nhiêu lượt chuyển token có lượng chuẩn hóa hợp lệ trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026?

English ID: `t35-008`; difficulty: `easy`; CQ: CQ15.

Categories: simple_filter, token_specific; entity kinds: concept_class.

Expected columns: `["normalized_transfer_count"]`; expected result size: `1`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.normalized_amount"]`.

```sql
SELECT COUNTIF(normalized_amount IS NOT NULL) AS normalized_transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08')
```

Candidate line SHA-256 (including newline): `84ce9aad79c7c507176fb7f460ce4cc9a64ba1023ee19a960ba4a1545f37882f`.

English case binding: `d9f35b9a44876972461528e4cb55bb998b00651ad48b70dd97e92d102b0b08fc`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-010

**Câu Vietnamese:** Có bao nhiêu giao dịch trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026?

English ID: `t35-010`; difficulty: `easy`; CQ: CQ01.

Categories: transaction_aggregation, time_range; entity kinds: concept_class.

Expected columns: `["transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_hash"]`.

```sql
SELECT COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `a6c8526ee7ca9795b521f8fa5760a9bf3b1dddbb9f31d8b61bdb68b988e76599`.

English case binding: `b77ba30c4701b7902be3e44e528d1266290f926d6de454af84ed7ce685426d61`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-011

**Câu Vietnamese:** Có bao nhiêu giao dịch thành công trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026?

English ID: `t35-011`; difficulty: `easy`; CQ: CQ03.

Categories: simple_filter, time_range; entity kinds: concept_class.

Expected columns: `["successful_transaction_count"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.is_success"]`.

```sql
SELECT COUNTIF(is_success IS TRUE) AS successful_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15')
```

Candidate line SHA-256 (including newline): `035dbe47be6f805ac99cf606d633989b5554c03c45fcc50f8f4d0bdb0f0838e2`.

English case binding: `df200da8b6d4bd1fbacf7f6aa4347b7166fa895c02f96537e4633d66c8c3a26c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
