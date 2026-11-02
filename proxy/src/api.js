const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

let authToken = null;

export function setAuthToken(token) {
  authToken = token;
}

async function request(path, options = {}) {
  const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  getStatus: () => request("/api/status"),

  listSessions: () => request("/api/sessions"),
  getSession: (id) => request(`/api/sessions/${id}`),
  createSession: (payload) => request("/api/sessions", { method: "POST", body: JSON.stringify(payload) }),
  leaveSession: (id) => request(`/api/sessions/${id}/leave`, { method: "POST" }),

  uploadDocument: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/documents", { method: "POST", body: form });
  },
};
