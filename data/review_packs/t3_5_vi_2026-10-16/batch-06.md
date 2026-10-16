# Vietnamese review — batch 06 (51–60)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-061

**Câu Vietnamese:** Thống kê số lượt chuyển token theo chuẩn ERC-721, ERC-20 và nhóm khác hoặc chưa xác định trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-061`; difficulty: `medium`; CQ: CQ15.

Categories: class_level, comparison, token_specific; entity kinds: concept_class.

Expected columns: `["token_standard", "transfer_count"]`; expected result size: `3`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.is_erc20", "token_transfer_facts.is_erc721"]`.

```sql
SELECT CASE WHEN is_erc721 IS TRUE THEN 'erc721' WHEN is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS token_standard, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY token_standard ORDER BY token_standard ASC
```

Candidate line SHA-256 (including newline): `a05604bbc1192bd3c885cf073edb1f8390c6af856936176dd06ec5374676f4c8`.

English case binding: `52615b2c9f2c9cbf456c2a19d6a6c13f853fa9b9fcabf916f3b6048b3f3da12c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-063

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận token có nhiều lượt chuyển nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-063`; difficulty: `medium`; CQ: CQ14.

Categories: top_k, token_specific; entity kinds: address_only.

Expected columns: `["recipient_address", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transfer_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `2b6f1a26f5386966a75fa8e1b5bfa6f0afb0f8d223b98e718335c6460b39b2cd`.

English case binding: `481be765b7e0d8f93415888ebe8dad433e6affe1a64344decfccae0f0f3eccf7`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-064

**Câu Vietnamese:** Thống kê số giao dịch theo từng loại giao dịch trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-064`; difficulty: `medium`; CQ: CQ01.

Categories: class_level, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["transaction_type", "transaction_count"]`; expected result size: `5`.

Schema elements: `["transaction_facts", "transaction_facts.transaction_type"]`.

```sql
SELECT transaction_type AS transaction_type, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY transaction_type ORDER BY transaction_count DESC, transaction_type ASC
```

Candidate line SHA-256 (including newline): `e3f36bceef5f1e1d9eaa07e41d888f252a8012913e2ec5dd9d79fdec999ecdd3`.

English case binding: `dcc426deabbcf3f300ae12adc4da6827e74ea004dffb88f16dc5b9a00faffbeb`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-065

**Câu Vietnamese:** Liệt kê 10 địa chỉ hợp đồng được tạo có giá trị giao dịch wei lớn nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-065`; difficulty: `medium`; CQ: CQ02, CQ18.

Categories: top_k, simple_filter; entity kinds: address_only.

Expected columns: `["created_contract_address", "transaction_value_wei"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.receipt_contract_address", "transaction_facts.value_wei"]`.

```sql
SELECT receipt_contract_address AS created_contract_address, value_wei AS transaction_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') WHERE receipt_contract_address IS NOT NULL ORDER BY transaction_value_wei DESC, created_contract_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `683c58d2a1e65fda24f5feeba2d080875d6962d6b21d5821a90d9890d64b169a`.

English case binding: `dc4cd6c37d9768ac1d71decfdb967dd32d450cf53666d5892d7d8fff684ba046`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-066

**Câu Vietnamese:** Liệt kê 10 lớp khái niệm của bên nhận có nhiều giao dịch nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026, kèm số giao dịch.

English ID: `t35-066`; difficulty: `medium`; CQ: CQ13, CQ22.

Categories: class_level, multi_hop, transaction_aggregation; entity kinds: named_entity.

Expected columns: `["recipient_concept_class", "transaction_count"]`; expected result size: `6`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS recipient_concept_class, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.to_address = labels.address GROUP BY recipient_concept_class ORDER BY transaction_count DESC, recipient_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `46f29aa809521473b9dafafe70a52fe3f39c393e3cfa6c1c1e88f18362141a96`.

English case binding: `bda7f52c2aaa31da292140630dc84600f2ab3b97381df2943dbe3b1503eeca24`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-067

**Câu Vietnamese:** Liệt kê 10 địa chỉ gửi có nhiều giao dịch nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-067`; difficulty: `medium`; CQ: CQ04.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["sender_address", "transaction_count"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.from_address"]`.

```sql
SELECT from_address AS sender_address, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY from_address ORDER BY transaction_count DESC, sender_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `7b802bb7d036ebcef322ee08027482b72fbbacd0dd0e5b4965b34982af343fab`.

English case binding: `af074215e7b8dde00aa90c148d9ee6cf39045173cbfb5c1943b0461ad190e650`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-068

**Câu Vietnamese:** Liệt kê 10 địa chỉ nhận có nhiều giao dịch nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-068`; difficulty: `medium`; CQ: CQ05.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["recipient_address", "transaction_count"]`; expected result size: `10`.

Schema elements: `["transaction_facts", "transaction_facts.to_address"]`.

```sql
SELECT to_address AS recipient_address, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') WHERE to_address IS NOT NULL GROUP BY to_address ORDER BY transaction_count DESC, recipient_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `2a57bc815d45628d18d9034dd4d3e230ae1cab9eb2547c8a969deca3fecc8312`.

English case binding: `cc0d34a73f945f0154c8796a5f333d69a3c7282de9f1d5fbeae4f19628dac47a`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-069

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, có bao nhiêu giao dịch?

English ID: `t35-069`; difficulty: `medium`; CQ: CQ01.

Categories: temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["activity_date", "transaction_count"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS transaction_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `c0657f676603a9b3ff06d7e296f1a7d5ca63029b40b754b87f3baaace421f5cd`.

English case binding: `a08e9271407215b4dd85ddd16cda41f5d0bb7547776ac47bfaa7f9f6900e7699`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-070

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, có bao nhiêu giao dịch thành công và thất bại?

English ID: `t35-070`; difficulty: `medium`; CQ: CQ03, CQ16.

Categories: comparison, temporal_pattern; entity kinds: concept_class.

Expected columns: `["activity_date", "successful_count", "failed_count"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.is_success"]`.

```sql
SELECT DATE(block_timestamp) AS activity_date, COUNTIF(is_success IS TRUE) AS successful_count, COUNTIF(is_success IS FALSE) AS failed_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY activity_date ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `32facd0612092a9227f3b512a1721cb11f2612777828e51f062d56aac6aad1ae`.

English case binding: `85181f12eceebee89d45570407680c2f0805cd0483348093726352d0497d276f`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-072

**Câu Vietnamese:** Liệt kê 10 địa chỉ thụ hưởng đã tạo nhiều khối nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-072`; difficulty: `medium`; CQ: CQ17.

Categories: top_k, transaction_aggregation; entity kinds: address_only.

Expected columns: `["beneficiary_address", "block_count"]`; expected result size: `10`.

Schema elements: `["block_facts", "block_facts.beneficiary_address"]`.

```sql
SELECT beneficiary_address AS beneficiary_address, COUNT(*) AS block_count FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-15', DATE '2026-06-22') WHERE beneficiary_address IS NOT NULL GROUP BY beneficiary_address ORDER BY block_count DESC, beneficiary_address ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `0ad53a84065648e6654758092a89cec6baf3ee4801df71d97c75e908612f2304`.

English case binding: `b6c2024e5a71206be132ce7bd8232c8de23404a045abfa9df6e3188aad0353a9`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
