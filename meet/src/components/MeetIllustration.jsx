export default function MeetIllustration() {
  return (
    <svg viewBox="0 0 420 340" className="meet-illustration" aria-hidden="true">
      <rect x="40" y="30" width="300" height="220" rx="20" fill="#3c4043" />
      <rect x="60" y="50" width="260" height="180" rx="12" fill="#28292c" />

      {/* center participant */}
      <circle cx="190" cy="120" r="36" fill="#8ab4f8" />
      <path d="M140 210c0-32 22-48 50-48s50 16 50 48" fill="#8ab4f8" />

      {/* mic/cam pill under the main tile */}
      <rect x="150" y="196" width="80" height="26" rx="13" fill="#202124" opacity="0.6" />
      <circle cx="175" cy="209" r="6" fill="#e8eaed" />
      <circle cx="205" cy="209" r="6" fill="#e8eaed" />

      {/* floating participant tiles */}
      <g>
        <rect x="290" y="10" width="110" height="80" rx="14" fill="#28292c" stroke="#3c4043" strokeWidth="2" />
        <circle cx="345" cy="46" r="20" fill="#f28b82" />
      </g>
      <g>
        <rect x="10" y="190" width="110" height="80" rx="14" fill="#28292c" stroke="#3c4043" strokeWidth="2" />
        <circle cx="65" cy="226" r="20" fill="#81c995" />
      </g>
      <g>
        <rect x="300" y="210" width="90" height="70" rx="14" fill="#28292c" stroke="#3c4043" strokeWidth="2" />
        <circle cx="345" cy="241" r="17" fill="#fdd663" />
      </g>

      {/* decorative dots */}
      <circle cx="20" cy="70" r="6" fill="#8ab4f8" opacity="0.6" />
      <circle cx="400" cy="150" r="5" fill="#f28b82" opacity="0.6" />
      <circle cx="60" cy="300" r="5" fill="#fdd663" opacity="0.6" />
    </svg>
  );
}
