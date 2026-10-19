"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ConsentModal } from "@/components/ConsentModal";
import { DeleteDataSection } from "@/components/DeleteDataSection";
import { apiRequest } from "@/lib/api";

type Goal = { id: string; field: string; course: string; target_level_name: string; status: string };

function GoalList() {
  const { session } = useAuth();
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    session
      .getToken()
      .then((token) => apiRequest<Goal[]>("/api/goals", { token }))
      .then(setGoals)
      .catch((e: Error) => setError(e.message));
  }, [session]);

  return (
    <section className="card">
      <h2>내 학습 목표</h2>
      {error && <p className="error">{error}</p>}
      {!error && goals === null && <p className="description">불러오는 중…</p>}
      {goals?.length === 0 && <p className="description">아직 저장된 학습 목표가 없습니다.</p>}
      {goals && goals.length > 0 && (
        <ul>
          {goals.map((goal) => (
            <li key={goal.id}>
              {goal.field} · {goal.course} → {goal.target_level_name} ({goal.status})
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Home() {
  const { status, session, errorMessage, accept, decline, reopenConsent } = useAuth();

  if (status === "checking") {
    return (
      <main className="shell">
        <p className="description">불러오는 중…</p>
      </main>
    );
  }

  if (status === "declined") {
    return (
      <main className="shell">
        <section className="card">
          <p className="eyebrow">PACEMATE · MVP</p>
          <h1>안내에 동의해야 개인화 기능을 이용할 수 있습니다.</h1>
          <p className="description">
            동의하지 않으면 익명 UID를 만들지 않으며 학습 목표·기록·AI 튜터 기능을 이용할 수 없습니다. 아무 데이터도 저장되지
            않았습니다.
          </p>
          <button className="btn" onClick={reopenConsent}>
            안내 다시 보기
          </button>
        </section>
      </main>
    );
  }

  if (status !== "ready") {
    return (
      <main className="shell">
        <ConsentModal
          busy={status === "starting"}
          errorMessage={status === "error" ? errorMessage : null}
          onAccept={accept}
          onDecline={decline}
        />
      </main>
    );
  }

  return (
    <main className="shell stack">
      <section className="card">
        <p className="eyebrow">PACEMATE · MVP</p>
        <h1>나에게 맞는 학습 페이스를 찾아보세요.</h1>
        <div className="status">
          <span className="dot ok" aria-hidden="true" />
          <span>
            익명 계정으로 시작했습니다 · UID <code>{session?.uid.slice(0, 8)}…</code>
          </span>
        </div>
      </section>
      <GoalList />
      <DeleteDataSection />
    </main>
  );
}
