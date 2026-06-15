# T4.3 — Class Resolver (Hierarchical Concept-to-Triple)

## Mục tiêu

Module `ClassResolver` quyết định cách inject entity vào SPARQL: là `VALUES` clause (instance addresses) hay class triple pattern (`?x a :Class`).

## Bối cảnh & lý do

Đặc thù 3 (xem `00-PROJECT_OVERVIEW.md`): hierarchical dictionary 2 tầng. Cùng ý tưởng "transactions to mixer" có 2 cách hiểu:
- **Concept-level:** "any mixer" → `?to a :MixerAccount`.
- **Instance-level:** "Tornado Cash specifically" → `VALUES ?to {0xabc... 0xdef...}`.

Resolver quyết định:
- Mention có alias/owner cụ thể → instance-level.
- Mention là common noun chỉ category → class-level.
- Mention "all major X" / "any X" / "exchanges" → class-level.

## Phụ thuộc

- T4.2 — `EntityLinker` đã có concept_class detection.
- T2.1 — Ontology với class hierarchy.

## Đầu vào

- Output của T4.2 (`EntityMatch` records).
- Câu hỏi NL gốc (cho linguistic clue).

## Đầu ra

- Module `src/nl2sparql/linking/class_resolver.py`.
- Tests `tests/test_class_resolver.py` ≥20 cases.
- Documentation `src/nl2sparql/linking/RESOLVER_RULES.md` giải thích rules.

## Acceptance criteria

- [ ] API: `resolve(matches: list[EntityMatch], nl: str) -> list[ResolvedEntity]`.
- [ ] Output mỗi entity có `triple_pattern` (string) inject vào SPARQL.
- [ ] Test cover 5 cases: pure instance, pure concept, ambiguous (default rule), "any X" trigger, "all X" trigger.
- [ ] Accuracy ≥90% trên test set 50 câu manual annotation.

## Hướng dẫn triển khai

### ResolvedEntity schema

```python
@dataclass
class ResolvedEntity:
    span: str
    resolution_type: str  # "instance" | "class" | "mixed"
    triple_pattern: str   # ready-to-inject SPARQL fragment
    var_name: str         # ?from, ?to, ?addr ...
    explanation: str      # for prompt context
```

### Resolution rules

Priority (top wins):

**Rule 1: Linguistic class trigger.**

Nếu NL chứa pattern: "any X", "all X", "every X", "X (plural common noun)" → class-level.

Examples:
- "any mixer" → `:MixerAccount`.
- "all exchanges" → `:ExchangeAccount`.
- "any DEX" → `:DEXProtocol`.

```python
CLASS_TRIGGERS = [
    r"\bany\s+(\w+)",
    r"\ball\s+(\w+s?)",
    r"\bevery\s+(\w+)",
    r"\bmajor\s+(\w+s?)",
]
```

**Rule 2: Plural common noun.**

"exchanges" (no specific name) → class.
"Binance" (proper noun, capitalized) → instance.

Heuristic: if span is in concept dictionary AND not in named entity dictionary → class.

**Rule 3: Default = instance (more specific).**

Nếu match cả concept và instance, ưu tiên instance.

Example: "Tornado Cash" match cả `MixerAccount` (class) và Tornado Cash entity (instance) → dùng instance addresses.

**Rule 4: Mixed (rare).**

Nếu user hỏi "transactions from Binance to any mixer" → 2 entities khác cách resolve. Resolver xử lý từng entity riêng.

### Triple pattern builder

```python
def build_instance_pattern(addresses, var_name):
    if len(addresses) == 1:
        return f"BIND(<{addresses[0]}> AS {var_name})"
    else:
        addr_list = " ".join(f"<{a}>" for a in addresses)
        return f"VALUES {var_name} {{ {addr_list} }}"

def build_class_pattern(class_uri, var_name):
    return f"{var_name} a {class_uri} ."
```

Examples:

```sparql
# instance, single
BIND(<0xabc...> AS ?from)

# instance, multiple (Binance ~30 addresses)
VALUES ?from { <0xabc...> <0xdef...> ... }

# class
?to a :MixerAccount .

# mixed (one entity each side)
VALUES ?from { <0x...> ... }
?to a :ExchangeAccount .
```

### Variable name assignment

Schema linker (T4.1) sẽ giúp suggest vars:
- "from X" → `?from`.
- "to Y" → `?to`.
- Default `?addr_<i>` if unclear.

Resolver cần coordinate với LLM Generator (T6.1) — có thể just pass triple_pattern và để LLM dùng làm hint.

### Prompt injection format

Output cuối cùng là string inject vào prompt LLM:

```
Linked entities:
- "Binance" → instance with 28 addresses
  Use: VALUES ?from { <0x...> ... <0x...> }
- "any mixer" → class :MixerAccount
  Use: ?to a :MixerAccount .
```

### Edge cases để test

- Entity ở vị trí object: "transactions to Binance" (object position).
- Entity là chủ ngữ: "Binance sent X" (subject).
- Entity với time qualifier: "Binance hot wallet last quarter" (vẫn instance).
- "DEX" alone (singular common noun, no "the"): class (ambiguous, rule lỏng).
- "the DEX" (with article + singular): có thể context-dependent, default class.

## Rủi ro & note

- **Tiếng Anh ambiguous:** "exchange" có thể là verb ("to exchange ETH") hoặc noun. NER + POS tag có thể cần. Defer nếu phức tạp.
- **Class hierarchy lookup:** "any DeFi protocol" → `:DEXProtocol ∪ :LendingProtocol`. Có thể dùng `?x a/rdfs:subClassOf* :DeFiProtocol`. Lưu ý SPARQL property path.
- **Variable naming clash:** nhiều entities cùng var → rename.

## Estimated effort

1 ngày.

## Trạng thái

todo
