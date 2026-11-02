import { useCallback, useState } from "react";
import { clearIdToken, decodeJwt, getStoredIdentity, storeIdToken } from "./auth.js";

export function useIdentity() {
  const [identity, setIdentity] = useState(() => getStoredIdentity());

  const signIn = useCallback((credentialResponse) => {
    const token = credentialResponse.credential;
    if (!token) return;
    storeIdToken(token);
    const claims = decodeJwt(token);
    setIdentity({ token, name: claims?.name || "Guest", email: claims?.email, picture: claims?.picture });
  }, []);

  const signOut = useCallback(() => {
    clearIdToken();
    setIdentity(null);
  }, []);

  return { identity, signIn, signOut };
}
