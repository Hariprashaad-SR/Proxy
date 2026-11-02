import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";
import formatChatText from "../formatChatText.jsx";

const DONE_STATUSES = new Set(["completed", "failed"]);
const TABS = ["transcript", "chat", "q&a", "summary"];

export default function SessionDetail() {
  const { id } = useParams();
  const [session, setSession] = useState(null);
  const [tab, setTab] = useState("transcript");
  const [leaving, setLeaving] = useState(false);

  const load = () => api.getSession(id).then(setSession).catch(() => {});

  useEffect(() => {
    load();
    const interval = setInterval(() => {
      if (session && DONE_STATUSES.has(session.status)) return;
      load();
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, session?.status]);

  if (!session) return <p className="muted">Loading...</p>;

  async function handleLeave() {
    setLeaving(true);
    try {
      await api.leaveSession(id);
      load(); // reflect the "leaving" status right away instead of waiting on the next poll
    } catch {
      setLeaving(false); // only reset on an actual failure, so it can be retried
    }
  }

  const canLeave = !["completed", "failed", "leaving", "summarizing"].includes(session.status);

  return (
    <>
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1>
              <a href={session.meet_url} target="_blank" rel="noreferrer">
                {session.meet_url}
              </a>
            </h1>
            <p className="muted">
              {session.bot_name} · Created {new Date(session.created_at).toLocaleString()}
            </p>
          </div>
          <StatusBadge status={session.status} />
        </div>
        {session.error && <div className="error-banner">{session.error}</div>}
        {session.instructions && (
          <div className="instructions-box">
            <strong>Instructions given:</strong> {session.instructions}
          </div>
        )}
        {session.document_title && <p className="muted">📄 Presenting: {session.document_title}</p>}
        {session.participants?.length > 0 && (
          <p className="muted">Participants seen: {session.participants.join(", ")}</p>
        )}
        {canLeave && (
          <button className="danger" onClick={handleLeave} disabled={leaving}>
            {leaving ? "Leaving..." : "Leave meeting now"}
          </button>
        )}
      </div>

      <div className="panel">
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {t === "q&a" ? "Q&A" : t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {tab === "transcript" && (
          <div className="scroll-box">
            {session.transcript_entries.length === 0 && <p className="muted">No captions captured yet.</p>}
            {session.transcript_entries.map((e, i) => (
              <div className="transcript-line" key={i}>
                <span className="speaker">{e.speaker}</span>
                {e.text}
                <span className="time">{new Date(e.started_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}

        {tab === "chat" && (
          <div className="scroll-box">
            {session.chat_messages.length === 0 && <p className="muted">No chat messages yet.</p>}
            {session.chat_messages.map((m, i) => (
              <div className={`chat-line ${m.direction}`} key={i}>
                <span className="sender">{m.sender}:</span>
                {formatChatText(m.text)}
              </div>
            ))}
          </div>
        )}

        {tab === "q&a" && (
          <div className="scroll-box">
            {session.qa_exchanges.length === 0 && <p className="muted">Proxy hasn't been asked anything yet.</p>}
            {session.qa_exchanges.map((q, i) => (
              <div className="panel" key={i} style={{ marginBottom: 12 }}>
                <p className="muted">Addressed by {q.asked_by} via {q.source}</p>
                <p><strong>{q.question}</strong></p>
                <div>{formatChatText(q.answer)}</div>
              </div>
            ))}
          </div>
        )}

        {tab === "summary" && (
          <div className="summary-section">
            {!session.summary ? (
              <p className="muted">
                {session.status === "completed" ? "No summary was generated." : "Summary appears after the bot leaves."}
              </p>
            ) : (
              <p className="summary-text">{session.summary.summary}</p>
            )}
          </div>
        )}
      </div>
    </>
  );
}
