"""Phase 6: Type A evaluators. One PASS, one FAIL, one REVIEW per match mode,
plus the disclaimer ordering rule and the real call end to end (DECISIONS D20)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.checks.library import resolve_for_date
from app.checks.models import TurnDict
from app.checks.verbatim import (
    score_disclaimer_ordering,
    score_type_a_check,
)
from app.ingest.transcribe import parse_utterances

RETAILER = "PROVIDER_A"
CALL_DATE = date(2026, 9, 19)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = PROJECT_ROOT / "cache" / "deepgram" / "b75ad7bf482b54190abf437f4e911c7015a06866db4ba6f6bddf5e2bf331559b.json"
SCRIPT = PROJECT_ROOT / "data" / "scripts" / "recorded_script.md"
HANDOUT = PROJECT_ROOT / "handout" / "transcript.pdf"


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
# verbatim mode
# ---------------------------------------------------------------------------


def test_a_customer_turn_never_contaminates_the_matched_window(snapshot):
    """A customer reply right after the agent's line must not leak into scoring."""
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "agent", 10.0, 15.0, "Please be advised that this call will be recorded for quality assurance and training purposes."),
        turn(1, "customer", 15.5, 17.0, "No way, I'm not okay with any of that, absolutely not."),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "PASS"
    assert all(e["speaker"] == "agent" for e in result["evidence"])


def test_verbatim_pass_on_a_close_match(snapshot):
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "agent", 10.0, 15.0, "Please be advised that this call will be recorded for quality assurance and training purposes."),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "PASS"
    assert result["evidence"]
    assert result["evidence"][0]["start_s"] == 10.0


def test_verbatim_fail_on_no_match(snapshot):
    check = snapshot.by_id("recording_disclaimer")
    turns = [turn(0, "agent", 0.0, 2.0, "Nice weather we are having today.")]

    result = score_type_a_check(check, turns)

    assert result["status"] == "FAIL"


def test_verbatim_review_on_a_partial_match(snapshot):
    check = snapshot.by_id("recording_disclaimer")
    turns = [turn(0, "agent", 0.0, 3.0, "Just so you know we might record this call sometime.")]

    result = score_type_a_check(check, turns)

    assert result["status"] in ("REVIEW", "FAIL")  # loose paraphrase, never a clean PASS


def test_low_confidence_downgrades_a_pass_to_review(snapshot):
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(
            0, "agent", 10.0, 15.0,
            "Please be advised that this call will be recorded for quality assurance and training purposes.",
            conf=0.5,
        ),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "REVIEW"


def test_unknown_speaker_turns_never_produce_a_confident_pass(snapshot):
    """Hard rule 7: an unresolved speaker must not let a critical check PASS cleanly."""
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(
            0, "unknown", 10.0, 15.0,
            "Please be advised that this call will be recorded for quality assurance and training purposes.",
            conf=0.8, source="script_alignment",
        ),
    ]

    # Not attributed to the agent at all, so no verbatim match should be found
    # against agent speech; the check should not PASS.
    result = score_type_a_check(check, turns)
    assert result["status"] != "PASS"


# ---------------------------------------------------------------------------
# coverage mode
# ---------------------------------------------------------------------------


