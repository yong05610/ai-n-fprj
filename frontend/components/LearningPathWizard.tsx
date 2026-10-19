"use client";

import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import { clearWizardDraft, loadWizardDraft, saveWizardDraft } from "@/lib/wizardStorage";
import { isMondayDateString, mondayOfThisWeekKST, todayKSTDateString } from "@/lib/week";

type LevelItem = { order: number; name: string; description: string };
type CourseItem = { id: string; title: string; description: string; levels: LevelItem[] };
type PathRecommendationResponse = { field: string; courses: CourseItem[]; suggested_roles: string[] };

type Weekday = "none" | "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
const WEEKDAY_LABEL: Record<Weekday, string> = {
  none: "선택 안 함",
  mon: "월요일",
  tue: "화요일",
  wed: "수요일",
  thu: "목요일",
  fri: "금요일",
  sat: "토요일",
  sun: "일요일",
};

type WeeklyTask = { title: string; description: string; estimated_minutes: number; suggested_weekday: Weekday };
type PlanGenerateResponse = {
  plan_week_start: string;
  plan_week_end: string;
  total_estimated_minutes: number;
  tasks: WeeklyTask[];
  advice: { title: string; content: string };
  references: { title: string; category: string; url: string | null; is_verified: boolean }[];
  references_notice: string | null;
};
type SavedTask = { id: string; title: string; estimated_minutes: number; suggested_weekday: string; status: string };

type PathStatus = "input" | "loading" | "ready" | "error";
type PlanStatus = "idle" | "loading" | "ready" | "error";
type ConfirmStatus = "idle" | "saving" | "done" | "error";

const AI_TIMEOUT_MS = 70_000; // server retries up to 3x a ~20s provider timeout; stay above that ceiling

type WizardSnapshot = {
  field: string;
  goal: string;
  recommendation: PathRecommendationResponse | null;
  courseId: string | null;
  courseTitle: string;
  courseDescription: string;
  selectedRole: string | null;
  currentOrder: number | null;
  currentLevelName: string;
  currentLevelDesc: string;
  targetOrder: number | null;
  targetLevelName: string;
  targetLevelDesc: string;
  weeklyHours: number;
  targetDate: string;
  planWeekStart: string;
  draft: PlanGenerateResponse | null;
  draftRecipeKey: string | null;
  tasks: WeeklyTask[];
  clientRequestId: string | null;
};

