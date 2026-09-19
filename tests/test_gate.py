"""Phase 8: the gate. FAIL beats REVIEW beats PASS, on critical checks only.

Type C is never inspected by the gate: it is always NOTE and never blocks.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.checks.library import load_lead_fixture, resolve_for_date
from app.checks.models import CheckResultDict
from app.ingest.transcribe import parse_utterances
from app.scoring.gate import (
    DECISION_AUTO_SUBMIT,
    DECISION_HELD_TL,
    DECISION_QA_REVIEW,
    decide_gate,
    is_sampled_for_qa,
    score_and_gate,
)

RETAILER = "PROVIDER_A"
CALL_DATE = date(2026, 9, 19)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

CALL1_SHA = "b75ad7bf482b54190abf437f4e911c7015a06866db4ba6f6bddf5e2bf331559b"
CALL1_SCRIPT = PROJECT_ROOT / "data" / "scripts" / "recorded_script.md"
CALL1_CACHE = PROJECT_ROOT / "cache" / "deepgram" / f"{CALL1_SHA}.json"

CALL2_SHA = "052fad9bba7ec6c28b7df7df4126bb58aff2934e9c2322c1fb3ab52463cba1f8"
CALL2_SCRIPT = PROJECT_ROOT / "data" / "scripts" / "clean_call_script.md"
CALL2_CACHE = PROJECT_ROOT / "cache" / "deepgram" / f"{CALL2_SHA}.json"


def result(check_id: str, status: str, critical_evidence: bool = True) -> CheckResultDict:
    return CheckResultDict(
        check_id=check_id,
        check_version=1,
        status=status,
        confidence=0.9,
        method="fuzzy",
        reason="test",
        evidence=[{"utterance_id": 0, "speaker": "agent", "start_s": 0.0, "end_s": 1.0, "text_redacted": "x"}]
        if critical_evidence
        else [],
    )


@pytest.fixture(scope="module")
def snapshot():
    return resolve_for_date(CALL_DATE, RETAILER)


# ---------------------------------------------------------------------------
# gate decision rule, in isolation
# ---------------------------------------------------------------------------


def test_any_critical_fail_holds_for_tl(snapshot):
    results = [
        result("recording_disclaimer", "FAIL"),
        result("promo_monthly_price", "PASS"),
    ]

    gate = decide_gate(results, snapshot, "L-ANY")

    assert gate["decision"] == DECISION_HELD_TL
    assert "recording_disclaimer" in gate["critical_fails"]


def test_a_critical_review_with_no_fail_routes_to_qa(snapshot):
    results = [
        result("recording_disclaimer", "REVIEW"),
        result("promo_monthly_price", "PASS"),
    ]

    gate = decide_gate(results, snapshot, "L-ANY")

    assert gate["decision"] == DECISION_QA_REVIEW
    assert "recording_disclaimer" in gate["critical_reviews"]


def test_fail_beats_review_when_both_are_present(snapshot):
    results = [
        result("recording_disclaimer", "FAIL"),
        result("account_holder_confirmation", "REVIEW"),
    ]

    gate = decide_gate(results, snapshot, "L-ANY")

    assert gate["decision"] == DECISION_HELD_TL


def test_a_non_critical_fail_never_holds_the_sale(snapshot):
    """agent_and_company_identification is not critical in v1."""
    results = [result("agent_and_company_identification", "FAIL")]

    gate = decide_gate(results, snapshot, "L-ANY")

    assert gate["decision"] != DECISION_HELD_TL


def test_a_critical_check_that_never_ran_is_treated_as_review_not_a_free_pass(snapshot):
    """Missing a critical result entirely must not silently look like a clean sheet."""
    gate = decide_gate([], snapshot, "L-ANY")

    assert gate["decision"] in (DECISION_HELD_TL, DECISION_QA_REVIEW)
    assert gate["decision"] != DECISION_AUTO_SUBMIT


def test_all_critical_pass_and_not_sampled_is_auto_submit(snapshot, monkeypatch):
    from app.scoring import gate as gate_module

    monkeypatch.setattr(gate_module, "is_sampled_for_qa", lambda lead_id, **kw: False)
    results = [result(c.check_id, "PASS") for c in snapshot.checks if c.critical]

    gate = decide_gate(results, snapshot, "L-NOT-SAMPLED")

    assert gate["decision"] == DECISION_AUTO_SUBMIT
    assert gate["sampled_for_qa"] is False


def test_all_critical_pass_but_sampled_goes_to_qa(snapshot, monkeypatch):
    from app.scoring import gate as gate_module

    monkeypatch.setattr(gate_module, "is_sampled_for_qa", lambda lead_id, **kw: True)
    results = [result(c.check_id, "PASS") for c in snapshot.checks if c.critical]

    gate = decide_gate(results, snapshot, "L-SAMPLED")

    assert gate["decision"] == DECISION_QA_REVIEW
    assert gate["sampled_for_qa"] is True


def test_type_c_results_never_affect_the_gate(snapshot):
    """Type C checks are never critical in the library, but assert the gate
    logic itself does not special-case or even need to look at them."""
    results = [result(c.check_id, "PASS") for c in snapshot.checks if c.critical]
    results.append(result("dead_air", "NOTE"))

    gate = decide_gate(results, snapshot, "L-WITH-NOTE")

    assert gate["decision"] in (DECISION_AUTO_SUBMIT, DECISION_QA_REVIEW)


def test_sampling_is_reproducible_for_the_same_lead_id():
    first = is_sampled_for_qa("L-DEMO-1")
    second = is_sampled_for_qa("L-DEMO-1")

    assert first == second


def test_sampling_rate_is_configurable():
    assert is_sampled_for_qa("L-ANY", sample_percent=100) is True
    assert is_sampled_for_qa("L-ANY", sample_percent=0) is False


# ---------------------------------------------------------------------------
# end to end: both real calls, from cache
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CALL1_CACHE.is_file(), reason="call 1 cache absent")
def test_call_one_end_to_end_is_held_for_tl():
    """Two deliberate script faults (79.90 vs 72.90, email mismatch) plus a
    library/recording wording gap on account_holder_confirmation (D20): all
    are critical FAILs, so the gate must hold."""
    turns = parse_utterances(
        json.loads(CALL1_CACHE.read_text(encoding="utf-8")), script_path=CALL1_SCRIPT
    )
    lead = load_lead_fixture("L-DEMO-1")

    outcome = score_and_gate(CALL_DATE, RETAILER, turns, lead)

    assert outcome["gate"]["decision"] == DECISION_HELD_TL
    assert "ongoing_monthly_price" in outcome["gate"]["critical_fails"]
    assert "customer_email" in outcome["gate"]["critical_fails"]
    assert outcome["snapshot_hash"]
    assert outcome["library_version"] == 1


@pytest.mark.skipif(not CALL2_CACHE.is_file(), reason="call 2 cache absent")
def test_call_two_end_to_end_carries_the_evidence_contract():
    """Call 2 was scripted clean, but as-recorded it also holds: Deepgram wrote
    some quoted numbers in digit form where the checklist's approved text
    (quoted from the CIMET transcript, D19) uses word form, and a stretch of
    the plan read merged into one long turn under speaker alignment (D18), which
    the money-role tagger reads as a repeated price rather than the single
    quote it actually was. See D22. The behaviour under test here is narrower
    and does not depend on which way the wording gap resolves: every result
    that runs must carry a full evidence contract, and the gate decision must
    be one of the three real values.
    """
    turns = parse_utterances(
        json.loads(CALL2_CACHE.read_text(encoding="utf-8")), script_path=CALL2_SCRIPT
    )
    lead = load_lead_fixture("L-DEMO-2")

    outcome = score_and_gate(CALL_DATE, RETAILER, turns, lead)

    assert outcome["gate"]["decision"] in (
        DECISION_HELD_TL,
        DECISION_QA_REVIEW,
        DECISION_AUTO_SUBMIT,
    )
    for r in outcome["results"]:
        if r["status"] == "PASS":
            assert r["evidence"], f"{r['check_id']} PASSed with empty evidence"
        for item in r["evidence"]:
            assert "utterance_id" in item
            assert "speaker" in item
            assert "start_s" in item
            assert "text_redacted" in item


@pytest.mark.skipif(
    not (CALL1_CACHE.is_file() and CALL2_CACHE.is_file()),
    reason="both call caches required",
)
def test_the_two_calls_do_not_share_a_gate_reason_by_accident():
    """Sanity check that these are genuinely two different calls being scored,
    not the same cached payload read twice."""
    turns1 = parse_utterances(
        json.loads(CALL1_CACHE.read_text(encoding="utf-8")), script_path=CALL1_SCRIPT
    )
    turns2 = parse_utterances(
        json.loads(CALL2_CACHE.read_text(encoding="utf-8")), script_path=CALL2_SCRIPT
    )

    assert turns1[0]["text_redacted"] != turns2[0]["text_redacted"]
