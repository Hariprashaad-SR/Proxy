"""WebRTC bot client for our self-hosted meet server — the replacement for
the old Google Meet / Playwright engine. There is no browser, no DOM to
scrape: the bot is a native WebRTC participant.

It joins a room through the backend's websocket signaling, exchanges SDP
with every other participant already there (and answers anyone who joins
later), and receives their audio tracks directly. Each peer's audio runs
through a lightweight voice-activity detector so Whisper gets one clean
utterance per call instead of arbitrary fixed-length windows that chop
words in half (the single biggest cause of garbage transcripts). The same
VAD state says whether anyone is currently talking, which bot_manager uses
to avoid the bot speaking over someone mid-sentence.

The bot also has a real outgoing audio track (BotAudioTrack, fanned out to
every peer connection via aiortc's MediaRelay) so it can speak its replies
with Groq TTS, not just type them — `speak()` synthesizes and enqueues
audio; when TTS is unavailable it's a no-op and the chat reply still goes
out on its own.

Exposes the same small interface bot_manager.py already drives (start, join,
enable_captions, refresh_roster, poll_captions, poll_chat, send_chat,
is_meeting_ended, leave, close) plus speak/is_anyone_speaking/wait_for_quiet
and present_slide/clear_slide (broadcasts the "slide" message meet_ws.py
relays so `meet` can render the current page of an attached document).
"""

from __future__ import annotations

import asyncio
import fractions
import json
import time
import wave
from dataclasses import dataclass
from io import BytesIO

import av
import numpy as np
import websockets
from aiortc import MediaStreamTrack, RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import MediaStreamError

from .. import config
from . import groq_client

