# T2.2 Chain-Aware Entity Dictionary Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild T2.2 as an offline, deterministic Ethereum-mainnet dictionary whose entities carry explicit address roles and immutable row-level provenance.

**Architecture:** Compile a committed CoinGecko chain-aware JSON snapshot and reviewed pinned source rows into one canonical CSV, then project that CSV through the existing dictionary builder. Fail-closed schema and artifact validation enforce `chain_id=1`, role semantics, provenance, coverage, and regression boundaries without executing network calls or upstream JavaScript.

**Tech Stack:** Python 3.11, standard-library `csv`/`hashlib`/`json`/`pathlib`, pytest 8, Ruff, committed JSON/CSV snapshots.

## Global Constraints

- T2.2 accepts only Ethereum mainnet records with integer `chain_id = 1`.
- `address_role` is exactly one of `operational`, `token`, or `treasury`.
- Every source has an immutable `source_revision` and non-empty `source_locator`.
- Unit tests and artifact validation perform no network access and execute no upstream JavaScript.
- Dictionary output remains deterministically sorted and contains at least 3,000 entities, 1,000 aliases, and 8-12 concepts.
- Top-30 exchange and top-50 DeFi protocol owner coverage remains mandatory.
- Flow-query consumers may sample only `operational` records.

---

## File structure

- Modify `src/nl2sparql/linking/dictionary/schema.py`: validate chain IDs, address roles, source revisions, and source locators.
- Modify `scripts/03_fetch_entity_labels.py`: deterministic compiler for CoinGecko JSON plus reviewed CSV.
- Modify `src/nl2sparql/linking/dictionary/build.py`: propagate chain, role, and immutable provenance into artifacts.
- Modify `src/nl2sparql/linking/dictionary/validate.py`: enforce chain-aware artifact and operational-coverage reporting.
- Create `data/entity_dictionary/raw/coingecko-uniswap-all.json`: committed mainnet token source snapshot.
- Create `data/entity_dictionary/curated/reviewed_ethereum_entities.csv`: reviewed exchange/protocol evidence rows.
- Regenerate `data/entity_dictionary/raw/entities.csv`: canonical compiler output.
- Regenerate `src/nl2sparql/linking/dictionary/entities.json`: chain-aware entity records.
- Regenerate `src/nl2sparql/linking/dictionary/concepts.json`: owner instance coverage.
- Regenerate `src/nl2sparql/linking/dictionary/aliases.json`: deterministic unambiguous aliases.
- Modify `tests/unit/test_entity_dictionary_schema.py`: schema, compiler, builder, and seven-case regressions.
- Modify `tests/unit/test_entity_dictionary_artifacts.py`: full committed-artifact contract and coverage reports.
- Create `docs/research/entity-dictionary-manual-sample-remediated-2026-08-09.md`: independent new-seed audit evidence.
- Modify `src/nl2sparql/linking/dictionary/sources.md`: immutable snapshot provenance and audit result.
- Modify `docs/tasks/phase-2-kg/02-entity-dictionary.md`: acceptance status and evidence.
- Modify `docs/memory/05-DECISION_LOG.md`: approved address-role and fail-closed source decisions.

---

### Task 1: Chain-aware schema contract

**Files:**
- Modify: `src/nl2sparql/linking/dictionary/schema.py`
- Modify: `tests/unit/test_entity_dictionary_schema.py`

**Interfaces:**
- Produces: `validate_chain_id(value: str | int) -> int`
- Produces: `validate_address_role(value: str) -> str`
- Produces: `validate_source_revision(value: str) -> str`
- Produces: `validate_source_locator(value: str) -> str`

- [ ] **Step 1: Write failing validator tests**

Append tests that define the accepted values and fail-closed boundary:

