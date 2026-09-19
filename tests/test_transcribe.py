"""Phase 3: Deepgram parsing, speaker mapping and caching. No network here.

Every test runs against a hand-built payload shaped like Deepgram's, so the
suite is offline and spends nothing.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.ingest import transcribe
from app.ingest.transcribe import (
    SPEAKER_AGENT,
    SPEAKER_CUSTOMER,
    TranscriptionError,
    build_params,
    identify_agent_speaker,
    parse_utterances,
    save_utterances,
    transcribe_recording,
    utterance_gaps,
)
from app.models import Lead, Recording, RecordingState, Utterance

CALL_AT = datetime(2026, 9, 19, 10, 5)


def seed_lead() -> Lead:
    return Lead(
        lead_id="L-1",
        retailer="R",
        agent_id="A",
        call_started_at=CALL_AT,
        crm_fields={},
    )

DISCLAIMER = "Before we go any further, please be advised that this call is being recorded."


def payload(utterances: list[dict]) -> dict:
    return {"metadata": {"duration": 270.5}, "results": {"utterances": utterances}}


def utterance(speaker: int, start: float, end: float, text: str, conf: float = 0.97) -> dict:
    return {
        "speaker": speaker,
        "start": start,
        "end": end,
        "transcript": text,
        "confidence": conf,
    }


DEMO = payload(
    [
        utterance(0, 0.0, 2.4, "Good afternoon, am I speaking with Jordan Avery?"),
        utterance(1, 3.5, 4.6, "Yes, speaking."),
        utterance(0, 5.2, 12.8, DISCLAIMER),
        utterance(1, 14.0, 15.1, "Yeah, that's fine."),
    ]
)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        yield s


def test_the_disclaimer_speaker_is_the_agent():
    assert identify_agent_speaker(DEMO["results"]["utterances"]) == 0


def test_the_agent_is_found_even_when_they_speak_second():
    """Diarization can label the customer 0. The disclaimer decides, not the number."""
    swapped = payload(
        [
            utterance(1, 0.0, 2.0, "Hello?"),
            utterance(0, 3.0, 9.0, DISCLAIMER),
        ]
    )
    assert identify_agent_speaker(swapped["results"]["utterances"]) == 0


def test_the_first_speaker_is_the_fallback_when_no_disclaimer():
    no_disclaimer = payload(
        [
            utterance(1, 0.0, 2.0, "Good afternoon, am I speaking with Jordan?"),
            utterance(0, 3.0, 4.0, "Yes."),
        ]
    )
    assert identify_agent_speaker(no_disclaimer["results"]["utterances"]) == 1


def test_utterances_are_parsed_with_speakers_and_timings():
    rows = parse_utterances(DEMO)

    assert [r["speaker"] for r in rows] == [
        SPEAKER_AGENT,
        SPEAKER_CUSTOMER,
        SPEAKER_AGENT,
        SPEAKER_CUSTOMER,
    ]
    assert [r["idx"] for r in rows] == [0, 1, 2, 3]
    assert rows[0]["start_s"] == 0.0
    assert rows[0]["end_s"] == 2.4
    assert rows[0]["avg_confidence"] == pytest.approx(0.97)
    assert rows[2]["text_redacted"] == DISCLAIMER


def test_an_empty_transcript_parses_to_nothing():
    assert parse_utterances(payload([])) == []
    assert parse_utterances({}) == []


def test_diarize_is_on_and_multichannel_is_never_sent():
    """D17: one microphone, one track. multichannel would be wrong here."""
    params = build_params()

    assert params["diarize"] == "true"
    assert "multichannel" not in params
    assert params["utterances"] == "true"


def test_pci_redaction_is_always_requested():
    """Hard rule 4. Card digits are masked at source."""
    assert build_params()["redact"] == "pci"


def test_utterances_are_saved_and_replaced_not_duplicated(session):
    session.add(seed_lead())
    session.add(Recording(id=1, lead_id="L-1", sha256="abc", path="x.wav"))
    session.commit()

    rows = parse_utterances(DEMO)
    assert save_utterances(session, 1, rows) == 4
    assert save_utterances(session, 1, rows) == 4

    stored = session.scalars(select(Utterance).where(Utterance.recording_id == 1)).all()
    assert len(stored) == 4


def test_transcription_uses_the_cache_and_never_calls_deepgram_twice(
    session, tmp_path, monkeypatch
):
    from app.config import Settings

    settings = Settings(_env_file=None, cache_dir=tmp_path / "cache", deepgram_api_key="unused")
    monkeypatch.setattr(transcribe, "get_settings", lambda: settings)

    audio = tmp_path / "call.wav"
    audio.write_bytes(b"RIFF fake wav")
    cached = transcribe.cache_path("sha-demo")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(DEMO), encoding="utf-8")

    def explode(*args, **kwargs):
        raise AssertionError("Deepgram was called despite a warm cache")

    monkeypatch.setattr(transcribe.httpx, "post", explode)

    session.add(seed_lead())
    session.add(Recording(id=1, lead_id="L-1", sha256="sha-demo", path=str(audio)))
    session.commit()

    count = transcribe_recording(session, 1)

    assert count == 4
    assert session.get(Recording, 1).state == RecordingState.TRANSCRIBED


def test_missing_audio_marks_the_recording_failed(session, tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(
        transcribe, "get_settings", lambda: Settings(_env_file=None, cache_dir=tmp_path / "c")
    )
    session.add(seed_lead())
    session.add(Recording(id=1, lead_id="L-1", sha256="s", path=str(tmp_path / "gone.wav")))
    session.commit()

    with pytest.raises(TranscriptionError):
        transcribe_recording(session, 1)

    assert session.get(Recording, 1).state == RecordingState.FAILED


def test_a_missing_api_key_is_an_error_not_a_silent_pass(session, tmp_path, monkeypatch):
    """Transcription failure must be visible, never an empty transcript that scores clean."""
    from app.config import Settings

    settings = Settings(_env_file=None, cache_dir=tmp_path / "cache", deepgram_api_key="")
    monkeypatch.setattr(transcribe, "get_settings", lambda: settings)

    audio = tmp_path / "call.wav"
    audio.write_bytes(b"RIFF fake wav")
    session.add(seed_lead())
    session.add(Recording(id=1, lead_id="L-1", sha256="nocache", path=str(audio)))
    session.commit()

    with pytest.raises(TranscriptionError):
        transcribe_recording(session, 1)

    assert session.get(Recording, 1).state == RecordingState.FAILED


def test_gaps_between_utterances_are_measured():
    """The dead-air fixture is a gap between utterances, not a quiet dB reading."""
    rows = [
        {"start_s": 0.0, "end_s": 10.0},
        {"start_s": 35.0, "end_s": 40.0},
        {"start_s": 41.0, "end_s": 45.0},
    ]

    gaps = utterance_gaps(rows)

    assert gaps[0] == (10.0, 25.0)
    assert gaps[1] == (40.0, 1.0)