RTC_CONFIG = RTCConfiguration(iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")])

# -- incoming audio -> Whisper -----------------------------------------------
IN_SAMPLE_RATE = 16000
VAD_FRAME_MS = 30
VAD_FRAME_SAMPLES = int(IN_SAMPLE_RATE * VAD_FRAME_MS / 1000)
VAD_FRAME_BYTES = VAD_FRAME_SAMPLES * 2  # 16-bit mono

# -- outgoing audio (TTS) -----------------------------------------------------
OUT_SAMPLE_RATE = 48000
OUT_CHANNELS = 2
OUT_BYTES_PER_SAMPLE_FRAME = 2 * OUT_CHANNELS  # int16 * channels
OUT_FRAME_MS = 20


@dataclass
class _PeerState:
    name: str
    pc: RTCPeerConnection


class BotAudioTrack(MediaStreamTrack):
    """The bot's own outgoing audio: silence until speak() enqueues PCM,
    paced in real time so aiortc's encoder gets frames at the right rate."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self.sample_rate = OUT_SAMPLE_RATE
        self._samples_per_frame = int(self.sample_rate * OUT_FRAME_MS / 1000)
        self._pending = bytearray()
        self._timestamp = 0
        self._start_time: float | None = None

    def enqueue(self, pcm_stereo_48k: bytes) -> None:
        self._pending += pcm_stereo_48k

    def pending_seconds(self) -> float:
        return len(self._pending) / OUT_BYTES_PER_SAMPLE_FRAME / self.sample_rate

    async def recv(self):
        if self._start_time is None:
            self._start_time = time.time()
        self._timestamp += self._samples_per_frame
        delay = self._start_time + self._timestamp / self.sample_rate - time.time()
        if delay > 0:
            await asyncio.sleep(delay)

        needed = self._samples_per_frame * OUT_BYTES_PER_SAMPLE_FRAME
        if len(self._pending) >= needed:
            chunk = bytes(self._pending[:needed])
            del self._pending[:needed]
        else:
            chunk = bytes(self._pending) + b"\x00" * (needed - len(self._pending))
            self._pending.clear()

        frame = av.AudioFrame(format="s16", layout="stereo", samples=self._samples_per_frame)
        frame.sample_rate = self.sample_rate
        frame.planes[0].update(chunk)
        frame.pts = self._timestamp - self._samples_per_frame
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        return frame


class MeetBot:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._ws = None
        self._recv_task: asyncio.Task | None = None
        self.peer_id: str | None = None
        self.room_id: str | None = None
        self._peers: dict[str, _PeerState] = {}
        self._roster: dict[str, str] = {}
        self._speaking: dict[str, bool] = {}
        self._caption_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._chat_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._closed = asyncio.Event()
        self._ever_had_peer = False
        self._empty_polls = 0
        self._out_track = BotAudioTrack()
        self._relay = MediaRelay()

    # -- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        pass  # nothing to warm up — no browser to launch

    @staticmethod
    def _room_id_from(meet_url: str) -> str:
        return meet_url.rstrip("/").rsplit("/", 1)[-1].strip().lower()

    async def join(self, meet_url: str, bot_name: str) -> None:
        self.room_id = self._room_id_from(meet_url)
        self._ws = await websockets.connect(config.MEET_SIGNAL_WS_URL, max_size=2**22)
        await self._ws.send(
            json.dumps(
                {"type": "join", "room": self.room_id, "bot_secret": config.BOT_JOIN_SECRET, "name": bot_name}
            )
        )

        first = json.loads(await self._ws.recv())
        if first.get("type") != "joined":
            raise RuntimeError(f"meet server didn't welcome us: {first}")
        self.peer_id = first["id"]

        for participant in first.get("participants", []):
            self._roster[participant["id"]] = participant["name"]
            await self._connect_to(participant["id"], participant["name"], initiator=True)

        self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._handle_message(msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._closed.set()

    async def _handle_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == "peer-joined":
            self._roster[msg["id"]] = msg["name"]
        elif mtype == "peer-left":
            self._roster.pop(msg.get("id"), None)
            self._speaking.pop(msg.get("id"), None)
            peer = self._peers.pop(msg.get("id"), None)
            if peer is not None:
                await peer.pc.close()
        elif mtype == "chat":
            await self._chat_queue.put((msg.get("name", "Unknown"), msg.get("text", "")))
        elif mtype == "signal":
            await self._handle_signal(msg["from"], msg.get("data") or {})

    async def _handle_signal(self, from_id: str, data: dict) -> None:
        description = data.get("description")
        if description is None:
            return
        peer = self._peers.get(from_id)

        if description.get("type") == "offer":
            if peer is None:
                peer = await self._connect_to(from_id, self._roster.get(from_id, "Guest"), initiator=False)
            await peer.pc.setRemoteDescription(RTCSessionDescription(sdp=description["sdp"], type="offer"))
            answer = await peer.pc.createAnswer()
            await peer.pc.setLocalDescription(answer)
            await self._wait_ice_complete(peer.pc)
            await self._send_signal(from_id, peer.pc.localDescription)
        elif description.get("type") == "answer" and peer is not None:
            await peer.pc.setRemoteDescription(RTCSessionDescription(sdp=description["sdp"], type="answer"))

    async def _connect_to(self, peer_id: str, name: str, *, initiator: bool) -> _PeerState:
        pc = RTCPeerConnection(configuration=RTC_CONFIG)
        state = _PeerState(name=name, pc=pc)
        self._peers[peer_id] = state

        # Every connection carries the bot's own (mostly-silent) outgoing
        # track from the start, so speaking later never needs renegotiation.
        pc.addTrack(self._relay.subscribe(self._out_track))

        @pc.on("track")
        def on_track(track) -> None:
            if track.kind == "audio":
                asyncio.create_task(self._consume_audio(peer_id, name, track))
            else:
                asyncio.create_task(self._drain_track(track))

        if initiator:
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await self._wait_ice_complete(pc)
            await self._send_signal(peer_id, pc.localDescription)

        return state

    @staticmethod
    async def _wait_ice_complete(pc: RTCPeerConnection, timeout: float = 5.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while pc.iceGatheringState != "complete" and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.05)

    async def _send_signal(self, to: str, description) -> None:
        await self._send(
            {"type": "signal", "to": to, "data": {"description": {"sdp": description.sdp, "type": description.type}}}
        )

    async def _send(self, payload: dict) -> None:
        if self._ws is not None:
            await self._ws.send(json.dumps(payload))

    # -- audio -> transcript, via per-speaker voice-activity detection ----

    @staticmethod
    async def _drain_track(track) -> None:
        """We never asked for video, but some peers' answers may still carry
        a track if their browser attached one before negotiation — discard
        frames so aiortc's jitter buffer doesn't grow unbounded."""
        while True:
            try:
                await track.recv()
            except MediaStreamError:
                return

    async def _consume_audio(self, peer_id: str, speaker: str, track) -> None:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=IN_SAMPLE_RATE)
        pending = bytearray()  # resampled PCM not yet sliced into VAD frames
        utterance = bytearray()
        silence_run_ms = 0
        in_speech = False
        self._speaking[peer_id] = False

        hangover_ms = config.VAD_HANGOVER_MS
        min_bytes = int(IN_SAMPLE_RATE * 2 * config.VAD_MIN_UTTERANCE_MS / 1000)
        max_bytes = int(IN_SAMPLE_RATE * 2 * config.VAD_MAX_UTTERANCE_MS / 1000)

        def flush(reason: str) -> None:
            nonlocal utterance
            if len(utterance) >= min_bytes:
                asyncio.create_task(self._transcribe_chunk(speaker, bytes(utterance)))
            utterance = bytearray()

        try:
            while True:
                try:
                    frame = await track.recv()
                except MediaStreamError:
                    return
                for resampled in resampler.resample(frame):
                    pending += resampled.to_ndarray().tobytes()

                while len(pending) >= VAD_FRAME_BYTES:
                    vad_frame, pending[:] = bytes(pending[:VAD_FRAME_BYTES]), pending[VAD_FRAME_BYTES:]
                    samples = np.frombuffer(vad_frame, dtype="<i2").astype(np.float32)
                    rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0

                    if rms >= config.VAD_RMS_THRESHOLD:
                        in_speech = True
                        silence_run_ms = 0
                        utterance += vad_frame
                        self._speaking[peer_id] = True
                    elif in_speech:
                        utterance += vad_frame  # keep natural trailing audio
                        silence_run_ms += VAD_FRAME_MS
                        if silence_run_ms >= hangover_ms:
                            flush("pause")
                            in_speech = False
                            silence_run_ms = 0
                            self._speaking[peer_id] = False

                    if len(utterance) >= max_bytes:
                        flush("max-length")  # still talking — just segment it

        finally:
            if len(utterance) >= min_bytes:
                flush("track-ended")
            self._speaking[peer_id] = False

    async def _transcribe_chunk(self, speaker: str, pcm: bytes) -> None:
        try:
            text = await groq_client.transcribe_audio(_pcm_to_wav(pcm, IN_SAMPLE_RATE))
        except groq_client.GroqError:
            return
        text = text.strip()
        if text:
            await self._caption_queue.put((speaker, text))

    # -- outgoing speech (TTS) ---------------------------------------------

    async def speak(self, text: str) -> None:
        """Best-effort: synthesizes `text` and plays it on the bot's
        outgoing track. No-ops quietly if TTS isn't available (e.g. the
        model's terms haven't been accepted yet) — the chat reply still
        goes out regardless."""
        text = text.strip()
        if not text:
            return
        try:
            audio_bytes = await groq_client.synthesize_speech(text)
            pcm = _decode_to_pcm_stereo48k(audio_bytes)
        except groq_client.GroqError:
            return
        if not pcm:
            return
        self._out_track.enqueue(pcm)
        duration = len(pcm) / OUT_BYTES_PER_SAMPLE_FRAME / OUT_SAMPLE_RATE
        await asyncio.sleep(duration)

    # -- turn-taking: don't speak over someone else -------------------------

    def is_anyone_speaking(self) -> bool:
        return any(self._speaking.values())

    async def wait_for_quiet(self, timeout: float = 8.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while self.is_anyone_speaking() and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.2)

    # -- bot_manager-facing interface --------------------------------------

    async def enable_captions(self) -> None:
        pass  # every participant's audio is transcribed continuously already

    async def refresh_roster(self) -> list[str]:
        return list(self._roster.values())

    async def poll_captions(self) -> list[tuple[str, str, str]]:
        ops: list[tuple[str, str, str]] = []
        while not self._caption_queue.empty():
            speaker, text = self._caption_queue.get_nowait()
            ops.append(("insert", speaker, text))
        return ops

    async def poll_chat(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        while not self._chat_queue.empty():
            out.append(self._chat_queue.get_nowait())
        return out

    async def send_chat(self, text: str) -> None:
        await self._send({"type": "chat", "text": text})

    async def present_slide(
        self, *, index: int, total: int, title: str, text: str | None = None, image_url: str | None = None
    ) -> None:
        await self._send(
            {"type": "slide", "index": index, "total": total, "title": title, "text": text, "image_url": image_url}
        )

    async def clear_slide(self) -> None:
        await self._send({"type": "slide", "clear": True})

    async def is_meeting_ended(self) -> bool:
        if self._closed.is_set():
            return True
        if self._roster:
            self._ever_had_peer = True
            self._empty_polls = 0
            return False
        if not self._ever_had_peer:
            return False  # bot joined an empty room; wait for someone to show up
        self._empty_polls += 1
        return self._empty_polls >= config.MEETING_END_CONFIRM_POLLS

    async def leave(self) -> None:
        try:
            await self._send({"type": "leave"})
        except Exception:  # noqa: BLE001 - socket may already be gone
            pass

    async def close(self) -> str | None:
        """No browser means no screen recording — always returns None."""
        if self._recv_task is not None:
            self._recv_task.cancel()
        for peer in self._peers.values():
            await peer.pc.close()
        if self._ws is not None:
            await self._ws.close()
        return None


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buf.getvalue()


def _decode_to_pcm_stereo48k(audio_bytes: bytes) -> bytes:
    container = av.open(BytesIO(audio_bytes))
    resampler = av.AudioResampler(format="s16", layout="stereo", rate=OUT_SAMPLE_RATE)
    pcm = bytearray()
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            pcm += resampled.to_ndarray().tobytes()
    container.close()
    return bytes(pcm)
