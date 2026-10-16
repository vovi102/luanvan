"""Rendered-language regressions from the first 200-row agent audit."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from nl2sparql.dataset.bilingual.contracts import TEMPLATES_PATH, load_catalog
from nl2sparql.dataset.bilingual.rendering import render_pattern
from nl2sparql.dataset.templates import load_templates

ARCHIVE = Path("tests/fixtures/dataset/bilingual-pre-audit-correction-catalog.json")


def rendered():
    templates = load_templates()
    by_id = {item["id"]: item for item in templates}
    for entry in load_catalog(TEMPLATES_PATH, templates).entries:
        slots = dict(by_id[entry.template_id]["example_fill"])
        if "n" in slots:
            slots["n"] = 1
        yield entry, render_pattern(entry, slots), slots


def test_bound_one_never_produces_english_plural_agreement_errors():
    plural = (
        r"\b1 (?:transactions|transfers|blocks|addresses|owners|groups|symbols|"
        r"hours|pairs|categories|senders|recipients)\b"
    )
    failures = [
        entry.id
        for entry, question, _ in rendered()
        if entry.language == "en" and re.search(plural, question, re.I)
    ]
    assert failures == []


@pytest.mark.parametrize(
    "template_id, english, vietnamese",
    [
        ("T_LIST_TX_FROM_ACCOUNT", r"latest|newest", r"mới nhất|gần nhất"),
        ("T_LIST_TX_TO_ACCOUNT", r"latest|newest", r"mới nhất|gần nhất"),
        ("T_LIST_FAILED_TX", r"latest|newest", r"mới nhất|gần nhất"),
        ("T_TX_BETWEEN_ACCOUNTS", r"latest|newest", r"mới nhất|gần nhất"),
        ("T_TOKEN_TRANSFERS_OF_TOKEN", r"latest|newest|recent", r"mới nhất|gần nhất|gần đây"),
        ("T_BLOCKS_BY_VALIDATOR", r"latest|newest", r"mới nhất|gần nhất"),
        ("T_FILTER_TX_BY_VALUE", r"largest|highest|top", r"lớn nhất|cao nhất|top"),
        ("T_LARGE_TX_TO_CLASS", r"largest|highest|top", r"lớn nhất|cao nhất|top|đứng đầu"),
        ("T_FAILED_HIGH_GAS_TX", r"highest|largest|top", r"lớn nhất|cao nhất|nhiều.*nhất|top"),
        ("T_TOKEN_AFTER_NATIVE_FUNDING", r"earliest|first", r"sớm nhất|đầu tiên"),
    ],
)
def test_every_style_identifies_material_top_k(template_id, english, vietnamese):
    failures = [
        entry.id
        for entry, question, _ in rendered()
        if entry.template_id == template_id
        and not re.search(english if entry.language == "en" else vietnamese, question, re.I)
    ]
    assert failures == []


def test_date_windows_are_explicitly_end_exclusive_in_both_languages():
    failures = []
    for entry, question, slots in rendered():
        if "end_date" not in slots:
            continue
        end = re.escape(slots["end_date"])
        explicit = (
            rf"before {end}|excluding {end}|{end}\)"
            if entry.language == "en"
            else rf"trước {end}|{end}\)"
        )
        if "through" in question.lower() or not re.search(explicit, question):
            failures.append(entry.id)
    assert failures == []


def test_native_value_requests_do_not_assert_successful_fund_movement():
    failures = []
    for entry, question, _ in rendered():
        if entry.template_id not in {
            "T_FILTER_TX_BY_VALUE",
            "T_TOP_SENDERS_BY_VALUE",
            "T_LARGE_TX_TO_CLASS",
        }:
            continue
        if entry.language == "en":
            okay = "native" in question.lower() and not re.search(
                r"moved|wei sent|transfers", question, re.I
            )
        else:
            okay = "giá trị native" in question and "chuyển" not in question
        if not okay:
            failures.append(entry.id)
    assert failures == []


def test_vietnamese_sender_totals_explicitly_aggregate_transactions():
    entry, question, _ = next(
        row for row in rendered() if row[0].id == "T_TOP_SENDERS_BY_VALUE__vi__formal"
    )
    assert "của các giao dịch" in question
    assert "tổng" in question and "giá trị native" in question


def test_repeated_pair_wording_preserves_direction_and_repeat_eligibility():
    failures = []
    for entry, question, _ in rendered():
        if entry.template_id != "T_REPEATED_PAIR_FLOW":
            continue
        direction = r"directed|sender.recipient" if entry.language == "en" else r"có hướng|gửi.nhận"
        repeated = r"at least two|>\s*1" if entry.language == "en" else r"ít nhất hai|>\s*1"
        if not re.search(direction, question, re.I) or not re.search(repeated, question, re.I):
            failures.append(entry.id)
    assert failures == []


def test_frozen_failed_audit_questions_remain_reproducible():
    assert (
        hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
        == "00d5dc083bd22aeeee4a8515c0cda0fb0f18cc972584f0e0f57681954cbf6cfe"
    )
    entries = {entry.id: entry for entry in load_catalog(ARCHIVE, load_templates()).entries}
    samples = Path("docs/evidence/bilingual-training-audit-sample-2026-10-15.jsonl")
    decisions = {
        row["record_id"]: row
        for row in map(
            json.loads,
            Path("docs/evidence/bilingual-training-audit-decisions-2026-10-15.jsonl")
            .read_text()
            .splitlines(),
        )
    }
    for row in map(json.loads, samples.read_text().splitlines()):
        assert (
            render_pattern(entries[row["catalog_entry_id"]], dict(row["slot_values"]))
            == row["question"]
        )
        assert decisions[row["id"]]["record_sha256"] == row["record_sha256"]
