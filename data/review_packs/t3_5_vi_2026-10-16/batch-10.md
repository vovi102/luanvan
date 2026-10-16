# Vietnamese review — batch 10 (91–100)

Candidate file SHA-256: `ffc3875802e954ed724b5500a19cefaa4c05cf9bf498e304076c693483154a96`. Training lock: `9adf02c`.

Đọc từng câu với SQL và metadata gốc. Điền phiếu CSV cùng batch hoặc trả lời trong chat. Mọi điểm/decision đang trống; chưa có human review.

## pair-t35-109

**Câu Vietnamese:** So sánh số giao dịch và tổng giá trị wei giữa giai đoạn trước ngày 18/06/2026 và giai đoạn từ ngày đó trở đi, xét trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-109`; difficulty: `hard`; CQ: CQ01, CQ02.

Categories: comparison, temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["period_name", "transaction_count", "total_value_wei"]`; expected result size: `2`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.value_wei"]`.

```sql
WITH period_totals AS (SELECT CASE WHEN block_timestamp < TIMESTAMP(DATE '2026-06-18') THEN 'early' ELSE 'late' END AS period_name, COUNT(*) AS transaction_count, COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY period_name) SELECT period_name AS period_name, transaction_count AS transaction_count, total_value_wei AS total_value_wei FROM period_totals ORDER BY period_name ASC
```

Candidate line SHA-256 (including newline): `9ac3d53878fd44ffc1b8710d85c22de1c0173fb6fa485aa9cfafe0cacabb5ff6`.

English case binding: `30d70a76b4b1b584cf7190a2f4d274173b27843717474bb455b8c18fe89f9821`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-110

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, hãy so sánh số dòng giao dịch quan sát được với tổng số giao dịch ghi nhận trong các khối.

English ID: `t35-110`; difficulty: `hard`; CQ: CQ06, CQ09.

Categories: multi_hop, comparison, temporal_pattern; entity kinds: concept_class.

Expected columns: `["activity_date", "observed_transaction_rows", "joined_block_transaction_total"]`; expected result size: `7`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "block_facts", "block_facts.block_timestamp", "block_facts.transaction_count"]`.

```sql
WITH tx_daily AS (SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS observed_transaction_rows FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY activity_date), block_daily AS (SELECT DATE(block_timestamp) AS activity_date, SUM(transaction_count) AS joined_block_transaction_total FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY activity_date) SELECT tx_daily.activity_date AS activity_date, tx_daily.observed_transaction_rows AS observed_transaction_rows, block_daily.joined_block_transaction_total AS joined_block_transaction_total FROM tx_daily JOIN block_daily USING (activity_date) ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `97b48f3540499604126408bd0cb474fa40c60fa5e749317c6e8af9776cc5e200`.

English case binding: `d69b90808de578b9c316a6b2f0f370e5a3194ec03d3db27b8cea9bc17e1b8464`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-112

**Câu Vietnamese:** Liệt kê 10 giao dịch có nhiều sự kiện chuyển token nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, kèm giá trị native theo wei và số lượt chuyển.

English ID: `t35-112`; difficulty: `hard`; CQ: CQ19.

Categories: multi_hop, top_k, token_specific; entity kinds: address_only.

Expected columns: `["transaction_hash", "native_value_wei", "transfer_count"]`; expected result size: `10`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.transaction_hash", "token_transfer_facts.block_number", "token_transfer_facts.block_hash", "transaction_facts", "transaction_facts.transaction_hash", "transaction_facts.value_wei"]`.