```python
@pytest.mark.parametrize("value", [1, "1"])
def test_validate_chain_id_accepts_ethereum_mainnet(value):
    assert validate_chain_id(value) == 1


@pytest.mark.parametrize("value", [10, "42161", "ethereum", ""])
def test_validate_chain_id_rejects_non_mainnet_or_ambiguous_values(value):
    with pytest.raises(DictionaryValidationError, match="Ethereum chain_id"):
        validate_chain_id(value)


@pytest.mark.parametrize("role", ["operational", "token", "treasury"])
def test_validate_address_role_accepts_closed_vocabulary(role):
    assert validate_address_role(role) == role


def test_validate_address_role_rejects_unknown_role():
    with pytest.raises(DictionaryValidationError, match="address_role"):
        validate_address_role("protocol")


@pytest.mark.parametrize(
    "revision",
    ["sha256:" + "a" * 64, "0123456789abcdef0123456789abcdef01234567"],
)
def test_validate_source_revision_accepts_digest_or_git_sha(revision):
    assert validate_source_revision(revision) == revision


@pytest.mark.parametrize("revision", ["main", "master", "latest", ""])
def test_validate_source_revision_rejects_mutable_or_empty_values(revision):
    with pytest.raises(DictionaryValidationError, match="source_revision"):
        validate_source_revision(revision)


def test_validate_source_locator_rejects_blank_value():
    with pytest.raises(DictionaryValidationError, match="source_locator"):
        validate_source_locator("  ")
```

- [ ] **Step 2: Run the schema tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_entity_dictionary_schema.py -q
```

Expected: collection fails because the four validators are not exported by
`schema.py`.

- [ ] **Step 3: Implement the minimal closed validators**

Add constants and functions:

```python
VALID_ADDRESS_ROLES = {"operational", "token", "treasury"}
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_chain_id(value: str | int) -> int:
    if value not in (1, "1"):
        raise DictionaryValidationError(
            f"Expected Ethereum chain_id 1, received: {value!r}"
        )
    return 1


def validate_address_role(value: str) -> str:
    if value not in VALID_ADDRESS_ROLES:
        raise DictionaryValidationError(f"Invalid address_role: {value!r}")
    return value


def validate_source_revision(value: str) -> str:
    if not isinstance(value, str) or not (
        GIT_SHA_RE.fullmatch(value) or SHA256_RE.fullmatch(value)
    ):
        raise DictionaryValidationError(f"Invalid source_revision: {value!r}")
    return value


