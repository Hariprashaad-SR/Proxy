import { useEffect, useRef, useState } from "react";
import VideoTile from "./VideoTile.jsx";
import Avatar from "./Avatar.jsx";
import SlidePanel from "./SlidePanel.jsx";
import formatChatText from "../formatChatText.jsx";
import { CamIcon, CamOffIcon, ChatIcon, CloseIcon, CopyIcon, HangupIcon, MicIcon, MicOffIcon, PeopleIcon } from "../icons.jsx";

const WS_URL = import.meta.env.VITE_MEET_WS_URL || "ws://localhost:8000/ws/meet";
const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];
const MAX_RECONNECT_ATTEMPTS = 4;

function waitIceComplete(pc) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    function check() {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    }
    pc.addEventListener("icegatheringstatechange", check);
    setTimeout(resolve, 4000); // don't hang forever on a stuck candidate gatherer
  });
}

function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export default function Call({ roomId, identity, initial, onLeave }) {
  const [micOn, setMicOn] = useState(initial.micOn);
  const [camOn, setCamOn] = useState(initial.camOn);
  const [peers, setPeers] = useState([]); // [{id, name, picture, isBot}]
  const [peerAV, setPeerAV] = useState({}); // id -> {muted, cameraOff}
  const [peerStreamsVersion, setPeerStreamsVersion] = useState(0);
  const [chat, setChat] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [slide, setSlide] = useState(null); // null | {index, total, title, text}
  const [panel, setPanel] = useState(null); // null | "chat" | "people"
  const [connection, setConnection] = useState("connecting"); // connecting | live | reconnecting | lost
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);

  const wsRef = useRef(null);
  const selfIdRef = useRef(null);
  const pcsRef = useRef(new Map());
  const remoteStreamsRef = useRef(new Map()); // id -> MediaStream
  const localStreamRef = useRef(initial.stream);
  const leavingRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  // Long-lived handlers (ws.onmessage et al.) are bound once at mount, so they'd
  // otherwise always see the mic/cam state from that first render. Refs make
  // sure broadcastState() always reads what's actually on right now.
  const micOnRef = useRef(initial.micOn);
  const camOnRef = useRef(initial.camOn);

  function send(payload) {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(payload));
  }

  function broadcastState() {
    send({ type: "state", muted: !micOnRef.current, cameraOff: !camOnRef.current });
  }

  function ensureRemoteStream(id) {
    if (!remoteStreamsRef.current.has(id)) remoteStreamsRef.current.set(id, new MediaStream());
    return remoteStreamsRef.current.get(id);
  }

  async function createPeerConnection(id, initiator) {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
    pcsRef.current.set(id, pc);

    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((track) => pc.addTrack(track, localStreamRef.current));
    }

    pc.ontrack = (event) => {
      const bucket = ensureRemoteStream(id);
      bucket.addTrack(event.track);
      setPeerStreamsVersion((v) => v + 1);
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed") {
        try {
          pc.restartIce?.();
        } catch {
          /* best-effort */
        }
      }
    };

    if (initiator) {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitIceComplete(pc);
      send({ type: "signal", to: id, data: { description: pc.localDescription } });
    }
    return pc;
  }

  async function handleSignal(fromId, data) {
    const description = data.description;
    if (!description) return;
    let pc = pcsRef.current.get(fromId);

    if (description.type === "offer") {
      if (!pc) pc = await createPeerConnection(fromId, false);
      await pc.setRemoteDescription(description);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await waitIceComplete(pc);
      send({ type: "signal", to: fromId, data: { description: pc.localDescription } });
    } else if (description.type === "answer" && pc) {
      await pc.setRemoteDescription(description);
    }
  }

  function removePeer(id) {
    setPeers((prev) => prev.filter((p) => p.id !== id));
    setPeerAV((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    const pc = pcsRef.current.get(id);
    if (pc) {
      pc.close();
      pcsRef.current.delete(id);
    }
    remoteStreamsRef.current.delete(id);
  }

  async function handleMessage(msg) {
    if (msg.type === "joined") {
      selfIdRef.current = msg.id;
      setConnection("live");
      reconnectAttemptsRef.current = 0;
      const participants = msg.participants || [];
      setPeers(participants.map((p) => ({ id: p.id, name: p.name, picture: p.picture, isBot: p.is_bot })));
      broadcastState();
      for (const p of participants) {
        await createPeerConnection(p.id, true);
      }
    } else if (msg.type === "peer-joined") {
      setPeers((prev) => [...prev, { id: msg.id, name: msg.name, picture: msg.picture, isBot: msg.is_bot }]);
      broadcastState(); // let the newcomer learn our current mic/cam state
    } else if (msg.type === "peer-left") {
      removePeer(msg.id);
    } else if (msg.type === "chat") {
      setChat((prev) => [...prev, { name: msg.name, text: msg.text, isSelf: msg.from === selfIdRef.current }]);
    } else if (msg.type === "signal") {
      await handleSignal(msg.from, msg.data || {});
    } else if (msg.type === "state") {
      setPeerAV((prev) => ({ ...prev, [msg.from]: { muted: msg.muted, cameraOff: msg.cameraOff } }));
    } else if (msg.type === "slide") {
      setSlide(
        msg.clear
          ? null
          : { index: msg.index, total: msg.total, title: msg.title, text: msg.text, imageUrl: msg.image_url }
      );
    }
  }

  function connectSocket() {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onopen = () => send({ type: "join", room: roomId, id_token: identity.token });
    ws.onmessage = (event) => handleMessage(JSON.parse(event.data));
    ws.onclose = () => {
      if (leavingRef.current) return;
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setConnection("lost");
        return;
      }
      setConnection("reconnecting");
      const delay = 1000 * 2 ** reconnectAttemptsRef.current;
      reconnectAttemptsRef.current += 1;
      setTimeout(() => {
        if (!leavingRef.current) connectSocket();
      }, delay);
    };
    ws.onerror = () => ws.close();
  }

  useEffect(() => {
    connectSocket();
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);

    function handleUnload() {
      leavingRef.current = true;
      wsRef.current?.close();
    }
    window.addEventListener("beforeunload", handleUnload);

    return () => {
      clearInterval(timer);
      window.removeEventListener("beforeunload", handleUnload);
      leavingRef.current = true;
      wsRef.current?.close();
      pcsRef.current.forEach((pc) => pc.close());
      pcsRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleMic() {
    const next = !micOn;
    localStreamRef.current?.getAudioTracks().forEach((t) => (t.enabled = next));
    micOnRef.current = next;
    setMicOn(next);
    send({ type: "state", muted: !next, cameraOff: !camOnRef.current });
  }

  function toggleCam() {
    const next = !camOn;
    localStreamRef.current?.getVideoTracks().forEach((t) => (t.enabled = next));
    camOnRef.current = next;
    setCamOn(next);
    send({ type: "state", muted: !micOnRef.current, cameraOff: !next });
  }

  function leave() {
    leavingRef.current = true;
    wsRef.current?.close();
    pcsRef.current.forEach((pc) => pc.close());
    pcsRef.current.clear();
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    onLeave();
  }

  function sendChat(e) {
    e.preventDefault();
    const text = chatInput.trim();
    if (!text) return;
    // Don't echo locally — the server broadcasts chat to everyone including
    // the sender, so this bubble appears once that message comes back in.
    send({ type: "chat", text });
    setChatInput("");
  }

  function copyInvite() {
    const url = `${window.location.origin}/${roomId}`;
    navigator.clipboard?.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const hasAudioTrack = (localStreamRef.current?.getAudioTracks().length || 0) > 0;
  const hasVideoTrack = (localStreamRef.current?.getVideoTracks().length || 0) > 0;

  const tiles = [
    <VideoTile
      key="self"
      stream={localStreamRef.current}
      name={identity.name}
      picture={identity.picture}
      isSelf
      muted={!micOn}
      cameraOff={!camOn}
    />,
    ...peers.map((p) => (
      <VideoTile
        key={p.id}
        stream={remoteStreamsRef.current.get(p.id)}
        version={peerStreamsVersion}
        name={p.name}
        picture={p.picture}
        isBot={p.isBot}
        muted={peerAV[p.id]?.muted || false}
        cameraOff={peerAV[p.id]?.cameraOff || false}
      />
    )),
  ];

  return (
    <div className="call">
      <header className="call-top">
        <span className="call-room">
          {roomId} · {formatElapsed(elapsed)}
        </span>
        <button className="link-button" onClick={copyInvite}>
          <CopyIcon /> {copied ? "Copied!" : "Copy invite"}
        </button>
      </header>

      {connection === "reconnecting" && <div className="banner warn floating">Reconnecting…</div>}
      {connection === "lost" && <div className="banner error floating">Lost connection to the meeting.</div>}

      <div className="call-body">
        {slide ? (
          <div className="present-area">
            <SlidePanel slide={slide} />
            <div className="filmstrip">{tiles}</div>
          </div>
        ) : (
          <div className="video-grid">{tiles}</div>
        )}

        {panel && (
          <div className="side-panel">
            <div className="side-panel-header">
              <span>{panel === "chat" ? "In-call messages" : `People (${peers.length + 1})`}</span>
              <button className="icon-button" onClick={() => setPanel(null)}>
                <CloseIcon />
              </button>
            </div>
            {panel === "chat" ? (
              <>
                <div className="scroll-box">
                  {chat.length === 0 && <p className="muted">No messages yet.</p>}
                  {chat.map((m, i) => (
                    <div className="chat-line" key={i}>
                      <span className="sender">
                        {m.name}
                        {m.isSelf ? " (you)" : ""}:
                      </span>
                      {formatChatText(m.text)}
                    </div>
                  ))}
                </div>
                <form onSubmit={sendChat} className="chat-input-row">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder="Send a message to everyone"
                  />
                  <button type="submit">Send</button>
                </form>
              </>
            ) : (
              <div className="people-list">
                <div className="people-row">
                  <Avatar name={identity.name} picture={identity.picture} size={32} />
                  <span>{identity.name} (you)</span>
                </div>
                {peers.map((p) => (
                  <div className="people-row" key={p.id}>
                    <Avatar name={p.name} picture={p.picture} size={32} />
                    <span>
                      {p.name}
                      {p.isBot ? " \u{1F916}" : ""}
                    </span>
                    {peerAV[p.id]?.muted && <MicOffIcon />}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <footer className="call-controls">
        <button className={`pill-btn ${micOn ? "" : "off"}`} onClick={toggleMic} disabled={!hasAudioTrack} title="Toggle microphone">
          {micOn ? <MicIcon /> : <MicOffIcon />}
        </button>
        <button className={`pill-btn ${camOn ? "" : "off"}`} onClick={toggleCam} disabled={!hasVideoTrack} title="Toggle camera">
          {camOn ? <CamIcon /> : <CamOffIcon />}
        </button>
        <button className="pill-btn hangup" onClick={leave} title="Leave call">
          <HangupIcon />
        </button>
        <button className={`pill-btn ${panel === "chat" ? "active" : ""}`} onClick={() => setPanel(panel === "chat" ? null : "chat")} title="Chat">
          <ChatIcon />
        </button>
        <button className={`pill-btn ${panel === "people" ? "active" : ""}`} onClick={() => setPanel(panel === "people" ? null : "people")} title="People">
          <PeopleIcon />
        </button>
      </footer>
    </div>
  );
}
