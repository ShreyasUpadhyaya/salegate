"""Phase 7: Type B extractors and factual comparisons.

Every extractor isolates its value's span before normalising (D14 rule),
extended past email to money, dates and addresses. Values the agent quotes
come from agent turns; DOB and address may be said by either side. Every
mention is checked, so a call that quotes two different values for the same
field FAILs, citing each mismatching mention with its timestamp.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.checks.factual import score_type_b_check
from app.checks.library import load_lead_fixture, resolve_for_date
from app.checks.models import TurnDict
from app.checks.normalise import (
    address_parts,
    extract_address_span,
    extract_dob,
    extract_download_speed_mbps,
    extract_modem_model,
    extract_money_mentions,
    extract_promo_term_months,
    extract_spoken_email,
)
from app.ingest.transcribe import parse_utterances

RETAILER = "PROVIDER_A"
CALL_DATE = date(2026, 9, 19)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = (
    PROJECT_ROOT / "cache" / "deepgram"
    / "b75ad7bf482b54190abf437f4e911c7015a06866db4ba6f6bddf5e2bf331559b.json"
)
SCRIPT = PROJECT_ROOT / "data" / "scripts" / "recorded_script.md"


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


@pytest.fixture(scope="module")
def rate_card():
    return load_lead_fixture("L-DEMO-1")["rate_card"]


@pytest.fixture(scope="module")
def crm():
    return load_lead_fixture("L-DEMO-1")["crm_fields"]


# ---------------------------------------------------------------------------
# extractor unit tests, including mid-utterance spans
# ---------------------------------------------------------------------------


def test_money_digit_form_mid_utterance():
    text = "so based on that plan it works out to $42.90 a month for you, sounds good?"
    assert [v for v, _ in extract_money_mentions(text)] == [42.9]


def test_money_spoken_form():
    text = "it will be forty two dollars and ninety a month for the first six months"
    values = [v for v, _ in extract_money_mentions(text)]
    assert 42.9 in values


def test_money_role_tagging_promo_vs_ongoing():
    text = "for the first six months it's $42.90 a month, then $79.90 ongoing"
    mentions = extract_money_mentions(text)
    assert (42.9, "promo") in mentions
    assert (79.9, "ongoing") in mentions


def test_promo_term_mid_utterance():
    text = "so for the first six months you get the discounted rate, after that it reverts"
    assert extract_promo_term_months(text) == 6


def test_download_speed_digit_and_word_forms():
    assert extract_download_speed_mbps("typical evening download speeds of 25 megabits per second") == 25.0
    assert extract_download_speed_mbps("you get twenty five Mbps on this plan") == 25.0


def test_modem_model_mangled_by_stt():
    assert extract_modem_model("you get a netcomm c f 40 modem included free") == "Netcomm CF40"
    assert extract_modem_model("the netcom p s forty wi fi six modem") == "Netcomm CF40"


def test_email_spoken_span_mid_utterance():
    text = "i have it on file as j dot avery at example dot com, is that current?"
    assert extract_spoken_email(text) == "j.avery@example.com"


def test_email_literal_form_from_smart_format():
    assert extract_spoken_email("i have it as j.avery@example.com on file") == "j.avery@example.com"


def test_dob_spoken_form():
    assert extract_dob("fourteenth of march, nineteen ninety") == "1990-03-14"


def test_dob_numeric_day_first_default():
    """Both parts <= 12: ambiguous, defaults day-first (en-AU), per D19."""
    assert extract_dob("date of birth is 05/03/1985") == "1985-03-05"


def test_dob_numeric_month_first_when_first_number_exceeds_12():
    """Deepgram writes the spoken DOB as US month/day order on the real call."""
    assert extract_dob("03/14/1990. and the service address is") == "1990-03-14"


def test_address_span_mid_utterance():
    text = "sure, the service address is 12 sample street, testville, new south wales 2000, is that right"
    found = extract_address_span(text)
    assert found is not None
    assert address_parts(found) == ("12", "2000")


# ---------------------------------------------------------------------------
# check-level PASS / FAIL / REVIEW, one per extractor
# ---------------------------------------------------------------------------


def test_ongoing_price_pass(snapshot, rate_card):
    check = snapshot.by_id("ongoing_monthly_price")
    turns = [turn(0, "agent", 10.0, 12.0, "after that it goes to $72.90 a month ongoing")]

    result = score_type_b_check(check, turns, {"rate_card": rate_card, "crm_fields": {}})

    assert result["status"] == "PASS"


def test_ongoing_price_fail_cites_the_mismatch(snapshot, rate_card):
    check = snapshot.by_id("ongoing_monthly_price")
    turns = [turn(0, "agent", 10.0, 12.0, "after that it goes to $79.90 a month ongoing")]

    result = score_type_b_check(check, turns, {"rate_card": rate_card, "crm_fields": {}})

    assert result["status"] == "FAIL"
    assert "10.0" in result["reason"]


def test_ongoing_price_review_when_never_mentioned(snapshot, rate_card):
    check = snapshot.by_id("ongoing_monthly_price")
    turns = [turn(0, "agent", 0.0, 2.0, "thanks for choosing us today")]

    result = score_type_b_check(check, turns, {"rate_card": rate_card, "crm_fields": {}})

    assert result["status"] == "REVIEW"
    assert result["evidence"] == []


def test_email_pass(snapshot, crm):
    check = snapshot.by_id("customer_email")
    turns = [turn(0, "agent", 0.0, 2.0, "i have it as jordan.avery@example.com on file")]

    result = score_type_b_check(check, turns, {"rate_card": {}, "crm_fields": crm})

    assert result["status"] == "PASS"


def test_email_fail(snapshot, crm):
    check = snapshot.by_id("customer_email")
    turns = [turn(0, "agent", 116.8, 118.0, "i have it as j.avery@example.com")]

    result = score_type_b_check(check, turns, {"rate_card": {}, "crm_fields": crm})

    assert result["status"] == "FAIL"
    assert "116.8" in result["reason"]


def test_email_review_when_never_mentioned(snapshot, crm):
    check = snapshot.by_id("customer_email")
    turns = [turn(0, "agent", 0.0, 2.0, "let's move on to the next step")]

    result = score_type_b_check(check, turns, {"rate_card": {}, "crm_fields": crm})

    assert result["status"] == "REVIEW"


# ---------------------------------------------------------------------------
# real cached call
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CACHE.is_file(), reason="Deepgram cache for the demo call is absent")
class TestRealCall:
    @pytest.fixture(scope="class")
    def turns(self):
        payload = json.loads(CACHE.read_text(encoding="utf-8"))
        return parse_utterances(payload, script_path=SCRIPT)

    @pytest.fixture(scope="class")
    def lead(self):
        return load_lead_fixture("L-DEMO-1")

    def test_ongoing_price_fails_at_both_mentions(self, snapshot, turns, lead):
        """The agent says 79.90 twice; rate card says 72.90. Both timestamps cited."""
        check = snapshot.by_id("ongoing_monthly_price")
        result = score_type_b_check(check, turns, lead)

        assert result["status"] == "FAIL"
        times = [e["start_s"] for e in result["evidence"] if "79.9" in e["text_redacted"]]
        assert len(times) >= 2
        assert any(69 < t < 72 for t in times)
        assert any(103 < t < 106 for t in times)

    def test_email_fails(self, snapshot, turns, lead):
        check = snapshot.by_id("customer_email")
        result = score_type_b_check(check, turns, lead)

        assert result["status"] == "FAIL"

    def test_promo_price_passes(self, snapshot, turns, lead):
        check = snapshot.by_id("promo_monthly_price")
        result = score_type_b_check(check, turns, lead)

        assert result["status"] == "PASS"

    def test_dob_passes(self, snapshot, turns, lead):
        check = snapshot.by_id("customer_dob")
        result = score_type_b_check(check, turns, lead)

        assert result["status"] == "PASS"

    def test_address_passes(self, snapshot, turns, lead):
        check = snapshot.by_id("service_address")
        result = score_type_b_check(check, turns, lead)

        assert result["status"] == "PASS"

    def test_download_speed_passes(self, snapshot, turns, lead):
        check = snapshot.by_id("plan_download_speed")
        result = score_type_b_check(check, turns, lead)

        assert result["status"] == "PASS"

    def test_every_result_carries_the_evidence_contract(self, snapshot, turns, lead):
        for check in snapshot.of_type("B"):
            result = score_type_b_check(check, turns, lead)
            assert result["status"] in ("PASS", "FAIL", "REVIEW", "NOTE", "NA")
            if result["status"] == "PASS":
                assert result["evidence"], f"{check.check_id} PASSed with no evidence"
            for item in result["evidence"]:
                assert "utterance_id" in item
                assert "speaker" in item
                assert "start_s" in item
                assert "text_redacted" in item
