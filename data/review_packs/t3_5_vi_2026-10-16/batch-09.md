# Vietnamese review — batch 09 (81–90)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-098

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, hãy so sánh số dòng giao dịch quan sát được với tổng số giao dịch ghi nhận trong các khối.

English ID: `t35-098`; difficulty: `hard`; CQ: CQ06, CQ09.

Categories: multi_hop, comparison, temporal_pattern; entity kinds: concept_class.

Expected columns: `["activity_date", "observed_transaction_rows", "joined_block_transaction_total"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "block_facts", "block_facts.block_timestamp", "block_facts.transaction_count"]`.

```sql
WITH tx_daily AS (SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS observed_transaction_rows FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY activity_date), block_daily AS (SELECT DATE(block_timestamp) AS activity_date, SUM(transaction_count) AS joined_block_transaction_total FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY activity_date) SELECT tx_daily.activity_date AS activity_date, tx_daily.observed_transaction_rows AS observed_transaction_rows, block_daily.joined_block_transaction_total AS joined_block_transaction_total FROM tx_daily JOIN block_daily USING (activity_date) ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `dca1f910b07905062462610c771a776ada0c6bead2afd813b245b66d8384ec7f`.

English case binding: `a8855f76e661fc46e5f4bcd168ba238771523baf2655bfd4980d5ecf4b67a3a5`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-099

**Câu Vietnamese:** Hãy thống kê số giao dịch và tổng giá trị wei theo lớp hợp đồng nhận (ERC-20, ERC-721 hoặc loại khác) trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-099`; difficulty: `hard`; CQ: CQ18.

Categories: multi_hop, class_level, comparison; entity kinds: concept_class.

Expected columns: `["recipient_contract_class", "transaction_count", "total_value_wei"]`; expected result size: `3`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "transaction_facts.value_wei", "contract_dimension", "contract_dimension.address", "contract_dimension.is_erc20", "contract_dimension.is_erc721"]`.

```sql
SELECT CASE WHEN contracts.is_erc721 IS TRUE THEN 'erc721' WHEN contracts.is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS recipient_contract_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.contract_dimension`(DATE '2026-06-08') AS contracts ON tx.to_address = contracts.address GROUP BY recipient_contract_class ORDER BY recipient_contract_class ASC
```

Candidate line SHA-256 (including newline): `7c25a827af15392f39ab4f063a4b03ce8a3eabf17f22c2e6eb180b751f4f3319`.

English case binding: `c6dab9f8fbcaf11ffe86b0495447940b35e1a5fb114472f474f08eace89fcadd`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-100

**Câu Vietnamese:** Liệt kê 10 giao dịch có nhiều sự kiện chuyển token nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, kèm giá trị native theo wei và số lượt chuyển.

English ID: `t35-100`; difficulty: `hard`; CQ: CQ19.

Categories: multi_hop, top_k, token_specific; entity kinds: address_only.

Expected columns: `["transaction_hash", "native_value_wei", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash", "token_transfer_facts.block_number", "token_transfer_facts.block_hash", "transaction_facts", "transaction_facts.transaction_hash", "transaction_facts.value_wei"]`.

