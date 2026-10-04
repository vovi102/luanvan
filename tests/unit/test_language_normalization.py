from dataclasses import FrozenInstanceError

import pytest

from nl2sparql.language import normalize_input


def test_normalize_input_preserves_original_and_composes_vietnamese():
    composed = "  Cho tôi địa chỉ Binance  "
    decomposed = "  Cho to\u0302i đi\u0323a chi\u0309 Binance  "

    composed_input = normalize_input(composed, language="vi")
    decomposed_input = normalize_input(decomposed, language="vi")

    assert composed_input.original == composed
    assert decomposed_input.original == decomposed
    assert composed_input.nfc == "  Cho tôi địa chỉ Binance  "
    assert composed_input.nfc == decomposed_input.nfc
    assert composed_input.match == decomposed_input.match == "cho tôi địa chỉ binance"
    with pytest.raises(FrozenInstanceError):
        composed_input.original = "changed"


def test_normalize_input_folds_accents_only_in_derived_form():
    normalized = normalize_input("Giá trị Đồng", language="vi")

    assert normalized.original == "Giá trị Đồng"
    assert normalized.nfc == "Giá trị Đồng"
    assert normalized.match == "giá trị đồng"
    assert normalized.accent_folded == "gia tri dong"
    assert normalized.normalization_version == "bilingual-nfc-v1"


def test_normalize_input_leaves_addresses_symbols_dates_and_numbers_intact():
    text = "Giao dịch 1,250.50 USDT từ 0xAbC123 ngày 2026-10-04"

    normalized = normalize_input(text, language="vi")

    for protected in ("1,250.50", "usdt", "0xabc123", "2026-10-04"):
        assert protected in normalized.match
        assert protected in normalized.accent_folded


def test_normalize_input_is_idempotent_for_unaccented_vietnamese():
    first = normalize_input("  Liet ke   giao dich tu dia chi 0xabc  ", language="vi")
    second = normalize_input(first.accent_folded, language="vi")

    assert first.match == first.accent_folded
    assert second.match == first.match
    assert second.accent_folded == first.accent_folded


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("", "vi"),
        ("   ", "en"),
        ("first\nsecond", "en"),
        ("bad\x00text", "vi"),
        ("valid text", "fr"),
    ],
)
def test_normalize_input_rejects_empty_control_or_unknown_language(text, language):
    with pytest.raises(ValueError):
        normalize_input(text, language=language)
