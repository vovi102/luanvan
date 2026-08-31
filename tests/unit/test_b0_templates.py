from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nl2sparql.dataset.templates import TEMPLATES_PATH
from nl2sparql.models.b0 import B0Policy, compile_template_snapshot


def test_compile_snapshot_binds_exact_source_fingerprint(tmp_path: Path) -> None:
    source = TEMPLATES_PATH.read_bytes()
    path = tmp_path / "templates.json"
    path.write_bytes(source)

    compiled = compile_template_snapshot(path, B0Policy())

    expected = hashlib.sha256(source).hexdigest()
    assert len(compiled) == 25
    assert {row.template_sha256 for row in compiled} == {expected}


def test_compile_snapshot_orders_specific_templates_deterministically() -> None:
    compiled = compile_template_snapshot(TEMPLATES_PATH, B0Policy())

    keys = [(-row.literal_token_count, row.template_id) for row in compiled]
    assert keys == sorted(keys)


def test_compiled_seed_matches_named_typed_groups() -> None:
    row = next(
        value
        for value in compile_template_snapshot(TEMPLATES_PATH, B0Policy())
        if value.template_id == "T_COUNT_TX_IN_RANGE"
    )

    match = row.seed_pattern.fullmatch(
        "How many transactions happened between 2026-06-15 and 2026-06-16?"
    )

    assert match is not None
    assert match.groupdict() == {
        "start_date": "2026-06-15",
        "end_date": "2026-06-16",
    }


def test_compiled_seed_tolerates_case_and_repeated_whitespace() -> None:
    row = next(
        value
        for value in compile_template_snapshot(TEMPLATES_PATH, B0Policy())
        if value.template_id == "T_COUNT_TX_IN_RANGE"
    )

    match = row.seed_pattern.fullmatch(
        "HOW MANY  transactions happened between 2026-06-15 and 2026-06-16?"
    )

    assert match is not None


def test_seed_literals_are_nfkc_normalized(tmp_path: Path) -> None:
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates[0]["nl_seed"] = (
        "Ｈｏｗ ｍａｎｙ ｔｒａｎｓａｃｔｉｏｎｓ ｈａｐｐｅｎｅｄ ｂｅｔｗｅｅｎ "
        "{start_date} ａｎｄ {end_date}?"
    )
    path = tmp_path / "templates.json"
    path.write_text(json.dumps(templates), encoding="utf-8")
    row = next(
        value
        for value in compile_template_snapshot(path, B0Policy())
        if value.template_id == "T_COUNT_TX_IN_RANGE"
    )

    assert row.seed_pattern.fullmatch(
        "How many transactions happened between 2026-06-15 and 2026-06-16?"
    )
