"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PasswordLoginForm, PasswordRegisterForm } from "@/components/PasswordForms";
import { usePasswordLoginEnabled } from "@/components/ServerGate";
import { requestIdFor } from "@/lib/adminLabels";
import { ApiError, apiRequest } from "@/lib/api";
import {
  LOGOUT_CONFIRM_TEXT,
  SWITCH_WARNING_NO_PASSWORD,
  SWITCH_WARNING_WITH_PASSWORD,
  formatSetAt,
} from "@/lib/passwordLogin";

export type PasswordPanel = "none" | "change" | "disable" | "logout" | "switch-warning" | "switch-login";

type ViewProps = {
  registered: boolean;
  setAt: string | null;
  panel: PasswordPanel;
  busy: boolean;
  message: string | null;
  onOpen: (panel: PasswordPanel) => void;
  onRegister: (password: string) => Promise<void>;
  onDisable: () => void;
  onLogout: () => void;
  onSwitchLogin: (password: string) => Promise<void>;
};

function ConfirmDialog({
  id,
  title,
  text,
  confirmLabel,
  busy,
  danger,
  onConfirm,
  onCancel,
}: {
  id: string;
  title: string;
  text: string;
  confirmLabel: string;
  busy: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby={id}>
      <section className="modal">
        <h2 id={id}>{title}</h2>
        <p>{text}</p>
        <div className="modal-actions">
          <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>
            취소
          </button>
          <button type="button" className={`btn${danger ? " danger" : ""}`} onClick={onConfirm} disabled={busy}>
            {busy ? "처리하는 중…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

/** The "다른 기기에서 이어 쓰기" card without any data access, so it can be rendered and tested on its own. */
export function PasswordCardView(props: ViewProps) {
  const { registered, setAt, panel, busy, message, onOpen } = props;
  return (
    <section className="card" id="password-card" style={{ marginTop: 13 }}>
      <h2>다른 기기에서 이어 쓰기</h2>
      <p className="small muted">
        암호를 등록하면 다른 PC·휴대폰에서 암호만으로 이 학습 기록을 이어 쓸 수 있어요.
      </p>

      {!registered && <PasswordRegisterForm submitLabel="등록" busyLabel="등록하는 중…" onSubmit={props.onRegister} />}

      {registered && (
        <>
          <p className="small" role="status" style={{ color: "#248160", fontWeight: 800 }}>
            등록됨{formatSetAt(setAt) ? ` (${formatSetAt(setAt)})` : ""}
          </p>
          {panel === "change" ? (
            <PasswordRegisterForm
              submitLabel="암호 바꾸기"
              busyLabel="바꾸는 중…"
              onSubmit={props.onRegister}
              onCancel={() => onOpen("none")}
            />
          ) : (
            <div className="modal-actions" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
              <button type="button" className="btn secondary" onClick={() => onOpen("change")}>
                암호 바꾸기
              </button>
              <button type="button" className="btn danger" onClick={() => onOpen("disable")}>
                암호 로그인 끄기
              </button>
              <button type="button" className="btn secondary" onClick={() => onOpen("logout")}>
                로그아웃
              </button>
            </div>
          )}
        </>
      )}

      {message && (
        <p className="error" role="alert">
          {message}
        </p>
      )}

      <p className="small" style={{ marginTop: 12 }}>
        <button type="button" className="link-btn" onClick={() => onOpen("switch-warning")}>
          다른 기기에서 등록한 암호로 로그인
        </button>
      </p>

      {panel === "disable" && (
        <ConfirmDialog
          id="pw-disable-title"
          title="암호 로그인을 끌까요?"
          text="끄면 이 암호로는 더 이상 들어올 수 없어요. 이 기기에서 쓰던 기록은 그대로예요."
          confirmLabel="끄기"
          danger
          busy={busy}
          onConfirm={props.onDisable}
          onCancel={() => onOpen("none")}
        />
      )}
      {panel === "logout" && (
        <ConfirmDialog
          id="pw-logout-title"
          title="로그아웃할까요?"
          text={LOGOUT_CONFIRM_TEXT}
          confirmLabel="로그아웃"
          busy={busy}
          onConfirm={props.onLogout}
          onCancel={() => onOpen("none")}
        />
      )}
      {panel === "switch-warning" && (
        <ConfirmDialog
          id="pw-switch-title"
          title="다른 학습 기록으로 들어갈까요?"
          text={registered ? SWITCH_WARNING_WITH_PASSWORD : SWITCH_WARNING_NO_PASSWORD}
          confirmLabel="계속"
          busy={busy}
          onConfirm={() => onOpen("switch-login")}
          onCancel={() => onOpen("none")}
        />
      )}
      {panel === "switch-login" && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="pw-switch-login-title">
          <section className="modal">
            <h2 id="pw-switch-login-title">등록한 암호로 로그인</h2>
            <p>두 기록을 합치지 않아요. 로그인하면 이 기기는 그 기록으로 바뀌어요.</p>
            <PasswordLoginForm onSubmit={props.onSwitchLogin} onCancel={() => onOpen("none")} />
          </section>
        </div>
      )}
    </section>
  );
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `pw-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

type Profile = { password_enabled?: boolean; password_set_at?: string | null };

/** Settings card (CR-005). Not rendered at all unless the server says password login is on. */
export function PasswordCard() {
  return usePasswordLoginEnabled() ? <LoadedPasswordCard /> : null;
}

function LoadedPasswordCard() {
  const { session, loginWithPassword, logout } = useAuth();
  const [loaded, setLoaded] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [setAt, setSetAt] = useState<string | null>(null);
  const [panel, setPanel] = useState<PasswordPanel>("none");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const request = useRef<{ key: string; requestId: string } | null>(null);

  const uid = session?.uid;
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    (async () => {
      try {
        const profile = await apiRequest<Profile>("/api/user/profile", { token: await session.getToken() });
        if (cancelled) return;
        setRegistered(profile.password_enabled === true);
        setSetAt(profile.password_set_at ?? null);
        setLoaded(true);
      } catch {
        if (!cancelled) setLoaded(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);

  if (!session || !loaded) return null;

  async function register(password: string) {
    // The same password keeps the same client_request_id, so pressing again after a lost answer repeats the same request.
    request.current = requestIdFor(request.current, password, newId);
    const result = await apiRequest<Profile>("/api/auth/password", {
      method: "POST",
      token: await session!.getToken(),
      body: { password, client_request_id: request.current.requestId },
    });
    request.current = null;
    setRegistered(result.password_enabled === true);
    setSetAt(result.password_set_at ?? null);
    setPanel("none");
    setMessage(null);
  }

  async function disable() {
    setBusy(true);
    try {
      await apiRequest("/api/auth/password", { method: "DELETE", token: await session!.getToken() });
      setRegistered(false);
      setSetAt(null);
      setPanel("none");
      setMessage(null);
    } catch (e) {
      setPanel("none");
      setMessage(e instanceof ApiError ? e.message : "끄지 못했어요. 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  async function doLogout() {
    setBusy(true);
    try {
      await logout();
    } finally {
      setBusy(false);
    }
  }

  async function switchLogin(password: string) {
    await loginWithPassword(password);
    // A different record: reload so every screen starts clean with the new session.
    window.location.hash = "#dashboard";
    window.location.reload();
  }

  return (
    <PasswordCardView
      registered={registered}
      setAt={setAt}
      panel={panel}
      busy={busy}
      message={message}
      onOpen={(next) => {
        setMessage(null);
        setPanel(next);
      }}
      onRegister={register}
      onDisable={disable}
      onLogout={doLogout}
      onSwitchLogin={switchLogin}
    />
  );
}
