import { useEffect, useState } from "react";

import { ApiError, getJob } from "../api";
import type { UiJob } from "../types";

const MAX_NETWORK_RETRIES = 5;

interface PollState {
  job: UiJob | null;
  error: ApiError | null;
}

/** Polls /ui/jobs/{id} every intervalMs until done/failed. Backs off on 429 and transient errors. */
export function useJobPolling(jobId: string, intervalMs: number): PollState {
  const [state, setState] = useState<PollState>({ job: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let failures = 0;

    const tick = async () => {
      let delay = intervalMs;
      try {
        const job = await getJob(jobId, controller.signal);
        failures = 0;
        setState({ job, error: null });
        if (job.status === "done" || job.status === "failed") return;
      } catch (err) {
        if (controller.signal.aborted) return;
        const apiErr = err instanceof ApiError ? err : new ApiError("network", 0, String(err));
        const transient = apiErr.status === 0 || apiErr.status === 429 || apiErr.status >= 500;
        failures += 1;
        if (!transient || failures > MAX_NETWORK_RETRIES) {
          setState((s) => ({ ...s, error: apiErr }));
          return;
        }
        delay = apiErr.retryAfterSec ? apiErr.retryAfterSec * 1000 : intervalMs * 2 ** failures;
      }
      timer = window.setTimeout(tick, delay);
    };

    setState({ job: null, error: null });
    void tick();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [jobId, intervalMs]);

  return state;
}
