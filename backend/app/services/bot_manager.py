"""Session lifecycle: one asyncio task per meeting, mirroring the shape of a
Celery-job-per-meeting setup without needing a broker for this scale.

The task: joins the bot (a WebRTC peer of the shared backend, see
meet_client.py) to its room, then runs two things concurrently (see _run):
_poll_loop, which polls for new transcript lines (from Whisper, chunked off
each participant's live audio) and chat, persisting both, and watching for
the trigger word (default "proxy") to respond — however the session's
freeform instructions say it should — and, if a document was attached,
_present_document, which walks through it slide-by-slide. Running them
concurrently (not one after the other) means a question asked while a slide
is up still gets answered right away rather than queueing behind the whole
deck. When the call ends (or a stop is requested) it leaves, summarizes with
Groq (again, per those instructions), emails the summary, and tears the
connection down.

Status values: queued -> joining -> live -> leaving -> summarizing ->
completed, plus failed (see the error field).
"""

from __future__ import annotations

import asyncio
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import config
from ..database import AsyncSessionLocal
from ..models import ChatMessage, Document, MeetingSession, QAExchange, TranscriptEntry
from . import email_sender, groq_client, retrieval
from .meet_client import MeetBot

_stop_events: dict[str, asyncio.Event] = {}
_tasks: dict[str, asyncio.Task] = {}

TRIGGER_RE = re.compile(r"\b" + re.escape(config.TRIGGER_WORD) + r"\b[,:]?\s*", re.I)


def _extract_trigger(text: str) -> str | None:
    match = TRIGGER_RE.search(text)
    if not match:
        return None
    return text[match.end():].strip()


async def _update_session(session_id: str, **fields) -> None:
    async with AsyncSessionLocal() as db:
        session = await db.get(MeetingSession, session_id)
        if session is None:
            return
        for key, value in fields.items():
            setattr(session, key, value)
        await db.commit()


async def _insert_transcript(session_id: str, speaker: str, text: str) -> int:
    async with AsyncSessionLocal() as db:
        row = TranscriptEntry(session_id=session_id, speaker=speaker, text=text)
        db.add(row)
        await db.commit()
        return row.id


async def _update_transcript(row_id: int, text: str) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(TranscriptEntry, row_id)
        if row is not None:
            row.text = text
            await db.commit()


