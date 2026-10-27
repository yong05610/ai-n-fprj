"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { API_BASE_URL, API_CONFIG_PROBLEM } from "@/lib/api";
import {
  FAILED_MESSAGE,
  PREPARING_MESSAGE,
  attemptTimeoutMs,
  coldStartView,
  nextAttemptDelayMs,
} from "@/lib/coldStart";
import { API_CONFIG_MESSAGES } from "@/lib/deployConfig";
import { type HealthModes, parseHealth, parsePasswordLoginFlag } from "@/lib/modeBanner";

/** The two mode names the server answered with at start-up (null when the body was not recognised). */
const HealthContext = createContext<HealthModes | null>(null);

export function useServerModes(): HealthModes | null {
  return useContext(HealthContext);
}

/** CR-005: the server decides whether the password-login card and links exist (no extra frontend setting). */
const PasswordLoginContext = createContext<boolean>(false);

export function usePasswordLoginEnabled(): boolean {
  return useContext(PasswordLoginContext);
}

type Answer = { modes: HealthModes | null; passwordLogin: boolean } | null;

/**
 * Wakes the server before the app starts: GET /health first, retried at 2s, 4s, 8s intervals for up
 * to 90 seconds. Consent, login and every other API call wait behind this gate. After 8 seconds a
 * notice says the server is getting ready; after 90 it offers a retry. A production build without a
 * usable API address shows the setting error here and sends nothing.
 */
export function ServerGate({ children }: { children: React.ReactNode }) {
  const [answer, setAnswer] = useState<Answer>(null);
  const [elapsed, setElapsed] = useState(0);
  const [gaveUp, setGaveUp] = useState(false);
  const [run, setRun] = useState(0); // a new run = the retry button was pressed

  useEffect(() => {
    if (API_CONFIG_PROBLEM) return;
    let cancelled = false;
    const startedAt = Date.now();
    const controllers = new Set<AbortController>();
    let sleepTimer: ReturnType<typeof setTimeout> | undefined;
    setAnswer(null);
    setGaveUp(false);
    setElapsed(0);
    const tick = setInterval(() => setElapsed(Date.now() - startedAt), 500);

    const tryOnce = async (failed: number) => {
      const controller = new AbortController();
      controllers.add(controller);
      const timer = setTimeout(() => controller.abort(), attemptTimeoutMs(Date.now() - startedAt));
      try {
        const response = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
        if (response.ok) {
          const body = await response.json().catch(() => null);
          if (!cancelled) setAnswer({ modes: parseHealth(body), passwordLogin: parsePasswordLoginFlag(body) });
          return;
        }
      } catch {
        // no answer yet: the server may still be waking up
      } finally {
        clearTimeout(timer);
        controllers.delete(controller);
      }
      if (cancelled) return;
      const delay = nextAttemptDelayMs(failed + 1, Date.now() - startedAt);
      if (delay === null) {
        setGaveUp(true);
        return;
      }
      sleepTimer = setTimeout(() => void tryOnce(failed + 1), delay);
    };
    void tryOnce(0);

    return () => {
      cancelled = true;
      clearInterval(tick);
      if (sleepTimer) clearTimeout(sleepTimer);
      controllers.forEach((c) => c.abort());
    };
  }, [run]);

  if (API_CONFIG_PROBLEM) {
    return (
      <main className="gate">
        <section className="card">
          <p className="eyebrow">PACEMATE · MVP</p>
          <h1>설정을 확인해 주세요</h1>
          <p className="error" role="alert">
            {API_CONFIG_MESSAGES[API_CONFIG_PROBLEM]}
          </p>
        </section>
      </main>
    );
  }

  const view = gaveUp ? "failed" : coldStartView(elapsed, answer !== null);
  if (view === "ready") {
    return (
      <HealthContext.Provider value={answer?.modes ?? null}>
        <PasswordLoginContext.Provider value={answer?.passwordLogin ?? false}>{children}</PasswordLoginContext.Provider>
      </HealthContext.Provider>
    );
  }

  return (
    <>
      {view === "preparing" && (
        <div className="mode-banner server-notice" role="status">
          <span>{PREPARING_MESSAGE}</span>
        </div>
      )}
      <main className="gate">
        {view === "failed" ? (
          <section className="card">
            <p className="eyebrow">PACEMATE · MVP</p>
            <h1>{FAILED_MESSAGE}</h1>
            <p className="description">서버가 아직 깨어나지 않았거나 인터넷 연결에 문제가 있을 수 있어요. 아무 데이터도 보내지 않았어요.</p>
            <button className="btn" onClick={() => setRun((n) => n + 1)}>
              다시 시도
            </button>
          </section>
        ) : (
          <p className="description">불러오는 중…</p>
        )}
      </main>
    </>
  );
}
