# Proxy

Two separate apps sharing one backend:

- **`meet`** — a Google Meet–alike video calling app. Google sign-in only,
  camera/mic lobby, in-call video grid with avatar fallback when a camera's
  off, chat, reconnect handling. This is where humans (and the bot) actually
  meet.
- **`proxy`** — the bot console, gated behind Google sign-in. Paste a link to
  a meeting already running in `meet`; the bot joins it as a real WebRTC
  participant through the backend (never a browser), does whatever you
  checked (summarize, present), and the result lands in your own History —
  every session is scoped to the Google account that created it.

No Google Meet API or browser automation is involved anywhere. `meet`'s
camera/mic calling is real WebRTC between browsers; the bot is a native
WebRTC peer of its own (via `aiortc`), not a scraped browser tab.

## Architecture

```
backend/   FastAPI + SQLAlchemy (async) against Postgres — the Proxy
           session/documents API AND the Meet websocket signaling endpoint
           (/ws/meet) both live here; the bot is a WebRTC client of its own API.
meet/      React (Vite, port 5174) — the calling app: Google sign-in, lobby,
           in-call UI.
proxy/     React (Vite, port 5173) — the bot console: start sessions, watch
           them live, read summaries.
docker-compose.yml   Runs everything: postgres, backend, meet, proxy
```

```
backend/app/
  main.py                   FastAPI app, CORS, lifespan (creates tables on boot), mounts
                            /media -> PAGES_DIR for rendered PDF page images
  config.py                 .env loading
  database.py               async engine/session
  models.py                 MeetingSession, TranscriptEntry, ChatMessage, QAExchange, Document, DocumentChunk
  schemas.py                Pydantic response/request models
  routers/sessions.py       POST/GET sessions, POST .../leave
  routers/documents.py      upload only — a document is scoped to the one request that
                            attached it, see services/bot_manager._cleanup_document
  routers/meet_ws.py        /ws/meet — room join/signal/chat relay; verifies Google
                            ID tokens (humans) or BOT_JOIN_SECRET (the bot)
  auth.py                   get_current_user — every Proxy REST route requires a Google
                            ID token (Bearer header); sessions are scoped to that email
  services/google_auth.py  shared Google ID token verification (meet_ws.py and auth.py both use it)
  services/meet_client.py   the bot: WebRTC peer connection, audio -> Whisper transcript, chat,
                            present_slide/clear_slide (the in-call document walkthrough)
  services/bot_manager.py   one asyncio task per session; runs _poll_loop (trigger detection)
                            and _present_document concurrently via asyncio.gather;
                            _cleanup_document deletes an attached document once the
                            session ends (file, DB row, rendered page images)
  services/groq_client.py   Groq calls: respond_to_trigger, summarize_slide, summarize_meeting,
                            transcribe_audio, synthesize_speech
  services/retrieval.py     keyword-overlap retrieval over uploaded document chunks
  services/documents_ingest.py   text extraction/chunking + extract_pages (per-slide text) +
                            render_pdf_pages (per-page PNGs via PyMuPDF)
  services/email_sender.py  SMTP summary email
meet/src/
  pages/Home.jsx            signed-in landing: "New meeting" / "Enter a code"
  pages/Room.jsx            orchestrates Lobby -> Call -> Ended for one room
  components/SignInGate.jsx Google sign-in gate (shown whenever not signed in)
  components/Lobby.jsx      camera/mic preview + device toggles + join, handles permission errors
  components/Call.jsx       mesh WebRTC, chat/people side panels, reconnect handling, shows
                            SlidePanel + a video filmstrip while Proxy AI is presenting
  components/SlidePanel.jsx the current slide: a real rendered PDF page image, or a text
                            fallback for non-PDF documents
  components/VideoTile.jsx  video or avatar fallback, mute badge, speaking indicator
  components/Avatar.jsx     Google profile picture, or an initial on a colored circle
proxy/src/
  components/SignInGate.jsx Google sign-in gate — Proxy requires an account, same as meet
  pages/NewRequest.jsx      the request form: meet link, instructions, optional
                            upload-only document attach, recipient
  pages/History.jsx         past sessions, + a "New request" button back to NewRequest
  pages/SessionDetail.jsx   live transcript / chat / Q&A / summary, polls every 3s
  formatChatText.jsx        renders **bold**/line breaks in chat text (Groq's output is
                            lightly-markdown plain text, not HTML)
```

