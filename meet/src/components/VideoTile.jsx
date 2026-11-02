import { useEffect, useRef, useState } from "react";
import Avatar from "./Avatar.jsx";
import { MicOffIcon } from "../icons.jsx";

export default function VideoTile({ stream, name, picture, isSelf, muted, cameraOff, isBot, version }) {
  const videoRef = useRef(null);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream || null;
  }, [stream]);

  useEffect(() => {
    if (!stream || stream.getAudioTracks().length === 0) return;
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    let raf;
    let active = true;
    const tick = () => {
      if (!active) return;
      analyser.getByteFrequencyData(data);
      const avg = data.reduce((a, b) => a + b, 0) / data.length;
      setSpeaking(avg > 18 && !muted);
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      active = false;
      cancelAnimationFrame(raf);
      source.disconnect();
      ctx.close().catch(() => {});
    };
    // version bumps whenever a new track lands on this (mutable, same-reference) stream
  }, [stream, muted, version]);

  return (
    <div className={`video-tile ${speaking ? "speaking" : ""}`}>
      {!cameraOff && stream ? (
        <video ref={videoRef} autoPlay muted={isSelf} playsInline />
      ) : (
        <div className="avatar-wrap">
          <Avatar name={name} picture={picture} size={88} />
        </div>
      )}
      <div className="tile-footer">
        {muted && (
          <span className="mute-badge">
            <MicOffIcon />
          </span>
        )}
        <span className="video-label">
          {name}
          {isSelf ? " (you)" : ""}
          {isBot ? " \u{1F916}" : ""}
        </span>
      </div>
    </div>
  );
}
