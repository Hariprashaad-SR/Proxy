"""Proxy — a bot that joins meetings hosted on our own self-hosted meet
server (see meet-server/) as a real WebRTC participant, transcribes every
speaker's live audio with Groq Whisper, answers questions and presents
uploaded material in chat when addressed by its trigger word, and emails a
Groq-generated summary once it leaves.

Run (after `docker compose up -d` for Postgres and meet-server):
    cp .env.example .env   # then fill it in
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .database import init_models
from .routers import documents, meet_ws, sessions
from .schemas import StatusOut
from .services import bot_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    yield
    bot_manager.stop_all()


app = FastAPI(title="Proxy", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(meet_ws.router)

# Rendered PDF page images for the in-call presentation walkthrough — plain
# static files, no auth, so `meet`'s <img> tags can load them directly (same
# trust model as the rest of the shared document library: anyone signed
# into Proxy can see it, and anyone with the direct image URL can too).
app.mount("/media", StaticFiles(directory=str(config.PAGES_DIR)), name="media")


@app.get("/api/status", response_model=StatusOut)
async def status() -> dict:
    return {
        "missing_settings": config.missing_settings(),
        "groq_model": config.GROQ_MODEL,
        "transcribe_model": config.GROQ_TRANSCRIBE_MODEL,
        "trigger_word": config.TRIGGER_WORD,
    }
