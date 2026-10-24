/**
 * Waking up a sleeping server (Phase 7). A free Render server sleeps after 15 minutes without
 * traffic and needs about a minute to answer again, so the app calls GET /health first and holds
 * back consent, login and every other request until it answers. Pure functions; the gate component
 * owns the timers and the fetch.
 */
export const SLOW_NOTICE_MS = 8_000;
export const MAX_WAIT_MS = 90_000;
export const ATTEMPT_TIMEOUT_MS = 15_000;
const RETRY_DELAYS_MS = [2_000, 4_000, 8_000];

export type ColdStartView = "loading" | "preparing" | "failed" | "ready";

export const PREPARING_MESSAGE = "서버를 준비하고 있습니다. 잠시만 기다려 주세요.";
export const FAILED_MESSAGE = "서버에 연결하지 못했어요.";

/** What the gate shows after `elapsedMs` of waiting: nothing special, the notice, the failure, or the app. */
export function coldStartView(elapsedMs: number, answered: boolean): ColdStartView {
  if (answered) return "ready";
  if (elapsedMs > MAX_WAIT_MS) return "failed";
  if (elapsedMs >= SLOW_NOTICE_MS) return "preparing";
  return "loading";
}

/** Wait before the next try after `failedAttempts` failures: 2s, 4s, 8s, then 8s again. */
export function retryDelayMs(failedAttempts: number): number {
  return RETRY_DELAYS_MS[Math.min(Math.max(failedAttempts, 1), RETRY_DELAYS_MS.length) - 1];
}

/**
 * Delay before the next try, or null when the 90 seconds are over. A delay that would run past the
 * limit is cut short, so the last try happens at the 90 second mark rather than being skipped.
 */
export function nextAttemptDelayMs(failedAttempts: number, elapsedMs: number): number | null {
  if (elapsedMs >= MAX_WAIT_MS) return null;
  return Math.min(retryDelayMs(failedAttempts), MAX_WAIT_MS - elapsedMs);
}

/** Time limit of one try: the usual limit, but never past the 90 seconds. */
export function attemptTimeoutMs(elapsedMs: number): number {
  return Math.max(1_000, Math.min(ATTEMPT_TIMEOUT_MS, MAX_WAIT_MS - elapsedMs));
}
