# T5.1 — B0: Rule-Based Baseline (Template Matching)

## Mục tiêu

Triển khai baseline B0 — template matching không dùng LLM. Mỗi câu hỏi NL được match với template gần nhất → fill slot từ entity linker → output SPARQL.

## Bối cảnh & lý do

B0 là **lower bound** trong 6 baselines. Nếu LLM không vượt được B0 thì có vấn đề. Cũng quan trọng để biết: rule-based có thể đi xa cỡ nào trên dataset có structure cao như NL2SPARQL?

## Phụ thuộc

- T3.1 — `templates.json` đã có.
- T4.1 — Schema linker.
- T4.2 — Entity linker.
- T4.3 — Class resolver.
- T3.5 — Test set 100 câu (để evaluate).

## Đầu vào

- Templates với `nl_seed` patterns.
- Entity linker output.
- Test set NL questions.

## Đầu ra

- Module `src/nl2sparql/models/b0_rule_based.py`.
- Predictions `data/eval/predictions/b0_test.jsonl`.
- Notebook `notebooks/13_b0_eval.ipynb`.

## Acceptance criteria

- [ ] API: `BaselineB0.predict(nl: str) -> str | None` (None = "không match template").
- [ ] Latency <100ms per query.
- [ ] Coverage rate ≥40% trên test set (40% câu match được template).
- [ ] Trên những câu match: Execution Accuracy ≥60%.

## Hướng dẫn triển khai

### Matching strategy

```python
class BaselineB0:
    def __init__(self, templates_path):
        self.templates = load(templates_path)
        # Pre-compile regex / pattern from each template's nl_seed
        self.patterns = [
            self._compile_pattern(t) for t in self.templates
        ]
        self.entity_linker = EntityLinker(...)

    def _compile_pattern(self, template):
        """Convert nl_seed with {slot_name} → regex with named groups."""
        # E.g. "Top {n} transactions from {entity_owner}" →
        # r"^Top (?P<n>\d+) transactions from (?P<entity_owner>.+?)$"
        nl = template["nl_seed"]
        for slot, slot_def in template["slots"].items():
            placeholder = "{" + slot + "}"
            pattern = self._slot_to_pattern(slot, slot_def)
            nl = nl.replace(placeholder, f"(?P<{slot}>{pattern})")
        return re.compile(nl, re.IGNORECASE)

    def predict(self, nl):
        # Try each template in order
        for tpl, pat in zip(self.templates, self.patterns):
            m = pat.fullmatch(nl.strip())
            if m:
                slots = m.groupdict()
                return self._fill_template(tpl, slots)

        # Fallback: fuzzy match nl_seed (Jaccard token overlap)
        best_tpl = self._fuzzy_match(nl)
        if best_tpl and best_tpl["score"] > 0.6:
            return self._fill_with_linker(best_tpl["tpl"], nl)
        return None
```

### Slot regex patterns

```python
SLOT_PATTERNS = {
    "integer": r"\d+",
    "decimal_eth": r"\d+(?:\.\d+)?",
    "ethereum_address": r"0x[a-fA-F0-9]{40}",
    "entity_owner": r".+?",  # broad, will validate via linker
    "concept_class": r".+?",
    "date": r"\d{4}-\d{2}-\d{2}",
    "duration": r"(?:last \w+|\d+ days?|\d+ weeks?)",
}
```

### Fuzzy fallback

```python
def _fuzzy_match(self, nl):
    nl_tokens = set(nl.lower().split())
    best = None
    for tpl in self.templates:
        seed_tokens = set(tpl["nl_seed"].lower().split())
        # Remove placeholder tokens
        seed_tokens = {t for t in seed_tokens if not t.startswith("{")}
        jaccard = len(nl_tokens & seed_tokens) / len(nl_tokens | seed_tokens)
        if not best or jaccard > best["score"]:
            best = {"tpl": tpl, "score": jaccard}
    return best
```

### Slot filling với entity linker

Khi fuzzy match (không exact regex), dùng entity linker để fill slot:

```python
def _fill_with_linker(self, tpl, nl):
    matches = self.entity_linker.link(nl)
    slots = {}
    for slot_name, slot_def in tpl["slots"].items():
        if slot_def["type"] == "entity_owner":
            # Pick first entity match
            slots[slot_name] = matches[0].matched_to if matches else None
        elif slot_def["type"] == "integer":
            # Extract number from NL
            m = re.search(r"\b(\d+)\b", nl)
            slots[slot_name] = m.group(1) if m else slot_def.get("default", "10")
        # ...
    return self._fill_template(tpl, slots)
```

### Coverage analysis

```python
def coverage_report(test_set):
    matched = 0
    for case in test_set:
        pred = b0.predict(case["nl"])
        if pred is not None:
            matched += 1
    return matched / len(test_set)
```

Coverage rate là metric quan trọng cho B0 — phản ánh "rule-based limit". Báo cáo trong thesis.

## Rủi ro & note

- **Templates không phủ realistic NL:** B0 sẽ có coverage rất thấp (cố ý). Đó là evidence cho LLM-based approach.
- **Regex brittle:** entity owner có space ("Binance Hot Wallet") làm regex `.+?` có thể greedy mất. Solution: priority sort templates dài trước (most specific first).
- **B0 không nhập nhằng:** nếu nl match nhiều templates → pick first OR pick longest. Document trong code.

## Estimated effort

1 ngày.

## Trạng thái

todo
