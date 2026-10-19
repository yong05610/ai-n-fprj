"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";

type Phase = "idle" | "confirm" | "deleting" | "error";

export function DeleteDataSection() {
  const { deleteAllData } = useAuth();
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const run = async () => {
    setPhase("deleting");
    try {
      await deleteAllData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "삭제 요청에 실패했습니다.");
      setPhase("error");
    }
  };

  return (
    <section className="card">
      <h2>내 학습 데이터 삭제</h2>
      <p className="description">
        학습 목표·과제·기록·회고·AI 튜터 대화와 동의 기록이 모두 삭제되고, 익명 계정도 함께 삭제됩니다. 삭제 후에는 되돌릴 수
        없습니다.
      </p>
      <button className="btn danger" onClick={() => setPhase("confirm")}>
        내 학습 데이터 삭제 요청
      </button>

      {phase !== "idle" && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-title">
          <section className="modal">
            <h2 id="delete-title">정말 모든 학습 데이터를 삭제할까요?</h2>
            <p>삭제가 완료되면 처음 안내 화면으로 돌아갑니다. 다시 이용하려면 새로 동의해야 합니다.</p>
            {phase === "error" && (
              <p className="error" role="alert">
                {message}
              </p>
            )}
            <div className="modal-actions">
              <button className="btn secondary" onClick={() => setPhase("idle")} disabled={phase === "deleting"}>
                취소
              </button>
              <button className="btn danger" onClick={run} disabled={phase === "deleting"}>
                {phase === "deleting" ? "삭제하는 중…" : phase === "error" ? "다시 시도" : "삭제"}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
