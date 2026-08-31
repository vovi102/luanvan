# GoogleSQL Class Resolver Rules

Tài liệu này mô tả rule contract của T4.3. Resolver tạo typed constraint plan;
consumer chịu trách nhiệm render identifier, parameter và query GoogleSQL an
toàn.

## Inputs and provenance

`ClassResolver` nhận một catalog path và một immutable `EntityCorpus`. Constructor
đọc catalog đúng một lần, validate toàn bộ schema, hash exact bytes và index các
field tham gia `fact_address_to_entity`.

Mọi owner/concept match phải tồn tại trong corpus, có target fingerprint và
metadata trùng snapshot. Raw `address:0x...` là ngoại lệ duy nhất: target ID,
one-address tuple, empty semantic claims và SHA-256 của target ID phải tự nhất
quán. Span phải bằng exact slice của câu hỏi; matches phải ordered và không
overlap.

## Rule priority

### 1. Ambiguity gate

Ambiguous match không dùng primary alternative mặc định. Resolver chỉ hydrate
concept alternative khi local span có `any`, `all`, `every`, `major`, hoặc plural
generic và danh sách alternatives có đúng một concept. Không thỏa điều kiện trả
`unresolved`, operator `none`, không field/value/join claim.

### 2. Resolution kind

- `owner` và `address` có verified addresses: `instance`, operator `in`.
- `concept` có đúng một canonical concept class: `concept`, operator `equals`.
- owner không có address hoặc concept metadata không nhất quán: `unresolved`.

Address values luôn lowercase, unique và sorted. Concept values là local class
name, không phải SQL literal đã quote.

### 3. Direction

Resolver đọc bounded context trước mention:

- `from`, `sent by`, `out of` → `from`;
- `to`, `into`, `received by` → `to`;
- một T4.1 `token_transfer_facts.token_address` candidate duy nhất → `token`;
- cue cạnh nhau xung đột hoặc không có evidence → `unspecified`.

Với flow như `from Binance to USDC`, cue gần mention hơn thắng. Với `from and to
Binance`, direction giữ unspecified và plan có warning.

### 4. Catalog fields

Candidate fields chỉ lấy từ left side của `fact_address_to_entity`:

- `from`: `transaction_facts.from_address`,
  `token_transfer_facts.from_address`;
- `to`: `transaction_facts.to_address`,
  `token_transfer_facts.to_address`;
- `token`: `token_transfer_facts.token_address`.

T4.1 relations/fields được validate với toàn catalog rồi intersect với candidates.
Không giao nhau thì resolver giữ catalog candidates và phát warning; unknown
identity fail closed. Resolver không nối identifier thành SQL.

### 5. Concept join, role and coverage

Concept constraint ghi:

- required relation `entity_labels_v1`;
- required join `fact_address_to_entity`;
- typed value trên `concept_class`;
- common accepted role chỉ khi mọi supporting owner target chia sẻ đúng một role
  trong catalog policy.

Coverage được chứng minh từ owner targets có cùng concept class và ít nhất một
verified address. Không có supporter, ví dụ MixerAccount trong snapshot hiện tại,
trả `coverage_gap`. Resolver vẫn mô tả constraint representable nhưng không claim
query có endpoint matches.

### 6. Cross-mention conflicts

Output giữ source order. Nếu nhiều entity cùng resolve vào một direction, plan là
`partial` với warning. T4.3 không tự chọn `AND`, `OR`, source/destination alias hay
join alias; đó là trách nhiệm của generator/renderer downstream.

## Failure behavior

Malformed question, match, span, fingerprint, corpus target, catalog identity,
schema link, operator/value combination hoặc provenance raise
`ClassResolverError`. Valid ambiguity, missing direction và coverage gap là typed
data. Resolver không persist question text, initialize encoder, access network,
query BigQuery hoặc emit executable SQL.

