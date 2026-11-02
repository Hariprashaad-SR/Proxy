import { useState } from "react";
import { useNavigate } from "react-router-dom";
import SignInGate from "../components/SignInGate.jsx";
import Avatar from "../components/Avatar.jsx";
import MeetIllustration from "../components/MeetIllustration.jsx";
import { useIdentity } from "../useIdentity.js";

const CODE_CHARS = "abcdefghijkmnpqrstuvwxyz23456789"; // skip ambiguous chars (l, 1, o, 0)

function randomRoomCode() {
  const part = (n) =>
    Array.from({ length: n }, () => CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)]).join("");
  return `${part(3)}-${part(4)}-${part(3)}`;
}

export default function Home() {
  const { identity, signIn, signOut } = useIdentity();
  const [joinCode, setJoinCode] = useState("");
  const navigate = useNavigate();

  if (!identity) return <SignInGate onSuccess={signIn} />;

  function newMeeting() {
    navigate(`/${randomRoomCode()}`);
  }

  function joinMeeting(e) {
    e.preventDefault();
    const code = joinCode.trim().toLowerCase().replace(/\s+/g, "");
    if (code) navigate(`/${code}`);
  }

  return (
    <div className="landing">
      <header className="landing-nav home-nav">
        <span className="brand">Meet</span>
        <div className="account-chip">
          <Avatar name={identity.name} picture={identity.picture} size={32} />
          <span>{identity.name}</span>
          <button className="link-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <main className="landing-hero">
        <div className="landing-copy">
          <h1>Video calls and meetings for everyone</h1>
          <p className="muted landing-sub">High-quality video meetings, now for everyone.</p>
          <div className="home-actions">
            <button onClick={newMeeting}>New meeting</button>
            <form onSubmit={joinMeeting} className="join-form">
              <input placeholder="Enter a code" value={joinCode} onChange={(e) => setJoinCode(e.target.value)} />
              <button type="submit" className="secondary" disabled={!joinCode.trim()}>
                Join
              </button>
            </form>
          </div>
        </div>

        <div className="landing-illustration">
          <MeetIllustration />
        </div>
      </main>
    </div>
  );
}
