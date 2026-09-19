"""Phase 12: crosstalk, mishears and silence must never produce a false critical.

PLAN.md's guardrails criterion: "Crosstalk/mishear/silence tests pass without
false criticals." A false critical here means a critical check reads FAIL when
nothing was actually wrong, purely because the transcript is messy. The safe
failure mode is REVIEW (hard rule 7: uncertainty never becomes a confident
PASS, and it must not manufacture a confident FAIL either).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.checks.factual import score_type_b_check
from app.checks.library import resolve_for_date
from app.checks.models import TurnDict
from app.checks.verbatim import score_disclaimer_ordering, score_type_a_check

RETAILER = "PROVIDER_A"
CALL_DATE = date(2026, 9, 19)

RATE_CARD = {
    "promo_price_monthly": 42.90,
    "ongoing_price_monthly": 72.90,
    "promo_term_months": 6,
    "download_speed_mbps": 25,
    "modem_model": "Netcomm CF40",
}
CRM_FIELDS = {
    "email": "jordan.avery@example.com",
    "dob": "1990-03-14",
    "service_address": "12 Sample Street, Testville NSW 2000",
}
LEAD = {"rate_card": RATE_CARD, "crm_fields": CRM_FIELDS}


def turn(idx, speaker, start, end, text, conf=0.95, source="diarization") -> TurnDict:
    return {
        "idx": idx,
        "speaker": speaker,
        "start_s": start,
        "end_s": end,
        "text_redacted": text,
        "avg_confidence": conf,
        "speaker_source": source,
    }


@pytest.fixture(scope="module")
def snapshot():
    return resolve_for_date(CALL_DATE, RETAILER)


# ---------------------------------------------------------------------------
# Crosstalk: an interrupting turn splits a check-bearing line mid-sentence
# ---------------------------------------------------------------------------


def test_crosstalk_does_not_fail_the_disclaimer(snapshot):
    """The customer talks over the tail of the disclaimer. The line is still
    there and still ordered correctly; a short interrupting turn must not
    turn a real disclaimer into a FAIL."""
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "agent", 10.0, 14.0, "Please be advised that this call will be recorded for"),
        turn(1, "customer", 13.8, 14.2, "sorry, go on"),
        turn(2, "agent", 14.3, 16.0, "quality assurance and training purposes, is that okay?"),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] != "FAIL"


def test_crosstalk_does_not_fail_a_correct_price_quote(snapshot):
    """A customer interjection between two halves of one price sentence must
    not be read as a second, conflicting price mention."""
    check = snapshot.by_id("ongoing_monthly_price")
    turns = [
        turn(0, "agent", 10.0, 12.0, "and after that it goes to"),
        turn(1, "customer", 11.8, 12.1, "mm-hmm"),
        turn(2, "agent", 12.2, 14.0, "seventy two dollars and ninety a month, the regular price"),
    ]

    result = score_type_b_check(check, turns, LEAD)

    assert result["status"] != "FAIL"


def test_crosstalk_around_consent_still_confirms(snapshot):
    """A customer talking over the question, then answering, must not FAIL
    the confirmation just because the exchange is not clean."""
    check = snapshot.by_id("consent_to_switch")
    turns = [
        turn(0, "agent", 10.0, 11.0, "sorry, one sec"),
        turn(1, "agent", 11.5, 15.0, "do you understand and agree to switch your internet service to this plan on these terms?"),
        turn(2, "customer", 15.2, 15.3, "uh"),
        turn(3, "customer", 15.4, 16.0, "yes, I agree"),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] != "FAIL"


# ---------------------------------------------------------------------------
# Mishear: a plausible transcription error near a check-bearing value
# ---------------------------------------------------------------------------


def test_a_mishear_near_the_correct_price_does_not_fail(snapshot):
    """STT renders 'seventy two' with a stray word inserted. Fuzzy matching
    must absorb small mishears rather than reading them as a wrong number."""
    check = snapshot.by_id("ongoing_monthly_price")
    turns = [
        turn(0, "agent", 10.0, 13.0, "it's seventy uh two dollars and ninety per month ongoing")
    ]

    result = score_type_b_check(check, turns, LEAD)

    assert result["status"] != "FAIL"


def test_a_mishear_in_the_disclaimer_routes_to_review_not_fail(snapshot):
    """A garbled but recognisable disclaimer must not be a confident FAIL:
    the safe outcome is REVIEW, never a manufactured critical failure from a
    transcription artefact."""
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(
            0, "agent", 10.0, 14.0,
            "please be advize that this call will be record for quality insurance and training porpoises",
        )
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] != "FAIL"


def test_a_mangled_modem_name_does_not_fail_on_letters_alone(snapshot):
    """STT commonly mangles the modem name (spike note). A close fuzzy match
    on the model number must still PASS or REVIEW, not FAIL outright."""
    check = snapshot.by_id("modem_model")
    turns = [turn(0, "agent", 0.0, 3.0, "you'll get the net calm see if forty modem, free")]

    result = score_type_b_check(check, turns, LEAD)

    assert result["status"] != "FAIL"


# ---------------------------------------------------------------------------
# Silence: no relevant speech at all
# ---------------------------------------------------------------------------


def test_total_silence_on_a_critical_check_is_review_not_fail(snapshot):
    """A critical value never mentioned must REVIEW (hard rule 7), never FAIL
    outright: FAIL asserts a wrong value was heard, which did not happen."""
    check = snapshot.by_id("ongoing_monthly_price")
    turns = [turn(0, "agent", 0.0, 2.0, "thanks for your time today")]

    result = score_type_b_check(check, turns, LEAD)

    assert result["status"] == "REVIEW"


def test_a_long_silent_gap_around_the_disclaimer_does_not_fail_it(snapshot):
    """A dead-air gap before the disclaimer must not itself cause a FAIL:
    dead air is a Type C coaching note on a separate check, never a reason
    to fail a Type A check that is otherwise said correctly."""
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "agent", 0.0, 1.0, "hi, one moment please"),
        turn(1, "agent", 40.0, 44.0, "please be advised that this call will be recorded for quality assurance and training purposes"),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] != "FAIL"


def test_an_empty_transcript_never_produces_a_false_critical_fail(snapshot):
    """No turns at all (silence for the whole call) must REVIEW every
    critical check, never FAIL any of them: nothing was heard to be wrong."""
    for check_id in ("recording_disclaimer", "consent_to_switch", "ongoing_monthly_price"):
        check = snapshot.by_id(check_id)
        if check.type == "A":
            result = score_type_a_check(check, [])
        else:
            result = score_type_b_check(check, [], LEAD)
        assert result["status"] != "FAIL", f"{check_id} FAILed on total silence"


# ---------------------------------------------------------------------------
# ordering rule under mess
# ---------------------------------------------------------------------------


def test_ordering_survives_crosstalk_around_the_disclaimer(snapshot):
    """A short interjection just before the disclaimer must not be read as a
    personal-data question that came first."""
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "customer", 5.0, 5.5, "hello?"),
        turn(1, "agent", 6.0, 10.0, "please be advised that this call will be recorded for quality assurance and training purposes"),
    ]
    disclaimer_result = score_type_a_check(check, turns)

    result = score_disclaimer_ordering(check, turns, disclaimer_result)

    assert result["status"] != "FAIL"
