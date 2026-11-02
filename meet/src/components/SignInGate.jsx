import { GoogleLogin } from "@react-oauth/google";
import MeetIllustration from "./MeetIllustration.jsx";

export default function SignInGate({ onSuccess }) {
  const configured = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);

  return (
    <div className="landing">
      <header className="landing-nav">
        <span className="brand">Meet</span>
      </header>

      <main className="landing-hero">
        <div className="landing-copy">
          <h1>Video calls and meetings for everyone</h1>
          <p className="muted landing-sub">
            Connect, collaborate, and celebrate from anywhere with Meet — sign in with Google to create or join a
            call.
          </p>
          {configured ? (
            <div className="landing-cta">
              <GoogleLogin onSuccess={onSuccess} onError={() => {}} theme="filled_black" shape="pill" size="large" text="signin_with" />
            </div>
          ) : (
            <div className="banner warn landing-cta">
              VITE_GOOGLE_CLIENT_ID isn't set — sign-in can't be shown until meet/.env has a real Google OAuth client
              ID.
            </div>
          )}
        </div>

        <div className="landing-illustration">
          <MeetIllustration />
        </div>
      </main>
    </div>
  );
}
