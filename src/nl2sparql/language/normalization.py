"""Pure normalization helpers for English and Vietnamese questions."""

import unicodedata

from nl2sparql.language.contracts import Language, NormalizedInput

_SUPPORTED_LANGUAGES = frozenset({"en", "vi"})
_VIETNAMESE_STROKED_D = str.maketrans({"đ": "d", "Đ": "D"})


def _fold_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.translate(_VIETNAMESE_STROKED_D))
    without_marks = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return unicodedata.normalize("NFC", without_marks)


def normalize_input(text: str, *, language: Language) -> NormalizedInput:
    """Derive stable matching forms without changing the submitted text.

    Args:
        text: Exact English or Vietnamese question submitted by the caller.
        language: Explicit language tag. The function never infers it.

    Returns:
        An immutable record containing the original and derived text forms.

    Raises:
        ValueError: If the input is empty, spans multiple/non-printable lines, or
            uses an unsupported language tag.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if not text.isprintable():
        raise ValueError("text must contain exactly one printable line")
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")

    nfc = unicodedata.normalize("NFC", text)
    match = " ".join(nfc.split()).casefold()
    return NormalizedInput(
        original=text,
        nfc=nfc,
        match=match,
        accent_folded=_fold_accents(match),
        language=language,
    )
