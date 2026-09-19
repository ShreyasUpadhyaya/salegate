"""POST /api/dialler/recordings. The only way audio enters the system."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.ingest.dialler import RecordingAccepted, store_recording
from app.models import Lead

router = APIRouter(prefix="/api/dialler", tags=["dialler"])


@router.post(
    "/recordings",
    response_model=RecordingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_recording(
    response: Response,
    lead_id: str = Form(...),
    call_started_at: datetime = Form(...),
    agent_id: str = Form(...),
    audio: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> RecordingAccepted:
    """Accept one call recording for one lead.

    202 on a new recording, 200 when this exact audio was already stored for this
    lead. Either way the body names the recording, so the dialler can retry a
    timed-out post without creating a second copy.
    """
    if session.get(Lead, lead_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown lead {lead_id}"
        )

    payload = await audio.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="empty audio upload"
        )

    try:
        result = store_recording(
            session,
            lead_id=lead_id,
            audio=payload,
            filename=audio.filename or "",
            call_started_at=call_started_at,
            agent_id=agent_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc

    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return result