## How it works

1. **Sign in** — `meet` requires a real Google account; there is no
   anonymous/typed-name join. The ID token Google hands back is verified
   server-side (`routers/meet_ws.py`) against Google's own public keys before
   anyone's allowed into a room, so a participant's name/photo can't be
   spoofed by the client.
2. **Create a meeting in `meet`, then send Proxy AI its link** — Proxy itself
   is also gated behind Google sign-in. On its "New" page, paste the `meet`
   link, write freeform instructions for what Proxy AI should do and what it
   should record, and optionally upload a document right there — there's no
   renaming it; it always joins as **Proxy AI**, and your instructions are
   the main thing that shapes its behavior, start to finish. The bot joins
   that room as a real WebRTC participant through the shared backend — no
   browser is opened for it. There's no document library to pick from —
   each upload belongs to that one request and nothing else; see step 3.
3. **Present the attached document, if any, concurrently with everything
   else** — right after joining, the bot walks through it one page at a
   time: for a PDF, each page is rendered to an actual image
   (`services/documents_ingest.render_pdf_pages`, via PyMuPDF) and pushed to
   everyone in the call over `/ws/meet` (`routers/meet_ws.py`'s `slide`
   message) so `meet`'s `Call.jsx`/`SlidePanel.jsx` can show the real page —
   not a text reconstruction of it — in a dedicated panel, served from this
   backend at `/media/{document_id}/{n}.png`. A `.txt`/`.md` document has no
   page images, so it falls back to a styled text slide instead (split on a
   manual `---`/`***`/form-feed break, or treated as one slide if there's
   none — see `extract_pages`). Each slide also gets a short Groq-written
   summary in chat and out loud via TTS, then stays up for a duration scaled
   to how much text is actually on it (`_slide_duration_seconds`: word count
   × `SLIDE_SECONDS_PER_WORD`, clamped to `[SLIDE_MIN_SECONDS,
   SLIDE_MAX_SECONDS]`, default 20-90s) before advancing — a title slide
   settles at the floor, a dense one gets more time. This step runs as its
   own task *alongside* step 5 below, not before it, and while it's live
   `_poll_loop` treats *any* chat message as a question for the bot, not
   just ones with the trigger word (`_PresentationState` — it already has
   the floor, so requiring "proxy" first would just mean missed questions;
   captions/speech still need the trigger word, so this doesn't make the
   bot jump into every spoken side conversation). A question asked while a
   slide is showing is picked up and answered right away, not queued behind
   the rest of the deck, and is answered using the attached document's own
   full text as context (`_run` builds `document_context` once and threads
   it through `_poll_loop`/`_handle_trigger`) rather than a keyword guess —
   see step 5. Once the session ends, the document (file, DB row, rendered
   page images) is deleted — `bot_manager._cleanup_document`, called from
   `_run`'s `finally` regardless of how the session ended. It never shows up
   again; the next request uploads its own.
4. **Listen** — the bot is one more WebRTC participant in the room, just
   without a camera or mic of its own (it authenticates with a shared
   `BOT_JOIN_SECRET` instead of a Google account). It receives everyone
   else's audio track directly and runs it through a lightweight
   voice-activity detector (`services/meet_client.py`): instead of chopping
   audio into fixed-length windows (which cuts words in half and makes
   Whisper guess at fragments), it buffers while someone's actually talking
   and only sends the clip to Whisper once they pause — one Whisper call per
   utterance, not per N seconds. It reads/writes the room's chat the same
   way, as a plain message over the signaling websocket.
5. **Respond — out loud, and without talking over anyone** — any transcript
   line or chat message containing the trigger word (default `proxy`, see
   `TRIGGER_WORD`) is treated as directed at the bot (chat is more lenient
   while presenting — see step 3). Before it answers, it checks whether
   anyone's still mid-sentence (same VAD state as above) and waits for
   things to actually go quiet, so it picks up the conversation rather than
   cutting someone off. The reply is generated by handing your instructions
   to Groq as the system prompt, along with transcript context and this
   session's attached document (if any; its full text, not matched
   snippets — see step 3). With no document attached, it falls back to
   keyword retrieval (`retrieval.py`) over whatever happens to still be in
   the table, e.g. another session's upload mid-call — a secondary path,
   not the primary one anymore now that documents aren't kept around. The
   answer is delivered both ways: posted to chat (rendered with light
   markdown — see `formatChatText.jsx` — so **bold** headers and paragraph
   breaks actually show up, not literal asterisks), and spoken aloud
   through a real outgoing WebRTC audio track via Groq TTS (see the TTS
   setup note below).
