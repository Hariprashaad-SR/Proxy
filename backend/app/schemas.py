from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    # A link into the `meet` app for a meeting that already exists (created
    # by whoever's hosting it) — Proxy joins that room as a participant.
    meet_url: str = Field(..., min_length=5)
    recipient_email: str | None = None
    # Freeform instructions for what Proxy should do/record in this meeting —
    # the only thing that shapes its behavior and its summary. No separate
    # checkboxes; it always joins as "Proxy AI".
    instructions: str = Field(..., min_length=3)
    # Optional — one document from the shared library to walk through
    # slide-by-slide right after joining. Doesn't scope Q&A retrieval.
    document_id: str | None = None


class TranscriptEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    speaker: str
    text: str
    started_at: datetime
    updated_at: datetime


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sender: str
    text: str
    direction: str
    created_at: datetime


class QAExchangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source: str
    asked_by: str
    kind: str
    question: str
    answer: str
    created_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meet_url: str
    bot_name: str
    recipient_email: str | None
    instructions: str
    document_id: str | None
    document_title: str | None
    status: str
    error: str | None
    participants: list
    recording_path: str | None
    summary: dict | None
    joined_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SessionDetailOut(SessionOut):
    transcript_entries: list[TranscriptEntryOut] = []
    chat_messages: list[ChatMessageOut] = []
    qa_exchanges: list[QAExchangeOut] = []


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    filename: str
    char_count: int
    page_count: int = 0
    created_at: datetime


class StatusOut(BaseModel):
    missing_settings: list[str]
    groq_model: str
    transcribe_model: str
    trigger_word: str
