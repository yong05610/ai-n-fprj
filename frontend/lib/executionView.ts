// CR-014: pure helpers of the execution screen (weekly target, task description, this-week task filter).

export type ExecutionPeriod = "week" | "all";

/** "주 목표" in minutes = the active learning's weekly_hours x 60 (same value as the dashboard's weekly_target_minutes). null when unknown. */
export function weeklyTargetMinutes(weeklyHours: unknown): number | null {
  return typeof weeklyHours === "number" && Number.isFinite(weeklyHours) && weeklyHours > 0 ? Math.round(weeklyHours * 60) : null;
}

export const ALL_PERIOD_HINT = "이번 주 보기에서 확인";
export const NO_TARGET_HINT = "주 목표를 읽지 못했어요";

export type GoalStat = {
  /** big number text: "44" or "–" when no percent is shown */
  percentText: string;
  /** small line under it */
  detailText: string;
  /** small line of the study-time card */
  targetLine: string;
};

/** The two cards that talk about the weekly target. The percent is only for the week view (the minutes are this week's) and is capped at 100. */
export function goalStat(period: ExecutionPeriod, minutes: number, target: number | null): GoalStat {
  if (period === "all") return { percentText: "–", detailText: ALL_PERIOD_HINT, targetLine: "전체 기간" };
  if (target === null) return { percentText: "–", detailText: NO_TARGET_HINT, targetLine: NO_TARGET_HINT };
  const percent = Math.min(100, Math.round((minutes / target) * 100));
  return { percentText: String(percent), detailText: `${minutes}분 / ${target}분`, targetLine: `주 목표 ${target}분` };
}

export const NO_WEEK_TASKS = "이번 주에 배치된 과제가 없어요. 전체 기간에서 확인하세요";

type WeekTask = { id: string; in_current_week?: boolean | null };

/** Week view: tasks placed this week (the server says so with in_current_week) + tasks with a record this week. All-period view: everything. */
export function visibleTasks<T extends WeekTask>(tasks: T[], period: ExecutionPeriod, logsByTask: Record<string, unknown[] | undefined>): T[] {
  if (period === "all") return tasks;
  // an older server without the field: nothing to filter by, keep showing everything
  return tasks.filter((t) => t.in_current_week !== false || (logsByTask[t.id]?.length ?? 0) > 0);
}

/** Empty description -> no line. */
export function taskDescription(description: unknown): string | null {
  return typeof description === "string" && description.trim() !== "" ? description : null;
}
