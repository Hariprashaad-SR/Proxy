const COLORS = ["#1a73e8", "#d93025", "#188038", "#e37400", "#9334e6", "#007b83"];

function colorFor(seed) {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[hash % COLORS.length];
}

export default function Avatar({ name, picture, size = 72 }) {
  if (picture) {
    return (
      <img
        className="avatar"
        src={picture}
        alt={name}
        referrerPolicy="no-referrer"
        style={{ width: size, height: size }}
      />
    );
  }
  const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
  return (
    <div
      className="avatar avatar-fallback"
      style={{ width: size, height: size, fontSize: size * 0.42, background: colorFor(name || "?") }}
    >
      {initial}
    </div>
  );
}
