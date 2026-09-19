"""Score, gate and submit endpoints for one lead.

The submit endpoint is the "no sale ships unscored" proof from PLAN.md: it
refuses with 409 if there is no score yet, or if the gate held the sale.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.checks.library import load_all
from app.db import get_session
from app.models import CheckResult, Lead, Score
from app.scoring.gate import DECISION_AUTO_SUBMIT
from app.scoring.scorer import ScoringError, latest_score, score_lead

router = APIRouter(prefix="/api/leads", tags=["leads"])


class EvidenceItem(BaseModel):
    utterance_id: int | None = None
    speaker: str | None = None
    start_s: float | None = None
    end_s: float | None = None
    text_redacted: str = ""


class CheckResultOut(BaseModel):
    check_id: str
    check_version: int
    status: str
    confidence: float
    method: str
    reason: str
    evidence: list[EvidenceItem]
    effective_status: str
    check_result_id: int


class ScoreOut(BaseModel):
    lead_id: str
    score_id: int
    decision: str
    sampled_for_qa: bool
    library_snapshot_hash: str
    scored_at: str
    results: list[CheckResultOut]


class GateOut(BaseModel):
    lead_id: str
    decision: str
    sampled_for_qa: bool
    critical_fails: list[str]
    critical_reviews: list[str]


class SubmitOut(BaseModel):
    lead_id: str
    status: str
    decision: str


def _effective_status(session: Session, check_result: CheckResult) -> str:
    """Latest override wins, else the model's own status (D8)."""
    if not check_result.overrides:
        return check_result.status
    latest = max(check_result.overrides, key=lambda o: o.created_at)
    return latest.new_status


def _require_lead(session: Session, lead_id: str) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown lead {lead_id}")
    return lead


def _require_score(session: Session, lead_id: str) -> Score:
    score = latest_score(session, lead_id)
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"lead {lead_id} has not been scored"
        )
    return score


def _score_out(session: Session, score: Score) -> ScoreOut:
    results = [
        CheckResultOut(
            check_id=r.check_id,
            check_version=r.check_version,
            status=r.status,
            confidence=r.confidence,
            method=r.method,
            reason=r.reason,
            evidence=[EvidenceItem(**e) for e in r.evidence],
            effective_status=_effective_status(session, r),
            check_result_id=r.id,
        )
        for r in score.check_results
    ]
    return ScoreOut(
        lead_id=score.lead_id,
        score_id=score.id,
        decision=score.decision,
        sampled_for_qa=score.sampled_for_qa,
        library_snapshot_hash=score.library_snapshot_hash,
        scored_at=score.scored_at.isoformat(),
        results=results,
    )


@router.post("/{lead_id}/score", response_model=ScoreOut, status_code=status.HTTP_201_CREATED)
def score_endpoint(lead_id: str, session: Session = Depends(get_session)) -> ScoreOut:
    """Score (or rescore) this lead's latest recording."""
    _require_lead(session, lead_id)
    try:
        score = score_lead(session, lead_id)
    except ScoringError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _score_out(session, score)


@router.get("/{lead_id}/score", response_model=ScoreOut)
def get_score(lead_id: str, session: Session = Depends(get_session)) -> ScoreOut:
    """Every check result and its evidence for the lead's latest score."""
    _require_lead(session, lead_id)
    score = _require_score(session, lead_id)
    return _score_out(session, score)


@router.get("/{lead_id}/gate", response_model=GateOut)
def get_gate(lead_id: str, session: Session = Depends(get_session)) -> GateOut:
    """The gate decision and which critical checks drove it."""
    _require_lead(session, lead_id)
    score = _require_score(session, lead_id)

    lead = session.get(Lead, lead_id)
    critical_ids = {
        c.check_id for c in load_all() if c.retailer == lead.retailer and c.critical
    }
    fails = [
        r.check_id
        for r in score.check_results
        if r.check_id in critical_ids and _effective_status(session, r) == "FAIL"
    ]
    reviews = [
        r.check_id
        for r in score.check_results
        if r.check_id in critical_ids and _effective_status(session, r) == "REVIEW"
    ]

    return GateOut(
        lead_id=lead_id,
        decision=score.decision,
        sampled_for_qa=score.sampled_for_qa,
        critical_fails=sorted(fails),
        critical_reviews=sorted(reviews),
    )


@router.post("/{lead_id}/submit", response_model=SubmitOut)
def submit_lead(lead_id: str, session: Session = Depends(get_session)) -> SubmitOut:
    """Refuse to ship an unscored or held sale. This is PLAN.md's live proof.

    409 when there is no score at all, and 409 again when the gate did not
    clear it for AUTO_SUBMIT, even after overrides: the system reports and
    holds, it never talks itself into shipping (hard rule 5).
    """
    lead = _require_lead(session, lead_id)
    score = latest_score(session, lead_id)
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"lead {lead_id} is unscored, cannot submit",
        )

    if score.decision != DECISION_AUTO_SUBMIT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"lead {lead_id} is held: {score.decision}",
        )

    lead.status = "SUBMITTED"
    session.commit()

    return SubmitOut(lead_id=lead_id, status=lead.status, decision=score.decision)