async def _insert_chat(session_id: str, sender: str, text: str, direction: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(ChatMessage(session_id=session_id, sender=sender, text=text, direction=direction))
        await db.commit()


async def _insert_qa(session_id: str, source: str, asked_by: str, question: str, answer: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            QAExchange(
                session_id=session_id, source=source, asked_by=asked_by, kind="response", question=question,
                answer=answer,
            )
        )
        await db.commit()


async def _handle_trigger(
    bot: MeetBot,
    session_id: str,
    source: str,
    speaker: str,
    text: str,
    *,
    instructions: str,
    require_trigger: bool = True,
    document_context: str | None = None,
) -> None:
    if speaker.strip().lower() == config.BOT_DISPLAY_NAME.strip().lower():
        return

    remainder = _extract_trigger(text)
    if remainder is None:
        # While presenting, _poll_loop passes require_trigger=False for chat
        # — the bot already has the floor, so a question in chat is assumed
        # to be directed at it without needing "proxy" first.
        if require_trigger:
            return
        remainder = text.strip()
    if not remainder:
        return

    # Don't start composing a reply while someone's still mid-sentence —
    # pick the conversation back up once it's actually quiet.
    await bot.wait_for_quiet()

    if document_context:
        # This session has its own attached document — use its actual full
        # text directly rather than guessing via keyword retrieval, so
        # answers are grounded in the right material instead of whatever
        # scored best by accidental word overlap.
        doc_context = document_context[:12000]
    else:
        async with AsyncSessionLocal() as db:
            # No document attached to this session — fall back to keyword
            # retrieval (see retrieval.py) in case something relevant is
            # still in the table (e.g. another session's upload, mid-call).
            doc_context = await retrieval.best_document_context(db, remainder)
            if not doc_context:
                doc_context = await retrieval.format_context(db, remainder)

    async with AsyncSessionLocal() as db:
        recent = (
            (
                await db.execute(
                    select(TranscriptEntry)
                    .where(TranscriptEntry.session_id == session_id)
                    .order_by(TranscriptEntry.started_at.desc())
                    .limit(15)
                )
            )
            .scalars()
            .all()
        )
    transcript_context = "\n".join(f"{e.speaker}: {e.text}" for e in reversed(recent))

    try:
        answer = await groq_client.respond_to_trigger(
            remainder,
            speaker=speaker,
            transcript_context=transcript_context,
            doc_context=doc_context,
            instructions=instructions,
        )

        async def _post_chat() -> None:
            # A longer, presentation-style reply reads as multiple paragraphs
            # — post each as its own chat message rather than one giant bubble.
            for part in [p.strip() for p in answer.split("\n\n") if p.strip()]:
                await bot.send_chat(part)
                await asyncio.sleep(0.6)

        # Someone may have started talking again while Groq was composing
        # this — check once more right before actually delivering it.
        await bot.wait_for_quiet()
        await asyncio.gather(_post_chat(), bot.speak(answer))
    except groq_client.GroqError as exc:
        answer = f"(couldn't reach Groq: {exc})"
        try:
            await bot.send_chat("Sorry, I couldn't come up with a response just now.")
        except Exception:  # noqa: BLE001
            pass

    await _insert_qa(session_id, source, speaker, remainder, answer)


class _PresentationState:
    """Shared between _present_document and _poll_loop (see _run) so the
    chat handler knows a presentation is live right now and can skip the
    trigger-word requirement — see _handle_trigger's require_trigger."""

    def __init__(self) -> None:
        self.active = False


def _slide_duration_seconds(text: str) -> float:
    """How long a slide should stay up, scaled to how much is actually on
    it — a title slide ("Q3 Roadmap") clamps to the floor, a dense slide
    gets more reading time, never more than the ceiling."""
    words = len(text.split())
    return max(config.SLIDE_MIN_SECONDS, min(config.SLIDE_MAX_SECONDS, words * config.SLIDE_SECONDS_PER_WORD))


async def _slide_wait(bot: MeetBot, stop: asyncio.Event, deadline: float) -> bool:
    """Waits until `deadline` (an event-loop clock time), checking every
    couple seconds whether to bail early. Returns False if the caller should
    stop presenting (stop requested / meeting ended), True otherwise."""
    loop = asyncio.get_event_loop()
    while loop.time() < deadline:
        if stop.is_set() or await bot.is_meeting_ended():
            return False
        await asyncio.sleep(min(2.0, deadline - loop.time()))
    return True


async def _present_document(
    bot: MeetBot,
    session_id: str,
    stop: asyncio.Event,
    document: Document,
    presentation_state: _PresentationState,
    *,
    instructions: str,
) -> None:
    """Walk through an attached document slide-by-slide right after joining:
    show the real rendered page (or, for a non-PDF document, its plain text)
    via present_slide, narrate a short summary in chat and out loud, then
    hold that slide up for a duration scaled to its content (see
    _slide_duration_seconds) before moving on. Runs concurrently with
    _poll_loop (see _run) — not sequentially before it — so questions asked
    mid-presentation are still answered right away; presentation_state.active
    additionally tells _poll_loop to treat any chat message as directed at
    the bot while this is running, not just ones with the trigger word.
    """
    loop = asyncio.get_event_loop()
    pages = document.pages or []
    images = document.page_images or []
    total = len(pages)
    presentation_state.active = True
    try:
        for i, text in enumerate(pages, start=1):
            if stop.is_set() or await bot.is_meeting_ended():
                return
            slide_start = loop.time()

            image_name = images[i - 1] if i - 1 < len(images) else None
            image_url = f"{config.PUBLIC_BACKEND_URL}/media/{document.id}/{image_name}" if image_name else None

            if text.strip():
                try:
                    summary = await groq_client.summarize_slide(
                        text, title=document.title, index=i, total=total, instructions=instructions
                    )
                except groq_client.GroqError:
                    summary = text[:400]
            else:
                summary = "This slide is mostly visual — take a moment to look it over."

            await bot.send_chat(f"**Slide {i}/{total} — {document.title}**\n{summary}")
            await bot.present_slide(
                index=i - 1, total=total, title=document.title, image_url=image_url, text=None if image_url else text
            )
            await bot.speak(summary)

            if not await _slide_wait(bot, stop, slide_start + _slide_duration_seconds(text)):
                return
    finally:
        presentation_state.active = False
        await bot.clear_slide()


async def _present_document_safe(
    bot: MeetBot,
    session_id: str,
    stop: asyncio.Event,
    document: Document,
    presentation_state: _PresentationState,
    *,
    instructions: str,
) -> None:
    """_present_document, but a failure here (e.g. Groq erroring on every
    slide) can't take down _poll_loop — they run via the same
    asyncio.gather, which otherwise cancels every task the moment any one
    of them raises."""
    try:
        await _present_document(bot, session_id, stop, document, presentation_state, instructions=instructions)
    except Exception:  # noqa: BLE001
        pass


async def _poll_loop(
    bot: MeetBot,
    session_id: str,
    stop: asyncio.Event,
    *,
    instructions: str,
    presentation_state: _PresentationState | None = None,
    document_context: str | None = None,
) -> None:
    transcript_row_id: int | None = None
    last_roster_refresh = 0.0
    bot_name = config.BOT_DISPLAY_NAME

    while not stop.is_set():
        now = asyncio.get_event_loop().time()
        if now - last_roster_refresh > 20:
            roster = await bot.refresh_roster()
            if roster:
                await _update_session(session_id, participants=roster)
            last_roster_refresh = now

        for mode, speaker, text in await bot.poll_captions():
            if mode == "insert":
                transcript_row_id = await _insert_transcript(session_id, speaker, text)
            elif transcript_row_id is not None:
                await _update_transcript(transcript_row_id, text)
            await _handle_trigger(
                bot, session_id, "caption", speaker, text, instructions=instructions, document_context=document_context
            )

        for sender, text in await bot.poll_chat():
            direction = "outgoing" if sender.strip().lower() == bot_name.strip().lower() else "incoming"
            await _insert_chat(session_id, sender, text, direction)
            if direction == "incoming":
                # While a document is being presented, treat any chat
                # message as a question for the bot — it already has the
                # floor, so requiring "proxy" first would just mean missed
                # questions. Captions/speech still need the trigger word,
                # so a side conversation between participants isn't
                # constantly interrupted.
                require_trigger = not (presentation_state and presentation_state.active)
                await _handle_trigger(
                    bot,
                    session_id,
                    "chat",
                    sender,
                    text,
                    instructions=instructions,
                    require_trigger=require_trigger,
                    document_context=document_context,
                )

        if await bot.is_meeting_ended():
            return

        await asyncio.sleep(config.MEETING_END_POLL_SECONDS)


async def _compile_logs(session_id: str) -> tuple[str, str, str]:
    async with AsyncSessionLocal() as db:
        session = await db.get(
            MeetingSession,
            session_id,
            options=[
                selectinload(MeetingSession.transcript_entries),
                selectinload(MeetingSession.chat_messages),
                selectinload(MeetingSession.qa_exchanges),
            ],
        )
        transcript_text = "\n".join(f"{e.speaker}: {e.text}" for e in session.transcript_entries)
        chat_text = "\n".join(f"{m.sender}: {m.text}" for m in session.chat_messages)
        qa_text = "\n".join(f"Q ({q.source}, {q.asked_by}): {q.question}\nA: {q.answer}" for q in session.qa_exchanges)
    return transcript_text, chat_text, qa_text


async def _cleanup_document(document_id: str) -> None:
    """A document attached to a request only ever belongs to that one
    session — delete its row (DocumentChunks cascade), the uploaded file,
    and any rendered page images once the session is over, so it never
    lingers or resurfaces for the next request. session.document_title (a
    plain string snapshot, not a join) still shows what was presented in
    history after this runs — see MeetingSession.document_id's
    ON DELETE SET NULL."""
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, document_id)
        if document is None:
            return
        storage_path = document.storage_path
        await db.delete(document)
        await db.commit()
    Path(storage_path).unlink(missing_ok=True)
    shutil.rmtree(config.PAGES_DIR / document_id, ignore_errors=True)


