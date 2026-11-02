const base = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "currentColor" };

export function MicIcon() {
  return (
    <svg {...base}>
      <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
      <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.93V20H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-2.07A7 7 0 0 0 19 11Z" />
    </svg>
  );
}

export function MicOffIcon() {
  return (
    <svg {...base}>
      <path d="M19 11a1 1 0 1 0-2 0c0 .78-.15 1.52-.42 2.2l1.45 1.45A6.96 6.96 0 0 0 19 11Z" />
      <path d="M15 11V6a3 3 0 0 0-5.91-.72l4.3 4.3A3 3 0 0 0 15 11Z" />
      <path d="M9 11V8.83l-2-2V11a5 5 0 0 0 7.1 4.52l1.49 1.49A6.97 6.97 0 0 1 12 17.93V20h2a1 1 0 1 1 0 2H9a1 1 0 1 1 0-2h2v-2.07A7.01 7.01 0 0 1 5 11a1 1 0 1 1 2 0 5 5 0 0 0 2 4Z" />
      <path d="M3.7 2.29a1 1 0 0 0-1.41 1.42l18 18a1 1 0 0 0 1.42-1.42l-18-18Z" />
    </svg>
  );
}

export function CamIcon() {
  return (
    <svg {...base}>
      <path d="M17 10.5V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3.5l4 4v-11l-4 4Z" />
    </svg>
  );
}

export function CamOffIcon() {
  return (
    <svg {...base}>
      <path d="M3.7 2.29a1 1 0 0 0-1.41 1.42l1.78 1.78A2 2 0 0 0 3 7v10a2 2 0 0 0 2 2h10a2 2 0 0 0 1.49-.67l2.8 2.8a1 1 0 0 0 1.42-1.42l-18-18Z" />
      <path d="m21 6.5-4 4V7a2 2 0 0 0-2-2H9.41l7.1 7.1V10.5l4 4v-8Z" />
    </svg>
  );
}

export function HangupIcon() {
  return (
    <svg {...base}>
      <path d="M12 9c-2.6 0-5.07.5-7.33 1.41a1.3 1.3 0 0 0-.67 1.76l1.2 2.6c.24.53.8.84 1.37.75a9.6 9.6 0 0 1 2.1-.2c.6 0 1.08.44 1.15 1.03l.25 2.06c.08.63.62 1.1 1.26 1.1h1.26c.64 0 1.18-.47 1.26-1.1l.25-2.06c.07-.6.55-1.03 1.15-1.03.7 0 1.4.07 2.1.2.56.09 1.13-.22 1.37-.75l1.2-2.6a1.3 1.3 0 0 0-.67-1.76A17.9 17.9 0 0 0 12 9Z" />
    </svg>
  );
}

export function ChatIcon() {
  return (
    <svg {...base}>
      <path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H8l-4.3 3.3A1 1 0 0 1 2 19.4V5a1 1 0 0 1 1-1Z" />
    </svg>
  );
}

export function PeopleIcon() {
  return (
    <svg {...base}>
      <path d="M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path d="M16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      <path d="M9 13c-3.3 0-6 1.6-6 3.6V19h12v-2.4c0-2-2.7-3.6-6-3.6Z" />
      <path d="M16.5 13.2c-.3 0-.6 0-.9.03.9.8 1.4 1.8 1.4 2.77V19H22v-2c0-1.8-2.3-3.3-5.5-3.8Z" />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg {...base} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function CopyIcon() {
  return (
    <svg {...base} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
    </svg>
  );
}
