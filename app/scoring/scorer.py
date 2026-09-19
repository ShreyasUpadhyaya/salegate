"""Persist a score: run the gate, write Score and CheckResult rows.

The gate itself (app/scoring/gate.py) is pure and DB-free, per CLAUDE.md.
This module is the one place that turns its plain-data result into rows,
and the one place that reads utterances back out of the DB into the
TurnDict shape the evaluators expect.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.models import TurnDict
from app.models import CheckResult, Lead, Recording, Score, Utterance
from app.scoring.gate import score_and_gate


class ScoringError(RuntimeError):
    """The lead or its recording is not in a state that can be scored."""


def _turns_for_recording(session: Session, recording_id: int) -> list[TurnDict]:
    rows = session.scalars(
        select(Utterance).where(Utterance.recording_id == recording_id).order_by(Utterance.idx)
    ).all()
    return [
        {
            "idx": r.idx,
            "speaker": r.speaker,
            "start_s": r.start_s,
            "end_s": r.end_s,
            "text_redacted": r.text_redacted,
            "avg_confidence": r.avg_confidence,
            "speaker_source": r.speaker_source,
        }
        for r in rows
    ]


def _lead_payload(lead: Lead) -> dict:
    """CRM fields plus a rate card, in the shape evaluators expect.

    crm_fields on the Lead row carries both the customer's own fields and a
    nested "rate_card" key, matching the tracked fixture JSON under
    app/checks/library/lead_*.json (see DECISIONS D19, D22).
    """
    fields = dict(lead.crm_fields or {})
    rate_card = fields.pop("rate_card", {})
    return {"lead_id": lead.lead_id, "crm_fields": fields, "rate_card": rate_card}


def score_lead(session: Session, lead_id: str) -> Score:
    """Score the lead's most recent recording and persist the result.

    Raises ScoringError if the lead is unknown or has no recording yet, so the
    caller (the submit endpoint) can turn that into a 409, never a silent
    partial score.
    """
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise ScoringError(f"unknown lead {lead_id}")

    recording = session.scalars(
        select(Recording)
        .where(Recording.lead_id == lead_id)
        .order_by(Recording.id.desc())
    ).first()
    if recording is None:
        raise ScoringError(f"lead {lead_id} has no recording")

    turns = _turns_for_recording(session, recording.id)
    if not turns:
        raise ScoringError(f"recording {recording.id} has no transcript yet")

    outcome = score_and_gate(
        lead.call_started_at, lead.retailer, turns, _lead_payload(lead)
    )

    score = Score(
        lead_id=lead.lead_id,
        recording_id=recording.id,
        library_snapshot_hash=outcome["snapshot_hash"],
        decision=outcome["gate"]["decision"],
        sampled_for_qa=outcome["gate"]["sampled_for_qa"],
        score_with_fatal=0.0,
        score_without_fatal=0.0,
    )
    session.add(score)
    session.flush()  # assigns score.id for the CheckResult rows below

    for result in outcome["results"]:
        session.add(
            CheckResult(
                score_id=score.id,
                check_id=result["check_id"],
                check_version=result["check_version"],
                status=result["status"],
                confidence=result["confidence"],
                method=result["method"],
                reason=result["reason"],
                evidence=result["evidence"],
            )
        )

    session.commit()
    return score


def latest_score(session: Session, lead_id: str) -> Score | None:
    return session.scalars(
        select(Score).where(Score.lead_id == lead_id).order_by(Score.id.desc())
    ).first()