```sql
WITH transfer_counts AS (SELECT transaction_hash AS transaction_hash, block_number AS block_number, block_hash AS block_hash, COUNT(*) AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22') GROUP BY transaction_hash, block_number, block_hash) SELECT tx.transaction_hash AS transaction_hash, tx.value_wei AS native_value_wei, transfer_counts.transfer_count AS transfer_count FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') AS tx JOIN transfer_counts ON tx.transaction_hash = transfer_counts.transaction_hash AND tx.block_number = transfer_counts.block_number AND tx.block_hash = transfer_counts.block_hash ORDER BY transfer_count DESC, native_value_wei DESC, transaction_hash ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `0c7d01f023c804fe0b3927a7b9bea883c49271878e0bb4126175591f2f327a9b`.

English case binding: `e9b895dd8f9b9d8f8fc6fee86f518c3baea0c1c0169248457627643e19a545b1`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-113

**Câu Vietnamese:** Cho biết 10 lớp khái niệm của bên gửi có tổng giá trị giao dịch lớn nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026, kèm số giao dịch và tổng giá trị wei.

English ID: `t35-113`; difficulty: `hard`; CQ: CQ13, CQ22.

Categories: multi_hop, class_level, top_k; entity kinds: named_entity.

Expected columns: `["sender_concept_class", "transaction_count", "total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.from_address", "transaction_facts.value_wei", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS sender_concept_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-15', DATE '2026-06-22') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.from_address = labels.address GROUP BY sender_concept_class ORDER BY total_value_wei DESC, sender_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `4eaf825f1bbea86430a9621aa3570a5b8615db5ca943e701bd2323ef73a590fb`.

English case binding: `09e7d36628ca68c41941e36d382e45fea60f8c9f84bf23510bbded55fb627bf2`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-114

**Câu Vietnamese:** Liệt kê 20 cặp chủ sở hữu bên nhận và ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 15/06/2026 đến hết ngày 21/06/2026.

English ID: `t35-114`; difficulty: `hard`; CQ: CQ25, CQ29.

Categories: multi_hop, token_specific, top_k; entity kinds: named_entity.

Expected columns: `["recipient_owner", "token_symbol", "total_normalized_amount"]`; expected result size: `20`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.owner"]`.

```sql
SELECT labels.owner AS recipient_owner, transfers.token_symbol AS token_symbol, SUM(transfers.normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-15', DATE '2026-06-22') AS transfers JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON transfers.to_address = labels.address WHERE transfers.normalized_amount IS NOT NULL AND transfers.token_symbol IS NOT NULL GROUP BY recipient_owner, token_symbol ORDER BY total_normalized_amount DESC, recipient_owner ASC, token_symbol ASC LIMIT 20
```

Candidate line SHA-256 (including newline): `25890916adffe3f615f7ff56d6c7753c27f6ad3c49e7898119c81157ae101334`.

English case binding: `fbbe90ea635f4cd93a4d28766fd66bedd3bfe5c5b6395ba5534b13494a6ba010`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-115

**Câu Vietnamese:** So sánh số giao dịch và tổng giá trị wei giữa giai đoạn trước ngày 26/06/2026 và giai đoạn từ ngày đó trở đi, xét trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-115`; difficulty: `hard`; CQ: CQ01, CQ02.

Categories: comparison, temporal_pattern, transaction_aggregation; entity kinds: concept_class.

Expected columns: `["period_name", "transaction_count", "total_value_wei"]`; expected result size: `2`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "transaction_facts.value_wei"]`.

```sql
WITH period_totals AS (SELECT CASE WHEN block_timestamp < TIMESTAMP(DATE '2026-06-26') THEN 'early' ELSE 'late' END AS period_name, COUNT(*) AS transaction_count, COALESCE(SUM(value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY period_name) SELECT period_name AS period_name, transaction_count AS transaction_count, total_value_wei AS total_value_wei FROM period_totals ORDER BY period_name ASC
```

Candidate line SHA-256 (including newline): `2910996e68b47744177d9a459d277b61df103c68e3c2b9b483404ce305a29930`.

English case binding: `a7bcee2f334b5cc525ab07c6411b9e039610653366e2d533d2319c65c20f8573`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-116

**Câu Vietnamese:** Theo từng ngày trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026, hãy so sánh số dòng giao dịch quan sát được với tổng số giao dịch ghi nhận trong các khối.

English ID: `t35-116`; difficulty: `hard`; CQ: CQ06, CQ09.

Categories: multi_hop, comparison, temporal_pattern; entity kinds: concept_class.

Expected columns: `["activity_date", "observed_transaction_rows", "joined_block_transaction_total"]`; expected result size: `9`.

Schema elements: `["transaction_facts", "transaction_facts.block_timestamp", "block_facts", "block_facts.block_timestamp", "block_facts.transaction_count"]`.

```sql
WITH tx_daily AS (SELECT DATE(block_timestamp) AS activity_date, COUNT(*) AS observed_transaction_rows FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY activity_date), block_daily AS (SELECT DATE(block_timestamp) AS activity_date, SUM(transaction_count) AS joined_block_transaction_total FROM `nl2sparql-thesis.nl2sparql_analytics.block_facts`(DATE '2026-06-22', DATE '2026-07-01') GROUP BY activity_date) SELECT tx_daily.activity_date AS activity_date, tx_daily.observed_transaction_rows AS observed_transaction_rows, block_daily.joined_block_transaction_total AS joined_block_transaction_total FROM tx_daily JOIN block_daily USING (activity_date) ORDER BY activity_date ASC
```

Candidate line SHA-256 (including newline): `7e75b274f1dfa7e2e166c239fc0887d9dff41d519f56abfd15d3b0ab6a34079d`.

English case binding: `fa14a9a4fd108762f5aea878f8fd0a85f1aaf583c8fc8da89f194fa929cc85a2`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-117

**Câu Vietnamese:** Hãy thống kê số giao dịch và tổng giá trị wei theo lớp hợp đồng nhận (ERC-20, ERC-721 hoặc loại khác) trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-117`; difficulty: `hard`; CQ: CQ18.

Categories: multi_hop, class_level, comparison; entity kinds: concept_class.

Expected columns: `["recipient_contract_class", "transaction_count", "total_value_wei"]`; expected result size: `3`.

Schema elements: `["transaction_facts", "transaction_facts.to_address", "transaction_facts.value_wei", "contract_dimension", "contract_dimension.address", "contract_dimension.is_erc20", "contract_dimension.is_erc721"]`.

```sql
SELECT CASE WHEN contracts.is_erc721 IS TRUE THEN 'erc721' WHEN contracts.is_erc20 IS TRUE THEN 'erc20' ELSE 'other_or_unknown' END AS recipient_contract_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.contract_dimension`(DATE '2026-07-01') AS contracts ON tx.to_address = contracts.address GROUP BY recipient_contract_class ORDER BY recipient_contract_class ASC
```

Candidate line SHA-256 (including newline): `2e32d27faf46293f6acfd53e08fe99e71f7d9ddd084743f4acd0ed860e204c14`.

English case binding: `6891c453197f945e7f57dec70081286007c84ac9bb10eef1ba6ed64cbf6fd530`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-119

**Câu Vietnamese:** Cho biết 10 lớp khái niệm của bên gửi có tổng giá trị giao dịch lớn nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026, kèm số giao dịch và tổng giá trị wei.

English ID: `t35-119`; difficulty: `hard`; CQ: CQ13, CQ22.

Categories: multi_hop, class_level, top_k; entity kinds: named_entity.

Expected columns: `["sender_concept_class", "transaction_count", "total_value_wei"]`; expected result size: `1`.

Schema elements: `["transaction_facts", "transaction_facts.from_address", "transaction_facts.value_wei", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.concept_class"]`.

```sql
SELECT labels.concept_class AS sender_concept_class, COUNT(*) AS transaction_count, COALESCE(SUM(tx.value_wei), 0) AS total_value_wei FROM `nl2sparql-thesis.nl2sparql_analytics.transaction_facts`(DATE '2026-06-22', DATE '2026-07-01') AS tx JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON tx.from_address = labels.address GROUP BY sender_concept_class ORDER BY total_value_wei DESC, sender_concept_class ASC LIMIT 10
```

Candidate line SHA-256 (including newline): `384844ba28c59685143acbc42636840fe1815d9e8cd992cb6ae36c81703ec72c`.

English case binding: `d558ded3060eb8597cf6bf2ad91c1f8a16af643ba04097b7cc2abedeac4d447a`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________

## pair-t35-120

**Câu Vietnamese:** Liệt kê 20 cặp chủ sở hữu bên nhận và ký hiệu token có tổng lượng chuyển chuẩn hóa lớn nhất trong khoảng từ ngày 22/06/2026 đến hết ngày 30/06/2026.

English ID: `t35-120`; difficulty: `hard`; CQ: CQ25, CQ29.

Categories: multi_hop, token_specific, top_k; entity kinds: named_entity.

Expected columns: `["recipient_owner", "token_symbol", "total_normalized_amount"]`; expected result size: `20`.

Schema elements: `["token_transfer_facts", "token_transfer_facts.to_address", "token_transfer_facts.token_symbol", "token_transfer_facts.normalized_amount", "entity_labels_v1", "entity_labels_v1.address", "entity_labels_v1.owner"]`.

```sql
SELECT labels.owner AS recipient_owner, transfers.token_symbol AS token_symbol, SUM(transfers.normalized_amount) AS total_normalized_amount FROM `nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts`(DATE '2026-06-22', DATE '2026-07-01') AS transfers JOIN `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1` AS labels ON transfers.to_address = labels.address WHERE transfers.normalized_amount IS NOT NULL AND transfers.token_symbol IS NOT NULL GROUP BY recipient_owner, token_symbol ORDER BY total_normalized_amount DESC, recipient_owner ASC, token_symbol ASC LIMIT 20
```

Candidate line SHA-256 (including newline): `59d91d79b421150b908d26ee801187e456fc03ab38e7fddbbf1e54e8525aeb7c`.

English case binding: `456f0bec1b57dc1a16b42998cfcb8ffef2ab380ea88579aa92c279b17fb58197`.

Decision: ______; naturalness: ___; SQL faithfulness: ___; terminology: ___; ambiguity: ___.

Revised question / notes: ______________________________________
