"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ApiError, apiRequest } from "@/lib/api";
import { clearConsent, consentPayload, hasStoredConsent, storeConsent } from "@/lib/consent";
import { type Session, endSession, restoreSession, startAnonymousSession } from "@/lib/session";

export type AuthStatus = "checking" | "needs-consent" | "declined" | "starting" | "ready" | "error";

type AuthContextValue = {
  status: AuthStatus;
  session: Session | null;
  errorMessage: string | null;
  accept: () => Promise<void>;
  decline: () => void;
  reopenConsent: () => void;
  deleteAllData: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function recordConsent(session: Session) {
  await apiRequest("/api/consent", { method: "POST", body: consentPayload, token: await session.getToken() });
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [session, setSession] = useState<Session | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fail = (error: unknown) => {
    setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
    setStatus("error");
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // No UID is created here: an existing session is only restored if consent was already given.
      if (!hasStoredConsent()) {
        if (!cancelled) setStatus("needs-consent");
        return;
      }
      try {
        const current = await restoreSession();
        if (!current) {
          // The stored consent flag doesn't match any live session (e.g. IndexedDB was cleared).
          // Don't mint a new UID/consent record behind the user's back - send them back through the modal.
          clearConsent();
          if (!cancelled) setStatus("needs-consent");
          return;
        }
        try {
          await apiRequest("/api/user/profile", { token: await current.getToken() });
        } catch (error) {
          // Server-side consent missing (e.g. records deleted): re-record the consent already given.
          if (error instanceof ApiError && error.code === "CONSENT_REQUIRED") await recordConsent(current);
          else throw error;
        }
        if (!cancelled) {
          setSession(current);
          setStatus("ready");
        }
      } catch (error) {
        if (!cancelled) fail(error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const accept = useCallback(async () => {
    setStatus("starting");
    setErrorMessage(null);
    try {
      const current = (await restoreSession()) ?? (await startAnonymousSession());
      await recordConsent(current);
      storeConsent();
      setSession(current);
      setStatus("ready");
    } catch (error) {
      fail(error);
    }
  }, []);

  const decline = useCallback(() => setStatus("declined"), []);
  const reopenConsent = useCallback(() => setStatus("needs-consent"), []);

  const deleteAllData = useCallback(async () => {
    if (!session) return;
    await apiRequest("/api/user/delete-data", { method: "POST", token: await session.getToken() });
    clearConsent();
    await endSession().catch(() => undefined);
    setSession(null);
    setStatus("needs-consent");
  }, [session]);

  return (
    <AuthContext.Provider value={{ status, session, errorMessage, accept, decline, reopenConsent, deleteAllData }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
