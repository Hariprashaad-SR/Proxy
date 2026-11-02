import { useEffect } from "react";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { Route, Routes } from "react-router-dom";
import Nav from "./components/Nav.jsx";
import SignInGate from "./components/SignInGate.jsx";
import NewRequest from "./pages/NewRequest.jsx";
import History from "./pages/History.jsx";
import SessionDetail from "./pages/SessionDetail.jsx";
import { useIdentity } from "./useIdentity.js";
import { setAuthToken } from "./api.js";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

function Console({ identity, signOut }) {
  useEffect(() => {
    setAuthToken(identity.token);
  }, [identity.token]);

  return (
    <div className="layout">
      <Nav identity={identity} signOut={signOut} />
      <Routes>
        <Route path="/" element={<NewRequest />} />
        <Route path="/history" element={<History />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
      </Routes>
    </div>
  );
}

export default function App() {
  const { identity, signIn, signOut } = useIdentity();

  return (
    <GoogleOAuthProvider clientId={CLIENT_ID}>
      {identity ? <Console identity={identity} signOut={signOut} /> : <SignInGate onSuccess={signIn} />}
    </GoogleOAuthProvider>
  );
}
