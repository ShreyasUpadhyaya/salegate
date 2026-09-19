"""Phase 8: Type C behaviour notes. Always NOTE, never blocks (PLAN.md)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.checks.behaviour import (
    INTERRUPTION_FOLLOW_ON_S,
    score_dead_air,
    score_interruptions,
    score_talk_ratio,
)
from app.checks.library import resolve_for_date
from app.checks.models import TurnDict
from app.ingest.transcribe import parse_utterances

RETAILER = "PROVIDER_A"
CALL_DATE = date(2026, 9, 19)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_CALL1 = (
    PROJECT_ROOT / "cache" / "deepgram"
    / "b75ad7bf482b54190abf437f4e911c7015a06866db4ba6f6bddf5e2bf331559b.json"
)
SCRIPT_CALL1 = PROJECT_ROOT / "data" / "scripts" / "recorded_script.md"


def turn(idx, speaker, start, end, text="x") -> TurnDict:
    return {
        "idx": idx,
        "speaker": speaker,
        "start_s": start,
        "end_s": end,
        "text_redacted": text,
        "avg_confidence": 0.95,
        "speaker_source": "diarization",
    }


@pytest.fixture(scope="module")
def snapshot():
    return resolve_for_date(CALL_DATE, RETAILER)


# ---------------------------------------------------------------------------
# dead air
# ---------------------------------------------------------------------------


def test_dead_air_notes_a_gap_at_or_over_threshold(snapshot):
    check = snapshot.by_id("dead_air")
    turns = [
        turn(0, "agent", 0.0, 10.0),
        turn(1, "customer", 31.0, 32.0),
    ]

    result = score_dead_air(check, turns)

    assert result["status"] == "NOTE"
    assert "20" in result["reason"] or "21" in result["reason"]
    assert result["evidence"]


def test_dead_air_ignores_a_gap_under_threshold(snapshot):
    check = snapshot.by_id("dead_air")
    turns = [
        turn(0, "agent", 0.0, 10.0),
        turn(1, "customer", 15.0, 16.0),
    ]

    result = score_dead_air(check, turns)

    assert result["status"] == "NOTE"
    assert result["evidence"] == []


def test_dead_air_never_blocks_regardless_of_gap_length(snapshot):
    """Even an absurd gap stays NOTE. Type C never FAILs, never REVIEWs."""
    check = snapshot.by_id("dead_air")
    turns = [turn(0, "agent", 0.0, 5.0), turn(1, "customer", 600.0, 601.0)]

    result = score_dead_air(check, turns)

    assert result["status"] == "NOTE"


def test_dead_air_lists_every_gap_not_just_the_first(snapshot):
    check = snapshot.by_id("dead_air")
    turns = [
        turn(0, "agent", 0.0, 5.0),
        turn(1, "customer", 30.0, 31.0),
        turn(2, "agent", 32.0, 33.0),
        turn(3, "customer", 60.0, 61.0),
    ]

    result = score_dead_air(check, turns)

    assert len(result["evidence"]) == 4  # two gaps, two turns of evidence each


# ---------------------------------------------------------------------------
# interruptions
# ---------------------------------------------------------------------------


def test_interruption_flagged_within_the_follow_on_window(snapshot):
    check = snapshot.by_id("interruptions")
    turns = [
        turn(0, "agent", 0.0, 10.0),
        turn(1, "customer", 10.2, 11.0),
    ]

    result = score_interruptions(check, turns)

    assert result["status"] == "NOTE"
    assert result["evidence"]


def test_no_interruption_outside_the_follow_on_window(snapshot):
    check = snapshot.by_id("interruptions")
    turns = [
        turn(0, "agent", 0.0, 10.0),
        turn(1, "customer", 12.0, 13.0),
    ]

    result = score_interruptions(check, turns)

    assert result["evidence"] == []


def test_a_same_speaker_follow_on_is_not_an_interruption(snapshot):
    check = snapshot.by_id("interruptions")
    turns = [
        turn(0, "agent", 0.0, 10.0),
        turn(1, "agent", 10.1, 12.0),
    ]

    result = score_interruptions(check, turns)

    assert result["evidence"] == []


def test_interruption_boundary_is_inclusive(snapshot):
    check = snapshot.by_id("interruptions")
    turns = [
        turn(0, "agent", 0.0, 10.0),
        turn(1, "customer", 10.0 + INTERRUPTION_FOLLOW_ON_S, 11.0),
    ]

    result = score_interruptions(check, turns)

    assert result["evidence"]


# ---------------------------------------------------------------------------
# talk ratio
# ---------------------------------------------------------------------------


def test_talk_ratio_reports_the_agent_share(snapshot):
    check = snapshot.by_id("talk_ratio")
    turns = [
        turn(0, "agent", 0.0, 8.0),
        turn(1, "customer", 8.0, 10.0),
    ]

    result = score_talk_ratio(check, turns)

    assert result["status"] == "NOTE"
    assert "80.0%" in result["reason"]


def test_talk_ratio_never_blocks_even_when_agent_dominates_completely(snapshot):
    check = snapshot.by_id("talk_ratio")
    turns = [turn(0, "agent", 0.0, 100.0)]

    result = score_talk_ratio(check, turns)

    assert result["status"] == "NOTE"


def test_talk_ratio_with_no_turns_does_not_divide_by_zero(snapshot):
    check = snapshot.by_id("talk_ratio")

    result = score_talk_ratio(check, [])

    assert result["status"] == "NOTE"


# ---------------------------------------------------------------------------
# real cached call 1: the 24.12s dead air at 141.60s
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CACHE_CALL1.is_file(), reason="Deepgram cache for call 1 is absent")
def test_the_real_dead_air_is_found_at_its_real_timestamp(snapshot):
    check = snapshot.by_id("dead_air")
    payload = json.loads(CACHE_CALL1.read_text(encoding="utf-8"))
    turns = parse_utterances(payload, script_path=SCRIPT_CALL1)

    result = score_dead_air(check, turns)

    assert result["status"] == "NOTE"
    assert any(abs(e["end_s"] - 141.60) < 0.5 for e in result["evidence"])
    assert "24." in result["reason"]
