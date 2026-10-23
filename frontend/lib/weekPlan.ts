/**
 * Pure helpers for the weekly plan screen (Phase 5D, page-wbs): which week to show, moving
 * between weeks, labels, totals and the weekday values. All date arithmetic goes through
 * lib/week.ts; "this week" is always passed in (from mondayOfThisWeekKST()).
 */
import { addDaysToDateString, daysBetweenDateStrings, monthDayLabel } from "@/lib/week";

export type Weekday = "none" | "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export const WEEKDAY_OPTIONS: { value: Weekday; label: string }[] = [
  { value: "none", label: "선택 안 함" },
  { value: "mon", label: "월요일" },
  { value: "tue", label: "화요일" },
  { value: "wed", label: "수요일" },
  { value: "thu", label: "목요일" },
  { value: "fri", label: "금요일" },
  { value: "sat", label: "토요일" },
  { value: "sun", label: "일요일" },
];

export function isWeekday(value: string): value is Weekday {
  return WEEKDAY_OPTIONS.some((o) => o.value === value);
}

/** The value a select element reports -> the API value; anything unexpected becomes "none". */
export function toWeekday(value: string): Weekday {
  return isWeekday(value) ? value : "none";
}

export type PlanTask = {
  id: string;
  title: string;
  description: string;
  estimated_minutes: number;
  suggested_weekday: string;
  status: string;
  plan_week_start: string;
  order_index: number;
};

/** Distinct plan weeks (Monday dates), oldest first. */
export function listWeekStarts(tasks: Pick<PlanTask, "plan_week_start">[]): string[] {
  return [...new Set(tasks.map((t) => t.plan_week_start))].sort();
}

/**
 * The week to open first: this week if it has tasks; otherwise the nearest later week with
 * tasks; if there is none, the last week that has tasks. null when there are no weeks.
 */
export function pickInitialWeek(weekStarts: string[], thisWeek: string): string | null {
  if (weekStarts.length === 0) return null;
  if (weekStarts.includes(thisWeek)) return thisWeek;
  const later = weekStarts.filter((w) => w > thisWeek);
  if (later.length > 0) return later[0];
  return weekStarts[weekStarts.length - 1];
}

/** Previous/next week that has tasks, or null at the ends (the buttons are disabled then). */
export function neighborWeek(weekStarts: string[], current: string, direction: "prev" | "next"): string | null {
  const i = weekStarts.indexOf(current);
  if (i === -1) return null;
  return weekStarts[direction === "prev" ? i - 1 : i + 1] ?? null;
}

/** Whole weeks from this week to `week` (0 = this week, negative = earlier). */
export function weekOffset(week: string, thisWeek: string): number {
  return Math.round(daysBetweenDateStrings(thisWeek, week) / 7);
}

/** Neutral wording only: never "overdue", "late" or similar. */
export function weekRelationLabel(offset: number): string {
  if (offset === 0) return "이번 주";
  if (offset === -1) return "지난 주";
  if (offset === 1) return "다음 주";
  return offset < 0 ? `${-offset}주 전` : `${offset}주 뒤`;
}

/** "10/19–10/25" for the Monday-to-Sunday week starting on `weekStart`. */
export function weekRangeLabel(weekStart: string): string {
  return `${monthDayLabel(weekStart)}–${monthDayLabel(addDaysToDateString(weekStart, 6))}`;
}

export function tasksOfWeek<T extends PlanTask>(tasks: T[], week: string | null): T[] {
  if (!week) return [];
  return tasks.filter((t) => t.plan_week_start === week).sort((a, b) => a.order_index - b.order_index);
}

/** 320 -> "5시간 20분", 420 -> "7시간", 45 -> "45분". */
export function formatHoursMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}분`;
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
}

/** Progress is completed / all tasks of the learning (no time weighting, no scoring). */
export function completionCounts(tasks: Pick<PlanTask, "status">[]): { done: number; total: number; percent: number } {
  const total = tasks.length;
  const done = tasks.filter((t) => t.status === "completed").length;
  return { done, total, percent: total === 0 ? 0 : Math.round((done / total) * 100) };
}

export function totalMinutes(tasks: Pick<PlanTask, "estimated_minutes">[]): number {
  return tasks.reduce((sum, t) => sum + t.estimated_minutes, 0);
}
