import { useEffect, useRef, useState, useCallback } from "react";
import { LogEntry } from "@/types";

function getWsBase() {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}`;
  }
  return "ws://localhost:8080";
}

const WS_BASE = getWsBase();

interface WSMessage {
  type: "log" | "status" | "done" | "error";
  data?: Record<string, unknown>;
  message?: string;
}

export function useTestRunLogs(testRunId: number | null) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [status, setStatus] = useState<string>("");
  const [connected, setConnected] = useState(false);
  const [done, setDone] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (!testRunId) return;

    const ws = new WebSocket(`${WS_BASE}/ws/test-runs/${testRunId}/logs`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
    };

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);

      if (msg.type === "log" && msg.data) {
        setLogs((prev) => [
          ...prev,
          {
            id: msg.data!.id as number,
            timestamp: msg.data!.timestamp as string,
            log_line: msg.data!.log_line as string,
            level: msg.data!.level as string,
          },
        ]);
      } else if (msg.type === "status" && msg.data) {
        setStatus(msg.data.status as string);
      } else if (msg.type === "done") {
        setDone(true);
        setStatus(msg.data?.status as string || "done");
      }
    };
  }, [testRunId]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return { logs, status, connected, done };
}
