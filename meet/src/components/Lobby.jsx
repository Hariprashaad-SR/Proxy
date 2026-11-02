import { useEffect, useRef, useState } from "react";
import Avatar from "./Avatar.jsx";
import { CamIcon, CamOffIcon, MicIcon, MicOffIcon } from "../icons.jsx";

async function acquireMedia() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    return { stream, micOn: true, camOn: true, error: null };
  } catch {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      return { stream, micOn: true, camOn: false, error: "camera" };
    } catch {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        return { stream, micOn: false, camOn: true, error: "mic" };
      } catch {
        return { stream: null, micOn: false, camOn: false, error: "both" };
      }
    }
  }
}

export default function Lobby({ roomId, identity, onJoin }) {
  const [state, setState] = useState({ stream: null, micOn: false, camOn: false, error: null, loading: true });
  const videoRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    acquireMedia().then((result) => {
      if (cancelled) {
        result.stream?.getTracks().forEach((t) => t.stop());
        return;
      }
      setState({ ...result, loading: false });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = state.stream;
  }, [state.stream]);

  function toggleMic() {
    if (!state.stream || state.stream.getAudioTracks().length === 0) return;
    const next = !state.micOn;
    state.stream.getAudioTracks().forEach((t) => (t.enabled = next));
    setState((s) => ({ ...s, micOn: next }));
  }

  function toggleCam() {
    if (!state.stream || state.stream.getVideoTracks().length === 0) return;
    const next = !state.camOn;
    state.stream.getVideoTracks().forEach((t) => (t.enabled = next));
    setState((s) => ({ ...s, camOn: next }));
  }

  return (
    <div className="lobby">
      <div className="lobby-preview">
        <div className="video-tile large">
          {state.camOn && state.stream ? (
            <video ref={videoRef} autoPlay muted playsInline />
          ) : (
            <div className="avatar-wrap">
              <Avatar name={identity.name} picture={identity.picture} size={96} />
            </div>
          )}
          {state.stream && (
            <div className="tile-controls">
              <button
                className={`pill-btn ${state.micOn ? "" : "off"}`}
                onClick={toggleMic}
                title="Toggle microphone"
                disabled={state.stream.getAudioTracks().length === 0}
              >
                {state.micOn ? <MicIcon /> : <MicOffIcon />}
              </button>
              <button
                className={`pill-btn ${state.camOn ? "" : "off"}`}
                onClick={toggleCam}
                title="Toggle camera"
                disabled={state.stream.getVideoTracks().length === 0}
              >
                {state.camOn ? <CamIcon /> : <CamOffIcon />}
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="lobby-side">
        <h2>Ready to join?</h2>
        <p className="muted">Room {roomId}</p>
        {state.loading && <p className="muted">Checking camera and microphone…</p>}
        {state.error === "camera" && (
          <div className="banner warn">Camera unavailable — you'll join with audio only.</div>
        )}
        {state.error === "mic" && <div className="banner warn">Microphone unavailable — you'll join with video only.</div>}
        {state.error === "both" && (
          <div className="banner warn">No camera or microphone access — you can still join and watch/listen.</div>
        )}
        <button disabled={state.loading} onClick={() => onJoin({ stream: state.stream, micOn: state.micOn, camOn: state.camOn })}>
          Join now
        </button>
        <p className="muted small">Signed in as {identity.name}</p>
      </div>
    </div>
  );
}
