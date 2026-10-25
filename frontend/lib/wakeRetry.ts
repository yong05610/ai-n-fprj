import { MAX_WAIT_MS, SLOW_NOTICE_MS, nextAttemptDelayMs } from "@/lib/coldStart";

export type WakeDeps = {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  /** Runs `fn` after `ms`; returns a cancel function. */
  after: (ms: number, fn: () => void) => () => void;
  /** true: the server looks like it is waking up (show the notice); false: that is over. */
  onWaiting: (waiting: boolean) => void;
};

export const realWakeDeps = (onWaiting: (waiting: boolean) => void): WakeDeps => ({
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  after: (ms, fn) => {
    const timer = setTimeout(fn, ms);
    return () => clearTimeout(timer);
  },
  onWaiting,
});

/**
 * Runs a request again while the server wakes up (2s, 4s, 8s intervals, 90 seconds in all). The
 * notice is switched on when the request is still open after 8 seconds or fails the first time with a
 * wake-up failure, and off when it ends either way. A failure that is not a wake-up failure, or the
 * last one after 90 seconds, is thrown to the caller, so a screen can show an error and a retry button
 * instead of an empty state. Only used for requests that are safe to repeat.
 */
export async function retryWhileWaking<T>(run: () => Promise<T>, isWake: (error: unknown) => boolean, deps: WakeDeps): Promise<T> {
  const startedAt = deps.now();
  let waiting = false;
  const setWaiting = (value: boolean) => {
    if (waiting === value) return;
    waiting = value;
    deps.onWaiting(value);
  };
  const cancelSlow = deps.after(SLOW_NOTICE_MS, () => setWaiting(true));
  try {
    for (let failed = 0; ; failed++) {
      try {
        return await run();
      } catch (error) {
        if (!isWake(error)) throw error;
        setWaiting(true);
        const delay = nextAttemptDelayMs(failed + 1, deps.now() - startedAt);
        if (delay === null || deps.now() - startedAt >= MAX_WAIT_MS) throw error;
        await deps.sleep(delay);
      }
    }
  } finally {
    cancelSlow();
    setWaiting(false);
  }
}