async def _run(
    session_id: str, meet_url: str, recipient_email: str | None, instructions: str, document_id: str | None = None
) -> None:
    stop = _stop_events[session_id]
    bot = MeetBot(session_id)
    joined_at = None

    try:
        await _update_session(session_id, status="joining")
        await bot.start()
        await bot.join(meet_url, config.BOT_DISPLAY_NAME)
        joined_at = datetime.now(timezone.utc)
        await bot.enable_captions()
        await bot.refresh_roster()

        await _update_session(session_id, status="live", joined_at=joined_at)

        document = None
        if document_id:
            async with AsyncSessionLocal() as db:
                document = await db.get(Document, document_id)

        # This session's own attached document (if any) is used directly as
        # Q&A context — see _handle_trigger — rather than guessed at via
        # keyword retrieval, since it's unambiguously the right material.
        document_context = "\n\n".join(document.pages) if document and document.pages else None

        presentation_state = _PresentationState()
        tasks = [
            _poll_loop(
                bot,
                session_id,
                stop,
                instructions=instructions,
                presentation_state=presentation_state,
                document_context=document_context,
            )
        ]
        if document is not None and document.pages:
            tasks.append(
                _present_document_safe(
                    bot, session_id, stop, document, presentation_state, instructions=instructions
                )
            )

        # Presenting and listening run concurrently — not one after the
        # other — so a question asked while a slide is up still gets
        # answered by _handle_trigger (inside _poll_loop) without waiting
        # for the walkthrough to finish.
        await asyncio.gather(*tasks)

        await _update_session(session_id, status="leaving")
        await bot.leave()
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        await _update_session(session_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        return
    finally:
        recording_path = None
        try:
            recording_path = await bot.close()
        except Exception:  # noqa: BLE001
            pass
        if recording_path:
            await _update_session(session_id, recording_path=recording_path)
        _stop_events.pop(session_id, None)
        _tasks.pop(session_id, None)
        # A document attached to a request is scoped to that one session —
        # nothing shows up again for the next one, so clean it up now
        # regardless of how this session ended.
        if document_id:
            try:
                await _cleanup_document(document_id)
            except Exception:  # noqa: BLE001
                pass

    ended_at = datetime.now(timezone.utc)
    transcript_text, chat_text, qa_text = await _compile_logs(session_id)
    duration_label = ""
    if joined_at:
        minutes = max(1, int((ended_at - joined_at).total_seconds() // 60))
        duration_label = f"{minutes} min"

    await _update_session(session_id, status="summarizing", ended_at=ended_at)
    try:
        summary = await groq_client.summarize_meeting(transcript_text, chat_text, qa_text, instructions)
    except groq_client.GroqError as exc:
        await _update_session(session_id, status="failed", error=f"Groq summary failed: {exc}")
        return

    await _update_session(session_id, status="completed", summary=summary)

    # Email is opt-in infrastructure, not a required step — if SMTP was
    # never configured, that's expected and not worth surfacing as an error
    # on every single completed session; only an actual send failure (SMTP
    # configured but something went wrong) gets recorded.
    if config.SMTP_HOST and config.SMTP_USERNAME and config.SMTP_PASSWORD:
        to_email = (recipient_email or config.DEFAULT_RECIPIENT_EMAIL or "").strip()
        try:
            email_sender.send_summary_email(
                to_email=to_email, meet_url=meet_url, summary=summary, duration_label=duration_label
            )
        except email_sender.EmailError as exc:
            await _update_session(session_id, error=f"Summary saved, but the email failed to send: {exc}")


def start(
    session_id: str, meet_url: str, recipient_email: str | None, instructions: str, document_id: str | None = None
) -> None:
    _stop_events[session_id] = asyncio.Event()
    _tasks[session_id] = asyncio.create_task(
        _run(session_id, meet_url, recipient_email, instructions, document_id)
    )


def stop(session_id: str) -> bool:
    event = _stop_events.get(session_id)
    if event is None:
        return False
    event.set()
    return True


def stop_all() -> None:
    for event in list(_stop_events.values()):
        event.set()
