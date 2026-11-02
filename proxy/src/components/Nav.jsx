import { NavLink } from "react-router-dom";

export default function Nav({ identity, signOut }) {
  return (
    <div className="nav">
      <span className="brand">Proxy</span>
      <NavLink to="/" className={({ isActive }) => `navlink${isActive ? " active" : ""}`} end>
        New
      </NavLink>
      <NavLink to="/history" className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
        History
      </NavLink>
      {identity && (
        <div className="account-chip">
          {identity.picture && <img className="avatar-small" src={identity.picture} alt={identity.name} referrerPolicy="no-referrer" />}
          <span>{identity.name}</span>
          <button className="link-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
