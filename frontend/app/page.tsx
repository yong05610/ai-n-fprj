"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AnalysisScreen } from "@/components/AnalysisScreen";
import { useAuth } from "@/components/AuthProvider";
import { ConsentModal } from "@/components/ConsentModal";
import { Dashboard } from "@/components/Dashboard";
import { ExecutionScreen } from "@/components/ExecutionScreen";
import { LearningPathWizard } from "@/components/LearningPathWizard";
import { SettingsScreen } from "@/components/SettingsScreen";
import { TutorScreen } from "@/components/TutorScreen";
import { type View, buildHash, parseHash } from "@/lib/viewHash";
import { todayKSTLabel } from "@/lib/week";

/**
 * Routing choice (Phase 5C): a single page with a `View` state, as before, plus the current
 * view mirrored into the URL hash so a refresh keeps the screen. The hash is written with
 * replaceState (no history entries), so the in-wizard "leave?" confirmation covers every
 * way of leaving that the app itself offers.
 */
type NavEntry = { view: View | null; icon: string; label: string };

const USER_NAV: NavEntry[] = [
  { view: "dashboard", icon: "⌂", label: "대시보드" },
  { view: "path", icon: "✦", label: "학습 경로 설정" },
  { view: null, icon: "▦", label: "학습 과제 계획" }, // Phase 5D
  { view: "execution", icon: "◷", label: "학습 실행 기록" },
  { view: "analysis", icon: "▥", label: "종합 학습 분석" },
  { view: "tutor", icon: "◌", label: "AI 튜터" },
  { view: null, icon: "▤", label: "참고자료 보관함" }, // Phase 6B+
  { view: "settings", icon: "⚙", label: "내 정보·설정" },
];

// Phase 5E; shown disabled so they never look like working features.
const ADMIN_NAV: NavEntry[] = [
  { view: null, icon: "▣", label: "운영 현황" },
  { view: null, icon: "♙", label: "사용자 관리" },
  { view: null, icon: "✧", label: "AI 생성 이력" },
  { view: null, icon: "▧", label: "참고자료 관리" },
  { view: null, icon: "♡", label: "사용자 피드백" },
  { view: null, icon: "⚙", label: "서비스 설정" },
];

function NavButton({ entry, current, onGo }: { entry: NavEntry; current: View; onGo: (v: View) => void }) {
  if (entry.view === null) {
    return (
      <button type="button" className="nav-item" aria-disabled="true" onClick={(e) => e.preventDefault()}>
        <span className="nav-icon">{entry.icon}</span>
        {entry.label}
        <span className="nav-soon">준비 중</span>
      </button>
    );
  }
  const target = entry.view;
  return (
    <button
      type="button"
      className={`nav-item${current === target ? " active" : ""}`}
      aria-current={current === target ? "page" : undefined}
      onClick={() => onGo(target)}
    >
      <span className="nav-icon">{entry.icon}</span>
      {entry.label}
    </button>
  );
}

export default function Home() {
  const { status, errorMessage, accept, decline, reopenConsent } = useAuth();
  const [view, setView] = useState<View | null>(null);
  const [today, setToday] = useState("");
  const [query, setQuery] = useState("");
  // The wizard registers a function that asks the user before leaving unsaved work.
  const leaveGuard = useRef<(() => boolean) | null>(null);

  useEffect(() => {
    setView(parseHash(window.location.hash).view ?? "dashboard");
    setToday(todayKSTLabel());
  }, []);

  const go = useCallback(
    (next: View) => {
      if (next === view) return;
      if (leaveGuard.current && !leaveGuard.current()) return;
      setView(next);
      window.history.replaceState(null, "", buildHash(next));
    },
    [view],
  );

  const registerLeaveGuard = useCallback((guard: (() => boolean) | null) => {
    leaveGuard.current = guard;
  }, []);

  if (status === "checking") {
    return (
      <main className="gate">
        <p className="description">불러오는 중…</p>
      </main>
    );
  }

  if (status === "declined") {
    return (
      <main className="gate">
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
      <main className="gate">
        <ConsentModal
          busy={status === "starting"}
          errorMessage={status === "error" ? errorMessage : null}
          onAccept={accept}
          onDecline={decline}
        />
      </main>
    );
  }

  const current: View = view ?? "dashboard";
  const currentLabel = USER_NAV.find((n) => n.view === current)?.label ?? "대시보드";

  function onSearch(value: string) {
    const needle = value.trim();
    if (!needle) return;
    const hit = USER_NAV.find((n) => n.view !== null && n.label.includes(needle));
    if (hit?.view) {
      go(hit.view);
      setQuery("");
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="#dashboard" onClick={(e) => { e.preventDefault(); go("dashboard"); }}>
          <span className="brand-icon">↗</span>
          <span>
            PaceMate<em>LEARN AT YOUR PACE</em>
          </span>
        </a>
        <div className="nav-group">
          <div className="nav-title">사용자</div>
          <nav>
            {USER_NAV.map((entry) => (
              <NavButton key={entry.label} entry={entry} current={current} onGo={go} />
            ))}
          </nav>
        </div>

        <div className="nav-separator"></div>

        <div className="nav-group">
          <div className="nav-title">관리자 · 준비 중</div>
          <nav>
            {ADMIN_NAV.map((entry) => (
              <NavButton key={entry.label} entry={entry} current={current} onGo={go} />
            ))}
          </nav>
        </div>

        <div className="sidebar-bottom">
          <div className="user-mini">
            <div className="avatar">학</div>
            <div>
              <strong>학습자 계정</strong>
              <small>테스터 미리보기</small>
            </div>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="crumb">
            PaceMate <span style={{ color: "#c6cad4" }}>/</span> <b>{currentLabel}</b>
          </div>
          <div className="top-right">
            <input
              className="search"
              placeholder="메뉴 또는 학습 검색"
              aria-label="검색"
              value={query}
              autoComplete="off"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSearch(query);
              }}
            />
            <span className="today-date">{today}</span>
            <button className="notice" aria-label="알림 (준비 중)" disabled>
              ♧
            </button>
          </div>
        </header>

        <main className="main">
          {view !== null && (
            <div className="page">
              {current === "dashboard" && <Dashboard onCreatePath={() => go("path")} onOpenAnalysis={() => go("analysis")} onOpenTutor={() => go("tutor")} />}
              {current === "path" && (
                <LearningPathWizard onClose={() => go("dashboard")} registerLeaveGuard={registerLeaveGuard} />
              )}
              {current === "execution" && <ExecutionScreen />}
              {current === "analysis" && <AnalysisScreen onCreatePath={() => go("path")} />}
              {current === "tutor" && <TutorScreen />}
              {current === "settings" && <SettingsScreen />}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
