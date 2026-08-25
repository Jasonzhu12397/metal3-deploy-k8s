import { useEffect, useRef, useState } from "react";
import type { DeploymentProgressEvent } from "./types";

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
    const url = `${base}/api/v1/deployments/${deploymentId}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
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
