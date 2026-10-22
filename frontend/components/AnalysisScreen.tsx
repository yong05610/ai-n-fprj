"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import { formatPeriod } from "@/lib/format";
import { todayKSTDateString } from "@/lib/week";

type AnalyticsGoal = {
  goal_id: string;
  course: string;
  start_date: string;
  target_date: string;
  completed_task_count: number;
  total_task_count: number;
  progress_percentage: number;
  weekly_minutes_by_day: number[];
};
type AnalyticsOverview = { week_start: string; week_end: string; goals: AnalyticsGoal[] };

const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

const HEADING = (
  <div className="heading">
    <div>
      <p className="kicker">LEARNING ANALYSIS</p>
      <h1>종합 학습 분석</h1>
      <p>진행 중인 학습의 일정, 일자별 투입 시간, 진행률을 한눈에 봅니다.</p>
    </div>
  </div>
);
type Status = "loading" | "ready" | "error";

/** Read-only overview of every in-progress learning (docs/multi_goal_design.md D). CSS bars only. */
export function AnalysisScreen({ onCreatePath }: { onCreatePath: () => void }) {
  const { session } = useAuth();
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!session) return;
    setStatus("loading");
    setError(null);
    try {
      const token = await session.getToken();
      setData(await apiRequest<AnalyticsOverview>("/api/analytics/overview", { token }));
      setStatus("ready");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "분석 데이터를 불러오지 못했습니다.");
      setStatus("error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  if (status === "loading") {
    return (
      <>
        {HEADING}
        <section className="card">
          <p className="description">불러오는 중…</p>
        </section>
      </>
    );
  }

  if (status === "error" || !data) {
    return (
      <>
        {HEADING}
        <section className="card">
          <p className="error" role="alert">
            {error}
          </p>
          <button className="btn" onClick={load}>
            다시 시도
          </button>
        </section>
      </>
    );
  }

  const thisYear = Number(todayKSTDateString().slice(0, 4));

  return (
    <>
      {HEADING}
      <p className="scope-note">
        완료된 학습은 포함하지 않아요. 읽기 전용 화면이며 기록된 데이터만 집계해요. 이번 주: {data.week_start} ~ {data.week_end}
      </p>

      {data.goals.length === 0 && (
        <section className="card" style={{ marginBottom: 14 }}>
          <h2>진행 중인 학습이 없어요</h2>
          <p className="description">학습 경로를 만들면 일정과 진행률, 요일별 투입 시간을 볼 수 있습니다.</p>
          <button className="btn" onClick={onCreatePath}>
            ＋ 학습 경로 만들기
          </button>
        </section>
      )}

      {data.goals.map((g) => {
        const weekTotal = g.weekly_minutes_by_day.reduce((a, b) => a + b, 0);
        const max = Math.max(...g.weekly_minutes_by_day, 1);
        return (
          <section key={g.goal_id} className="card" style={{ marginBottom: 14 }}>
            <div className="card-head">
              <div>
                <h2>{g.course}</h2>
                <p>일정 {formatPeriod(g.start_date, g.target_date, thisYear)}</p>
              </div>
              <span className="pill blue">진행 중</span>
            </div>
            <div className="bar" role="progressbar" aria-valuenow={g.progress_percentage} aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${g.progress_percentage}%` }}></span>
            </div>
            <div className="bar-label">
              <span>
                {g.completed_task_count} / {g.total_task_count} 과제 완료
              </span>
              <b>진행률 {g.progress_percentage}%</b>
            </div>
            <p className="scope-note">일자별 투입 시간(분) · 이번 주 {weekTotal}분</p>
            <div className="mini-bars" aria-label="요일별 학습 분">
              {g.weekly_minutes_by_day.map((m, i) => (
                <span key={DAY_LABELS[i]} style={{ height: `${Math.max(6, Math.round((m / max) * 100))}%` }}>
                  <i>{m}</i>
                </span>
              ))}
            </div>
            <div className="mini-days">
              {DAY_LABELS.map((d) => (
                <span key={d}>{d}</span>
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}