```sql
WITH transfer_counts AS (SELECT transaction_hash AS transaction_hash, block_number AS block_number, block_hash AS block_hash, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') GROUP BY transaction_hash, block_number, block_hash) SELECT tx.transaction_hash AS transaction_hash, tx.value_wei AS native_value_wei, transfer_counts.transfer_count AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') AS tx JOIN transfer_counts ON tx.transaction_hash = transfer_counts.transaction_hash AND tx.block_number = transfer_counts.block_number AND tx.block_hash = transfer_counts.block_hash ORDER BY transfer_count DESC, native_value_wei DESC, transaction_hash ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `f72115460a05e43064cb64bfbcf269e389d63ab8802f78c96bb13ae9bc327120`.

English case binding: `3a61aa43fa401612a14595419c23088d1ee1d29f2c968fdb75a1f799276672c7`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-101

**Câu Vietnamese:** Cho biết 10 lớp khái niệm của bên gửi có tổng giá trị giao dịch lớn nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026, kèm số giao dịch và tổng giá trị wei.

English ID: `t35-101`; difficulty: `hard`; CQ: CQ13, CQ22.

Categories: multi_hop, class_level, top_k; entity kinds: named_entity.

Expected columns: `["sender_concept_class", "transaction_count", "total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.from_address", "transaction_facts.value_wei", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS sender_concept_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-01', DATE '2026-06-08') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.from_address = labels.address GROUP BY sender_concept_class ORDER BY total_value_wei DESC, sender_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `de9abc09c425117541b1683d7cb099ed61c863cf4d1e99443a47a48dae267fd6`.

English case binding: `6a1b81cc0dd846bb917b8375f363047978f6b8de5e0386c27405ed4fc5928b1c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-102

**Câu Vietnamese:** Liệt kê 20 cặp chủ sở hữu bên nhận và ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 01/06/2026 đến hết ngày 07/06/2026.

English ID: `t35-102`; difficulty: `hard`; CQ: CQ25, CQ29.

Categories: multi_hop, token_specific, top_k; entity kinds: named_entity.

Expected columns: `["recipient_owner", "token_symbol", "total_normalized_amount"]`; expected result size: `20`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.owner"]`.

```sql
SELECT labels.owner AS recipient_owner, transfers.token_symbol AS token_symbol, SUM(transfers.normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-01', DATE '2026-06-08') AS transfers JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON transfers.to_address = labels.address WHERE transfers.normalized_amount IS NOT NULL AND transfers.token_symbol IS NOT NULL GROUP BY recipient_owner, token_symbol ORDER BY total_normalized_amount DESC, recipient_owner ASC, token_symbol ASC LIMIT 20
```

Candidate line SHA-256 (including newline): `5b5171cb7ad9578823481cfb36a24e754f3534f7281bdb0b0e04fe2f113278f0`.

English case binding: `3bf3f818d01a220ee46557877e2cde422f76bfc4cd57f6b5bea8043fda21c7b2`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-103

**Câu Vietnamese:** So sánh số giao dịch và tổng giá trị wei giữa giai đoạn trước ngày 11/06/2026 và giai đoạn từ ngày đó trở đi, xét trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-103`; difficulty: `hard`; CQ: CQ01, CQ02.

Categories: comparison, temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["period_name", "transaction_count", "total_value_wei"]`; expected result size: `2`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.value_wei"]`.

```sql
WITH period_totals AS (SELECT CASE WHEN block_timestamp < TIMESTAMP(DATE '2026-06-11') THEN 'early' ELSE 'late' END AS period_name, COUNT(*) AS transaction_count, COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY period_name) SELECT period_name AS period_name, transaction_count AS transaction_count, total_value_wei AS total_value_wei FROM period_totals ORDER BY period_name ASC
```

Candidate line SHA-256 (including newline): `0940286414bfeb42520613f72635970d351558e50f1886df1391169652b62e0b`.

English case binding: `ba6a2e3d7835ed006958d25d98c44b08fd0ec6233f190075aa4b66cc909a2f75`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-105

**Câu Vietnamese:** Hãy thống kê số giao dịch và tổng giá trị wei theo lớp hợp đồng nhận (ERC-20, ERC-721 hoặc loại khác) trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-105`; difficulty: `hard`; CQ: CQ18.

Categories: multi_hop, class_level, comparison; entity kinds: concept_class.

Expected columns: `["recipient_contract_class", "transaction_count", "total_value_wei"]`; expected result size: `3`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "transaction_facts.value_wei", "contract_dimension", "contract_dimension.address", "contract_dimension.is_erc20", "contract_dimension.is_erc721"]`.

```sql
SELECT CASE WHEN contracts.is_erc721 IS TRUE THEN 'erc721' WHEN contracts.is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS recipient_contract_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.contract_dimension`(DATE '2026-06-15') AS contracts ON tx.to_address = contracts.address GROUP BY recipient_contract_class ORDER BY recipient_contract_class ASC
```

Candidate line SHA-256 (including newline): `181f0c0f309e9686e9857c3409d0a878753274ab0953cf08c79442ecffde1723`.

English case binding: `47018868abd7f0efa1353f7c7a6852542bbcb01fa07f351d2d06fd9fd8927295`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-106

**Câu Vietnamese:** Liệt kê 10 giao dịch có nhiều sự kiện chuyển token nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026, kèm giá trị native theo wei và số lượt chuyển.

English ID: `t35-106`; difficulty: `hard`; CQ: CQ19.

Categories: multi_hop, top_k, token_specific; entity kinds: address_only.

Expected columns: `["transaction_hash", "native_value_wei", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash", "token_transfer_facts.block_number", "token_transfer_facts.block_hash", "transaction_facts", "transaction_facts.transaction_hash", "transaction_facts.value_wei"]`.

```sql
WITH transfer_counts AS (SELECT transaction_hash AS transaction_hash, block_number AS block_number, block_hash AS block_hash, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15') GROUP BY transaction_hash, block_number, block_hash) SELECT tx.transaction_hash AS transaction_hash, tx.value_wei AS native_value_wei, transfer_counts.transfer_count AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') AS tx JOIN transfer_counts ON tx.transaction_hash = transfer_counts.transaction_hash AND tx.block_number = transfer_counts.block_number AND tx.block_hash = transfer_counts.block_hash ORDER BY transfer_count DESC, native_value_wei DESC, transaction_hash ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `a85555878e41f65a1d142cb416b220d68685faa6f3a74d8f61c4f5c24ef8f0b2`.

English case binding: `17c10f7ec88a192dc0ac60cfb7f00242b086ce982b75d52d24388a5db525665c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-107

**Câu Vietnamese:** Cho biết 10 lớp khái niệm của bên gửi có tổng giá trị giao dịch lớn nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026, kèm số giao dịch và tổng giá trị wei.

English ID: `t35-107`; difficulty: `hard`; CQ: CQ13, CQ22.

Categories: multi_hop, class_level, top_k; entity kinds: named_entity.

Expected columns: `["sender_concept_class", "transaction_count", "total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.from_address", "transaction_facts.value_wei", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS sender_concept_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-08', DATE '2026-06-15') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.from_address = labels.address GROUP BY sender_concept_class ORDER BY total_value_wei DESC, sender_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `d666f1fdb957101f76f19d14fecb215be85adeb8628a2b8854d14017a459334c`.

English case binding: `6cd8d53183e45dee029c6c260f77d0363b1c86500d8857841ca9aa83ff42355c`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-108

**Câu Vietnamese:** Liệt kê 20 cặp chủ sở hữu bên nhận và ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 08/06/2026 đến hết ngày 14/06/2026.

English ID: `t35-108`; difficulty: `hard`; CQ: CQ25, CQ29.

Categories: multi_hop, token_specific, top_k; entity kinds: named_entity.

Expected columns: `["recipient_owner", "token_symbol", "total_normalized_amount"]`; expected result size: `20`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.owner"]`.

```sql
SELECT labels.owner AS recipient_owner, transfers.token_symbol AS token_symbol, SUM(transfers.normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-08', DATE '2026-06-15') AS transfers JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON transfers.to_address = labels.address WHERE transfers.normalized_amount IS NOT NULL AND transfers.token_symbol IS NOT NULL GROUP BY recipient_owner, token_symbol ORDER BY total_normalized_amount DESC, recipient_owner ASC, token_symbol ASC LIMIT 20
```

Candidate line SHA-256 (including newline): `fefc4a0991da8e7f28969f0b0519948c8bf8cdc1132d8460cd6e2d51c37a373f`.

English case binding: `a5dd97c1b60d4c382219f3eb439becd41d2a3f7c1abed4fa55fbe0ae1c0f9795`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
