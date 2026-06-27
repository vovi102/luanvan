# T2.2 Entity Dictionary v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible Ethereum entity dictionary snapshot with at least 3000 externally sourced address entries, at least 1000 aliases, and 8-12 concept categories for Phase 4 entity linking.

**Architecture:** Separate artifact validation, source ingestion, and committed outputs. Tests run offline against committed snapshots; live fetchers are optional acquisition tools that write raw snapshots first and never run in CI.

**Tech Stack:** Python 3.11, stdlib `json`/`csv`/`dataclasses`/`pathlib`, pytest, optional `requests`/`beautifulsoup4` only if already available through project dependencies.

---

## File structure

- Create `src/nl2sparql/linking/dictionary/__init__.py`: package paths for dictionary artifacts.
- Create `src/nl2sparql/linking/dictionary/schema.py`: normalization helpers and validation errors.
- Create `src/nl2sparql/linking/dictionary/build.py`: deterministic builder from raw CSV/JSON snapshots to final JSON artifacts.
- Create `src/nl2sparql/linking/dictionary/validate.py`: offline validator used by tests.
- Create `src/nl2sparql/linking/dictionary/entities.json`: committed real-source entity snapshot.
- Create `src/nl2sparql/linking/dictionary/concepts.json`: committed concept metadata.
- Create `src/nl2sparql/linking/dictionary/aliases.json`: committed alias map.
- Create `src/nl2sparql/linking/dictionary/sources.md`: provenance and manual verification boundary.
- Create `data/entity_dictionary/raw/entities.csv`: source snapshot rows with real addresses and source URLs.
- Create `data/entity_dictionary/curated/concepts.json`: concept definitions.
- Create `data/entity_dictionary/curated/coverage.json`: required top-30 exchange and top-50 DeFi owner lists.
- Create `scripts/03_fetch_entity_labels.py`: optional polite fetcher that writes raw CSV rows.
- Create `notebooks/05_dict_eda.ipynb`: lightweight EDA notebook.
- Create `tests/unit/test_entity_dictionary_schema.py`: unit tests for normalization and builder behavior.
- Create `tests/unit/test_entity_dictionary_artifacts.py`: offline acceptance tests for committed artifacts.
- Modify `docs/tasks/phase-2-kg/02-entity-dictionary.md`: status and evidence.
- Modify `docs/memory/05-DECISION_LOG.md`: snapshot-vs-live-scraping decision.

---

## Task 1: Schema and artifact path helpers

**Files:**
- Create: `src/nl2sparql/linking/dictionary/__init__.py`
- Create: `src/nl2sparql/linking/dictionary/schema.py`
- Test: `tests/unit/test_entity_dictionary_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/unit/test_entity_dictionary_schema.py`:

```python
import pytest

from nl2sparql.linking.dictionary.schema import (
    DictionaryValidationError,
    normalize_alias,
    normalize_address,
    validate_confidence,
)


def test_normalize_alias_lowercases_trims_and_collapses_spaces():
    assert normalize_alias("  Binance   Hot Wallet  ") == "binance hot wallet"


def test_normalize_address_returns_lowercase_key():
    assert (
        normalize_address("0x28C6c06298d514Db089934071355E5743bf21d60")
        == "0x28c6c06298d514db089934071355e5743bf21d60"
    )


def test_normalize_address_rejects_malformed_value():
    with pytest.raises(DictionaryValidationError, match="Invalid Ethereum address"):
        normalize_address("0x1234")


def test_validate_confidence_accepts_known_values():
    assert validate_confidence("high") == "high"
    assert validate_confidence("medium") == "medium"
    assert validate_confidence("low") == "low"


def test_validate_confidence_rejects_unknown_value():
    with pytest.raises(DictionaryValidationError, match="Invalid confidence"):
        validate_confidence("certain")
```

