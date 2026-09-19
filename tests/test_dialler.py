"""Phase 2: recordings arrive by API, land against the lead, and never double up."""

from __future__ import annotations

import struct
import wave
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_session
from app.main import app
from app.models import Lead, Recording, RecordingState

LEAD_ID = "L-TEST-2001"
CALL_STARTED = datetime(2026, 9, 19, 10, 5, tzinfo=UTC).isoformat()


def make_wav(path, seconds: float = 0.25, channels: int = 1) -> bytes:
    """A real single channel wav, so the channel and duration read is exercised."""
    rate = 8000
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack("<h", 0) * frames * channels)
    return path.read_bytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App wired to a temp SQLite file and a temp audio dir, with one seeded lead."""
    from app.config import Settings, get_settings
    from app.ingest import dialler

    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "app.db",
        audio_dir=tmp_path / "recordings",
        cache_dir=tmp_path / "cache",
    )
    settings.ensure_dirs()
    monkeypatch.setattr(dialler, "get_settings", lambda: settings)

    engine = create_engine(
        f"sqlite+pysqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as seed:
        seed.add(
            Lead(
                lead_id=LEAD_ID,
                retailer="Retailer 1",
                agent_id="",
                call_started_at=datetime(2026, 9, 19, tzinfo=UTC).replace(tzinfo=None),
                crm_fields={},
            )
        )
        seed.commit()

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    # The real lifespan would build tables in the project DB, so skip it here.
    test_client = TestClient(app)
    test_client.session_factory = session_factory
    test_client.settings = settings
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def post_audio(client, payload: bytes, *, lead_id: str = LEAD_ID, filename: str = "call.wav"):
    return client.post(
        "/api/dialler/recordings",
        data={"lead_id": lead_id, "call_started_at": CALL_STARTED, "agent_id": "A-007"},
        files={"audio": (filename, payload, "audio/wav")},
    )


def test_recording_is_accepted_and_stored_against_the_lead(client, tmp_path):
    payload = make_wav(tmp_path / "call.wav")

    response = post_audio(client, payload)

    assert response.status_code == 202
    body = response.json()
    assert body["lead_id"] == LEAD_ID
    assert body["duplicate"] is False
    assert body["state"] == RecordingState.RECEIVED
    assert body["channels"] == 1
    assert body["duration_s"] == pytest.approx(0.25)

    with client.session_factory() as session:
        rows = session.scalars(select(Recording)).all()
    assert len(rows) == 1
    assert rows[0].sha256 == body["sha256"]
    stored = client.settings.audio_dir / LEAD_ID / f"{body['sha256']}.wav"
    assert stored.read_bytes() == payload


def test_the_same_audio_posted_twice_makes_one_recording(client, tmp_path):
    payload = make_wav(tmp_path / "call.wav")

    first = post_audio(client, payload)
    second = post_audio(client, payload)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["recording_id"] == first.json()["recording_id"]

    with client.session_factory() as session:
        assert len(session.scalars(select(Recording)).all()) == 1


def test_different_audio_for_the_same_lead_is_a_second_recording(client, tmp_path):
    first = post_audio(client, make_wav(tmp_path / "one.wav", seconds=0.25))
    second = post_audio(client, make_wav(tmp_path / "two.wav", seconds=0.5))

    assert second.status_code == 202
    assert second.json()["duplicate"] is False
    assert second.json()["recording_id"] != first.json()["recording_id"]

    with client.session_factory() as session:
        assert len(session.scalars(select(Recording)).all()) == 2


def test_an_unknown_lead_is_refused(client, tmp_path):
    response = post_audio(client, make_wav(tmp_path / "call.wav"), lead_id="L-NOPE")

    assert response.status_code == 404
    with client.session_factory() as session:
        assert session.scalars(select(Recording)).all() == []


def test_a_non_audio_upload_is_refused(client):
    response = post_audio(client, b"not audio at all", filename="notes.txt")

    assert response.status_code == 415
    with client.session_factory() as session:
        assert session.scalars(select(Recording)).all() == []


def test_an_empty_upload_is_refused(client):
    response = post_audio(client, b"")

    assert response.status_code == 400


def test_the_response_never_leaks_the_storage_path(client, tmp_path):
    body = post_audio(client, make_wav(tmp_path / "call.wav")).json()

    assert "path" not in body
    assert str(client.settings.audio_dir) not in str(body)
