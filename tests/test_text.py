from redline.text import (
    normalize_case,
    normalize_whitespace,
    split_paragraphs,
    split_sentences,
    split_words,
)


def test_normalize_whitespace_collapses_runs():
    assert normalize_whitespace("a   b\tc") == "a b c"


def test_normalize_whitespace_smart_quotes():
    assert normalize_whitespace("Party’s “claim”") == "Party's \"claim\""


def test_normalize_whitespace_preserves_case():
    assert normalize_whitespace("The Agreement") == "The Agreement"


def test_normalize_case_folds_case_after_whitespace_cleanup():
    assert normalize_case("The   Agreement") == "the agreement"


def test_split_paragraphs_on_blank_lines():
    assert split_paragraphs("One.\n\nTwo.\n\n\nThree.") == ["One.", "Two.", "Three."]


def test_split_sentences_basic():
    assert split_sentences("Pay by May 1. Late fees apply.") == [
        "Pay by May 1.",
        "Late fees apply.",
    ]


def test_split_words_basic():
    assert split_words("The quick fox.") == ["The", "quick", "fox."]
