# Vietnamese review — batch 04 (31–40)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-039

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, có bao nhiêu giao dịch?

English ID: `t35-039`; difficulty: `medium`; CQ: CQ01.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "transaction_count"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `a1c78589d11725af2a045920b01563d62f483e8f83dfb4866881e73fa4194a91`.

English case binding: `e2da03bfa61abd482f5a53bd179a7fc478d1c164bc7b51b43d18562c4c404e4b`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-040

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, có bao nhiêu giao dịch thành công và thất bại?

English ID: `t35-040`; difficulty: `medium`; CQ: CQ03, CQ16.

Categories: comparison, temporal_pattern; entity kinds: concept_class.

Expected columns: `["activity_date", "successful_count", "failed_count"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.is_success"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNTIF(is_success IS TRUE) AS successful_count, COUNTIF(is_success IS FALSE) AS failed_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `1786c706fd9c195041d5f87e7310b429cce56554ca79ffd95aa0ec3a8429c713`.

English case binding: `db79a13309a775715e43f0f97feb6987a33e42e3dc65f4a69e0b23bb9eb9b70c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-041

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, giá gas trung bình theo wei và lượng gas biên lai trung bình là bao nhiêu?

English ID: `t35-041`; difficulty: `medium`; CQ: CQ16.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "average_gas_price_wei", "average_receipt_gas_used"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.gas_price_wei", "transaction_facts.receipt_gas_used"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, AVG(gas_price_wei) AS average_gas_price_wei, AVG(receipt_gas_used) AS average_receipt_gas_used FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `b97e471e751ce1925ca36d189dac86716bd6ca4d8095febb60f6afcb7c97daaf`.

English case binding: `d68b5c4e1e28db0784dbce7dfd4597706595824d2484ae6a8b4fd296126e3533`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-042

**Câu Vietnamese:** Liệt kê 10 địa chỉ thụ hưởng đã tạo nhiều khối nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-042`; difficulty: `medium`; CQ: CQ17.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["beneficiary_address", "block_count"]`; expected result size: `10`.

Schema elements: `["block_facts", "block_facts.beneficiary_address"]`.

```sql
SELECT beneficiary_address AS beneficiary_address, COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-01', DATE '2026-06-08') WHERE beneficiary_address IS NOT NULL GROUP BY beneficiary_address ORDER BY block_count DESC, beneficiary_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `f2c17caa81edfd8d1aac2d0b0a9103accd9ff204974cae71f66144c430f593eb`.

English case binding: `fe8fd4be9723007b4068d71d52b8af85dbc6957b0911f043e2ba0399f6561a1b`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-043

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, hãy cho biết số khối, tổng gas đã dùng và tổng số giao dịch trong các khối.

English ID: `t35-043`; difficulty: `medium`; CQ: CQ09, CQ17.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "block_count", "total_gas_used", "total_transaction_count"]`; expected result size: `7`.

Schema elements: `["block_facts", "block_facts.block_timestamp", "block_facts.gas_used", "block_facts.transaction_count"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS block_count, SUM(gas_used) AS total_gas_used, SUM(transaction_count) AS total_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `e1785f94163b56936b14a3519e6e262568a34148c41406f309216c0b016e172b`.

English case binding: `e1cb27f3c8fdb77f8444ddbfa8b14c712b6c1c24972042fcac824e6a92522285`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-044

**Câu Vietnamese:** Liệt kê 10 địa chỉ token có nhiều lượt chuyển nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-044`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: address_only.

Expected columns: `["token_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_address"]`.

```sql
SELECT token_address AS token_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY token_address ORDER BY transfer_count DESC, token_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `180102a2607d0300fcfae9356a318196f6ea61309ba0fc96a1710c9467e999a6`.

English case binding: `ec7a467facc71f335f65ac1e2e955b3b859ca41b6dce1866e0af66e359fc8766`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-045

**Câu Vietnamese:** Liệt kê 10 ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-045`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: named_entity.

Expected columns: `["token_symbol", "total_normalized_amount"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount"]`.

```sql
SELECT token_symbol AS token_symbol, SUM(normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') WHERE normalized_amount IS NOT NULL AND token_symbol IS NOT NULL GROUP BY token_symbol ORDER BY total_normalized_amount DESC, token_symbol ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `4a705580c043a28aa34ff7073311e168ec105aeb61676564959fc7d75f569df3`.

English case binding: `6f556c0b0b7928c75743000bde7d099f820726336e80b6b00fa53780ba732ef8`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-046

**Câu Vietnamese:** Thống kê số lượt chuyển token theo chuẩn ERC-721, ERC-20 và nhóm khác hoặc chưa xác định trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-046`; difficulty: `medium`; CQ: CQ15.

Categories: class_level, comparison, token_specific; entity kinds: concept_class.

Expected columns: `["token_standard", "transfer_count"]`; expected result size: `3`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.is_erc20", "token_transfer_facts.is_erc721"]`.

```sql
SELECT CASE WHEN is_erc721 IS TRUE THEN 'erc721' WHEN is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS token_standard, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY token_standard ORDER BY token_standard ASC
```

Candidate line SHA-256 (including newline): `7b0d11f33611b97a3798b249c52ec6e9ee117fef149397747d2ad8952dade31b`.

English case binding: `66a34f5ce2c2ba42de108eecdbaaf148a2d049f5dafbaeb874fb9cb38c624a15`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-047

**Câu Vietnamese:** Liệt kê 10 địa chỉ gửi token có nhiều lượt chuyển nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-047`; difficulty: `medium`; CQ: CQ14.

Categories: top_k, token_specific; entity kinds: address_only.

Expected columns: `["sender_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.from_address"]`.

```sql
SELECT from_address AS sender_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') WHERE from_address IS NOT NULL GROUP BY from_address ORDER BY transfer_count DESC, sender_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `60fe9bd7d7c5af29380919d286ae28a1a200515d0f94e8ec23d91e1070574463`.

English case binding: `24b869ace8766ec35442eade8aca87a71a4d38fd89cee5e0f130f6fc56e90f79`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-048

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận token có nhiều lượt chuyển nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-048`; difficulty: `medium`; CQ: CQ14.

Categories: top_k, token_specific; entity kinds: address_only.

Expected columns: `["recipient_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transfer_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `8df650cd5282b9b9ae8b473bc591c98511d9aada8b55aa5132f2c90e46b43f3b`.

English case binding: `967a2d24f96724695da08654b4730da8408f7c53709fd1b25643600b29410ad8`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
