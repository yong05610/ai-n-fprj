"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";

type TodayTask = {
  id: string;
  title: string;
  estimated_minutes: number;
  suggested_weekday: string;
  is_completed: boolean;
  record_count: number;
};
type DailyHit = { day: string; date: string; has_activity: boolean; is_today: boolean };
type Insight = { text: string; notice: string; is_insufficient: boolean };
export type GoalOverview = {
  goal_id: string;
  course: string;
  start_date: string;
  target_date: string;
  completed_task_count: number;
  total_task_count: number;
  progress_percentage: number;
};
type DashboardSummary = {
  active_goal_title: string;
  level_progress_text: string;
  completed_task_count: number;
  total_task_count: number;
  progress_percentage: number;
  weekly_study_minutes: number;
  weekly_target_minutes: number;
  total_study_log_count: number;
  today_tasks: TodayTask[];
  all_tasks_completed_this_week: boolean;
  weekly_hits: DailyHit[];
  insight: Insight;
  goals_overview: GoalOverview[];
};

type Status = "loading" | "ready" | "error";

export function Dashboard({ onCreatePath }: { onCreatePath: () => void }) {
  const { session } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<Record<string, "pending" | "error">>({});
  // Optimistic overlay used only while a toggle's own PATCH+refetch is in flight; once the
  // refetch lands, summary.today_tasks[].is_completed (now accurate - P5-4) is the source
  // of truth again, so the override is cleared rather than kept forever.
  const [checkedOverride, setCheckedOverride] = useState<Record<string, boolean>>({});

  async function load(opts: { silent?: boolean } = {}) {
    if (!session) return;
    if (!opts.silent) setStatus("loading");
    setError(null);
    try {
      const token = await session.getToken();
      const result = await apiRequest<DashboardSummary>("/api/dashboard/summary", { token });
      setSummary(result);
      setStatus("ready");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "대시보드를 불러오지 못했습니다.");
      setStatus("error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  async function toggleTask(taskId: string, currentlyChecked: boolean) {
    if (!session || toggling[taskId] === "pending") return;
    const next = !currentlyChecked;
    setCheckedOverride((prev) => ({ ...prev, [taskId]: next }));
    setToggling((prev) => ({ ...prev, [taskId]: "pending" }));
    try {
      const token = await session.getToken();
      await apiRequest(`/api/tasks/${taskId}`, { method: "PATCH", token, body: { status: next ? "completed" : "pending" } });
      // P5-3: re-fetch so completed_task_count/progress_percentage update too, not just
      // the checkbox. `silent: true` keeps the whole dashboard from flashing a loading
      // screen - the optimistic checkmark already shows the right thing meanwhile.
      await load({ silent: true });
      setToggling((prev) => {
        const { [taskId]: _removed, ...rest } = prev;
        return rest;
      });
      setCheckedOverride((prev) => {
        const { [taskId]: _removed, ...rest } = prev;
        return rest;
      });
    } catch {
      setCheckedOverride((prev) => ({ ...prev, [taskId]: currentlyChecked }));
      setToggling((prev) => ({ ...prev, [taskId]: "error" }));
    }
  }

  if (status === "loading") {
    return (
      <section className="card">
        <p className="description">대시보드를 불러오는 중…</p>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section className="card">
        <p className="error" role="alert">
          {error}
        </p>
        <button className="btn" onClick={() => load()}>
          다시 시도
        </button>
      </section>
    );
  }

  if (!summary) return null;

  if (!summary.active_goal_title && summary.goals_overview.length === 0) {
    return (
      <section className="card">
        <h2>아직 학습 목표가 없어요</h2>
        <p className="description">학습 경로를 만들면 대시보드에 진행현황이 표시됩니다.</p>
        <button className="btn" onClick={onCreatePath}>
          ＋ 학습 경로 만들기
        </button>
      </section>
    );
  }

  const weeklyAchievementPercent =
    summary.weekly_target_minutes > 0
      ? Math.round((summary.weekly_study_minutes / summary.weekly_target_minutes) * 100)
      : 0;

  const recentBlock = summary.active_goal_title !== "";

  return (
    <div className="stack">
      <section className="card">
        <p className="eyebrow">MY LEARNING SPACE</p>
        {recentBlock ? (
          <>
            <p className="scope-label">최근 학습 경로</p>
            <h2>{summary.active_goal_title}</h2>
            <p className="description">{summary.level_progress_text}</p>
          </>
        ) : (
          <p className="description">
            최근 학습이 선택되어 있지 않아요. 학습 실행 기록 화면에서 학습을 전환하면 이곳에 표시됩니다.
          </p>
        )}
      </section>

      <section className="card" aria-label="종합 학습 현황">
        <div className="card-head">
          <div>
            <h2>종합 학습 현황</h2>
            <p className="small muted">진행 중인 모든 학습</p>
          </div>
        </div>
        {summary.goals_overview.length === 0 ? (
          <p className="description">진행 중인 학습이 없습니다.</p>
        ) : (
          summary.goals_overview.map((g) => (
            <div key={g.goal_id} className="goal-row">
              <div>
                <strong>{g.course}</strong>
                <small className="block-small">
                  {g.start_date} ~ {g.target_date}
                </small>
              </div>
              <div>
                <div className="bar" role="progressbar" aria-valuenow={g.progress_percentage} aria-valuemin={0} aria-valuemax={100}>
                  <span style={{ width: `${g.progress_percentage}%` }}></span>
                </div>
                <small className="block-small">
                  {g.completed_task_count} / {g.total_task_count} 과제 완료
                </small>
              </div>
              <b>{g.progress_percentage}%</b>
            </div>
          ))
        )}
      </section>

      {recentBlock && (
        <>

      <div className="grid stats">
        <article className="card stat">
          <label>완료 학습 과제</label>
          <strong>
            {summary.completed_task_count} <small>/ {summary.total_task_count}개</small>
          </strong>
          <small>전체 진행률 {summary.progress_percentage}%</small>
        </article>
        <article className="card stat">
          <label>이번 주 학습</label>
          <strong>
            {summary.weekly_study_minutes} <small>분</small>
          </strong>
          <small>주간 목표 {summary.weekly_target_minutes}분</small>
        </article>
        <article className="card stat">
          <label>학습 기록</label>
          <strong>{summary.total_study_log_count}</strong>
          <small>전체 기간</small>
        </article>
        <article className="card stat">
          <label>주간 목표 달성률</label>
          <strong>{weeklyAchievementPercent}%</strong>
          <small>이번 주 학습 시간 기준</small>
        </article>
      </div>

      <section className="card">
        <div className="card-head">
          <h2>오늘의 추천 과제</h2>
          <p className="small muted">추천 과제는 필수 일정이 아닙니다. 미완료 과제는 주간 계획에 그대로 남습니다.</p>
        </div>
        {summary.all_tasks_completed_this_week && (
          <p className="description">이번 주 과제를 모두 완료했어요 🎉</p>
        )}
        {summary.today_tasks.length === 0 && <p className="description">이번 주 추천 과제가 없습니다.</p>}
        <div className="task-list">
          {summary.today_tasks.map((t) => {
            const checked = checkedOverride[t.id] ?? t.is_completed;
            return (
              <div key={t.id} className={`task${checked ? " done" : ""}`}>
                <button
                  type="button"
                  className="task-check"
                  onClick={() => toggleTask(t.id, checked)}
                  disabled={toggling[t.id] === "pending"}
                  aria-label={checked ? "완료 취소" : "완료로 표시"}
                >
                  {checked ? "✓" : "○"}
                </button>
                <div className="task-info">
                  <strong>{t.title}</strong>
                  <small>
                    예상 {t.estimated_minutes}분 · 기록 {t.record_count}건
                  </small>
                </div>
                {toggling[t.id] === "error" && (
                  <button type="button" className="link-btn" onClick={() => toggleTask(t.id, checked)}>
                    재시도
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="card">
        <h2>이번 주 학습 활동</h2>
        <div className="week-days">
          {summary.weekly_hits.map((h) => (
            <div key={h.date} className={`day${h.has_activity ? " hit" : ""}${h.is_today ? " now" : ""}`}>
              {h.day}
              <i></i>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>학습 인사이트</h2>
        <p className="description">{summary.insight.text}</p>
      </section>
        </>
      )}
    </div>
  );
}
