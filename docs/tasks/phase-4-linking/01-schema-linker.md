# T4.1 — Schema Linker (Property + Class Ranking)

## Mục tiêu

Xây dựng module `SchemaLinker` nhận câu hỏi NL → trả về top-K properties và classes liên quan (ranked by similarity), để inject vào prompt LLM.

## Bối cảnh & lý do

LLM nhỏ (8B) thường không biết được tên chính xác property `:hasFrom` vs `:initiatedBy`. Schema linker giúp:
- Filter ontology xuống ~10 properties relevant thay vì cấp full ontology cho LLM (nhiều noise).
- Rank theo similarity → cấp top-K vào prompt.
- Là **đóng góp khoa học định lượng** (RQ2): so sánh có/không schema linker.

Method: sentence-transformers MiniLM-L6-v2 embed (a) câu NL; (b) property documentation đầy đủ (label + comment + synonyms + exampleUsage). Cosine similarity rank.

## Phụ thuộc

- T2.1 — Ontology với rich documentation (label, comment, synonyms, exampleUsage trên mọi property).

## Đầu vào

- `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`.
- Câu hỏi NL.

## Đầu ra

- Module `src/nl2sparql/linking/schema_linker.py`.
- File index `src/nl2sparql/linking/cache/schema_index.pkl` (precomputed embeddings).
- Tests `tests/test_schema_linker.py`.
- Notebook `notebooks/11_schema_linker_eval.ipynb`.

## Acceptance criteria

- [ ] Module có API: `link(nl_question: str, top_k: int = 10) -> List[(uri, score)]`.
- [ ] Precompute embeddings index, load <1s.
- [ ] Inference latency <100ms cho 1 query.
- [ ] Recall@10 ≥80% trên test set 50 câu (manual annotation: câu nào dùng property nào).
- [ ] Test bao gồm edge cases: ambiguous (`:hasFrom` vs `:initiatedBy`), synonym (`:hasValue` vs `:hasAmount`).

## Hướng dẫn triển khai

### Build property documents

Với mỗi property, concat tất cả annotation thành 1 document:

```python
def build_property_doc(prop_uri, ontology_graph):
    label = get_label(prop_uri)
    comment = get_comment(prop_uri)
    synonyms = get_synonyms(prop_uri)
    example = get_example_usage(prop_uri)
    domain = get_domain_label(prop_uri)
    range_ = get_range_label(prop_uri)

    doc = f"""
Property: {label}
Description: {comment}
Synonyms: {', '.join(synonyms)}
Example: {example}
Used on: {domain} → {range_}
""".strip()
    return doc
```

### Embedding + index

```python
from sentence_transformers import SentenceTransformer

class SchemaLinker:
    def __init__(self, ontology_path, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.props = self._load_props(ontology_path)
        self.classes = self._load_classes(ontology_path)
        self.prop_embeddings = self.model.encode(
            [p["doc"] for p in self.props],
            normalize_embeddings=True
        )
        self.class_embeddings = self.model.encode(
            [c["doc"] for c in self.classes],
            normalize_embeddings=True
        )

    def link(self, nl_question, top_k=10):
        q_emb = self.model.encode(nl_question, normalize_embeddings=True)
        prop_scores = self.prop_embeddings @ q_emb  # cosine since normalized
        class_scores = self.class_embeddings @ q_emb

        top_props = topk(prop_scores, top_k)
        top_classes = topk(class_scores, top_k // 2)
        return {"properties": top_props, "classes": top_classes}

    def save(self, path): ...
    def load(self, path): ...
```

### Caching

- Pickle embeddings + URI list để load nhanh, không recompute.
- Invalidate cache khi ontology version thay đổi (check ontology hash).

### Evaluation

Tạo `data/eval/schema_link_groundtruth.jsonl`:
```json
{"nl": "transactions from Binance to Tornado Cash", "gold_props": [":hasFrom", ":hasTo"]}
```

50 câu manual annotation. Compute:
- **Recall@K** (gold ∈ top-K): chính.
- **MRR** (Mean Reciprocal Rank).
- **Precision@K** (less important: K cao thì precision tự nhiên thấp).

### Variants để thử

| Variant | Embedding input | Mục đích |
|---|---|---|
| V1 | label only | Baseline |
| V2 | label + comment | + context |
| V3 | label + comment + synonyms | + linguistic variation |
| V4 (default) | full doc với example | Full context |

Report cả 4 trong ablation chap.

### Hard cases để document

- "transactions from X" → `:hasFrom` (đúng) vs `:initiatedBy` (sai).
- "amount sent" → `:hasValue` (cho ETH) vs token-specific property.
- "mixer addresses" → cần class-level (`:MixerAccount`) chứ không property.

## Rủi ro & note

- **MiniLM nhỏ, có thể không đủ context blockchain:** thử fallback `all-mpnet-base-v2` nếu recall thấp. Trade-off: 4x slower nhưng quality cao hơn.
- **Domain-specific vocabulary:** "rug pull", "sandwich attack" model không biết. Có thể fine-tune embedding nhưng tốn thời gian — defer.
- **Property tên gần giống:** dependency trên rich documentation (T2.1) — nếu doc nghèo, accuracy thấp.

## Estimated effort

1.5 ngày.

## Trạng thái

todo
