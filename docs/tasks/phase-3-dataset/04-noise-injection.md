# T3.4 — Noise Injection (Bước D)

## Mục tiêu

Thêm noise tự nhiên (typo, viết tắt, câu không hoàn chỉnh) vào ~5% records để model robust với input thực tế.

## Bối cảnh & lý do

User thực không type câu hỏi hoàn hảo. Họ:
- Sai chính tả ("Binnace" thay vì "Binance").
- Viết tắt ("TC" thay "Tornado Cash", "txs" thay "transactions").
- Câu không hoàn chỉnh / fragment ("biggest tx last week binance to mixer").
- Chữ thường lẫn hoa lung tung ("binance to TORNADO").

Inject noise quá nhiều → confuse model. Quá ít → không học robustness. Tỉ lệ 5-10% là sweet spot theo literature.

## Phụ thuộc

- T3.3 — `synthetic-stage-c.jsonl` đã có ~3000 records.

## Đầu vào

- `data/dataset/raw/synthetic-stage-c.jsonl`.
- Abbreviation dictionary (build manual).

## Đầu ra

- File `data/dataset/raw/synthetic-stage-d.jsonl` — bổ sung ~5-10% noisy records.
- File `src/nl2sparql/dataset/abbreviations.json` — mapping {full_form: [abbrev_options]}.
- Notebook `notebooks/10_noise_injection.ipynb` với sample 30 noisy examples để verify quality.

## Acceptance criteria

- [ ] Tổng ~3000 records (3000 từ stage C + ~150-300 noisy variants).
- [ ] Noisy records labeled `noise_type` ∈ {typo, abbrev, fragment, mixed_case}.
- [ ] Manual review 30 noisy records: ≥90% vẫn "decipherable" (con người vẫn hiểu).
- [ ] SPARQL gold KHÔNG đổi (chỉ NL đổi).

## Hướng dẫn triển khai

### Abbreviation dictionary

```json
{
  "transaction": ["tx", "txn", "txs"],
  "transactions": ["txs", "txns"],
  "address": ["addr", "addy"],
  "Tornado Cash": ["TC", "tornado", "tornado.cash"],
  "Binance": ["BN", "binance hot wallet", "binance hot"],
  "Uniswap": ["UNI", "uni"],
  "Ethereum": ["ETH", "eth"],
  "between": ["btwn", "btw"],
  "greater than": [">", "gt", "more than", "over"],
  "less than": ["<", "lt", "under"],
  "from": ["frm"],
  "to": ["->", "to"],
  ...
}
```

### Noise functions

```python
def inject_typo(text: str, rate: float = 0.05) -> str:
    """Random char swap, delete, double-press."""
    chars = list(text)
    for i in range(len(chars)):
        if random.random() < rate and chars[i].isalpha():
            op = random.choice(["swap", "delete", "double", "neighbor"])
            if op == "swap" and i+1 < len(chars):
                chars[i], chars[i+1] = chars[i+1], chars[i]
            elif op == "delete":
                chars[i] = ""
            elif op == "double":
                chars[i] = chars[i] * 2
            elif op == "neighbor":
                chars[i] = keyboard_neighbor(chars[i])
    return "".join(chars)

def inject_abbrev(text: str, abbrev_dict) -> str:
    for full, abbrevs in abbrev_dict.items():
        if full.lower() in text.lower() and random.random() < 0.4:
            text = re.sub(full, random.choice(abbrevs), text, flags=re.I)
    return text

def inject_fragment(text: str) -> str:
    """Drop articles, contractions, modal verbs."""
    drops = ["the ", "a ", "an ", "what is ", "what are ", "show me ", "could you "]
    for d in drops:
        text = text.replace(d, "")
    return text.strip()

def inject_case(text: str) -> str:
    """Random caps."""
    return "".join(c.upper() if random.random() < 0.2 else c.lower() for c in text)
```

### Pipeline

```python
def process_record(rec, noise_rate=0.05):
    if random.random() > noise_rate:
        return [rec]  # keep as-is

    # Pick noise type (or combine)
    noise_type = random.choice([
        "typo", "abbrev", "fragment", "mixed_case",
        "typo+abbrev", "abbrev+fragment"
    ])

    new_nl = rec["nl"]
    if "typo" in noise_type:
        new_nl = inject_typo(new_nl)
    if "abbrev" in noise_type:
        new_nl = inject_abbrev(new_nl, ABBREV_DICT)
    if "fragment" in noise_type:
        new_nl = inject_fragment(new_nl)
    if "mixed_case" in noise_type:
        new_nl = inject_case(new_nl)

    noisy_rec = dict(rec)
    noisy_rec["id"] = rec["id"] + f"-noise-{noise_type}"
    noisy_rec["nl"] = new_nl
    noisy_rec["nl_original"] = rec["nl"]
    noisy_rec["noise_type"] = noise_type

    # Return BOTH original and noisy (data augmentation)
    return [rec, noisy_rec]
```

### Quality control

- **Manual review 30 records:** đọc và confirm con người vẫn hiểu được câu hỏi.
- Reject record nếu noise quá nặng đến mức không decipher được.
- Chừa lại nl_original để analysis sau (ablation: train có/không noise).

### Optional: realistic typo from corpus

Có thể dùng GitHub's `wikipedia-common-misspellings` hoặc `holbrook-misspellings` thay vì random typo nếu muốn realistic hơn.

## Rủi ro & note

- **Inject quá rate hoặc quá thô:** đọc 30 examples để calibrate.
- **Abbreviation phá entity:** "TC" có thể ambiguous. Track entity preservation: nếu record có abbrev mà entity dictionary không lookup được → log warning.
- **SPARQL gold không đổi:** double check, đây là invariant.

## Estimated effort

0.5 ngày.

## Trạng thái

todo
