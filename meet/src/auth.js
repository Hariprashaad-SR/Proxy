const STORAGE_KEY = "meet_id_token";

export function decodeJwt(token) {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decodeURIComponent(escape(json)));
  } catch {
    return null;
  }
}

export function getStoredIdentity() {
  const token = localStorage.getItem(STORAGE_KEY);
  if (!token) return null;
  const claims = decodeJwt(token);
  if (!claims || !claims.exp || claims.exp * 1000 < Date.now()) {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
  return { token, name: claims.name, email: claims.email, picture: claims.picture };
}

export function storeIdToken(token) {
  localStorage.setItem(STORAGE_KEY, token);
}

export function clearIdToken() {
  localStorage.removeItem(STORAGE_KEY);
}
