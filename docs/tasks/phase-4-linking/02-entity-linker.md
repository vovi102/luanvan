# T4.2 — GoogleSQL Entity Linker (4-Stage Cascading Match)

## Mục tiêu

Xây dựng module `EntityLinker` nhận câu hỏi ngôn ngữ tự nhiên và nhận diện
evidence thực thể cho pipeline GoogleSQL/BigQuery: owner, concept hoặc Ethereum
address. T4.2 chỉ nhận diện và trả provenance; T4.3 mới quyết định predicate,
join và filter GoogleSQL.

## Thiết kế đã triển khai

API công khai là `EntityLinker.link(question: str) -> tuple[EntityMatch, ...]`.
Kết quả bất biến có raw span/original offset, stable target ID/kind, owner,
addresses, category/concept class khi có, confidence, stage, alternatives và
fingerprint của dictionary target. Một câu không có entity evidence trả tuple
rỗng, không tạo `unknown` giả.

Cascade chạy theo thứ tự:

1. Address/exact: nhận diện đầy đủ `0x` + 40 hex hoặc phrase dictionary/concept
   dài nhất với Unicode NFKC, case-folding và original-character offsets.
2. Fuzzy: RapidFuzz cho các cửa sổ 1--5 token chưa phủ, threshold `0.85` và
   different-target margin `0.03`.
3. Embedding: MiniLM `sentence-transformers/all-MiniLM-L6-v2`, threshold `0.75`
   và cùng margin; encoder chỉ khởi tạo ở lệnh production explicit.
4. Ambiguity: trả alternatives typed thay vì tự chọn khi collision hoặc khoảng
   cách không đủ an toàn.

Một address hợp lệ luôn query được. Address đã biết được enrich từ dictionary;
address lạ trả target `address:<lowercase-address>` không owner/category claim.
Kết quả recognition không chứa SQL fragment và không tự quyết định SQL predicate
hay join.

## Dictionary, index và an toàn

Dictionary đã validate trước khi sinh owner/concept targets và aliases. Production
index không dùng pickle: manifest JSON canonical bind schema/document/model,
dictionary/documents và effective fuzzy/embedding/ambiguity policy; matrix
float32 nằm trong immutable,
content-addressed `entity-index-<sha256>.npz`, load với `allow_pickle=False`.
Publish dưới process lock theo manifest-last; strict load kiểm tra generation,
digest, shape, finite/L2-normalized vectors, aliases/symlink/hardlink/path
traversal và metadata hiện tại. Không có implicit rebuild, download model hay
BigQuery call.

## Evidence triển khai cục bộ — 2026-08-29

Build dùng cache model cục bộ thành công, không tải model:

```text
uv run python scripts/14_entity_linker.py build-index --local-files-only
```

- Targets: `5,107`; dimension: `384`.
- Model: `sentence-transformers/all-MiniLM-L6-v2`.
- Policy bound in the strict manifest: fuzzy threshold `0.85`, embedding
  threshold `0.75`, ambiguity margin `0.03`. Strict load rejects missing,
  malformed, out-of-range, non-finite, or effective-policy-mismatched values.
- Manifest file SHA-256:
  `0575e2222b0d1aebff0bee80cdd338c6dc8a80be38f6094f19cf9bbc05979a31`.
- Manifest body SHA-256:
  `bc27bb10e6e09ea3244107c4adef3679604cf65583ab32f1ca3a02251588e2ce`.
- Matrix SHA-256:
  `ee33c9fededf9be1091bca69e64c7f4075ba1d0f9948652a412c39f14c4dfa53`.
- Strict-load succeeded against the current accepted dictionary and model ID.
- Representative strict-loaded CLI queries succeeded with `--local-files-only`:
  exact `Binance` → `owner:Binance`; fuzzy `Binnance` → `owner:Binance`
  (`0.933333...`); `centralized exchange` → `concept:exchange`; known address
  `0x6454ac71ca260f99cca99a3f4241dfda20cfa965` → enriched `owner:Binance`.
- After strict load and explicit local MiniLM initialization, a warmed in-process
  `show Binnance transfers` fuzzy smoke measured `74.945 ms`; 20 warm samples had
  median `80.338 ms` and maximum `148.265 ms`. This is a smoke measurement, not
  the independently evaluated p95 scientific acceptance result.

## Acceptance criteria

- [x] GoogleSQL-native recognition API and immutable typed matches are implemented.
- [x] Address, exact, fuzzy, embedding and explicit ambiguity behavior have focused
  production-module test coverage.
- [x] Safe manifest-last, content-addressed and policy-bound production index builds
  and strict-loads with the cached local MiniLM model.
- [x] Representative exact, fuzzy, concept and address production queries strict-load.
- [ ] Named-entity Top-1 accuracy >=85% on exactly 100 independently reviewed
  ground-truth questions. `data/eval/entity_link_groundtruth.jsonl` is absent;
  no synthetic/manual labels were created.
- [ ] Warm p95 latency <200 ms from the independently reviewed 100-row evaluation.
  The local 20-query smoke above is intentionally not substituted for this gate.

## Trạng thái

Implementation checkpoint complete locally. Scientific acceptance remains pending
the independent 100-row artifact and a real `evaluate` run. The production index
and test evidence are offline/local; no BigQuery query or external write is part
of this checkpoint.
