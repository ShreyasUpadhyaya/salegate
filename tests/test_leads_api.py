"""Phase 9: score, gate, submit and override endpoints.

Submit's 409 cases are the "no sale ships unscored" proof from PLAN.md.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.checks.library import LIBRARY_DIR, load_all
from app.db import Base, get_session
from app.main import app
from app.models import Lead, Recording, RecordingState, Utterance

RETAILER = LIBRARY_DIR and load_all()[0].retailer  # "PROVIDER_A", from the real library
CALL_DATE = datetime(2026, 9, 19, 10, 5)

CLEAN_TURNS = [
    (0, "agent", 0.0, 3.0, "Please be advised that this call will be recorded for quality assurance and training purposes.", 0.95),
    (1, "customer", 3.5, 4.5, "Yeah, that's fine.", 0.95),
    (2, "agent", 5.0, 8.0, "And this will be under your name, am I correct?", 0.95),
    (3, "customer", 8.5, 9.5, "Yes, that's correct.", 0.95),
    (4, "agent", 10.0, 40.0, (
        "This value plan comes with a month to month contract only and provides twenty five Mbps "
        "typical download speed and eight point five Mbps typical upload speed from seven PM to "
        "eleven PM. The original plan cost is seventy two dollars and ninety per month, but we have "
        "an offer ongoing where you will get this plan at forty two dollars and ninety per month for "
        "the first six months and then seventy two dollars and ninety. The modem that you will "
        "receive is the Netcomm CF40 Wi-Fi six modem, it is one hundred percent free, no extra cost."
    ), 0.95),
    (5, "agent", 41.0, 43.0, "And the total minimum cost will be forty two dollars and ninety only, no setup fee, no any additional cost.", 0.95),
    (6, "agent", 44.0, 45.0, "Can you please verify your first and last name as per ID?", 0.95),
    (7, "customer", 45.5, 46.5, "Jordan Avery.", 0.95),
    (8, "agent", 47.0, 48.0, "And your email address?", 0.95),
    (9, "customer", 48.5, 50.0, "jordan.avery@example.com", 0.95),
    (10, "agent", 51.0, 55.0, "And do you understand and agree to switch your internet service to this plan on these terms?", 0.95),
    (11, "customer", 55.5, 56.5, "Yes, I agree.", 0.95),
    (12, "agent", 57.0, 60.0, "This is Sam from Econnex Comparison, it was a pleasure to help you today.", 0.95),
]

LEAD_ID = "L-API-CLEAN"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Fresh DB per test, wired to a lead with a transcribed recording."""
    from app.config import Settings

    settings = Settings(_env_file=None, db_path=tmp_path / "app.db", cache_dir=tmp_path / "cache")
    settings.ensure_dirs()

    engine = create_engine(
        f"sqlite+pysqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as seed:
        seed.add(
            Lead(
                lead_id=LEAD_ID,
                retailer=RETAILER,
                agent_id="A-007",
                call_started_at=CALL_DATE,
                crm_fields={
                    "email": "jordan.avery@example.com",
                    "dob": "1990-03-14",
                    "service_address": "12 Sample Street, Testville NSW 2000",
                    "rate_card": {
                        "promo_price_monthly": 42.90,
                        "ongoing_price_monthly": 72.90,
                        "promo_term_months": 6,
                        "download_speed_mbps": 25,
                        "modem_model": "Netcomm CF40",
                    },
                },
            )
        )
        recording = Recording(
            lead_id=LEAD_ID, sha256="a" * 64, path="x.wav", state=RecordingState.TRANSCRIBED
        )
        seed.add(recording)
        seed.commit()
        seed.refresh(recording)

        for idx, speaker, start, end, text, conf in CLEAN_TURNS:
            seed.add(
                Utterance(
                    recording_id=recording.id,
                    idx=idx,
                    speaker=speaker,
                    start_s=start,
                    end_s=end,
                    text_redacted=text,
                    avg_confidence=conf,
                    speaker_source="diarization",
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
    test_client = TestClient(app)
    test_client.session_factory = session_factory
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_submit_before_scoring_is_refused(client):
    response = client.post(f"/api/leads/{LEAD_ID}/submit")

    assert response.status_code == 409


def test_score_returns_every_check_with_evidence(client):
    response = client.post(f"/api/leads/{LEAD_ID}/score")

    assert response.status_code == 201
    body = response.json()
    assert body["lead_id"] == LEAD_ID
    assert body["results"]
    for result in body["results"]:
        assert result["check_id"]
        assert result["status"] in ("PASS", "FAIL", "REVIEW", "NOTE", "NA")
        if result["status"] == "PASS":
            assert result["evidence"], f"{result['check_id']} PASSed with no evidence"


def test_get_score_after_scoring_matches_what_was_posted(client):
    posted = client.post(f"/api/leads/{LEAD_ID}/score").json()

    fetched = client.get(f"/api/leads/{LEAD_ID}/score").json()

    assert fetched["score_id"] == posted["score_id"]
    assert fetched["decision"] == posted["decision"]


def test_get_score_before_scoring_is_404(client):
    response = client.get(f"/api/leads/{LEAD_ID}/score")

    assert response.status_code == 404


def test_get_gate_names_the_critical_checks_involved(client):
    client.post(f"/api/leads/{LEAD_ID}/score")

    response = client.get(f"/api/leads/{LEAD_ID}/gate")

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in ("AUTO_SUBMIT", "QA_REVIEW", "HELD_TL")
    if body["decision"] == "HELD_TL":
        assert body["critical_fails"]


def test_submit_succeeds_only_when_the_gate_cleared_it(client):
    scored = client.post(f"/api/leads/{LEAD_ID}/score").json()

    response = client.post(f"/api/leads/{LEAD_ID}/submit")

    if scored["decision"] == "AUTO_SUBMIT":
        assert response.status_code == 200
        assert response.json()["status"] == "SUBMITTED"
    else:
        assert response.status_code == 409


def test_submit_is_refused_for_an_unknown_lead(client):
    response = client.post("/api/leads/L-NOPE/submit")

    assert response.status_code == 404


def test_score_is_refused_for_a_lead_with_no_recording(client):
    with client.session_factory() as session:
        session.add(
            Lead(
                lead_id="L-NO-RECORDING",
                retailer=RETAILER,
                agent_id="A-001",
                call_started_at=CALL_DATE,
                crm_fields={},
            )
        )
        session.commit()

    response = client.post("/api/leads/L-NO-RECORDING/score")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# overrides: append-only
# ---------------------------------------------------------------------------


def test_an_override_is_recorded_and_becomes_the_effective_status(client):
    scored = client.post(f"/api/leads/{LEAD_ID}/score").json()
    check_result_id = scored["results"][0]["check_result_id"]
    old_status = scored["results"][0]["status"]
    new_status = "REVIEW" if old_status != "REVIEW" else "PASS"

    response = client.post(
        f"/api/check-results/{check_result_id}/override",
        json={"auditor": "qa1", "new_status": new_status, "reason": "manual review"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["old_status"] == old_status
    assert body["new_status"] == new_status

    fetched = client.get(f"/api/leads/{LEAD_ID}/score").json()
    updated = next(r for r in fetched["results"] if r["check_result_id"] == check_result_id)
    assert updated["effective_status"] == new_status
    assert updated["status"] == old_status  # the model's own status never changes


def test_overrides_are_never_updated_only_appended(client):
    scored = client.post(f"/api/leads/{LEAD_ID}/score").json()
    check_result_id = scored["results"][0]["check_result_id"]

    client.post(
        f"/api/check-results/{check_result_id}/override",
        json={"auditor": "qa1", "new_status": "REVIEW", "reason": "first pass"},
    )
    client.post(
        f"/api/check-results/{check_result_id}/override",
        json={"auditor": "qa2", "new_status": "PASS", "reason": "second pass, disagree"},
    )

    history = client.get(f"/api/check-results/{check_result_id}/overrides").json()

    assert len(history) == 2
    assert history[0]["auditor"] == "qa1"
    assert history[1]["auditor"] == "qa2"
    assert history[1]["old_status"] == "REVIEW"  # chained off the first override


def test_an_override_on_an_unknown_check_result_is_404(client):
    response = client.post(
        "/api/check-results/999999/override",
        json={"auditor": "qa1", "new_status": "PASS", "reason": "x"},
    )

    assert response.status_code == 404


def test_an_invalid_status_is_rejected(client):
    scored = client.post(f"/api/leads/{LEAD_ID}/score").json()
    check_result_id = scored["results"][0]["check_result_id"]

    response = client.post(
        f"/api/check-results/{check_result_id}/override",
        json={"auditor": "qa1", "new_status": "MAYBE", "reason": "x"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# dashboards
# ---------------------------------------------------------------------------


def test_agent_rollup_counts_the_scored_lead(client):
    client.post(f"/api/leads/{LEAD_ID}/score")

    response = client.get("/api/dashboards/agents")

    assert response.status_code == 200
    rows = response.json()
    row = next(r for r in rows if r["agent_id"] == "A-007")
    assert row["total_scored"] == 1
    assert row["auto_submit"] + row["qa_review"] + row["held_tl"] == 1


def test_agent_rollup_is_empty_with_no_scores(client):
    response = client.get("/api/dashboards/agents")

    assert response.status_code == 200
    assert response.json() == []


def test_rescoring_the_same_lead_only_counts_once_in_the_rollup(client):
    client.post(f"/api/leads/{LEAD_ID}/score")
    client.post(f"/api/leads/{LEAD_ID}/score")

    rows = client.get("/api/dashboards/agents").json()

    row = next(r for r in rows if r["agent_id"] == "A-007")
    assert row["total_scored"] == 1


def test_transcript_returns_the_utterances(client):
    response = client.get(f"/api/leads/{LEAD_ID}/transcript")

    assert response.status_code == 200
    body = response.json()
    assert body["lead_id"] == LEAD_ID
    assert len(body["utterances"]) == len(CLEAN_TURNS)
    assert body["utterances"][0]["text_redacted"] == CLEAN_TURNS[0][4]


def test_transcript_404s_for_a_lead_with_no_recording(client):
    with client.session_factory() as session:
        session.add(
            Lead(
                lead_id="L-NO-REC-2",
                retailer=RETAILER,
                agent_id="A-001",
                call_started_at=CALL_DATE,
                crm_fields={},
            )
        )
        session.commit()

    response = client.get("/api/leads/L-NO-REC-2/transcript")

    assert response.status_code == 404