def validate_source_locator(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DictionaryValidationError(f"Invalid source_locator: {value!r}")
    return value.strip()
```

- [ ] **Step 4: Run the schema tests and verify GREEN**

Run `uv run pytest tests/unit/test_entity_dictionary_schema.py -q` and expect all
schema tests to pass.

- [ ] **Step 5: Commit the schema contract**

```bash
git add src/nl2sparql/linking/dictionary/schema.py tests/unit/test_entity_dictionary_schema.py
git commit -m "feat(linking): enforce chain-aware entity schema"
```

---

### Task 2: Deterministic source snapshot compiler

**Files:**
- Modify: `scripts/03_fetch_entity_labels.py`
- Modify: `tests/unit/test_entity_dictionary_schema.py`

**Interfaces:**
- Consumes: the four validators from Task 1
- Produces: `rows_from_coingecko(snapshot: dict[str, object], revision: str, retrieved_date: str) -> list[dict[str, str]]`
- Produces: `read_reviewed_rows(path: Path) -> list[dict[str, str]]`
- Produces: `compile_rows(token_rows: list[dict[str, str]], reviewed_rows: list[dict[str, str]]) -> list[dict[str, str]]`
- Preserves: `write_rows(rows: list[dict[str, str]], output: Path) -> None`

- [ ] **Step 1: Write failing compiler tests**

Load the script with `importlib.util.spec_from_file_location` and add focused
fixtures:

```python
def valid_chain_aware_row(*, address: str) -> dict[str, str]:
    return {
        "address": address,
        "primary_label": "Reviewed entity",
        "owner": "Reviewed Owner",
        "category": "dex",
        "concept_class": "DEXProtocol",
        "aliases": "reviewed owner",
        "chain_id": "1",
        "address_role": "operational",
        "source_name": "reviewed_source",
        "source_url": "https://example.test/pinned-source",
        "source_revision": "a" * 40,
        "source_locator": "projects/reviewed/index.js:L1-L4",
        "retrieved_date": "2026-08-09",
        "confidence": "high",
    }


def test_coingecko_compiler_keeps_only_exact_ethereum_mainnet_tokens(fetcher):
    snapshot = {
        "tokens": [
            {"chainId": 1, "address": "0x" + "1" * 40, "name": "One", "symbol": "ONE"},
            {"chainId": 42161, "address": "0x" + "2" * 40, "name": "Two", "symbol": "TWO"},
        ]
    }

    rows = fetcher.rows_from_coingecko(
        snapshot, revision="sha256:" + "a" * 64, retrieved_date="2026-08-09"
    )

    assert len(rows) == 1
    assert rows[0]["chain_id"] == "1"
    assert rows[0]["address_role"] == "token"
    assert rows[0]["source_locator"] == "/tokens/0"


def test_coingecko_compiler_rejects_address_prefix_embedded_in_long_identifier(fetcher):
    snapshot = {
        "tokens": [{
            "chainId": 1,
            "address": "0x" + "3" * 64,
            "name": "Aptos-shaped",
            "symbol": "BAD",
        }]
    }
    with pytest.raises(DictionaryValidationError, match="Invalid Ethereum address"):
        fetcher.rows_from_coingecko(
            snapshot, revision="sha256:" + "b" * 64, retrieved_date="2026-08-09"
        )


def test_compile_rows_rejects_duplicate_address_across_sources(fetcher):
    row = valid_chain_aware_row(address="0x" + "4" * 40)
    with pytest.raises(DictionaryValidationError, match="Duplicate Ethereum entity"):
        fetcher.compile_rows([row], [dict(row)])
```

Add parameterized regression rows for the audited non-Ethereum addresses and
assert that a reviewed row with `chain_id` other than `1`, a missing locator, or
an address longer than 42 characters is rejected. The named cases are
`swissborg_arbitrum`, `bitget_bsc`, `kelp_zksync`, `buidl_aptos`, `curve_base`,
`spiko_polygon`, and `avalon_mantle`.

- [ ] **Step 2: Run compiler tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_entity_dictionary_schema.py -q
```

Expected: the new compiler functions do not exist.

- [ ] **Step 3: Implement strict source adapters and merge**

Expand `FIELDS` with `chain_id`, `address_role`, `source_revision`, and
`source_locator`. Implement CoinGecko conversion using exact JSON fields, and
validate every reviewed CSV row before merge:

```python
def compile_rows(
    token_rows: list[dict[str, str]], reviewed_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    merged: dict[tuple[int, str], dict[str, str]] = {}
    for row in [*token_rows, *reviewed_rows]:
        chain_id = validate_chain_id(row["chain_id"])
        address_lower = normalize_address(row["address"])
        validate_address_role(row["address_role"])
        validate_source_revision(row["source_revision"])
        validate_source_locator(row["source_locator"])
        key = (chain_id, address_lower)
        if key in merged:
            raise DictionaryValidationError(
                f"Duplicate Ethereum entity across sources: {address_lower}"
            )
        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (row["category"], row["owner"], row["address"].lower()),
    )
```

The CLI requires `--coingecko-snapshot`, `--reviewed-rows`, and
`--retrieved-date`; it computes the CoinGecko file SHA-256 itself and writes only
the canonical CSV.

- [ ] **Step 4: Run compiler tests and verify GREEN**

Run `uv run pytest tests/unit/test_entity_dictionary_schema.py -q` and expect all
tests to pass.

- [ ] **Step 5: Commit the compiler**

```bash
git add scripts/03_fetch_entity_labels.py tests/unit/test_entity_dictionary_schema.py
git commit -m "feat(linking): compile fail-closed entity snapshots"
```

---

### Task 3: Propagate and validate chain-aware artifacts

**Files:**
- Modify: `src/nl2sparql/linking/dictionary/build.py`
- Modify: `src/nl2sparql/linking/dictionary/validate.py`
- Modify: `tests/unit/test_entity_dictionary_schema.py`
- Modify: `tests/unit/test_entity_dictionary_artifacts.py`

**Interfaces:**
- Consumes: canonical CSV fields from Task 2
- Extends: `build_dictionary(raw_path: Path, concepts_path: Path) -> dict[str, Any]`
- Extends: `validate_artifacts(...) -> dict[str, int]` with `operational_entity_count`

- [ ] **Step 1: Update fixtures and write failing propagation tests**

Change test CSV headers and rows to include the four new fields, then assert:

```python
entry = built["entities"][0]
assert entry["chain_id"] == 1
assert entry["address_role"] == "operational"
assert entry["sources"][0]["revision"] == "a" * 40
assert entry["sources"][0]["locator"] == "projects/curve/index.js:L10-L14"
```

Add artifact-fixture tests that reject missing chain IDs, invalid roles,
mutable-only revisions, blank locators, and duplicate addresses.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_entity_dictionary_schema.py tests/unit/test_entity_dictionary_artifacts.py -q
```

Expected: builder output lacks the new fields and artifact validation does not
enforce them.

- [ ] **Step 3: Propagate validated fields in the builder**

Add to each entity:

```python
"chain_id": validate_chain_id(row["chain_id"]),
"address_role": validate_address_role(row["address_role"]),
```

Replace the provenance payload with:

```python
{
    "name": row["source_name"],
    "url": row["source_url"],
    "revision": validate_source_revision(row["source_revision"]),
    "locator": validate_source_locator(row["source_locator"]),
    "retrieved_date": row["retrieved_date"],
    "note": f"{row['address_role'].title()} evidence for {row['owner']}",
}
```

- [ ] **Step 4: Enforce the final artifact contract**

Require `chain_id` and `address_role` in every entity; require `revision` and
`locator` in every source. Count operational entries and return it in the report:

```python
operational_entity_count = sum(
    entry["address_role"] == "operational" for entry in entities
)
return {
    "entity_count": len(entities),
    "concept_count": len(concepts),
    "alias_count": len(aliases),
    "operational_entity_count": operational_entity_count,
}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run `uv run pytest tests/unit/test_entity_dictionary_schema.py tests/unit/test_entity_dictionary_artifacts.py -q` and expect all tests to pass.

- [ ] **Step 6: Commit builder and validator changes**

```bash
git add src/nl2sparql/linking/dictionary/build.py src/nl2sparql/linking/dictionary/validate.py tests/unit/test_entity_dictionary_schema.py tests/unit/test_entity_dictionary_artifacts.py
git commit -m "feat(linking): preserve entity chain roles and provenance"
```

---

### Task 4: Rebuild the reviewed snapshot and artifacts

**Files:**
- Create: `data/entity_dictionary/raw/coingecko-uniswap-all.json`
- Create: `data/entity_dictionary/curated/reviewed_ethereum_entities.csv`
- Regenerate: `data/entity_dictionary/raw/entities.csv`
- Regenerate: `src/nl2sparql/linking/dictionary/entities.json`
- Regenerate: `src/nl2sparql/linking/dictionary/concepts.json`
- Regenerate: `src/nl2sparql/linking/dictionary/aliases.json`
- Modify: `tests/unit/test_entity_dictionary_artifacts.py`

**Interfaces:**
- Consumes: compiler CLI from Task 2 and builder CLI from Task 3
- Produces: committed chain-aware T2.2 artifacts

- [ ] **Step 1: Write acceptance assertions before replacing data**

Extend committed-artifact tests:

```python
assert {entry["chain_id"] for entry in entities} == {1}
assert {entry["address_role"] for entry in entities} <= {
    "operational", "token", "treasury"
}
assert all(source["revision"] for entry in entities for source in entry["sources"])
assert all(source["locator"] for entry in entities for source in entry["sources"])
assert report["operational_entity_count"] > 0
```

Compute owner coverage by role and assert every top exchange has at least one
`treasury` row. Assert every top protocol has at least one Ethereum row, while
reporting the subset with `operational` rows separately.

- [ ] **Step 2: Run acceptance tests against the old artifact and verify RED**

Run `uv run pytest tests/unit/test_entity_dictionary_artifacts.py -q` and expect
failure on missing chain-aware fields.

- [ ] **Step 3: Acquire and pin the CoinGecko source snapshot**

Download `https://tokens.coingecko.com/uniswap/all.json` to the declared raw
snapshot path. Confirm its top-level `tokens` list, `chainId=1` rows, exact
address shape, and SHA-256 before compilation. This is the only bulk automated
source and remains committed for offline reproducibility.

```bash
curl --fail --location --retry 3 \
  --output data/entity_dictionary/raw/coingecko-uniswap-all.json \
  https://tokens.coingecko.com/uniswap/all.json
sha256sum data/entity_dictionary/raw/coingecko-uniswap-all.json
uv run python -c 'import json; from pathlib import Path; p=Path("data/entity_dictionary/raw/coingecko-uniswap-all.json"); d=json.loads(p.read_text()); assert isinstance(d["tokens"], list); assert sum(t.get("chainId") == 1 for t in d["tokens"]) >= 3000'
```

- [ ] **Step 4: Build reviewed exchange and protocol evidence rows**

For every owner in `coverage.json`, add at least one row whose pinned URL,
40-character Git commit or committed-snapshot SHA-256, and locator establish the
Ethereum chain and role. Exchange rows use `treasury`. Protocol rows use
`operational` only for explicit deployments and otherwise use `token`. Exclude
all seven failed sample records and reject any row whose evidence only shows a
different chain.

Use this exact CSV header:

```csv
address,primary_label,owner,category,concept_class,aliases,chain_id,address_role,source_name,source_url,source_revision,source_locator,retrieved_date,confidence
```

Before compilation, verify the manifest covers the declared owner sets:

```bash
uv run python - <<'PY'
import csv, json
from pathlib import Path

coverage = json.loads(Path("data/entity_dictionary/curated/coverage.json").read_text())
with Path("data/entity_dictionary/curated/reviewed_ethereum_entities.csv").open(newline="") as handle:
    rows = list(csv.DictReader(handle))
owners = {row["owner"] for row in rows}
assert set(coverage["top_exchanges"]) <= owners
assert set(coverage["top_defi_protocols"]) <= owners
assert all(row["chain_id"] == "1" for row in rows)
assert all(row["source_revision"] and row["source_locator"] for row in rows)
PY
```

- [ ] **Step 5: Compile and build deterministic artifacts**

Run:

```bash
uv run python scripts/03_fetch_entity_labels.py \
  --coingecko-snapshot data/entity_dictionary/raw/coingecko-uniswap-all.json \
  --reviewed-rows data/entity_dictionary/curated/reviewed_ethereum_entities.csv \
  --retrieved-date 2026-08-09 \
  --output data/entity_dictionary/raw/entities.csv
uv run python -m nl2sparql.linking.dictionary.build
```

- [ ] **Step 6: Run focused tests and inspect counts**

Run:

```bash
uv run pytest tests/unit/test_entity_dictionary_schema.py tests/unit/test_entity_dictionary_artifacts.py -q
uv run python -c 'from nl2sparql.linking.dictionary.validate import validate_artifacts; print(validate_artifacts())'
```

Expected: at least 3,000 entities, at least 1,000 aliases, 8-12 concepts, all
required owners covered, all chain IDs equal to 1, and all provenance valid.

- [ ] **Step 7: Commit source snapshots and generated artifacts**

```bash
git add data/entity_dictionary src/nl2sparql/linking/dictionary tests/unit/test_entity_dictionary_artifacts.py
git commit -m "data(linking): rebuild verified Ethereum entity snapshot"
```

---

### Task 5: Independent audit and documentation closure

**Files:**
- Create: `docs/research/entity-dictionary-manual-sample-remediated-2026-08-09.md`
- Modify: `src/nl2sparql/linking/dictionary/sources.md`
- Modify: `docs/tasks/phase-2-kg/02-entity-dictionary.md`
- Modify: `docs/memory/05-DECISION_LOG.md`

**Interfaces:**
- Consumes: final committed artifact from Task 4
- Produces: manual acceptance evidence and honest downstream role boundary

- [ ] **Step 1: Draw an independent fixed sample**

Use `random.Random(20260809).sample(range(len(entities)), 50)` against the final
sorted `entities.json`. Record index, address, owner, category, role, source,
observed evidence, and verdict for all 50 rows.

- [ ] **Step 2: Verify source evidence independently**

For CoinGecko rows, confirm exact address/name and `chainId=1` in the committed
snapshot. For reviewed rows, open the pinned revision and locator and confirm
owner, Ethereum context, and claimed role. Do not use the generated dictionary
as evidence for itself.

- [ ] **Step 3: Record and evaluate the audit**

The report passes only with zero critical chain/address errors and no more than
one minor metadata error. A critical error keeps the T2.2 manual checkbox open
and returns implementation to Task 4.

- [ ] **Step 4: Update source, task, and decision documentation**

Document source snapshot hashes, pinned DefiLlama commit(s), row counts by source
and role, the new sample method/result, and the rule that flow queries consume
only `operational` addresses. Mark the manual checkbox complete only if Step 3
passes.

- [ ] **Step 5: Run complete verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
git diff --check
git status --short
```

Expected: the full suite passes, Ruff and diff checks are clean, and status
contains only the intended documentation changes before commit.

- [ ] **Step 6: Commit acceptance evidence**

```bash
git add docs/research/entity-dictionary-manual-sample-remediated-2026-08-09.md src/nl2sparql/linking/dictionary/sources.md docs/tasks/phase-2-kg/02-entity-dictionary.md docs/memory/05-DECISION_LOG.md
git commit -m "docs(linking): accept remediated entity dictionary"
```
