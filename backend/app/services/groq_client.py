"""Groq client: chat-completions plus Whisper transcription.

Everything Proxy AI says or writes — live responses and the final summary —
is shaped by the freeform instructions whoever sent it typed into the
session form. There's no separate fixed "present" format or fixed summary
schema; respond_to_trigger and summarize_meeting both just hand those
instructions to the model as the thing to follow.

transcribe_audio turns one rolling chunk of a speaker's raw WAV audio
(captured straight off their WebRTC track — see meet_client.py) into text,
standing in for live captions.
"""

from __future__ import annotations

import json

import httpx

from .. import config


class GroqError(RuntimeError):
    pass


async def _chat(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> str:
    if not config.GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY is not set")

    payload: dict = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if max_tokens:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{config.GROQ_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        )

    if response.status_code >= 400:
        detail = response.text[:500]
        try:
            detail = response.json()["error"]["message"]
        except Exception:  # noqa: BLE001 - fall back to raw body
            pass
        raise GroqError(f"{response.status_code}: {detail}")

    body = response.json()
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise GroqError(f"Unexpected response shape: {json.dumps(body)[:300]}") from exc


async def transcribe_audio(wav_bytes: bytes, *, filename: str = "chunk.wav") -> str:
    if not config.GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY is not set")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{config.GROQ_BASE_URL}/audio/transcriptions",
            data={"model": config.GROQ_TRANSCRIBE_MODEL},
            files={"file": (filename, wav_bytes, "audio/wav")},
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        )

    if response.status_code >= 400:
        detail = response.text[:500]
        try:
            detail = response.json()["error"]["message"]
        except Exception:  # noqa: BLE001 - fall back to raw body
            pass
        raise GroqError(f"{response.status_code}: {detail}")

    body = response.json()
    return body.get("text", "")


async def synthesize_speech(text: str) -> bytes:
    """Text -> WAV bytes via Groq's TTS endpoint, so Proxy AI can actually
    speak its reply into the call instead of only typing it. Requires the
    org to have accepted the TTS model's terms in the Groq console — until
    then this raises GroqError and callers fall back to text-only."""
    if not config.GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY is not set")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{config.GROQ_BASE_URL}/audio/speech",
            json={
                "model": config.GROQ_TTS_MODEL,
                "input": text[:2000],
                "voice": config.TTS_VOICE,
                "response_format": "wav",
            },
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        )

    if response.status_code >= 400:
        detail = response.text[:500]
        try:
            detail = response.json()["error"]["message"]
        except Exception:  # noqa: BLE001 - fall back to raw body
            pass
        raise GroqError(f"{response.status_code}: {detail}")

    return response.content


def _response_system_prompt(instructions: str) -> str:
    return (
        "You are Proxy AI, sent into this live meeting by someone who gave you these instructions for "
        f"what you should do and pay attention to:\n\"{instructions.strip()}\"\n\n"
        "Follow those instructions when deciding how to respond — what to focus on, what to present if "
        "asked, what tone to use, what NOT to do. Where they don't cover something you're asked, use your "
        "own good judgement. Keep replies concise and conversational — they get typed into the meeting "
        "chat, not read as a document."
    )


async def respond_to_trigger(
    message: str, *, speaker: str, transcript_context: str, doc_context: str, instructions: str
) -> str:
    prompt = (
        f"{speaker} just addressed you during the meeting:\n\"{message}\"\n\n"
        f"Recent meeting transcript for context:\n{transcript_context or '(no transcript yet)'}\n\n"
        f"Relevant material from uploaded documents, if any:\n{doc_context or '(none found)'}\n\n"
        "Respond directly, following your instructions above. If you don't have enough information, say "
        "so plainly instead of guessing."
    )
    return await _chat(
        [
            {"role": "system", "content": _response_system_prompt(instructions)},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=600,
    )


def _slide_system_prompt(instructions: str) -> str:
    return (
        "You are Proxy AI, presenting an uploaded document slide-by-slide to a live meeting, narrating "
        "each one in chat (and out loud) as you go. The person who sent you gave these instructions for "
        f"what you should do and pay attention to:\n\"{instructions.strip()}\"\n\n"
        "Follow those instructions where they say anything relevant to how you present. Otherwise, just "
        "summarize this one slide's content in 2-4 short, conversational sentences — not a copy of the "
        "raw text, and no preamble like \"this slide covers\"; just say the substance directly."
    )


async def summarize_slide(text: str, *, title: str, index: int, total: int, instructions: str) -> str:
    prompt = f"Document: {title}\nSlide {index} of {total}:\n{text[:4000]}"
    return await _chat(
        [
            {"role": "system", "content": _slide_system_prompt(instructions)},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=300,
    )


def _summary_system_prompt(instructions: str) -> str:
    return (
        "You are Proxy AI, writing the post-meeting summary. Default to a Minutes of Meeting format: "
        "Attendees, Discussion Summary (organized by topic), Decisions Made, Action Items (each with an "
        "owner where one was stated), and Open Questions / Next Steps.\n\n"
        "The person who sent you into this meeting gave you these instructions for what to do and what "
        f"to record:\n\"{instructions.strip()}\"\n\n"
        "Those instructions take priority over the default structure above — if they ask for something "
        "narrower, different, or additional, follow that; treat the Minutes of Meeting shape as a "
        "fallback, not a rigid template to force everything into. Use only what's in the "
        "transcript/chat/Q&A below — never invent anything that wasn't actually said or decided. Format "
        "as clean markdown (headers, bullet points).\n\n"
        'Return strict JSON of this exact shape: {"summary": "<the markdown-formatted summary as one string>"}.'
    )


async def summarize_meeting(transcript_text: str, chat_text: str, qa_text: str, instructions: str) -> dict:
    if not transcript_text.strip() and not chat_text.strip():
        raise GroqError("Nothing was captured during the meeting to summarize")

    prompt = (
        f"TRANSCRIPT (everyone's actual speech, via Whisper):\n{transcript_text or '(none captured)'}\n\n"
        f"CHAT LOG:\n{chat_text or '(none)'}\n\n"
        f"RESPONSES PROXY AI GAVE DURING THE MEETING:\n{qa_text or '(none)'}\n"
    )
    raw = await _chat(
        [
            {"role": "system", "content": _summary_system_prompt(instructions)},
            {"role": "user", "content": prompt},
        ],
        json_mode=True,
        temperature=0.3,
        max_tokens=1500,
    )
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GroqError("Model did not return valid JSON for the summary") from exc
    result["model"] = config.GROQ_MODEL
    return result
