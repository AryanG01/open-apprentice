import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, get } from "./api";
import { accept } from "./session";
import { TERMINAL, type SessionState } from "./types";

const POLL_MS = 2000;

/** Polls GET /sessions/{sid} every 2 s until the session ends; stale responses never replace newer state. */
export function useSession(sid: string | null): { state: SessionState | null; error: string | null; refresh: () => void } {
  const [state, setState] = useState<SessionState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const latest = useRef<SessionState | null>(null);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    latest.current = null;
    setState(null);
    setError(null);
  }, [sid]);

  useEffect(() => {
    if (!sid) return;
    const ctl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await get<SessionState>(`/sessions/${sid}`, ctl.signal);
        const merged = accept(latest.current, next);
        latest.current = merged;
        setState(merged);
        setError(null);
        if (!TERMINAL.has(merged.state)) timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof ApiError ? e.message : String(e));
        timer = setTimeout(poll, POLL_MS);
      }
    };
    void poll();
    return () => {
      ctl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [sid, tick]);

  return { state, error, refresh };
}
