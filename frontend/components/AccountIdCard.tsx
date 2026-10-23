"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";

/**
 * "관리자 등록용 계정 ID" (Phase 5E). Every user sees only their own UID. Copying uses the
 * clipboard; if that is unavailable or refused, the ID is shown as selectable text instead.
 */
export function AccountIdCard() {
  const { session } = useAuth();
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle");
  if (!session) return null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(session!.uid);
      setState("copied");
    } catch {
      setState("manual");
    }
  }

  return (
    <section className="card">
      <h2>관리자 등록용 계정 ID</h2>
      <p className="small muted">
        관리자로 등록하려면 이 계정 ID 를 운영자에게 전달하세요. 본인 계정의 ID 만 보여요.
      </p>
      <button type="button" className="btn secondary" onClick={copy}>
        계정 ID 복사
      </button>
      {state === "copied" && (
        <p className="small" role="status" style={{ color: "#248160", fontWeight: 800 }}>
          복사했어요
        </p>
      )}
      {state === "manual" && (
        <div className="field">
          <label htmlFor="account-id">복사하지 못했어요. 아래 ID 를 직접 선택해 복사해 주세요.</label>
          <input id="account-id" readOnly value={session.uid} onFocus={(e) => e.currentTarget.select()} />
        </div>
      )}
    </section>
  );
}