6. **Leave & summarize** — when everyone else leaves the room (or you click
   "Leave meeting now" on the session page), the bot leaves, and the full
   transcript (from Whisper, i.e. everyone's actual speech) plus chat and
   its own responses goes to Groq for a summary written as Minutes of the
   Meeting (attendees, discussion by topic, decisions, action items with
   owners, open questions) by default — your instructions can narrow or
   change that shape further. It appears in your History, and is emailed to
   you only if SMTP is actually configured (`SMTP_HOST`/`SMTP_USERNAME`/
   `SMTP_PASSWORD`) — otherwise that step is just skipped, not reported as
   an error, since email is optional infrastructure, not a required one.

### Meet, specifically

- **Lobby**: camera/mic preview before joining. Falls back gracefully if a
  device is blocked or missing — tries video+audio, then audio-only, then
  video-only, then joins with neither, and says so in a banner either way.
- **In-call**: a participant with their camera off shows their Google profile
  photo (or an initial on a colored circle if they have none) instead of a
  blank tile. A muted mic shows a badge on the tile. A rough speaking
  indicator (Web Audio analyser on each stream) highlights whoever's talking.
- **Edge cases handled**: toggling mic/camera mid-call doesn't re-request
  permissions (just enables/disables the existing track, and broadcasts the
  new state so others update that tile); an unexpected websocket drop shows
  "Reconnecting…" and retries with backoff before giving up; leaving shows a
  "You left the meeting" screen with Rejoin / Return home, same as real Meet.

### Text-to-speech setup (one-time, per Groq org)

Proxy AI's spoken replies use Groq's TTS endpoint (`canopylabs/orpheus-v1-english`),
which is gated behind a one-time terms acceptance — without it, `speak()`
fails silently and the bot falls back to chat-only (nothing breaks, it just
won't talk). To enable it: open
https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english
while signed in as the org that owns your `GROQ_API_KEY`, and accept the
model's terms. `TTS_VOICE` (default `tara`) picks which Orpheus voice to use.

### Known limitations, by design

- **Transcription is still utterance-level, not word-by-word streaming.**
  The transcript line for something someone said only appears once they
  pause (VAD_HANGOVER_MS, default 600ms) — correct, but not instantaneous.
  A hard cap (`VAD_MAX_UTTERANCE_MS`, default 12s) segments a long
  uninterrupted monologue into more than one line.
- **The "wait for quiet" turn-taking check has a timeout** (8s) — if VAD
  keeps flagging someone as "speaking" (e.g. sustained background noise
  crossing `VAD_RMS_THRESHOLD`), the bot answers anyway rather than going
  silent forever. Raise the threshold if a noisy room trips this often.
- **Rooms are in-memory only**, inside the shared backend process. Nothing
  to persist; restarting the backend drops every live call (and currently
  any session mid-flight — the bot task dies with it).
- **There's no document library anymore** — a document only exists for the
  one request it was uploaded to, and is deleted once that session ends
  (`bot_manager._cleanup_document`). `retrieval.py`'s keyword-overlap
  scoring over the `documents` table still exists as a fallback for a
  session with no attachment of its own (see step 5), but with nothing
  persisting beyond one live session at a time, it rarely has more than
  that one document to search — effectively dead weight kept around for
  that edge case rather than load-bearing.
- **Only PDFs get real page images** — `.txt`/`.md` documents are rendered
  as a styled text slide instead (there's no original page layout to
  rasterize). A document uploaded before this feature existed (or one whose
  PDF failed to rasterize — `page_images` ends up `null`) has no stored
  images; attaching it to a request falls back to the text slide, or skips
  the walkthrough entirely if it has no stored pages at all either.
- **The walkthrough has no voice/manual control** — slides always advance on
  their own content-scaled timer; there's no "next slide"/"go back" trigger
  yet. Chat questions during it don't need the trigger word (step 3 above),
  but spoken questions still do, same as outside a presentation.
- **Rendered page images are served unauthenticated** (`/media/...`) so
  `meet`'s plain `<img>` tags can load them without a bearer token —
  anyone with the exact image URL can view it while the session is still
  live, since `<img>` can't carry an Authorization header. They stop being
  reachable once the session ends and `_cleanup_document` deletes the
  files.

## Setup

### 1. Google OAuth client ID (required for both `meet` and `proxy`)

1. [Google Cloud Console](https://console.cloud.google.com/) → create/select
   a project → **APIs & Services → Credentials**.
2. Configure the **OAuth consent screen** if you haven't (External is fine
   for personal testing; add yourself — and anyone else who'll sign in — as
   a test user, or publish the app).
3. **Create Credentials → OAuth client ID → Application type: Web
   application**.
4. Under **Authorized JavaScript origins**, add both `http://localhost:5174`
   (meet) and `http://localhost:5173` (proxy).
5. Copy the client ID (looks like `xxxxx.apps.googleusercontent.com`) into
   **all three**: `.env` (`GOOGLE_CLIENT_ID`), `meet/.env`
   (`VITE_GOOGLE_CLIENT_ID`), and `proxy/.env` (`VITE_GOOGLE_CLIENT_ID`) —
   same value everywhere.

No client secret is needed — this uses Google Identity Services' client-side
sign-in flow (an ID token), not a server-side OAuth redirect. The backend
verifies every token itself against Google's public keys before trusting a
name/email/photo or a Bearer-authenticated API call.

### 2. Docker (recommended — runs everything at once)

```bash
cp .env.example .env                # fill in GOOGLE_CLIENT_ID, GROQ_API_KEY, etc.
cp meet/.env.example meet/.env      # fill in VITE_GOOGLE_CLIENT_ID — same value as above
cp proxy/.env.example proxy/.env    # fill in VITE_GOOGLE_CLIENT_ID — same value as above
docker compose up --build
```

That starts Postgres, the shared `backend`, `meet` (http://localhost:5174),
and `proxy` (http://localhost:5173) together.

### Running locally instead

```bash
cp .env.example .env
cp meet/.env.example meet/.env
cp proxy/.env.example proxy/.env

docker compose up -d postgres

cd backend
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 recommended — aiortc wheels lag new releases
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# in another terminal
cd meet && npm install && npm run dev    # http://localhost:5174

# in another terminal
cd proxy && npm install && npm run dev   # http://localhost:5173
```

Open `meet`, sign in, start a meeting, copy its link. Open `proxy`, sign in
(same Google account or a different one — it's whoever's sending the bot),
paste that link into the "New" page, say what Proxy should do, and send it.

## API

Every route below except `/api/status` requires `Authorization: Bearer
<google-id-token>` — `auth.py`'s `get_current_user` verifies it and, for
sessions, scopes reads/writes to that email.

```
POST /api/sessions   {meet_url, instructions, recipient_email?, document_id?} -> 201 session
GET  /api/sessions                                                        -> [session, ...]   (only the caller's own)
GET  /api/sessions/{id}                                                   -> session + transcript + chat + qa + summary
POST /api/sessions/{id}/leave                                             -> ends a live session early
```

`meet_url` is a link into an already-running `meet` room (whatever's after
the last `/` is taken as the room code). `instructions` is required freeform
text — it's the only thing that shapes what the bot does and how it
summarizes; there's no bot-name override (always "Proxy AI") and no
present/summary toggles. `document_id` is optional — the id a prior
`POST /api/documents` call for *this request* returned, to walk through
slide-by-slide on join (see step 3 above); leaving it out behaves exactly as
before. `session.meet_url` in the response is that same link, normalized;
`document_id`/`document_title` echo back what (if anything) was attached —
`document_id` goes back to `null` once the session ends and the document is
deleted, but `document_title` (a plain snapshot, not a join) keeps showing
what was presented in History.

```
POST   /api/documents            multipart file upload (.txt/.md/.pdf)  -> 201 document (incl. page_count)

GET  /api/status                 -> missing settings, model, trigger word (no auth required)

WS   /ws/meet                    -> room join/signal/chat relay, see routers/meet_ws.py
```

Session states: `queued -> joining -> live -> leaving -> summarizing ->
completed`, plus `failed` with an `error` field. A partial failure after the
summary is saved (e.g. the email bounces) is recorded in `error` without
flipping the session back out of `completed`.
