from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import config
from ..auth import get_current_user
from ..database import get_db
from ..models import Document, MeetingSession
from ..schemas import SessionCreate, SessionDetailOut, SessionOut
from ..services import bot_manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

ROOM_CODE_RE = re.compile(r"^[a-z0-9-]{3,48}$")


def _room_code_from_link(meet_url: str) -> str:
    return meet_url.strip().rstrip("/").rsplit("/", 1)[-1].strip().lower()


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    payload: SessionCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)
) -> MeetingSession:
    room_code = _room_code_from_link(payload.meet_url)
    if not ROOM_CODE_RE.match(room_code):
        raise HTTPException(status_code=422, detail="That doesn't look like a valid meet link")
    if not config.GROQ_API_KEY:
        raise HTTPException(status_code=400, detail="GROQ_API_KEY is not set in .env")

    document = None
    if payload.document_id:
        document = await db.get(Document, payload.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="No document with that id")

    session = MeetingSession(
        meet_url=f"{config.MEET_ROOM_BASE_URL}/{room_code}",
        owner_email=user["email"],
        bot_name=config.BOT_DISPLAY_NAME,
        recipient_email=(payload.recipient_email or user["email"] or config.DEFAULT_RECIPIENT_EMAIL or None),
        instructions=payload.instructions.strip(),
        document_id=document.id if document else None,
        document_title=document.title if document else None,
        status="queued",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    bot_manager.start(
        session.id, session.meet_url, session.recipient_email, session.instructions, document_id=session.document_id
    )
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)
) -> list[MeetingSession]:
    rows = (
        (
            await db.execute(
                select(MeetingSession)
                .where(MeetingSession.owner_email == user["email"])
                .order_by(MeetingSession.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)
) -> MeetingSession:
    session = await db.get(
        MeetingSession,
        session_id,
        options=[
            selectinload(MeetingSession.transcript_entries),
            selectinload(MeetingSession.chat_messages),
            selectinload(MeetingSession.qa_exchanges),
        ],
    )
    if session is None or session.owner_email != user["email"]:
        raise HTTPException(status_code=404, detail="No session with that id")
    return session


@router.post("/{session_id}/leave")
async def leave_session(
    session_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)
) -> dict:
    session = await db.get(MeetingSession, session_id)
    if session is None or session.owner_email != user["email"]:
        raise HTTPException(status_code=404, detail="No session with that id")
    if not bot_manager.stop(session_id):
        raise HTTPException(status_code=409, detail="That session is not running")
    return {"id": session_id, "status": "leaving"}
