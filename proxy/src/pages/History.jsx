import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";

export default function History() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    const refresh = () => api.listSessions().then(setSessions).catch(() => {});
    refresh();
    const interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h2 style={{ margin: 0 }}>History</h2>
        <Link to="/">
          <button type="button">+ New request</button>
        </Link>
      </div>
      {sessions.length === 0 ? (
        <p className="muted">No sessions yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Meet link</th>
              <th>Document</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="clickable" onClick={() => navigate(`/sessions/${s.id}`)}>
                <td>
                  <a href={s.meet_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    {s.meet_url}
                  </a>
                </td>
                <td className="muted">{s.document_title || "—"}</td>
                <td><StatusBadge status={s.status} /></td>
                <td className="muted">{new Date(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
