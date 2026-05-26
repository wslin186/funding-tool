import { useEffect, useState } from "react";
import { api } from "./api";
import type { ApiError, HistoryTaskStatus, TaskStatus } from "./types";

export interface UseTaskPollResult {
  status: HistoryTaskStatus | null;
  error: ApiError | null;
}

const POLL_INTERVAL_MS = 2000;

function isTerminal(s: TaskStatus): boolean {
  return s === "done" || s === "failed";
}

/**
 * Polls GET /history/result/{taskId} every 2 seconds until the task reaches
 * a terminal status ("done" or "failed") or an API error occurs. Returns the
 * latest status snapshot and any terminal error.
 */
export function useTaskPoll(taskId: string | null): UseTaskPollResult {
  const [status, setStatus] = useState<HistoryTaskStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!taskId) {
      setStatus(null);
      setError(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      if (cancelled) return;
      const r = await api.get<HistoryTaskStatus>(
        `/history/result/${encodeURIComponent(taskId as string)}`,
      );
      if (cancelled) return;
      if (r.error) {
        setError(r.error);
        return; // stop polling on transport / server error
      }
      if (r.data) {
        setStatus(r.data);
        if (isTerminal(r.data.status)) return;
      }
      timer = setTimeout(() => {
        void tick();
      }, POLL_INTERVAL_MS);
    }

    setStatus(null);
    setError(null);
    void tick();

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [taskId]);

  return { status, error };
}
