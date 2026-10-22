"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { AnalysisScreen } from "@/components/AnalysisScreen";
import { ConsentModal } from "@/components/ConsentModal";
import { Dashboard } from "@/components/Dashboard";
import { DeleteDataSection } from "@/components/DeleteDataSection";
import { ExecutionScreen } from "@/components/ExecutionScreen";
import { LearningPathWizard } from "@/components/LearningPathWizard";

type View = "dashboard" | "execution" | "analysis" | "wizard";

function NavBar({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  return (
    <nav className="nav-bar">
      <button className={`btn${view === "dashboard" ? " active" : ""}`} onClick={() => onChange("dashboard")}>
        대시보드
      </button>
      <button className={`btn${view === "execution" ? " active" : ""}`} onClick={() => onChange("execution")}>
        학습 실행 기록
      </button>
      <button className={`btn${view === "analysis" ? " active" : ""}`} onClick={() => onChange("analysis")}>
        종합 학습 분석
      </button>
      <button className={`btn${view === "wizard" ? " active" : ""}`} onClick={() => onChange("wizard")}>
        학습 경로 만들기
      </button>
    </nav>
  );
}

export default function Home() {
  const { status, session, errorMessage, accept, decline, reopenConsent } = useAuth();
  const [view, setView] = useState<View>("dashboard");
  const [dashboardKey, setDashboardKey] = useState(0);

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

  if (view === "wizard") {
    return (
      <main className="shell wide">
        <LearningPathWizard
          onClose={() => {
            setView("dashboard");
            setDashboardKey((k) => k + 1);
          }}
        />
      </main>
    );
  }

  return (
    <main className="shell wide">
      <NavBar view={view} onChange={setView} />
      {view === "dashboard" && (
        <div className="stack">
          <Dashboard key={dashboardKey} onCreatePath={() => setView("wizard")} />
          <DeleteDataSection />
        </div>
      )}
      {view === "execution" && <ExecutionScreen />}
      {view === "analysis" && <AnalysisScreen onCreatePath={() => setView("wizard")} />}
    </main>
  );
}
