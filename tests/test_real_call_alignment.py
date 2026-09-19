"""End to end on the real cached Deepgram response for the demo call.

Short hand-built fixtures missed a bug that collapsed all 4.5 minutes into one
turn, because the fixtures were too short to show it (DECISIONS D18). These
tests run the actual 70-utterance payload through the whole speaker pipeline.

They skip when the cache is absent, since cache/ is gitignored and a fresh
clone has not called Deepgram yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingest.speakers import SPEAKER_AGENT, SPEAKER_CUSTOMER
from app.ingest.transcribe import parse_utterances

DEMO_SHA = "b75ad7bf482b54190abf437f4e911c7015a06866db4ba6f6bddf5e2bf331559b"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = PROJECT_ROOT / "cache" / "deepgram" / f"{DEMO_SHA}.json"
SCRIPT = PROJECT_ROOT / "data" / "scripts" / "recorded_script.md"

pytestmark = pytest.mark.skipif(
    not CACHE.is_file(), reason="Deepgram cache for the demo call is not present"
)


@pytest.fixture(scope="module")
def rows():
    payload = json.loads(CACHE.read_text(encoding="utf-8"))
    return parse_utterances(payload, script_path=SCRIPT)


def test_the_call_does_not_collapse_into_one_turn(rows):
    """The bug this file exists for: one turn spanning the whole call."""
    assert len(rows) >= 20

    longest = max(r["end_s"] - r["start_s"] for r in rows)
    assert longest < 120.0, "a single turn covers most of the call"


def test_both_speakers_are_present_and_neither_dominates_completely(rows):
    talk: dict[str, float] = {}
    for row in rows:
        talk[row["speaker"]] = talk.get(row["speaker"], 0.0) + (row["end_s"] - row["start_s"])
    total = sum(talk.values())

    assert talk.get(SPEAKER_AGENT, 0) > 0
    assert talk.get(SPEAKER_CUSTOMER, 0) > 0
    # An outbound sales call is agent heavy, but not the entire call.
    agent_share = talk[SPEAKER_AGENT] / total
    assert 0.6 < agent_share < 0.95


def test_turns_are_in_time_order_and_do_not_overlap(rows):
    for previous, current in zip(rows, rows[1:], strict=False):
        assert previous["start_s"] <= current["start_s"]
        assert previous["end_s"] <= current["start_s"] + 0.001


def test_the_check_bearing_lines_land_on_the_right_speaker(rows):
    """Every line a check depends on, and who must own it."""
    expected = [
        ("recorded for quality assurance", SPEAKER_AGENT),
        ("account holder for the internet service", SPEAKER_AGENT),
        ("yes. i am the account holder", SPEAKER_CUSTOMER),
        ("j.avery@example.com", SPEAKER_AGENT),
        ("agree to switch your internet", SPEAKER_AGENT),
        ("stop there", SPEAKER_AGENT),
    ]

    for fragment, speaker in expected:
        matches = [r for r in rows if fragment in r["text_redacted"].lower()]
        assert matches, f"{fragment!r} not found in the transcript"
        for row in matches:
            assert row["speaker"] == speaker, f"{fragment!r} attributed to {row['speaker']}"


def test_the_wrong_ongoing_price_is_attributed_to_the_agent(rows):
    """79.90 is the headline catch, and only counts if the agent said it."""
    quotes = [r for r in rows if "79.90" in r["text_redacted"]]

    assert len(quotes) >= 2, "the wrong price should appear twice"
    assert all(r["speaker"] == SPEAKER_AGENT for r in quotes)


def test_the_card_number_is_redacted_and_never_the_agents(rows):
    """Hard rule 4, proven on real audio rather than a fixture."""
    tokens = [r for r in rows if "[CREDIT_CARD" in r["text_redacted"]]

    assert tokens, "the redaction token is missing from the real transcript"
    for row in tokens:
        assert row["speaker"] == SPEAKER_CUSTOMER
    # No digit run long enough to be a card survives anywhere.
    for row in rows:
        digits = "".join(c for c in row["text_redacted"] if c.isdigit())
        assert "4111111111111111" not in digits


def test_the_dead_air_gap_survives_alignment(rows):
    """The 24s pause is the Type C fixture and must stay visible."""
    from app.config import DEAD_AIR_THRESHOLD_S

    gaps = [
        current["start_s"] - previous["end_s"]
        for previous, current in zip(rows, rows[1:], strict=False)
    ]

    assert max(gaps) >= DEAD_AIR_THRESHOLD_S


def test_every_turn_records_that_it_came_from_alignment(rows):
    assert all(r["speaker_source"] == "script_alignment" for r in rows)


def test_no_turn_is_left_unknown_on_the_demo_call(rows):
    """Not a hard requirement in general, but true today. If this fails the
    alignment has drifted and the transcript should be re-read before trusting
    any score built on it."""
    unknown = [r for r in rows if r["speaker"] == "unknown"]

    assert not unknown, f"{len(unknown)} turns could not be attributed"
