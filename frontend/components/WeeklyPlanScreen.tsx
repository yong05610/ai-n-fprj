"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { GoalSwitch } from "@/components/GoalSwitch";
import { useGoalSwitch } from "@/components/useGoalSwitch";
import { ApiError, apiRequest } from "@/lib/api";
import { LatestWinsSaver, type SaveState } from "@/lib/latestWins";
import { SEARCH_LINKS_HEADING, SEARCH_LINKS_WARNING, type SearchLink, sourceLine, visibleSearchLinks } from "@/lib/searchLinks";
import { mondayOfThisWeekKST } from "@/lib/week";
import {
  type PlanTask,
  WEEKDAY_OPTIONS,
  type Weekday,
  completionCounts,
  formatHoursMinutes,
  listWeekStarts,
  neighborWeek,
  pickInitialWeek,
  tasksOfWeek,
  toWeekday,
  totalMinutes,
  weekOffset,
  weekRangeLabel,
  weekRelationLabel,
} from "@/lib/weekPlan";

type GoalDetail = {
  id: string;
  course: string;
  weekly_hours: number;
  current_level_name: string;
  target_level_name: string;
  advice_title: string | null;
  advice_content: string | null;
};
type Reference = { title: string; category: string; source_name: string | null; url: string | null; is_verified: boolean };
type ReferencesResult = { references: Reference[]; references_notice: string | null; search_links: SearchLink[] };
type LoadStatus = "loading" | "ready" | "error";

