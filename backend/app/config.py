"""Configuration, loaded from .env at import time."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(key: str, default: str = "0") -> bool:
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


def _int(key: str, default: str) -> int:
    return int(os.getenv(key, default).strip() or default)


def _float(key: str, default: str) -> float:
    return float(os.getenv(key, default).strip() or default)


# --------------------------------------------------------------------------
# App / CORS
# --------------------------------------------------------------------------
APP_ENV = os.getenv("APP_ENV", "development").strip()
BACKEND_PORT = _int("BACKEND_PORT", "8000")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# --------------------------------------------------------------------------
# Postgres
# --------------------------------------------------------------------------
POSTGRES_USER = os.getenv("POSTGRES_USER", "proxy").strip()
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "").strip()
POSTGRES_DB = os.getenv("POSTGRES_DB", "proxy").strip()
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost").strip()
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# --------------------------------------------------------------------------
# Groq
# --------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
# Whisper endpoint used to transcribe each participant's live audio chunks.
GROQ_TRANSCRIBE_MODEL = os.getenv("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3").strip()
# Text-to-speech endpoint used for the bot's spoken replies. The model is
# gated behind a one-time terms acceptance per Groq org — see
# https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english").strip()
TTS_VOICE = os.getenv("TTS_VOICE", "tara").strip()

# --------------------------------------------------------------------------
# Meet — Google sign-in + the shared websocket signaling endpoint
# (routers/meet_ws.py), used by both the `meet` calling app and the bot.
# --------------------------------------------------------------------------
# OAuth client ID of the `meet` frontend (Google Cloud Console -> Credentials
# -> OAuth client ID -> Web application). Used server-side to verify the
# audience of every Google ID token presented when joining a room.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
# Shared secret the bot presents instead of a Google ID token (it has no
# Google account of its own). Any non-empty value; keep it out of the client.
BOT_JOIN_SECRET = os.getenv("BOT_JOIN_SECRET", "").strip()
BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "Proxy AI").strip()
# Websocket signaling endpoint the bot connects to (this same backend).
MEET_SIGNAL_WS_URL = os.getenv("MEET_SIGNAL_WS_URL", "ws://localhost:8000/ws/meet").strip()
# Base URL humans open in a browser to join the same room, e.g.
# MEET_ROOM_BASE_URL/<room code> — the standalone `meet` app, not `proxy`.
MEET_ROOM_BASE_URL = os.getenv("MEET_ROOM_BASE_URL", "http://localhost:5174").rstrip("/")
# Voice-activity detection for transcription: instead of chopping each
# speaker's audio into fixed-length windows (which cuts mid-word and makes
# Whisper hallucinate on fragments), buffer while they're actually speaking
# and flush once a pause lasts VAD_HANGOVER_MS — i.e. one Whisper call per
# utterance, not per N seconds.
VAD_RMS_THRESHOLD = _int("VAD_RMS_THRESHOLD", "450")  # 16-bit PCM RMS; raise if background noise triggers it
VAD_HANGOVER_MS = _int("VAD_HANGOVER_MS", "600")  # silence required to consider an utterance finished
VAD_MIN_UTTERANCE_MS = _int("VAD_MIN_UTTERANCE_MS", "400")  # shorter blips are dropped, not sent to Whisper
VAD_MAX_UTTERANCE_MS = _int("VAD_MAX_UTTERANCE_MS", "12000")  # hard cap so a long monologue still gets flushed
MEETING_END_POLL_SECONDS = _float("MEETING_END_POLL_SECONDS", "5")
# Consecutive empty-room polls required before Proxy decides everyone left.
MEETING_END_CONFIRM_POLLS = _int("MEETING_END_CONFIRM_POLLS", "3")
# Word Proxy listens for (in speech or chat) before it answers or presents,
# e.g. "Proxy, what did we decide about X?"
TRIGGER_WORD = os.getenv("TRIGGER_WORD", "proxy").strip().lower()
# How long each slide stays up when auto-presenting an attached document,
# scaled to how much text is actually on it (word_count * SECONDS_PER_WORD,
# clamped to [MIN, MAX]) — a title slide gets ~MIN seconds, a dense one gets
# more reading time. Narrating/TTS for that slide counts toward the total;
# the rest is just a wait. The presentation runs concurrently with normal
# trigger listening, so questions can still be asked and answered while a
# slide is showing (see bot_manager._PresentationState).
SLIDE_MIN_SECONDS = _float("SLIDE_MIN_SECONDS", "20")
SLIDE_MAX_SECONDS = _float("SLIDE_MAX_SECONDS", "90")
SLIDE_SECONDS_PER_WORD = _float("SLIDE_SECONDS_PER_WORD", "0.35")

# --------------------------------------------------------------------------
# Email (SMTP) — sent after the bot leaves a meeting
# --------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = _int("SMTP_PORT", "587")
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "").strip() or SMTP_USERNAME
SMTP_USE_TLS = _bool("SMTP_USE_TLS", "1")
DEFAULT_RECIPIENT_EMAIL = os.getenv("DEFAULT_RECIPIENT_EMAIL", "").strip()

# --------------------------------------------------------------------------
# Documents (uploaded concepts the bot can present / answer from)
# --------------------------------------------------------------------------
DOCUMENTS_DIR = BASE_DIR / os.getenv("DOCUMENTS_DIR", "documents")
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", "20")
# Rendered PDF page images (see documents_ingest.render_pdf_pages), served
# at PUBLIC_BACKEND_URL/media/{document_id}/{n}.png — see main.py's mount.
PAGES_DIR = DOCUMENTS_DIR / "pages"
# Base URL this backend is actually reachable at from a browser (the `meet`
# frontend's <img> tags, specifically) — not necessarily BACKEND_PORT's
# bind address if you're behind a proxy/different host.
PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", f"http://localhost:{BACKEND_PORT}").rstrip("/")

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
PAGES_DIR.mkdir(parents=True, exist_ok=True)


def missing_settings() -> list[str]:
    """Names of settings the app needs before the bot/email features work."""
    problems = []
    if not GROQ_API_KEY:
        problems.append("GROQ_API_KEY")
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
        problems.append("SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD")
    if not DEFAULT_RECIPIENT_EMAIL:
        problems.append("DEFAULT_RECIPIENT_EMAIL")
    if not GOOGLE_CLIENT_ID:
        problems.append("GOOGLE_CLIENT_ID")
    if not BOT_JOIN_SECRET:
        problems.append("BOT_JOIN_SECRET")
    return problems
