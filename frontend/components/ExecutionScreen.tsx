"use client";

import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { type GoalOption, GoalSwitch } from "@/components/GoalSwitch";
import { ApiError, apiRequest, apiRequestWithHeaders } from "@/lib/api";
import { taskToSelectForTimer, timerLocation } from "@/lib/timerSelection";
import { todayKSTDateString } from "@/lib/week";

type Weekday = "none" | "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
type TaskItem = {
  id: string;
  title: string;
  estimated_minutes: number;
  suggested_weekday: Weekday;
  status: string;
  record_count: number;
  total_minutes: number;
};
type Reflection = { content: string; tags: string[] };
type StudyLog = {
  id: string;
  task_id: string;
  study_date: string;
  minutes: number;
  activity: string;
  started_at: string | null;
  ended_at: string | null;
  reflection: Reflection | null;
};
type ActiveTimer = { active: boolean; task_id: string | null; goal_id: string | null; started_at: string | null };

type Period = "week" | "all";
type LoadStatus = "loading" | "ready" | "error";

function newRequestId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatElapsed(startedAt: string | null, tick: number): string {
  void tick; // re-render trigger only
  if (!startedAt) return "00:00:00";
  const totalSec = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  const h = String(Math.floor(totalSec / 3600)).padStart(2, "0");
  const m = String(Math.floor((totalSec % 3600) / 60)).padStart(2, "0");
  const s = String(totalSec % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

export function ExecutionScreen() {
  const { session } = useAuth();
  const [period, setPeriod] = useState<Period>("week");
  const [tasks, setTasks] = useState<TaskItem[] | null>(null);
  const [logs, setLogs] = useState<StudyLog[] | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [timer, setTimer] = useState<ActiveTimer | null>(null);
  const [tick, setTick] = useState(0);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const mode: "new" | "edit" = selectedLogId ? "edit" : "new";

  const [date, setDate] = useState(todayKSTDateString());
  const [minutes, setMinutes] = useState(30);
  const [activity, setActivity] = useState("");
  const [reflection, setReflection] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [confirmingCancelTimer, setConfirmingCancelTimer] = useState(false);
  const [requestId, setRequestId] = useState(newRequestId());
  const [logsTruncated, setLogsTruncated] = useState(false);
  const [goals, setGoals] = useState<GoalOption[]>([]);
  const [activeGoalId, setActiveGoalId] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

  async function load() {
    if (!session) return;
    setLoadStatus("loading");
    setLoadError(null);
    try {
      const token = await session.getToken();
      const [profile, goalList] = await Promise.all([
        apiRequest<{ active_goal_id: string | null }>("/api/user/profile", { token }),
        apiRequest<GoalOption[]>("/api/goals", { token }),
      ]);
      const [taskList, logsResult, active] = await Promise.all([
        profile.active_goal_id
          ? apiRequest<TaskItem[]>(`/api/tasks?goal_id=${encodeURIComponent(profile.active_goal_id)}`, { token })
          : Promise.resolve([] as TaskItem[]),
        // Only the current learning's records, so the stats don't mix in other learnings.
        apiRequestWithHeaders<StudyLog[]>(
          profile.active_goal_id
            ? `/api/study-logs?period=${period}&goal_id=${encodeURIComponent(profile.active_goal_id)}`
            : `/api/study-logs?period=${period}`,
          { token },
        ),
        apiRequest<ActiveTimer>("/api/timer/active", { token }),
      ]);
      setGoals(goalList);
      setActiveGoalId(profile.active_goal_id);
      setTasks(taskList);
      setLogs(logsResult.data);
      setLogsTruncated(logsResult.headers.get("x-study-logs-truncated") === "true");
      setTimer(active);
      // F3: a timer still running on the server must be visible after a refresh or after
      // switching away and back, so its task is selected unless the user already picked one.
      const timerTask = taskToSelectForTimer(active, profile.active_goal_id, taskList.map((t) => t.id));
      if (timerTask) setSelectedTaskId((prev) => prev ?? timerTask);
      setLoadStatus("ready");
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : "불러오지 못했습니다.");
      setLoadStatus("error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, period]);

  useEffect(() => {
    if (!timer?.active) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [timer?.active]);

  const logsByTask = useMemo(() => {
    const map: Record<string, StudyLog[]> = {};
    (logs ?? []).forEach((l) => {
      (map[l.task_id] ??= []).push(l);
    });
    return map;
  }, [logs]);

  function resetFormForNew(taskId: string) {
    setSelectedTaskId(taskId);
    setSelectedLogId(null);
    setDate(todayKSTDateString());
    setMinutes(30);
    setActivity("");
    setReflection("");
    setTags("");
    setSaveError(null);
    setRequestId(newRequestId());
  }

  function loadFormForEdit(log: StudyLog) {
    setSelectedTaskId(log.task_id);
    setSelectedLogId(log.id);
    setDate(log.study_date);
    setMinutes(log.minutes);
    setActivity(log.activity);
    setReflection(log.reflection?.content ?? "");
    setTags((log.reflection?.tags ?? []).join(", "));
    setSaveError(null);
  }

  function cancelEdit() {
    if (selectedLogId) {
      const log = (logs ?? []).find((l) => l.id === selectedLogId);
      if (log) loadFormForEdit(log); // roll back to the saved values
    } else if (selectedTaskId) {
      resetFormForNew(selectedTaskId);
    }
  }

  async function save() {
    if (!session || !selectedTaskId || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const token = await session.getToken();
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const reflectionPayload = reflection.trim() ? { content: reflection.trim(), tags: tagList } : null;
      if (mode === "new") {
        await apiRequest("/api/study-logs", {
          method: "POST",
          token,
          body: { task_id: selectedTaskId, study_date: date, minutes, activity, reflection: reflectionPayload, client_request_id: requestId },
        });
      } else {
        await apiRequest(`/api/study-logs/${selectedLogId}`, {
          method: "PATCH",
          token,
          body: reflectionPayload
            ? { study_date: date, minutes, activity, reflection: reflectionPayload }
            : { study_date: date, minutes, activity, delete_reflection: true },
        });
      }
      const taskId = selectedTaskId;
      await load();
      resetFormForNew(taskId);
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : "저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete(log: StudyLog) {
    if (!session) return;
    try {
      const token = await session.getToken();
      await apiRequest(`/api/study-logs/${log.id}`, { method: "DELETE", token });
      setConfirmingDeleteId(null);
      const taskId = log.task_id;
      await load();
      if (selectedLogId === log.id) resetFormForNew(taskId);
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : "삭제하지 못했습니다.");
    }
  }

  async function startTimer() {
    if (!session || !selectedTaskId) return;
    setSaveError(null);
    try {
      const token = await session.getToken();
      const result = await apiRequest<ActiveTimer>("/api/timer/start", {
        method: "POST",
        token,
        body: { task_id: selectedTaskId, client_request_id: newRequestId() },
      });
      setTimer(result);
    } catch (error) {
      if (error instanceof ApiError && error.code === "TIMER_ALREADY_RUNNING") {
        // The screen's timer state was stale; refresh it so the "go to it" button appears.
        try {
          const token = await session.getToken();
          setTimer(await apiRequest<ActiveTimer>("/api/timer/active", { token }));
        } catch {
          // keep the message below even if the refresh fails
        }
        setSaveError("이미 진행 중인 타이머가 있어요. 아래 버튼으로 해당 과제로 이동해 먼저 종료하거나 취소해 주세요.");
      } else {
        setSaveError(error instanceof ApiError ? error.message : "타이머를 시작하지 못했습니다.");
      }
    }
  }

  async function finishTimer() {
    if (!session) return;
    setSaving(true);
    setSaveError(null);
    try {
      const token = await session.getToken();
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await apiRequest("/api/timer/finish", {
        method: "POST",
        token,
        body: {
          activity: activity.trim() || "학습 진행",
          reflection: reflection.trim() ? { content: reflection.trim(), tags: tagList } : null,
          client_request_id: requestId,
        },
      });
      const taskId = selectedTaskId;
      setTimer({ active: false, task_id: null, goal_id: null, started_at: null });
      await load();
      if (taskId) resetFormForNew(taskId);
    } catch (error) {
      if (error instanceof ApiError && error.code === "TIMER_TASK_GONE") {
        // The server already cleared the dangling timer; reflect that locally too.
        setTimer({ active: false, task_id: null, goal_id: null, started_at: null });
        setSaveError("타이머가 연결된 과제가 삭제되어 타이머가 정리되었습니다.");
      } else {
        setSaveError(error instanceof ApiError ? error.message : "타이머 저장에 실패했습니다.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function cancelTimer() {
    if (!session) return;
    try {
      const token = await session.getToken();
      await apiRequest("/api/timer/cancel", { method: "POST", token, body: {} });
      setTimer({ active: false, task_id: null, goal_id: null, started_at: null });
      setConfirmingCancelTimer(false);
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : "타이머를 취소하지 못했습니다.");
    }
  }

  // Switching does not touch a running timer; the timer keeps belonging to its own learning.
  async function switchGoal(goalId: string) {
    if (!session || goalId === activeGoalId || switching) return;
    setSwitching(true);
    setSwitchError(null);
    try {
      const token = await session.getToken();
      await apiRequest("/api/user/profile", { method: "PATCH", token, body: { active_goal_id: goalId } });
      setSelectedTaskId(null);
      setSelectedLogId(null);
      setConfirmingDeleteId(null);
      setConfirmingCancelTimer(false);
      setSaveError(null);
      await load();
    } catch (error) {
      setSwitchError(error instanceof ApiError ? error.message : "학습을 전환하지 못했습니다.");
    } finally {
      setSwitching(false);
    }
  }

  const weeklyMinutes = (logs ?? []).reduce((sum, l) => sum + l.minutes, 0);
  const recordCount = (logs ?? []).length;
  const activeTaskCount = (tasks ?? []).filter((t) => t.status !== "completed").length;
  const weeklyTargetMinutes = (tasks ?? []).reduce((sum, t) => sum + t.estimated_minutes, 0) || 1;
  const weeklyPercent = Math.min(100, Math.round((weeklyMinutes / weeklyTargetMinutes) * 100));

  const timerRunsHere = timer?.active && timer.task_id === selectedTaskId;
  const timerRunsElsewhere = timer?.active && timer.task_id !== selectedTaskId;
  const location = timerLocation(timer, activeGoalId, selectedTaskId);

  // Jump to the running timer: same learning -> select its task; another learning -> switch
  // back to it (the reload then auto-selects the task).
  function goToTimerTask() {
    if (!timer?.active || !timer.task_id) return;
    if (timer.goal_id && timer.goal_id !== activeGoalId) {
      switchGoal(timer.goal_id);
      return;
    }
    resetFormForNew(timer.task_id);
  }

  const timerGoal = timer?.active && timer.goal_id && timer.goal_id !== activeGoalId ? goals.find((g) => g.id === timer.goal_id) : null;
  const switcher = (
    <>
      <GoalSwitch goals={goals} activeGoalId={activeGoalId} busy={switching} onSelect={switchGoal} />
      {switchError && (
        <p className="error" role="alert">
          {switchError}
        </p>
      )}
      {timer?.active && timer.goal_id && timer.goal_id !== activeGoalId && (
        <p className="small muted" role="status">
          진행 중인 타이머는 {timerGoal ? `'${timerGoal.course}'` : "다른"} 학습의 과제입니다. 그 학습으로 전환하면 종료하거나 취소할 수 있어요.{" "}
          <button type="button" className="link-btn" onClick={goToTimerTask} disabled={switching}>
            그 학습으로 돌아가기
          </button>
        </p>
      )}
      {location === "other-task-same-goal" && (
        <p className="small muted" role="status">
          다른 과제의 타이머가 진행 중입니다.{" "}
          <button type="button" className="link-btn" onClick={goToTimerTask}>
            진행 중인 과제로 이동
          </button>
        </p>
      )}
    </>
  );

  const heading = (
    <div className="heading">
      <div>
        <p className="kicker">STUDY EXECUTION</p>
        <h1>학습 실행 기록</h1>
        <p>과제별 실행 기록과 진행현황을 확인하고, 새 기록을 남기거나 기존 기록을 수정합니다.</p>
      </div>
    </div>
  );

  if (loadStatus === "loading") {
    return (
      <>
        {heading}
        <section className="card">
          <p className="description">불러오는 중…</p>
        </section>
      </>
    );
  }

  if (loadStatus === "error") {
    return (
      <>
        {heading}
        <section className="card">
          <p className="error" role="alert">
            {loadError}
          </p>
          <button className="btn" onClick={load}>
            다시 시도
          </button>
        </section>
      </>
    );
  }

  if (!tasks || tasks.length === 0) {
    return (
      <>
        {switcher}
        {heading}
        <section className="card">
          <h2>학습 과제가 없습니다</h2>
          <p className="description">학습 경로를 만들어 과제를 먼저 확정해 주세요.</p>
        </section>
      </>
    );
  }

  return (
    <>
      {switcher}
      {heading}
      <div className="grid stats">
        <article className="card stat">
          <div>
            <label>{period === "week" ? "이번 주 학습시간" : "전체 학습시간"}</label>
            <strong>
              {weeklyMinutes} <small>분</small>
            </strong>
            <small>{period === "week" ? `주 목표 ${weeklyTargetMinutes}분` : "전체 기간"}</small>
          </div>
          <span className="stat-icon">◷</span>
        </article>
        <article className="card stat">
          <div>
            <label>학습 기록</label>
            <strong>
              {recordCount} <small>건</small>
            </strong>
            <small>{period === "week" ? "이번 주 기록" : "전체 기간 기록"}</small>
          </div>
          <span className="stat-icon">↗</span>
        </article>
        <article className="card stat">
          <div>
            <label>진행 중인 과제</label>
            <strong>
              {activeTaskCount} <small>개</small>
            </strong>
            <small>전체 학습 과제 {tasks.length}개</small>
          </div>
          <span className="stat-icon">▦</span>
        </article>
        <article className="card stat">
          <div>
            <label>주간 목표 달성</label>
            <strong>
              {weeklyPercent} <small>%</small>
            </strong>
            <small>
              {weeklyMinutes}분 / {weeklyTargetMinutes}분
            </small>
          </div>
          <span className="stat-icon">◎</span>
        </article>
      </div>

      {/* Phase 6.9 builds the real insight; until then the slot is visible but inactive. */}
      <section className="card insight-card">
        <div className="insight-mark">✦</div>
        <div className="insight-copy">
          <div className="insight-heading">
            <div>
              <p className="kicker">AI LEARNING INSIGHT</p>
              <h2>기록에서 찾은 이번 주 학습 인사이트</h2>
            </div>
            <button type="button" className="btn secondary small" disabled aria-disabled="true">
              인사이트 갱신 (준비 중)
            </button>
          </div>
          <p>기록과 회고를 바탕으로 한 학습 인사이트가 준비 중입니다.</p>
          <small>내 실행 기록과 회고 기반 · AI 생성 안내</small>
        </div>
      </section>

      <div className="grid columns execution-layout">
        <section className="card">
          <div className="card-head">
            <div>
              <h2>과제별 학습 기록</h2>
              <p>과제 하나에 여러 기록을 쌓고 진행 상황을 확인합니다.</p>
            </div>
            <select className="searchbar" value={period} onChange={(e) => setPeriod(e.target.value as Period)} aria-label="기간 선택">
              <option value="week">이번 주</option>
              <option value="all">전체 기간</option>
            </select>
          </div>
          {saveError && (
            <p className="error" role="alert">
              {saveError}
            </p>
          )}
          {logsTruncated && <p className="small muted">최근 200건만 표시됩니다.</p>}
          <div className="activity-list">
          {tasks.map((task) => (
            <article key={task.id} className="task-record-group">
              <div className="task-record-head">
                <div>
                  <h3>{task.title}</h3>
                  <div className="task-record-meta">
                    계획 {task.estimated_minutes}분 · 누적 {task.total_minutes}분 · 기록 {task.record_count}건
                  </div>
                </div>
                <div className="task-record-controls">
                  <span className={`pill ${task.status === "completed" ? "green" : "blue"}`}>
                    {task.status === "completed" ? "완료" : "진행 중"}
                  </span>
                  <button type="button" className="btn secondary small task-select" onClick={() => resetFormForNew(task.id)}>
                    이 과제로 기록
                  </button>
                </div>
              </div>
              <div className="task-progress-line">
                <span style={{ width: `${Math.min(100, Math.round((task.total_minutes / Math.max(1, task.estimated_minutes)) * 100))}%` }}></span>
              </div>
              <div className="task-records">
              {(logsByTask[task.id] ?? []).map((log) => (
                <div key={log.id} className={`record-entry${selectedLogId === log.id ? " selected" : ""}`}>
                  <button type="button" className="record-select" onClick={() => loadFormForEdit(log)}>
                    <strong>
                      {log.activity} · {log.minutes}분
                    </strong>
                    <small>
                      {log.study_date} · 회고: {log.reflection?.content ?? "없음"}
                    </small>
                  </button>
                  {confirmingDeleteId === log.id ? (
                    <span className="inline-confirm">
                      정말 삭제할까요?
                      <button type="button" className="link-btn" onClick={() => confirmDelete(log)}>
                        삭제
                      </button>
                      <button type="button" className="link-btn" onClick={() => setConfirmingDeleteId(null)}>
                        취소
                      </button>
                    </span>
                  ) : (
                    <button type="button" className="record-delete" onClick={() => setConfirmingDeleteId(log.id)}>
                      삭제
                    </button>
                  )}
                </div>
              ))}
              {(logsByTask[task.id] ?? []).length === 0 && <p className="small muted">아직 기록이 없습니다.</p>}
              </div>
            </article>
          ))}
          </div>
        </section>

        <section className="card record-editor">
          <div className="card-head">
            <div>
              <span className={`mode-pill${mode === "edit" ? " edit-mode" : ""}`}>
                {mode === "edit" ? "학습 기록 수정 중" : "새 학습 기록"}
              </span>
              <h2>{mode === "edit" ? "기록을 수정하세요" : "실행 내용을 기록하세요"}</h2>
              <p>과제를 선택하고 학습을 시작하거나 지난 기록을 직접 입력할 수 있어요.</p>
            </div>
          </div>
          <div className="field">
            <label htmlFor="record-task">학습 과제</label>
            <select
              id="record-task"
              value={selectedTaskId ?? ""}
              disabled={mode === "edit"}
              onChange={(e) => {
                if (e.target.value) resetFormForNew(e.target.value);
              }}
            >
              <option value="">과제를 선택하세요</option>
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </select>
          </div>
          {!selectedTaskId ? (
            <p className="small muted">위에서 과제를 고르거나 왼쪽 목록의 "이 과제로 기록"을 눌러 시작하세요.</p>
          ) : (
            <>
              {mode === "new" && (
                <div className="timer-panel">
                  <div>
                    <span className="timer-label">학습 타이머</span>
                    <strong>{timerRunsHere ? formatElapsed(timer?.started_at ?? null, tick) : "00:00:00"}</strong>
                    <span className="timer-status">
                      {timerRunsElsewhere
                        ? "다른 과제의 타이머가 진행 중입니다."
                        : timerRunsHere
                          ? "진행 중"
                          : "과제를 선택한 뒤 시작하세요"}
                    </span>
                  </div>
                  <div className="timer-actions">
                    {!timerRunsHere ? (
                      <button type="button" className="btn" onClick={startTimer} disabled={Boolean(timerRunsElsewhere)}>
                        학습 시작
                      </button>
                    ) : confirmingCancelTimer ? (
                      <span className="inline-confirm">
                        기록을 만들지 않고 취소할까요?
                        <button type="button" className="link-btn" onClick={cancelTimer}>
                          취소 확정
                        </button>
                        <button type="button" className="link-btn" onClick={() => setConfirmingCancelTimer(false)}>
                          아니요
                        </button>
                      </span>
                    ) : (
                      <>
                        <button type="button" className="btn danger" onClick={finishTimer} disabled={saving}>
                          학습 종료
                        </button>
                        <button type="button" className="btn secondary" onClick={() => setConfirmingCancelTimer(true)} disabled={saving}>
                          타이머 취소
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
              <p className="small muted">타이머 없이 지난 학습을 기록할 때는 날짜와 시간을 직접 입력해도 됩니다.</p>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="record-date">학습 날짜</label>
                  <input id="record-date" type="date" max={todayKSTDateString()} value={date} onChange={(e) => setDate(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="record-minutes">학습 시간(분)</label>
                  <input id="record-minutes" type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
                </div>
              </div>
              <div className="field">
                <label htmlFor="record-activity">실행 내용</label>
                <textarea id="record-activity" value={activity} onChange={(e) => setActivity(e.target.value)} placeholder="예: 반복문 예제 5개를 풀고 오답을 정리했어요." />
              </div>
              <div className="field">
                <label htmlFor="record-reflection">오늘의 회고 (선택)</label>
                <textarea id="record-reflection" value={reflection} onChange={(e) => setReflection(e.target.value)} placeholder="무엇이 쉬웠고, 무엇이 어려웠나요?" />
              </div>
              <div className="field">
                <label htmlFor="record-tags">
                  회고 태그 <span className="muted">(쉼표로 구분, 선택)</span>
                </label>
                <input id="record-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="예: 복습 필요, 자료형" />
              </div>
              <div className="record-actions" style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 10 }}>
                {mode === "edit" && (
                  <button type="button" className="btn secondary" onClick={cancelEdit} disabled={saving}>
                    수정 취소
                  </button>
                )}
                <button type="button" className="btn" onClick={save} disabled={saving || !activity.trim()}>
                  {saving ? "저장하는 중…" : mode === "edit" ? "변경사항 저장" : "기록 저장"}
                </button>
              </div>
              <p className="small muted">저장한 회고는 내 AI 튜터와 학습 인사이트에 활용됩니다.</p>
            </>
          )}
        </section>
      </div>
    </>
  );
}
