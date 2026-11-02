"""ORM models.

A `MeetingSession` is one run of the bot against one Meet link. Everything it
hears (captions), reads (chat), asks and answers, and ultimately summarizes
hangs off of it.

`Document` / `DocumentChunk` hold the material the user uploads ("concepts")
that the bot can be asked to present or answer questions from during a
meeting — independent of any one session.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class MeetingSession(Base):
    __tablename__ = "meeting_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    meet_url: Mapped[str] = mapped_column(String(512))
    owner_email: Mapped[str] = mapped_column(String(320), default="")
    bot_name: Mapped[str] = mapped_column(String(128), default="Proxy AI")
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Freeform instructions from whoever sent the bot — what it should do and
    # pay attention to in this meeting. Drives both its live responses and
    # the shape of its end-of-meeting summary; there's no separate
    # checkbox/toggle behavior layered on top of this.
    instructions: Mapped[str] = mapped_column(Text, default="")
    # Optional document attached to this request — the bot walks through it
    # slide-by-slide in the meeting right after joining (see bot_manager's
    # _present_document). This does NOT scope Q&A retrieval, which stays
    # global across the whole shared document library. document_title is a
    # snapshot taken at creation so history views don't need a join.
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    document_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)
    recording_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transcript_entries: Mapped[list["TranscriptEntry"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TranscriptEntry.started_at"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )
    qa_exchanges: Mapped[list["QAExchange"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="QAExchange.created_at"
    )


class TranscriptEntry(Base):
    """One speaker turn scraped from Meet's live captions."""

    __tablename__ = "transcript_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="CASCADE"))
    speaker: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped[MeetingSession] = relationship(back_populates="transcript_entries")


class ChatMessage(Base):
    """One message scraped from the visible Meet chat panel."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="CASCADE"))
    sender: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(16), default="incoming")  # incoming | outgoing (bot)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[MeetingSession] = relationship(back_populates="chat_messages")


class QAExchange(Base):
    """A question the bot was asked (by voice/caption or chat) and its answer."""

    __tablename__ = "qa_exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(16))  # caption | chat
    asked_by: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), default="question")  # question | present
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[MeetingSession] = relationship(back_populates="qa_exchanges")


class Document(Base):
    """An uploaded file holding concepts the bot can present / answer from."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256))
    filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(512))
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # Ordered slide text for the in-call presentation walkthrough — one entry
    # per PDF page, or per manual break in a .txt/.md file (see
    # documents_ingest.extract_pages). Nullable for documents uploaded before
    # this existed; bot_manager skips presentation quietly when absent.
    pages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Rendered page images for a PDF (see documents_ingest.render_pdf_pages)
    # — filenames under DOCUMENTS_DIR/pages/{document.id}/, served at
    # PUBLIC_BACKEND_URL/media/{document.id}/{filename}. 1:1 with `pages` by
    # index when present. None for non-PDFs, or if rendering failed — the
    # walkthrough falls back to showing that slide's text instead.
    page_images: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index"
    )

    @property
    def page_count(self) -> int:
        return len(self.pages) if self.pages else 0


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="chunks")
