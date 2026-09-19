"""Phase 10: theme helpers. Pure functions, no Streamlit runtime needed.

Status must always be shown as colour paired with a word (qa-console-ui skill:
"Status shown by colour only" is banned), so every chip is checked for both.
"""

from __future__ import annotations

from ui.theme import (
    FAIL,
    NOTE,
    PASS,
    REVIEW,
    decision_chip,
    decision_label,
    format_timestamp,
    status_chip,
    status_colour,
)


def test_every_status_chip_carries_a_word_not_just_a_colour():
    for value in ("PASS", "FAIL", "REVIEW", "NOTE", "NA"):
        chip = status_chip(value)
        assert any(word in chip for word in ("Passed", "Failed", "Needs review", "Note", "Not applicable"))


def test_status_colours_are_distinct():
    colours = {status_colour(s) for s in ("PASS", "FAIL", "REVIEW", "NOTE")}
    assert colours == {PASS, FAIL, REVIEW, NOTE}


def test_decision_chip_and_label_agree():
    for decision in ("AUTO_SUBMIT", "QA_REVIEW", "HELD_TL"):
        chip = decision_chip(decision)
        label = decision_label(decision)
        assert label in chip


def test_format_timestamp_is_mm_ss():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(3661) == "61:01"


def test_an_unknown_status_falls_back_gracefully():
    chip = status_chip("SOMETHING_NEW")
    assert "SOMETHING_NEW" in chip
