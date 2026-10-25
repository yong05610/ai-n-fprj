"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import { formatPeriod, formatTargetMinutes, levelSummary } from "@/lib/format";
import { continuedLabel, dashboardScheduleText } from "@/lib/planText";
import { todayKSTDateString } from "@/lib/week";

type TodayTask = {
  id: string;
  title: string;
  estimated_minutes: number;
  suggested_weekday: string;
  is_completed: boolean;
  record_count: number;
  /** Phase 5F: this task's scheduled minutes this week, and whether it continues from an earlier week */
  week_minutes: number;
  continued: boolean;
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
  week_scheduled_minutes: number;
  today_scheduled_minutes: number;
  plan_total_minutes: number;
  plan_available_minutes: number;
  weekly_hits: DailyHit[];
  insight: Insight;
  goals_overview: GoalOverview[];
};

type Status = "loading" | "ready" | "error";

export function Dashboard({
  onCreatePath,
  onOpenAnalysis,
  onOpenTutor,
  onOpenPlan,
}: {
  onCreatePath: () => void;
  onOpenAnalysis: () => void;
  onOpenTutor: () => void;
  onOpenPlan: () => void;
}) {
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

  const heading = (
    <div className="heading">
      <div>
        <p className="kicker">MY LEARNING SPACE</p>
        <h1>안녕하세요, 학습자님 👋</h1>
        <p>현재 수준에서 목표까지, 오늘의 한 걸음을 시작해보세요.</p>
      </div>
      <button className="btn" onClick={onCreatePath}>
        ＋ 학습 경로 만들기
      </button>
    </div>
  );

  if (status === "loading") {
    return (
      <>
        {heading}
        <section className="card">
          <p className="description">대시보드를 불러오는 중…</p>
        </section>
      </>
    );
  }

  if (status === "error") {
    return (
      <>
        {heading}
        <section className="card">
          <p className="error" role="alert">
            {error}
          </p>
          <button className="btn" onClick={() => load()}>
            다시 시도
          </button>
        </section>
      </>
    );
  }

  if (!summary) return null;

  if (!summary.active_goal_title && summary.goals_overview.length === 0) {
    return (
      <>
        {heading}
        <section className="card">
          <h2>아직 학습 목표가 없어요</h2>
          <p className="description">학습 경로를 만들면 대시보드에 진행현황이 표시됩니다.</p>
        </section>
      </>
    );
  }

  const thisYear = Number(todayKSTDateString().slice(0, 4));
  const recentBlock = summary.active_goal_title !== "";
  const levels = levelSummary(summary.level_progress_text);
  const weeklyAchievementPercent =
    summary.weekly_target_minutes > 0 ? Math.round((summary.weekly_study_minutes / summary.weekly_target_minutes) * 100) : 0;
  const activeDays = summary.weekly_hits.filter((h) => h.has_activity).length;
  // "field · course" -> the course part is what the mockup's progress card names.
  const courseName = summary.active_goal_title.split(" · ").slice(1).join(" · ") || summary.active_goal_title;

  return (
    <>
      {heading}

      <section className="card" style={{ marginBottom: 14 }} aria-label="종합 학습 현황">
        <div className="card-head">
          <div>
            <h2>종합 학습 현황 · 진행 중인 모든 학습</h2>
            <p>아래 통계는 최근 학습 기준이고, 이 영역은 진행 중인 전체 학습을 보여줘요.</p>
          </div>
          <button type="button" className="link-btn" onClick={onOpenAnalysis}>
            종합 분석 →
          </button>
        </div>
        {summary.goals_overview.length === 0 ? (
          <p className="description">진행 중인 학습이 없습니다.</p>
        ) : (
          summary.goals_overview.map((g) => (
            <div key={g.goal_id} className="goal-row">
              <div>
                <strong>{g.course}</strong>
                <p className="small muted" style={{ margin: "2px 0 0" }}>
                  {formatPeriod(g.start_date, g.target_date, thisYear)}
                </p>
              </div>
              <div>
                <div className="bar" role="progressbar" aria-valuenow={g.progress_percentage} aria-valuemin={0} aria-valuemax={100}>
                  <span style={{ width: `${g.progress_percentage}%` }}></span>
                </div>
              </div>
              <b>{g.progress_percentage}%</b>
            </div>
          ))
        )}
      </section>

      {recentBlock ? (
        <div className="grid stats">
          <article className="card stat">
            <div>
              <label>최근 학습 경로</label>
              <strong className="long">{summary.active_goal_title}</strong>
              <small>{levels ? `현재 ${levels.current} → 목표 ${levels.target}` : summary.level_progress_text}</small>
            </div>
            <span className="stat-icon">✦</span>
          </article>
          <article className="card stat">
            <div>
              <label>완료 학습 과제</label>
              <strong>
                {summary.completed_task_count} <small>/ {summary.total_task_count}개</small>
              </strong>
              <small>전체 진행률 {summary.progress_percentage}%</small>
            </div>
            <span className="stat-icon">▦</span>
          </article>
          <article className="card stat">
            <div>
              <label>이번 주 학습</label>
              <strong>
                {summary.weekly_study_minutes} <small>분</small>
              </strong>
              <small>
                주간 목표 {formatTargetMinutes(summary.weekly_target_minutes)} · 달성 {weeklyAchievementPercent}%
              </small>
            </div>
            <span className="stat-icon">◷</span>
          </article>
          <article className="card stat">
            <div>
              <label>학습 기록</label>
              <strong>
                {summary.total_study_log_count} <small>회</small>
              </strong>
              <small>전체 기간</small>
            </div>
            <span className="stat-icon">↗</span>
          </article>
        </div>
      ) : (
        <section className="card" style={{ marginBottom: 15 }}>
          <p className="description">
            최근 학습이 선택되어 있지 않아요. 학습 실행 기록 화면에서 학습을 전환하면 이곳에 표시됩니다.
          </p>
        </section>
      )}

      {recentBlock && (
        <div className="grid two-col">
          <section className="card">
            <div className="card-head">
              <div>
                <h2>오늘의 추천 과제</h2>
                <p>이번 주 미완료 과제 중 시작하기 좋은 항목</p>
              </div>
              <button type="button" className="link-btn" onClick={onOpenPlan}>
                전체 일정 보기 →
              </button>
            </div>
            <div className="card progress-card">
              <div className="progress-top">
                <div>
                  <strong>{courseName}</strong>
                  <p>{levels ? `현재 ${levels.current} → 목표 ${levels.target}` : summary.level_progress_text}</p>
                </div>
                <span className="pill">진행 중</span>
              </div>
              <div className="bar">
                <span style={{ width: `${summary.progress_percentage}%` }}></span>
              </div>
              <div className="bar-label">
                <span>
                  {summary.completed_task_count} / {summary.total_task_count} 과업 완료
                </span>
                <b>{summary.progress_percentage}%</b>
              </div>
            </div>
            <p className="small muted schedule-line">{dashboardScheduleText(summary.week_scheduled_minutes, summary.today_scheduled_minutes)}</p>
            {summary.all_tasks_completed_this_week && <p className="description">이번 주 과제를 모두 완료했어요 🎉</p>}
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
                        {checked
                          ? "과제 완료"
                          : t.continued || t.week_minutes < t.estimated_minutes
                            ? continuedLabel(t.week_minutes, t.estimated_minutes)
                            : `예상 ${t.estimated_minutes}분`}{" "}
                        · 학습 기록 {t.record_count}건
                      </small>
                    </div>
                    {toggling[t.id] === "error" && (
                      <button type="button" className="link-btn" onClick={() => toggleTask(t.id, checked)}>
                        재시도
                      </button>
                    )}
                    <span className="task-time">
                      {checked ? `${t.estimated_minutes}분` : t.record_count > 0 ? "기록 추가" : "추천 과제"}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="small muted" style={{ marginTop: 10 }}>
              추천 과제는 필수 일정이 아닙니다. 미완료 과제는 주간 계획에 그대로 남습니다.
            </p>
          </section>

          <aside>
            <section className="coach">
              <p className="kicker">AI LEARNING INSIGHT</p>
              <h3>{summary.insight.text}</h3>
              {summary.insight.notice && <p>{summary.insight.notice}</p>}
              <button type="button" className="btn" onClick={onOpenTutor}>
                AI 튜터에게 물어보기 →
              </button>
            </section>
            <section className="card" style={{ marginTop: 13 }}>
              <div className="card-head">
                <div>
                  <h2>현재 학습 수준</h2>
                  <p>{summary.active_goal_title.split(" · ")[0]} · AI가 제안한 수준 체계</p>
                </div>
              </div>
              {levels ? (
                <div className="bar-label">
                  <span>현재 · {levels.current}</span>
                  <b>목표 · {levels.target}</b>
                </div>
              ) : (
                <p className="small muted">{summary.level_progress_text}</p>
              )}
            </section>
            <section className="card" style={{ marginTop: 13 }}>
              <div className="card-head">
                <div>
                  <h2>이번 주 학습 활동</h2>
                  <p>기록을 남긴 날짜</p>
                </div>
                <span className="pill blue">{activeDays}일</span>
              </div>
              <div className="week-days">
                {summary.weekly_hits.map((h) => (
                  <div key={h.date} className={`day${h.has_activity ? " hit" : ""}${h.is_today ? " now" : ""}`}>
                    {h.day}
                    <i></i>
                  </div>
                ))}
              </div>
            </section>
          </aside>
        </div>
      )}
    </>
  );
}
