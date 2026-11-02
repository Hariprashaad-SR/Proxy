from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..auth import get_current_user
from ..database import get_db
from ..models import Document, DocumentChunk
from ..schemas import DocumentOut
from ..services.documents_ingest import chunk_text, extract_pages, extract_text, render_pdf_pages

# Upload only — a document attached to a request is scoped to that one
# session and cleaned up automatically once it ends (see
# bot_manager._cleanup_document), so there's no shared library to list or
# manage here.
router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(get_current_user)])

ALLOWED_SUFFIXES = {".txt", ".md", ".pdf"}


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)) -> Document:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail=f"Supported file types: {', '.join(sorted(ALLOWED_SUFFIXES))}")

    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {config.MAX_UPLOAD_MB} MB limit")

    doc_id = uuid.uuid4().hex
    stored_name = f"{doc_id}{suffix}"
    storage_path = config.DOCUMENTS_DIR / stored_name
    storage_path.write_bytes(raw)

    try:
        text = extract_text(storage_path)
    except Exception as exc:  # noqa: BLE001 - surface extraction failures clearly
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not read file contents: {exc}") from exc

    chunks = chunk_text(text)
    if not chunks:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No extractable text found in that file")

    pages = extract_pages(storage_path)

    page_images = None
    if suffix == ".pdf":
        try:
            page_images = render_pdf_pages(storage_path, config.PAGES_DIR / doc_id)
        except Exception:  # noqa: BLE001 - presentation falls back to text slides for this doc
            page_images = None

    document = Document(
        id=doc_id,
        title=Path(file.filename or stored_name).stem,
        filename=file.filename or stored_name,
        storage_path=str(storage_path),
        char_count=len(text),
        pages=pages,
        page_images=page_images,
    )
    db.add(document)
    for i, chunk in enumerate(chunks):
        db.add(DocumentChunk(document_id=doc_id, chunk_index=i, text=chunk))
    await db.commit()
    await db.refresh(document)
    return document
