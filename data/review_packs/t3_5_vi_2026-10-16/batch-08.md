# Vietnamese review — batch 08 (71–80)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-084

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026, có bao nhiêu giao dịch?

English ID: `t35-084`; difficulty: `medium`; CQ: CQ01.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "transaction_count"]`; expected result size: `9`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `cef200eec892bd726e8ca823516d021cd59b7086162dced502dd0d46e00775d6`.

English case binding: `3ead44e84c119d0688495ef711b1d5968064c6246ec7281dfa5bd5838ce70734`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-086

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026, giá gas trung bình theo wei và lượng gas biên lai trung bình là bao nhiêu?

English ID: `t35-086`; difficulty: `medium`; CQ: CQ16.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "average_gas_price_wei", "average_receipt_gas_used"]`; expected result size: `9`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.gas_price_wei", "transaction_facts.receipt_gas_used"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, AVG(gas_price_wei) AS average_gas_price_wei, AVG(receipt_gas_used) AS average_receipt_gas_used FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `718bea487c580632a89935181372da03cb935e73a75994f272acef775d969f05`.

English case binding: `d9a5b62bed8c07a214c0c021a3b2c1d59cfe07336284dc72f95c6a1bef5cc5c6`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-087

**Câu Vietnamese:** Liệt kê 10 địa chỉ thụ hưởng đã tạo nhiều khối nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-087`; difficulty: `medium`; CQ: CQ17.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["beneficiary_address", "block_count"]`; expected result size: `10`.

Schema elements: `["block_facts", "block_facts.beneficiary_address"]`.

```sql
SELECT beneficiary_address AS beneficiary_address, COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-22', DATE '2026-07-01') WHERE beneficiary_address IS NOT NULL GROUP BY beneficiary_address ORDER BY block_count DESC, beneficiary_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `25643747f9b936f31dca439491ab99aad326ae437370228d0d9914071312d41d`.

English case binding: `1a8c336f2d5caba3f5d8ae1567c67df185740212f2067c74edff37e96ccb2f3b`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-088

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026, hãy cho biết số khối, tổng gas đã dùng và tổng số giao dịch trong các khối.

English ID: `t35-088`; difficulty: `medium`; CQ: CQ09, CQ17.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "block_count", "total_gas_used", "total_transaction_count"]`; expected result size: `9`.

Schema elements: `["block_facts", "block_facts.block_timestamp", "block_facts.gas_used", "block_facts.transaction_count"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS block_count, SUM(gas_used) AS total_gas_used, SUM(transaction_count) AS total_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `557c2b5ed818e3c01f989171155cf458fbff331d1f617739e06aad3a931840d9`.

English case binding: `f73a5c0e3dfbd752c918fba2001913210217eedbe91c759b22f9cdd8f4170d60`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-089

**Câu Vietnamese:** Liệt kê 10 địa chỉ token có nhiều lượt chuyển nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-089`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: address_only.

Expected columns: `["token_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_address"]`.

```sql
SELECT token_address AS token_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY token_address ORDER BY transfer_count DESC, token_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `88de8fa71e5d7d3aa33b9ed258574d466015ae32a12907ac4f15a7f1b0ab0339`.

English case binding: `5fc98677e6a7c4ad45c1331902a34a951f6307f3daa1288de00c4a29145f9b44`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-090

**Câu Vietnamese:** Liệt kê 10 ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-090`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: named_entity.

Expected columns: `["token_symbol", "total_normalized_amount"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount"]`.

```sql
SELECT token_symbol AS token_symbol, SUM(normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-22', DATE '2026-07-01') WHERE normalized_amount IS NOT NULL AND token_symbol IS NOT NULL GROUP BY token_symbol ORDER BY total_normalized_amount DESC, token_symbol ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `ebea4d077492f7013361dc2d92f4062a3e8459a29d590c2cc4952a5fc57ebe23`.

English case binding: `47c873336006fc3f844ac7efe1036b1aabbb9c765a0b4959d982691d4f161c97`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-091

**Câu Vietnamese:** Thống kê số lượt chuyển token theo chuẩn ERC-721, ERC-20 và nhóm khác hoặc chưa xác định trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-091`; difficulty: `medium`; CQ: CQ15.

Categories: class_level, comparison, token_specific; entity kinds: concept_class.

Expected columns: `["token_standard", "transfer_count"]`; expected result size: `3`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.is_erc20", "token_transfer_facts.is_erc721"]`.

```sql
SELECT CASE WHEN is_erc721 IS TRUE THEN 'erc721' WHEN is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS token_standard, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY token_standard ORDER BY token_standard ASC
```

Candidate line SHA-256 (including newline): `a916dc41f4b73a522c1b839fe40e7d02b1ca8045688d293e9c1fd135bbc98736`.

English case binding: `869c2ea06d77b2b4a48805f8b4191f760c789858c2851184fb46cdc696d53351`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-093

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận token có nhiều lượt chuyển nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-093`; difficulty: `medium`; CQ: CQ14.

Categories: top_k, token_specific; entity kinds: address_only.

Expected columns: `["recipient_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-22', DATE '2026-07-01') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transfer_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `aeb7d359ee4f92164d987822f62f124d95bd607e5efcfed209f71a6fdfd3751f`.

English case binding: `7cc00476e6f42a1bf125b0624ac49ca568cec4d06ac37ab8af42a60046fe184d`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-094

**Câu Vietnamese:** Thống kê số giao dịch theo từng loại giao dịch trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-094`; difficulty: `medium`; CQ: CQ01.

Categories: class_level, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["transaction_type", "transaction_count"]`; expected result size: `5`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_type"]`.

```sql
SELECT transaction_type AS transaction_type, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY transaction_type ORDER BY transaction_count DESC, transaction_type ASC
```

Candidate line SHA-256 (including newline): `4c68af24d168d0e261634932a09be0fb0fad4139c58abd74fb259f7c5626e4c8`.

English case binding: `13cfae59535c56cbd58ed45faf61e1c59f8d740dd02bdb637e9fc2812215aa58`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-096

**Câu Vietnamese:** Liệt kê 10 lớp khái niệm của bên nhận có nhiều giao dịch nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026, kèm số giao dịch.

English ID: `t35-096`; difficulty: `medium`; CQ: CQ13, CQ22.

Categories: class_level, multi_hop, transaction_aggregation; entity kinds: named_entity.

Expected columns: `["recipient_concept_class", "transaction_count"]`; expected result size: `6`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS recipient_concept_class, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.to_address = labels.address GROUP BY recipient_concept_class ORDER BY transaction_count DESC, recipient_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `c8afe3f3ddccf75a3abb540a370f6b58dcfa0a7dce4c92b85326ea437b756542`.

English case binding: `fa9019fdfab5fa1b2aecee920b591003ff5c2f97882b81a86bcb9ec647d6f597`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
