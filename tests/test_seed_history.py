"""Phase 11: seed_history.py produces a labelled, reproducible demo dataset."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Lead, Score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.db as db_module
    import scripts.seed_history as seed_history
    from app.config import Settings

    settings = Settings(_env_file=None, db_path=tmp_path / "app.db")
    settings.ensure_dirs()
    engine = create_engine(
        f"sqlite+pysqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(db_module, "SessionLocal", factory)
    monkeypatch.setattr(seed_history, "SessionLocal", factory)
    monkeypatch.setattr(seed_history, "DAYS_BACK", 3)
    monkeypatch.setattr(seed_history, "CALLS_PER_DAY", 2)

    yield factory


def test_every_seeded_lead_is_labelled(db):
    from scripts.seed_history import seed

    assert seed() == 0

    with db() as session:
        leads = session.scalars(select(Lead)).all()

    assert leads
    assert all(lead.lead_id.startswith("SEED-") for lead in leads)
    assert all(lead.status == "SEEDED" for lead in leads)


def test_every_seeded_lead_has_a_score_and_gate_decision(db):
    from scripts.seed_history import seed

    seed()

    with db() as session:
        leads = session.scalars(select(Lead)).all()
        scores = session.scalars(select(Score)).all()

    assert len(scores) == len(leads)
    assert all(s.decision in ("AUTO_SUBMIT", "QA_REVIEW", "HELD_TL") for s in scores)


def test_seeding_is_reproducible(db):
    from scripts.seed_history import seed

    seed()
    with db() as session:
        first_decisions = sorted(s.decision for s in session.scalars(select(Score)).all())

    with db() as session:
        session.query(Score).delete()
        session.query(Lead).delete()
        session.commit()

    seed()
    with db() as session:
        second_decisions = sorted(s.decision for s in session.scalars(select(Score)).all())

    assert first_decisions == second_decisions


def test_the_gate_decisions_are_not_all_the_same(db):
    """A useful demo needs a real mix, not every call landing the same way."""
    from scripts.seed_history import seed

    seed()
    with db() as session:
        decisions = {s.decision for s in session.scalars(select(Score)).all()}

    assert len(decisions) >= 2
