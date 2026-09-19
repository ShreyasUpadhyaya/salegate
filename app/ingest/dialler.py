"""Dialler ingestion. Accepts a call recording and stores it against a lead.

Idempotent on (lead_id, sha256). The same audio posted twice returns the first
recording row and never writes a second copy to disk. Transcription happens in a
later phase, so the row lands in RECEIVED and stops there.
"""

from __future__ import annotations

import hashlib
import wave
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Lead, Recording, RecordingState

# Read the upload in chunks so a long call never sits in memory whole.
CHUNK_BYTES = 1024 * 1024

ALLOWED_SUFFIXES = {".wav", ".mp3", ".m4a"}


class RecordingAccepted(BaseModel):
    """What the dialler gets back. No filesystem path is exposed."""

    recording_id: int
    lead_id: str
    sha256: str
    state: str
    duplicate: bool = Field(
        description="True when this audio was already stored for this lead."
    )
    channels: int | None = None
    duration_s: float | None = None


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    """Hash a file without reading it all at once. Used by the simulator."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def storage_path(lead_id: str, sha256: str, suffix: str) -> Path:
    """data/recordings/<lead_id>/<sha>.wav. Gitignored, see CLAUDE.md rule 2."""
    return get_settings().audio_dir / lead_id / f"{sha256}{suffix}"


def wav_properties(path: Path) -> tuple[int | None, float | None]:
    """Channels and duration for a wav. Anything else returns unknowns.

    ffprobe is not a dependency, and the demo recording is a wav (D17), so the
    stdlib reader covers the real path and other formats degrade quietly.
    """
    if path.suffix.lower() != ".wav":
        return None, None
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            channels = handle.getnchannels()
    except (wave.Error, OSError):
        return None, None
    duration = round(frames / rate, 3) if rate else None
    return channels, duration


def store_recording(
    session: Session,
    *,
    lead_id: str,
    audio: bytes,
    filename: str,
    call_started_at: datetime | None = None,
    agent_id: str | None = None,
) -> RecordingAccepted:
    """Store audio against a lead, once. Returns the existing row on a repost.

    The caller has already checked that the lead exists. Nothing here edits CRM
    fields on the lead beyond the agent id when the dialler supplies one and the
    lead has none, which keeps CLAUDE.md rule 5 intact.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported audio type {suffix or '(none)'}")

    digest = sha256_of(audio)
    existing = session.scalars(
        select(Recording).where(
            Recording.lead_id == lead_id, Recording.sha256 == digest
        )
    ).first()
    if existing is not None:
        return RecordingAccepted(
            recording_id=existing.id,
            lead_id=existing.lead_id,
            sha256=existing.sha256,
            state=existing.state,
            duplicate=True,
            channels=existing.channels,
            duration_s=existing.duration_s,
        )

    path = storage_path(lead_id, digest, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(audio)

    channels, duration_s = wav_properties(path)
    recording = Recording(
        lead_id=lead_id,
        sha256=digest,
        path=str(path),
        channels=channels,
        duration_s=duration_s,
        state=RecordingState.RECEIVED,
    )
    session.add(recording)

    lead = session.get(Lead, lead_id)
    if lead is not None:
        if call_started_at is not None:
            lead.call_started_at = call_started_at
        if agent_id and not lead.agent_id:
            lead.agent_id = agent_id
    session.commit()

    return RecordingAccepted(
        recording_id=recording.id,
        lead_id=recording.lead_id,
        sha256=recording.sha256,
        state=recording.state,
        duplicate=False,
        channels=recording.channels,
        duration_s=recording.duration_s,
    )
