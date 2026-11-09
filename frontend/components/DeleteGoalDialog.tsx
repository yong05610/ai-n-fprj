"use client";

import { useEffect } from "react";

import { DELETE_TITLE, DELETE_TUTOR_NOTE, type DeleteCounts, deleteBody, deleteConfirmButton } from "@/lib/goalDelete";

type Props = {
  course: string;
  counts: DeleteCounts;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

/**
 * CR-013: confirmation before a learning is deleted. The focus starts on "취소"; Esc and a click outside cancel
 * (not while the delete is running). A failure shows here with "다시 시도"; nothing was deleted then.
 */
export function DeleteGoalDialog({ course, counts, busy, error, onCancel, onConfirm }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  const [name, rest] = deleteBody(course, counts);
  const confirm = deleteConfirmButton(busy, error !== null);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-goal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <section className="modal">
        <h2 id="delete-goal-title">{DELETE_TITLE}</h2>
        <p>
          <b>{name}</b>
          {rest}
        </p>
        <p>{DELETE_TUTOR_NOTE}</p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="btn secondary" id="delete-goal-cancel" onClick={onCancel} disabled={busy} autoFocus>
            취소
          </button>
          <button type="button" className="btn danger" id="delete-goal-confirm" onClick={onConfirm} disabled={confirm.disabled}>
            {confirm.label}
          </button>
        </div>
      </section>
    </div>
  );
}
