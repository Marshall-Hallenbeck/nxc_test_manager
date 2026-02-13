"use client";

import { useEffect, useRef, useState } from "react";
import { useTestRunLogs } from "@/lib/websocket";

const levelColors: Record<string, string> = {
  INFO: "text-gray-300",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  DEBUG: "text-gray-500",
};

export default function LogViewer({ testRunId }: { testRunId: number }) {
  const { logs, status, connected, done } = useTestRunLogs(testRunId);
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-400"}`}
          />
          {connected ? "Live" : done ? "Completed" : "Disconnected"}
        </div>
        <label className="flex items-center gap-1 text-sm text-[var(--muted)]">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Auto-scroll
        </label>
      </div>
      <div
        ref={containerRef}
        className="bg-gray-900 text-gray-100 rounded-lg p-4 font-mono text-sm h-[48rem] min-h-48 overflow-auto resize-y"
      >
        <div className="min-w-max">
          {logs.length === 0 && (
            <div className="text-gray-500">Waiting for logs...</div>
          )}
          {logs.map((log) => (
            <div key={log.id} className={`whitespace-nowrap ${levelColors[log.level] || "text-gray-300"}`}>
              <span className="text-gray-500 mr-2">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              {log.log_line}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
