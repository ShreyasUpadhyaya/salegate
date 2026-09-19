"""Append-only override log. Never updated, never deleted (D8, hard rule 9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import CheckResult, Override

router = APIRouter(prefix="/api/check-results", tags=["overrides"])


class OverrideIn(BaseModel):
    auditor: str = Field(min_length=1)
    new_status: str = Field(pattern="^(PASS|FAIL|REVIEW|NOTE|NA)$")
    reason: str = Field(min_length=1)


class OverrideOut(BaseModel):
    id: int
    check_result_id: int
    auditor: str
    old_status: str
    new_status: str
    reason: str
    created_at: str


@router.post(
    "/{check_result_id}/override",
    response_model=OverrideOut,
    status_code=status.HTTP_201_CREATED,
)
def create_override(
    check_result_id: int, payload: OverrideIn, session: Session = Depends(get_session)
) -> OverrideOut:
    """Append one override row. The old status is read live, never supplied
    by the caller, so the audit trail always reflects what was true at the
    time, not what the client claimed it was.
    """
    check_result = session.get(CheckResult, check_result_id)
    if check_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown check result {check_result_id}",
        )

    current_status = check_result.status
    if check_result.overrides:
        current_status = max(check_result.overrides, key=lambda o: o.created_at).new_status

    override = Override(
        check_result_id=check_result_id,
        auditor=payload.auditor,
        old_status=current_status,
        new_status=payload.new_status,
        reason=payload.reason,
    )
    session.add(override)
    session.commit()
    session.refresh(override)

    return OverrideOut(
        id=override.id,
        check_result_id=override.check_result_id,
        auditor=override.auditor,
        old_status=override.old_status,
        new_status=override.new_status,
        reason=override.reason,
        created_at=override.created_at.isoformat(),
    )


@router.get("/{check_result_id}/overrides", response_model=list[OverrideOut])
def list_overrides(
    check_result_id: int, session: Session = Depends(get_session)
) -> list[OverrideOut]:
    """Full override history for one check result, oldest first."""
    check_result = session.get(CheckResult, check_result_id)
    if check_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown check result {check_result_id}",
        )

    ordered = sorted(check_result.overrides, key=lambda o: o.created_at)
    return [
        OverrideOut(
            id=o.id,
            check_result_id=o.check_result_id,
            auditor=o.auditor,
            old_status=o.old_status,
            new_status=o.new_status,
            reason=o.reason,
            created_at=o.created_at.isoformat(),
        )
        for o in ordered
    ]
