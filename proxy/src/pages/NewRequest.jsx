import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function NewRequest() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);

  const [meetUrl, setMeetUrl] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [instructions, setInstructions] = useState("");
  const [attachedDoc, setAttachedDoc] = useState(null); // {id, title, page_count} once uploaded
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => {});
  }, []);

  async function handleFilePicked(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const doc = await api.uploadDocument(file);
      setAttachedDoc({ id: doc.id, title: doc.title, page_count: doc.page_count });
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const session = await api.createSession({
        meet_url: meetUrl.trim(),
        recipient_email: recipientEmail.trim() || undefined,
        instructions: instructions.trim(),
        document_id: attachedDoc?.id || undefined,
      });
      navigate(`/sessions/${session.id}`);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <>
      {status && status.missing_settings.length > 0 && (
        <div className="error-banner">
          Missing settings: {status.missing_settings.join(", ")}. Fill these into .env.
        </div>
      )}

      <div className="panel">
        <h2>New request</h2>
        <p className="muted">
          Paste the link to a meeting already running in Meet — Proxy AI joins it as a real participant
          through the backend, not a browser.
        </p>
        <form className="request-form" onSubmit={handleSubmit}>
          <h3>Meeting</h3>
          <div className="field">
            <label>Meet link</label>
            <input
              placeholder="http://localhost:5174/abc-defg-hij"
              value={meetUrl}
              onChange={(e) => setMeetUrl(e.target.value)}
              required
            />
          </div>

          <h3>Instructions</h3>
          <div className="field">
            <label>What should Proxy AI do, and what should it record?</label>
            <textarea
              placeholder={
                'e.g. "Listen for questions about the Q3 roadmap and answer them. At the end, record every ' +
                'action item and who owns it, plus any open questions nobody answered."'
              }
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={5}
              required
            />
          </div>

          <h3>Document (optional)</h3>
          <p className="muted" style={{ marginTop: -6, marginBottom: 10 }}>
            Attach a document and Proxy AI will walk through it slide-by-slide in the meeting right after
            joining, narrating a summary of each page in chat as it goes. It's only used for this one
            request — nothing is kept afterward, so there's nothing to manage or clean up.
          </p>
          {attachedDoc ? (
            <div className="doc-chip">
              <span>
                📄 {attachedDoc.title}
                {attachedDoc.page_count ? ` · ${attachedDoc.page_count} slide${attachedDoc.page_count === 1 ? "" : "s"}` : ""}
              </span>
              <button type="button" className="link-button" onClick={() => setAttachedDoc(null)}>
                Remove
              </button>
            </div>
          ) : (
            <div className="field">
              <input type="file" accept=".txt,.md,.pdf" onChange={handleFilePicked} disabled={uploading} />
              {uploading && <p className="muted">Uploading…</p>}
            </div>
          )}

          <h3>Delivery</h3>
          <div className="field">
            <label>Summary email recipient (optional, defaults to your account)</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
            />
          </div>

          {error && <div className="error-banner">{error}</div>}
          <button type="submit" disabled={submitting || uploading}>
            {submitting ? "Sending..." : "Send the bot"}
          </button>
        </form>
      </div>
    </>
  );
}
