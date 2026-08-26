// Shared by api.ts (reads the token on every request, needs no knowledge
// of React) and auth.tsx (the React context). Kept separate so neither
// module has to import the other -- api.ts calling into auth.tsx and
// auth.tsx calling into api.ts at the same time would be a circular
// import, which is fragile across dev/prod bundling.
const TOKEN_KEY = "metal3_console_token";
const USERNAME_KEY = "metal3_console_username";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function setSession(token: string, username: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

export const UNAUTHORIZED_EVENT = "metal3:unauthorized";
