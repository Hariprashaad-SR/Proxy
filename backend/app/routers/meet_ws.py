"""The meet signaling endpoint: websocket room relay the `meet` frontend (and
Proxy's own bot, see services/meet_client.py) connect to. Lives in the same
backend as the session/documents APIs — one shared backend for both the
Meet calling app and the Proxy console, per the split described in the repo
README.

No media ever passes through here — it only relays two things between
whoever is in the same room:
  1. WebRTC signaling (SDP offer/answer) so browsers can set up direct
     peer-to-peer audio/video.
  2. Chat messages, and mic/camera state changes (so a muted/camera-off
     participant can be shown correctly without a media-level signal).

A human joins with a Google ID token, verified server-side against Google's
public keys — the resulting name/email/picture is the authoritative identity
for that participant, not anything the client could just claim. The bot
joins instead with a shared secret (BOT_JOIN_SECRET) since it has no Google
account; it gets a name but no picture, and `is_bot: true`.

Protocol (JSON messages over one websocket per participant):
  -> {"type": "join", "room": "<code>", "id_token": "<google id token>"}
  -> {"type": "join", "room": "<code>", "bot_secret": "<...>", "name": "<bot display name>"}
  <- {"type": "joined", "id": "<peer id>", "participants": [{"id","name","picture","is_bot"}, ...]}
  <- {"type": "peer-joined", "id", "name", "picture", "is_bot"}   (broadcast to the room, not the joiner)
  <- {"type": "peer-left", "id"}
  -> {"type": "signal", "to": "<peer id>", "data": {"description": {"sdp","type"}}}
  <- {"type": "signal", "from": "<peer id>", "data": {...}}          (relayed verbatim)
  -> {"type": "chat", "text": "..."}
  <- {"type": "chat", "from": "<peer id>", "name": "<sender name>", "text": "..."}
  -> {"type": "state", "muted": bool, "cameraOff": bool}
  <- {"type": "state", "from": "<peer id>", "muted": bool, "cameraOff": bool}
  -> {"type": "slide", "index": int, "total": int, "title": "...",
      "text": "..."|null, "image_url": "..."|null}                                  (the bot, presenting)
  -> {"type": "slide", "clear": true}                                               (presentation done)
  <- {"type": "slide", "from": "<peer id>", ...same fields, relayed verbatim}

  A slide carries image_url (an actual rendered PDF page, preferred) or text
  (a plain-text fallback for non-PDF documents) — never neither.

Rooms and participants are kept in memory only — there's nothing to
persist, a room just exists as long as someone is in it.
"""

from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import config
from ..services import google_auth

router = APIRouter()

# room_id -> {peer_id: {"ws": WebSocket, "name": str, "picture": str | None, "is_bot": bool}}
ROOMS: dict[str, dict[str, dict]] = {}


def _room(room_id: str) -> dict:
    return ROOMS.setdefault(room_id, {})


def _public(peer_id: str, info: dict) -> dict:
    return {"id": peer_id, "name": info["name"], "picture": info["picture"], "is_bot": info["is_bot"]}


async def _broadcast(room_id: str, payload: dict, *, exclude: str | None = None) -> None:
    data = json.dumps(payload)
    for peer_id, info in list(_room(room_id).items()):
        if peer_id == exclude:
            continue
        try:
            await info["ws"].send_text(data)
        except Exception:  # noqa: BLE001 - a dead socket will be cleaned up by its own handler
            pass


async def _send_to(room_id: str, peer_id: str, payload: dict) -> None:
    info = _room(room_id).get(peer_id)
    if info is not None:
        try:
            await info["ws"].send_text(json.dumps(payload))
        except Exception:  # noqa: BLE001
            pass


def _verify_identity(join_msg: dict) -> dict | None:
    """Returns {"name","picture","is_bot"} for a valid credential, else None."""
    bot_secret = join_msg.get("bot_secret")
    if bot_secret:
        if not config.BOT_JOIN_SECRET or not secrets.compare_digest(bot_secret, config.BOT_JOIN_SECRET):
            return None
        name = str(join_msg.get("name") or "Proxy").strip() or "Proxy"
        return {"name": name, "picture": None, "is_bot": True}

    token = join_msg.get("id_token")
    if not token:
        return None
    identity = google_auth.verify_id_token(token)
    if identity is None:
        return None
    return {"name": identity["name"], "picture": identity["picture"], "is_bot": False}


@router.websocket("/ws/meet")
async def meet_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        raw = await websocket.receive_text()
        join_msg = json.loads(raw)
    except Exception:  # noqa: BLE001 - bad/slow client, nothing to clean up yet
        await websocket.close(code=4000, reason="expected a join message")
        return

    if join_msg.get("type") != "join":
        await websocket.close(code=4000, reason="first message must be type=join")
        return

    room_id = str(join_msg.get("room") or "").strip().lower()
    if not room_id:
        await websocket.close(code=4000, reason="room is required")
        return

    identity = _verify_identity(join_msg)
    if identity is None:
        await websocket.close(code=4001, reason="sign-in required")
        return

    peer_id = secrets.token_hex(4)
    room = _room(room_id)
    participants = [_public(pid, info) for pid, info in room.items()]
    room[peer_id] = {"ws": websocket, **identity}

    await websocket.send_text(json.dumps({"type": "joined", "id": peer_id, "participants": participants}))
    await _broadcast(room_id, {"type": "peer-joined", **_public(peer_id, room[peer_id])}, exclude=peer_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "signal":
                to = msg.get("to")
                if to:
                    await _send_to(room_id, to, {"type": "signal", "from": peer_id, "data": msg.get("data")})
            elif mtype == "chat":
                text = str(msg.get("text") or "").strip()
                if text:
                    name = room[peer_id]["name"]
                    await _broadcast(room_id, {"type": "chat", "from": peer_id, "name": name, "text": text})
            elif mtype == "state":
                await _broadcast(
                    room_id,
                    {
                        "type": "state",
                        "from": peer_id,
                        "muted": bool(msg.get("muted")),
                        "cameraOff": bool(msg.get("cameraOff")),
                    },
                    exclude=peer_id,
                )
            elif mtype == "slide":
                await _broadcast(room_id, {**msg, "type": "slide", "from": peer_id}, exclude=peer_id)
    except WebSocketDisconnect:
        pass
    finally:
        room.pop(peer_id, None)
        await _broadcast(room_id, {"type": "peer-left", "id": peer_id})
        if not room:
            ROOMS.pop(room_id, None)
