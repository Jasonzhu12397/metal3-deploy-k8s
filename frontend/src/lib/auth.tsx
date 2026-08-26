import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { clearSession, getStoredUsername, getToken, setSession, UNAUTHORIZED_EVENT } from "./tokenStore";

interface AuthContextValue {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getToken());
  const [username, setUsername] = useState<string | null>(() => getStoredUsername());

  useEffect(() => {
    // Any request() call that gets a 401 dispatches this so every tab/
    // component reacts (token expired, revoked, or just never valid) --
    // see api.ts's request().
    const onUnauthorized = () => {
      setToken(null);
      setUsername(null);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      username,
      isAuthenticated: !!token,
      login: async (u: string, p: string) => {
        const res = await api.auth.login(u, p);
        setSession(res.access_token, res.username);
        setToken(res.access_token);
        setUsername(res.username);
      },
      logout: () => {
        clearSession();
        setToken(null);
        setUsername(null);
      },
    }),
    [token, username],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
