import { useState } from "react";
import { useParams } from "react-router-dom";
import SignInGate from "../components/SignInGate.jsx";
import Lobby from "../components/Lobby.jsx";
import Call from "../components/Call.jsx";
import Ended from "../components/Ended.jsx";
import { useIdentity } from "../useIdentity.js";

export default function Room() {
  const { roomId } = useParams();
  const { identity, signIn } = useIdentity();
  const [phase, setPhase] = useState("lobby"); // lobby | call | ended
  const [joinConfig, setJoinConfig] = useState(null);

  if (!identity) return <SignInGate onSuccess={signIn} />;

  if (phase === "call" && joinConfig) {
    return (
      <Call
        roomId={roomId}
        identity={identity}
        initial={joinConfig}
        onLeave={() => setPhase("ended")}
      />
    );
  }

  if (phase === "ended") {
    return <Ended onRejoin={() => setPhase("lobby")} />;
  }

  return (
    <Lobby
      roomId={roomId}
      identity={identity}
      onJoin={(cfg) => {
        setJoinConfig(cfg);
        setPhase("call");
      }}
    />
  );
}