- [ ] **Step 2: Run and verify RED**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_schema.py -q
```

Expected: import failure because `nl2sparql.linking.dictionary.schema` does not exist.

- [ ] **Step 3: Implement package paths and schema helpers**

Create `src/nl2sparql/linking/dictionary/__init__.py`:

```python
"""Entity dictionary artifacts and validation helpers for Ethereum KG linking."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ENTITIES_PATH = PACKAGE_DIR / "entities.json"
CONCEPTS_PATH = PACKAGE_DIR / "concepts.json"
ALIASES_PATH = PACKAGE_DIR / "aliases.json"
SOURCES_PATH = PACKAGE_DIR / "sources.md"

__all__ = ["PACKAGE_DIR", "ENTITIES_PATH", "CONCEPTS_PATH", "ALIASES_PATH", "SOURCES_PATH"]
```

Create `src/nl2sparql/linking/dictionary/schema.py`:

```python
from __future__ import annotations

import re

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
VALID_CONFIDENCE = {"high", "medium", "low"}


class DictionaryValidationError(ValueError):
    """Raised when an entity dictionary artifact is malformed."""


def normalize_alias(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    if not normalized:
        raise DictionaryValidationError("Alias must not be empty")
    return normalized


def normalize_address(value: str) -> str:
    if not isinstance(value, str) or not ADDRESS_RE.match(value):
        raise DictionaryValidationError(f"Invalid Ethereum address: {value!r}")
    return value.lower()


def validate_confidence(value: str) -> str:
    if value not in VALID_CONFIDENCE:
        raise DictionaryValidationError(f"Invalid confidence: {value!r}")
    return value
```

- [ ] **Step 4: Run and verify GREEN**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_schema.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nl2sparql/linking/dictionary/__init__.py src/nl2sparql/linking/dictionary/schema.py tests/unit/test_entity_dictionary_schema.py
git commit -m "feat(linking): add entity dictionary schema helpers"
```

---

## Task 2: Builder for real-source raw snapshots

**Files:**
- Create: `src/nl2sparql/linking/dictionary/build.py`
- Create: `data/entity_dictionary/curated/concepts.json`
- Modify: `tests/unit/test_entity_dictionary_schema.py`

- [ ] **Step 1: Write failing builder tests**

Append to `tests/unit/test_entity_dictionary_schema.py`:

```python
import csv
import json

from nl2sparql.linking.dictionary.build import build_dictionary


def test_build_dictionary_merges_real_source_rows_and_sorts_outputs(tmp_path):
    raw_path = tmp_path / "entities.csv"
    concepts_path = tmp_path / "concepts.json"
    raw_path.write_text(
        "\n".join(
            [
                "address,primary_label,owner,category,concept_class,aliases,source_name,source_url,retrieved_date,confidence",
                "0x28C6c06298d514Db089934071355E5743bf21d60,Binance: Hot Wallet 14,Binance,exchange,ExchangeAccount,binance|binance hot wallet,etherscan,https://etherscan.io/address/0x28C6c06298d514Db089934071355E5743bf21d60,2026-06-28,high",
                "0x0000000000000000000000000000000000000000,Curve: Registry,Curve,dex,DEXProtocol,curve|curve protocol,curated_seed,https://curve.fi,2026-06-28,medium",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    concepts_path.write_text(
        json.dumps(
            {
                "exchange": {
                    "ontology_class": "https://thesis.example.org/eth-kg/ExchangeAccount",
                    "aliases": ["exchange", "cex"],
                    "description": "Centralized exchange accounts",
                },
                "dex": {
                    "ontology_class": "https://thesis.example.org/eth-kg/DEXProtocol",
                    "aliases": ["dex", "amm"],
                    "description": "Decentralized exchange protocols",
                },
            }
        ),
        encoding="utf-8",
    )

    built = build_dictionary(raw_path, concepts_path)

    assert [entry["owner"] for entry in built["entities"]] == ["Curve", "Binance"]
    assert built["entities"][0]["address_lower"] == "0x0000000000000000000000000000000000000000"
    assert built["aliases"]["binance hot wallet"] == "Binance"
    assert built["concepts"]["exchange"]["instances"] == ["Binance"]
```

- [ ] **Step 2: Run and verify RED**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_schema.py -q
```

Expected: import failure because `nl2sparql.linking.dictionary.build` does not exist.

- [ ] **Step 3: Implement builder**

Create `src/nl2sparql/linking/dictionary/build.py`:

```python
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from nl2sparql.linking.dictionary.schema import normalize_address, normalize_alias, validate_confidence


def _read_rows(raw_path: Path) -> list[dict[str, str]]:
    with raw_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _split_aliases(value: str) -> list[str]:
    return sorted({normalize_alias(part) for part in value.split("|") if part.strip()})


def build_dictionary(raw_path: Path, concepts_path: Path) -> dict[str, Any]:
    concepts = json.loads(concepts_path.read_text(encoding="utf-8"))
    entities: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    seen_addresses: set[str] = set()

    for concept in concepts.values():
        concept["instances"] = []

    for row in _read_rows(raw_path):
        address_lower = normalize_address(row["address"])
        if address_lower in seen_addresses:
            raise ValueError(f"Duplicate address in raw snapshot: {address_lower}")
        seen_addresses.add(address_lower)
        if row["category"] not in concepts:
            raise ValueError(f"Unknown category: {row['category']}")
        confidence = validate_confidence(row["confidence"])
        entry_aliases = _split_aliases(row["aliases"])
        entry_aliases.append(normalize_alias(row["owner"]))
        entry_aliases = sorted(set(entry_aliases))
        for alias in entry_aliases:
            existing = aliases.get(alias)
            if existing is not None and existing != row["owner"]:
                raise ValueError(f"Alias collision: {alias!r} maps to both {existing!r} and {row['owner']!r}")
            aliases[alias] = row["owner"]
        concepts[row["category"]]["instances"].append(row["owner"])
        entities.append(
            {
                "address": row["address"],
                "address_lower": address_lower,
                "primary_label": row["primary_label"],
                "owner": row["owner"],
                "category": row["category"],
                "concept_class": row["concept_class"],
                "aliases": entry_aliases,
                "sources": [
                    {
                        "name": row["source_name"],
                        "url": row["source_url"],
                        "retrieved_date": row["retrieved_date"],
                        "note": f"Raw snapshot label for {row['owner']}",
                    }
                ],
                "confidence": confidence,
                "verified_date": row["retrieved_date"],
            }
        )

    for concept in concepts.values():
        concept["instances"] = sorted(set(concept["instances"]))

    return {
        "entities": sorted(entities, key=lambda entry: (entry["category"], entry["owner"], entry["address_lower"])),
        "concepts": dict(sorted(concepts.items())),
        "aliases": dict(sorted(aliases.items())),
    }


def write_dictionary(built: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, filename in (("entities", "entities.json"), ("concepts", "concepts.json"), ("aliases", "aliases.json")):
        (output_dir / filename).write_text(
            json.dumps(built[key], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build T2.2 entity dictionary artifacts from raw snapshots.")
    parser.add_argument("--raw", type=Path, default=Path("data/entity_dictionary/raw/entities.csv"))
    parser.add_argument("--concepts", type=Path, default=Path("data/entity_dictionary/curated/concepts.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("src/nl2sparql/linking/dictionary"))
    args = parser.parse_args()
    write_dictionary(build_dictionary(args.raw, args.concepts), args.output_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add concept definitions**

Create `data/entity_dictionary/curated/concepts.json` with 10 concepts:

```json
{
  "bridge": {"ontology_class": "https://thesis.example.org/eth-kg/BridgeProtocol", "aliases": ["bridge", "cross chain bridge"], "description": "Cross-chain bridge protocols."},
  "dex": {"ontology_class": "https://thesis.example.org/eth-kg/DEXProtocol", "aliases": ["dex", "amm", "decentralized exchange", "swap"], "description": "Decentralized exchange protocols and router contracts."},
  "exchange": {"ontology_class": "https://thesis.example.org/eth-kg/ExchangeAccount", "aliases": ["exchange", "cex", "centralized exchange", "exchange wallet"], "description": "Centralized exchange-owned accounts and wallets."},
  "lending": {"ontology_class": "https://thesis.example.org/eth-kg/LendingProtocol", "aliases": ["lending", "borrow", "money market"], "description": "Lending and borrowing protocols."},
  "mev": {"ontology_class": "https://thesis.example.org/eth-kg/MEVActor", "aliases": ["mev", "searcher", "builder"], "description": "MEV searchers, builders, and relays."},
  "mixer": {"ontology_class": "https://thesis.example.org/eth-kg/MixerAccount", "aliases": ["mixer", "tumbler", "privacy tool"], "description": "Mixer or privacy-service accounts and contracts."},
  "nft_marketplace": {"ontology_class": "https://thesis.example.org/eth-kg/NFTMarketplace", "aliases": ["nft marketplace", "nft market"], "description": "NFT marketplace protocols and exchange contracts."},
  "stablecoin": {"ontology_class": "https://thesis.example.org/eth-kg/StablecoinIssuer", "aliases": ["stablecoin", "stable coin"], "description": "Stablecoin issuers and token contracts."},
  "staking": {"ontology_class": "https://thesis.example.org/eth-kg/StakingAccount", "aliases": ["staking", "validator", "liquid staking"], "description": "Staking and liquid-staking accounts."},
  "token_contract": {"ontology_class": "https://thesis.example.org/eth-kg/TokenContract", "aliases": ["token contract", "erc20", "erc721"], "description": "Token contracts and token issuer contracts."}
}
```

- [ ] **Step 5: Run tests and commit**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_schema.py -q
git add src/nl2sparql/linking/dictionary/build.py data/entity_dictionary/curated/concepts.json tests/unit/test_entity_dictionary_schema.py
git commit -m "feat(linking): add entity dictionary snapshot builder"
```

---

## Task 3: Offline artifact validator

**Files:**
- Create: `src/nl2sparql/linking/dictionary/validate.py`
- Create: `tests/unit/test_entity_dictionary_artifacts.py`

- [ ] **Step 1: Write failing validator tests**

Create `tests/unit/test_entity_dictionary_artifacts.py`:

```python
import json

import pytest

from nl2sparql.linking.dictionary import ALIASES_PATH, CONCEPTS_PATH, ENTITIES_PATH, SOURCES_PATH
from nl2sparql.linking.dictionary.schema import DictionaryValidationError
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts, validate_artifacts


def test_validate_artifacts_reports_missing_files(tmp_path):
    artifacts = DictionaryArtifacts(
        entities_path=tmp_path / "entities.json",
        concepts_path=tmp_path / "concepts.json",
        aliases_path=tmp_path / "aliases.json",
        sources_path=tmp_path / "sources.md",
    )

    with pytest.raises(DictionaryValidationError, match="Missing dictionary artifact"):
        validate_artifacts(artifacts, min_entities=1, min_aliases=1)


def test_committed_dictionary_artifacts_meet_t2_2_thresholds():
    report = validate_artifacts(min_entities=3000, min_aliases=1000)

    assert report["entity_count"] >= 3000
    assert 8 <= report["concept_count"] <= 12
    assert report["alias_count"] >= 1000


def test_committed_dictionary_covers_required_exchange_and_defi_owners():
    entities = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
    concepts = json.loads(CONCEPTS_PATH.read_text(encoding="utf-8"))
    owners = {entry["owner"] for entry in entities}

    required_exchanges = {
        "Binance", "Coinbase", "Kraken", "OKX", "Bitfinex", "Huobi",
        "KuCoin", "Crypto.com", "Gemini", "Bitstamp", "Bybit", "Gate.io",
        "MEXC", "Bittrex", "Poloniex", "Bithumb", "Upbit", "Bitget",
        "Deribit", "BitMEX", "Coincheck", "BitFlyer", "Luno", "WazirX",
        "AscendEX", "WhiteBIT", "BitMart", "Phemex", "Liquid", "Zaif",
    }
    required_defi = {
        "Uniswap V2", "Uniswap V3", "Curve", "Aave", "Compound", "MakerDAO",
        "Lido", "Balancer", "SushiSwap", "1inch", "Convex", "Yearn",
        "Synthetix", "Rocket Pool", "Frax", "EigenLayer", "Pendle", "GMX",
        "dYdX", "Ether.fi", "Renzo", "Morpho", "Spark", "Liquity",
        "Alchemix", "Gearbox", "Instadapp", "KyberSwap", "Bancor", "CoW Swap",
        "ParaSwap", "0x Protocol", "OpenSea", "Blur", "LooksRare", "Stargate",
        "Hop Protocol", "Across", "Synapse", "Arbitrum Bridge", "Optimism Bridge",
        "Polygon Bridge", "Base Bridge", "Tornado Cash", "Railgun", "Tether",
        "Circle", "Paxos", "Frax Finance", "Ethena",
    }

    assert required_exchanges <= owners
    assert required_defi <= owners
    assert set(concepts["exchange"]["instances"]) >= required_exchanges
    assert SOURCES_PATH.exists()
```

- [ ] **Step 2: Run and verify RED**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_artifacts.py -q
```

Expected: import failure because `validate.py` does not exist.

- [ ] **Step 3: Implement validator**

Create `src/nl2sparql/linking/dictionary/validate.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sparql.linking.dictionary import ALIASES_PATH, CONCEPTS_PATH, ENTITIES_PATH, SOURCES_PATH
from nl2sparql.linking.dictionary.schema import DictionaryValidationError, normalize_address, normalize_alias, validate_confidence


@dataclass(frozen=True)
class DictionaryArtifacts:
    entities_path: Path = ENTITIES_PATH
    concepts_path: Path = CONCEPTS_PATH
    aliases_path: Path = ALIASES_PATH
    sources_path: Path = SOURCES_PATH


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise DictionaryValidationError(f"Missing dictionary artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_artifacts(
    artifacts: DictionaryArtifacts = DictionaryArtifacts(),
    *,
    min_entities: int = 3000,
    min_aliases: int = 1000,
) -> dict[str, int]:
    entities = _load_json(artifacts.entities_path)
    concepts = _load_json(artifacts.concepts_path)
    aliases = _load_json(artifacts.aliases_path)
    if not artifacts.sources_path.exists():
        raise DictionaryValidationError(f"Missing dictionary artifact: {artifacts.sources_path}")
    if not isinstance(entities, list):
        raise DictionaryValidationError("entities.json must contain a list")
    if not isinstance(concepts, dict):
        raise DictionaryValidationError("concepts.json must contain an object")
    if not isinstance(aliases, dict):
        raise DictionaryValidationError("aliases.json must contain an object")
    if len(entities) < min_entities:
        raise DictionaryValidationError(f"entities.json has {len(entities)} entries; expected at least {min_entities}")
    if not 8 <= len(concepts) <= 12:
        raise DictionaryValidationError(f"concepts.json has {len(concepts)} concepts; expected 8-12")
    if len(aliases) < min_aliases:
        raise DictionaryValidationError(f"aliases.json has {len(aliases)} aliases; expected at least {min_aliases}")
    if list(aliases) != sorted(aliases):
        raise DictionaryValidationError("aliases.json keys must be sorted")

    concept_keys = set(concepts)
    owners = set()
    seen_addresses = set()
    entity_sort_keys = [(entry.get("category"), entry.get("owner"), entry.get("address_lower")) for entry in entities]
    if entity_sort_keys != sorted(entity_sort_keys):
        raise DictionaryValidationError("entities.json must be sorted by category, owner, address_lower")

    for concept_key, concept in concepts.items():
        if normalize_alias(concept_key) != concept_key:
            raise DictionaryValidationError(f"Concept key is not normalized: {concept_key!r}")
        for field in ("ontology_class", "aliases", "instances", "description"):
            if field not in concept:
                raise DictionaryValidationError(f"Concept {concept_key!r} missing field {field!r}")
        owners.update(concept["instances"])

    required = {"address", "address_lower", "primary_label", "owner", "category", "concept_class", "aliases", "sources", "confidence", "verified_date"}
    for entry in entities:
        missing = required - set(entry)
        if missing:
            raise DictionaryValidationError(f"Entity missing fields: {sorted(missing)}")
        address_lower = normalize_address(entry["address"])
        if entry["address_lower"] != address_lower:
            raise DictionaryValidationError(f"address_lower mismatch for {entry['address']}")
        if address_lower in seen_addresses:
            raise DictionaryValidationError(f"Duplicate address_lower: {address_lower}")
        seen_addresses.add(address_lower)
        if entry["category"] not in concept_keys:
            raise DictionaryValidationError(f"Unknown category: {entry['category']}")
        validate_confidence(entry["confidence"])
        if not entry["sources"]:
            raise DictionaryValidationError(f"Entity has no sources: {entry['address']}")
        owners.add(entry["owner"])
        for alias in entry["aliases"]:
            normalize_alias(alias)
        for source in entry["sources"]:
            for field in ("name", "url", "retrieved_date", "note"):
                if field not in source:
                    raise DictionaryValidationError(f"Source missing field {field!r} for {entry['address']}")

    for alias, target in aliases.items():
        if normalize_alias(alias) != alias:
            raise DictionaryValidationError(f"Alias key is not normalized: {alias!r}")
        if target not in owners:
            raise DictionaryValidationError(f"Alias target does not exist: {target!r}")

    sources_text = artifacts.sources_path.read_text(encoding="utf-8")
    for phrase in ("Retrieved date:", "Manual verification:", "Automated acceptance criteria"):
        if phrase not in sources_text:
            raise DictionaryValidationError(f"sources.md missing phrase: {phrase}")

    return {"entity_count": len(entities), "concept_count": len(concepts), "alias_count": len(aliases)}
```

- [ ] **Step 4: Run validator tests**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_artifacts.py -q
```

Expected before artifacts exist: the missing-file test passes and committed-artifact tests fail because outputs are not created yet.

- [ ] **Step 5: Commit validator**

```bash
git add src/nl2sparql/linking/dictionary/validate.py tests/unit/test_entity_dictionary_artifacts.py
git commit -m "feat(linking): add entity dictionary artifact validator"
```

---

## Task 4: Acquire and commit real-source raw snapshot

**Files:**
- Create: `scripts/03_fetch_entity_labels.py`
- Create: `data/entity_dictionary/raw/entities.csv`
- Create: `data/entity_dictionary/curated/coverage.json`
- Regenerate: `src/nl2sparql/linking/dictionary/entities.json`
- Regenerate: `src/nl2sparql/linking/dictionary/concepts.json`
- Regenerate: `src/nl2sparql/linking/dictionary/aliases.json`

- [ ] **Step 1: Add coverage list**

Create `data/entity_dictionary/curated/coverage.json`:

```json
{
  "top_exchanges": ["Binance", "Coinbase", "Kraken", "OKX", "Bitfinex", "Huobi", "KuCoin", "Crypto.com", "Gemini", "Bitstamp", "Bybit", "Gate.io", "MEXC", "Bittrex", "Poloniex", "Bithumb", "Upbit", "Bitget", "Deribit", "BitMEX", "Coincheck", "BitFlyer", "Luno", "WazirX", "AscendEX", "WhiteBIT", "BitMart", "Phemex", "Liquid", "Zaif"],
  "top_defi_protocols": ["Uniswap V2", "Uniswap V3", "Curve", "Aave", "Compound", "MakerDAO", "Lido", "Balancer", "SushiSwap", "1inch", "Convex", "Yearn", "Synthetix", "Rocket Pool", "Frax", "EigenLayer", "Pendle", "GMX", "dYdX", "Ether.fi", "Renzo", "Morpho", "Spark", "Liquity", "Alchemix", "Gearbox", "Instadapp", "KyberSwap", "Bancor", "CoW Swap", "ParaSwap", "0x Protocol", "OpenSea", "Blur", "LooksRare", "Stargate", "Hop Protocol", "Across", "Synapse", "Arbitrum Bridge", "Optimism Bridge", "Polygon Bridge", "Base Bridge", "Tornado Cash", "Railgun", "Tether", "Circle", "Paxos", "Frax Finance", "Ethena"]
}
```

- [ ] **Step 2: Add optional fetcher skeleton**

Create `scripts/03_fetch_entity_labels.py` with a fail-fast CLI that writes normalized CSV rows only from explicitly reviewed source rows. The implementation must never fabricate addresses.

```python
from __future__ import annotations

import argparse
import csv
from pathlib import Path

FIELDS = [
    "address",
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "aliases",
    "source_name",
    "source_url",
    "retrieved_date",
    "confidence",
]


def write_rows(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write reviewed Ethereum label rows to T2.2 raw snapshot CSV.")
    parser.add_argument("--output", type=Path, default=Path("data/entity_dictionary/raw/entities.csv"))
    args = parser.parse_args()
    raise SystemExit(
        "This fetcher is intentionally not automatic yet. Add reviewed rows from Etherscan, DeFiLlama, Dune, or Arkham snapshots, then write them with write_rows()."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Populate `data/entity_dictionary/raw/entities.csv` with real sourced rows**

Use real addresses from source pages or exported datasets only. Required CSV header:

```csv
address,primary_label,owner,category,concept_class,aliases,source_name,source_url,retrieved_date,confidence
```

Each row must meet these rules:

- `address` is a real Ethereum address from the cited source.
- `source_url` points to the source page, API endpoint, or exported dataset.
- `aliases` uses `|` separator, for example `binance|binance hot wallet`.
- `confidence` is `high`, `medium`, or `low`.
- No generated/fake addresses are allowed.

Stop and report a blocker if fewer than 3000 real-source rows can be obtained in the current environment.

- [ ] **Step 4: Build artifacts**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run python -m nl2sparql.linking.dictionary.build
```

Expected: `entities.json`, `concepts.json`, and `aliases.json` are written from real raw rows.

- [ ] **Step 5: Run artifact tests**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_artifacts.py -q
```

Expected after `sources.md` exists in Task 5: all artifact tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/03_fetch_entity_labels.py data/entity_dictionary/raw/entities.csv data/entity_dictionary/curated/coverage.json src/nl2sparql/linking/dictionary/entities.json src/nl2sparql/linking/dictionary/concepts.json src/nl2sparql/linking/dictionary/aliases.json
git commit -m "feat(linking): add sourced entity dictionary snapshot"
```

---

## Task 5: Provenance documentation and decision log

**Files:**
- Create: `src/nl2sparql/linking/dictionary/sources.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `tests/unit/test_entity_dictionary_artifacts.py`

- [ ] **Step 1: Add source-doc test**

Append to `tests/unit/test_entity_dictionary_artifacts.py`:

```python
def test_sources_document_manual_verification_boundary():
    text = SOURCES_PATH.read_text(encoding="utf-8")

    assert "Retrieved date: 2026-06-28" in text
    assert "Manual verification: pending" in text
    assert "Automated acceptance criteria" in text
    assert "Live scraping is not required for CI" in text
```

- [ ] **Step 2: Run and verify RED**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_artifacts.py::test_sources_document_manual_verification_boundary -q
```

Expected: fail because `sources.md` does not exist or lacks the required text.

- [ ] **Step 3: Create `sources.md`**

Create `src/nl2sparql/linking/dictionary/sources.md`:

```markdown
# Entity Dictionary Sources

Retrieved date: 2026-06-28

## Snapshot strategy

T2.2 uses committed raw and final snapshots for CI and thesis reproducibility.
Live scraping is not required for CI. Optional live fetchers must write raw
snapshots before final JSON artifacts are rebuilt.

## Source files

- Raw rows: `data/entity_dictionary/raw/entities.csv`
- Concepts: `data/entity_dictionary/curated/concepts.json`
- Coverage list: `data/entity_dictionary/curated/coverage.json`

## Automated acceptance criteria

- `entities.json` has at least 3000 real-source entries.
- `concepts.json` has 8-12 concepts.
- `aliases.json` has at least 1000 aliases.
- Required top-30 exchange owners are present.
- Required top-50 DeFi owners are present.
- Address shape, lowercase key, category, confidence, provenance, deterministic ordering, and alias normalization are validated offline.

## Manual verification

Manual verification: pending

The T2.2 task checkbox for "Sample 50 entries verify thủ công" must remain
unchecked until a random sample of 50 committed entries is checked against
external source pages and the result is recorded here.

## Known limitations

- Public labels can be stale or inconsistent.
- Some service labels describe a protocol or service rather than a legal owner.
- Ambiguous aliases such as `eth`, `usdc`, and `uni` are excluded unless context can disambiguate them.
- The committed snapshot is optimized for reproducible linker development, not real-time attribution.
```

- [ ] **Step 4: Update decision log**

Append to `docs/memory/05-DECISION_LOG.md`:

```markdown
## 2026-06-28 — T2.2 dictionary uses committed source snapshots

Decision: T2.2 accepts committed raw and final dictionary snapshots as the source of truth for tests and thesis reproducibility. Live scraping may be added as optional tooling, but CI and unit tests must read committed artifacts only.

Rationale: Public label sources can change, rate-limit, or fail. A committed snapshot gives stable Phase 4 entity-linker inputs and makes future refreshes auditable through git diffs.

Consequence: Manual verification remains a separate evidence step. The task should not mark the 50-entry manual verification criterion done until sampled entries are checked against external source pages.
```

- [ ] **Step 5: Run tests and commit**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_artifacts.py -q
git add src/nl2sparql/linking/dictionary/sources.md docs/memory/05-DECISION_LOG.md tests/unit/test_entity_dictionary_artifacts.py
git commit -m "docs(linking): document entity dictionary provenance"
```

---

## Task 6: EDA notebook and task status

**Files:**
- Create: `notebooks/05_dict_eda.ipynb`
- Modify: `docs/tasks/phase-2-kg/02-entity-dictionary.md`

- [ ] **Step 1: Add notebook**

Create `notebooks/05_dict_eda.ipynb`:

```json
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# T2.2 Entity Dictionary EDA\n",
        "\n",
        "Offline EDA over committed dictionary artifacts.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import json\n",
        "from collections import Counter\n",
        "from pathlib import Path\n",
        "\n",
        "base = Path('../src/nl2sparql/linking/dictionary')\n",
        "entities = json.loads((base / 'entities.json').read_text())\n",
        "aliases = json.loads((base / 'aliases.json').read_text())\n",
        "concepts = json.loads((base / 'concepts.json').read_text())\n",
        "\n",
        "{'entities': len(entities), 'aliases': len(aliases), 'concepts': len(concepts)}\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "Counter(entry['category'] for entry in entities).most_common()\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "Counter(entry['owner'] for entry in entities).most_common(20)\n"
      ]
    }
  ],
  "metadata": {
    "kernelspec": {
      "display_name": "Python 3",
      "language": "python",
      "name": "python3"
    },
    "language_info": {
      "name": "python",
      "pygments_lexer": "ipython3"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
```

- [ ] **Step 2: Execute notebook**

```bash
JUPYTER_CONFIG_DIR=/tmp/t2-2-jupyter-config JUPYTER_DATA_DIR=/tmp/t2-2-jupyter-data JUPYTER_RUNTIME_DIR=/tmp/t2-2-jupyter-runtime UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run jupyter nbconvert --to notebook --execute notebooks/05_dict_eda.ipynb --output /tmp/t2-2-dict-eda-verified.ipynb --ExecutePreprocessor.timeout=120
```

Expected: nbconvert exits 0.

- [ ] **Step 3: Update task status**

Modify `docs/tasks/phase-2-kg/02-entity-dictionary.md`:

- Mark automated criteria done only if artifact tests pass.
- Keep manual 50-entry verification unchecked unless the sampled check has been performed and recorded.
- Set status to `done-local-auto-pending-manual` if automated criteria pass and manual sampling remains pending.
- Add evidence with exact commands and observed outputs.

- [ ] **Step 4: Commit**

```bash
git add notebooks/05_dict_eda.ipynb docs/tasks/phase-2-kg/02-entity-dictionary.md
git commit -m "docs(linking): add entity dictionary EDA and task evidence"
```

---

## Task 7: Final verification and branch finish

**Files:**
- No new files expected.

- [ ] **Step 1: Focused verification**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest tests/unit/test_entity_dictionary_schema.py tests/unit/test_entity_dictionary_artifacts.py -q
```

Expected: all T2.2 tests pass.

- [ ] **Step 2: Full suite**

```bash
UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python uv run pytest -q
```

Expected: full suite passes.

- [ ] **Step 3: Whitespace check**

```bash
git diff --check
```

Expected: no output, exit 0.

- [ ] **Step 4: Finish branch**

Use `superpowers:finishing-a-development-branch` and offer:

1. Merge locally
2. Push and create a Pull Request
3. Keep branch as-is
4. Discard this work

---

## Self-review

- Spec coverage: The plan covers schema, raw snapshots, deterministic builder, offline validator, committed artifacts, provenance docs, manual-verification boundary, EDA, task status, and final verification.
- Data integrity: The plan explicitly forbids generated/fake addresses for the accepted snapshot. If fewer than 3000 real-source rows are obtainable, implementation must stop and report the blocker.
- Manual boundary: The 50-entry manual verification criterion remains unchecked until external evidence exists.
- Placeholder scan: No `TBD` or `TODO` placeholders remain. The only open condition is explicit: real-source row acquisition must succeed or the task is blocked.
- Type consistency: Function names and paths are consistent across tasks: `normalize_alias`, `normalize_address`, `validate_confidence`, `build_dictionary`, `DictionaryArtifacts`, and `validate_artifacts`.
