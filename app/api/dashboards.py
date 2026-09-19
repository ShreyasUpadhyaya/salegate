"""Rollups for the dashboards. Read-only, no writes to leads or scores here."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Lead, Score
from app.scoring.gate import DECISION_AUTO_SUBMIT, DECISION_HELD_TL, DECISION_QA_REVIEW

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


class AgentRollup(BaseModel):
    agent_id: str
    total_scored: int
    auto_submit: int
    qa_review: int
    held_tl: int
    first_pass_yield: float  # AUTO_SUBMIT / total, the un-held share
    critical_fail_rate: float  # HELD_TL / total


@router.get("/agents", response_model=list[AgentRollup])
def agent_rollup(session: Session = Depends(get_session)) -> list[AgentRollup]:
    """One row per agent, counted from every lead's latest score.

    A lead can be scored more than once (a rerun); only the latest score per
    lead counts, so an agent's numbers reflect where each call stands now, not
    every historical attempt.
    """
    leads = {lead.lead_id: lead for lead in session.scalars(select(Lead)).all()}

    latest_by_lead: dict[str, Score] = {}
    for score in session.scalars(select(Score).order_by(Score.id)).all():
        latest_by_lead[score.lead_id] = score  # later id overwrites, so this is the latest

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for lead_id, score in latest_by_lead.items():
        lead = leads.get(lead_id)
        if lead is None:
            continue
        counts[lead.agent_id]["total"] += 1
        counts[lead.agent_id][score.decision] += 1

    rollups: list[AgentRollup] = []
    for agent_id, c in sorted(counts.items()):
        total = c["total"]
        rollups.append(
            AgentRollup(
                agent_id=agent_id,
                total_scored=total,
                auto_submit=c[DECISION_AUTO_SUBMIT],
                qa_review=c[DECISION_QA_REVIEW],
                held_tl=c[DECISION_HELD_TL],
                first_pass_yield=round(c[DECISION_AUTO_SUBMIT] / total, 3) if total else 0.0,
                critical_fail_rate=round(c[DECISION_HELD_TL] / total, 3) if total else 0.0,
            )
        )
    return rollups
