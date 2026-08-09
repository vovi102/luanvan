from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from nl2sparql.linking.dictionary.schema import (
    DictionaryValidationError,
    normalize_address,
    validate_address_role,
    validate_chain_id,
    validate_confidence,
    validate_source_locator,
    validate_source_revision,
)

COINGECKO_SOURCE_URL = "https://tokens.coingecko.com/uniswap/all.json"

FIELDS = [
    "address",
    "primary_label",
    "owner",
    "category",
    "concept_class",
    "aliases",
    "chain_id",
    "address_role",
    "source_name",
    "source_url",
    "source_revision",
    "source_locator",
    "retrieved_date",
    "confidence",
]


def rows_from_coingecko(
    snapshot: dict[str, Any],
    *,
    revision: str,
    retrieved_date: str,
    excluded_addresses: set[str] | None = None,
) -> list[dict[str, str]]:
    """Convert an immutable CoinGecko snapshot to Ethereum token rows."""

    validate_source_revision(revision)
    tokens = snapshot.get("tokens")
    if not isinstance(tokens, list):
        raise DictionaryValidationError("CoinGecko snapshot must contain a tokens list")

    excluded_addresses = excluded_addresses or set()
    rows: list[dict[str, str]] = []
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            raise DictionaryValidationError(f"CoinGecko token at index {index} must be an object")
        if token.get("chainId") != 1:
            continue
        address = token.get("address")
        address_lower = normalize_address(address)
        if address_lower in excluded_addresses:
            continue
        name = token.get("name")
        symbol = token.get("symbol")
        if not isinstance(name, str) or not name.strip():
            raise DictionaryValidationError(f"CoinGecko token at index {index} has no name")
        if not isinstance(symbol, str) or not symbol.strip():
            raise DictionaryValidationError(f"CoinGecko token at index {index} has no symbol")
        name = name.strip()
        symbol = symbol.strip()
        rows.append(
            {
                "address": address,
                "primary_label": f"{name} ({symbol}) token contract",
                "owner": name,
                "category": "token_contract",
                "concept_class": "TokenContract",
                "aliases": f"{name}|{symbol}",
                "chain_id": "1",
                "address_role": "token",
                "source_name": "coingecko_token_list",
                "source_url": COINGECKO_SOURCE_URL,
                "source_revision": revision,
                "source_locator": f"/tokens/{index}",
                "retrieved_date": retrieved_date,
                "confidence": "medium",
            }
        )
    return rows


def read_reviewed_rows(path: Path) -> list[dict[str, str]]:
    """Read explicitly reviewed Ethereum rows from a committed CSV snapshot."""

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise DictionaryValidationError(f"Reviewed CSV fields must be exactly {FIELDS!r}")
        return list(reader)


def compile_rows(
    token_rows: list[dict[str, str]],
    reviewed_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Validate and merge source rows without inferring chain context."""

    merged: dict[tuple[int, str], dict[str, str]] = {}
    for source_row in [*token_rows, *reviewed_rows]:
        row = dict(source_row)
        chain_id = validate_chain_id(row["chain_id"])
        address_lower = normalize_address(row["address"])
        row["chain_id"] = str(chain_id)
        row["address_role"] = validate_address_role(row["address_role"])
        row["source_revision"] = validate_source_revision(row["source_revision"])
        row["source_locator"] = validate_source_locator(row["source_locator"])
        row["confidence"] = validate_confidence(row["confidence"])
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


def write_rows(rows: list[dict[str, str]], output: Path) -> None:
    """Write reviewed Ethereum label rows to the raw T2.2 snapshot CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDS,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile offline chain-aware snapshots into the T2.2 raw CSV."
    )
    parser.add_argument(
        "--coingecko-snapshot",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--reviewed-rows",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--retrieved-date",
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/entity_dictionary/raw/entities.csv"),
    )
    args = parser.parse_args()

    snapshot_bytes = args.coingecko_snapshot.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    revision = f"sha256:{hashlib.sha256(snapshot_bytes).hexdigest()}"
    reviewed_rows = read_reviewed_rows(args.reviewed_rows)
    reviewed_addresses = {normalize_address(row["address"]) for row in reviewed_rows}
    token_rows = rows_from_coingecko(
        snapshot,
        revision=revision,
        retrieved_date=args.retrieved_date,
        excluded_addresses=reviewed_addresses,
    )
    write_rows(compile_rows(token_rows, reviewed_rows), args.output)


if __name__ == "__main__":
    main()
