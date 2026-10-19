"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";

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

type PathStatus = "input" | "loading" | "ready" | "error";
type PlanStatus = "idle" | "loading" | "ready" | "error";
type ConfirmStatus = "idle" | "saving" | "done" | "error";

const AI_TIMEOUT_MS = 45_000;

function mondayOfThisWeek(): string {
  const d = new Date();
  const dayIndex = (d.getDay() + 6) % 7; // Monday = 0
  d.setDate(d.getDate() - dayIndex);
  return d.toISOString().slice(0, 10);
}

export function LearningPathWizard({ onClose }: { onClose: () => void }) {
  const { session } = useAuth();

  // --- Step 1: path setup (분야 -> 과정/수준 추천 -> 선택) ---
  const [field, setField] = useState("");
  const [goal, setGoal] = useState("");
  const [pathStatus, setPathStatus] = useState<PathStatus>("input");
  const [pathError, setPathError] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<PathRecommendationResponse | null>(null);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [currentOrder, setCurrentOrder] = useState<number | null>(null);
  const [targetOrder, setTargetOrder] = useState<number | null>(null);
  const [weeklyHours, setWeeklyHours] = useState(7);
  const [targetDate, setTargetDate] = useState("");
  const [planWeekStart, setPlanWeekStart] = useState(mondayOfThisWeek());

  const selectedCourse = useMemo(
    () => recommendation?.courses.find((c) => c.id === courseId) ?? null,
    [recommendation, courseId],
  );
  const currentLevel = useMemo(
    () => selectedCourse?.levels.find((l) => l.order === currentOrder) ?? null,
    [selectedCourse, currentOrder],
  );
  const targetLevel = useMemo(
    () => selectedCourse?.levels.find((l) => l.order === targetOrder) ?? null,
    [selectedCourse, targetOrder],
  );
  const targetLevelOptions = useMemo(
    () => selectedCourse?.levels.filter((l) => currentOrder == null || l.order > currentOrder) ?? [],
    [selectedCourse, currentOrder],
  );

  function pickCourse(course: CourseItem) {
    setCourseId(course.id);
    setCurrentOrder(course.levels[0]?.order ?? null);
    setTargetOrder(course.levels[1]?.order ?? course.levels[0]?.order ?? null);
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
  const [draft, setDraft] = useState<PlanGenerateResponse | null>(null);
  const [tasks, setTasks] = useState<WeeklyTask[]>([]);
  const [activeTab, setActiveTab] = useState<"tasks" | "advice" | "refs">("tasks");

  async function generatePlan() {
    if (!session || !recommendation || !selectedCourse || !currentLevel || !targetLevel || !targetDate) return;
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
          course: selectedCourse.title,
          selected_role: selectedRole,
          current_level_order: currentLevel.order,
          current_level_name: currentLevel.name,
          current_level_description: currentLevel.description,
          target_level_order: targetLevel.order,
          target_level_name: targetLevel.name,
          target_level_description: targetLevel.description,
          weekly_hours: weeklyHours,
          target_date: targetDate,
          plan_week_start: planWeekStart,
        },
      });
      setDraft(result);
      setTasks(result.tasks);
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

  const canConfirm = Boolean(draft) && !overBudget && tasks.length > 0 && tasks.every((t) => t.title.trim());

  async function confirmPlan() {
    if (!session || !recommendation || !selectedCourse || !currentLevel || !targetLevel || !draft || !canConfirm) return;
    setConfirmStatus("saving");
    setConfirmError(null);
    try {
      const token = await session.getToken();
      await apiRequest("/api/plan/confirm", {
        method: "POST",
        token,
        body: {
          field: recommendation.field,
          course: selectedCourse.title,
          current_level_order: currentLevel.order,
          current_level_name: currentLevel.name,
          current_level_description: currentLevel.description,
          target_level_order: targetLevel.order,
          target_level_name: targetLevel.name,
          target_level_description: targetLevel.description,
          weekly_hours: weeklyHours,
          target_date: targetDate,
          plan_week_start: draft.plan_week_start,
          tasks,
        },
      });
      setConfirmStatus("done");
    } catch (error) {
      setConfirmError(error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.");
      setConfirmStatus("error");
    }
  }

  if (confirmStatus === "done") {
    return (
      <section className="card">
        <p className="eyebrow">PACEMATE · PLAN SAVED</p>
        <h2>학습 계획이 저장되었습니다.</h2>
        <p className="description">목표와 이번 주 과제가 저장되어 언제든 다시 확인할 수 있습니다.</p>
        <button className="btn" onClick={onClose}>
          홈으로 돌아가기
        </button>
      </section>
    );
  }

  return (
    <div className="stack">
      <button className="btn secondary" onClick={onClose} style={{ alignSelf: "flex-start" }}>
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
              {selectedCourse && <p className="small muted">{selectedCourse.description}</p>}
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
                <label>3. 현재 수준과 목표 수준</label>
                <p className="small muted">수준 이름만 표시하며, 목표 수준은 현재 수준보다 높은 항목만 선택할 수 있습니다.</p>
                <div className="field-grid" style={{ marginTop: 10 }}>
                  <div className="field">
                    <label htmlFor="current-level">현재 수준</label>
                    <select
                      id="current-level"
                      value={currentOrder ?? ""}
                      onChange={(e) => {
                        const order = Number(e.target.value);
                        setCurrentOrder(order);
                        if (targetOrder != null && targetOrder <= order) {
                          const next = selectedCourse.levels.find((l) => l.order > order);
                          setTargetOrder(next?.order ?? null);
                        }
                      }}
                    >
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
                      onChange={(e) => setTargetOrder(Number(e.target.value))}
                    >
                      {targetLevelOptions.map((l) => (
                        <option key={l.order} value={l.order}>
                          {l.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <p className="small muted">
                  {currentLevel && `현재: ${currentLevel.description}`}
                  {targetLevel && ` · 목표: ${targetLevel.description}`}
                </p>
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
                <input id="target-date" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
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
            </div>

            <button
              className="btn"
              onClick={generatePlan}
              disabled={!selectedCourse || !currentLevel || !targetLevel || !targetDate || planStatus === "loading"}
            >
              {planStatus === "loading" ? "계획 만드는 중…" : "✦ 과제·조언·참고자료 만들기"}
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
              {confirmError}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
