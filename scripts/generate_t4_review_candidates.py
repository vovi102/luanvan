#!/usr/bin/env python
"""Generate deterministic, review-only T4 candidate artifacts.

The output is deliberately written under ``data/review_drafts``.  It is not
ground truth and this command must never publish directly to ``data/eval``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from nl2sparql.linking.dictionary import ALIASES_PATH, CONCEPTS_PATH, ENTITIES_PATH, SOURCES_PATH
from nl2sparql.linking.dictionary.validate import DictionaryArtifacts
from nl2sparql.linking.entity import (
    EntityAlternative,
    EntityMatch,
    EntityTarget,
    build_entity_corpus,
)
from nl2sparql.linking.resolver import ClassResolver
from nl2sparql.sql.schema import CATALOG_PATH, load_catalog

OUTPUT = Path("data/review_drafts/t4_candidate_set_2026-09-24")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _match(question: str, span: str, target: EntityTarget) -> EntityMatch:
    start = question.index(span)
    return EntityMatch(
        span=span,
        span_offset=(start, start + len(span)),
        target_id=target.target_id,
        target_kind=target.target_kind,
        owner=target.owner,
        addresses=target.addresses,
        categories=target.categories,
        concept_classes=target.concept_classes,
        stage="exact",
        confidence=1.0,
        alternatives=(),
        target_sha256=target.document_sha256,
    )


def _raw_address_match(question: str, address: str) -> EntityMatch:
    start = question.index(address)
    target_id = f"address:{address}"
    return EntityMatch(
        span=address,
        span_offset=(start, start + len(address)),
        target_id=target_id,
        target_kind="address",
        owner=None,
        addresses=(address,),
        categories=(),
        concept_classes=(),
        stage="address",
        confidence=1.0,
        alternatives=(),
        target_sha256=hashlib.sha256(target_id.encode()).hexdigest(),
    )


def _semantic_match(question: str, span: str, target: EntityTarget) -> EntityMatch:
    exact = _match(question, span, target)
    return EntityMatch(
        **{
            **asdict(exact),
            "stage": "embedding",
            "confidence": 0.9,
        }
    )


def _resolver_row(
    resolver: ClassResolver, case_id: str, question: str, matches: tuple[EntityMatch, ...]
) -> dict:
    plan = resolver.resolve(question, matches)
    return {
        "id": case_id,
        "question": question,
        "matches": [asdict(match) for match in matches],
        "expected": [
            {
                "span_offset": list(entity.span_offset),
                "target_id": entity.target_id,
                "resolution_kind": entity.resolution_kind,
                "direction": entity.direction,
                "coverage_status": entity.coverage_status,
            }
            for entity in plan.entities
        ],
        "expected_status": plan.status,
    }


def _schema_cases() -> list[dict]:
    recipes = [
        (
            "How many transactions occurred each day in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.block_timestamp"],
        ),
        (
            "How many successful transactions occurred each day in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.block_timestamp", "transaction_facts.is_success"],
        ),
        (
            "Which sender addresses initiated the most transactions in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.from_address", "transaction_facts.block_timestamp"],
        ),
        (
            "Which recipient addresses received the most transactions in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.to_address", "transaction_facts.block_timestamp"],
        ),
        (
            "What was the total wei value sent by each address in June 2026?",
            ["transaction_facts"],
            [
                "transaction_facts.from_address",
                "transaction_facts.value_wei",
                "transaction_facts.block_timestamp",
            ],
        ),
        (
            "What was the total wei value received by each address in June 2026?",
            ["transaction_facts"],
            [
                "transaction_facts.to_address",
                "transaction_facts.value_wei",
                "transaction_facts.block_timestamp",
            ],
        ),
        (
            "Which transactions used the most gas in June 2026?",
            ["transaction_facts"],
            [
                "transaction_facts.transaction_hash",
                "transaction_facts.receipt_gas_used",
                "transaction_facts.block_timestamp",
            ],
        ),
        (
            "What is the average receipt gas used per day in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.block_timestamp", "transaction_facts.receipt_gas_used"],
        ),
        (
            "How many failed transactions were there in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.is_success", "transaction_facts.block_timestamp"],
        ),
        (
            "List contract-creation transactions in June 2026.",
            ["transaction_facts"],
            [
                "transaction_facts.transaction_hash",
                "transaction_facts.receipt_contract_address",
                "transaction_facts.block_timestamp",
            ],
        ),
        (
            "How many transactions were in each transaction type in June 2026?",
            ["transaction_facts"],
            ["transaction_facts.transaction_type", "transaction_facts.block_timestamp"],
        ),
        (
            "Which blocks contained the most transactions in June 2026?",
            ["block_facts"],
            [
                "block_facts.block_number",
                "block_facts.transaction_count",
                "block_facts.block_timestamp",
            ],
        ),
        (
            "What is the daily average block gas used in June 2026?",
            ["block_facts"],
            ["block_facts.block_timestamp", "block_facts.gas_used"],
        ),
        (
            "Which block beneficiary addresses were listed on the most blocks in June 2026?",
            ["block_facts"],
            ["block_facts.beneficiary_address", "block_facts.block_timestamp"],
        ),
        (
            "What was the highest base fee per gas in June 2026?",
            ["block_facts"],
            ["block_facts.base_fee_per_gas_wei", "block_facts.block_timestamp"],
        ),
        (
            "How many blocks were produced each day in June 2026?",
            ["block_facts"],
            ["block_facts.block_timestamp"],
        ),
        (
            "Which token addresses had the most transfers in June 2026?",
            ["token_transfer_facts"],
            ["token_transfer_facts.token_address", "token_transfer_facts.block_timestamp"],
        ),
        (
            "Which token symbols had the most transfers in June 2026?",
            ["token_transfer_facts"],
            ["token_transfer_facts.token_symbol", "token_transfer_facts.block_timestamp"],
        ),
        (
            "Which addresses sent the most token transfers in June 2026?",
            ["token_transfer_facts"],
            ["token_transfer_facts.from_address", "token_transfer_facts.block_timestamp"],
        ),
        (
            "Which addresses received the most token transfers in June 2026?",
            ["token_transfer_facts"],
            ["token_transfer_facts.to_address", "token_transfer_facts.block_timestamp"],
        ),
        (
            "What is the total raw token value transferred per token address in June 2026?",
            ["token_transfer_facts"],
            [
                "token_transfer_facts.token_address",
                "token_transfer_facts.value_raw",
                "token_transfer_facts.block_timestamp",
            ],
        ),
        (
            "What is the total normalized token amount transferred per token symbol in June 2026?",
            ["token_transfer_facts"],
            [
                "token_transfer_facts.token_symbol",
                "token_transfer_facts.normalized_amount",
                "token_transfer_facts.block_timestamp",
            ],
        ),
        (
            "How many ERC-20 token transfers occurred in June 2026?",
            ["token_transfer_facts"],
            ["token_transfer_facts.is_erc20", "token_transfer_facts.block_timestamp"],
        ),
        (
            "How many ERC-721 token transfers occurred in June 2026?",
            ["token_transfer_facts"],
            ["token_transfer_facts.is_erc721", "token_transfer_facts.block_timestamp"],
        ),
        (
            "Which token transfers had invalid numeric values in June 2026?",
            ["token_transfer_facts"],
            [
                "token_transfer_facts.value_cast_valid",
                "token_transfer_facts.transaction_hash",
                "token_transfer_facts.log_index",
                "token_transfer_facts.block_timestamp",
            ],
        ),
        (
            "Show token names and decimals for the most frequently transferred "
            "tokens in June 2026.",
            ["token_transfer_facts"],
            [
                "token_transfer_facts.token_name",
                "token_transfer_facts.token_decimals",
                "token_transfer_facts.token_address",
                "token_transfer_facts.block_timestamp",
            ],
        ),
        (
            "Which ERC-20 contracts existed before July 2026?",
            ["contract_dimension"],
            ["contract_dimension.address", "contract_dimension.is_erc20"],
        ),
        (
            "How many ERC-721 contracts existed before July 2026?",
            ["contract_dimension"],
            ["contract_dimension.is_erc721"],
        ),
        (
            "List contract addresses with their latest observed block number before July 2026.",
            ["contract_dimension"],
            ["contract_dimension.address", "contract_dimension.block_number"],
        ),
        (
            "Which token symbols in the token registry have the most decimal places?",
            ["token_dimension"],
            ["token_dimension.symbol", "token_dimension.decimals"],
        ),
        (
            "List token names and addresses from the token registry.",
            ["token_dimension"],
            ["token_dimension.name", "token_dimension.address"],
        ),
        (
            "Which entity labels are classified as exchanges?",
            ["entity_labels_v1"],
            ["entity_labels_v1.primary_label", "entity_labels_v1.concept_class"],
        ),
        (
            "List entity addresses and categories for decentralized exchanges.",
            ["entity_labels_v1"],
            ["entity_labels_v1.address", "entity_labels_v1.category"],
        ),
        (
            "Which entity labels have high confidence?",
            ["entity_labels_v1"],
            ["entity_labels_v1.primary_label", "entity_labels_v1.confidence"],
        ),
        (
            "Show aliases for all labels owned by Binance.",
            ["entity_labels_v1"],
            ["entity_labels_v1.owner", "entity_labels_v1.aliases"],
        ),
        (
            "List entity labels verified most recently.",
            ["entity_labels_v1"],
            ["entity_labels_v1.primary_label", "entity_labels_v1.verified_date"],
        ),
        (
            "Which entity labels have the role of treasury?",
            ["entity_labels_v1"],
            ["entity_labels_v1.primary_label", "entity_labels_v1.address_role"],
        ),
        (
            "Show the source URLs for entity labels classified as lending protocols.",
            ["entity_labels_v1"],
            ["entity_labels_v1.concept_class", "entity_labels_v1.sources"],
        ),
        ("Count entity labels by category.", ["entity_labels_v1"], ["entity_labels_v1.category"]),
        (
            "Find addresses belonging to OKX and their primary labels.",
            ["entity_labels_v1"],
            [
                "entity_labels_v1.owner",
                "entity_labels_v1.address",
                "entity_labels_v1.primary_label",
            ],
        ),
        (
            "Which transaction senders are labeled exchanges?",
            ["transaction_facts", "entity_labels_v1"],
            [
                "transaction_facts.from_address",
                "entity_labels_v1.address",
                "entity_labels_v1.concept_class",
            ],
        ),
        (
            "Which transaction recipients are labeled lending protocols?",
            ["transaction_facts", "entity_labels_v1"],
            [
                "transaction_facts.to_address",
                "entity_labels_v1.address",
                "entity_labels_v1.concept_class",
            ],
        ),
        (
            "How many token transfers were sent by known exchanges in June 2026?",
            ["token_transfer_facts", "entity_labels_v1"],
            [
                "token_transfer_facts.from_address",
                "token_transfer_facts.block_timestamp",
                "entity_labels_v1.address",
                "entity_labels_v1.concept_class",
            ],
        ),
        (
            "How many token transfers went to decentralized exchanges in June 2026?",
            ["token_transfer_facts", "entity_labels_v1"],
            [
                "token_transfer_facts.to_address",
                "token_transfer_facts.block_timestamp",
                "entity_labels_v1.address",
                "entity_labels_v1.category",
            ],
        ),
        (
            "Which token symbols were received by Binance in June 2026?",
            ["token_transfer_facts", "entity_labels_v1"],
            [
                "token_transfer_facts.to_address",
                "token_transfer_facts.token_symbol",
                "token_transfer_facts.block_timestamp",
                "entity_labels_v1.owner",
                "entity_labels_v1.address",
            ],
        ),
        (
            "Which blocks had the greatest transaction counts and high gas use in June 2026?",
            ["block_facts"],
            [
                "block_facts.block_number",
                "block_facts.transaction_count",
                "block_facts.gas_used",
                "block_facts.block_timestamp",
            ],
        ),
        (
            "Which successful transactions had the greatest receipt gas used in June 2026?",
            ["transaction_facts"],
            [
                "transaction_facts.transaction_hash",
                "transaction_facts.is_success",
                "transaction_facts.receipt_gas_used",
                "transaction_facts.block_timestamp",
            ],
        ),
        (
            "Which token contracts were marked both ERC-20 and ERC-721 before July 2026?",
            ["contract_dimension"],
            [
                "contract_dimension.address",
                "contract_dimension.is_erc20",
                "contract_dimension.is_erc721",
            ],
        ),
        (
            "Show entity owners, categories, and verified dates for bridge labels.",
            ["entity_labels_v1"],
            [
                "entity_labels_v1.owner",
                "entity_labels_v1.category",
                "entity_labels_v1.verified_date",
            ],
        ),
        (
            "Which token transfers had the largest normalized amount in June 2026?",
            ["token_transfer_facts"],
            [
                "token_transfer_facts.transaction_hash",
                "token_transfer_facts.log_index",
                "token_transfer_facts.normalized_amount",
                "token_transfer_facts.block_timestamp",
            ],
        ),
    ]
    assert len(recipes) == 50
    return [
        {
            "id": f"schema-candidate-{index:02d}",
            "nl": question,
            "gold_relations": relations,
            "gold_fields": fields,
        }
        for index, (question, relations, fields) in enumerate(recipes, start=1)
    ]


def _choose_owner_targets(corpus) -> list[EntityTarget]:
    owners = [target for target in corpus.targets if target.target_kind == "owner"]
    selected: list[EntityTarget] = []
    for category in ("exchange", "dex", "lending", "bridge", "staking", "mev", "stablecoin"):
        selected.extend(target for target in owners if category in target.categories)
    selected_ids = {target.target_id for target in selected}
    token_contracts = [
        target
        for target in owners
        if "token_contract" in target.categories
        and target.target_id not in selected_ids
        and 2 <= len(target.owner or "") <= 36
        and all(character.isprintable() for character in target.owner or "")
    ]
    selected.extend(token_contracts[: 100 - len(selected)])
    if len(selected) != 100:
        raise RuntimeError(f"expected 100 selected owners, got {len(selected)}")
    return selected


def _entity_cases(selected: list[EntityTarget]) -> list[dict]:
    templates = (
        "Show token transfers from {owner} in June 2026.",
        "Which token transfers were received by {owner} in June 2026?",
        "How many transactions involved {owner} in June 2026?",
        "List transfers sent to {owner} during June 2026.",
    )
    rows = []
    for index, target in enumerate(selected, start=1):
        assert target.owner is not None
        question = templates[(index - 1) % len(templates)].format(owner=target.owner)
        start = question.index(target.owner)
        rows.append(
            {
                "id": f"entity-candidate-{index:03d}",
                "question": question,
                "mentions": [
                    {
                        "span": target.owner,
                        "span_offset": [start, start + len(target.owner)],
                        "target_id": target.target_id,
                    }
                ],
            }
        )
    return rows


def _resolver_cases(corpus, selected: list[EntityTarget]) -> list[dict]:
    resolver = ClassResolver(CATALOG_PATH, corpus)
    owner_targets = selected[:25]
    rows: list[dict] = []
    for index, target in enumerate(owner_targets, start=1):
        assert target.owner is not None
        question = (
            f"Show transactions from {target.owner} in June 2026."
            if index % 2
            else f"Show transactions to {target.owner} in June 2026."
        )
        match = _match(question, target.owner, target)
        rows.append(_resolver_row(resolver, f"resolver-candidate-{index:02d}", question, (match,)))

    phrases = {
        "concept:bridge": "bridge",
        "concept:dex": "decentralized exchange",
        "concept:exchange": "exchange",
        "concept:lending": "lending",
        "concept:mev": "mev",
        "concept:mixer": "mixer",
        "concept:nft_marketplace": "nft marketplace",
        "concept:stablecoin": "stablecoin",
        "concept:staking": "staking",
        "concept:token_contract": "token contract",
    }
    concept_targets = [corpus.targets_by_id[target_id] for target_id in sorted(phrases)]
    revised_questions = (
        "Show token transfers from bridge in June 2026.",
        "Show token transfers to decentralized exchange in June 2026.",
        "Count transactions from exchange in June 2026.",
        "List transactions received by lending in June 2026.",
        "Find activity involving mev in June 2026.",
        "Show token transfers from mixer in June 2026.",
        "Show token transfers to nft marketplace in June 2026.",
        "Count transactions from stablecoin in June 2026.",
        "List transactions received by staking in June 2026.",
        "Find activity involving token contract in June 2026.",
    )
    for offset, question in enumerate(revised_questions):
        target = concept_targets[offset]
        phrase = phrases[target.target_id]
        match = _match(question, phrase, target)
        rows.append(
            _resolver_row(resolver, f"resolver-candidate-{offset + 26:02d}", question, (match,))
        )

    def pair_case(case_id: int, question: str, first: EntityTarget, second: EntityTarget) -> dict:
        assert first.owner is not None and second.owner is not None
        return _resolver_row(
            resolver,
            f"resolver-candidate-{case_id:02d}",
            question,
            (_match(question, first.owner, first), _match(question, second.owner, second)),
        )

    first, second, third = selected[0], selected[1], selected[2]
    assert all(target.owner is not None for target in (first, second, third))
    raw_a = "0x1111111111111111111111111111111111111111"
    raw_b = "0x2222222222222222222222222222222222222222"
    raw_c = "0x3333333333333333333333333333333333333333"
    ambiguous_concept = corpus.targets_by_id["concept:exchange"]

    def ambiguous_case(case_id: int, owner: EntityTarget) -> dict:
        assert owner.owner is not None
        question = f"Show activity involving {owner.owner} in June 2026."
        exact_match = _match(question, owner.owner, owner)
        match = EntityMatch(
            **{
                **asdict(exact_match),
                "stage": "ambiguous",
                "confidence": 0.6,
                "alternatives": (
                    EntityAlternative(owner.target_id, "owner", 0.6),
                    EntityAlternative(ambiguous_concept.target_id, "concept", 0.4),
                ),
            }
        )
        return _resolver_row(resolver, f"resolver-candidate-{case_id:02d}", question, (match,))

    def raw_case(case_id: int, question: str, address: str) -> dict:
        return _resolver_row(
            resolver,
            f"resolver-candidate-{case_id:02d}",
            question,
            (_raw_address_match(question, address),),
        )

    bridge = corpus.targets_by_id["concept:bridge"]
    dex = corpus.targets_by_id["concept:dex"]
    lending = corpus.targets_by_id["concept:lending"]
    replacements = [
        ambiguous_case(36, selected[4]),
        ambiguous_case(37, selected[5]),
        ambiguous_case(38, selected[6]),
        _resolver_row(
            resolver,
            "resolver-candidate-39",
            f"Show activity involving {first.owner} in June 2026.",
            (_match(f"Show activity involving {first.owner} in June 2026.", first.owner, first),),
        ),
        _resolver_row(
            resolver,
            "resolver-candidate-40",
            f"Show token transfers from and to {second.owner} in June 2026.",
            (
                _match(
                    f"Show token transfers from and to {second.owner} in June 2026.",
                    second.owner,
                    second,
                ),
            ),
        ),
        _resolver_row(
            resolver,
            "resolver-candidate-41",
            f"List transactions received by and sent by {third.owner} in June 2026.",
            (
                _match(
                    f"List transactions received by and sent by {third.owner} in June 2026.",
                    third.owner,
                    third,
                ),
            ),
        ),
        pair_case(
            42,
            f"Show token transfers from {first.owner} to {second.owner} in June 2026.",
            first,
            second,
        ),
        pair_case(
            43,
            f"Show token transfers from {first.owner} and {second.owner} in June 2026.",
            first,
            second,
        ),
        _resolver_row(
            resolver,
            "resolver-candidate-44",
            f"Show token transfers from {first.owner} to exchange in June 2026.",
            (
                _match(
                    f"Show token transfers from {first.owner} to exchange in June 2026.",
                    first.owner,
                    first,
                ),
                _match(
                    f"Show token transfers from {first.owner} to exchange in June 2026.",
                    "exchange",
                    ambiguous_concept,
                ),
            ),
        ),
        raw_case(45, f"Show transfers from {raw_a} in June 2026.", raw_a),
        raw_case(46, f"Show transfers to {raw_b} in June 2026.", raw_b),
        raw_case(47, f"Find activity involving {raw_c} in June 2026.", raw_c),
        _resolver_row(
            resolver,
            "resolver-candidate-48",
            "Show token transfers sent by bridges in June 2026.",
            (
                _semantic_match(
                    "Show token transfers sent by bridges in June 2026.", "bridges", bridge
                ),
            ),
        ),
        _resolver_row(
            resolver,
            "resolver-candidate-49",
            "Show token transfers into decentralized exchanges in June 2026.",
            (
                _semantic_match(
                    "Show token transfers into decentralized exchanges in June 2026.",
                    "decentralized exchanges",
                    dex,
                ),
            ),
        ),
        _resolver_row(
            resolver,
            "resolver-candidate-50",
            "List transactions sent out of lending protocols in June 2026.",
            (
                _semantic_match(
                    "List transactions sent out of lending protocols in June 2026.",
                    "lending protocols",
                    lending,
                ),
            ),
        ),
    ]
    rows.extend(replacements)
    assert len(rows) == 50
    return rows


def _write_review_template(path: Path, rows: list[dict], replacement_ids: set[str]) -> None:
    existing: dict[str, dict[str, str]] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as stream:
            existing = {row["id"]: row for row in csv.DictReader(stream)}
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["component", "id", "decision", "reviewer_note"])
        writer.writeheader()
        for row in rows:
            prior = existing.get(row["id"], {})
            writer.writerow(
                {
                    "component": row["component"],
                    "id": row["id"],
                    "decision": "" if row["id"] in replacement_ids else prior.get("decision", ""),
                    "reviewer_note": ""
                    if row["id"] in replacement_ids
                    else prior.get("reviewer_note", ""),
                }
            )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifacts = DictionaryArtifacts(ENTITIES_PATH, CONCEPTS_PATH, ALIASES_PATH, SOURCES_PATH)
    corpus = build_entity_corpus(artifacts)
    selected = _choose_owner_targets(corpus)
    schema_rows = _schema_cases()
    entity_rows = _entity_cases(selected)
    resolver_rows = _resolver_cases(corpus, selected)
    catalog = load_catalog(CATALOG_PATH)

    _write_jsonl(OUTPUT / "schema_link_candidates.jsonl", schema_rows)
    _write_jsonl(OUTPUT / "entity_link_candidates.jsonl", entity_rows)
    _write_jsonl(OUTPUT / "class_resolver_candidates.jsonl", resolver_rows)
    manifest = {
        "status": "DRAFT — agent-authored; not ground truth; not for training or publication",
        "created_on": "2026-09-24",
        "counts": {
            "schema_linker": len(schema_rows),
            "entity_linker": len(entity_rows),
            "class_resolver": len(resolver_rows),
        },
        "catalog_version": catalog["catalog_version"],
        "dictionary_sha256": {
            "entities": corpus.entities_sha256,
            "aliases": corpus.aliases_sha256,
            "concepts": corpus.concepts_sha256,
        },
        "promotion_rule": (
            "A human reviewer must record ACCEPT or a corrected REVISE before a row "
            "may enter data/eval. REJECT rows remain only in this draft set."
        ),
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    review_rows = [
        {"component": component, "id": row["id"]}
        for component, rows in (
            ("schema_linker", schema_rows),
            ("entity_linker", entity_rows),
            ("class_resolver", resolver_rows),
        )
        for row in rows
    ]
    _write_review_template(
        OUTPUT / "review_decisions.csv",
        review_rows,
        {f"resolver-candidate-{index:02d}" for index in range(36, 51)},
    )


if __name__ == "__main__":
    main()
