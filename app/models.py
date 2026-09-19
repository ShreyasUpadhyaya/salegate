"""SQLAlchemy models. The schema in PLAN.md, one class per table.

Nothing here stores card digits or unredacted customer speech: utterance text is
stored redacted, and overrides are append-only by contract (see DECISIONS D7, D8).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RecordingState:
    RECEIVED = "RECEIVED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    SCORED = "SCORED"
    FAILED = "FAILED"


class Decision:
    AUTO_SUBMIT = "AUTO_SUBMIT"
    HELD_TL = "HELD_TL"
    QA_REVIEW = "QA_REVIEW"


class CheckStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOTE = "NOTE"
    NA = "NA"


class Lead(Base):
    __tablename__ = "leads"

    lead_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    retailer: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    tl_id: Mapped[str | None] = mapped_column(String(64), default=None)
    site: Mapped[str | None] = mapped_column(String(128), default=None)
    campaign: Mapped[str | None] = mapped_column(String(128), default=None)
    call_started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    crm_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    plan_code: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(String(32), default="NEW")

    recordings: Mapped[list[Recording]] = relationship(back_populates="lead")
    scores: Mapped[list[Score]] = relationship(back_populates="lead")


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        UniqueConstraint("lead_id", "sha256", name="uq_recordings_lead_sha"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.lead_id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(String(512))
    channels: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_s: Mapped[float | None] = mapped_column(Float, default=None)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    state: Mapped[str] = mapped_column(String(32), default=RecordingState.RECEIVED)

    lead: Mapped[Lead] = relationship(back_populates="recordings")
    utterances: Mapped[list[Utterance]] = relationship(back_populates="recording")


class Utterance(Base):
    __tablename__ = "utterances"
    __table_args__ = (
        Index("ix_utterances_recording_idx", "recording_id", "idx", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))  # agent | customer | unknown
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    text_redacted: Mapped[str] = mapped_column(String)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    recording: Mapped[Recording] = relationship(back_populates="utterances")
    words: Mapped[list[Word]] = relationship(back_populates="utterance")


class Word(Base):
    """Optional detail. Utterances alone satisfy the evidence contract."""

    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    utterance_id: Mapped[int] = mapped_column(ForeignKey("utterances.id"), index=True)
    word: Mapped[str] = mapped_column(String(128))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    utterance: Mapped[Utterance] = relationship(back_populates="words")


class CheckLibrary(Base):
    """One row per check version. The scorer resolves by call date, not today."""

    __tablename__ = "check_library"
    __table_args__ = (
        UniqueConstraint("check_id", "version", name="uq_check_library_id_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    retailer: Mapped[str] = mapped_column(String(128), index=True)
    type: Mapped[str] = mapped_column(String(1))  # A | B | C
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    fatal: Mapped[bool] = mapped_column(Boolean, default=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    effective_from: Mapped[datetime] = mapped_column(DateTime, index=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    content_hash: Mapped[str] = mapped_column(String(64))


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.lead_id"), index=True)
    recording_id: Mapped[int | None] = mapped_column(
        ForeignKey("recordings.id"), default=None
    )
    library_snapshot_hash: Mapped[str] = mapped_column(String(64))
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    sampled_for_qa: Mapped[bool] = mapped_column(Boolean, default=False)
    score_with_fatal: Mapped[float] = mapped_column(Float, default=0.0)
    score_without_fatal: Mapped[float] = mapped_column(Float, default=0.0)

    lead: Mapped[Lead] = relationship(back_populates="scores")
    check_results: Mapped[list[CheckResult]] = relationship(back_populates="score")


class CheckResult(Base):
    """Evidence is a JSON list of {utterance_id, speaker, start_s, end_s, text_redacted}.

    A PASS with empty evidence is a bug, enforced by tests once evaluators land.
    """

    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("scores.id"), index=True)
    check_id: Mapped[str] = mapped_column(String(64), index=True)
    check_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(16))  # fuzzy|regex|extract|timing|llm
    reason: Mapped[str] = mapped_column(String)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    score: Mapped[Score] = relationship(back_populates="check_results")
    overrides: Mapped[list[Override]] = relationship(back_populates="check_result")


class Override(Base):
    """Append-only. Never updated, never deleted. See DECISIONS D8."""

    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_result_id: Mapped[int] = mapped_column(
        ForeignKey("check_results.id"), index=True
    )
    auditor: Mapped[str] = mapped_column(String(64))
    old_status: Mapped[str] = mapped_column(String(16))
    new_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    check_result: Mapped[CheckResult] = relationship(back_populates="overrides")
