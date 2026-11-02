import { useNavigate } from "react-router-dom";

export default function Ended({ onRejoin }) {
  const navigate = useNavigate();

  return (
    <div className="gate">
      <div className="gate-card">
        <div className="gate-logo">Meet</div>
        <h2>You left the meeting</h2>
        <div className="ended-actions">
          <button onClick={onRejoin}>Rejoin</button>
          <button className="secondary" onClick={() => navigate("/")}>
            Return to home screen
          </button>
        </div>
      </div>
    </div>
  );
}
