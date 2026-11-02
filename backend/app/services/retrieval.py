"""Naive keyword-overlap retrieval over uploaded document chunks.

No embeddings API is involved — Groq is an inference endpoint, not an
embeddings provider the rest of this app depends on, and pulling in a
separate embeddings service for a handful of uploaded documents is more
machinery than the problem needs. Scoring by token overlap is good enough to
find the right chunk to hand the model for a "present X" or "what does the
doc say about Y" request.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document, DocumentChunk

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> Counter:
    return Counter(_WORD.findall(text.lower()))


async def top_chunks(
    db: AsyncSession, query: str, *, limit: int = 4, document_ids: list[str] | None = None
) -> list[tuple[str, str]]:
    """Returns [(document_title, chunk_text), ...] ranked by token overlap with query.

    document_ids, if given non-empty, restricts the search to just those
    documents — used to scope a "present" request to whichever docs the user
    picked for that session, rather than the whole library.
    """
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []

    stmt = select(DocumentChunk.text, Document.title).join(Document, Document.id == DocumentChunk.document_id)
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))
    rows = (await db.execute(stmt)).all()

    scored = []
    for chunk_text, title in rows:
        chunk_tokens = set(_tokens(chunk_text))
        overlap = len(query_tokens & chunk_tokens)
        if overlap:
            scored.append((overlap, title, chunk_text))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [(title, text) for _, title, text in scored[:limit]]


async def format_context(
    db: AsyncSession, query: str, *, limit: int = 4, document_ids: list[str] | None = None
) -> str:
    chunks = await top_chunks(db, query, limit=limit, document_ids=document_ids)
    if not chunks:
        return ""
    return "\n\n".join(f"[{title}]\n{text}" for title, text in chunks)


async def best_document_context(db: AsyncSession, query: str, *, max_chars: int = 12000) -> str:
    """When a request clearly points at one specific uploaded document (e.g.
    "present the pricing doc"), return that document's FULL text rather than
    a handful of matched chunks — "opening the file" instead of skimming
    excerpts. Returns "" if no document stands out as a clear match.
    """
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return ""

    rows = (
        await db.execute(
            select(Document.id, Document.title, DocumentChunk.chunk_index, DocumentChunk.text).join(
                DocumentChunk, DocumentChunk.document_id == Document.id
            )
        )
    ).all()
    if not rows:
        return ""

    scores: dict[str, int] = {}
    titles: dict[str, str] = {}
    chunks_by_doc: dict[str, list[tuple[int, str]]] = {}
    for doc_id, title, chunk_index, text in rows:
        titles[doc_id] = title
        chunks_by_doc.setdefault(doc_id, []).append((chunk_index, text))
        # A hit against the title is a much stronger signal of "which file do
        # they mean" than a hit buried in one chunk of body text.
        title_overlap = len(query_tokens & set(_tokens(title))) * 5
        chunk_overlap = len(query_tokens & set(_tokens(text)))
        scores[doc_id] = scores.get(doc_id, 0) + title_overlap + chunk_overlap

    best_id = max(scores, key=scores.get)
    if scores[best_id] <= 0:
        return ""

    full_text = "\n".join(text for _, text in sorted(chunks_by_doc[best_id]))[:max_chars]
    return f"[{titles[best_id]} — full document]\n{full_text}"
