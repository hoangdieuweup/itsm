"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_CONFIG } from "@/shared/constants/api";
import { logEntrySchema, type LogEntry } from "../model/schema";

const MAX_BUFFERED_ENTRIES = 500;

interface ApiEnvelope {
  success: boolean;
  data?: unknown;
  error?: { code: string; message: string };
}

/**
 * Wraps native EventSource for the Loki live-tail SSE endpoint. No new
 * dependency — EventSource is a browser built-in, and this app already
 * authenticates via an httpOnly cookie (withCredentials sends it same-origin
 * automatically), so no auth header plumbing is needed here the way apiFetch
 * needs for REST calls.
 */
export function useLogTail(environmentId: string, query: string) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [isLive, setIsLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const stop = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    setIsLive(false);
  }, []);

  const start = useCallback(() => {
    setError(null);
    setEntries([]);
    const url = new URL(
      `${API_CONFIG.API_V1_URL}${API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_TAIL(environmentId)}`,
      window.location.origin,
    );
    url.searchParams.set("query", query);
    const source = new EventSource(url.toString(), { withCredentials: true });

    source.onmessage = (event) => {
      const envelope = JSON.parse(event.data) as ApiEnvelope;
      if (!envelope.success) {
        setError(envelope.error?.message ?? "Live tail failed");
        stop();
        return;
      }
      const entry = logEntrySchema.parse(envelope.data);
      setEntries((current) => [...current, entry].slice(-MAX_BUFFERED_ENTRIES));
    };

    source.onerror = () => {
      // EventSource auto-reconnects on a dropped connection by design —
      // only surface an error state, never stop() here, or a transient
      // network blip would silently end a session the user expects to
      // keep running until they explicitly pause it.
      setError("Connection interrupted — retrying...");
    };

    sourceRef.current = source;
    setIsLive(true);
  }, [environmentId, query, stop]);

  useEffect(() => stop, [stop]);

  return { entries, isLive, start, stop, error };
}
