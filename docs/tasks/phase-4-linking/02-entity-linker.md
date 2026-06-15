# T4.2 — Entity Linker (4-Stage Cascading Match)

## Mục tiêu

Xây dựng module `EntityLinker` nhận câu hỏi NL → trích xuất entity mentions ("Binance", "Tornado Cash") → resolve sang địa chỉ Ethereum (set của addresses) hoặc concept class.

## Bối cảnh & lý do

Đặc thù blockchain (xem `00-PROJECT_OVERVIEW.md` đặc thù 1-3): "Binance" = ~30 addresses; "Tornado Cash" có aliases. Đây là **đóng góp khoa học định lượng** (RQ2).

Pipeline 4 stage cascading (mỗi stage trả lại kết quả nếu match, fallback xuống stage sau):
- **Stage A:** Exact match (case-insensitive) trên `entities.json` + `aliases.json`.
- **Stage B:** Fuzzy match (Levenshtein/rapidfuzz) ratio ≥0.85.
- **Stage C:** Embedding similarity (sentence-transformers) ≥0.75.
- **Stage D:** Fallback → "unknown", prompt clarification (hoặc skip).

## Phụ thuộc

- T2.2 — Entity dictionary đã có ≥3000 entries.
- T4.1 — Sentence-transformers model đã load (reuse).

## Đầu vào

- `src/nl2sparql/linking/dictionary/entities.json`.
- `src/nl2sparql/linking/dictionary/aliases.json`.
- Câu hỏi NL.

## Đầu ra

- Module `src/nl2sparql/linking/entity_linker.py`.
- File index `src/nl2sparql/linking/cache/entity_index.pkl`.
- Tests `tests/test_entity_linker.py` với 30+ test cases.
- Notebook `notebooks/12_entity_linker_eval.ipynb`.

## Acceptance criteria

- [ ] API: `link(nl_question: str) -> List[EntityMatch]`.
- [ ] Latency <200ms cho 1 query (typical 1-3 entities).
- [ ] Top-1 accuracy ≥85% trên test set 100 câu (named entities only, không kể address-only).
- [ ] Test cover 4 stages, có ít nhất 1 case mỗi stage.
- [ ] Clarification UI khi confidence <0.75 (return special "ambiguous" type).

## Hướng dẫn triển khai

### EntityMatch schema

```python
@dataclass
class EntityMatch:
    span: str                    # raw text trong câu hỏi
    span_offset: tuple[int, int] # (start, end) char offset
    matched_to: str              # primary_label, e.g. "Binance"
    addresses: list[str]         # [0x..., 0x..., ...]
    concept_class: Optional[str] # "Exchange", "MixerAccount", ...
    stage: str                   # "exact" | "fuzzy" | "embedding" | "unknown"
    confidence: float            # 0-1
    candidates: list[dict]       # top-3 alternatives nếu ambiguous
```

### Mention extraction

Vì câu hỏi ngắn, KHÔNG dùng NER nặng. Strategy: candidate generation từ n-grams + dictionary lookup.

```python
def extract_candidates(nl: str, max_ngram: int = 4) -> list[str]:
    tokens = nl.split()
    candidates = []
    for n in range(1, min(max_ngram, len(tokens)) + 1):
        for i in range(len(tokens) - n + 1):
            span = " ".join(tokens[i:i+n])
            candidates.append((span, (i, i+n)))
    return candidates
```

Optional: dùng spaCy NER để filter candidates xuống ORG/PERSON labels.

### Stage A — Exact match

```python
def stage_a(span, exact_index):
    # exact_index: dict[lower_str] -> entity_record
    key = span.lower().strip()
    return exact_index.get(key)
```

Build index với both `primary_label` và `aliases`.

### Stage B — Fuzzy

```python
from rapidfuzz import process, fuzz

def stage_b(span, all_labels, threshold=85):
    matches = process.extract(span, all_labels, scorer=fuzz.WRatio, limit=3)
    matches = [m for m in matches if m[1] >= threshold]
    return matches  # [(label, score, idx), ...]
```

`WRatio` xử lý token order và partial matches tốt hơn Levenshtein thuần.

### Stage C — Embedding

```python
def stage_c(span, label_embeddings, labels, threshold=0.75):
    span_emb = self.model.encode(span, normalize_embeddings=True)
    scores = label_embeddings @ span_emb
    top_idx = np.argsort(-scores)[:3]
    matches = [(labels[i], scores[i]) for i in top_idx if scores[i] >= threshold]
    return matches
```

### Stage D — Fallback

```python
def stage_d(span):
    return EntityMatch(
        span=span, matched_to=None, addresses=[],
        stage="unknown", confidence=0.0,
        candidates=[]
    )
```

### Address detection (parallel pipeline)

Nếu user paste 0x... trực tiếp: regex `^0x[a-fA-F0-9]{40}$`, không cần linking.

```python
def detect_address(span):
    if re.fullmatch(r'0x[a-fA-F0-9]{40}', span):
        return span.lower()
    return None
```

### Concept-class detection

Một số mention không phải instance mà là class: "any DEX", "all exchanges", "mixers". Build small concept dictionary:

```json
{
  "exchange": ":ExchangeAccount",
  "exchanges": ":ExchangeAccount",
  "DEX": ":DEXProtocol",
  "DEXes": ":DEXProtocol",
  "mixer": ":MixerAccount",
  "mixers": ":MixerAccount",
  "lending protocol": ":LendingProtocol"
}
```

Nếu match concept → returnconcept_class set, addresses=[] (LLM sẽ generate `?x a :Class` triple thay vì VALUES).

### Greedy span selection

Có thể nhiều ngram match. Dùng greedy left-to-right longest-match để tránh duplicate:

```
"Binance hot wallet" → match "Binance" (1-gram) AND "Binance hot wallet" (3-gram)
→ chọn 3-gram (longest), drop 1-gram nested.
```

### Ambiguity handling

Nếu top-2 matches có confidence gần (delta <0.1) → flag `ambiguous=true`, return cả 2 candidates. Downstream pipeline có thể:
- Hỏi user clarification (interactive demo).
- Pick top-1 và log warning (batch mode).

## Rủi ro & note

- **False positive trên common words:** "the" có thể fuzzy match một entity nào đó. Solution: stop-word filter trước khi gen candidates.
- **Aliases conflict:** "Uni" = Uniswap hay UNI token? Cần priority rule (giữ trong `entities.json` field `priority`).
- **Long-tail entities không có dictionary:** stage D báo "unknown" rõ ràng, không hallucinate. Là finding khoa học (long-tail performance).

## Estimated effort

2 ngày.

## Trạng thái

todo