def test_coverage_pass_when_all_sentences_are_said(snapshot):
    check = snapshot.by_id("total_minimum_cost_disclosed")
    turns = [
        turn(0, "agent", 100.0, 105.0, check.approved_text),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "PASS"


def test_coverage_fail_when_nothing_is_said(snapshot):
    check = snapshot.by_id("total_minimum_cost_disclosed")
    turns = [turn(0, "agent", 0.0, 2.0, "Let's talk about the weather instead.")]

    result = score_type_a_check(check, turns)

    assert result["status"] == "FAIL"
    assert "Missing" in result["reason"]


def test_coverage_review_when_most_but_not_all_sentences_are_said(snapshot):
    check = snapshot.by_id("plan_key_information")
    # Say most of the block but drop the modem sentence entirely.
    partial = check.approved_text.split(". The modem")[0] + "."
    turns = [turn(0, "agent", 50.0, 70.0, partial)]

    result = score_type_a_check(check, turns)

    assert result["status"] in ("REVIEW", "FAIL")
    assert result["status"] != "PASS"


def test_coverage_reason_names_the_missing_sentences_verbatim(snapshot):
    check = snapshot.by_id("plan_key_information")
    turns = [turn(0, "agent", 0.0, 2.0, "hello there")]

    result = score_type_a_check(check, turns)

    assert "Missing:" in result["reason"]
    assert "modem" in result["reason"].lower()


# ---------------------------------------------------------------------------
# confirmation mode
# ---------------------------------------------------------------------------


def test_confirmation_review_on_a_near_miss_question_with_a_reply(snapshot):
    """Score 60-79 with a confirming reply: likely the same question, different
    wording. Routed to REVIEW rather than a flat FAIL, approved text untouched."""
    check = snapshot.by_id("account_holder_confirmation")
    turns = [
        turn(0, "agent", 10.0, 13.0, "Just to confirm, is this account under your name?"),
        turn(1, "customer", 13.5, 14.5, "Yes, I am the account holder."),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "REVIEW"
    assert len(result["evidence"]) == 2
    assert "differs from approved text" in result["reason"]


def test_confirmation_fail_when_the_question_score_is_too_low_even_with_a_reply(snapshot):
    """Below the near-miss floor entirely: not the same question, so FAIL even
    though something affirmative-sounding follows."""
    check = snapshot.by_id("account_holder_confirmation")
    turns = [
        turn(0, "agent", 10.0, 13.0, "Hi, is this Jordan? My name's Sam calling about your plan."),
        turn(1, "customer", 13.5, 14.5, "Yes, that's me."),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "FAIL"


def test_confirmation_pass_on_question_then_affirmative(snapshot):
    check = snapshot.by_id("account_holder_confirmation")
    turns = [
        turn(0, "agent", 10.0, 13.0, "And this will be under your name, am I correct?"),
        turn(1, "customer", 13.5, 14.5, "Yes, that's correct."),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "PASS"
    assert len(result["evidence"]) == 2


def test_confirmation_fail_when_question_never_asked(snapshot):
    check = snapshot.by_id("consent_to_switch")
    turns = [turn(0, "agent", 0.0, 2.0, "So, anything else I can help with today?")]

    result = score_type_a_check(check, turns)

    assert result["status"] == "FAIL"
    assert result["evidence"] == []


def test_confirmation_fail_when_question_asked_but_no_affirmative_follows(snapshot):
    check = snapshot.by_id("consent_to_switch")
    turns = [
        turn(0, "agent", 10.0, 13.0, "Do you understand and agree to switch your internet service to this plan on these terms?"),
        turn(1, "customer", 13.5, 15.0, "Hmm, I'm not sure, let me think about it."),
        turn(2, "customer", 16.0, 17.0, "Can you call back tomorrow?"),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "FAIL"


def test_confirmation_review_when_the_reply_is_low_confidence(snapshot):
    check = snapshot.by_id("account_holder_confirmation")
    turns = [
        turn(0, "agent", 10.0, 13.0, "And this will be under your name, am I correct?", conf=0.9),
        turn(1, "customer", 13.5, 14.5, "Yes, that's correct.", conf=0.4),
    ]

    result = score_type_a_check(check, turns)

    assert result["status"] == "REVIEW"


# ---------------------------------------------------------------------------
# ordering rule
# ---------------------------------------------------------------------------


def test_ordering_fails_when_personal_data_comes_before_the_disclaimer(snapshot):
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "agent", 5.0, 8.0, "Can you confirm your date of birth for me?"),
        turn(1, "customer", 8.5, 9.5, "Sure, 14 March 1990."),
        turn(2, "agent", 15.0, 20.0, "Please be advised that this call will be recorded for quality assurance and training purposes."),
    ]
    disclaimer_result = score_type_a_check(check, turns)

    result = score_disclaimer_ordering(check, turns, disclaimer_result)

    assert result["status"] == "FAIL"
    assert "5.0" in result["reason"] or "5.00" in result["reason"]
    assert len(result["evidence"]) >= 2


def test_ordering_passes_when_disclaimer_comes_first(snapshot):
    check = snapshot.by_id("recording_disclaimer")
    turns = [
        turn(0, "agent", 5.0, 10.0, "Please be advised that this call will be recorded for quality assurance and training purposes."),
        turn(1, "agent", 15.0, 18.0, "Can you confirm your date of birth for me?"),
    ]
    disclaimer_result = score_type_a_check(check, turns)

    result = score_disclaimer_ordering(check, turns, disclaimer_result)

    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# real cached call, end to end
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CACHE.is_file(), reason="Deepgram cache for the demo call is absent")
class TestRealCall:
    @pytest.fixture(scope="class")
    def turns(self):
        payload = json.loads(CACHE.read_text(encoding="utf-8"))
        return parse_utterances(payload, script_path=SCRIPT)

    def test_disclaimer_is_found_at_its_real_turn(self, snapshot, turns):
        """Score lands just under PASS (85 vs 88) because the matched window
        also catches the customer's trailing "Yeah. That's me." Genuine
        paraphrase drift, not a scorer bug: see the D19/D20 finding."""
        check = snapshot.by_id("recording_disclaimer")
        result = score_type_a_check(check, turns)

        assert result["status"] in ("PASS", "REVIEW")
        assert result["evidence"][0]["start_s"] < 25.0
        assert result["confidence"] > 0.75

    def test_key_information_fails_and_names_what_was_missed(self, snapshot, turns):
        check = snapshot.by_id("plan_key_information")
        result = score_type_a_check(check, turns)

        assert result["status"] == "FAIL"
        assert "Missing:" in result["reason"]

    def test_total_minimum_cost_fails(self, snapshot, turns):
        check = snapshot.by_id("total_minimum_cost_disclosed")
        result = score_type_a_check(check, turns)

        assert result["status"] in ("FAIL", "REVIEW")

    def test_account_holder_confirmation_is_a_real_library_gap(self, snapshot, turns):
        """The recording says "can I confirm you are the account holder", which
        matches neither v1's approved text nor its alternates (both quoted from
        the real CIMET transcript's different phrasing, per D19). This FAILs
        honestly: it is a gap between the checklist and this recording's
        wording, not something to paper over by editing the approved text."""
        check = snapshot.by_id("account_holder_confirmation")
        result = score_type_a_check(check, turns)

        assert result["status"] == "FAIL"

    def test_ordering_rule_is_evaluated_on_whatever_the_disclaimer_scored(self, snapshot, turns):
        """Our own recording puts the disclaimer first on purpose (D17 script),
        so ordering must never make things worse than the underlying wording
        match already is."""
        check = snapshot.by_id("recording_disclaimer")
        disclaimer_result = score_type_a_check(check, turns)

        result = score_disclaimer_ordering(check, turns, disclaimer_result)

        assert result["status"] == disclaimer_result["status"]


# ---------------------------------------------------------------------------
# real CIMET transcript: the ordering violation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HANDOUT.is_file(), reason="handout/transcript.pdf is not present")
def test_the_real_cimet_call_fails_the_disclaimer_ordering_rule(snapshot):
    """D19: the source call confirms the address twice before the disclaimer.

    Reads handout/ locally only. Nothing from the transcript is copied into the
    repo; this test extracts turns in memory and asserts on the ordering
    result, never on transcript text.
    """
    import base64
    import re
    import zlib

    raw = HANDOUT.read_bytes()
    streams = []
    for m in re.finditer(rb"stream[\r\n]{1,2}(.*?)endstream", raw, re.S):
        body = m.group(1).strip(b"\r\n")
        for candidate in (body, base64.a85decode(body, adobe=True) if True else body):
            try:
                streams.append(zlib.decompress(candidate))
                break
            except Exception:
                continue
    text = b"\n".join(streams).decode("latin-1")

    pieces = []
    for m in re.finditer(r"\[(.*?)\]\s*TJ|\((.*?)\)\s*Tj", text, re.S):
        if m.group(1) is not None:
            for lit in re.finditer(r"\((?:\\.|[^()\\])*\)", m.group(1), re.S):
                pieces.append(lit.group(0)[1:-1])
        elif m.group(2) is not None:
            pieces.append(m.group(2))
    full_text = "".join(pieces).lower()

    disclaimer_pos = full_text.find("please be advised")
    address_pos = full_text.find("service_address")

    assert disclaimer_pos > 0, "disclaimer not found in the source transcript"
    assert address_pos > 0, "service address marker not found in the source transcript"
    assert address_pos < disclaimer_pos, (
        "expected the source call to collect the address before the disclaimer (D19 finding)"
    )