function newRequestId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function LearningPathWizard({ onClose }: { onClose: () => void }) {
  const { session } = useAuth();
  const restored = useMemo(() => loadWizardDraft<WizardSnapshot>(), []);

  // --- Step 1: path setup (분야 -> 과정/수준 추천 -> 선택, 이름 수정 가능) ---
  const [field, setField] = useState(restored?.field ?? "");
  const [goal, setGoal] = useState(restored?.goal ?? "");
  const [pathStatus, setPathStatus] = useState<PathStatus>("input");
  const [pathError, setPathError] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<PathRecommendationResponse | null>(restored?.recommendation ?? null);
  const [courseId, setCourseId] = useState<string | null>(restored?.courseId ?? null);
  const [courseTitle, setCourseTitle] = useState(restored?.courseTitle ?? "");
  const [courseDescription, setCourseDescription] = useState(restored?.courseDescription ?? "");
  const [selectedRole, setSelectedRole] = useState<string | null>(restored?.selectedRole ?? null);
  const [currentOrder, setCurrentOrder] = useState<number | null>(restored?.currentOrder ?? null);
  const [currentLevelName, setCurrentLevelName] = useState(restored?.currentLevelName ?? "");
  const [currentLevelDesc, setCurrentLevelDesc] = useState(restored?.currentLevelDesc ?? "");
  const [targetOrder, setTargetOrder] = useState<number | null>(restored?.targetOrder ?? null);
  const [targetLevelName, setTargetLevelName] = useState(restored?.targetLevelName ?? "");
  const [targetLevelDesc, setTargetLevelDesc] = useState(restored?.targetLevelDesc ?? "");
  const [weeklyHours, setWeeklyHours] = useState(restored?.weeklyHours ?? 7);
  const [targetDate, setTargetDate] = useState(restored?.targetDate ?? "");
  const [planWeekStart, setPlanWeekStart] = useState(restored?.planWeekStart ?? mondayOfThisWeekKST());

  const selectedCourse = useMemo(
    () => recommendation?.courses.find((c) => c.id === courseId) ?? null,
    [recommendation, courseId],
  );
  const targetLevelOptions = useMemo(
    () => selectedCourse?.levels.filter((l) => currentOrder == null || l.order > currentOrder) ?? [],
    [selectedCourse, currentOrder],
  );
  const onlyOneLevelInCourse = Boolean(selectedCourse && selectedCourse.levels.length < 2);

  function pickCourse(course: CourseItem) {
    setCourseId(course.id);
    setCourseTitle(course.title);
    setCourseDescription(course.description);
    const first = course.levels[0];
    const second = course.levels.find((l) => first && l.order > first.order) ?? first;
    setCurrentOrder(first?.order ?? null);
    setCurrentLevelName(first?.name ?? "");
    setCurrentLevelDesc(first?.description ?? "");
    setTargetOrder(second?.order ?? null);
    setTargetLevelName(second?.name ?? "");
    setTargetLevelDesc(second?.description ?? "");
  }

  function pickCurrentLevel(order: number) {
    setCurrentOrder(order);
    const lvl = selectedCourse?.levels.find((l) => l.order === order);
    setCurrentLevelName(lvl?.name ?? "");
    setCurrentLevelDesc(lvl?.description ?? "");
    if (targetOrder != null && targetOrder <= order) {
      const next = selectedCourse?.levels.find((l) => l.order > order) ?? null;
      setTargetOrder(next?.order ?? null);
      setTargetLevelName(next?.name ?? "");
      setTargetLevelDesc(next?.description ?? "");
    }
  }

  function pickTargetLevel(order: number) {
    setTargetOrder(order);
    const lvl = selectedCourse?.levels.find((l) => l.order === order);
    setTargetLevelName(lvl?.name ?? "");
    setTargetLevelDesc(lvl?.description ?? "");
  }

  async function recommend() {
    if (!session || !field.trim()) return;
    setPathStatus("loading");
    setPathError(null);
    try {
      const token = await session.getToken();
      const result = await apiRequest<PathRecommendationResponse>("/api/path/recommend", {
        method: "POST",
        token,
        timeoutMs: AI_TIMEOUT_MS,
        body: { field, goal: goal.trim() || undefined },
      });
      setRecommendation(result);
      if (result.courses[0]) pickCourse(result.courses[0]);
      setPathStatus("ready");
    } catch (error) {
      setPathError(error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.");
      setPathStatus("error");
    }
  }

  // --- Step 2: plan draft (초안, 미저장) ---
  const [planStatus, setPlanStatus] = useState<PlanStatus>("idle");
  const [planError, setPlanError] = useState<string | null>(null);
  const [draft, setDraft] = useState<PlanGenerateResponse | null>(restored?.draft ?? null);
  const [draftRecipeKey, setDraftRecipeKey] = useState<string | null>(restored?.draftRecipeKey ?? null);
  const [tasks, setTasks] = useState<WeeklyTask[]>(restored?.tasks ?? []);
  const [activeTab, setActiveTab] = useState<"tasks" | "advice" | "refs">("tasks");
  const [clientRequestId, setClientRequestId] = useState<string | null>(restored?.clientRequestId ?? null);

  const currentRecipeKey = useMemo(
    () =>
      JSON.stringify([
        recommendation?.field,
        courseTitle,
        courseDescription,
        selectedRole,
        currentOrder,
        currentLevelName,
        currentLevelDesc,
        targetOrder,
        targetLevelName,
        targetLevelDesc,
        weeklyHours,
        targetDate,
        planWeekStart,
      ]),
    [
      recommendation,
      courseTitle,
      courseDescription,
      selectedRole,
      currentOrder,
      currentLevelName,
      currentLevelDesc,
      targetOrder,
      targetLevelName,
      targetLevelDesc,
      weeklyHours,
      targetDate,
      planWeekStart,
    ],
  );
  const isDraftStale = draft != null && draftRecipeKey != null && draftRecipeKey !== currentRecipeKey;

  const planWeekStartIsMonday = isMondayDateString(planWeekStart);

  async function generatePlan() {
    if (!session || !recommendation || !selectedCourse || currentOrder == null || targetOrder == null || !targetDate) return;
    if (!planWeekStartIsMonday) return;
    setPlanStatus("loading");
    setPlanError(null);
    try {
      const token = await session.getToken();
      const result = await apiRequest<PlanGenerateResponse>("/api/plan/generate", {
        method: "POST",
        token,
        timeoutMs: AI_TIMEOUT_MS,
        body: {
          field: recommendation.field,
          course: courseTitle,
          selected_role: selectedRole,
          current_level_order: currentOrder,
          current_level_name: currentLevelName,
          current_level_description: currentLevelDesc,
          target_level_order: targetOrder,
          target_level_name: targetLevelName,
          target_level_description: targetLevelDesc,
          weekly_hours: weeklyHours,
          target_date: targetDate,
          plan_week_start: planWeekStart,
        },
      });
      setDraft(result);
      setDraftRecipeKey(currentRecipeKey);
      setTasks(result.tasks);
      setClientRequestId(newRequestId());
      setActiveTab("tasks");
      setPlanStatus("ready");
    } catch (error) {
      setPlanError(error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.");
      setPlanStatus("error");
    }
  }

  const totalMinutes = tasks.reduce((sum, t) => sum + (t.estimated_minutes || 0), 0);
  const overBudget = totalMinutes > weeklyHours * 60;

  function updateTask(index: number, patch: Partial<WeeklyTask>) {
    setTasks((prev) => prev.map((t, i) => (i === index ? { ...t, ...patch } : t)));
  }
  function removeTask(index: number) {
    setTasks((prev) => prev.filter((_, i) => i !== index));
  }
  function addTask() {
    setTasks((prev) => [...prev, { title: "", description: "", estimated_minutes: 30, suggested_weekday: "none" }]);
  }

  // --- Step 3: confirm (목표+과제 저장) ---
  const [confirmStatus, setConfirmStatus] = useState<ConfirmStatus>("idle");
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [savedTasks, setSavedTasks] = useState<SavedTask[] | null>(null);
  const [savedGoalField, setSavedGoalField] = useState<string>("");

  const tasksAreValid = tasks.length > 0 && tasks.every((t) => t.title.trim() && t.estimated_minutes > 0);
  const canConfirm = Boolean(draft) && !isDraftStale && !overBudget && tasksAreValid;

  async function confirmPlan() {
    if (!session || !recommendation || !selectedCourse || currentOrder == null || targetOrder == null || !draft || !canConfirm) {
      return;
    }
    setConfirmStatus("saving");
    setConfirmError(null);
    try {
      const token = await session.getToken();
      const result = await apiRequest<{ goal: { id: string }; tasks: unknown[] }>("/api/plan/confirm", {
        method: "POST",
        token,
        body: {
          field: recommendation.field,
          course: courseTitle,
          current_level_order: currentOrder,
          current_level_name: currentLevelName,
          current_level_description: currentLevelDesc,
          target_level_order: targetOrder,
          target_level_name: targetLevelName,
          target_level_description: targetLevelDesc,
          weekly_hours: weeklyHours,
          target_date: targetDate,
          plan_week_start: draft.plan_week_start,
          tasks,
          client_request_id: clientRequestId,
        },
      });
      setSavedGoalField(recommendation.field);
      try {
        const reloaded = await apiRequest<SavedTask[]>(
          `/api/tasks?goal_id=${encodeURIComponent(result.goal.id)}&plan_week_start=${encodeURIComponent(draft.plan_week_start)}`,
          { token },
        );
        setSavedTasks(reloaded);
      } catch {
        setSavedTasks(null); // save itself already succeeded; the confirmation screen just won't list tasks
      }
      clearWizardDraft();
      setConfirmStatus("done");
    } catch (error) {
      setConfirmError(error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.");
      setConfirmStatus("error");
    }
  }

  // Persist the in-progress wizard (P4-7): survives refresh/navigation until confirmed or cleared.
  useEffect(() => {
    if (confirmStatus === "done") return;
    const snapshot: WizardSnapshot = {
      field,
      goal,
      recommendation,
      courseId,
      courseTitle,
      courseDescription,
      selectedRole,
      currentOrder,
      currentLevelName,
      currentLevelDesc,
      targetOrder,
      targetLevelName,
      targetLevelDesc,
      weeklyHours,
      targetDate,
      planWeekStart,
      draft,
      draftRecipeKey,
      tasks,
      clientRequestId,
    };
    saveWizardDraft(snapshot);
  }, [
    field,
    goal,
    recommendation,
    courseId,
    courseTitle,
    courseDescription,
    selectedRole,
    currentOrder,
    currentLevelName,
    currentLevelDesc,
    targetOrder,
    targetLevelName,
    targetLevelDesc,
    weeklyHours,
    targetDate,
    planWeekStart,
    draft,
    draftRecipeKey,
    tasks,
    clientRequestId,
    confirmStatus,
  ]);

  function handleClose() {
    const hasProgress = recommendation != null || draft != null;
    if (hasProgress && confirmStatus !== "done") {
      const ok = window.confirm("작성 중인 학습 경로·계획이 있습니다. 저장하지 않고 홈으로 돌아갈까요?");
      if (!ok) return;
    }
    onClose();
  }

  if (confirmStatus === "done") {
    return (
      <section className="card">
        <p className="eyebrow">PACEMATE · PLAN SAVED</p>
        <h2>학습 계획이 저장되었습니다.</h2>
        <p className="description">
          {savedGoalField} 목표와 이번 주 과제가 저장되어 언제든 다시 확인할 수 있습니다.
        </p>
        {savedTasks && savedTasks.length > 0 && (
          <ul>
            {savedTasks.map((t) => (
              <li key={t.id}>
                {t.title} · {t.estimated_minutes}분
                {t.suggested_weekday !== "none" && ` · ${WEEKDAY_LABEL[t.suggested_weekday as Weekday]}`}
              </li>
            ))}
          </ul>
        )}
        <button className="btn" onClick={onClose}>
          홈으로 돌아가기
        </button>
      </section>
    );
  }

  return (
    <div className="stack">
      <button className="btn secondary" onClick={handleClose} style={{ alignSelf: "flex-start" }}>
        ← 홈으로
      </button>

      <section className="card">
        <p className="eyebrow">PERSONAL LEARNING PATH</p>
        <h2>1. 학습 분야에서 나만의 목표까지</h2>
        <div className="field">
          <label htmlFor="wizard-field">학습하고 싶은 분야</label>
          <input
            id="wizard-field"
            value={field}
            onChange={(e) => setField(e.target.value)}
            placeholder="예: UX 디자인, 데이터 분석, 영어 회화"
            disabled={pathStatus === "loading"}
          />
        </div>
        <div className="field">
          <label htmlFor="wizard-goal">학습 목표 (선택)</label>
          <input
            id="wizard-goal"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="예: 백엔드 신입 취업"
            disabled={pathStatus === "loading"}
          />
        </div>
        <button className="btn" onClick={recommend} disabled={!field.trim() || pathStatus === "loading"}>
          {pathStatus === "loading" ? "추천 받는 중…" : recommendation ? "✦ 다시 추천받기" : "✦ AI 세부 과정·수준 추천"}
        </button>
        {pathStatus === "error" && (
          <p className="error" role="alert">
            {pathError}
          </p>
        )}

        {recommendation && (
          <>
            <div className="field" style={{ marginTop: 17 }}>
              <label>2. 추천된 세부 과정 중 하나를 선택하세요</label>
              <div className="chip-row">
                {recommendation.courses.map((c) => (
                  <button
                    type="button"
                    key={c.id}
                    className={`chip${c.id === courseId ? " on" : ""}`}
                    onClick={() => pickCourse(c)}
                  >
                    {c.title}
                  </button>
                ))}
              </div>
              {selectedCourse && (
                <>
                  <label htmlFor="course-title">과정명 (수정 가능)</label>
                  <input id="course-title" value={courseTitle} onChange={(e) => setCourseTitle(e.target.value)} />
                  <label htmlFor="course-description">과정 설명 (수정 가능)</label>
                  <textarea
                    id="course-description"
                    value={courseDescription}
                    onChange={(e) => setCourseDescription(e.target.value)}
                  />
                </>
              )}
            </div>

            {recommendation.suggested_roles.length > 0 && (
              <div className="field">
                <label>추천 직무 (선택)</label>
                <div className="chip-row">
                  {recommendation.suggested_roles.map((role) => (
                    <button
                      type="button"
                      key={role}
                      className={`chip${role === selectedRole ? " on" : ""}`}
                      onClick={() => setSelectedRole(role === selectedRole ? null : role)}
                    >
                      {role}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {selectedCourse && (
              <div className="field">
                <label>3. 현재 수준과 목표 수준 (이름·설명 수정 가능)</label>
                <p className="small muted">수준 번호는 표시하지 않으며, 목표 수준은 현재 수준보다 높은 항목만 선택할 수 있습니다.</p>
                {onlyOneLevelInCourse && (
                  <p className="error" role="alert">
                    이 과정은 수준이 1개뿐이라 목표 수준을 선택할 수 없습니다. 다른 과정을 선택하거나 다시 추천받으세요.
                  </p>
                )}
                <div className="field-grid" style={{ marginTop: 10 }}>
                  <div className="field">
                    <label htmlFor="current-level">현재 수준</label>
                    <select id="current-level" value={currentOrder ?? ""} onChange={(e) => pickCurrentLevel(Number(e.target.value))}>
                      {selectedCourse.levels.map((l) => (
                        <option key={l.order} value={l.order}>
                          {l.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="target-level">도달 목표 수준</label>
                    <select
                      id="target-level"
                      value={targetOrder ?? ""}
                      onChange={(e) => pickTargetLevel(Number(e.target.value))}
                      disabled={targetLevelOptions.length === 0}
                    >
                      {targetLevelOptions.map((l) => (
                        <option key={l.order} value={l.order}>
                          {l.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="field-grid">
                  <div className="field">
                    <label htmlFor="current-level-name">현재 수준 이름</label>
                    <input id="current-level-name" value={currentLevelName} onChange={(e) => setCurrentLevelName(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="target-level-name">목표 수준 이름</label>
                    <input id="target-level-name" value={targetLevelName} onChange={(e) => setTargetLevelName(e.target.value)} />
                  </div>
                </div>
                <div className="field-grid">
                  <div className="field">
                    <label htmlFor="current-level-desc">현재 수준 설명</label>
                    <textarea id="current-level-desc" value={currentLevelDesc} onChange={(e) => setCurrentLevelDesc(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="target-level-desc">목표 수준 설명</label>
                    <textarea id="target-level-desc" value={targetLevelDesc} onChange={(e) => setTargetLevelDesc(e.target.value)} />
                  </div>
                </div>
              </div>
            )}

            <div className="field-grid">
              <div className="field">
                <label htmlFor="weekly-hours">주간 학습 가능 시간(시간)</label>
                <input
                  id="weekly-hours"
                  type="number"
                  min={1}
                  max={100}
                  value={weeklyHours}
                  onChange={(e) => setWeeklyHours(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="target-date">목표 완료 희망일</label>
                <input
                  id="target-date"
                  type="date"
                  min={todayKSTDateString()}
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="plan-week-start">계획 주간 시작일 (월요일)</label>
              <input
                id="plan-week-start"
                type="date"
                value={planWeekStart}
                onChange={(e) => setPlanWeekStart(e.target.value)}
              />
              {!planWeekStartIsMonday && (
                <p className="error" role="alert">
                  계획 주간 시작일은 월요일이어야 합니다.{" "}
                  <button type="button" className="link-btn" onClick={() => setPlanWeekStart(mondayOfThisWeekKST())}>
                    이번 주 월요일로 설정
                  </button>
                </p>
              )}
            </div>

            <button
              className="btn"
              onClick={generatePlan}
              disabled={
                !selectedCourse ||
                currentOrder == null ||
                targetOrder == null ||
                !targetDate ||
                !planWeekStartIsMonday ||
                onlyOneLevelInCourse ||
                planStatus === "loading"
              }
            >
              {planStatus === "loading" ? "계획 만드는 중…" : draft ? "✦ 계획 다시 만들기" : "✦ 과제·조언·참고자료 만들기"}
            </button>
            {planStatus === "error" && (
              <p className="error" role="alert">
                {planError}
              </p>
            )}
            <p className="small muted">생성 결과는 검토·수정 후 저장할 수 있습니다. AI가 생성한 내용이며 정확성을 확인해 주세요.</p>
          </>
        )}
      </section>

      {draft && (
        <section className="card">
          <p className="eyebrow">저장 전 초안</p>
          <h2>AI 학습 설계 미리보기</h2>
          <p className="small muted">
            {draft.plan_week_start} ~ {draft.plan_week_end}
          </p>
          {isDraftStale && (
            <p className="error" role="alert">
              입력 조건이 바뀌어 이 초안은 최신 상태가 아닙니다. 위의 "계획 다시 만들기"로 새로 생성한 뒤 저장하세요.
            </p>
          )}

          <div className="tabs">
            <button
              type="button"
              className={`tab${activeTab === "tasks" ? " active" : ""}`}
              onClick={() => setActiveTab("tasks")}
            >
              학습 과제
            </button>
            <button
              type="button"
              className={`tab${activeTab === "advice" ? " active" : ""}`}
              onClick={() => setActiveTab("advice")}
            >
              조언·인사이트
            </button>
            <button
              type="button"
              className={`tab${activeTab === "refs" ? " active" : ""}`}
              onClick={() => setActiveTab("refs")}
            >
              참고자료
            </button>
          </div>

          {activeTab === "tasks" && (
            <div>
              <p className={overBudget ? "error" : "small muted"} role={overBudget ? "alert" : undefined}>
                총 예상 시간 {totalMinutes}분 / 주당 가능 시간 {weeklyHours * 60}분
                {overBudget && " · 시간이 초과되어 확정할 수 없습니다. 과업을 줄이거나 시간을 조정하세요."}
              </p>
              <p className="small muted">추천 요일은 마감일이 아닙니다. 하루를 놓쳐도 과제가 실패 처리되거나 이월되지 않습니다.</p>
              {tasks.map((t, i) => (
                <div key={i} className="task-edit-row">
                  <input
                    value={t.title}
                    onChange={(e) => updateTask(i, { title: e.target.value })}
                    placeholder="과업 제목"
                  />
                  <textarea
                    value={t.description}
                    onChange={(e) => updateTask(i, { description: e.target.value })}
                    placeholder="과업 설명"
                  />
                  <div className="field-grid">
                    <input
                      type="number"
                      min={1}
                      value={t.estimated_minutes}
                      onChange={(e) => updateTask(i, { estimated_minutes: Number(e.target.value) })}
                      aria-label="예상 학습 시간(분)"
                    />
                    <select
                      value={t.suggested_weekday}
                      onChange={(e) => updateTask(i, { suggested_weekday: e.target.value as Weekday })}
                      aria-label="추천 요일"
                    >
                      {(Object.keys(WEEKDAY_LABEL) as Weekday[]).map((w) => (
                        <option key={w} value={w}>
                          {WEEKDAY_LABEL[w]}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button type="button" className="btn secondary small" onClick={() => removeTask(i)}>
                    과업 삭제
                  </button>
                </div>
              ))}
              <button type="button" className="btn secondary" onClick={addTask}>
                + 과업 추가
              </button>
            </div>
          )}

          {activeTab === "advice" && (
            <div>
              <h3>{draft.advice.title}</h3>
              <p className="description">{draft.advice.content}</p>
            </div>
          )}

          {activeTab === "refs" && (
            <div>
              {draft.references.length > 0 ? (
                <ul>
                  {draft.references.map((r) => (
                    <li key={r.title}>
                      <strong>{r.title}</strong> · {r.category}
                      {r.url && (
                        <>
                          {" · "}
                          <a href={r.url} target="_blank" rel="noreferrer">
                            자료 열기 ↗
                          </a>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="description" style={{ whiteSpace: "pre-line" }}>
                  {draft.references_notice}
                </p>
              )}
            </div>
          )}

          <p className="small muted">모든 AI 생성 결과는 참고용이며 정확성을 직접 확인해 주세요.</p>
          <button
            className="btn"
            style={{ width: "100%", marginTop: 13 }}
            onClick={confirmPlan}
            disabled={!canConfirm || confirmStatus === "saving"}
          >
            {confirmStatus === "saving" ? "저장하는 중…" : "계획과 참고자료 저장"}
          </button>
          {confirmStatus === "error" && (
            <p className="error" role="alert">
              {confirmError} 같은 저장 버튼으로 다시 시도해도 중복 저장되지 않습니다.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
