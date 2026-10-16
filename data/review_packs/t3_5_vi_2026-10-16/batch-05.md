# Vietnamese review — batch 05 (41–50)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-049

**Câu Vietnamese:** Thống kê số giao dịch theo từng loại giao dịch trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-049`; difficulty: `medium`; CQ: CQ01.

Categories: class_level, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["transaction_type", "transaction_count"]`; expected result size: `5`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_type"]`.

```sql
SELECT transaction_type AS transaction_type, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY transaction_type ORDER BY transaction_count DESC, transaction_type ASC
```

Candidate line SHA-256 (including newline): `b1be4c3ff24b04624825b0605eb09dacee741d5220b6b5ffa4040453ad0e9db9`.

English case binding: `281f6df96221b40fd433e91d21cdd31596d026f62d589263b16eee7e0752a82a`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-050

**Câu Vietnamese:** Liệt kê 10 địa chỉ hợp đồng được tạo có giá trị giao dịch wei lớn nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-050`; difficulty: `medium`; CQ: CQ02, CQ18.

Categories: top_k, simple_filter; entity kinds: address_only.

Expected columns: `["created_contract_address", "transaction_value_wei"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.receipt_contract_address", "transaction_facts.value_wei"]`.

```sql
SELECT receipt_contract_address AS created_contract_address, value_wei AS transaction_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') WHERE receipt_contract_address IS NOT NULL ORDER BY transaction_value_wei DESC, created_contract_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `d6992dc238f84dc7a4dd7e6011f5da65f5a2f6a138c1445d70961802e19f9a4a`.

English case binding: `e11f62e956e46bc0376e2f72006de176521070df6c95bed762a0e11a4bd79115`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-051

**Câu Vietnamese:** Liệt kê 10 lớp khái niệm của bên nhận có nhiều giao dịch nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, kèm số giao dịch.

English ID: `t35-051`; difficulty: `medium`; CQ: CQ13, CQ22.

Categories: class_level, multi_hop, transaction_aggregation; entity kinds: named_entity.

Expected columns: `["recipient_concept_class", "transaction_count"]`; expected result size: `6`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS recipient_concept_class, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.to_address = labels.address GROUP BY recipient_concept_class ORDER BY transaction_count DESC, recipient_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `61994d4b8fc169f08eca799c6c2f30e0c7c7421a4d5ad57a53357f8c9523eb58`.

English case binding: `a80fed1eb22ef8c5aad23b151de45f86d61fa73c717299e01f0d236bba12ed4b`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-052

**Câu Vietnamese:** Liệt kê 10 địa chỉ gửi có nhiều giao dịch nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-052`; difficulty: `medium`; CQ: CQ04.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["sender_address", "transaction_count"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.from_address"]`.

```sql
SELECT from_address AS sender_address, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY from_address ORDER BY transaction_count DESC, sender_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `6acd5dd9dcae5d6f3b80cab4541601fb41ac44247832ddef7ca6e46e3466df6f`.

English case binding: `5b9baf8427e2af87ce9bf25686ef4937b289053cec229668cac0760a0257b7bf`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-053

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận có nhiều giao dịch nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-053`; difficulty: `medium`; CQ: CQ05.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["recipient_address", "transaction_count"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transaction_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `a6e8ea94a3c0d7b4f46f9cbb9f7db35374f9a78ff8a35dd776dd95de0df78529`.

English case binding: `119f38aa96909210bdf0de8d02b94e987a3d70d198c398e7478dfefaad002795`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-055

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026, có bao nhiêu giao dịch thành công và thất bại?

English ID: `t35-055`; difficulty: `medium`; CQ: CQ03, CQ16.

Categories: comparison, temporal_pattern; entity kinds: concept_class.

Expected columns: `["activity_date", "successful_count", "failed_count"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.is_success"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNTIF(is_success IS TRUE) AS successful_count, COUNTIF(is_success IS FALSE) AS failed_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `9150b15ca78e01ceb816e350f0ff295b98286cef6f52fc97daa59be8ac0c9a5f`.

English case binding: `747603625aef91ca35e333c00f8ad0c6ccb46aa1d8a72e7b9179e62ecb03c35c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-056

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026, giá gas trung bình theo wei và lượng gas biên lai trung bình là bao nhiêu?

English ID: `t35-056`; difficulty: `medium`; CQ: CQ16.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "average_gas_price_wei", "average_receipt_gas_used"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.gas_price_wei", "transaction_facts.receipt_gas_used"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, AVG(gas_price_wei) AS average_gas_price_wei, AVG(receipt_gas_used) AS average_receipt_gas_used FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `ff444b8af36c5f29f7fbe924013ed8082280fe47df64f4e162f143e465bee706`.

English case binding: `15e44774124ba67c311ec4627728a90ce330a6188356769db184754d26265652`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-058

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026, hãy cho biết số khối, tổng gas đã dùng và tổng số giao dịch trong các khối.

English ID: `t35-058`; difficulty: `medium`; CQ: CQ09, CQ17.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "block_count", "total_gas_used", "total_transaction_count"]`; expected result size: `7`.

Schema elements: `["block_facts", "block_facts.block_timestamp", "block_facts.gas_used", "block_facts.transaction_count"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS block_count, SUM(gas_used) AS total_gas_used, SUM(transaction_count) AS total_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `9df95c850e7db122bb3b962ab2d0c06d1d6167a4ea664d0e0739e4a2d890b980`.

English case binding: `dffb78a177f3666e8723bf235ea371c86da713e74ae26ded2e87846f3e75b022`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-059

**Câu Vietnamese:** Liệt kê 10 địa chỉ token có nhiều lượt chuyển nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-059`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: address_only.

Expected columns: `["token_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_address"]`.

```sql
SELECT token_address AS token_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY token_address ORDER BY transfer_count DESC, token_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `9313636f0b115f52952e36ed6b90b29925a67caeac51cf601fa5b21291cb3234`.

English case binding: `3eff6c0f9dc62ba1b0e24c1c0e57e6ac10d66e0acf4ea5196ee22eadc04be678`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-060

**Câu Vietnamese:** Liệt kê 10 ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-060`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: named_entity.

Expected columns: `["token_symbol", "total_normalized_amount"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount"]`.

```sql
SELECT token_symbol AS token_symbol, SUM(normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15') WHERE normalized_amount IS NOT NULL AND token_symbol IS NOT NULL GROUP BY token_symbol ORDER BY total_normalized_amount DESC, token_symbol ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `bdf7d1d60edc942b4727b990787de79e82518e1232c5bde26a099ab6750e6201`.

English case binding: `fec05d227d2381c4ffc27e51140292ca60ac432b7e75fd45d4eb42903eb75302`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
