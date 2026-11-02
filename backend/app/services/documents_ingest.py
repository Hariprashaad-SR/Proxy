"""Extract/chunk text, and render PDF pages to images, from an uploaded document.

Plain text/markdown is read directly; PDFs go through pypdf for text and
pymupdf for rendering actual page images (used by the in-call presentation
walkthrough — see bot_manager._present_document). No embeddings API is used
for retrieval (see retrieval.py) so there is no step here beyond plain-text
extraction and fixed-size chunking for that.
"""

from __future__ import annotations

import re
from pathlib import Path

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


_PAGE_BREAK_RE = re.compile(r"\f|^[ \t]*(?:-{3,}|\*{3,})[ \t]*$", re.MULTILINE)


def extract_pages(path: Path) -> list[str]:
    """Split a document into "slides" for the in-call presentation walkthrough.

    For a PDF this returns exactly one entry per actual page (including blank
    ones, e.g. a title slide or an image-only page with no text layer) so it
    lines up 1:1 by index with render_pdf_pages' images — the walkthrough
    shows the real page and narrates whatever text (if any) came with it.
    Plain text/markdown has no such boundary, so we honor an explicit manual
    break instead (a form-feed, or a lone "---"/"***" line, same convention
    reveal.js/marp-style slide decks use) — falling back to the whole file as
    one slide if no break is found. Blank sections are dropped there, since
    there's no image counterpart to stay aligned with.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return [(page.extract_text() or "").strip() for page in reader.pages]

    text = path.read_text(encoding="utf-8", errors="ignore")
    pages = [p.strip() for p in _PAGE_BREAK_RE.split(text) if p.strip()]
    if pages:
        return pages

    fallback = extract_text(path).strip()
    return [fallback] if fallback else []


def render_pdf_pages(path: Path, out_dir: Path, *, dpi: int = 150) -> list[str]:
    """Rasterize each page of a PDF to a PNG under out_dir, named "0.png",
    "1.png", etc. — the actual page as it looks, not a text reconstruction.
    Returns the filenames in page order (always len() == the PDF's page
    count, matching extract_pages above). Raises on a corrupt/unreadable
    PDF; callers should treat that as "no images available", not a hard
    upload failure."""
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    filenames = []
    with pymupdf.open(str(path)) as doc:
        zoom = dpi / 72
        matrix = pymupdf.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            pixmap = page.get_pixmap(matrix=matrix)
            filename = f"{i}.png"
            pixmap.save(str(out_dir / filename))
            filenames.append(filename)
    return filenames


def chunk_text(text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks
