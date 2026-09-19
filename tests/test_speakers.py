"""Speaker recovery when diarization fails. See DECISIONS D18.

The demo call is one voice reading both parts, so Deepgram labelled all 70
utterances speaker 0 and merged some turns. These tests cover the alignment that
recovers the turns from the script that was read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingest.speakers import (
    SOURCE_ALIGNMENT,
    SOURCE_DIARIZATION,
    SPEAKER_AGENT,
    SPEAKER_CUSTOMER,
    SPEAKER_UNKNOWN,
    align_words_to_script,
    attach_redaction_tokens,
    diarization_speaker_count,
    parse_script,
    resolve_speakers,
    words_with_gaps,
)

SCRIPT = Path(__file__).resolve().parent.parent / "data" / "scripts" / "recorded_script.md"


def words(text: str, start: float = 0.0, rate: float = 0.3, conf: float = 0.97):
    """Evenly spaced words, the shape Deepgram returns."""
    out = []
    t = start
    for token in text.split():
        out.append(
            {
                "word": token.lower().strip(".,?"),
                "punctuated_word": token,
                "start": round(t, 2),
                "end": round(t + rate, 2),
                "confidence": conf,
            }
        )
        t += rate
    return out


@pytest.fixture(scope="module")
def script():
    return parse_script(SCRIPT)


def test_the_script_parses_into_ordered_agent_and_customer_lines(script):
    assert len(script) > 20
    assert script[0].speaker == SPEAKER_AGENT
    assert "hi is this jordan" in script[0].text
    assert script[1].speaker == SPEAKER_CUSTOMER
    # Markers and bold markup are stripped, not left in the text.
    assert all("[" not in line.text and "*" not in line.text for line in script)


def test_stage_directions_and_tables_are_not_spoken_lines(script):
    joined = " ".join(line.text for line in script)
    assert "stay completely quiet" not in joined
    assert "deliberate mismatch" not in joined
    assert "rate card value" not in joined


def test_a_merged_utterance_splits_into_agent_disclaimer_and_customer_reply(script):
    """Deepgram merged these two into one utterance with a 0.16s gap (D18)."""
    stream = words(
        "Before we go any further, just letting you know this call will be "
        "recorded for quality assurance and training purpose. Is that okay with you? "
        "Yeah. That's fine."
    )

    turns = align_words_to_script(stream, script)

    assert len(turns) >= 2
    disclaimer = turns[0]
    reply = turns[1]
    assert disclaimer.speaker == SPEAKER_AGENT
    assert "recorded for quality assurance" in disclaimer.text.lower()
    assert reply.speaker == SPEAKER_CUSTOMER
    assert "fine" in reply.text.lower()
    # The cut keeps real timings, which the evidence contract needs.
    assert disclaimer.end_s <= reply.start_s


def test_the_account_holder_question_and_answer_get_different_speakers(script):
    stream = words(
        "Great. And can I confirm you are the account holder for the internet "
        "service at this address? Yes. I am the account holder."
    )

    turns = align_words_to_script(stream, script)

    question = next(t for t in turns if "confirm you are the account holder" in t.text.lower())
    answer = next(t for t in turns if t.text.lower().startswith("yes"))
    assert question.speaker == SPEAKER_AGENT
    assert answer.speaker == SPEAKER_CUSTOMER


def test_a_garbled_turn_is_unknown_and_never_confidently_attributed(script):
    """Below the match floor the speaker is unknown, not a guess (hard rule 7)."""
    stream = words("wibble frotz quux zzyzx blorp snarf glurk")

    turns = align_words_to_script(stream, script)

    assert turns
    assert all(t.speaker == SPEAKER_UNKNOWN for t in turns)
    assert all(t.script_idx is None for t in turns)


def test_an_unknown_speaker_has_capped_confidence(script):
    from app.config import UNKNOWN_SPEAKER_CONFIDENCE

    turns = align_words_to_script(words("wibble frotz quux zzyzx blorp"), script)

    assert all(t.confidence <= UNKNOWN_SPEAKER_CONFIDENCE for t in turns)


def test_every_aligned_turn_records_its_source(script):
    turns = align_words_to_script(words("Hi, is this Jordan?"), script)

    assert all(t.speaker_source == SOURCE_ALIGNMENT for t in turns)


def test_a_redaction_token_inherits_the_previous_speaker():
    from app.ingest.speakers import Turn

    turns = [
        Turn(
            speaker=SPEAKER_CUSTOMER,
            start_s=227.7,
            end_s=229.7,
            text="Do you need my card now?",
            confidence=0.98,
            speaker_source=SOURCE_ALIGNMENT,
        ),
        Turn(
            speaker=SPEAKER_UNKNOWN,
            start_s=230.9,
            end_s=239.2,
            text="[CREDIT_CARD_1].",
            confidence=0.4,
            speaker_source=SOURCE_ALIGNMENT,
        ),
    ]

    attach_redaction_tokens(turns)

    assert turns[1].speaker == SPEAKER_CUSTOMER


def test_diarization_wins_when_deepgram_found_two_speakers():
    """D18 keeps diarization first. Alignment is only the fallback."""
    payload = {
        "results": {
            "utterances": [
                {
                    "speaker": 0,
                    "start": 0.0,
                    "end": 9.0,
                    "transcript": "this call is being recorded for quality assurance",
                    "confidence": 0.99,
                    "words": [],
                },
                {
                    "speaker": 1,
                    "start": 10.0,
                    "end": 11.0,
                    "transcript": "Yeah, that's fine.",
                    "confidence": 0.98,
                    "words": [],
                },
            ]
        }
    }

    turns = resolve_speakers(payload, SCRIPT)

    assert [t.speaker for t in turns] == [SPEAKER_AGENT, SPEAKER_CUSTOMER]
    assert all(t.speaker_source == SOURCE_DIARIZATION for t in turns)


def test_speaker_counting_sees_the_single_speaker_case():
    single = [{"speaker": 0}, {"speaker": 0}, {"speaker": 0}]
    both = [{"speaker": 0}, {"speaker": 1}]

    assert diarization_speaker_count(single) == 1
    assert diarization_speaker_count(both) == 2


def test_word_gaps_are_carried_for_tie_breaking():
    utterances = [
        {
            "words": [
                {"word": "a", "start": 0.0, "end": 0.5, "confidence": 1.0},
                {"word": "b", "start": 1.3, "end": 1.6, "confidence": 1.0},
            ]
        }
    ]

    flat = words_with_gaps(utterances)

    assert flat[0]["gap_after"] == pytest.approx(0.8)
    assert flat[-1]["gap_after"] == 0.0


def test_turns_stay_in_time_order(script):
    stream = words(
        "Hi, is this Jordan? Yeah, that's me. Hi. Before we go any further, just "
        "letting you know this call will be recorded for quality assurance."
    )

    turns = align_words_to_script(stream, script)

    starts = [t.start_s for t in turns]
    assert starts == sorted(starts)
