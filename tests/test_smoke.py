"""Phase 1 smoke tests: the app answers, the schema builds, no secrets leak out."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import Base
from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_never_returns_secrets() -> None:
    with TestClient(app) as client:
        body = client.get("/health").text.lower()
    assert "api_key" not in body
    assert "deepgram" not in body
    assert "gemini" not in body


def test_every_planned_table_is_mapped() -> None:
    import app.models  # noqa: F401  (registers the mappers)

    expected = {
        "leads",
        "recordings",
        "utterances",
        "words",
        "check_library",
        "scores",
        "check_results",
        "overrides",
    }
    assert expected <= set(Base.metadata.tables)


def test_settings_defaults_do_not_enable_the_llm() -> None:
    """Deterministic first: the LLM is opt in through .env (DECISIONS D4)."""
    settings = Settings(_env_file=None)
    assert settings.llm_enabled is False
    assert settings.qa_sample_percent == 5


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()
