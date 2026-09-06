import { useEffect, useState } from "react";
import type { DeploymentProgressEvent } from "./types";
import { clearSession, getToken, UNAUTHORIZED_EVENT } from "./tokenStore";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/^http/, "ws") || "";
// Deployments can run for many minutes (waiting on hosts, waiting on the
// control plane...) -- a transient network blip or an intermediate
// proxy's idle timeout shouldn't force a manual page refresh to see
// progress again. Capped, not infinite: a real auth failure (4401) or a
// deployment that's actually gone shouldn't retry forever either.
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 10;

/** Subscribes to /api/v1/deployments/{id}/ws and accumulates the phase
 * events it receives, so a deployment detail page can render a live
 * timeline without polling. Falls back to nothing if the id is empty.
 * Automatically reconnects (with a fixed delay, capped attempts) on an
 * unexpected close -- never on the 4401 "token missing or invalid"
 * close code, which means retrying with the same token would just fail
 * the same way forever. */
export function useDeploymentSocket(deploymentId: string | undefined) {
  const [events, setEvents] = useState<DeploymentProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!deploymentId) return;
    setEvents([]);

    let cancelled = false;
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let ws: WebSocket | undefined;

    const connect = () => {
      const base = WS_BASE || `${window.location.origin.replace(/^http/, "ws")}`;
      // Browsers can't set an Authorization header on a WebSocket handshake,
      // so the token travels as a query param instead -- the backend's
      // ws_router checks it manually (see decode_token_for_websocket).
      const token = getToken();
      const url = `${base}/api/v1/deployments/${deploymentId}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
      ws = new WebSocket(url);

      ws.onopen = () => {
        reconnectAttempts = 0;
        setConnected(true);
      };
      ws.onclose = (event) => {
        setConnected(false);
        // 4401 is this backend's custom close code for "token missing or
        // invalid" (see decode_token_for_websocket on the server side) --
        // treat it the same as an HTTP 401 so the whole app drops back to
        // the login screen instead of endlessly retrying with a token
        // that will never become valid.
        if (event.code === 4401) {
          clearSession();
          window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
          return;
        }
        if (cancelled || reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;
        reconnectAttempts += 1;
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
      ws.onerror = () => setConnected(false);
      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as DeploymentProgressEvent;
          setEvents((prev) => [...prev, event]);
        } catch {
          /* ignore malformed frame */
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [deploymentId]);

  return { events, connected };
}

