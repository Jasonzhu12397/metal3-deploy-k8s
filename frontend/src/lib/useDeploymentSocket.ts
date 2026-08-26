import { useEffect, useRef, useState } from "react";
import type { DeploymentProgressEvent } from "./types";
import { clearSession, getToken, UNAUTHORIZED_EVENT } from "./tokenStore";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/^http/, "ws") || "";

/** Subscribes to /api/v1/deployments/{id}/ws and accumulates the phase
 * events it receives, so a deployment detail page can render a live
 * timeline without polling. Falls back to nothing if the id is empty. */
export function useDeploymentSocket(deploymentId: string | undefined) {
  const [events, setEvents] = useState<DeploymentProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!deploymentId) return;
    setEvents([]);

    const base = WS_BASE || `${window.location.origin.replace(/^http/, "ws")}`;
    // Browsers can't set an Authorization header on a WebSocket handshake,
    // so the token travels as a query param instead -- the backend's
    // ws_router checks it manually (see decode_token_for_websocket).
    const token = getToken();
    const url = `${base}/api/v1/deployments/${deploymentId}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = (event) => {
      setConnected(false);
      // 4401 is this backend's custom close code for "token missing or
      // invalid" (see decode_token_for_websocket on the server side) --
      // treat it the same as an HTTP 401 so the whole app drops back to
      // the login screen instead of just silently sitting disconnected.
      if (event.code === 4401) {
        clearSession();
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      }
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

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [deploymentId]);

  return { events, connected };
}
