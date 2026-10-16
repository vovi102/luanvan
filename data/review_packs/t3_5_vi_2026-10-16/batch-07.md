# Vietnamese review — batch 07 (61–70)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-073

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, hãy cho biết số khối, tổng gas đã dùng và tổng số giao dịch trong các khối.

English ID: `t35-073`; difficulty: `medium`; CQ: CQ09, CQ17.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "block_count", "total_gas_used", "total_transaction_count"]`; expected result size: `7`.

Schema elements: `["block_facts", "block_facts.block_timestamp", "block_facts.gas_used", "block_facts.transaction_count"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS block_count, SUM(gas_used) AS total_gas_used, SUM(transaction_count) AS total_transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `b2c1280da8a64caa1c1f361fc13be57328c576e87bc2496bfeb6832fd46eea2b`.

English case binding: `78fd7fe5c77faec491792db4b85117e49daae8c4340155516fb8d1f13e7b9e4e`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-075

**Câu Vietnamese:** Liệt kê 10 ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-075`; difficulty: `medium`; CQ: CQ15.

Categories: token_specific, top_k; entity kinds: named_entity.

Expected columns: `["token_symbol", "total_normalized_amount"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount"]`.

```sql
SELECT token_symbol AS token_symbol, SUM(normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22') WHERE normalized_amount IS NOT NULL AND token_symbol IS NOT NULL GROUP BY token_symbol ORDER BY total_normalized_amount DESC, token_symbol ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `4363793dd626649bfc49504b785a2fa818154eb4a2bb834b9dda0ce7a3c0f049`.

English case binding: `9a95f79ff90fc1d40a5f83a23c3f5a89326332caf4d95b6fa47730dba376f3b0`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-076

**Câu Vietnamese:** Thống kê số lượt chuyển token theo chuẩn ERC-721, ERC-20 và nhóm khác hoặc chưa xác định trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-076`; difficulty: `medium`; CQ: CQ15.

Categories: class_level, comparison, token_specific; entity kinds: concept_class.

Expected columns: `["token_standard", "transfer_count"]`; expected result size: `3`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.is_erc20", "token_transfer_facts.is_erc721"]`.

```sql
SELECT CASE WHEN is_erc721 IS TRUE THEN 'erc721' WHEN is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS token_standard, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY token_standard ORDER BY token_standard ASC
```

Candidate line SHA-256 (including newline): `d0ca9c8b1a1ced8978bd6adaa9468228f61d2f6264d02f5d9b86e23a0510d66c`.

English case binding: `1fb144afd67ae49fcd6a30179932b42fef722ff3c98d91caa33393dd446a6871`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-077

**Câu Vietnamese:** Liệt kê 10 địa chỉ gửi token có nhiều lượt chuyển nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-077`; difficulty: `medium`; CQ: CQ14.

Categories: top_k, token_specific; entity kinds: address_only.

Expected columns: `["sender_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.from_address"]`.

```sql
SELECT from_address AS sender_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22') WHERE from_address IS NOT NULL GROUP BY from_address ORDER BY transfer_count DESC, sender_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `d51b03705a34be082a1bf885b4b23382958147108e2df4784f11dc717fac8127`.

English case binding: `ad37e41cd9656ec2c01c171df7e4811fcd719bedce1b23ab1e01e781a1567098`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-078

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận token có nhiều lượt chuyển nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-078`; difficulty: `medium`; CQ: CQ14.

Categories: top_k, token_specific; entity kinds: address_only.

Expected columns: `["recipient_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transfer_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `65c221fe44c3e45b4c2982f1960515395b381b4641fa9441313a41c023c8dd37`.

English case binding: `e4e3e7dea7d8bf668f8ba555050b3e1f764921ff9c480e8f7216cc62e33630e3`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-079

**Câu Vietnamese:** Thống kê số giao dịch theo từng loại giao dịch trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-079`; difficulty: `medium`; CQ: CQ01.

Categories: class_level, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["transaction_type", "transaction_count"]`; expected result size: `5`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_type"]`.

```sql
SELECT transaction_type AS transaction_type, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY transaction_type ORDER BY transaction_count DESC, transaction_type ASC
```

Candidate line SHA-256 (including newline): `89f6454e5bffdbdc5e55fdf22682db1384e47a09458b9a8f66a7a0232c249012`.

English case binding: `dfd6b6abcd70481aa4d673bef896f55afa2c0bb02bb44e391ff889245a007912`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-080

**Câu Vietnamese:** Liệt kê 10 địa chỉ hợp đồng được tạo có giá trị giao dịch wei lớn nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-080`; difficulty: `medium`; CQ: CQ02, CQ18.

Categories: top_k, simple_filter; entity kinds: address_only.

Expected columns: `["created_contract_address", "transaction_value_wei"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.receipt_contract_address", "transaction_facts.value_wei"]`.

```sql
SELECT receipt_contract_address AS created_contract_address, value_wei AS transaction_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') WHERE receipt_contract_address IS NOT NULL ORDER BY transaction_value_wei DESC, created_contract_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `8d218072fae169918ff36b9fd8d18702858fafce25f86c02149d17fa7e882e6b`.

English case binding: `6b51e1f8ff7a1d1f9eb765179e9214e98309399f5685ed240bf8b0e227f90509`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-081

**Câu Vietnamese:** Liệt kê 10 lớp khái niệm của bên nhận có nhiều giao dịch nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, kèm số giao dịch.

English ID: `t35-081`; difficulty: `medium`; CQ: CQ13, CQ22.

Categories: class_level, multi_hop, transaction_aggregation; entity kinds: named_entity.

Expected columns: `["recipient_concept_class", "transaction_count"]`; expected result size: `6`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS recipient_concept_class, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.to_address = labels.address GROUP BY recipient_concept_class ORDER BY transaction_count DESC, recipient_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `a73c878ed920eb2e7408e3d62d8e210db5ea20f0d6a0f4b5fbbf8d06fef3eb5a`.

English case binding: `af8256ec63b659eaf0411a0366f93017f644ce95f12873a2db18c04796bff585`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-082

**Câu Vietnamese:** Liệt kê 10 địa chỉ gửi có nhiều giao dịch nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-082`; difficulty: `medium`; CQ: CQ04.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["sender_address", "transaction_count"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.from_address"]`.

```sql
SELECT from_address AS sender_address, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY from_address ORDER BY transaction_count DESC, sender_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `a7c010d7e26148614a47ad002944b034b515aff75882178d59a4e31e2635ec45`.

English case binding: `72c22c4711e627e2f15e9493f2a1db6607321c093d4fcdf6eca925cb134af8d9`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-083

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận có nhiều giao dịch nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-083`; difficulty: `medium`; CQ: CQ05.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["recipient_address", "transaction_count"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transaction_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `e48b2669970d00c8f158828b34f2de0a7283e23765c58b62ee756507c5192e7b`.

English case binding: `af79323e7b9831148c1a659469a854f95b4a1911cc0f0e1100cdc60b7a66b8ea`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
