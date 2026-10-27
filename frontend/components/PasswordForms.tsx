"use client";

import { useState } from "react";

import {
  ACKNOWLEDGE_TEXT,
  passwordChecks,
  passwordErrorMessage,
  registerBlocker,
} from "@/lib/passwordLogin";

type ErrorLike = { status?: number; code?: string; message?: string };

/**
 * Password + confirmation + the rules + the acknowledgement checkbox (CR-005). The password stays in this
 * component's state: it is sent once and then cleared, never written to any storage. The rules are shown
 * as words ("충족"/"필요"), not by colour alone.
 */
export function PasswordRegisterForm({
  submitLabel,
  busyLabel,
  onSubmit,
  onCancel,
}: {
  submitLabel: string;
  busyLabel: string;
  onSubmit: (password: string) => Promise<void>;
  onCancel?: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const blocker = registerBlocker({ password, confirm, acknowledged, busy });
  const checks = passwordChecks(password);

  async function submit() {
    if (blocker) return;
    setBusy(true);
    setMessage(null);
    try {
      await onSubmit(password);
      setPassword("");
      setConfirm("");
      setAcknowledged(false);
    } catch (error) {
      setMessage(passwordErrorMessage(error as ErrorLike, "저장하지 못했어요. 다시 시도해 주세요."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="field">
        <label htmlFor="pw-new">암호</label>
        <input
          id="pw-new"
          type="password"
          autoComplete="new-password"
          value={password}
          maxLength={64}
          disabled={busy}
          aria-describedby="pw-rules"
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <ul id="pw-rules" className="pw-rules" aria-label="암호 규칙">
        {checks.map((c) => (
          <li key={c.key} data-ok={c.ok ? "true" : "false"}>
            <strong>{c.ok ? "충족" : "필요"}</strong> {c.label}
          </li>
        ))}
      </ul>
      <div className="field">
        <label htmlFor="pw-confirm">암호 확인</label>
        <input
          id="pw-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          maxLength={64}
          disabled={busy}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {confirm !== "" && confirm !== password && <span className="small error">암호 확인이 암호와 달라요.</span>}
      </div>
      <label className="consent-check">
        <input type="checkbox" checked={acknowledged} disabled={busy} onChange={(e) => setAcknowledged(e.target.checked)} />
        {ACKNOWLEDGE_TEXT}
      </label>
      {message && (
        <p className="error" role="alert">
          {message}
        </p>
      )}
      <div className="modal-actions" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="btn" id="pw-submit" onClick={submit} disabled={blocker !== null}>
          {busy ? busyLabel : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>
            취소
          </button>
        )}
      </div>
    </div>
  );
}

/** Password only, for coming in from another device. Sent once, then cleared (also after a failure). */
export function PasswordLoginForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (password: string) => Promise<void>;
  onCancel?: () => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function submit() {
    if (busy || password === "") return;
    setBusy(true);
    setMessage(null);
    const sent = password;
    setPassword("");
    try {
      await onSubmit(sent);
    } catch (error) {
      setMessage(passwordErrorMessage(error as ErrorLike, "로그인하지 못했어요. 다시 시도해 주세요."));
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="field">
        <label htmlFor="pw-login">등록한 암호</label>
        <input
          id="pw-login"
          type="password"
          autoComplete="current-password"
          value={password}
          maxLength={64}
          disabled={busy}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {message && (
        <p className="error" role="alert">
          {message}
        </p>
      )}
      <div className="modal-actions" style={{ justifyContent: "flex-start" }}>
        <button type="submit" className="btn" id="pw-login-submit" disabled={busy || password === ""}>
          {busy ? "확인하는 중…" : "암호로 들어가기"}
        </button>
        {onCancel && (
          <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>
            취소
          </button>
        )}
      </div>
    </form>
  );
}