export function WeeklyPlanScreen({ onOpenPath }: { onOpenPath: () => void }) {
  const { session } = useAuth();
  const goalSwitch = useGoalSwitch();
  const { loaded, goals, activeGoalId } = goalSwitch;
  const hasActiveGoals = goals.some((g) => g.status === "active");
  const goalId = activeGoalId && goals.some((g) => g.id === activeGoalId && g.status === "active") ? activeGoalId : null;

  const [status, setStatus] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [goal, setGoal] = useState<GoalDetail | null>(null);
  const [tasks, setTasks] = useState<PlanTask[]>([]);
  const [refs, setRefs] = useState<ReferencesResult | null>(null);
  const [refsError, setRefsError] = useState(false);
  const [week, setWeek] = useState<string | null>(null);
  // The weekday the user picked per task. It stays on screen even if saving fails (nothing is
  // rolled back to the server value), and is the source of truth for the select elements.
  const [chosen, setChosen] = useState<Record<string, Weekday>>({});
  const [save, setSave] = useState<SaveState>({ status: "idle", failedKeys: [] });
  const [reloadKey, setReloadKey] = useState(0);
  const saverRef = useRef<LatestWinsSaver<Weekday> | null>(null);

  // The saver is created once; it only needs the session token at send time.
  const sessionRef = useRef(session);
  sessionRef.current = session;
  if (saverRef.current === null) {
    saverRef.current = new LatestWinsSaver<Weekday>(
      async (taskId, value) => {
        const token = await sessionRef.current!.getToken();
        await apiRequest(`/api/tasks/${encodeURIComponent(taskId)}`, {
          method: "PATCH",
          token,
          body: { suggested_weekday: value },
        });
      },
      (state) => setSave(state),
    );
  }

  useEffect(() => {
    if (!session || !loaded) return;
    if (!goalId) {
      setStatus("ready");
      setGoal(null);
      setTasks([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setStatus("loading");
      setLoadError(null);
      try {
        const token = await session.getToken();
        const [goalDetail, taskList] = await Promise.all([
          apiRequest<GoalDetail>(`/api/goals/${encodeURIComponent(goalId)}`, { token }),
          apiRequest<PlanTask[]>(`/api/tasks?goal_id=${encodeURIComponent(goalId)}`, { token }),
        ]);
        let refResult: ReferencesResult | null = null;
        let refFailed = false;
        try {
          refResult = await apiRequest<ReferencesResult>(`/api/goals/${encodeURIComponent(goalId)}/references`, { token });
        } catch {
          refFailed = true; // the side card says so; the plan itself still shows
        }
        if (cancelled) return;
        setGoal(goalDetail);
        setTasks(taskList);
        setRefs(refResult);
        setRefsError(refFailed);
        setChosen({});
        setWeek(pickInitialWeek(listWeekStarts(taskList), mondayOfThisWeekKST()));
        setStatus("ready");
      } catch (e) {
        if (cancelled) return;
        setLoadError(e instanceof ApiError ? e.message : "계획을 불러오지 못했습니다.");
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, loaded, goalId, reloadKey]);

  const thisWeek = mondayOfThisWeekKST();
  const weeks = useMemo(() => listWeekStarts(tasks), [tasks]);
  const weekTasks = useMemo(() => tasksOfWeek(tasks, week), [tasks, week]);
  const overall = completionCounts(tasks);
  const weekMinutes = totalMinutes(weekTasks);
  const relation = week ? weekRelationLabel(weekOffset(week, thisWeek)) : "";

  function changeWeekday(taskId: string, raw: string) {
    const value = toWeekday(raw);
    setChosen((prev) => ({ ...prev, [taskId]: value }));
    saverRef.current!.set(taskId, value);
  }

  const switcher = (
    <>
      <GoalSwitch goals={goals} activeGoalId={activeGoalId} busy={goalSwitch.switching} onSelect={goalSwitch.switchGoal} />
      {goalSwitch.error && (
        <p className="error" role="alert">
          {goalSwitch.error}
        </p>
      )}
    </>
  );

  const saveButton = (
    <button
      type="button"
      className="btn secondary"
      onClick={() => saverRef.current!.retry()}
      disabled={save.status !== "error"}
      aria-live="polite"
    >
      {save.status === "saving" ? "저장 중…" : save.status === "error" ? "저장하지 못했어요. 다시 시도" : "계획 저장됨 ✓"}
    </button>
  );

  const heading = (
    <div className="heading">
      <div>
        <p className="kicker">WEEKLY LEARNING PLAN</p>
        <h1>주간 학습 계획</h1>
        <p>이번 주 목표와 과제를 정하고, 편한 요일에 학습하세요.</p>
      </div>
      {status === "ready" && goal && tasks.length > 0 && saveButton}
    </div>
  );

  if (!loaded) {
    return (
      <>
        {heading}
        <section className="card">
          <p className="description">불러오는 중…</p>
        </section>
      </>
    );
  }

  if (!hasActiveGoals) {
    return (
      <>
        {heading}
        <section className="card">
          <h2>진행 중인 학습이 없어요</h2>
          <p className="description">학습 경로를 만들면 주차별 과제와 추천 요일을 이곳에서 볼 수 있어요.</p>
          <button type="button" className="btn" onClick={onOpenPath}>
            학습 경로 설정으로 이동
          </button>
        </section>
      </>
    );
  }

  if (!goalId) {
    return (
      <>
        {switcher}
        {heading}
        <section className="card">
          <h2>보고 싶은 학습을 선택해 주세요</h2>
          <p className="description">위의 “현재 학습”에서 학습을 고르면 그 학습의 주간 계획이 나타나요.</p>
        </section>
      </>
    );
  }

  if (status === "loading") {
    return (
      <>
        {switcher}
        {heading}
        <section className="card">
          <p className="description">계획을 불러오는 중…</p>
        </section>
      </>
    );
  }

  if (status === "error" || !goal) {
    return (
      <>
        {switcher}
        {heading}
        <section className="card">
          <p className="error" role="alert">
            {loadError}
          </p>
          <button type="button" className="btn" onClick={() => setReloadKey((k) => k + 1)}>
            다시 시도
          </button>
        </section>
      </>
    );
  }

  if (tasks.length === 0) {
    return (
      <>
        {switcher}
        {heading}
        <section className="card">
          <h2>{goal.course}</h2>
          <p className="description">이 학습에는 아직 과제가 없어요. 학습 경로 설정에서 계획을 만들면 이곳에 나타나요.</p>
          <button type="button" className="btn" onClick={onOpenPath}>
            학습 경로 설정으로 이동
          </button>
        </section>
      </>
    );
  }

  const prevWeek = week ? neighborWeek(weeks, week, "prev") : null;
  const nextWeek = week ? neighborWeek(weeks, week, "next") : null;
  const hasAdvice = goal.advice_title !== null && goal.advice_content !== null;

  return (
    <>
      {switcher}
      {heading}
      {save.status === "error" && (
        <p className="error" role="alert">
          요일 변경을 저장하지 못했어요. 고른 요일은 그대로 두었어요. 위의 “다시 시도”를 눌러 주세요.
        </p>
      )}
      <div className="grid columns">
        <section className="card">
          <div className="card-head">
            <div>
              <h2>{goal.course}</h2>
              <p>
                현재 {goal.current_level_name} → 목표 {goal.target_level_name} · 주 {goal.weekly_hours}시간
              </p>
            </div>
            {week && (
              <span className="pill blue">
                {weekRangeLabel(week)} · {relation}
              </span>
            )}
          </div>
          <div className="week-nav">
            <button type="button" className="btn secondary small" disabled={!prevWeek} onClick={() => prevWeek && setWeek(prevWeek)}>
              ← 이전 주
            </button>
            <button type="button" className="btn secondary small" disabled={!nextWeek} onClick={() => nextWeek && setWeek(nextWeek)}>
              다음 주 →
            </button>
          </div>
          <div className="bar" role="progressbar" aria-valuenow={overall.percent} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${overall.percent}%` }}></span>
          </div>
          <div className="bar-label">
            <span>
              {relation} 예상 {formatHoursMinutes(weekMinutes)} · 목표 {goal.weekly_hours}시간
            </span>
            <b>
              {overall.done} / {overall.total} 전체 과업 완료
            </b>
          </div>
          {weekTasks.map((t) => {
            const value = chosen[t.id] ?? toWeekday(t.suggested_weekday);
            return (
              <div key={t.id} className="wbs-row">
                <div>
                  <span className="wbs-date">추천 요일</span>
                  <select
                    className="weekday-select"
                    aria-label={`${t.title} 추천 요일`}
                    value={value}
                    onChange={(e) => changeWeekday(t.id, e.target.value)}
                  >
                    {WEEKDAY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <strong>{t.title}</strong>
                  <p>
                    {t.description ? `${t.description} · ` : ""}예상 {t.estimated_minutes}분
                  </p>
                </div>
                <span className={`pill ${t.status === "completed" ? "green" : "gray"}`}>{t.status === "completed" ? "완료" : "미완료"}</span>
              </div>
            );
          })}
          <p className="small muted">추천 요일은 참고용입니다. 요일을 바꾸거나 지정하지 않아도 과제는 이번 주 계획에 남습니다.</p>
        </section>

        <aside>
          <section className="card">
            <h2>AI 학습 조언</h2>
            {hasAdvice ? (
              <>
                <p className="advice-title">{goal.advice_title}</p>
                <p className="small muted" style={{ whiteSpace: "pre-wrap" }}>
                  {goal.advice_content}
                </p>
                <p className="small muted">AI 생성 · 참고용</p>
              </>
            ) : (
              <p className="small muted">
                주 {goal.weekly_hours}시간 안에서 가능한 날에 나누어 공부해 보세요. 하루를 놓쳐도 과제는 미완료 상태로 이번 주 계획에 남고,
                원하는 날로 옮길 수 있습니다.
              </p>
            )}
          </section>
          <section className="card" style={{ marginTop: 13 }}>
            <h2>연결된 참고자료</h2>
            {refsError && <p className="small muted">참고자료를 불러오지 못했어요. 잠시 후 다시 열어 주세요.</p>}
            {refs && refs.references.length > 0 &&
              refs.references.map((r) => (
                <div key={r.title} className="resource">
                  <strong>{r.title}</strong>
                  <p>{sourceLine(r.source_name, r.category)}</p>
                  {r.url && (
                    <a href={r.url} target="_blank" rel="noreferrer">
                      원문 보기 ↗
                    </a>
                  )}
                </div>
              ))}
            {refs && refs.references.length === 0 && (
              <p className="small muted" style={{ whiteSpace: "pre-line" }}>
                {refs.references_notice}
              </p>
            )}
            {refs && visibleSearchLinks(refs.search_links).length > 0 && (
              <div className="search-links-block">
                <h3>{SEARCH_LINKS_HEADING}</h3>
                {visibleSearchLinks(refs.search_links).map((l) => (
                  <div key={l.url} className="resource">
                    <a href={l.url} target="_blank" rel="noreferrer">
                      {l.label} ↗
                    </a>
                  </div>
                ))}
                <p className="small muted">{SEARCH_LINKS_WARNING}</p>
              </div>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
