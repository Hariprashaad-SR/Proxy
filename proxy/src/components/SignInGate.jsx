import { GoogleLogin } from "@react-oauth/google";

export default function SignInGate({ onSuccess }) {
  const configured = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);

  return (
    <div className="signin-gate">
      <div className="panel signin-card">
        <h1 className="brand">Proxy</h1>
        <p className="muted">Sign in with Google to send Proxy into meetings and see your session history.</p>
        {configured ? (
          <div className="signin-button">
            <GoogleLogin onSuccess={onSuccess} onError={() => {}} theme="filled_black" shape="pill" size="large" text="signin_with" />
          </div>
        ) : (
          <div className="error-banner">VITE_GOOGLE_CLIENT_ID isn't set — add it to proxy/.env.</div>
        )}
      </div>
    </div>
  );
}
