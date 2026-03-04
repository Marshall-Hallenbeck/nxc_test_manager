"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

export function useClaudeAvailability() {
  const [claudeAvailable, setClaudeAvailable] = useState(false);
  const [claudeUnavailableReason, setClaudeUnavailableReason] = useState("");

  useEffect(() => {
    api.getHealth().then((health) => {
      setClaudeAvailable(health.claude_available);
      if (!health.claude_available) {
        setClaudeUnavailableReason(health.claude_unavailable_reason);
      }
    }).catch((err) => {
      setClaudeUnavailableReason(`Health check failed: ${err instanceof Error ? err.message : err}`);
    });
  }, []);

  return { claudeAvailable, claudeUnavailableReason };
}
