"""Deepgram pre-recorded transcription. The only module that talks to Deepgram.

One REST call per recording, cached on disk by audio sha256 so a rerun costs
nothing (CLAUDE.md: never call an external service in a loop without cache).
Diarization is the primary speaker path because our recording is single channel
(DECISIONS D17), and redact=pci masks card digits at source (hard rule 4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Recording, RecordingState, Utterance

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"

# Long calls plus a cold connection. The demo file is 4.5 minutes.
REQUEST_TIMEOUT_S = 300.0

CONTENT_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}

# Domain words nova-3 would otherwise mangle. Cheap accuracy on the exact terms
# the Type B extractors compare against.
KEYTERMS = (
    "NBN",
    "Econnex",
    "Netcomm",
    "Wi-Fi 6",
    "fibre to the premises",
    "iPrimus",
    "megabits",
    "direct debit",
)

SPEAKER_AGENT = "agent"
SPEAKER_CUSTOMER = "customer"
SPEAKER_UNKNOWN = "unknown"

# The disclaimer is the agent's line, and it comes early. Whoever says the most
# of it is the agent. See identify_agent_speaker.
_DISCLAIMER_MARKERS = (
    "recorded for quality",
    "quality assurance",
    "this call is being recorded",
    "please be advised",
)


class TranscriptionError(RuntimeError):
    """Deepgram was unreachable or answered with something unusable."""


def cache_path(sha256: str) -> Path:
    return get_settings().cache_dir / "deepgram" / f"{sha256}.json"


def build_params() -> dict[str, Any]:
    """Query parameters for the pre-recorded endpoint.

    diarize is on and multichannel is off on purpose: one microphone, one track
    (D17). smart_format gives punctuation and sensible number formatting, which
    the Type B extractors read.
    """
    settings = get_settings()
    return {
        "model": settings.deepgram_model,
        "language": settings.deepgram_language,
        "diarize": "true",
        "utterances": "true",
        "punctuate": "true",
        "smart_format": "true",
        "redact": "pci",
        "keyterm": list(KEYTERMS),
    }


def fetch_transcript(audio_path: Path, sha256: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Return Deepgram's raw response, from disk when we have seen this audio.

    The cache key is the audio hash, so the same call never bills twice and a
    rerun is offline. The API key is read through config and never logged.
    """
    cached = cache_path(sha256)
    if use_cache and cached.is_file():
        return json.loads(cached.read_text(encoding="utf-8"))

    settings = get_settings()
    if not settings.deepgram_api_key:
        raise TranscriptionError("no Deepgram API key configured")

    content_type = CONTENT_TYPES.get(audio_path.suffix.lower(), "application/octet-stream")
    try:
        response = httpx.post(
            DEEPGRAM_URL,
            params=build_params(),
            headers={
                "Authorization": f"Token {settings.deepgram_api_key}",
                "Content-Type": content_type,
            },
            content=audio_path.read_bytes(),
            timeout=REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Deepgram request failed: {type(exc).__name__}") from exc

    if response.status_code != 200:
        # The body can echo request detail, so only the status is surfaced.
        raise TranscriptionError(f"Deepgram returned {response.status_code}")

    payload = response.json()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def identify_agent_speaker(utterances: list[dict[str, Any]]) -> int | None:
    """Which diarized speaker label is the agent.

    The recording disclaimer is the agent's line and arrives in the first turns,
    so the speaker who says it is the agent. Falls back to the speaker who talks
    first, which in an outbound call is the agent opening the call.
    """
    for utterance in utterances:
        text = (utterance.get("transcript") or "").lower()
        if any(marker in text for marker in _DISCLAIMER_MARKERS):
            speaker = utterance.get("speaker")
            return int(speaker) if speaker is not None else None
    for utterance in utterances:
        speaker = utterance.get("speaker")
        if speaker is not None:
            return int(speaker)
    return None


def parse_utterances(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Deepgram utterances into the rows we store.

    Returns dicts, not ORM objects, so this stays pure and testable.
    """
    raw = payload.get("results", {}).get("utterances") or []
    agent_speaker = identify_agent_speaker(raw)

    rows: list[dict[str, Any]] = []
    for idx, utterance in enumerate(raw):
        speaker_label = utterance.get("speaker")
        if speaker_label is None:
            speaker = SPEAKER_UNKNOWN
        elif agent_speaker is None:
            speaker = SPEAKER_UNKNOWN
        elif int(speaker_label) == agent_speaker:
            speaker = SPEAKER_AGENT
        else:
            speaker = SPEAKER_CUSTOMER

        rows.append(
            {
                "idx": idx,
                "speaker": speaker,
                "start_s": float(utterance.get("start", 0.0)),
                "end_s": float(utterance.get("end", 0.0)),
                "text_redacted": (utterance.get("transcript") or "").strip(),
                "avg_confidence": float(utterance.get("confidence", 0.0)),
            }
        )
    return rows


def save_utterances(session: Session, recording_id: int, rows: list[dict[str, Any]]) -> int:
    """Replace this recording's utterances. Rerunning transcription is safe."""
    session.execute(delete(Utterance).where(Utterance.recording_id == recording_id))
    session.add_all(
        [Utterance(recording_id=recording_id, **row) for row in rows]
    )
    session.commit()
    return len(rows)


def transcribe_recording(
    session: Session, recording_id: int, *, use_cache: bool = True
) -> int:
    """Transcribe one stored recording and save its utterances.

    Moves the row through TRANSCRIBING to TRANSCRIBED, or FAILED if Deepgram
    could not be used. Returns the number of utterances saved.
    """
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise TranscriptionError(f"no recording {recording_id}")

    audio_path = Path(recording.path)
    if not audio_path.is_file():
        recording.state = RecordingState.FAILED
        session.commit()
        raise TranscriptionError(f"audio missing for recording {recording_id}")

    recording.state = RecordingState.TRANSCRIBING
    session.commit()

    try:
        payload = fetch_transcript(audio_path, recording.sha256, use_cache=use_cache)
        rows = parse_utterances(payload)
    except TranscriptionError:
        recording.state = RecordingState.FAILED
        session.commit()
        raise

    count = save_utterances(session, recording_id, rows)

    duration = payload.get("metadata", {}).get("duration")
    if duration is not None and not recording.duration_s:
        recording.duration_s = float(duration)
    recording.state = RecordingState.TRANSCRIBED
    session.commit()
    return count


def transcribe_in_background(recording_id: int) -> None:
    """Background task entry point. Owns its own session and never raises.

    A failure leaves the recording in FAILED for the UI to show, rather than
    taking down the worker.
    """
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        transcribe_recording(session, recording_id)
    except TranscriptionError:
        pass
    finally:
        session.close()


def utterance_gaps(rows: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """(gap_start, gap_seconds) between consecutive utterances.

    Type C dead air reads this in Phase 8. Kept here because it is a property of
    the transcript, not of any one check.
    """
    gaps: list[tuple[float, float]] = []
    for previous, current in zip(rows, rows[1:], strict=False):
        gap = current["start_s"] - previous["end_s"]
        if gap > 0:
            gaps.append((previous["end_s"], round(gap, 3)))
    return gaps
